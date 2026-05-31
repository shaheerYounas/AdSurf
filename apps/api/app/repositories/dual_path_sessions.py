"""Repository for dual-path decision sessions — stores every AI vs deterministic comparison."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from apps.api.app.schemas.dual_path_sessions import DualPathSession, DualPathSessionListItem


class DualPathSessionRepository:
    """Persists dual-path sessions to the database."""

    def __init__(self, db=None):
        self._db = db

    def create_session(self, *, workspace_id: UUID, product_id: UUID | None, agent_id: str, mode: str, input_summary: dict, provider: str | None = None, model_name: str | None = None, created_by: str | None = None) -> DualPathSession:
        """Create a new pending session record."""
        now = datetime.now(UTC)
        session = DualPathSession(
            id=uuid4(),
            workspace_id=workspace_id,
            product_id=product_id,
            agent_id=agent_id,
            mode=mode,
            provider=provider,
            model=model_name,
            status="pending",
            input_summary_json=input_summary,
            created_at=now,
            created_by=created_by,
        )
        self._insert(session)
        return session

    def complete_deterministic(self, *, session_id: UUID, result_json: dict, latency_ms: int = 0) -> DualPathSession:
        """Save deterministic path result."""
        session = self._get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        session.deterministic_result_json = result_json
        session.deterministic_latency_ms = latency_ms
        self._update(session)
        return session

    def complete_ai(self, *, session_id: UUID, result_json: dict, prompt_json: dict | None = None, model_params_json: dict | None = None, latency_ms: int = 0) -> DualPathSession:
        """Save AI path result."""
        session = self._get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        session.ai_result_json = result_json
        session.ai_latency_ms = latency_ms
        session.ai_prompt_json = prompt_json
        session.ai_model_params_json = model_params_json
        self._update(session)
        return session

    def finalize_session(self, *, session_id: UUID, decision_source: str, used_ai: bool, fallback_used: bool, validation_errors: list[str] | None = None, comparison_summary: dict | None = None, status: str = "succeeded") -> DualPathSession:
        """Mark session as completed with final metadata."""
        session = self._get(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")
        session.decision_source = decision_source
        session.used_ai = used_ai
        session.fallback_used = fallback_used
        session.validation_errors = validation_errors or []
        session.comparison_summary_json = comparison_summary
        session.status = status
        session.completed_at = datetime.now(UTC)
        self._update(session)
        return session

    def get_session(self, session_id: UUID) -> DualPathSession | None:
        return self._get(session_id)

    def list_sessions(self, *, workspace_id: UUID, agent_id: str | None = None, page: int = 1, page_size: int = 50) -> tuple[list[DualPathSessionListItem], int]:
        """List sessions for a workspace, optionally filtered by agent."""
        # Simulated — in production, queries the DB
        all_sessions = self._list_all(workspace_id)
        if agent_id:
            all_sessions = [s for s in all_sessions if s.agent_id == agent_id]
        total = len(all_sessions)
        start = (page - 1) * page_size
        items = [
            DualPathSessionListItem(
                id=s.id,
                agent_id=s.agent_id,
                mode=s.mode,
                status=s.status,
                provider=s.provider,
                model=s.model,
                decision_source=s.decision_source,
                used_ai=s.used_ai,
                fallback_used=s.fallback_used,
                created_at=s.created_at,
                completed_at=s.completed_at,
            )
            for s in all_sessions[start:start + page_size]
        ]
        return items, total

    # -- Internal storage (in-memory for MVP) --

    _store: dict[UUID, DualPathSession] = {}

    def _insert(self, session: DualPathSession) -> None:
        DualPathSessionRepository._store[session.id] = session

    def _update(self, session: DualPathSession) -> None:
        DualPathSessionRepository._store[session.id] = session

    def _get(self, session_id: UUID) -> DualPathSession | None:
        return DualPathSessionRepository._store.get(session_id)

    def _list_all(self, workspace_id: UUID) -> list[DualPathSession]:
        return [s for s in DualPathSessionRepository._store.values() if s.workspace_id == workspace_id]


# Singleton accessor
_session_repo: DualPathSessionRepository | None = None


def get_dual_path_session_repository() -> DualPathSessionRepository:
    global _session_repo
    if _session_repo is None:
        _session_repo = DualPathSessionRepository()
    return _session_repo