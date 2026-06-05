# Background Jobs

## Queue Decision
Use a database-backed job queue for MVP. This keeps operations simple, auditable, and colocated with workspace-scoped state until throughput requires a dedicated queue service.

Batch 1 includes `outbox_events` as migration/schema infrastructure only. Event dispatch, retries for published events, and consumers are later implementation work.

## Worker Responsibilities
| Worker | Jobs |
| --- | --- |
| file-processing-worker | Batch 4 claims `process_upload`, reads storage, parses raw rows/errors, updates upload and job status. |
| campaign-generation-worker | Generate campaign plans, negative keyword rows, bulk sheet exports. |
| monitoring-worker | Normalize performance reports, calculate metrics, create recommendations. |

## Job Fields
job_queue records must include job_type, workspace_id, payload_json, status, idempotency_key, attempts, locked_at, locked_by, heartbeat_at, last_error, created_at, updated_at.

## Job States
queued, running, succeeded, failed, dead_letter, cancelled.

## Job Rules
- Jobs are idempotent by object and version.
- Jobs write audit events for completed decision outputs.
- Failed jobs expose user-safe error messages and internal diagnostic detail separately.
- Every job must have an idempotency key.
- Every meaningful side effect must write an audit log or outbox event.

## Batch 3 Job Skeleton
`process_upload` is created when an initialized upload is confirmed. The payload contains `workspace_id`, `product_id`, `upload_id`, `storage_path`, and `source_type`.

The confirm endpoint uses an upload-scoped job idempotency key, so confirming the same upload twice returns the existing job instead of creating a duplicate. No worker parses the file in Batch 3.

Batch 3.1 confirm rules are intentionally narrow: only `initialized -> queued_for_processing` creates a job. If the upload is already queued and the job exists, the API returns that job. Active or terminal upload states return `409` and never enqueue a new job.

Job enqueue code distinguishes inserted jobs from existing jobs after conflicts. `job.queued` audit logs are written only when the job row is newly created.

## Batch 4 Process Upload Lifecycle
1. Claim one queued `process_upload` job and mark it `running`.
2. Load upload metadata and require `queued_for_processing`.
3. Mark the upload `processing`.
4. Create an `upload_parse_runs` row with `running`.
5. Read the raw object through the storage adapter.
6. Parse rows and row/file errors deterministically.
7. Insert `upload_parsed_rows` and `upload_parse_errors`.
8. On success, mark parse run `succeeded`, upload `processed`, and job `succeeded`.
9. On failure, mark parse run `failed`, upload `failed`, and job `failed` with a safe error message.

Audit events: `upload.processing_started`, `upload.parsed`, and `upload.parse_failed`.

Batch 4 does not implement workers for column mapping, scoring, campaign generation, exports, monitoring, recommendations, or Amazon Ads API work.

## Batch 10 Process Monitoring Import Lifecycle
`process_monitoring_import` is created when a user creates a monitoring import from a processed Sponsored Products Search Term report upload. The payload contains `workspace_id`, `product_id`, `monitoring_import_id`, `upload_id`, and `parse_run_id`.

1. Claim one queued `process_monitoring_import` job and mark it `running`. In local SQLite development, a stale `running` monitoring job whose lock is older than five minutes can also be reclaimed.
2. Load the monitoring import, product, succeeded parse run, and parsed rows.
3. Mark the monitoring import `processing`.
4. Validate required Sponsored Products Search Term report columns.
5. Normalize campaign, ad group, targeting, search term, date range, and metric fields into `monitoring_snapshots`.
6. Run deterministic optimization rules for bid increase, bid decrease, pause review, negative keyword review, and watch lock.
7. Store `recommendations` with rule version, metric evidence, proposed action, priority, and explanation JSON.
8. Store `ai_runs` for stakeholder summaries or recommendation explanations. Agent output is bounded to explanation and cannot change recommendation status.
9. On success, mark the import and job `succeeded`.
10. On failure, mark the import and job `failed` with a user-safe error.

Audit events: `monitoring_import.queued`, `monitoring_import.processed`, `monitoring_import.failed`, `recommendation.approved`, and `recommendation.rejected`.

Batch 10 does not execute live Amazon Ads actions. Approved recommendations mean approved for manual action or a later explicitly approved export workflow.

## Worker Locking
Workers claim jobs using a database transaction that sets `locked_at`, `locked_by`, `status = running`, and increments or records attempt metadata. A worker may only process a job it successfully claimed.

The local SQLite worker claim path treats five-minute-old `running` locks as stale so interrupted local browser/API debugging sessions do not strand uploads or monitoring imports indefinitely. Reclaimed monitoring imports may continue from `queued` or `processing`; the worker still only creates recommendation-only records and never executes live Amazon Ads mutations.

## Retry, Timeout, And Dead Letter
| Policy | Decision |
| --- | --- |
| Max retries | 3 retries. |
| Backoff | Exponential backoff after retryable failures. |
| Timeout | Per job type timeout; long-running jobs must heartbeat. |
| Dead letter | After retry exhaustion, mark `dead_letter` and expose user-safe failure state. |
| Cancellation | Cancelled jobs must stop before side effects when possible. |

## Worker Heartbeat And Stale Recovery
Workers update `heartbeat_at` while running. Jobs running without heartbeat beyond the job timeout are considered stale. Stale jobs become `queued` again when retries remain, or `failed`/`dead_letter` when retry limits are exhausted.

## Acceptance Criteria
- Duplicate jobs with the same idempotency key do not duplicate campaign plans, exports, recommendations, or audit events.
- Job status can be observed through the API without exposing internal stack traces.
- Dead-letter jobs are visible to operators and linked to the affected workspace object.
