"""REST endpoint for the upload-only file upload module.

POST /v1/workspaces/{workspace_id}/file-uploads
  Accepts multipart/form-data with a single ``file`` field.
  Returns upload_id, filename, row_count (if readable), and initial status.
  Does NOT trigger any analysis workflow.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from apps.api.app.core.auth import (
    PRODUCT_PROFILE_WRITE_ROLES,
    WorkspacePrincipal,
    require_workspace_member,
)
from apps.api.app.core.errors import ApiError
from apps.api.app.repositories.audit_logs import AuditLogRepository, get_audit_log_repository
from apps.api.app.repositories.uploads import UploadRepository, get_upload_repository
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.file_upload import FileUploadService
from apps.api.app.services.storage import StorageService, get_storage_service

router = APIRouter()


@router.post(
    "/workspaces/{workspace_id}/file-uploads",
    status_code=status.HTTP_201_CREATED,
)
async def upload_report_file(
    workspace_id: UUID,
    request: Request,
    principal: WorkspacePrincipal = Depends(require_workspace_member),
    upload_repository: UploadRepository = Depends(get_upload_repository),
    storage_service: StorageService = Depends(get_storage_service),
    audit_repository: AuditLogRepository = Depends(get_audit_log_repository),
) -> dict:
    """Upload an Amazon Ads report file (.xlsx or .csv) without analysis.

    Validates file type, file size, empty file, and unreadable Excel.
    Returns upload_id, filename, row_count (if readable), and initial status.
    """
    principal.ensure_workspace(workspace_id)
    principal.require_role(PRODUCT_PROFILE_WRITE_ROLES)

    # Read multipart form data
    try:
        form = await request.form()
    except Exception as exc:
        raise ApiError(
            code="MULTIPART_UPLOAD_REQUIRED",
            message="File upload requires multipart/form-data with a file field.",
            status_code=400,
        ) from exc

    file_part = form.get("file")
    if file_part is None or not hasattr(file_part, "read"):
        raise ApiError(
            code="REPORT_FILE_REQUIRED",
            message="File upload requires a file field.",
            status_code=400,
        )

    content = await file_part.read()  # type: ignore[union-attr]
    filename = getattr(file_part, "filename", "") or "report.csv"
    mime_type = getattr(file_part, "content_type", None) or "text/csv"

    # Delegate to the upload-only service
    service = FileUploadService(
        upload_repository=upload_repository,
        storage_service=storage_service,
    )
    result = service.upload(
        content=content,
        original_filename=filename,
        mime_type=mime_type,
        workspace_id=workspace_id,
        product_id=None,
        actor_user_id=principal.user_id,
    )

    audit_repository.record(
        workspace_id=workspace_id,
        actor_user_id=principal.user_id,
        action="upload.file_received",
        entity_type="upload",
        entity_id=result.upload_id,
        details={
            "filename": result.filename,
            "file_size_bytes": result.file_size_bytes,
            "row_count": result.row_count,
            "status": result.status.value,
        },
    )

    return success_response(
        data={
            "upload_id": str(result.upload_id),
            "filename": result.filename,
            "row_count": result.row_count,
            "status": result.status.value,
        }
    )