from uuid import UUID

from apps.api.app.repositories.workflows import WorkflowRepository
from apps.api.app.schemas.workflows import WorkflowStatus


def persist_node_state(
    repository: WorkflowRepository,
    *,
    workspace_id: UUID,
    workflow_id: UUID,
    node_name: str,
    status: WorkflowStatus,
    state_json: dict,
    error_json: dict | None = None,
    completed: bool = False,
) -> None:
    repository.update_workflow(
        workflow_id=workflow_id,
        workspace_id=workspace_id,
        status=status,
        current_node=node_name,
        state_json=state_json,
        error_json=error_json,
        completed=completed,
    )
