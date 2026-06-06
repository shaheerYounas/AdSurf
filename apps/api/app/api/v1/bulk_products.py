"""Bulk product profile import API.

POST   /v1/workspaces/{workspace_id}/products/bulk-import
  — Upload a CSV/XLSX file and get a validation preview (no products created yet).

GET    /v1/workspaces/{workspace_id}/products/bulk-import/{import_id}
  — Retrieve the full import record with all rows (for the review step).

POST   /v1/workspaces/{workspace_id}/products/bulk-import/{import_id}/commit
  — Actually create products for all valid rows.

GET    /v1/workspaces/{workspace_id}/products/bulk-import
  — List recent bulk imports for this workspace.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Body, Depends, File, Form, UploadFile, status
from sqlalchemy.engine import Engine
from sqlalchemy import text

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.product_profiles import ProductProfileRepository, get_product_profile_repository
from apps.api.app.schemas.bulk_product_import import (
    BulkImportConflictStrategy,
    BulkImportRowStatus,
    BulkImportStatus,
    BulkProductImport,
    BulkProductImportCommitRequest,
    BulkProductImportSummary,
    BulkProductImportWithRows,
    BulkProductRow,
    BulkProductRowValidationError,
)
from apps.api.app.schemas.envelope import success_response
from apps.api.app.schemas.product_profiles import ProductProfileCreate, ProductProfileUpdate
from apps.api.app.services.bulk_product_import_service import BulkProductImportParseError, BulkProductImportService

router = APIRouter()

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


# ─── Upload + validate ────────────────────────────────────────────────────────


@router.post(
    "/workspaces/{workspace_id}/products/bulk-import",
    status_code=status.HTTP_201_CREATED,
    summary="Parse and validate a bulk product import file",
)
async def create_bulk_product_import(
    workspace_id: UUID,
    file: UploadFile = File(...),
    conflict_strategy: BulkImportConflictStrategy = Form(default=BulkImportConflictStrategy.SKIP_EXISTING),
    workspace_default_acos: float | None = Form(default=None),
    workspace_default_budget: float | None = Form(default=None),
    workspace_default_bid: float | None = Form(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    # Validate file type
    filename = file.filename or "upload.csv"
    if not filename.lower().endswith((".csv", ".xlsx", ".tsv")):
        raise ApiError(
            code="UNSUPPORTED_FILE_TYPE",
            message="Only CSV, TSV, and XLSX files are supported for bulk product import.",
            status_code=400,
        )

    # Read content
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ApiError(
            code="FILE_TOO_LARGE",
            message=f"File exceeds the {MAX_FILE_SIZE_BYTES // 1024 // 1024} MB limit.",
            status_code=413,
        )
    if not content.strip():
        raise ApiError(code="EMPTY_FILE", message="The uploaded file is empty.", status_code=400)

    # Workspace defaults
    ws_defaults: dict = {}
    if workspace_default_acos is not None:
        ws_defaults["target_acos"] = Decimal(str(workspace_default_acos))
    if workspace_default_budget is not None:
        ws_defaults["default_budget"] = Decimal(str(workspace_default_budget))
    if workspace_default_bid is not None:
        ws_defaults["default_bid"] = Decimal(str(workspace_default_bid))

    # Run service
    service = BulkProductImportService()
    try:
        rows, column_mapping, file_hash = service.parse_and_validate(
            content=content,
            filename=filename,
            workspace_defaults=ws_defaults,
        )
    except BulkProductImportParseError as exc:
        details: dict = {}
        if exc.code == "SP_REPORT_DETECTED":
            details = {
                "redirect_to": "monitoring_import",
                "hint": "Use Monitoring Import to analyse this file and get keyword recommendations.",
            }
        raise ApiError(
            code=exc.code,
            message=exc.message,
            status_code=exc.status_code,
            details=details or None,
        ) from exc
    except Exception as exc:
        raise ApiError(
            code="PARSE_FAILED",
            message=f"Could not parse file: {exc}",
            status_code=422,
        ) from exc

    # Check for previously imported file (idempotency)
    existing_import_id = _find_existing_import(workspace_id, file_hash)
    if existing_import_id:
        raise ApiError(
            code="DUPLICATE_FILE",
            message=f"This file was already imported (import_id: {existing_import_id}). Use the existing import or choose a different file.",
            status_code=409,
            details={"existing_import_id": str(existing_import_id)},
        )

    # Check for existing products in workspace
    existing_products = product_repository.list(workspace_id=workspace_id)
    existing_by_asin = {p.asin.upper(): p.id for p in existing_products if p.asin}
    existing_by_sku = {p.sku.upper(): p.id for p in existing_products if p.sku}

    rows = service.check_workspace_conflicts(
        rows=rows,
        existing_by_asin=existing_by_asin,
        existing_by_sku=existing_by_sku,
        conflict_strategy=conflict_strategy,
    )

    # Persist import record + rows
    import_id = _persist_import(
        workspace_id=workspace_id,
        filename=filename,
        file_hash=file_hash,
        conflict_strategy=conflict_strategy,
        rows=rows,
        column_mapping=column_mapping,
        ws_defaults=ws_defaults,
        actor_user_id=principal.user_id,
    )

    # Build summary
    counts = service.summarise(rows)
    exception_rows = [r for r in rows if r.status not in (BulkImportRowStatus.VALID,)]
    exportable_valid = counts.get(BulkImportRowStatus.VALID.value, 0)
    rows_to_update = sum(1 for row in rows if row.status == BulkImportRowStatus.VALID and row.product_id)
    rows_to_create = exportable_valid - rows_to_update
    rows_to_skip = (
        counts.get(BulkImportRowStatus.INVALID.value, 0)
        + counts.get(BulkImportRowStatus.DUPLICATE_IN_FILE.value, 0)
        + counts.get(BulkImportRowStatus.ALREADY_EXISTS.value, 0)
    )

    summary = BulkProductImportSummary(
        import_id=import_id,
        status=BulkImportStatus.READY_FOR_REVIEW,
        total_rows=len(rows),
        valid_rows=exportable_valid,
        invalid_rows=counts.get(BulkImportRowStatus.INVALID.value, 0),
        duplicate_in_file_rows=counts.get(BulkImportRowStatus.DUPLICATE_IN_FILE.value, 0),
        already_exists_rows=counts.get(BulkImportRowStatus.ALREADY_EXISTS.value, 0),
        rows_needing_review=(
            counts.get(BulkImportRowStatus.INVALID.value, 0)
            + counts.get(BulkImportRowStatus.DUPLICATE_IN_FILE.value, 0)
            + counts.get(BulkImportRowStatus.ALREADY_EXISTS.value, 0)
        ),
        exportable_valid_rows=exportable_valid,
        rows_to_create=rows_to_create,
        rows_to_update=rows_to_update,
        rows_to_skip=rows_to_skip,
        warning_rows=0,
        detected_columns=column_mapping,
        exception_rows=exception_rows[:50],  # limit for UI
    )

    return success_response(data=summary.model_dump(mode="json"))


# ─── Get import detail ────────────────────────────────────────────────────────


@router.get(
    "/workspaces/{workspace_id}/products/bulk-import/{import_id}",
    summary="Get bulk import record with all rows",
)
def get_bulk_product_import(
    workspace_id: UUID,
    import_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)

    record = _load_import_with_rows(workspace_id, import_id)
    if not record:
        raise ApiError(code="NOT_FOUND", message="Bulk import not found.", status_code=404)

    return success_response(data=record.model_dump(mode="json"))


# ─── Commit (create products) ─────────────────────────────────────────────────


@router.post(
    "/workspaces/{workspace_id}/products/bulk-import/{import_id}/commit",
    summary="Create product profiles from validated bulk import",
)
def commit_bulk_product_import(
    workspace_id: UUID,
    import_id: UUID,
    request_body: BulkProductImportCommitRequest | None = Body(default=None),
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    product_repository: ProductProfileRepository = Depends(get_product_profile_repository),
) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    record = _load_import_with_rows(workspace_id, import_id)
    if not record:
        raise ApiError(code="NOT_FOUND", message="Bulk import not found.", status_code=404)

    if record.status not in (BulkImportStatus.READY_FOR_REVIEW, BulkImportStatus.VALIDATING):
        raise ApiError(
            code="INVALID_IMPORT_STATUS",
            message=f"Import is in status '{record.status}'. Only ready_for_review imports can be committed.",
            status_code=409,
        )

    if not _claim_import_for_commit(workspace_id, import_id):
        current = _load_import_with_rows(workspace_id, import_id)
        current_status = current.status if current else "unknown"
        raise ApiError(
            code="INVALID_IMPORT_STATUS",
            message=f"Import is in status '{current_status}'. Only ready_for_review imports can be committed.",
            status_code=409,
        )

    conflict_strategy = request_body.conflict_strategy if request_body else record.conflict_strategy
    created_ids: list[str] = []
    updated_ids: list[str] = []
    skipped_ids: list[str] = []
    failed_ids: list[str] = []

    existing_products = product_repository.list(workspace_id=workspace_id)
    existing_by_asin = {p.asin.upper(): p for p in existing_products if p.asin}
    existing_by_sku = {p.sku.upper(): p for p in existing_products if p.sku}

    for row in record.rows:
        if row.status != BulkImportRowStatus.VALID:
            skipped_ids.append(str(row.id))
            continue

        try:
            existing_product = _existing_product_for_row(row=row, existing_by_asin=existing_by_asin, existing_by_sku=existing_by_sku)
            if existing_product and conflict_strategy in (
                BulkImportConflictStrategy.SKIP_EXISTING,
                BulkImportConflictStrategy.CREATE_ONLY_MISSING,
            ):
                skipped_ids.append(str(row.id))
                _update_row_status(row.id, BulkImportRowStatus.SKIPPED, product_id=existing_product.id)
                _emit_audit_event(
                    workspace_id,
                    "product_skipped_duplicate",
                    "product_profiles",
                    str(existing_product.id),
                    {"import_id": str(import_id), "asin": row.asin, "sku": row.sku, "strategy": conflict_strategy.value},
                    principal.user_id,
                )
                continue

            if existing_product and conflict_strategy == BulkImportConflictStrategy.UPDATE_EXISTING:
                product = product_repository.update(
                    workspace_id=workspace_id,
                    product_id=existing_product.id,
                    payload=ProductProfileUpdate(**_row_product_payload(row, include_missing_identity=False)),
                    actor_user_id=principal.user_id,
                )
                if product is None:
                    raise RuntimeError("Existing product disappeared before update.")
                updated_ids.append(str(product.id))
                _update_row_status(row.id, BulkImportRowStatus.UPDATED, product_id=product.id)
                _emit_audit_event(
                    workspace_id,
                    "product_updated",
                    "product_profiles",
                    str(product.id),
                    {"import_id": str(import_id), "asin": row.asin, "sku": row.sku},
                    principal.user_id,
                )
                if product.asin:
                    existing_by_asin[product.asin.upper()] = product
                if product.sku:
                    existing_by_sku[product.sku.upper()] = product
                continue

            product = product_repository.create(
                workspace_id=workspace_id,
                payload=ProductProfileCreate(**_row_product_payload(row, include_missing_identity=True)),
                actor_user_id=principal.user_id,
            )
            created_ids.append(str(product.id))
            if product.asin:
                existing_by_asin[product.asin.upper()] = product
            if product.sku:
                existing_by_sku[product.sku.upper()] = product
            _update_row_status(row.id, BulkImportRowStatus.CREATED, product_id=product.id)
            _emit_audit_event(
                workspace_id,
                "product_created",
                "product_profiles",
                str(product.id),
                {"import_id": str(import_id), "asin": row.asin, "sku": row.sku},
                principal.user_id,
            )
        except Exception as exc:
            failed_ids.append(str(row.id))
            _update_row_status(
                row.id,
                BulkImportRowStatus.FAILED,
                validation_errors=[
                    *row.validation_errors,
                    BulkProductRowValidationError(field="row", message="Product profile could not be created or updated."),
                ],
            )
            _emit_audit_event(
                workspace_id,
                "product_validation_failed",
                "bulk_product_import_rows",
                str(row.id),
                {"import_id": str(import_id), "error": _safe_error_message(exc)},
                principal.user_id,
            )

    # Final status
    final_status = BulkImportStatus.COMPLETED if not failed_ids else BulkImportStatus.COMPLETED
    _update_import_status(
        import_id,
        final_status,
        created=len(created_ids),
        updated=len(updated_ids),
        skipped=len(skipped_ids),
        failed=len(failed_ids),
    )
    _emit_audit_event(workspace_id, "bulk_product_import_completed", "bulk_product_imports", str(import_id),
                      {"created": len(created_ids), "updated": len(updated_ids), "skipped": len(skipped_ids), "failed": len(failed_ids)}, principal.user_id)

    return success_response(data={
        "import_id": str(import_id),
        "status": final_status.value,
        "created_count": len(created_ids),
        "updated_count": len(updated_ids),
        "skipped_count": len(skipped_ids),
        "failed_count": len(failed_ids),
        "created_product_ids": created_ids,
        "updated_product_ids": updated_ids,
    })


# ─── List recent imports ──────────────────────────────────────────────────────


@router.get(
    "/workspaces/{workspace_id}/products/bulk-import",
    summary="List bulk product imports for workspace",
)
def list_bulk_product_imports(
    workspace_id: UUID,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
) -> dict:
    principal.ensure_workspace(workspace_id)
    records = _list_imports(workspace_id)
    return success_response(
        data=[r.model_dump(mode="json") for r in records],
        meta={"total": len(records)},
    )


def _row_product_payload(row: BulkProductRow, *, include_missing_identity: bool) -> dict:
    payload = {
        "product_name": row.product_name or "Unnamed product",
        "marketplace": row.marketplace or "US",
        "currency": row.currency or "USD",
        "target_acos": row.target_acos or Decimal("0.5000"),
        "default_budget": row.default_budget or Decimal("10.0000"),
        "default_bid": row.default_bid or Decimal("1.0000"),
    }
    if include_missing_identity or row.asin is not None:
        payload["asin"] = row.asin
    if include_missing_identity or row.sku is not None:
        payload["sku"] = row.sku
    if row.brand is not None:
        payload["brand_name"] = row.brand
    if row.category is not None:
        payload["category"] = row.category
    return payload


def _existing_product_for_row(*, row: BulkProductRow, existing_by_asin: dict, existing_by_sku: dict):
    if row.asin and row.asin.upper() in existing_by_asin:
        return existing_by_asin[row.asin.upper()]
    if row.sku and row.sku.upper() in existing_by_sku:
        return existing_by_sku[row.sku.upper()]
    return None


def _safe_error_message(exc: Exception) -> str:
    return str(exc).replace("\n", " ")[:300]


# ─── DB helpers (SQLite + Postgres compatible via raw SQL) ────────────────────


def _find_existing_import(workspace_id: UUID, file_hash: str | None) -> UUID | None:
    if not file_hash:
        return None
    try:
        engine = get_database_engine()
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT id FROM bulk_product_imports WHERE workspace_id = :wid AND file_hash = :hash LIMIT 1"),
                {"wid": str(workspace_id), "hash": file_hash},
            ).mappings().first()
        return UUID(str(row["id"])) if row else None
    except Exception:
        return None


def _persist_import(
    *,
    workspace_id: UUID,
    filename: str,
    file_hash: str,
    conflict_strategy: BulkImportConflictStrategy,
    rows: list[BulkProductRow],
    column_mapping: dict,
    ws_defaults: dict,
    actor_user_id,
) -> UUID:
    import json as _json

    import_id = uuid4()
    counts = {s.value: 0 for s in BulkImportRowStatus}
    for row in rows:
        counts[row.status.value] += 1

    engine = get_database_engine()
    now_sql = _now_sql(engine)
    json_param = _json_param(engine)
    with engine.begin() as conn:
        conn.execute(
            text(f"""
                INSERT INTO bulk_product_imports (
                    id, workspace_id, original_filename, file_hash,
                    status, conflict_strategy,
                    total_rows, valid_rows, invalid_rows,
                    duplicate_in_file_rows, already_exists_rows,
                    detected_columns_json,
                    workspace_default_acos, workspace_default_budget, workspace_default_bid,
                    created_by, created_at, updated_at
                ) VALUES (
                    :id, :wid, :filename, :file_hash,
                    :status, :strategy,
                    :total, :valid, :invalid,
                    :dup_file, :dup_ws,
                    {json_param(":cols")},
                    :def_acos, :def_budget, :def_bid,
                    :created_by, {now_sql}, {now_sql}
                )
            """),
            {
                "id": str(import_id),
                "wid": str(workspace_id),
                "filename": filename,
                "file_hash": file_hash,
                "status": BulkImportStatus.READY_FOR_REVIEW.value,
                "strategy": conflict_strategy.value,
                "total": len(rows),
                "valid": counts.get(BulkImportRowStatus.VALID.value, 0),
                "invalid": counts.get(BulkImportRowStatus.INVALID.value, 0),
                "dup_file": counts.get(BulkImportRowStatus.DUPLICATE_IN_FILE.value, 0),
                "dup_ws": counts.get(BulkImportRowStatus.ALREADY_EXISTS.value, 0),
                "cols": _json.dumps(column_mapping),
                "def_acos": str(ws_defaults.get("target_acos", "")) or None,
                "def_budget": str(ws_defaults.get("default_budget", "")) or None,
                "def_bid": str(ws_defaults.get("default_bid", "")) or None,
                "created_by": str(actor_user_id) if actor_user_id else None,
            },
        )

        for row in rows:
            conn.execute(
                text(f"""
                    INSERT INTO bulk_product_import_rows (
                        id, workspace_id, import_id, row_number, status,
                        product_name, asin, sku, marketplace, currency,
                        target_acos, default_budget, default_bid,
                        brand, category, notes,
                        validation_errors, raw_row_json, created_at
                    ) VALUES (
                        :id, :wid, :import_id, :row_num, :status,
                        :product_name, :asin, :sku, :marketplace, :currency,
                        :target_acos, :default_budget, :default_bid,
                        :brand, :category, :notes,
                        {json_param(":errors")}, {json_param(":raw")}, {now_sql}
                    )
                """),
                {
                    "id": str(row.id),
                    "wid": str(workspace_id),
                    "import_id": str(import_id),
                    "row_num": row.row_number,
                    "status": row.status.value,
                    "product_name": row.product_name,
                    "asin": row.asin,
                    "sku": row.sku,
                    "marketplace": row.marketplace,
                    "currency": row.currency,
                    "target_acos": str(row.target_acos) if row.target_acos else None,
                    "default_budget": str(row.default_budget) if row.default_budget else None,
                    "default_bid": str(row.default_bid) if row.default_bid else None,
                    "brand": row.brand,
                    "category": row.category,
                    "notes": row.notes,
                    "errors": _json.dumps([e.model_dump() for e in row.validation_errors]),
                    "raw": _json.dumps(row.raw_row_json),
                },
            )

    return import_id


def _load_import_with_rows(workspace_id: UUID, import_id: UUID) -> BulkProductImportWithRows | None:
    import json as _json

    engine = get_database_engine()
    with engine.connect() as conn:
        imp_row = conn.execute(
            text("SELECT * FROM bulk_product_imports WHERE id = :id AND workspace_id = :wid"),
            {"id": str(import_id), "wid": str(workspace_id)},
        ).mappings().first()
        if not imp_row:
            return None

        row_rows = conn.execute(
            text("SELECT * FROM bulk_product_import_rows WHERE import_id = :id AND workspace_id = :wid ORDER BY row_number"),
            {"id": str(import_id), "wid": str(workspace_id)},
        ).mappings().all()

    def _parse_errors(raw) -> list[BulkProductRowValidationError]:
        try:
            data = raw if isinstance(raw, list) else _json.loads(raw or "[]")
            return [BulkProductRowValidationError(**e) for e in data]
        except Exception:
            return []

    rows = [
        BulkProductRow(
            id=r["id"],
            row_number=r["row_number"],
            status=r["status"],
            product_name=r["product_name"],
            asin=r["asin"],
            sku=r["sku"],
            marketplace=r["marketplace"],
            currency=r["currency"],
            target_acos=r["target_acos"],
            default_budget=r["default_budget"],
            default_bid=r["default_bid"],
            brand=r["brand"],
            category=r["category"],
            notes=r["notes"],
            product_id=r["product_id"],
            validation_errors=_parse_errors(r["validation_errors"]),
            raw_row_json=_json_value(r["raw_row_json"], {}),
        )
        for r in row_rows
    ]

    imp = imp_row
    return BulkProductImportWithRows(
        id=imp["id"],
        workspace_id=imp["workspace_id"],
        upload_id=_mapping_get(imp, "upload_id"),
        original_filename=imp["original_filename"],
        file_hash=_mapping_get(imp, "file_hash"),
        status=imp["status"],
        conflict_strategy=imp["conflict_strategy"],
        total_rows=imp["total_rows"],
        valid_rows=imp["valid_rows"],
        invalid_rows=imp["invalid_rows"],
        duplicate_in_file_rows=imp["duplicate_in_file_rows"],
        already_exists_rows=imp["already_exists_rows"],
        created_rows=_mapping_get(imp, "created_rows", 0),
        updated_rows=_mapping_get(imp, "updated_rows", 0),
        skipped_rows=_mapping_get(imp, "skipped_rows", 0),
        failed_rows=_mapping_get(imp, "failed_rows", 0),
        detected_columns_json=_json_value(_mapping_get(imp, "detected_columns_json"), {}),
        workspace_default_acos=_mapping_get(imp, "workspace_default_acos"),
        workspace_default_budget=_mapping_get(imp, "workspace_default_budget"),
        workspace_default_bid=_mapping_get(imp, "workspace_default_bid"),
        error_message=_mapping_get(imp, "error_message"),
        created_at=imp["created_at"],
        updated_at=imp["updated_at"],
        rows=rows,
    )


def _list_imports(workspace_id: UUID) -> list[BulkProductImport]:
    engine = get_database_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM bulk_product_imports WHERE workspace_id = :wid ORDER BY created_at DESC LIMIT 50"),
            {"wid": str(workspace_id)},
        ).mappings().all()

    return [
        BulkProductImport(
            id=r["id"],
            workspace_id=r["workspace_id"],
            upload_id=_mapping_get(r, "upload_id"),
            original_filename=r["original_filename"],
            file_hash=_mapping_get(r, "file_hash"),
            status=r["status"],
            conflict_strategy=r["conflict_strategy"],
            total_rows=r["total_rows"],
            valid_rows=r["valid_rows"],
            invalid_rows=r["invalid_rows"],
            duplicate_in_file_rows=r["duplicate_in_file_rows"],
            already_exists_rows=r["already_exists_rows"],
            created_rows=_mapping_get(r, "created_rows", 0),
            updated_rows=_mapping_get(r, "updated_rows", 0),
            skipped_rows=_mapping_get(r, "skipped_rows", 0),
            failed_rows=_mapping_get(r, "failed_rows", 0),
            detected_columns_json=_json_value(_mapping_get(r, "detected_columns_json"), {}),
            workspace_default_acos=_mapping_get(r, "workspace_default_acos"),
            workspace_default_budget=_mapping_get(r, "workspace_default_budget"),
            workspace_default_bid=_mapping_get(r, "workspace_default_bid"),
            error_message=_mapping_get(r, "error_message"),
            created_at=r["created_at"],
            updated_at=r["updated_at"],
        )
        for r in rows
    ]


def _json_value(value, fallback):
    import json as _json

    if value is None:
        return fallback
    if isinstance(value, str):
        try:
            return _json.loads(value)
        except Exception:
            return fallback
    return value


def _mapping_get(row, key: str, default=None):
    try:
        return row[key]
    except Exception:
        return default


def _claim_import_for_commit(workspace_id: UUID, import_id: UUID) -> bool:
    engine = get_database_engine()
    now_sql = _now_sql(engine)
    with engine.begin() as conn:
        result = conn.execute(
            text(f"""
                UPDATE bulk_product_imports
                SET status = :creating, updated_at = {now_sql}
                WHERE id = :id
                  AND workspace_id = :wid
                  AND status IN (:ready, :validating)
            """),
            {
                "creating": BulkImportStatus.CREATING.value,
                "id": str(import_id),
                "wid": str(workspace_id),
                "ready": BulkImportStatus.READY_FOR_REVIEW.value,
                "validating": BulkImportStatus.VALIDATING.value,
            },
        )
    return result.rowcount == 1


def _update_import_status(
    import_id: UUID,
    status: BulkImportStatus,
    *,
    created: int = 0,
    updated: int = 0,
    skipped: int = 0,
    failed: int = 0,
) -> None:
    try:
        engine = get_database_engine()
        now_sql = _now_sql(engine)
        with engine.begin() as conn:
            try:
                conn.execute(
                    text(f"""
                    UPDATE bulk_product_imports
                    SET status = :status, created_rows = :created, updated_rows = :updated, skipped_rows = :skipped,
                        failed_rows = :failed, updated_at = {now_sql}
                    WHERE id = :id
                """),
                    {"status": status.value, "created": created, "updated": updated, "skipped": skipped, "failed": failed, "id": str(import_id)},
                )
            except Exception:
                conn.execute(
                    text(f"""
                        UPDATE bulk_product_imports
                        SET status = :status, created_rows = :created, skipped_rows = :skipped,
                            failed_rows = :failed, updated_at = {now_sql}
                        WHERE id = :id
                    """),
                    {"status": status.value, "created": created, "skipped": skipped, "failed": failed, "id": str(import_id)},
                )
    except Exception:
        pass  # Non-fatal — commit already happened


def _update_row_status(
    row_id: UUID,
    status: BulkImportRowStatus,
    product_id: UUID | None = None,
    validation_errors: list[BulkProductRowValidationError] | None = None,
) -> None:
    import json as _json

    try:
        engine = get_database_engine()
        json_param = _json_param(engine)
        if validation_errors is None:
            statement = text("UPDATE bulk_product_import_rows SET status = :status, product_id = :pid WHERE id = :id")
            params = {"status": status.value, "pid": str(product_id) if product_id else None, "id": str(row_id)}
        else:
            statement = text(
                f"""
                UPDATE bulk_product_import_rows
                SET status = :status, product_id = :pid, validation_errors = {json_param(":errors")}
                WHERE id = :id
                """
            )
            params = {
                "status": status.value,
                "pid": str(product_id) if product_id else None,
                "id": str(row_id),
                "errors": _json.dumps([error.model_dump() for error in validation_errors]),
            }
        with engine.begin() as conn:
            conn.execute(statement, params)
    except Exception:
        pass


def _emit_audit_event(
    workspace_id: UUID,
    event_type: str,
    object_type: str,
    object_id: str,
    metadata: dict,
    actor_user_id,
) -> None:
    import json as _json
    try:
        engine = get_database_engine()
        now_sql = _now_sql(engine)
        json_param = _json_param(engine)
        with engine.begin() as conn:
            conn.execute(
                text(f"""
                    INSERT INTO audit_logs (id, workspace_id, actor_user_id, event_type, object_type, object_id, metadata_json, created_at)
                    VALUES (:id, :wid, :actor, :event, :obj_type, :obj_id, {json_param(":meta")}, {now_sql})
                """),
                {
                    "id": str(uuid4()),
                    "wid": str(workspace_id),
                    "actor": str(actor_user_id) if actor_user_id else None,
                    "event": event_type,
                    "obj_type": object_type,
                    "obj_id": object_id,
                    "meta": _json.dumps(metadata),
                },
            )
    except Exception:
        pass


def _now_sql(engine: Engine) -> str:
    return "datetime('now')" if engine.dialect.name == "sqlite" else "NOW()"


def _json_param(engine: Engine):
    if engine.dialect.name == "sqlite":
        return lambda name: name
    return lambda name: f"CAST({name} AS JSONB)"
