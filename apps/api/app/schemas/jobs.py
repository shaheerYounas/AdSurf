from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobRecord(BaseModel):
    id: UUID
    workspace_id: UUID
    job_type: str
    status: JobStatus
    payload_json: dict
    idempotency_key: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
