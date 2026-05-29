from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.agent_control import AgentConfig, AgentRunEvent
from apps.api.app.schemas.agent_control import AgentProvider
from apps.api.app.services.agent_registry import AGENT_DEFINITION_BY_ID, list_agent_definitions

_CONFIG_DB_COLUMNS = [
    "workspace_id",
    "product_id",
    "agent_id",
    "enabled",
    "mode",
    "provider",
    "model",
    "strictness_level",
    "confidence_threshold",
    "max_recommendations",
    "max_rows_per_ai_call",
    "max_groups_per_ai_call",
    "max_products_per_run",
    "analysis_depth",
    "include_account_level_analysis",
    "include_product_level_analysis",
    "include_campaign_level_analysis",
    "include_keyword_level_analysis",
    "include_search_term_level_analysis",
    "allow_bid_recommendations",
    "allow_negative_keyword_recommendations",
    "allow_pause_recommendations",
    "allow_budget_recommendations",
    "allow_keep_running",
    "allow_increase_bid",
    "allow_decrease_bid",
    "allow_pause_review",
    "allow_negative_exact",
    "allow_negative_phrase",
    "allow_move_to_exact",
    "allow_budget_review",
    "allow_data_quality_review",
    "allow_product_mapping_recommendations",
    "max_bid_increase_multiplier",
    "max_bid_decrease_multiplier",
    "require_high_confidence_for_pause",
    "require_high_confidence_for_negative_keywords",
    "require_min_clicks_before_action",
    "require_min_spend_before_action",
    "target_acos_override",
    "min_orders_for_scaling",
    "min_roas_for_scaling",
    "custom_system_instruction",
    "custom_business_goal",
    "optimization_goal",
    "brand_safety_notes",
    "competitor_notes",
    "product_margin_notes",
    "recommendation_language",
    "explanation_detail",
    "show_raw_ai_reasoning_summary",
    "show_metric_evidence",
    "require_action_risk_note",
    "chunk_strategy",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
]


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
        update_columns = [column for column in _CONFIG_DB_COLUMNS if column not in {"workspace_id", "product_id", "agent_id", "created_by", "created_at", "updated_at"}]
        insert_columns = _CONFIG_DB_COLUMNS
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    update agent_configs
                    set {", ".join(f"{column} = :{column}" for column in update_columns)},
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
                        f"""
                        insert into agent_configs (
                            {", ".join(insert_columns)}
                        )
                        values (
                            {", ".join(f":{column}" for column in insert_columns)}
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
    settings = get_settings()
    provider = AgentProvider.DEEPSEEK
    if settings.deepseek_api_key or (settings.ai_provider == "deepseek" and settings.ai_api_key):
        provider = AgentProvider.DEEPSEEK
    elif settings.ai_api_key and settings.ai_base_url:
        provider = AgentProvider.PRIMARY
    elif settings.ai_fallback_api_key and settings.ai_fallback_base_url:
        provider = AgentProvider.FALLBACK
    return AgentConfig(workspace_id=workspace_id, product_id=product_id, agent_id=agent_id, enabled=definition.enabled_by_default if definition else True, provider=provider)


def _config_from_row(row: RowMapping) -> AgentConfig:
    d = dict(row)
    if d.get("created_by") is not None:
        d["created_by"] = str(d["created_by"])
    if d.get("updated_by") is not None:
        d["updated_by"] = str(d["updated_by"])
    return AgentConfig(**d)


def _event_from_row(row: RowMapping) -> AgentRunEvent:
    return AgentRunEvent(**dict(row))


def _config_params(params: dict) -> dict:
    serialized = {}
    for key, value in params.items():
        serialized[key] = value.value if hasattr(value, "value") else value
    return serialized


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
