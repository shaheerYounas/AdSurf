from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from fastapi import Request

from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import ApiError


class WorkspaceRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    APPROVER = "approver"
    VIEWER = "viewer"


CANONICAL_WORKSPACE_ROLES = tuple(role.value for role in WorkspaceRole)


@dataclass(frozen=True)
class WorkspacePrincipal:
    user_id: str
    workspace_id: UUID
    role: WorkspaceRole

    def ensure_workspace(self, workspace_id: UUID) -> None:
        if self.workspace_id != workspace_id:
            raise ApiError(
                code="WORKSPACE_FORBIDDEN",
                message="You do not have access to this workspace.",
                status_code=403,
            )

    def require_role(self, allowed_roles: set[WorkspaceRole]) -> None:
        if self.role not in allowed_roles:
            raise ApiError(
                code="WORKSPACE_ROLE_FORBIDDEN",
                message="Your workspace role cannot perform this action.",
                status_code=403,
            )


class AuthAdapter:
    def authenticate(self, request: Request, workspace_id: UUID) -> WorkspacePrincipal:
        raise NotImplementedError


class LocalHeaderAuthAdapter(AuthAdapter):
    """Local/test adapter. It is explicit header-based test auth, not production auth."""

    def authenticate(self, request: Request, workspace_id: UUID) -> WorkspacePrincipal:
        user_id = request.headers.get("x-user-id")
        workspace_roles = request.headers.get("x-test-workspaces")

        if not user_id:
            raise ApiError(code="UNAUTHENTICATED", message="Authentication is required.", status_code=401)
        if not workspace_roles:
            raise ApiError(code="WORKSPACE_FORBIDDEN", message="Workspace membership is required.", status_code=403)

        role = _role_for_workspace(workspace_roles=workspace_roles, workspace_id=workspace_id)
        if role is None:
            raise ApiError(
                code="WORKSPACE_FORBIDDEN",
                message="You do not have access to this workspace.",
                status_code=403,
            )

        return WorkspacePrincipal(user_id=user_id, workspace_id=workspace_id, role=role)


def _role_for_workspace(workspace_roles: str, workspace_id: UUID) -> WorkspaceRole | None:
    for entry in workspace_roles.split(","):
        if not entry.strip():
            continue
        parts = entry.strip().split(":", 1)
        if len(parts) != 2:
            raise ApiError(
                code="INVALID_WORKSPACE_MEMBERSHIP",
                message="Workspace membership header is malformed.",
                status_code=403,
            )
        entry_workspace_id, role_value = (part.strip() for part in parts)
        if entry_workspace_id != str(workspace_id):
            continue
        try:
            return WorkspaceRole(role_value)
        except ValueError as exc:
            raise ApiError(
                code="INVALID_WORKSPACE_ROLE",
                message="Workspace role is not recognized.",
                status_code=403,
            ) from exc
    return None


class ProductionJwtAuthAdapter(AuthAdapter):
    """Production skeleton. Full JWT verification and membership lookup are Batch 2 follow-up work."""

    def authenticate(self, request: Request, workspace_id: UUID) -> WorkspacePrincipal:
        authorization = request.headers.get("authorization")
        if not authorization:
            raise ApiError(code="UNAUTHENTICATED", message="Authentication is required.", status_code=401)

        raise ApiError(
            code="AUTH_NOT_IMPLEMENTED",
            message="JWT verification skeleton is present but not enabled yet.",
            status_code=503,
        )


def get_auth_adapter() -> AuthAdapter:
    settings = get_settings()
    if not settings.is_known_app_env:
        raise ApiError(
            code="APP_ENV_NOT_CONFIGURED",
            message="APP_ENV must be set to a supported environment before authentication is enabled.",
            status_code=503,
        )
    if settings.is_local_or_test:
        return LocalHeaderAuthAdapter()
    return ProductionJwtAuthAdapter()


def require_workspace_member(request: Request, workspace_id: UUID) -> WorkspacePrincipal:
    return get_auth_adapter().authenticate(request=request, workspace_id=workspace_id)


PRODUCT_PROFILE_READ_ROLES = {
    WorkspaceRole.OWNER,
    WorkspaceRole.ADMIN,
    WorkspaceRole.ANALYST,
    WorkspaceRole.APPROVER,
    WorkspaceRole.VIEWER,
}

PRODUCT_PROFILE_WRITE_ROLES = {
    WorkspaceRole.OWNER,
    WorkspaceRole.ADMIN,
    WorkspaceRole.ANALYST,
}
