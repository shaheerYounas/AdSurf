from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.performance import get_pooled_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.monitoring import (
    AiRun,
    MonitoringImport,
    MonitoringImportStatus,
    MonitoringSnapshot,
    Recommendation,
    RecommendationDecision,
    RecommendationStatus,
)


class MonitoringRepository(ABC):
    @abstractmethod
    def create_import(self, *, import_record: MonitoringImport) -> MonitoringImport:
        raise NotImplementedError

    @abstractmethod
    def get_import(self, *, workspace_id: UUID, monitoring_import_id: UUID) -> MonitoringImport | None:
        raise NotImplementedError

    @abstractmethod
    def list_imports(self, *, workspace_id: UUID, product_id: UUID | None = None) -> list[MonitoringImport]:
        raise NotImplementedError

    @abstractmethod
    def update_import(
        self,
        *,
        workspace_id: UUID,
        monitoring_import_id: UUID,
        status: MonitoringImportStatus,
        total_rows: int | None = None,
        processed_rows: int | None = None,
        error_rows: int | None = None,
        date_range_start: str | None = None,
        date_range_end: str | None = None,
        data_quality_warnings_json: list[dict] | None = None,
        error_message: str | None = None,
    ) -> MonitoringImport | None:
        raise NotImplementedError

    @abstractmethod
    def insert_snapshots(self, *, snapshots: list[MonitoringSnapshot]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_snapshots(self, *, workspace_id: UUID, product_id: UUID | None = None, monitoring_import_id: UUID | None = None) -> list[MonitoringSnapshot]:
        raise NotImplementedError

    @abstractmethod
    def insert_recommendations(self, *, recommendations: list[Recommendation]) -> None:
        raise NotImplementedError

    @abstractmethod
    def list_recommendations(
        self,
        *,
        workspace_id: UUID,
        product_id: UUID | None = None,
        status: RecommendationStatus | None = None,
        recommendation_type: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Recommendation]:
        raise NotImplementedError

    @abstractmethod
    def get_recommendation(self, *, workspace_id: UUID, recommendation_id: UUID) -> Recommendation | None:
        raise NotImplementedError

    @abstractmethod
    def decide_recommendation(
        self,
        *,
        workspace_id: UUID,
        recommendation_id: UUID,
        decision: RecommendationStatus,
        actor_user_id: str,
        note: str,
    ) -> tuple[Recommendation | None, RecommendationDecision | None]:
        raise NotImplementedError

    @abstractmethod
    def insert_ai_run(self, *, ai_run: AiRun) -> AiRun:
        raise NotImplementedError

    @abstractmethod
    def latest_ai_run(self, *, workspace_id: UUID, agent_name: str) -> AiRun | None:
        raise NotImplementedError

    @abstractmethod
    def list_ai_runs(self, *, workspace_id: UUID, product_id: UUID | None = None, agent_name: str | None = None, limit: int | None = None) -> list[AiRun]:
        raise NotImplementedError

    @abstractmethod
    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        raise NotImplementedError


class LocalMonitoringRepository(MonitoringRepository):
    def __init__(self) -> None:
        self._imports: dict[UUID, MonitoringImport] = {}
        self._snapshots: dict[UUID, MonitoringSnapshot] = {}
        self._recommendations: dict[UUID, Recommendation] = {}
        self._decisions: dict[UUID, RecommendationDecision] = {}
        self._ai_runs: dict[UUID, AiRun] = {}

    def create_import(self, *, import_record: MonitoringImport) -> MonitoringImport:
        self._imports[import_record.id] = import_record
        return import_record

    def get_import(self, *, workspace_id: UUID, monitoring_import_id: UUID) -> MonitoringImport | None:
        item = self._imports.get(monitoring_import_id)
        return item if item and item.workspace_id == workspace_id else None

    def list_imports(self, *, workspace_id: UUID, product_id: UUID | None = None) -> list[MonitoringImport]:
        items = [item for item in self._imports.values() if item.workspace_id == workspace_id and (product_id is None or item.product_id == product_id)]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def update_import(self, **kwargs) -> MonitoringImport | None:
        current = self.get_import(workspace_id=kwargs["workspace_id"], monitoring_import_id=kwargs["monitoring_import_id"])
        if current is None:
            return None
        updates = {"status": kwargs["status"], "updated_at": datetime.now(UTC)}
        for key in ["total_rows", "processed_rows", "error_rows", "date_range_start", "date_range_end", "data_quality_warnings_json", "error_message"]:
            if kwargs.get(key) is not None:
                updates[key] = kwargs[key]
        updated = current.model_copy(update=updates)
        self._imports[updated.id] = updated
        return updated

    def insert_snapshots(self, *, snapshots: list[MonitoringSnapshot]) -> None:
        for snapshot in snapshots:
            self._snapshots[snapshot.id] = snapshot

    def list_snapshots(self, *, workspace_id: UUID, product_id: UUID | None = None, monitoring_import_id: UUID | None = None) -> list[MonitoringSnapshot]:
        return [
            item
            for item in self._snapshots.values()
            if item.workspace_id == workspace_id
            and (product_id is None or item.product_id == product_id)
            and (monitoring_import_id is None or item.monitoring_import_id == monitoring_import_id)
        ]

    def insert_recommendations(self, *, recommendations: list[Recommendation]) -> None:
        for recommendation in recommendations:
            self._recommendations[recommendation.id] = recommendation

    def list_recommendations(self, *, workspace_id: UUID, product_id: UUID | None = None, status: RecommendationStatus | None = None, recommendation_type: str | None = None, limit: int | None = None, offset: int = 0) -> list[Recommendation]:
        items = [
            item
            for item in self._recommendations.values()
            if item.workspace_id == workspace_id
            and (product_id is None or item.product_id == product_id)
            and (status is None or item.status == status)
            and (recommendation_type is None or item.recommendation_type == recommendation_type)
        ]
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        sorted_items = sorted(items, key=lambda item: (priority_order.get(str(item.priority), 9), item.created_at))
        return sorted_items[offset : offset + limit] if limit is not None else sorted_items[offset:]

    def get_recommendation(self, *, workspace_id: UUID, recommendation_id: UUID) -> Recommendation | None:
        item = self._recommendations.get(recommendation_id)
        return item if item and item.workspace_id == workspace_id else None

    def decide_recommendation(self, *, workspace_id: UUID, recommendation_id: UUID, decision: RecommendationStatus, actor_user_id: str, note: str) -> tuple[Recommendation | None, RecommendationDecision | None]:
        current = self.get_recommendation(workspace_id=workspace_id, recommendation_id=recommendation_id)
        if current is None or current.status not in {RecommendationStatus.PENDING, RecommendationStatus.PENDING_APPROVAL}:
            return None, None
        now = datetime.now(UTC)
        updated = current.model_copy(update={"status": decision, "decided_by": actor_user_id, "decision_note": note.strip(), "decided_at": now, "updated_at": now})
        decision_record = RecommendationDecision(id=uuid4(), workspace_id=workspace_id, recommendation_id=recommendation_id, decision=decision, actor_user_id=actor_user_id, note=note.strip(), created_at=now)
        self._recommendations[updated.id] = updated
        self._decisions[decision_record.id] = decision_record
        return updated, decision_record

    def insert_ai_run(self, *, ai_run: AiRun) -> AiRun:
        self._ai_runs[ai_run.id] = ai_run
        return ai_run

    def latest_ai_run(self, *, workspace_id: UUID, agent_name: str) -> AiRun | None:
        runs = [run for run in self._ai_runs.values() if run.workspace_id == workspace_id and run.agent_name == agent_name]
        return sorted(runs, key=lambda run: run.created_at, reverse=True)[0] if runs else None

    def list_ai_runs(self, *, workspace_id: UUID, product_id: UUID | None = None, agent_name: str | None = None, limit: int | None = None) -> list[AiRun]:
        runs = [
            run
            for run in self._ai_runs.values()
            if run.workspace_id == workspace_id
            and (product_id is None or run.product_id == product_id)
            and (agent_name is None or run.agent_name == agent_name)
        ]
        sorted_runs = sorted(runs, key=lambda run: run.created_at, reverse=True)
        return sorted_runs[:limit] if limit is not None else sorted_runs

    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        import_ids = [item_id for item_id, item in self._imports.items() if item.workspace_id == workspace_id and item.upload_id == upload_id]
        for import_id in import_ids:
            self._imports.pop(import_id, None)
            for snapshot_id, snapshot in list(self._snapshots.items()):
                if snapshot.workspace_id == workspace_id and snapshot.monitoring_import_id == import_id:
                    self._snapshots.pop(snapshot_id, None)
            recommendation_ids = [
                recommendation_id
                for recommendation_id, recommendation in self._recommendations.items()
                if recommendation.workspace_id == workspace_id and recommendation.monitoring_import_id == import_id
            ]
            for recommendation_id in recommendation_ids:
                self._recommendations.pop(recommendation_id, None)
                for decision_id, decision in list(self._decisions.items()):
                    if decision.workspace_id == workspace_id and decision.recommendation_id == recommendation_id:
                        self._decisions.pop(decision_id, None)


class PostgresMonitoringRepository(MonitoringRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_import(self, *, import_record: MonitoringImport) -> MonitoringImport:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into monitoring_imports (
                        id, workspace_id, product_id, upload_id, parse_run_id, report_type, status,
                        date_range_start, date_range_end, total_rows, processed_rows, error_rows,
                        data_quality_warnings_json, created_by, error_message, created_at, updated_at
                    )
                    values (
                        :id, :workspace_id, :product_id, :upload_id, :parse_run_id, :report_type, :status,
                        :date_range_start, :date_range_end, :total_rows, :processed_rows, :error_rows,
                        cast(:data_quality_warnings_json as jsonb), :created_by, :error_message, :created_at, :updated_at
                    )
                    returning *
                    """
                ),
                _import_params(import_record),
            ).mappings().one()
        return _import_from_row(row)

    def get_import(self, *, workspace_id: UUID, monitoring_import_id: UUID) -> MonitoringImport | None:
        with self._engine.begin() as connection:
            row = connection.execute(text("select * from monitoring_imports where workspace_id = :workspace_id and id = :id"), {"workspace_id": workspace_id, "id": monitoring_import_id}).mappings().first()
        return _import_from_row(row) if row else None

    def list_imports(self, *, workspace_id: UUID, product_id: UUID | None = None) -> list[MonitoringImport]:
        params = {"workspace_id": workspace_id}
        clause = "workspace_id = :workspace_id"
        if product_id:
            clause += " and product_id = :product_id"
            params["product_id"] = product_id
        with self._engine.begin() as connection:
            rows = connection.execute(text(f"select * from monitoring_imports where {clause} order by created_at desc"), params).mappings().all()
        return [_import_from_row(row) for row in rows]

    def update_import(self, **kwargs) -> MonitoringImport | None:
        params = {
            "workspace_id": kwargs["workspace_id"],
            "monitoring_import_id": kwargs["monitoring_import_id"],
            "status": kwargs["status"].value,
            "total_rows": kwargs.get("total_rows"),
            "processed_rows": kwargs.get("processed_rows"),
            "error_rows": kwargs.get("error_rows"),
            "date_range_start": kwargs.get("date_range_start"),
            "date_range_end": kwargs.get("date_range_end"),
            "error_message": kwargs.get("error_message"),
            "data_quality_warnings_json": _json_dumps(kwargs.get("data_quality_warnings_json")) if kwargs.get("data_quality_warnings_json") is not None else None,
        }
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update monitoring_imports
                    set status = :status,
                        total_rows = coalesce(:total_rows, total_rows),
                        processed_rows = coalesce(:processed_rows, processed_rows),
                        error_rows = coalesce(:error_rows, error_rows),
                        date_range_start = coalesce(:date_range_start, date_range_start),
                        date_range_end = coalesce(:date_range_end, date_range_end),
                        data_quality_warnings_json = coalesce(cast(:data_quality_warnings_json as jsonb), data_quality_warnings_json),
                        error_message = :error_message,
                        updated_at = now()
                    where workspace_id = :workspace_id and id = :monitoring_import_id
                    returning *
                    """
                ),
                params,
            ).mappings().first()
        return _import_from_row(row) if row else None

    def insert_snapshots(self, *, snapshots: list[MonitoringSnapshot]) -> None:
        if not snapshots:
            return
        statement = text(
            """
            insert into monitoring_snapshots (
                id, workspace_id, product_id, monitoring_import_id, upload_id, parse_run_id, source_row_id,
                campaign_name, ad_group_name, targeting, match_type, customer_search_term, start_date, end_date,
                impressions, clicks, spend, sales, orders, units, cpc, ctr, cvr, acos, roas, raw_metrics_json, created_at
            )
            values (
                :id, :workspace_id, :product_id, :monitoring_import_id, :upload_id, :parse_run_id, :source_row_id,
                :campaign_name, :ad_group_name, :targeting, :match_type, :customer_search_term, :start_date, :end_date,
                :impressions, :clicks, :spend, :sales, :orders, :units, :cpc, :ctr, :cvr, :acos, :roas, cast(:raw_metrics_json as jsonb), :created_at
            )
            """
        )
        with self._engine.begin() as connection:
            connection.execute(statement, [_snapshot_params(snapshot) for snapshot in snapshots])

    def list_snapshots(self, *, workspace_id: UUID, product_id: UUID | None = None, monitoring_import_id: UUID | None = None) -> list[MonitoringSnapshot]:
        params = {"workspace_id": workspace_id}
        clauses = ["workspace_id = :workspace_id"]
        if product_id:
            clauses.append("product_id = :product_id")
            params["product_id"] = product_id
        if monitoring_import_id:
            clauses.append("monitoring_import_id = :monitoring_import_id")
            params["monitoring_import_id"] = monitoring_import_id
        with self._engine.begin() as connection:
            rows = connection.execute(text(f"select * from monitoring_snapshots where {' and '.join(clauses)} order by created_at desc"), params).mappings().all()
        return [_snapshot_from_row(row) for row in rows]

    def insert_recommendations(self, *, recommendations: list[Recommendation]) -> None:
        if not recommendations:
            return
        statement = text(
            """
            insert into recommendations (
                id, workspace_id, product_id, monitoring_import_id, snapshot_id, account_import_id, entity_key,
                decision_source, agent_run_id, ai_run_id, approval_boundary, recommendation_type,
                entity_type, status, priority, confidence, rule_version_id, rule_name, campaign_name, ad_group_name, targeting,
                customer_search_term, input_metrics_json, current_metric_snapshot_json, evidence_json, proposed_action_json, explanation_json,
                decided_by, decision_note, decided_at, created_at, updated_at
            )
            values (
                :id, :workspace_id, :product_id, :monitoring_import_id, :snapshot_id, :account_import_id, :entity_key,
                :decision_source, :agent_run_id, :ai_run_id, cast(:approval_boundary as jsonb), :recommendation_type,
                :entity_type, :status, :priority, :confidence, :rule_version_id, :rule_name, :campaign_name, :ad_group_name, :targeting,
                :customer_search_term, cast(:input_metrics_json as jsonb), cast(:current_metric_snapshot_json as jsonb), cast(:evidence_json as jsonb), cast(:proposed_action_json as jsonb), cast(:explanation_json as jsonb),
                :decided_by, :decision_note, :decided_at, :created_at, :updated_at
            )
            """
        )
        with self._engine.begin() as connection:
            connection.execute(statement, [_recommendation_params(recommendation) for recommendation in recommendations])

    def list_recommendations(self, *, workspace_id: UUID, product_id: UUID | None = None, status: RecommendationStatus | None = None, recommendation_type: str | None = None, limit: int | None = None, offset: int = 0) -> list[Recommendation]:
        params = {"workspace_id": workspace_id, "limit": limit, "offset": offset}
        clauses = ["workspace_id = :workspace_id"]
        if product_id:
            clauses.append("product_id = :product_id")
            params["product_id"] = product_id
        if status:
            clauses.append("status = :status")
            params["status"] = status.value
        if recommendation_type:
            clauses.append("recommendation_type = :recommendation_type")
            params["recommendation_type"] = recommendation_type
        limit_clause = " limit :limit offset :offset" if limit is not None else ""
        with self._engine.begin() as connection:
            rows = connection.execute(text(f"select * from recommendations where {' and '.join(clauses)} order by case priority::text when 'critical' then 0 when 'high' then 1 when 'medium' then 2 else 3 end, created_at desc{limit_clause}"), params).mappings().all()
        return [_recommendation_from_row(row) for row in rows]

    def get_recommendation(self, *, workspace_id: UUID, recommendation_id: UUID) -> Recommendation | None:
        with self._engine.begin() as connection:
            row = connection.execute(text("select * from recommendations where workspace_id = :workspace_id and id = :id"), {"workspace_id": workspace_id, "id": recommendation_id}).mappings().first()
        return _recommendation_from_row(row) if row else None

    def decide_recommendation(self, *, workspace_id: UUID, recommendation_id: UUID, decision: RecommendationStatus, actor_user_id: str, note: str) -> tuple[Recommendation | None, RecommendationDecision | None]:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update recommendations
                    set status = :decision, decided_by = :actor_user_id, decision_note = :note,
                        decided_at = now(), updated_at = now()
                    where workspace_id = :workspace_id and id = :recommendation_id and status in ('pending', 'pending_approval')
                    returning *
                    """
                ),
                {"workspace_id": workspace_id, "recommendation_id": recommendation_id, "decision": decision.value, "actor_user_id": _uuid_or_none(actor_user_id), "note": note.strip()},
            ).mappings().first()
            if row is None:
                return None, None
            decision_row = connection.execute(
                text(
                    """
                    insert into recommendation_decisions (id, workspace_id, recommendation_id, decision, actor_user_id, note)
                    values (:id, :workspace_id, :recommendation_id, :decision, :actor_user_id, :note)
                    returning *
                    """
                ),
                {"id": uuid4(), "workspace_id": workspace_id, "recommendation_id": recommendation_id, "decision": decision.value, "actor_user_id": _uuid_or_none(actor_user_id), "note": note.strip()},
            ).mappings().one()
        return _recommendation_from_row(row), _decision_from_row(decision_row)

    def insert_ai_run(self, *, ai_run: AiRun) -> AiRun:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into ai_runs (id, workspace_id, product_id, agent_name, provider, model, schema_version, input_hash, output_json, status, latency_ms, created_at)
                    values (:id, :workspace_id, :product_id, :agent_name, :provider, :model, :schema_version, :input_hash, cast(:output_json as jsonb), :status, :latency_ms, :created_at)
                    returning *
                    """
                ),
                _ai_run_params(ai_run),
            ).mappings().one()
        return _ai_run_from_row(row)

    def latest_ai_run(self, *, workspace_id: UUID, agent_name: str) -> AiRun | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from ai_runs where workspace_id = :workspace_id and agent_name = :agent_name order by created_at desc limit 1"),
                {"workspace_id": workspace_id, "agent_name": agent_name},
            ).mappings().first()
        return _ai_run_from_row(row) if row else None

    def list_ai_runs(self, *, workspace_id: UUID, product_id: UUID | None = None, agent_name: str | None = None, limit: int | None = None) -> list[AiRun]:
        params = {"workspace_id": workspace_id, "limit": limit}
        clauses = ["workspace_id = :workspace_id"]
        if product_id:
            clauses.append("product_id = :product_id")
            params["product_id"] = product_id
        if agent_name:
            clauses.append("agent_name = :agent_name")
            params["agent_name"] = agent_name
        limit_clause = " limit :limit" if limit is not None else ""
        with self._engine.begin() as connection:
            rows = connection.execute(text(f"select * from ai_runs where {' and '.join(clauses)} order by created_at desc{limit_clause}"), params).mappings().all()
        return [_ai_run_from_row(row) for row in rows]

    def delete_by_upload(self, *, workspace_id: UUID, upload_id: UUID) -> None:
        with self._engine.begin() as connection:
            recommendation_ids = [
                row[0]
                for row in connection.execute(
                    text(
                        """
                        select r.id
                        from recommendations r
                        inner join monitoring_imports mi on mi.id = r.monitoring_import_id
                        where mi.workspace_id = :workspace_id and mi.upload_id = :upload_id
                        """
                    ),
                    {"workspace_id": workspace_id, "upload_id": upload_id},
                ).all()
            ]
            for recommendation_id in recommendation_ids:
                connection.execute(
                    text("delete from recommendation_decisions where workspace_id = :workspace_id and recommendation_id = :recommendation_id"),
                    {"workspace_id": workspace_id, "recommendation_id": recommendation_id},
                )
                connection.execute(
                    text("delete from recommendations where workspace_id = :workspace_id and id = :recommendation_id"),
                    {"workspace_id": workspace_id, "recommendation_id": recommendation_id},
                )
            connection.execute(
                text("delete from monitoring_snapshots where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )
            connection.execute(
                text("delete from monitoring_imports where workspace_id = :workspace_id and upload_id = :upload_id"),
                {"workspace_id": workspace_id, "upload_id": upload_id},
            )


_local_repository = LocalMonitoringRepository()


def get_monitoring_repository() -> MonitoringRepository:
    settings = get_settings()
    if settings.database_url:
        # Use pooled engine for production performance (5 persistent connections + 10 overflow)
        pooled = get_pooled_engine()
        engine = pooled if pooled is not None else get_database_engine()
        return PostgresMonitoringRepository(engine=engine)
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(code="DATABASE_NOT_CONFIGURED", message="DATABASE_URL must be configured outside local and test environments.", status_code=503)


def new_monitoring_import(*, workspace_id: UUID, product_id: UUID, upload_id: UUID, parse_run_id: UUID, created_by: str) -> MonitoringImport:
    now = datetime.now(UTC)
    return MonitoringImport(
        id=uuid4(),
        workspace_id=workspace_id,
        product_id=product_id,
        upload_id=upload_id,
        parse_run_id=parse_run_id,
        report_type="sponsored_products_search_term",
        status=MonitoringImportStatus.QUEUED,
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


def _import_from_row(row: RowMapping) -> MonitoringImport:
    data = dict(row)
    data["created_by"] = str(row["created_by"])
    return MonitoringImport(**data)


def _snapshot_from_row(row: RowMapping) -> MonitoringSnapshot:
    return MonitoringSnapshot(**dict(row))


def _recommendation_from_row(row: RowMapping) -> Recommendation:
    data = dict(row)
    if data.get("decided_by") is not None:
        data["decided_by"] = str(data["decided_by"])
    # Ensure `entity_type` is a valid string for the Recommendation enum.
    # If the DB value is NULL, default to 'search_term' which matches the
    # RecommendationEntityType default in the schema.
    if data.get("entity_type") is None:
        data["entity_type"] = "search_term"
    else:
        data["entity_type"] = str(data["entity_type"])

    return Recommendation(**data)


def _decision_from_row(row: RowMapping) -> RecommendationDecision:
    return RecommendationDecision(**{**dict(row), "actor_user_id": str(row["actor_user_id"])})


def _ai_run_from_row(row: RowMapping) -> AiRun:
    return AiRun(**dict(row))


def _import_params(import_record: MonitoringImport) -> dict:
    return {**import_record.model_dump(), "status": import_record.status.value, "created_by": _uuid_or_none(import_record.created_by), "data_quality_warnings_json": _json_dumps(import_record.data_quality_warnings_json)}


def _snapshot_params(snapshot: MonitoringSnapshot) -> dict:
    return {**snapshot.model_dump(), "raw_metrics_json": _json_dumps(snapshot.raw_metrics_json)}


def _recommendation_params(recommendation: Recommendation) -> dict:
    return {
        **recommendation.model_dump(),
        "recommendation_type": recommendation.recommendation_type.value,
        "entity_type": recommendation.entity_type.value,
        "status": recommendation.status.value,
        "priority": recommendation.priority.value,
        "confidence": recommendation.confidence.value,
        "approval_boundary": _json_dumps(recommendation.approval_boundary),
        "input_metrics_json": _json_dumps(recommendation.input_metrics_json),
        "current_metric_snapshot_json": _json_dumps(recommendation.current_metric_snapshot_json),
        "evidence_json": _json_dumps(recommendation.evidence_json),
        "proposed_action_json": _json_dumps(recommendation.proposed_action_json),
        "explanation_json": _json_dumps(recommendation.explanation_json),
        "decided_by": _uuid_or_none(recommendation.decided_by) if recommendation.decided_by else None,
    }


def _ai_run_params(ai_run: AiRun) -> dict:
    return {**ai_run.model_dump(), "output_json": _json_dumps(ai_run.output_json)}


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _json_dumps(value) -> str:
    import json

    return json.dumps(value, default=str)
