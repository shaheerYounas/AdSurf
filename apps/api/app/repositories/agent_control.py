from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.agent_control import AgentConfig, AgentRunEvent
from apps.api.app.services.agent_registry import AGENT_DEFINITION_BY_ID, list_agent_definitions


class AgentControlRepository(ABC):
    @abstractmethod
    def list_configs(self, *, workspace_id: UUID, product_id: UUID | None = None) -> list[AgentConfig]:
        raise NotImplementedError

    @abstractmethod
    def get_config(self, *, workspace_id: UUID, agent_id: str, product_id: UUID | None = None) -> AgentConfig:
        raise NotImplementedError

    @abstractmethod
    def upsert_config(self, *, config: AgentConfig) -> tuple[AgentConfig, AgentConfig | None]:
        raise NotImplementedError

    @abstractmethod
    def record_control_action(self, *, workspace_id: UUID, agent_id: str, agent_run_id: UUID | None, monitoring_import_id: UUID | None, action: str, actor_user_id: str, reason: str, metadata_json: dict) -> None:
        raise NotImplementedError

    @abstractmethod
    def latest_control_action(self, *, workspace_id: UUID, agent_id: str, monitoring_import_id: UUID | None = None, agent_run_id: UUID | None = None) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def insert_event(self, *, event: AgentRunEvent) -> AgentRunEvent:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, *, workspace_id: UUID, agent_run_id: UUID | None = None, monitoring_import_id: UUID | None = None) -> list[AgentRunEvent]:
        raise NotImplementedError


class LocalAgentControlRepository(AgentControlRepository):
    def __init__(self) -> None:
        self._configs: dict[tuple[UUID, UUID | None, str], AgentConfig] = {}
        self._actions: list[dict] = []
        self._events: dict[UUID, AgentRunEvent] = {}

    def list_configs(self, *, workspace_id: UUID, product_id: UUID | None = None) -> list[AgentConfig]:
        explicit = [config for (scope, scoped_product, _), config in self._configs.items() if scope == workspace_id and (product_id is None or scoped_product in {None, product_id})]
        by_key = {(config.product_id, config.agent_id): config for config in explicit}
        for definition in list_agent_definitions():
            key = (product_id, definition.agent_id)
            workspace_key = (None, definition.agent_id)
            if key not in by_key and workspace_key not in by_key:
                by_key[workspace_key] = _default_config(workspace_id=workspace_id, product_id=None, agent_id=definition.agent_id)
        return sorted(by_key.values(), key=lambda item: item.agent_id)

    def get_config(self, *, workspace_id: UUID, agent_id: str, product_id: UUID | None = None) -> AgentConfig:
        return self._configs.get((workspace_id, product_id, agent_id)) or self._configs.get((workspace_id, None, agent_id)) or _default_config(workspace_id=workspace_id, product_id=product_id, agent_id=agent_id)

    def upsert_config(self, *, config: AgentConfig) -> tuple[AgentConfig, AgentConfig | None]:
        now = datetime.now(UTC)
        key = (config.workspace_id, config.product_id, config.agent_id)
        old = self._configs.get(key)
        created_at = old.created_at if old and old.created_at else now
        updated = config.model_copy(update={"created_at": created_at, "updated_at": now})
        self._configs[key] = updated
        return updated, old

    def record_control_action(self, *, workspace_id: UUID, agent_id: str, agent_run_id: UUID | None, monitoring_import_id: UUID | None, action: str, actor_user_id: str, reason: str, metadata_json: dict) -> None:
        self._actions.append(
            {
                "id": uuid4(),
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "agent_run_id": agent_run_id,
                "monitoring_import_id": monitoring_import_id,
                "action": action,
                "actor_user_id": actor_user_id,
                "reason": reason,
                "metadata_json": metadata_json,
                "created_at": datetime.now(UTC),
            }
        )

    def latest_control_action(self, *, workspace_id: UUID, agent_id: str, monitoring_import_id: UUID | None = None, agent_run_id: UUID | None = None) -> dict | None:
        actions = [
            action
            for action in self._actions
            if action["workspace_id"] == workspace_id
            and action["agent_id"] == agent_id
            and (monitoring_import_id is None or action["monitoring_import_id"] == monitoring_import_id)
            and (agent_run_id is None or action["agent_run_id"] == agent_run_id)
        ]
        return sorted(actions, key=lambda item: item["created_at"], reverse=True)[0] if actions else None

    def insert_event(self, *, event: AgentRunEvent) -> AgentRunEvent:
        self._events[event.id] = event
        return event

    def list_events(self, *, workspace_id: UUID, agent_run_id: UUID | None = None, monitoring_import_id: UUID | None = None) -> list[AgentRunEvent]:
        events = [
            event
            for event in self._events.values()
            if event.workspace_id == workspace_id
            and (agent_run_id is None or event.agent_run_id == agent_run_id)
            and (monitoring_import_id is None or event.monitoring_import_id == monitoring_import_id)
        ]
        return sorted(events, key=lambda item: item.created_at)


class PostgresAgentControlRepository(AgentControlRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_configs(self, *, workspace_id: UUID, product_id: UUID | None = None) -> list[AgentConfig]:
        clauses = ["workspace_id = :workspace_id"]
        params = {"workspace_id": workspace_id, "product_id": product_id}
        if product_id:
            clauses.append("(product_id is null or product_id = :product_id)")
        with self._engine.begin() as connection:
            rows = connection.execute(text(f"select * from agent_configs where {' and '.join(clauses)}"), params).mappings().all()
        configs = [_config_from_row(row) for row in rows]
        by_key = {(config.product_id, config.agent_id): config for config in configs}
        for definition in list_agent_definitions():
            key = (product_id, definition.agent_id)
            workspace_key = (None, definition.agent_id)
            if key not in by_key and workspace_key not in by_key:
                by_key[workspace_key] = _default_config(workspace_id=workspace_id, product_id=None, agent_id=definition.agent_id)
        return sorted(by_key.values(), key=lambda item: item.agent_id)

    def get_config(self, *, workspace_id: UUID, agent_id: str, product_id: UUID | None = None) -> AgentConfig:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select * from agent_configs
                    where workspace_id = :workspace_id and agent_id = :agent_id and (product_id = :product_id or product_id is null)
                    order by product_id nulls last
                    limit 1
                    """
                ),
                {"workspace_id": workspace_id, "agent_id": agent_id, "product_id": product_id},
            ).mappings().first()
        return _config_from_row(row) if row else _default_config(workspace_id=workspace_id, product_id=product_id, agent_id=agent_id)

    def upsert_config(self, *, config: AgentConfig) -> tuple[AgentConfig, AgentConfig | None]:
        old = self.get_config(workspace_id=config.workspace_id, product_id=config.product_id, agent_id=config.agent_id)
        now = datetime.now(UTC)
        params = {**config.model_dump(), "created_at": config.created_at or now, "updated_at": now}
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update agent_configs
                    set enabled = :enabled,
                        mode = :mode,
                        strictness_level = :strictness_level,
                        confidence_threshold = :confidence_threshold,
                        max_recommendations = :max_recommendations,
                        allow_bid_recommendations = :allow_bid_recommendations,
                        allow_negative_keyword_recommendations = :allow_negative_keyword_recommendations,
                        allow_pause_recommendations = :allow_pause_recommendations,
                        allow_budget_recommendations = :allow_budget_recommendations,
                        updated_by = :updated_by,
                        updated_at = now()
                    where workspace_id = :workspace_id and agent_id = :agent_id and product_id is not distinct from :product_id
                    returning *
                    """
                ),
                _config_params(params),
            ).mappings().first()
            if row is None:
                row = connection.execute(
                    text(
                        """
                        insert into agent_configs (
                            workspace_id, product_id, agent_id, enabled, mode, strictness_level, confidence_threshold,
                            max_recommendations, allow_bid_recommendations, allow_negative_keyword_recommendations,
                            allow_pause_recommendations, allow_budget_recommendations, created_by, updated_by, created_at, updated_at
                        )
                        values (
                            :workspace_id, :product_id, :agent_id, :enabled, :mode, :strictness_level, :confidence_threshold,
                            :max_recommendations, :allow_bid_recommendations, :allow_negative_keyword_recommendations,
                            :allow_pause_recommendations, :allow_budget_recommendations, :created_by, :updated_by, :created_at, :updated_at
                        )
                        returning *
                        """
                    ),
                    _config_params(params),
                ).mappings().one()
        return _config_from_row(row), old

    def record_control_action(self, *, workspace_id: UUID, agent_id: str, agent_run_id: UUID | None, monitoring_import_id: UUID | None, action: str, actor_user_id: str, reason: str, metadata_json: dict) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text(
                    """
                    insert into agent_control_actions (
                        id, workspace_id, agent_id, agent_run_id, monitoring_import_id, action, actor_user_id, reason, metadata_json
                    )
                    values (:id, :workspace_id, :agent_id, :agent_run_id, :monitoring_import_id, :action, :actor_user_id, :reason, cast(:metadata_json as jsonb))
                    """
                ),
                {"id": uuid4(), "workspace_id": workspace_id, "agent_id": agent_id, "agent_run_id": agent_run_id, "monitoring_import_id": monitoring_import_id, "action": action, "actor_user_id": _uuid_or_none(actor_user_id), "reason": reason, "metadata_json": _json_dumps(metadata_json)},
            )

    def latest_control_action(self, *, workspace_id: UUID, agent_id: str, monitoring_import_id: UUID | None = None, agent_run_id: UUID | None = None) -> dict | None:
        clauses = ["workspace_id = :workspace_id", "agent_id = :agent_id"]
        params = {"workspace_id": workspace_id, "agent_id": agent_id, "monitoring_import_id": monitoring_import_id, "agent_run_id": agent_run_id}
        if monitoring_import_id:
            clauses.append("monitoring_import_id = :monitoring_import_id")
        if agent_run_id:
            clauses.append("agent_run_id = :agent_run_id")
        with self._engine.begin() as connection:
            row = connection.execute(text(f"select * from agent_control_actions where {' and '.join(clauses)} order by created_at desc limit 1"), params).mappings().first()
        return dict(row) if row else None

    def insert_event(self, *, event: AgentRunEvent) -> AgentRunEvent:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into agent_run_events (
                        id, workspace_id, agent_id, agent_run_id, monitoring_import_id, event_type, message, metadata_json, created_at
                    )
                    values (:id, :workspace_id, :agent_id, :agent_run_id, :monitoring_import_id, :event_type, :message, cast(:metadata_json as jsonb), :created_at)
                    returning *
                    """
                ),
                {**event.model_dump(), "metadata_json": _json_dumps(event.metadata_json)},
            ).mappings().one()
        return _event_from_row(row)

    def list_events(self, *, workspace_id: UUID, agent_run_id: UUID | None = None, monitoring_import_id: UUID | None = None) -> list[AgentRunEvent]:
        clauses = ["workspace_id = :workspace_id"]
        params = {"workspace_id": workspace_id, "agent_run_id": agent_run_id, "monitoring_import_id": monitoring_import_id}
        if agent_run_id:
            clauses.append("agent_run_id = :agent_run_id")
        if monitoring_import_id:
            clauses.append("monitoring_import_id = :monitoring_import_id")
        with self._engine.begin() as connection:
            rows = connection.execute(text(f"select * from agent_run_events where {' and '.join(clauses)} order by created_at asc"), params).mappings().all()
        return [_event_from_row(row) for row in rows]


_local_repository = LocalAgentControlRepository()


def get_agent_control_repository() -> AgentControlRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresAgentControlRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(code="DATABASE_NOT_CONFIGURED", message="DATABASE_URL must be configured outside local and test environments.", status_code=503)


def new_agent_event(*, workspace_id: UUID, agent_id: str, event_type: str, message: str, agent_run_id: UUID | None = None, monitoring_import_id: UUID | None = None, metadata_json: dict | None = None) -> AgentRunEvent:
    return AgentRunEvent(
        id=uuid4(),
        workspace_id=workspace_id,
        agent_id=agent_id,
        agent_run_id=agent_run_id,
        monitoring_import_id=monitoring_import_id,
        event_type=event_type,
        message=message,
        metadata_json=metadata_json or {},
        created_at=datetime.now(UTC),
    )


def _default_config(*, workspace_id: UUID, product_id: UUID | None, agent_id: str) -> AgentConfig:
    definition = AGENT_DEFINITION_BY_ID.get(agent_id)
    return AgentConfig(workspace_id=workspace_id, product_id=product_id, agent_id=agent_id, enabled=definition.enabled_by_default if definition else True)


def _config_from_row(row: RowMapping) -> AgentConfig:
    return AgentConfig(**dict(row))


def _event_from_row(row: RowMapping) -> AgentRunEvent:
    return AgentRunEvent(**dict(row))


def _config_params(params: dict) -> dict:
    return {**params, "mode": str(params["mode"]), "strictness_level": str(params["strictness_level"]), "confidence_threshold": str(params["confidence_threshold"])}


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _json_dumps(value: dict) -> str:
    import json

    return json.dumps(value, default=str)
