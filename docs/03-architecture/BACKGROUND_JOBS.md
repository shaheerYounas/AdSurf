# Background Jobs

## Worker Responsibilities
| Worker | Jobs |
| --- | --- |
| file-processing-worker | Parse uploads, clean rows, suggest mappings, create keyword candidates. |
| campaign-generation-worker | Generate campaign plans, negative keyword rows, bulk sheet exports. |
| monitoring-worker | Normalize performance reports, calculate metrics, create recommendations. |

## Job Fields
worker_jobs must include job_type, tenant_id, payload_json, status, attempts, last_error, created_at, updated_at.

## Job Rules
- Jobs are idempotent by object and version.
- Jobs write audit events for completed decision outputs.
- Failed jobs expose user-safe error messages and internal diagnostic detail separately.

