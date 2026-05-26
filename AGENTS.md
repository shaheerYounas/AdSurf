# AGENTS.md

## Mission
Build the Amazon Ads AI Automation Control Center as a production-minded, MVP-friendly SaaS for Amazon sellers and agencies. The product helps customers move from competitor keyword research files to reviewed keyword lists, campaign plans, bulk sheet exports, monitoring insights, and approval-controlled recommendations.

## Prime Directive
AI agents do not directly execute dangerous changes. Rules calculate. AI explains. Humans approve. The system logs every decision.

## Required Working Rules
| Rule | Requirement |
| --- | --- |
| Documentation parity | Any future code change that changes behavior, data contracts, workflows, security, or business rules must update the relevant docs in the same change. |
| Human approval | Never implement live ad execution, bid changes, pauses, negative keyword additions, campaign locks, or exports without an explicit approval record. |
| Deterministic decisions | Business decisions must be produced by deterministic rules, not by unconstrained AI text. |
| Auditability | Store inputs, outputs, rule versions, AI prompt metadata, approvals, and actor identity for every customer-impacting decision. |
| Workspace isolation | Every workspace-owned record must be workspace-scoped in API, database, storage, and logs. |
| MVP restraint | Prefer bulk sheet export and approval workflows before Amazon Ads API automation. |

## Repository Ownership Map
| Area | Responsibility |
| --- | --- |
| `apps/web` | Next.js customer dashboard, approval queue, upload UI, campaign plan review, reporting views. |
| `apps/api` | FastAPI REST API, auth enforcement, rule orchestration, data access, worker job creation. |
| `workers/file-processing-worker` | CSV/XLSX parsing, cleaning, normalization, column mapping support, file validation. |
| `workers/campaign-generation-worker` | Approved keyword grouping, campaign plan generation, negative keyword structure, bulk sheet rows. |
| `workers/monitoring-worker` | Monitoring ingestion, 14-day rule evaluation, recommendation generation. |
| `packages/types` | Shared TypeScript/Python contract references and generated API types when introduced. |
| `packages/shared` | Shared deterministic rule descriptions and test fixtures when introduced. |
| `packages/config` | Shared lint, formatting, app config, and environment schema when introduced. |
| `docs` | Product, domain, architecture, AI, workflow, UI, engineering, planning, and ADR source of truth. |

## Development Standards
- Read the relevant docs before changing behavior.
- Add tests for every business rule touched.
- Keep AI outputs explainable and bounded by structured schemas.
- Prefer small, reviewable changes with clear acceptance criteria.
- Do not store secrets, customer uploads, generated bulk sheets, or local reports in Git.

## Required Safety Checks Before Implementation
| Check | Pass condition |
| --- | --- |
| Approval boundary | The change cannot perform customer-impacting actions without an approval record. |
| Rule ownership | Metrics and decisions are calculated by code rules, not free-form AI text. |
| Workspace boundary | All reads and writes are scoped by workspace and user role. |
| Docs updated | Related PRD, domain, API, database, workflow, and testing docs are current. |
| Tests planned | Unit, integration, or E2E coverage is defined for changed behavior. |

## Non-Negotiable MVP Constraints
- First execution mode is Amazon bulk sheet export.
- Amazon Ads API execution is later-version work only.
- Product must be usable by non-technical sellers and agency operators.
- AI may recommend, summarize, map, and explain; AI may not silently act.
- Canonical roles are `owner`, `admin`, `analyst`, `approver`, and `viewer`.
