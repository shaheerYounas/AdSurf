# Deployment Plan

## MVP Deployment Shape
| Component | Deployment target |
| --- | --- |
| Web app | Managed Next.js hosting. |
| API | Containerized FastAPI service. |
| Workers | Containerized Python worker processes. |
| Database | Supabase PostgreSQL. |
| Storage | Supabase Storage private buckets. |
| Observability | Sentry and OpenTelemetry-compatible logs/traces. |

## Deployment Gates
- Tests pass.
- Environment variables validated.
- Database migrations reviewed.
- RLS policies verified.
- Approval and audit flows smoke-tested.

