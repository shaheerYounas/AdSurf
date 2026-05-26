# Deployment Plan

## Environments
| Environment | Purpose |
| --- | --- |
| local | Developer machine with local or development Supabase resources. |
| preview | Per-branch or per-PR validation environment. |
| staging | Production-like validation with non-production data. |
| production | Customer-facing environment. |

Promotion path: local -> preview -> staging -> production.

## MVP Deployment Shape
| Component | Deployment target |
| --- | --- |
| Web app | Managed Next.js hosting. |
| API | Containerized FastAPI service. |
| Workers | Containerized Python worker processes. |
| Database | Supabase PostgreSQL. |
| Storage | Supabase Storage private buckets. |
| Observability | Sentry and OpenTelemetry-compatible logs/traces. |

## Database Migrations
| Requirement | Decision |
| --- | --- |
| Migration format | Migration files only; no manual production schema edits. |
| Review | Migrations must be reviewed before production. |
| Rollback | Destructive migrations require a rollback plan and data backup confirmation. |
| Validation | Migration/constraint tests run before staging and production promotion. |

## Backups And Restore
| Requirement | Decision |
| --- | --- |
| Production database backups | Daily backups required. |
| Restore drills | Restore drill required on a regular cadence before relying on production. |
| Export retention | Generated exports retained at least 12 months. |

## Secrets
- No secrets in the repository.
- Use the deployment platform secret manager for Supabase, AI provider, observability, and future Amazon Ads credentials.
- Rotate exposed or suspected secrets immediately.

## Storage
- Supabase Storage buckets must be private.
- Signed URLs must expire.
- Upload and export paths must follow the workspace/product path convention from `DATABASE_SCHEMA.md`.

## Workers
- Workers are separately deployable from the API and web app.
- Worker scaling is based on queue depth, job age, and job failure rate.
- Dead-letter jobs must be visible to operators.

## Monitoring
| Signal | Alert intent |
| --- | --- |
| API error rate | Detect backend regressions. |
| Job failure rate | Detect processing issues. |
| Dead-letter count | Detect unrecoverable worker failures. |
| Upload processing latency | Detect slow or stuck file processing. |
| Export generation failures | Detect bulk sheet generation regressions. |

## Incident Response
| Requirement | Decision |
| --- | --- |
| Severity levels | Define Sev1 customer-impacting outage/data risk, Sev2 degraded workflow, Sev3 minor issue. |
| Rollback steps | Each release must identify rollback path for web, API, workers, and migrations. |
| Workspace notification | Customer or workspace owner notification is required for material data, export, approval, or availability incidents. |
| Audit preservation | Incident response must preserve audit logs and relevant job records. |

## Deployment Gates
- Tests pass.
- Environment variables validated.
- Database migrations reviewed.
- RLS policies verified.
- Approval and audit flows smoke-tested.
- Monitoring alerts configured for production.
- Backup and rollback requirements satisfied.
