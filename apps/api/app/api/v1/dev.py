from fastapi import APIRouter

from apps.api.app.core.config import get_settings
from apps.api.app.core.errors import ApiError
from apps.api.app.domain.uploads import PROCESS_UPLOAD_JOB_TYPE
from apps.api.app.domain.monitoring import PROCESS_MONITORING_IMPORT_JOB_TYPE
from apps.api.app.schemas.envelope import success_response
from apps.api.app.services.monitoring_worker import MonitoringWorker
from apps.api.app.services.upload_processing_worker import UploadProcessingWorker

router = APIRouter()


@router.post("/dev/process-upload-jobs")
def process_upload_jobs() -> dict:
    settings = get_settings()
    if not settings.is_local_or_test:
        raise ApiError(code="DEV_ENDPOINT_DISABLED", message="Dev worker endpoints are only available in local/test.", status_code=404)

    processed = 0
    parse_runs = []
    worker = UploadProcessingWorker()
    while True:
        result = worker.process_one()
        if not result.processed:
            break
        processed += 1
        if result.parse_run is not None:
            parse_runs.append(result.parse_run.model_dump(mode="json"))

    return success_response(data={"job_type": PROCESS_UPLOAD_JOB_TYPE, "processed": processed, "parse_runs": parse_runs})


@router.post("/dev/process-monitoring-jobs")
def process_monitoring_jobs() -> dict:
    settings = get_settings()
    if not settings.is_local_or_test:
        raise ApiError(code="DEV_ENDPOINT_DISABLED", message="Dev worker endpoints are only available in local/test.", status_code=404)

    processed = 0
    imports = []
    worker = MonitoringWorker()
    while True:
        result = worker.process_one()
        if not result.processed:
            break
        processed += 1
        if result.import_record is not None:
            imports.append(result.import_record.model_dump(mode="json"))

    return success_response(data={"job_type": PROCESS_MONITORING_IMPORT_JOB_TYPE, "processed": processed, "imports": imports})
