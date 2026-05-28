from uuid import UUID

from apps.api.app.repositories.workflows import WorkflowRepository, new_checkpoint, new_workflow_event
from apps.api.app.schemas.workflows import WorkflowStatus


def emit_event(
    repository: WorkflowRepository,
    *,
    workflow_id: UUID,
    workspace_id: UUID,
    node_name: str,
    event_type: str,
    message: str,
    agent_id: str | None = None,
    metadata_json: dict | None = None,
    latency_ms: int | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    event = repository.insert_event(
        event=new_workflow_event(
            workflow_id=workflow_id,
            workspace_id=workspace_id,
            node_name=node_name,
            event_type=event_type,
            message=message,
            agent_id=agent_id,
            metadata_json=metadata_json,
            latency_ms=latency_ms,
            provider=provider,
            model=model,
        )
    )
    return str(event.id)


def checkpoint(repository: WorkflowRepository, *, workflow_id: UUID, node_name: str, state_json: dict, status: WorkflowStatus | str) -> None:
    repository.insert_checkpoint(
        checkpoint=new_checkpoint(
            workflow_id=workflow_id,
            node_name=node_name,
            state_json=state_json,
            status=status,
        )
    )
