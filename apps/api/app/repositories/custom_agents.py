"""Repository layer for custom agent builder entities."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from apps.api.app.core.database import get_database_engine, run_database_operation
from apps.api.app.schemas.custom_agents import (
    AgentMemoryCreate,
    AgentMemoryResponse,
    AgentMemoryUpdate,
    AgentMessageCreate,
    AgentMessageResponse,
    AgentStatus,
    AgentThreadCreate,
    AgentThreadResponse,
    AgentToolCreate,
    AgentToolResponse,
    AgentToolUpdate,
    CustomAgentCreate,
    CustomAgentResponse,
    CustomAgentRunResponse,
    CustomAgentRunStepResponse,
    CustomAgentSummary,
    CustomAgentUpdate,
    KnowledgeBaseCreate,
    KnowledgeBaseFileResponse,
    KnowledgeBaseResponse,
    KnowledgeBaseUpdate,
    MemoryType,
    SubAgentCreate,
    SubAgentResponse,
    SubAgentUpdate,
)
from apps.api.app.schemas.agent_control import AgentTemplateResponse


class CustomAgentRepository:
    """Data access for custom_agents table."""

    def create(self, payload: CustomAgentCreate) -> CustomAgentResponse:
        agent_id = uuid4()
        now = datetime.now(UTC)
        return run_database_operation(lambda: self._insert(agent_id, payload, now))

    def _insert(self, agent_id: UUID, payload: CustomAgentCreate, now: datetime) -> CustomAgentResponse:
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO custom_agents (id, workspace_id, name, description, role_instructions,
                        model_provider, model_name, temperature, max_tokens, memory_enabled, memory_ttl_days,
                        output_format, output_schema, workflow_type, workflow_graph, status, metadata_json,
                        created_by, updated_by, created_at, updated_at)
                    VALUES (:id, :workspace_id, :name, :description, :role_instructions,
                        :model_provider, :model_name, :temperature, :max_tokens, :memory_enabled, :memory_ttl_days,
                        :output_format, :output_schema, :workflow_type, :workflow_graph, :status, :metadata_json,
                        :created_by, :updated_by, :created_at, :updated_at)
                """),
                dict(
                    id=agent_id, workspace_id=payload.workspace_id, name=payload.name,
                    description=payload.description, role_instructions=payload.role_instructions,
                    model_provider=payload.model_provider.value, model_name=payload.model_name,
                    temperature=payload.temperature, max_tokens=payload.max_tokens,
                    memory_enabled=payload.memory_enabled, memory_ttl_days=payload.memory_ttl_days,
                    output_format=payload.output_format.value,
                    output_schema=_jsonb(payload.output_schema),
                    workflow_type=payload.workflow_type.value,
                    workflow_graph=_jsonb(payload.workflow_graph),
                    status=payload.status.value,
                    metadata_json=_jsonb(payload.metadata_json),
                    created_by=payload.created_by, updated_by=payload.created_by,
                    created_at=now, updated_at=now,
                ),
            )
            return self.get_by_id(agent_id, conn=conn)

    def list_by_workspace(self, workspace_id: UUID, *, conn=None) -> list[CustomAgentSummary]:
        engine = get_database_engine()
        executor = conn or engine
        rows = executor.execute(
            text("""
                SELECT
                    ca.id, ca.workspace_id, ca.name, ca.description,
                    ca.model_provider, ca.model_name, ca.memory_enabled, ca.status,
                    ca.created_at, ca.updated_at,
                    COALESCE(t.tool_count, 0) AS tool_count,
                    COALESCE(sa.sub_agent_count, 0) AS sub_agent_count,
                    COALESCE(th.thread_count, 0) AS thread_count
                FROM custom_agents ca
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS tool_count FROM agent_tools WHERE agent_id = ca.id
                ) t ON true
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS sub_agent_count FROM sub_agents WHERE parent_agent_id = ca.id
                ) sa ON true
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS thread_count FROM agent_threads WHERE agent_id = ca.id
                ) th ON true
                WHERE ca.workspace_id = :workspace_id
                ORDER BY ca.updated_at DESC
            """),
            dict(workspace_id=workspace_id),
        ).mappings().all()
        return [_summary_row(row) for row in rows]

    def get_by_id(self, agent_id: UUID, *, conn=None) -> CustomAgentResponse | None:
        engine = get_database_engine()
        executor = conn or engine
        rows = executor.execute(
            text("SELECT * FROM custom_agents WHERE id = :id"),
            dict(id=agent_id),
        ).mappings().all()
        if not rows:
            return None
        return self._enrich_response(_agent_row(rows[0]))

    def update(self, agent_id: UUID, payload: CustomAgentUpdate) -> CustomAgentResponse | None:
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            sets = []
            params: dict = {"id": agent_id, "updated_at": now}
            for field, value in payload.model_dump(exclude_none=True).items():
                col = field
                if isinstance(value, dict):
                    sets.append(f"{col} = :{col}")
                    params[col] = _jsonb(value)
                elif isinstance(value, (AgentStatus,)):
                    sets.append(f"{col} = :{col}")
                    params[col] = value.value
                else:
                    sets.append(f"{col} = :{col}")
                    params[col] = value
            if not sets:
                return self.get_by_id(agent_id)
            result = conn.execute(
                text(f"UPDATE custom_agents SET {', '.join(sets)}, updated_at = :updated_at WHERE id = :id"),
                params,
            )
            if result.rowcount == 0:
                return None
            return self.get_by_id(agent_id)

    def delete(self, agent_id: UUID) -> bool:
        engine = get_database_engine()
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM custom_agents WHERE id = :id"), dict(id=agent_id))
            return result.rowcount > 0

    def _enrich_response(self, agent: dict, *, conn=None) -> CustomAgentResponse:
        engine = get_database_engine()
        executor = conn or engine
        agent_id = agent["id"]
        tools = ToolRepository().list_by_agent(agent_id)
        sub_agents = SubAgentRepository().list_by_agent(agent_id)
        kb_rows = executor.execute(
            text("SELECT knowledge_base_id FROM agent_knowledge_bases WHERE agent_id = :agent_id"),
            dict(agent_id=agent_id),
        ).mappings().all()
        kb_ids = [row["knowledge_base_id"] for row in kb_rows]
        return CustomAgentResponse(
            id=agent["id"], workspace_id=agent["workspace_id"], name=agent["name"],
            description=agent.get("description"), role_instructions=agent.get("role_instructions"),
            model_provider=agent["model_provider"], model_name=agent["model_name"],
            temperature=float(agent.get("temperature", 0.7)), max_tokens=agent.get("max_tokens", 4096),
            memory_enabled=bool(agent.get("memory_enabled", False)),
            memory_ttl_days=agent.get("memory_ttl_days", 30),
            output_format=agent.get("output_format", "text"),
            output_schema=agent.get("output_schema"),
            workflow_type=agent.get("workflow_type", "sequential"),
            workflow_graph=agent.get("workflow_graph"),
            status=agent.get("status", "draft"),
            metadata_json=agent.get("metadata_json") or {},
            created_by=agent.get("created_by"), updated_by=agent.get("updated_by"),
            created_at=agent["created_at"], updated_at=agent["updated_at"],
            tools=tools, sub_agents=sub_agents, knowledge_base_ids=kb_ids,
        )


class ToolRepository:
    """Data access for agent_tools table."""

    def list_by_agent(self, agent_id: UUID) -> list[AgentToolResponse]:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM agent_tools WHERE agent_id = :agent_id ORDER BY tool_name"),
            dict(agent_id=agent_id),
        ).mappings().all()
        return [_tool_row(row) for row in rows]

    def create(self, payload: AgentToolCreate) -> AgentToolResponse:
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_tools (id, workspace_id, agent_id, tool_name, tool_config,
                        enabled, permission_level, requires_approval, rate_limit_per_day,
                        allowed_domains, allowed_actions, created_at, updated_at)
                    VALUES (:id, :workspace_id, :agent_id, :tool_name, :tool_config,
                        :enabled, :permission_level, :requires_approval, :rate_limit_per_day,
                        :allowed_domains, :allowed_actions, :created_at, :updated_at)
                """),
                dict(
                    id=uuid4(), workspace_id=UUID("00000000-0000-0000-0000-000000000000"),
                    agent_id=payload.agent_id, tool_name=payload.tool_name,
                    tool_config=_jsonb(payload.tool_config),
                    enabled=payload.enabled, permission_level=payload.permission_level.value,
                    requires_approval=payload.requires_approval,
                    rate_limit_per_day=payload.rate_limit_per_day,
                    allowed_domains=_jsonb(payload.allowed_domains) if payload.allowed_domains else None,
                    allowed_actions=_jsonb(payload.allowed_actions) if payload.allowed_actions else None,
                    created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
                ),
            )
        return self.get_by_agent_and_name(payload.agent_id, payload.tool_name)

    def update(self, tool_id: UUID, payload: AgentToolUpdate) -> AgentToolResponse | None:
        engine = get_database_engine()
        with engine.begin() as conn:
            sets = ["updated_at = :updated_at"]
            params = {"id": tool_id, "updated_at": datetime.now(UTC)}
            for field, value in payload.model_dump(exclude_none=True).items():
                if isinstance(value, dict) or isinstance(value, list):
                    sets.append(f"{field} = :{field}")
                    params[field] = _jsonb(value)
                elif isinstance(value, (ToolPermissionLevel,)):
                    sets.append(f"{field} = :{field}")
                    params[field] = value.value if hasattr(value, 'value') else value
                else:
                    sets.append(f"{field} = :{field}")
                    params[field] = value
            result = conn.execute(
                text(f"UPDATE agent_tools SET {', '.join(sets)} WHERE id = :id"),
                params,
            )
            if result.rowcount == 0:
                return None
        return self.get_by_id(tool_id)

    def get_by_id(self, tool_id: UUID) -> AgentToolResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM agent_tools WHERE id = :id"), dict(id=tool_id)
        ).mappings().all()
        return _tool_row(rows[0]) if rows else None

    def get_by_agent_and_name(self, agent_id: UUID, tool_name: str) -> AgentToolResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM agent_tools WHERE agent_id = :agent_id AND tool_name = :tool_name"),
            dict(agent_id=agent_id, tool_name=tool_name),
        ).mappings().all()
        return _tool_row(rows[0]) if rows else None

    def delete(self, tool_id: UUID) -> bool:
        engine = get_database_engine()
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM agent_tools WHERE id = :id"), dict(id=tool_id))
            return result.rowcount > 0


class KnowledgeBaseRepository:
    """Data access for knowledge_bases and related tables."""

    def create(self, payload: KnowledgeBaseCreate) -> KnowledgeBaseResponse:
        kb_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO knowledge_bases (id, workspace_id, name, description, source_type,
                        embedding_model, embedding_provider, status, created_by, created_at, updated_at)
                    VALUES (:id, :workspace_id, :name, :description, :source_type,
                        :embedding_model, :embedding_provider, :status, :created_by, :created_at, :updated_at)
                """),
                dict(
                    id=kb_id, workspace_id=payload.workspace_id, name=payload.name,
                    description=payload.description, source_type=payload.source_type,
                    embedding_model=payload.embedding_model,
                    embedding_provider=payload.embedding_provider,
                    status="pending", created_by=payload.created_by,
                    created_at=now, updated_at=now,
                ),
            )
        return self.get_by_id(kb_id)

    def list_by_workspace(self, workspace_id: UUID) -> list[KnowledgeBaseResponse]:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM knowledge_bases WHERE workspace_id = :workspace_id ORDER BY updated_at DESC"),
            dict(workspace_id=workspace_id),
        ).mappings().all()
        return [_kb_row(row) for row in rows]

    def get_by_id(self, kb_id: UUID) -> KnowledgeBaseResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM knowledge_bases WHERE id = :id"), dict(id=kb_id)
        ).mappings().all()
        if not rows:
            return None
        kb = _kb_row(rows[0])
        # enrich with files
        file_rows = engine.execute(
            text("SELECT * FROM knowledge_base_files WHERE knowledge_base_id = :kb_id ORDER BY created_at DESC"),
            dict(kb_id=kb_id),
        ).mappings().all()
        kb.files = [_kbf_row(row) for row in file_rows]
        return kb

    def update(self, kb_id: UUID, payload: KnowledgeBaseUpdate) -> KnowledgeBaseResponse | None:
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            sets = ["updated_at = :updated_at"]
            params: dict = {"id": kb_id, "updated_at": now}
            for field, value in payload.model_dump(exclude_none=True).items():
                sets.append(f"{field} = :{field}")
                params[field] = value
            result = conn.execute(
                text(f"UPDATE knowledge_bases SET {', '.join(sets)} WHERE id = :id"),
                params,
            )
            if result.rowcount == 0:
                return None
        return self.get_by_id(kb_id)

    def delete(self, kb_id: UUID) -> bool:
        engine = get_database_engine()
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM knowledge_bases WHERE id = :id"), dict(id=kb_id))
            return result.rowcount > 0

    def create_file(self, kb_id: UUID, workspace_id: UUID, file_name: str, file_path: str, file_type: str, file_size: int) -> UUID:
        file_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO knowledge_base_files (id, workspace_id, knowledge_base_id, file_name,
                        file_path, file_type, file_size_bytes, status, created_at, updated_at)
                    VALUES (:id, :workspace_id, :kb_id, :file_name, :file_path, :file_type,
                        :file_size, :status, :created_at, :updated_at)
                """),
                dict(id=file_id, workspace_id=workspace_id, kb_id=kb_id, file_name=file_name,
                     file_path=file_path, file_type=file_type, file_size=file_size,
                     status="pending", created_at=now, updated_at=now),
            )
            conn.execute(
                text("UPDATE knowledge_bases SET file_count = file_count + 1, updated_at = :now WHERE id = :kb_id"),
                dict(now=now, kb_id=kb_id),
            )
        return file_id

    def update_file_status(self, file_id: UUID, status: str, chunk_count: int = 0, error: str | None = None):
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE knowledge_base_files SET status = :status, chunk_count = :chunk_count, error_message = :error, updated_at = :now WHERE id = :id"),
                dict(status=status, chunk_count=chunk_count, error=error, now=datetime.now(UTC), id=file_id),
            )

    def link_agent_to_kb(self, agent_id: UUID, kb_id: UUID, workspace_id: UUID):
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_knowledge_bases (id, workspace_id, agent_id, knowledge_base_id, created_at)
                    VALUES (:id, :workspace_id, :agent_id, :kb_id, :created_at)
                    ON CONFLICT (agent_id, knowledge_base_id) DO NOTHING
                """),
                dict(id=uuid4(), workspace_id=workspace_id, agent_id=agent_id, kb_id=kb_id,
                     created_at=datetime.now(UTC)),
            )

    def unlink_agent_from_kb(self, agent_id: UUID, kb_id: UUID) -> bool:
        engine = get_database_engine()
        with engine.begin() as conn:
            result = conn.execute(
                text("DELETE FROM agent_knowledge_bases WHERE agent_id = :agent_id AND knowledge_base_id = :kb_id"),
                dict(agent_id=agent_id, kb_id=kb_id),
            )
            return result.rowcount > 0


class SubAgentRepository:
    """Data access for sub_agents table."""

    def list_by_agent(self, parent_agent_id: UUID) -> list[SubAgentResponse]:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM sub_agents WHERE parent_agent_id = :parent_agent_id ORDER BY execution_order"),
            dict(parent_agent_id=parent_agent_id),
        ).mappings().all()
        return [_sub_row(row) for row in rows]

    def create(self, payload: SubAgentCreate) -> SubAgentResponse:
        sa_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO sub_agents (id, workspace_id, parent_agent_id, name, role, instructions,
                        model_provider, model_name, tools_json, execution_order, enabled,
                        requires_approval, created_at, updated_at)
                    VALUES (:id, :workspace_id, :parent_agent_id, :name, :role, :instructions,
                        :model_provider, :model_name, :tools_json, :execution_order, :enabled,
                        :requires_approval, :created_at, :updated_at)
                """),
                dict(
                    id=sa_id, workspace_id=UUID("00000000-0000-0000-0000-000000000000"),
                    parent_agent_id=payload.parent_agent_id, name=payload.name,
                    role=payload.role, instructions=payload.instructions,
                    model_provider=payload.model_provider.value if payload.model_provider else None,
                    model_name=payload.model_name,
                    tools_json=_jsonb(payload.tools_json),
                    execution_order=payload.execution_order,
                    enabled=payload.enabled, requires_approval=payload.requires_approval,
                    created_at=now, updated_at=now,
                ),
            )
        return self.get_by_id(sa_id)

    def update(self, sub_agent_id: UUID, payload: SubAgentUpdate) -> SubAgentResponse | None:
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            sets = ["updated_at = :updated_at"]
            params: dict = {"id": sub_agent_id, "updated_at": now}
            for field, value in payload.model_dump(exclude_none=True).items():
                if isinstance(value, list):
                    sets.append(f"{field} = :{field}")
                    params[field] = _jsonb(value)
                elif hasattr(value, 'value'):
                    sets.append(f"{field} = :{field}")
                    params[field] = value.value
                else:
                    sets.append(f"{field} = :{field}")
                    params[field] = value
            result = conn.execute(
                text(f"UPDATE sub_agents SET {', '.join(sets)} WHERE id = :id"),
                params,
            )
            if result.rowcount == 0:
                return None
        return self.get_by_id(sub_agent_id)

    def get_by_id(self, sa_id: UUID) -> SubAgentResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM sub_agents WHERE id = :id"), dict(id=sa_id)
        ).mappings().all()
        return _sub_row(rows[0]) if rows else None

    def delete(self, sa_id: UUID) -> bool:
        engine = get_database_engine()
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM sub_agents WHERE id = :id"), dict(id=sa_id))
            return result.rowcount > 0


class ThreadRepository:
    """Data access for agent_threads and agent_messages."""

    def create_thread(self, payload: AgentThreadCreate) -> AgentThreadResponse:
        thread_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        agent = CustomAgentRepository().get_by_id(payload.agent_id)
        workspace_id = agent.workspace_id if agent else UUID("00000000-0000-0000-0000-000000000000")
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_threads (id, workspace_id, agent_id, title, status, metadata_json,
                        created_by, created_at, updated_at)
                    VALUES (:id, :workspace_id, :agent_id, :title, :status, :metadata_json,
                        :created_by, :created_at, :updated_at)
                """),
                dict(id=thread_id, workspace_id=workspace_id, agent_id=payload.agent_id,
                     title=payload.title, status="active", metadata_json=_jsonb(payload.metadata_json),
                     created_by=payload.created_by, created_at=now, updated_at=now),
            )
        return self.get_thread(thread_id)

    def list_threads(self, workspace_id: UUID) -> list[AgentThreadResponse]:
        engine = get_database_engine()
        rows = engine.execute(
            text("""
                SELECT t.*, COUNT(m.id) as message_count, MAX(m.created_at) as last_message_at
                FROM agent_threads t
                LEFT JOIN agent_messages m ON m.thread_id = t.id
                WHERE t.workspace_id = :workspace_id
                GROUP BY t.id
                ORDER BY t.updated_at DESC
            """),
            dict(workspace_id=workspace_id),
        ).mappings().all()
        return [_thread_row(row) for row in rows]

    def list_threads_by_agent(self, agent_id: UUID) -> list[AgentThreadResponse]:
        engine = get_database_engine()
        rows = engine.execute(
            text("""
                SELECT t.*, COUNT(m.id) as message_count, MAX(m.created_at) as last_message_at
                FROM agent_threads t
                LEFT JOIN agent_messages m ON m.thread_id = t.id
                WHERE t.agent_id = :agent_id
                GROUP BY t.id
                ORDER BY t.updated_at DESC
            """),
            dict(agent_id=agent_id),
        ).mappings().all()
        return [_thread_row(row) for row in rows]

    def get_thread(self, thread_id: UUID) -> AgentThreadResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("""
                SELECT t.*, COUNT(m.id) as message_count, MAX(m.created_at) as last_message_at
                FROM agent_threads t
                LEFT JOIN agent_messages m ON m.thread_id = t.id
                WHERE t.id = :id
                GROUP BY t.id
            """),
            dict(id=thread_id),
        ).mappings().all()
        return _thread_row(rows[0]) if rows else None

    def create_message(self, payload: AgentMessageCreate) -> AgentMessageResponse:
        msg_id = uuid4()
        now = datetime.now(UTC)
        thread = self.get_thread(payload.thread_id)
        workspace_id = thread.workspace_id if thread else UUID("00000000-0000-0000-0000-000000000000")
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_messages (id, workspace_id, thread_id, agent_id, role, content,
                        tool_calls_json, tool_call_id, sub_agent_name, metadata_json, created_at)
                    VALUES (:id, :workspace_id, :thread_id, :agent_id, :role, :content,
                        :tool_calls_json, :tool_call_id, :sub_agent_name, :metadata_json, :created_at)
                """),
                dict(id=msg_id, workspace_id=workspace_id, thread_id=payload.thread_id,
                     agent_id=payload.agent_id, role=payload.role, content=payload.content,
                     tool_calls_json=_jsonb(payload.tool_calls_json) if payload.tool_calls_json else None,
                     tool_call_id=payload.tool_call_id,
                     sub_agent_name=payload.sub_agent_name,
                     metadata_json=_jsonb(payload.metadata_json), created_at=now),
            )
            conn.execute(
                text("UPDATE agent_threads SET updated_at = :now WHERE id = :thread_id"),
                dict(now=now, thread_id=payload.thread_id),
            )
        return self.get_message(msg_id)

    def list_messages(self, thread_id: UUID, limit: int = 50) -> list[AgentMessageResponse]:
        engine = get_database_engine()
        rows = engine.execute(
            text("""
                SELECT * FROM agent_messages
                WHERE thread_id = :thread_id
                ORDER BY created_at ASC
                LIMIT :limit
            """),
            dict(thread_id=thread_id, limit=limit),
        ).mappings().all()
        return [_msg_row(row) for row in rows]

    def get_message(self, msg_id: UUID) -> AgentMessageResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM agent_messages WHERE id = :id"), dict(id=msg_id)
        ).mappings().all()
        return _msg_row(rows[0]) if rows else None

    def update_thread(self, thread_id: UUID, title: str | None = None, status: str | None = None):
        engine = get_database_engine()
        with engine.begin() as conn:
            sets = ["updated_at = :now"]
            params: dict = {"id": thread_id, "now": datetime.now(UTC)}
            if title is not None:
                sets.append("title = :title")
                params["title"] = title
            if status is not None:
                sets.append("status = :status")
                params["status"] = status
            conn.execute(
                text(f"UPDATE agent_threads SET {', '.join(sets)} WHERE id = :id"),
                params,
            )


class MemoryRepository:
    """Data access for agent_memories table."""

    def create(self, payload: AgentMemoryCreate) -> AgentMemoryResponse:
        mem_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        agent = CustomAgentRepository().get_by_id(payload.agent_id)
        workspace_id = agent.workspace_id if agent else UUID("00000000-0000-0000-0000-000000000000")
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO agent_memories (id, workspace_id, agent_id, thread_id, memory_type,
                        content, importance, expires_at, metadata_json, created_at, updated_at)
                    VALUES (:id, :workspace_id, :agent_id, :thread_id, :memory_type,
                        :content, :importance, :expires_at, :metadata_json, :created_at, :updated_at)
                """),
                dict(id=mem_id, workspace_id=workspace_id, agent_id=payload.agent_id,
                     thread_id=payload.thread_id, memory_type=payload.memory_type.value,
                     content=payload.content, importance=payload.importance,
                     expires_at=payload.expires_at, metadata_json=_jsonb(payload.metadata_json),
                     created_at=now, updated_at=now),
            )
        return self.get_by_id(mem_id)

    def list_by_agent(self, agent_id: UUID, memory_type: MemoryType | None = None) -> list[AgentMemoryResponse]:
        engine = get_database_engine()
        query = "SELECT * FROM agent_memories WHERE agent_id = :agent_id"
        params: dict = {"agent_id": agent_id}
        if memory_type:
            query += " AND memory_type = :memory_type"
            params["memory_type"] = memory_type.value
        query += " ORDER BY importance DESC, updated_at DESC"
        rows = engine.execute(text(query), params).mappings().all()
        return [_mem_row(row) for row in rows]

    def get_by_id(self, mem_id: UUID) -> AgentMemoryResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM agent_memories WHERE id = :id"), dict(id=mem_id)
        ).mappings().all()
        if rows:
            # increment access count
            with engine.begin() as conn:
                conn.execute(
                    text("UPDATE agent_memories SET access_count = access_count + 1, last_accessed_at = :now WHERE id = :id"),
                    dict(now=datetime.now(UTC), id=mem_id),
                )
        return _mem_row(rows[0]) if rows else None

    def update(self, mem_id: UUID, payload: AgentMemoryUpdate) -> AgentMemoryResponse | None:
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            sets = ["updated_at = :updated_at"]
            params: dict = {"id": mem_id, "updated_at": now}
            for field, value in payload.model_dump(exclude_none=True).items():
                sets.append(f"{field} = :{field}")
                params[field] = value
            result = conn.execute(
                text(f"UPDATE agent_memories SET {', '.join(sets)} WHERE id = :id"),
                params,
            )
            if result.rowcount == 0:
                return None
        return self.get_by_id(mem_id)

    def delete(self, mem_id: UUID) -> bool:
        engine = get_database_engine()
        with engine.begin() as conn:
            result = conn.execute(text("DELETE FROM agent_memories WHERE id = :id"), dict(id=mem_id))
            return result.rowcount > 0


class CustomAgentRunRepository:
    """Data access for custom_agent_runs and custom_agent_run_steps."""

    def create_run(self, workspace_id: UUID, agent_id: UUID, thread_id: UUID | None,
                   model_provider: str, model_name: str, input_json: dict) -> UUID:
        run_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO custom_agent_runs (id, workspace_id, agent_id, thread_id, status,
                        model_provider, model_name, input_json, created_at, started_at)
                    VALUES (:id, :workspace_id, :agent_id, :thread_id, :status,
                        :model_provider, :model_name, :input_json, :created_at, :started_at)
                """),
                dict(id=run_id, workspace_id=workspace_id, agent_id=agent_id,
                     thread_id=thread_id, status="running",
                     model_provider=model_provider, model_name=model_name,
                     input_json=_jsonb(input_json), created_at=now, started_at=now),
            )
        return run_id

    def add_step(self, run_id: UUID, workspace_id: UUID, agent_name: str | None,
                 step_type: str, step_order: int, input_json: dict, output_json: dict,
                 status: str, latency_ms: int | None = None, error_message: str | None = None) -> UUID:
        step_id = uuid4()
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO custom_agent_run_steps (id, workspace_id, run_id, agent_name,
                        step_type, step_order, input_json, output_json, status, error_message,
                        latency_ms, created_at, completed_at)
                    VALUES (:id, :workspace_id, :run_id, :agent_name, :step_type, :step_order,
                        :input_json, :output_json, :status, :error_message, :latency_ms,
                        :created_at, :completed_at)
                """),
                dict(id=step_id, workspace_id=workspace_id, run_id=run_id,
                     agent_name=agent_name, step_type=step_type, step_order=step_order,
                     input_json=_jsonb(input_json), output_json=_jsonb(output_json),
                     status=status, error_message=error_message,
                     latency_ms=latency_ms, created_at=now,
                     completed_at=now if status in ("completed", "failed", "skipped") else None),
            )
        return step_id

    def complete_run(self, run_id: UUID, status: str, output_json: dict, error_json: dict | None = None,
                     tokens_input: int = 0, tokens_output: int = 0, cost_usd: float = 0,
                     latency_ms: int | None = None, tool_call_count: int = 0,
                     knowledge_chunks_retrieved: int = 0):
        now = datetime.now(UTC)
        engine = get_database_engine()
        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE custom_agent_runs SET status = :status, output_json = :output_json,
                        error_json = :error_json, tokens_input = :tokens_input,
                        tokens_output = :tokens_output, cost_usd = :cost_usd,
                        latency_ms = :latency_ms, tool_call_count = :tool_call_count,
                        knowledge_chunks_retrieved = :kcr,
                        completed_at = :completed_at
                    WHERE id = :id
                """),
                dict(id=run_id, status=status, output_json=_jsonb(output_json),
                     error_json=_jsonb(error_json or {}), tokens_input=tokens_input,
                     tokens_output=tokens_output, cost_usd=cost_usd,
                     latency_ms=latency_ms, tool_call_count=tool_call_count,
                     kcr=knowledge_chunks_retrieved, completed_at=now),
            )

    def get_run(self, run_id: UUID) -> CustomAgentRunResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM custom_agent_runs WHERE id = :id"), dict(id=run_id)
        ).mappings().all()
        if not rows:
            return None
        row = rows[0]
        step_rows = engine.execute(
            text("SELECT * FROM custom_agent_run_steps WHERE run_id = :run_id ORDER BY step_order"),
            dict(run_id=run_id),
        ).mappings().all()
        steps = [_run_step_row(s) for s in step_rows]
        return CustomAgentRunResponse(
            id=row["id"], workspace_id=row["workspace_id"], agent_id=row["agent_id"],
            thread_id=row.get("thread_id"), status=row["status"],
            model_provider=row.get("model_provider"), model_name=row.get("model_name"),
            input_json=row.get("input_json") or {},
            output_json=row.get("output_json") or {},
            error_json=row.get("error_json") or {},
            tokens_input=row.get("tokens_input", 0),
            tokens_output=row.get("tokens_output", 0),
            cost_usd=float(row.get("cost_usd", 0)),
            latency_ms=row.get("latency_ms"),
            sub_agent_runs_json=row.get("sub_agent_runs_json") or [],
            tool_call_count=row.get("tool_call_count", 0),
            knowledge_chunks_retrieved=row.get("knowledge_chunks_retrieved", 0),
            metadata_json=row.get("metadata_json") or {},
            started_at=row.get("started_at"),
            completed_at=row.get("completed_at"),
            created_at=row["created_at"],
            steps=steps,
        )


class AgentTemplateRepository:
    """Data access for agent_templates table."""

    def list_templates(self, category: str | None = None) -> list[AgentTemplateResponse]:
        engine = get_database_engine()
        query = "SELECT * FROM agent_templates WHERE is_public = true"
        params: dict = {}
        if category:
            query += " AND category = :category"
            params["category"] = category
        query += " ORDER BY usage_count DESC"
        rows = engine.execute(text(query), params).mappings().all()
        return [_template_row(row) for row in rows]

    def get_template(self, template_id: UUID) -> AgentTemplateResponse | None:
        engine = get_database_engine()
        rows = engine.execute(
            text("SELECT * FROM agent_templates WHERE id = :id"), dict(id=template_id)
        ).mappings().all()
        return _template_row(rows[0]) if rows else None


# ── Helper row constructors ──────────────────────────────────────────────────

def _summary_row(row: dict) -> CustomAgentSummary:
    return CustomAgentSummary(
        id=row["id"], workspace_id=row["workspace_id"], name=row["name"],
        description=row.get("description"),
        model_provider=row["model_provider"],
        model_name=row["model_name"],
        memory_enabled=bool(row.get("memory_enabled", False)),
        status=row.get("status", "draft"),
        created_at=row["created_at"], updated_at=row["updated_at"],
        tool_count=row.get("tool_count", 0),
        sub_agent_count=row.get("sub_agent_count", 0),
        thread_count=row.get("thread_count", 0),
    )


def _agent_row(row: dict) -> dict:
    return dict(row)


def _tool_row(row: dict) -> AgentToolResponse:
    return AgentToolResponse(
        id=row["id"], workspace_id=row["workspace_id"], agent_id=row["agent_id"],
        tool_name=row["tool_name"], tool_config=row.get("tool_config") or {},
        enabled=bool(row.get("enabled", True)),
        permission_level=row.get("permission_level", "read"),
        requires_approval=bool(row.get("requires_approval", False)),
        rate_limit_per_day=row.get("rate_limit_per_day"),
        allowed_domains=row.get("allowed_domains"),
        allowed_actions=row.get("allowed_actions"),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _kb_row(row: dict) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse(
        id=row["id"], workspace_id=row["workspace_id"], name=row["name"],
        description=row.get("description"), source_type=row.get("source_type", "upload"),
        embedding_model=row.get("embedding_model", "text-embedding-3-small"),
        embedding_provider=row.get("embedding_provider", "openai"),
        file_count=row.get("file_count", 0),
        chunk_count=row.get("chunk_count", 0),
        status=row.get("status", "pending"),
        created_by=row.get("created_by"),
        created_at=row["created_at"], updated_at=row["updated_at"],
        files=[],
    )


def _kbf_row(row: dict) -> KnowledgeBaseFileResponse:
    return KnowledgeBaseFileResponse(
        id=row["id"], knowledge_base_id=row["knowledge_base_id"],
        file_name=row["file_name"], file_path=row["file_path"],
        file_type=row["file_type"], file_size_bytes=row.get("file_size_bytes"),
        chunk_count=row.get("chunk_count", 0),
        status=row.get("status", "pending"),
        error_message=row.get("error_message"),
        created_at=row["created_at"],
    )


def _sub_row(row: dict) -> SubAgentResponse:
    return SubAgentResponse(
        id=row["id"], workspace_id=row["workspace_id"],
        parent_agent_id=row["parent_agent_id"],
        name=row["name"], role=row["role"], instructions=row["instructions"],
        model_provider=row.get("model_provider"),
        model_name=row.get("model_name"),
        tools_json=row.get("tools_json") or [],
        execution_order=row.get("execution_order", 1),
        enabled=bool(row.get("enabled", True)),
        requires_approval=bool(row.get("requires_approval", False)),
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _thread_row(row: dict) -> AgentThreadResponse:
    return AgentThreadResponse(
        id=row["id"], workspace_id=row["workspace_id"], agent_id=row["agent_id"],
        title=row.get("title"), status=row.get("status", "active"),
        metadata_json=row.get("metadata_json") or {},
        created_by=row.get("created_by"),
        created_at=row["created_at"], updated_at=row["updated_at"],
        message_count=row.get("message_count", 0),
        last_message_at=row.get("last_message_at"),
    )


def _msg_row(row: dict) -> AgentMessageResponse:
    return AgentMessageResponse(
        id=row["id"], workspace_id=row["workspace_id"],
        thread_id=row["thread_id"], agent_id=row.get("agent_id"),
        role=row["role"], content=row.get("content"),
        tool_calls_json=row.get("tool_calls_json"),
        tool_call_id=row.get("tool_call_id"),
        sub_agent_name=row.get("sub_agent_name"),
        token_count=row.get("token_count"),
        metadata_json=row.get("metadata_json") or {},
        created_at=row["created_at"],
    )


def _mem_row(row: dict) -> AgentMemoryResponse:
    return AgentMemoryResponse(
        id=row["id"], workspace_id=row["workspace_id"], agent_id=row["agent_id"],
        thread_id=row.get("thread_id"),
        memory_type=row.get("memory_type", "preference"),
        content=row["content"],
        importance=float(row.get("importance", 0.5)),
        access_count=row.get("access_count", 0),
        last_accessed_at=row.get("last_accessed_at"),
        expires_at=row.get("expires_at"),
        metadata_json=row.get("metadata_json") or {},
        created_at=row["created_at"], updated_at=row["updated_at"],
    )


def _run_step_row(row: dict) -> CustomAgentRunStepResponse:
    return CustomAgentRunStepResponse(
        id=row["id"], workspace_id=row["workspace_id"], run_id=row["run_id"],
        agent_name=row.get("agent_name"),
        step_type=row["step_type"], step_order=row["step_order"],
        input_json=row.get("input_json") or {},
        output_json=row.get("output_json") or {},
        status=row.get("status", "pending"),
        error_message=row.get("error_message"),
        latency_ms=row.get("latency_ms"),
        created_at=row["created_at"],
        completed_at=row.get("completed_at"),
    )


def _template_row(row: dict) -> AgentTemplateResponse:
    return AgentTemplateResponse(
        id=row["id"], name=row["name"], description=row["description"],
        category=row["category"], config_json=row.get("config_json") or {},
        is_public=bool(row.get("is_public", True)),
        usage_count=row.get("usage_count", 0),
        created_at=row["created_at"],
    )


def _jsonb(value):
    """Return value as-is; SQLAlchemy text() handles dict/list serialization to PostgreSQL JSONB."""
    if value is None:
        return None
    return value