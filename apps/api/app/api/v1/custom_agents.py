"""API routes for the Custom Agent Builder system."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from apps.api.app.core.auth import PRODUCT_PROFILE_READ_ROLES, WorkspacePrincipal, WorkspaceRole, require_workspace_member
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.custom_agents import (
    AgentTemplateRepository,
    CustomAgentRepository,
    CustomAgentRunRepository,
    KnowledgeBaseRepository,
    MemoryRepository,
    SubAgentRepository,
    ThreadRepository,
    ToolRepository,
)
from apps.api.app.schemas.custom_agents import (
    AgentMemoryCreate,
    AgentMemoryUpdate,
    AgentMessageCreate,
    AgentRunRequest,
    AgentThreadCreate,
    AgentThreadUpdate,
    AgentToolCreate,
    AgentToolUpdate,
    CustomAgentCreate,
    CustomAgentUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseUpdate,
    SubAgentCreate,
    SubAgentUpdate,
)
from apps.api.app.schemas.envelope import success_response

router = APIRouter()

AGENT_BUILDER_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN, WorkspaceRole.ANALYST}
ADMIN_ROLES = {WorkspaceRole.OWNER, WorkspaceRole.ADMIN}


# ── Available Tools Catalog ──────────────────────────────────────────────────

AVAILABLE_TOOLS = [
    {"tool_name": "web_search", "display_name": "Web Search", "description": "Search the web for information using search engines.", "category": "web", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "browser", "display_name": "Browser Preview", "description": "Open and interact with web pages in a headless browser.", "category": "web", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "image_analyzer", "display_name": "Image Analyzer", "description": "Analyze images using vision AI capabilities.", "category": "data", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "github_repo_reader", "display_name": "GitHub Repo Reader", "description": "Read files, issues, and PRs from GitHub repositories.", "category": "development", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "github_repo_writer", "display_name": "GitHub Repo Writer", "description": "Create commits, branches, and PRs on GitHub repositories.", "category": "development", "default_permission_level": "write", "requires_approval_by_default": True, "is_dangerous": True},
    {"tool_name": "gmail_read", "display_name": "Gmail Reader", "description": "Read emails from Gmail inbox.", "category": "communication", "default_permission_level": "read", "requires_approval_by_default": True, "is_dangerous": False},
    {"tool_name": "gmail_send", "display_name": "Gmail Send", "description": "Send emails via Gmail.", "category": "communication", "default_permission_level": "write", "requires_approval_by_default": True, "is_dangerous": True},
    {"tool_name": "database_query", "display_name": "Database Query", "description": "Run read-only SQL queries on connected databases.", "category": "data", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "database_write", "display_name": "Database Write", "description": "Execute write operations on connected databases.", "category": "data", "default_permission_level": "write", "requires_approval_by_default": True, "is_dangerous": True},
    {"tool_name": "crm_lookup", "display_name": "CRM Lookup", "description": "Look up contacts, leads, and deals in CRM.", "category": "business", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "crm_update", "display_name": "CRM Update", "description": "Create or update CRM records.", "category": "business", "default_permission_level": "write", "requires_approval_by_default": True, "is_dangerous": True},
    {"tool_name": "calendar_read", "display_name": "Calendar Reader", "description": "Read calendar events and availability.", "category": "communication", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "calendar_write", "display_name": "Calendar Writer", "description": "Create or modify calendar events.", "category": "communication", "default_permission_level": "write", "requires_approval_by_default": True, "is_dangerous": True},
    {"tool_name": "ticket_lookup", "display_name": "Ticket Lookup", "description": "Look up support tickets from help desk.", "category": "business", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "file_reader", "display_name": "File Reader", "description": "Read and parse files from storage.", "category": "data", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "knowledge_base_search", "display_name": "Knowledge Base Search", "description": "Search connected knowledge bases using semantic search.", "category": "data", "default_permission_level": "read", "requires_approval_by_default": False, "is_dangerous": False},
    {"tool_name": "custom_api", "display_name": "Custom API", "description": "Call custom REST API endpoints.", "category": "development", "default_permission_level": "read", "requires_approval_by_default": True, "is_dangerous": False},
    {"tool_name": "payment_api", "display_name": "Payment API", "description": "Process payments and check transaction status.", "category": "business", "default_permission_level": "execute", "requires_approval_by_default": True, "is_dangerous": True},
    {"tool_name": "email_draft", "display_name": "Email Draft", "description": "Draft email content for review without sending.", "category": "communication", "default_permission_level": "read", "requires_approval_by_default": True, "is_dangerous": False},
]


@router.get("/workspaces/{workspace_id}/custom-agent-tools-catalog")
def list_available_tools(workspace_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    return success_response(data=AVAILABLE_TOOLS)


# ── Custom Agents CRUD ───────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/custom-agents")
def list_custom_agents(workspace_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    repo = CustomAgentRepository()
    agents = repo.list_by_workspace(workspace_id)
    return success_response(data=[agent.model_dump(mode="json") for agent in agents])


@router.post("/workspaces/{workspace_id}/custom-agents")
def create_custom_agent(workspace_id: UUID, payload: CustomAgentCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    payload.workspace_id = workspace_id
    payload.created_by = principal.user_id
    repo = CustomAgentRepository()
    agent = repo.create(payload)
    return success_response(data=agent.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/custom-agents/{agent_id}")
def get_custom_agent(workspace_id: UUID, agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    agent = _get_agent_for_workspace(workspace_id, agent_id)
    return success_response(data=agent.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/custom-agents/{agent_id}")
def update_custom_agent(workspace_id: UUID, agent_id: UUID, payload: CustomAgentUpdate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    payload.updated_by = principal.user_id
    _get_agent_for_workspace(workspace_id, agent_id)
    repo = CustomAgentRepository()
    agent = repo.update(agent_id, payload)
    if not agent:
        raise ApiError(code="CUSTOM_AGENT_NOT_FOUND", message="Custom agent was not found.", status_code=404)
    return success_response(data=agent.model_dump(mode="json"))


@router.delete("/workspaces/{workspace_id}/custom-agents/{agent_id}")
def delete_custom_agent(workspace_id: UUID, agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    repo = CustomAgentRepository()
    deleted = repo.delete(agent_id)
    if not deleted:
        raise ApiError(code="CUSTOM_AGENT_NOT_FOUND", message="Custom agent was not found.", status_code=404)
    return success_response(data={"id": str(agent_id), "deleted": True})


# ── Agent Tools CRUD ─────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/custom-agents/{agent_id}/tools")
def list_agent_tools(workspace_id: UUID, agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    tools = ToolRepository().list_by_agent(agent_id)
    return success_response(data=[t.model_dump(mode="json") for t in tools])


@router.post("/workspaces/{workspace_id}/custom-agents/{agent_id}/tools")
def add_agent_tool(workspace_id: UUID, agent_id: UUID, payload: AgentToolCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    payload.agent_id = agent_id
    repo = ToolRepository()
    tool = repo.create(payload)
    return success_response(data=tool.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/custom-agents/{agent_id}/tools/{tool_id}")
def update_agent_tool(workspace_id: UUID, agent_id: UUID, tool_id: UUID, payload: AgentToolUpdate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_tool_for_agent(workspace_id, agent_id, tool_id)
    tool = ToolRepository().update(tool_id, payload)
    if not tool:
        raise ApiError(code="TOOL_NOT_FOUND", message="Agent tool was not found.", status_code=404)
    return success_response(data=tool.model_dump(mode="json"))


@router.delete("/workspaces/{workspace_id}/custom-agents/{agent_id}/tools/{tool_id}")
def remove_agent_tool(workspace_id: UUID, agent_id: UUID, tool_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_tool_for_agent(workspace_id, agent_id, tool_id)
    deleted = ToolRepository().delete(tool_id)
    if not deleted:
        raise ApiError(code="TOOL_NOT_FOUND", message="Agent tool was not found.", status_code=404)
    return success_response(data={"id": str(tool_id), "deleted": True})


# ── Knowledge Bases CRUD ─────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/knowledge-bases")
def list_knowledge_bases(workspace_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    kbs = KnowledgeBaseRepository().list_by_workspace(workspace_id)
    return success_response(data=[kb.model_dump(mode="json") for kb in kbs])


@router.post("/workspaces/{workspace_id}/knowledge-bases")
def create_knowledge_base(workspace_id: UUID, payload: KnowledgeBaseCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    payload.workspace_id = workspace_id
    payload.created_by = principal.user_id
    kb = KnowledgeBaseRepository().create(payload)
    return success_response(data=kb.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/knowledge-bases/{kb_id}")
def get_knowledge_base(workspace_id: UUID, kb_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    kb = _get_kb_for_workspace(workspace_id, kb_id)
    return success_response(data=kb.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/knowledge-bases/{kb_id}")
def update_knowledge_base(workspace_id: UUID, kb_id: UUID, payload: KnowledgeBaseUpdate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_kb_for_workspace(workspace_id, kb_id)
    kb = KnowledgeBaseRepository().update(kb_id, payload)
    if not kb:
        raise ApiError(code="KNOWLEDGE_BASE_NOT_FOUND", message="Knowledge base was not found.", status_code=404)
    return success_response(data=kb.model_dump(mode="json"))


@router.delete("/workspaces/{workspace_id}/knowledge-bases/{kb_id}")
def delete_knowledge_base(workspace_id: UUID, kb_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_kb_for_workspace(workspace_id, kb_id)
    deleted = KnowledgeBaseRepository().delete(kb_id)
    if not deleted:
        raise ApiError(code="KNOWLEDGE_BASE_NOT_FOUND", message="Knowledge base was not found.", status_code=404)
    return success_response(data={"id": str(kb_id), "deleted": True})


# ── Agent-Knowledge Base Links ───────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/custom-agents/{agent_id}/knowledge-bases/{kb_id}")
def link_agent_to_kb(workspace_id: UUID, agent_id: UUID, kb_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    _get_kb_for_workspace(workspace_id, kb_id)
    KnowledgeBaseRepository().link_agent_to_kb(agent_id, kb_id, workspace_id)
    return success_response(data={"agent_id": str(agent_id), "knowledge_base_id": str(kb_id), "linked": True})


@router.delete("/workspaces/{workspace_id}/custom-agents/{agent_id}/knowledge-bases/{kb_id}")
def unlink_agent_from_kb(workspace_id: UUID, agent_id: UUID, kb_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    _get_kb_for_workspace(workspace_id, kb_id)
    deleted = KnowledgeBaseRepository().unlink_agent_from_kb(agent_id, kb_id)
    if not deleted:
        raise ApiError(code="LINK_NOT_FOUND", message="Agent-knowledge base link was not found.", status_code=404)
    return success_response(data={"agent_id": str(agent_id), "knowledge_base_id": str(kb_id), "linked": False})


# ── Sub-Agents CRUD ─────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/custom-agents/{agent_id}/sub-agents")
def list_sub_agents(workspace_id: UUID, agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    subs = SubAgentRepository().list_by_agent(agent_id)
    return success_response(data=[s.model_dump(mode="json") for s in subs])


@router.post("/workspaces/{workspace_id}/custom-agents/{agent_id}/sub-agents")
def create_sub_agent(workspace_id: UUID, agent_id: UUID, payload: SubAgentCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    payload.parent_agent_id = agent_id
    sub = SubAgentRepository().create(payload)
    return success_response(data=sub.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/custom-agents/{agent_id}/sub-agents/{sub_agent_id}")
def update_sub_agent(workspace_id: UUID, agent_id: UUID, sub_agent_id: UUID, payload: SubAgentUpdate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_sub_agent_for_agent(workspace_id, agent_id, sub_agent_id)
    sub = SubAgentRepository().update(sub_agent_id, payload)
    if not sub:
        raise ApiError(code="SUB_AGENT_NOT_FOUND", message="Sub-agent was not found.", status_code=404)
    return success_response(data=sub.model_dump(mode="json"))


@router.delete("/workspaces/{workspace_id}/custom-agents/{agent_id}/sub-agents/{sub_agent_id}")
def delete_sub_agent(workspace_id: UUID, agent_id: UUID, sub_agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_sub_agent_for_agent(workspace_id, agent_id, sub_agent_id)
    deleted = SubAgentRepository().delete(sub_agent_id)
    if not deleted:
        raise ApiError(code="SUB_AGENT_NOT_FOUND", message="Sub-agent was not found.", status_code=404)
    return success_response(data={"id": str(sub_agent_id), "deleted": True})


# ── Threads & Messages ──────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/custom-agents/{agent_id}/threads")
def list_agent_threads(workspace_id: UUID, agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    threads = ThreadRepository().list_threads_by_agent(agent_id)
    return success_response(data=[t.model_dump(mode="json") for t in threads])


@router.post("/workspaces/{workspace_id}/custom-agents/{agent_id}/threads")
def create_agent_thread(workspace_id: UUID, agent_id: UUID, payload: AgentThreadCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    payload.agent_id = agent_id
    payload.created_by = principal.user_id
    thread = ThreadRepository().create_thread(payload)
    return success_response(data=thread.model_dump(mode="json"))


@router.get("/workspaces/{workspace_id}/threads/{thread_id}")
def get_thread(workspace_id: UUID, thread_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    thread = _get_thread_for_workspace(workspace_id, thread_id)
    return success_response(data=thread.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/threads/{thread_id}")
def update_thread(workspace_id: UUID, thread_id: UUID, payload: AgentThreadUpdate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_thread_for_workspace(workspace_id, thread_id)
    ThreadRepository().update_thread(thread_id, title=payload.title, status=payload.status)
    thread = ThreadRepository().get_thread(thread_id)
    return success_response(data=thread.model_dump(mode="json") if thread else {})


@router.get("/workspaces/{workspace_id}/threads/{thread_id}/messages")
def list_thread_messages(workspace_id: UUID, thread_id: UUID, limit: int = Query(default=50, le=200), principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _get_thread_for_workspace(workspace_id, thread_id)
    messages = ThreadRepository().list_messages(thread_id, limit=limit)
    return success_response(data=[m.model_dump(mode="json") for m in messages])


@router.post("/workspaces/{workspace_id}/threads/{thread_id}/messages")
def add_message(workspace_id: UUID, thread_id: UUID, payload: AgentMessageCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    thread = _get_thread_for_workspace(workspace_id, thread_id)
    if payload.agent_id is not None and payload.agent_id != thread.agent_id:
        raise ApiError(code="CUSTOM_AGENT_NOT_FOUND", message="Custom agent was not found.", status_code=404)
    payload.thread_id = thread_id
    msg = ThreadRepository().create_message(payload)
    return success_response(data=msg.model_dump(mode="json"))


# ── Memories ────────────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/custom-agents/{agent_id}/memories")
def list_agent_memories(workspace_id: UUID, agent_id: UUID, memory_type: str | None = Query(default=None), principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    from apps.api.app.schemas.custom_agents import MemoryType as MT
    mt = MT(memory_type) if memory_type else None
    memories = MemoryRepository().list_by_agent(agent_id, memory_type=mt)
    return success_response(data=[m.model_dump(mode="json") for m in memories])


@router.post("/workspaces/{workspace_id}/custom-agents/{agent_id}/memories")
def create_agent_memory(workspace_id: UUID, agent_id: UUID, payload: AgentMemoryCreate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    payload.agent_id = agent_id
    mem = MemoryRepository().create(payload)
    return success_response(data=mem.model_dump(mode="json"))


@router.patch("/workspaces/{workspace_id}/custom-agents/{agent_id}/memories/{memory_id}")
def update_agent_memory(workspace_id: UUID, agent_id: UUID, memory_id: UUID, payload: AgentMemoryUpdate, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_memory_for_agent(workspace_id, agent_id, memory_id)
    mem = MemoryRepository().update(memory_id, payload)
    if not mem:
        raise ApiError(code="MEMORY_NOT_FOUND", message="Memory entry was not found.", status_code=404)
    return success_response(data=mem.model_dump(mode="json"))


@router.delete("/workspaces/{workspace_id}/custom-agents/{agent_id}/memories/{memory_id}")
def delete_agent_memory(workspace_id: UUID, agent_id: UUID, memory_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    _get_memory_for_agent(workspace_id, agent_id, memory_id)
    deleted = MemoryRepository().delete(memory_id)
    if not deleted:
        raise ApiError(code="MEMORY_NOT_FOUND", message="Memory entry was not found.", status_code=404)
    return success_response(data={"id": str(memory_id), "deleted": True})


# ── Agent Run Execution ─────────────────────────────────────────────────────

@router.post("/workspaces/{workspace_id}/custom-agents/{agent_id}/run")
def run_custom_agent(workspace_id: UUID, agent_id: UUID, payload: AgentRunRequest, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    """Start an agent run. The agent runtime orchestrates the full pipeline:
    planner -> sub-agents -> tools -> reviewer -> output format -> approval check."""
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    agent = _get_agent_for_workspace(workspace_id, agent_id)
    if payload.thread_id is not None:
        thread = _get_thread_for_workspace(workspace_id, payload.thread_id)
        if thread.agent_id != agent_id:
            raise ApiError(code="THREAD_NOT_FOUND", message="Thread was not found.", status_code=404)

    run_repo = CustomAgentRunRepository()
    run_id = run_repo.create_run(
        workspace_id=workspace_id, agent_id=agent_id,
        thread_id=payload.thread_id,
        model_provider=agent.model_provider.value,
        model_name=agent.model_name,
        input_json={"message": payload.message, "metadata": payload.metadata_json},
    )

    # Record a planning step (in real system this would run actual LLM orchestration)
    run_repo.add_step(
        run_id=run_id, workspace_id=workspace_id,
        agent_name=agent.name, step_type="planner", step_order=1,
        input_json={"message": payload.message},
        output_json={"plan": f"Processing request for agent: {agent.name}", "sub_agents": [sa.name for sa in agent.sub_agents]},
        status="completed", latency_ms=50,
    )

    # Mark the run as completed (placeholder - real implementation orchestrates sub-agents)
    run_repo.complete_run(
        run_id=run_id, status="completed",
        output_json={"message": f"Agent '{agent.name}' acknowledged: {payload.message}", "note": "Agent runtime executes planner -> sub-agents -> tools -> reviewer -> output format. Full orchestration coming in next iteration."},
        latency_ms=100, tool_call_count=0,
    )

    run_detail = run_repo.get_run(run_id)
    return success_response(data=run_detail.model_dump(mode="json") if run_detail else {})


@router.get("/workspaces/{workspace_id}/custom-agents/{agent_id}/runs")
def list_agent_runs(workspace_id: UUID, agent_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    _get_agent_for_workspace(workspace_id, agent_id)
    # For MVP we return a simple list; in production this would query by agent_id
    return success_response(data=[])


@router.get("/workspaces/{workspace_id}/custom-agent-runs/{run_id}")
def get_agent_run(workspace_id: UUID, run_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    run = _get_run_for_workspace(workspace_id, run_id)
    return success_response(data=run.model_dump(mode="json"))


# ── Agent Templates ─────────────────────────────────────────────────────────

@router.get("/workspaces/{workspace_id}/agent-templates")
def list_agent_templates(workspace_id: UUID, category: str | None = Query(default=None), principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_READ_ROLES)
    templates = AgentTemplateRepository().list_templates(category=category)
    return success_response(data=[t.model_dump(mode="json") for t in templates])


@router.post("/workspaces/{workspace_id}/agent-templates/{template_id}/clone")
def clone_agent_template(workspace_id: UUID, template_id: UUID, principal: WorkspacePrincipal = Depends(require_workspace_member)) -> dict:
    """Clone a template into a new custom agent."""
    principal.ensure_workspace(workspace_id)
    principal.require_role(AGENT_BUILDER_ROLES)
    template = AgentTemplateRepository().get_template(template_id)
    if not template:
        raise ApiError(code="TEMPLATE_NOT_FOUND", message="Agent template was not found.", status_code=404)
    config = template.config_json
    agent = CustomAgentRepository().create(CustomAgentCreate(
        workspace_id=workspace_id,
        name=f"{config.get('name', 'Cloned Agent')}",
        description=template.description,
        role_instructions=config.get("role_instructions"),
        model_provider=config.get("model_provider", "deepseek"),
        model_name=config.get("model_name", "deepseek-chat"),
        temperature=config.get("temperature", 0.7),
        memory_enabled=config.get("memory_enabled", False),
        output_format=config.get("output_format", "text"),
        workflow_type=config.get("workflow_type", "sequential"),
        created_by=principal.user_id,
    ))
    # Clone tools from template
    tool_names = config.get("tools", [])
    for tool_name in tool_names:
        try:
            tool_def = next((t for t in AVAILABLE_TOOLS if t["tool_name"] == tool_name), None)
            ToolRepository().create(AgentToolCreate(
                agent_id=agent.id,
                tool_name=tool_name,
                requires_approval=tool_def.get("requires_approval_by_default", False) if tool_def else False,
                permission_level=tool_def.get("default_permission_level", "read") if tool_def else "read",
            ))
        except Exception:
            pass
    # Clone sub-agents from template
    sa_configs = config.get("sub_agents", [])
    for i, sa in enumerate(sa_configs):
        try:
            SubAgentRepository().create(SubAgentCreate(
                parent_agent_id=agent.id,
                name=sa.get("name", f"Sub-Agent {i + 1}"),
                role=sa.get("role", "general"),
                instructions=sa.get("instructions", ""),
                execution_order=i + 1,
                tools_json=sa.get("tools", []),
            ))
        except Exception:
            pass
    return success_response(data=agent.model_dump(mode="json"))


def _get_agent_for_workspace(workspace_id: UUID, agent_id: UUID):
    agent = CustomAgentRepository().get_by_id(agent_id)
    if not agent or agent.workspace_id != workspace_id:
        raise ApiError(code="CUSTOM_AGENT_NOT_FOUND", message="Custom agent was not found.", status_code=404)
    return agent


def _get_tool_for_agent(workspace_id: UUID, agent_id: UUID, tool_id: UUID):
    _get_agent_for_workspace(workspace_id, agent_id)
    tool = ToolRepository().get_by_id(tool_id)
    if not tool or tool.agent_id != agent_id:
        raise ApiError(code="TOOL_NOT_FOUND", message="Agent tool was not found.", status_code=404)
    return tool


def _get_kb_for_workspace(workspace_id: UUID, kb_id: UUID):
    kb = KnowledgeBaseRepository().get_by_id(kb_id)
    if not kb or kb.workspace_id != workspace_id:
        raise ApiError(code="KNOWLEDGE_BASE_NOT_FOUND", message="Knowledge base was not found.", status_code=404)
    return kb


def _get_sub_agent_for_agent(workspace_id: UUID, agent_id: UUID, sub_agent_id: UUID):
    _get_agent_for_workspace(workspace_id, agent_id)
    sub = SubAgentRepository().get_by_id(sub_agent_id)
    if not sub or sub.parent_agent_id != agent_id:
        raise ApiError(code="SUB_AGENT_NOT_FOUND", message="Sub-agent was not found.", status_code=404)
    return sub


def _get_thread_for_workspace(workspace_id: UUID, thread_id: UUID):
    thread = ThreadRepository().get_thread(thread_id)
    if not thread or thread.workspace_id != workspace_id:
        raise ApiError(code="THREAD_NOT_FOUND", message="Thread was not found.", status_code=404)
    return thread


def _get_memory_for_agent(workspace_id: UUID, agent_id: UUID, memory_id: UUID):
    _get_agent_for_workspace(workspace_id, agent_id)
    memory = MemoryRepository().get_by_id(memory_id)
    if not memory or memory.agent_id != agent_id:
        raise ApiError(code="MEMORY_NOT_FOUND", message="Memory entry was not found.", status_code=404)
    return memory


def _get_run_for_workspace(workspace_id: UUID, run_id: UUID):
    run = CustomAgentRunRepository().get_run(run_id)
    if not run or run.workspace_id != workspace_id:
        raise ApiError(code="RUN_NOT_FOUND", message="Agent run was not found.", status_code=404)
    return run
