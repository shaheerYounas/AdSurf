from abc import ABC, abstractmethod
from datetime import UTC, datetime
from uuid import UUID, uuid4
import json

from sqlalchemy import text
from sqlalchemy.engine import Engine, RowMapping

from apps.api.app.core.config import get_settings
from apps.api.app.core.database import get_database_engine
from apps.api.app.core.errors import ApiError
from apps.api.app.schemas.workflows import (
    AgentWorkflow,
    AgentWorkflowCheckpoint,
    AgentWorkflowEvent,
    WorkflowStatus,
    WorkflowType,
)


class WorkflowRepository(ABC):
    @abstractmethod
    def create_workflow(self, *, workflow: AgentWorkflow) -> AgentWorkflow:
        raise NotImplementedError

    @abstractmethod
    def get_workflow(self, *, workspace_id: UUID, workflow_id: UUID) -> AgentWorkflow | None:
        raise NotImplementedError

    @abstractmethod
    def get_latest_for_account_import(self, *, workspace_id: UUID, account_import_id: UUID) -> AgentWorkflow | None:
        raise NotImplementedError

    @abstractmethod
    def update_workflow(self, *, workflow_id: UUID, workspace_id: UUID, status: WorkflowStatus, current_node: str | None = None, state_json: dict | None = None, error_json: dict | None = None, completed: bool = False) -> AgentWorkflow | None:
        raise NotImplementedError

    @abstractmethod
    def insert_checkpoint(self, *, checkpoint: AgentWorkflowCheckpoint) -> AgentWorkflowCheckpoint:
        raise NotImplementedError

    @abstractmethod
    def insert_event(self, *, event: AgentWorkflowEvent) -> AgentWorkflowEvent:
        raise NotImplementedError

    @abstractmethod
    def list_events(self, *, workspace_id: UUID, workflow_id: UUID) -> list[AgentWorkflowEvent]:
        raise NotImplementedError


class LocalWorkflowRepository(WorkflowRepository):
    def __init__(self) -> None:
        self._workflows: dict[UUID, AgentWorkflow] = {}
        self._checkpoints: dict[UUID, list[AgentWorkflowCheckpoint]] = {}
        self._events: dict[UUID, list[AgentWorkflowEvent]] = {}

    def create_workflow(self, *, workflow: AgentWorkflow) -> AgentWorkflow:
        self._workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, *, workspace_id: UUID, workflow_id: UUID) -> AgentWorkflow | None:
        workflow = self._workflows.get(workflow_id)
        return workflow if workflow and workflow.workspace_id == workspace_id else None

    def get_latest_for_account_import(self, *, workspace_id: UUID, account_import_id: UUID) -> AgentWorkflow | None:
        workflows = [
            item
            for item in self._workflows.values()
            if item.workspace_id == workspace_id and item.account_import_id == account_import_id
        ]
        return sorted(workflows, key=lambda item: item.created_at, reverse=True)[0] if workflows else None

    def update_workflow(self, *, workflow_id: UUID, workspace_id: UUID, status: WorkflowStatus, current_node: str | None = None, state_json: dict | None = None, error_json: dict | None = None, completed: bool = False) -> AgentWorkflow | None:
        current = self.get_workflow(workspace_id=workspace_id, workflow_id=workflow_id)
        if current is None:
            return None
        updates = {"status": status, "updated_at": datetime.now(UTC)}
        if current_node is not None:
            updates["current_node"] = current_node
        if state_json is not None:
            updates["state_json"] = state_json
        if error_json is not None:
            updates["error_json"] = error_json
        if completed:
            updates["completed_at"] = datetime.now(UTC)
        updated = current.model_copy(update=updates)
        self._workflows[workflow_id] = updated
        return updated

    def insert_checkpoint(self, *, checkpoint: AgentWorkflowCheckpoint) -> AgentWorkflowCheckpoint:
        self._checkpoints.setdefault(checkpoint.workflow_id, []).append(checkpoint)
        return checkpoint

    def insert_event(self, *, event: AgentWorkflowEvent) -> AgentWorkflowEvent:
        self._events.setdefault(event.workflow_id, []).append(event)
        return event

    def list_events(self, *, workspace_id: UUID, workflow_id: UUID) -> list[AgentWorkflowEvent]:
        return sorted(
            [event for event in self._events.get(workflow_id, []) if event.workspace_id == workspace_id],
            key=lambda item: item.created_at,
        )


class PostgresWorkflowRepository(WorkflowRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_workflow(self, *, workflow: AgentWorkflow) -> AgentWorkflow:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into agent_workflows (
                        id, workspace_id, account_import_id, upload_id, product_id, monitoring_import_id,
                        workflow_type, status, current_node, state_json, error_json, created_by,
                        created_at, updated_at, completed_at
                    )
                    values (
                        :id, :workspace_id, :account_import_id, :upload_id, :product_id, :monitoring_import_id,
                        :workflow_type, :status, :current_node, cast(:state_json as jsonb), cast(:error_json as jsonb), :created_by,
                        :created_at, :updated_at, :completed_at
                    )
                    returning *
                    """
                ),
                _workflow_params(workflow),
            ).mappings().one()
        return _workflow_from_row(row)

    def get_workflow(self, *, workspace_id: UUID, workflow_id: UUID) -> AgentWorkflow | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text("select * from agent_workflows where workspace_id = :workspace_id and id = :workflow_id"),
                {"workspace_id": workspace_id, "workflow_id": workflow_id},
            ).mappings().first()
        return _workflow_from_row(row) if row else None

    def get_latest_for_account_import(self, *, workspace_id: UUID, account_import_id: UUID) -> AgentWorkflow | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    select * from agent_workflows
                    where workspace_id = :workspace_id and account_import_id = :account_import_id
                    order by created_at desc
                    limit 1
                    """
                ),
                {"workspace_id": workspace_id, "account_import_id": account_import_id},
            ).mappings().first()
        return _workflow_from_row(row) if row else None

    def update_workflow(self, *, workflow_id: UUID, workspace_id: UUID, status: WorkflowStatus, current_node: str | None = None, state_json: dict | None = None, error_json: dict | None = None, completed: bool = False) -> AgentWorkflow | None:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    update agent_workflows
                    set status = :status,
                        current_node = coalesce(:current_node, current_node),
                        state_json = coalesce(cast(:state_json as jsonb), state_json),
                        error_json = coalesce(cast(:error_json as jsonb), error_json),
                        completed_at = case when :completed then now() else completed_at end,
                        updated_at = now()
                    where workspace_id = :workspace_id and id = :workflow_id
                    returning *
                    """
                ),
                {
                    "workspace_id": workspace_id,
                    "workflow_id": workflow_id,
                    "status": status.value,
                    "current_node": current_node,
                    "state_json": _json_dumps(state_json) if state_json is not None else None,
                    "error_json": _json_dumps(error_json) if error_json is not None else None,
                    "completed": completed,
                },
            ).mappings().first()
        return _workflow_from_row(row) if row else None

    def insert_checkpoint(self, *, checkpoint: AgentWorkflowCheckpoint) -> AgentWorkflowCheckpoint:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into agent_workflow_checkpoints (id, workflow_id, node_name, state_json, status, created_at)
                    values (:id, :workflow_id, :node_name, cast(:state_json as jsonb), :status, :created_at)
                    returning *
                    """
                ),
                _checkpoint_params(checkpoint),
            ).mappings().one()
        return _checkpoint_from_row(row)

    def insert_event(self, *, event: AgentWorkflowEvent) -> AgentWorkflowEvent:
        with self._engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    insert into agent_workflow_events (
                        id, workflow_id, workspace_id, agent_id, node_name, event_type, message,
                        metadata_json, latency_ms, provider, model, created_at
                    )
                    values (
                        :id, :workflow_id, :workspace_id, :agent_id, :node_name, :event_type, :message,
                        cast(:metadata_json as jsonb), :latency_ms, :provider, :model, :created_at
                    )
                    returning *
                    """
                ),
                _event_params(event),
            ).mappings().one()
        return _event_from_row(row)

    def list_events(self, *, workspace_id: UUID, workflow_id: UUID) -> list[AgentWorkflowEvent]:
        with self._engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    select * from agent_workflow_events
                    where workspace_id = :workspace_id and workflow_id = :workflow_id
                    order by created_at asc
                    """
                ),
                {"workspace_id": workspace_id, "workflow_id": workflow_id},
            ).mappings().all()
        return [_event_from_row(row) for row in rows]


_local_repository = LocalWorkflowRepository()


def get_workflow_repository() -> WorkflowRepository:
    settings = get_settings()
    if settings.database_url:
        return PostgresWorkflowRepository(engine=get_database_engine())
    if settings.is_local_or_test:
        return _local_repository
    raise ApiError(code="DATABASE_NOT_CONFIGURED", message="DATABASE_URL must be configured outside local and test environments.", status_code=503)


def new_workflow(*, workspace_id: UUID, created_by: str | None, account_import_id: UUID | None = None, upload_id: UUID | None = None, product_id: UUID | None = None, monitoring_import_id: UUID | None = None, workflow_type: WorkflowType = WorkflowType.ACCOUNT_IMPORT_ANALYSIS, state_json: dict | None = None) -> AgentWorkflow:
    now = datetime.now(UTC)
    return AgentWorkflow(
        id=uuid4(),
        workspace_id=workspace_id,
        account_import_id=account_import_id,
        upload_id=upload_id,
        product_id=product_id,
        monitoring_import_id=monitoring_import_id,
        workflow_type=workflow_type,
        status=WorkflowStatus.PENDING,
        current_node="start_workflow",
        state_json=state_json or {},
        error_json={},
        created_by=created_by,
        created_at=now,
        updated_at=now,
    )


def new_workflow_event(*, workflow_id: UUID, workspace_id: UUID, node_name: str, event_type: str, message: str, agent_id: str | None = None, metadata_json: dict | None = None, latency_ms: int | None = None, provider: str | None = None, model: str | None = None) -> AgentWorkflowEvent:
    return AgentWorkflowEvent(
        id=uuid4(),
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        agent_id=agent_id,
        node_name=node_name,
        event_type=event_type,
        message=message,
        metadata_json=metadata_json or {},
        latency_ms=latency_ms,
        provider=provider,
        model=model,
        created_at=datetime.now(UTC),
    )


def new_checkpoint(*, workflow_id: UUID, node_name: str, state_json: dict, status: WorkflowStatus | str) -> AgentWorkflowCheckpoint:
    return AgentWorkflowCheckpoint(
        id=uuid4(),
        workflow_id=workflow_id,
        node_name=node_name,
        state_json=state_json,
        status=status,
        created_at=datetime.now(UTC),
    )


def _workflow_from_row(row: RowMapping) -> AgentWorkflow:
    data = dict(row)
    if data.get("created_by") is not None:
        data["created_by"] = str(data["created_by"])
    return AgentWorkflow(**data)


def _checkpoint_from_row(row: RowMapping) -> AgentWorkflowCheckpoint:
    return AgentWorkflowCheckpoint(**dict(row))


def _event_from_row(row: RowMapping) -> AgentWorkflowEvent:
    return AgentWorkflowEvent(**dict(row))


def _workflow_params(item: AgentWorkflow) -> dict:
    return {
        **item.model_dump(),
        "workflow_type": item.workflow_type.value,
        "status": item.status.value,
        "created_by": _uuid_or_none(item.created_by),
        "state_json": _json_dumps(item.state_json),
        "error_json": _json_dumps(item.error_json),
    }


def _checkpoint_params(item: AgentWorkflowCheckpoint) -> dict:
    data = item.model_dump()
    status = data["status"]
    data["status"] = status.value if hasattr(status, "value") else status
    data["state_json"] = _json_dumps(item.state_json)
    return data


def _event_params(item: AgentWorkflowEvent) -> dict:
    data = item.model_dump()
    event_type = data["event_type"]
    data["event_type"] = event_type.value if hasattr(event_type, "value") else event_type
    data["metadata_json"] = _json_dumps(item.metadata_json)
    return data


def _uuid_or_none(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def _json_dumps(value) -> str:
    return json.dumps(value or {}, default=str)
