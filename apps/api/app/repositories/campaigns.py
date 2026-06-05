from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.campaigns import BulkExport, CampaignPlan, CampaignPlanStatus


class CampaignRepository(ABC):
    @abstractmethod
    def next_plan_version(self, *, workspace_id: UUID, product_id: UUID) -> int:
        raise NotImplementedError

    @abstractmethod
    def create_plan(self, *, plan: CampaignPlan) -> CampaignPlan:
        raise NotImplementedError

    @abstractmethod
    def get_plan(self, *, workspace_id: UUID, plan_id: UUID) -> CampaignPlan | None:
        raise NotImplementedError

    @abstractmethod
    def approve_plan(self, *, workspace_id: UUID, plan_id: UUID, actor_user_id: str, approval_note: str) -> CampaignPlan | None:
        raise NotImplementedError

    @abstractmethod
    def create_export(self, *, export: BulkExport) -> BulkExport:
        raise NotImplementedError

    @abstractmethod
    def get_export(self, *, workspace_id: UUID, export_id: UUID) -> BulkExport | None:
        raise NotImplementedError


class LocalCampaignRepository(CampaignRepository):
    def __init__(self) -> None:
        self._plans: dict[UUID, CampaignPlan] = {}
        self._exports: dict[UUID, BulkExport] = {}

    def next_plan_version(self, *, workspace_id: UUID, product_id: UUID) -> int:
        versions = [plan.version for plan in self._plans.values() if plan.workspace_id == workspace_id and plan.product_id == product_id]
        return (max(versions) if versions else 0) + 1

    def create_plan(self, *, plan: CampaignPlan) -> CampaignPlan:
        self._plans[plan.id] = plan
        return plan

    def get_plan(self, *, workspace_id: UUID, plan_id: UUID) -> CampaignPlan | None:
        plan = self._plans.get(plan_id)
        return plan if plan and plan.workspace_id == workspace_id else None

    def approve_plan(self, *, workspace_id: UUID, plan_id: UUID, actor_user_id: str, approval_note: str) -> CampaignPlan | None:
        plan = self.get_plan(workspace_id=workspace_id, plan_id=plan_id)
        if plan is None:
            return None
        approved = plan.model_copy(
            update={
                "status": CampaignPlanStatus.APPROVED,
                "approved_by": actor_user_id,
                "approval_note": approval_note.strip(),
                "approved_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self._plans[plan_id] = approved
        return approved

    def create_export(self, *, export: BulkExport) -> BulkExport:
        self._exports[export.id] = export
        return export

    def get_export(self, *, workspace_id: UUID, export_id: UUID) -> BulkExport | None:
        export = self._exports.get(export_id)
        return export if export and export.workspace_id == workspace_id else None


class PostgresCampaignRepository(CampaignRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def next_plan_version(self, *, workspace_id: UUID, product_id: UUID) -> int:
        with self._engine.begin() as connection:
            current = connection.execute(
                text("select coalesce(max(version), 0) from campaign_plans where workspace_id = :workspace_id and product_id = :product_id"),
                {"workspace_id": workspace_id, "product_id": product_id},
            ).scalar_one()
        return int(current) + 1

    def create_plan(self, *, plan: CampaignPlan) -> CampaignPlan:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into campaign_plans (
                        id, workspace_id, product_id, approved_keyword_set_id, version, status,
                        rule_version_id, plan_json, created_by, approved_by, approval_note,
                        approved_at, created_at, updated_at
                    )
                    values (
                        :id, :workspace_id, :product_id, :approved_keyword_set_id, :version, :status,
                        :rule_version_id, :plan_json, :created_by, :approved_by, :approval_note,
                        :approved_at, :created_at, :updated_at
                    )
                    returning *
                    """
                ),
                _plan_params(plan),
            ).mappings().one()
        return _plan_from_row(row)

    def get_plan(self, *, workspace_id: UUID, plan_id: UUID) -> CampaignPlan | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from campaign_plans where workspace_id = :workspace_id and id = :plan_id"),
                {"workspace_id": workspace_id, "plan_id": plan_id},
            ).mappings().first()
        return _plan_from_row(row) if row else None

    def approve_plan(self, *, workspace_id: UUID, plan_id: UUID, actor_user_id: str, approval_note: str) -> CampaignPlan | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update campaign_plans
                    set status = 'approved',
                        approved_by = :approved_by,
                        approval_note = :approval_note,
                        approved_at = datetime('now'),
                        updated_at = datetime('now')
                    where workspace_id = :workspace_id and id = :plan_id and status = 'generated'
                    returning *
                    """
                ),
                {"workspace_id": workspace_id, "plan_id": plan_id, "approved_by": _uuid_or_none(actor_user_id), "approval_note": approval_note.strip()},
            ).mappings().first()
        return _plan_from_row(row) if row else None

    def create_export(self, *, export: BulkExport) -> BulkExport:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into bulk_exports (
                        id, workspace_id, product_id, campaign_plan_id, status, storage_path,
                        original_filename, rows_json, approved_by, approval_note, approved_at,
                        created_at, updated_at
                    )
                    values (
                        :id, :workspace_id, :product_id, :campaign_plan_id, :status, :storage_path,
                        :original_filename, :rows_json, :approved_by, :approval_note, :approved_at,
                        :created_at, :updated_at
                    )
                    returning *
                    """
                ),
                _export_params(export),
            ).mappings().one()
        return _export_from_row(row)

    def get_export(self, *, workspace_id: UUID, export_id: UUID) -> BulkExport | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from bulk_exports where workspace_id = :workspace_id and id = :export_id"),
                {"workspace_id": workspace_id, "export_id": export_id},
            ).mappings().first()
        return _export_from_row(row) if row else None


_local_repository = LocalCampaignRepository()


def get_campaign_repository() -> CampaignRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresCampaignRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def new_campaign_plan(
    *,
    workspace_id: UUID,
    product_id: UUID,
    approved_keyword_set_id: UUID,
    version: int,
    plan_json: dict,
    created_by: str,
) -> CampaignPlan:
    now = datetime.now(UTC)
    return CampaignPlan(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        approved_keyword_set_id=approved_keyword_set_id,
        version=version,
        status="generated",
        rule_version_id="campaign_creation_rules_v1",
        plan_json=plan_json,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


def new_bulk_export(
    *,
    workspace_id: UUID,
    product_id: UUID,
    campaign_plan_id: UUID,
    storage_path: str,
    original_filename: str,
    rows_json: list[dict],
    approved_by: str,
    approval_note: str,
) -> BulkExport:
    now = datetime.now(UTC)
    return BulkExport(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        campaign_plan_id=campaign_plan_id,
        status="approved",
        storage_path=storage_path,
        original_filename=original_filename,
        rows_json=rows_json,
        approved_by=approved_by,
        approval_note=approval_note.strip(),
        approved_at=now,
        created_at=now,
        updated_at=now,
    )


def _plan_from_row(row: RowMapping) -> CampaignPlan:
    return CampaignPlan(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        approved_keyword_set_id=row["approved_keyword_set_id"],
        version=row["version"],
        status=row["status"],
        rule_version_id=row["rule_version_id"],
        plan_json=row["plan_json"],
        created_by=str(row["created_by"]),
        approved_by=str(row["approved_by"]) if row["approved_by"] else None,
        approval_note=row["approval_note"],
        approved_at=row["approved_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _export_from_row(row: RowMapping) -> BulkExport:
    return BulkExport(
        id=row["id"],
        workspace_id=row["workspace_id"],
        product_id=row["product_id"],
        campaign_plan_id=row["campaign_plan_id"],
        status=row["status"],
        storage_path=row["storage_path"],
        original_filename=row["original_filename"],
        rows_json=row["rows_json"],
        approved_by=str(row["approved_by"]),
        approval_note=row["approval_note"],
        approved_at=row["approved_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _plan_params(plan: CampaignPlan) -> dict:
    import json

    return {
        "id": plan.id,
        "workspace_id": plan.workspace_id,
        "product_id": plan.product_id,
        "approved_keyword_set_id": plan.approved_keyword_set_id,
        "version": plan.version,
        "status": plan.status.value,
        "rule_version_id": plan.rule_version_id,
        "plan_json": json.dumps(plan.plan_json),
        "created_by": _uuid_or_none(plan.created_by),
        "approved_by": _uuid_or_none(plan.approved_by) if plan.approved_by else None,
        "approval_note": plan.approval_note,
        "approved_at": plan.approved_at,
        "created_at": plan.created_at,
        "updated_at": plan.updated_at,
    }


def _export_params(export: BulkExport) -> dict:
    import json

    return {
        "id": export.id,
        "workspace_id": export.workspace_id,
        "product_id": export.product_id,
        "campaign_plan_id": export.campaign_plan_id,
        "status": export.status.value,
        "storage_path": export.storage_path,
        "original_filename": export.original_filename,
        "rows_json": json.dumps(export.rows_json),
        "approved_by": _uuid_or_none(export.approved_by),
        "approval_note": export.approval_note,
        "approved_at": export.approved_at,
        "created_at": export.created_at,
        "updated_at": export.updated_at,
    }


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None
