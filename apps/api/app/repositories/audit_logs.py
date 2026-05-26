from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError


class AuditLogRepository(ABC):
    @abstractmethod
    def record(
        self,
        *,
        workspace_id: UUID,
        actor_user_id: str,
        action: str,
        entity_type: str,
        entity_id: UUID,
        details: dict,
    ) -> None:
        raise NotImplementedError


class LocalAuditLogRepository(AuditLogRepository):
    """Local/test in-memory audit writer; production uses the database audit log."""

    def __init__(self) -> None:
        self.records: list[dict] = []

    def record(
        self,
        *,
        workspace_id: UUID,
        actor_user_id: str,
        action: str,
        entity_type: str,
        entity_id: UUID,
        details: dict,
    ) -> None:
        self.records.append(
            {
                "workspace_id": workspace_id,
                "actor_user_id": actor_user_id,
                "event_type": action,
                "object_type": entity_type,
                "object_id": entity_id,
                "metadata_json": details,
                "created_at": datetime.now(UTC),
            }
        )

    def count(self, *, workspace_id: UUID, event_type: str, object_id: UUID | None = None) -> int:
        return sum(
            1
            for record in self.records
            if record["workspace_id"] == workspace_id
            and record["event_type"] == event_type
            and (object_id is None or record["object_id"] == object_id)
        )


class PostgresAuditLogRepository(AuditLogRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def record(
        self,
        *,
        workspace_id: UUID,
        actor_user_id: str,
        action: str,
        entity_type: str,
        entity_id: UUID,
        details: dict,
    ) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into audit_logs (
                        id, workspace_id, actor_user_id, event_type, object_type, object_id, metadata_json
                    )
                    values (
                        :id, :workspace_id, :actor_user_id, :event_type, :object_type, :object_id,
                        cast(:metadata_json as jsonb)
                    )
                    """
                ),
                {
                    "id": uuid4(),
                    "workspace_id": workspace_id,
                    "actor_user_id": _uuid_or_none(actor_user_id),
                    "event_type": action,
                    "object_type": entity_type,
                    "object_id": entity_id,
                    "metadata_json": _json_dumps(details),
                },
            )


_local_repository = LocalAuditLogRepository()


def get_audit_log_repository() -> AuditLogRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresAuditLogRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(
        code="DATABASE_NOT_CONFIGURED",
        message="DATABASE_URL must be configured outside local and test environments.",
        status_code=503,
    )


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _json_dumps(value: dict) -> str:
    import json

    return json.dumps(value)
