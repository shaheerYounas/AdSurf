# System Architecture

## Architecture Summary
| Layer | Responsibility | MVP technology |
| --- | --- | --- |
| Web app | Customer dashboard, uploads, reviews, approvals, reporting | Next.js, TypeScript, Tailwind CSS, shadcn/ui |
| API | Auth context, validation, orchestration, rule execution, contracts | FastAPI, Python |
| Database | Multi-workspace source of truth and audit records | Supabase PostgreSQL |
| Storage | Original uploads and generated exports | Supabase Storage |
| Workers | File processing, campaign generation, monitoring | Python workers |
| AI layer | Structured assistance and explanations | Provider-agnostic abstraction |

## Data Flow
1. Web app uploads files through API-authorized storage flow.
2. API creates database records and worker jobs.
3. Workers parse, score, generate plans, export sheets, or evaluate monitoring data.
4. API exposes reviewable records and approval actions.
5. Every customer-impacting transition writes an audit log.

## Safety Boundary
The MVP has no live Amazon Ads execution service. Bulk sheet export is the execution handoff and requires customer approval.
