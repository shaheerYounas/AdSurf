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
| Dual-path decisions | Every decision-making service MUST support BOTH deterministic rules AND AI-powered reasoning, following the `DualPathDecisionService[T]` base class. Deterministic path is always available as fallback. |
| Auditability | Store inputs, outputs, rule versions, AI prompt metadata, approvals, actor identity, and `decision_source` for every customer-impacting decision. |
| Workspace isolation | Every workspace-owned record must be workspace-scoped in API, database, storage, and logs. |
| MVP restraint | Prefer bulk sheet export and approval workflows before Amazon Ads API automation. |

## Dual-Path Decision Architecture
All decision services inherit from `dual_path_decision.DualPathDecisionService[T]`:
- **Deterministic path**: Pure rule-based calculation (always available, no external dependencies)
- **AI path**: LLM-powered reasoning (configurable, with deterministic fallback)
- **Mode selection**: `deterministic` | `ai` | `hybrid` per workspace per product
- **Safety invariants**: AI may recommend/explain/map but never silently act; human approval always required; no live Amazon Ads API mutation; deterministic fallback on AI failure; every AI prompt includes safety guardrails; every output includes `requires_human_approval: true` and `executes_live_amazon_change: false`

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

## Project: Amazon Ads Optimization Software

### Goal
Build a professional Amazon Ads analysis and campaign planning system.

The software must process uploaded Sponsored Products Search Term Reports, validate the file, normalize metrics, detect risky data, generate campaign recommendations, create campaign build plans, preview negative keywords, and support human approval before any money-spending action.

### Core Safety Rule
Never make or suggest a money-spending Amazon Ads action without:
- validation
- explanation
- risk label
- human approval state
- audit log

### Required Workflow
The product flow must be:

Upload Report
-> Validate File
-> Normalize Data
-> Analyze Search Terms
-> Generate Recommendations
-> Review Campaign Builder
-> Review Negative Keywords
-> Confirm Budget Risk
-> Export or Apply Approved Changes
-> Monitor Performance

Do not build a single "Optimize" button that hides the logic.

### Backend Principles
Use modular services:
- FileUploadService
- ReportParserService
- ColumnMappingService
- ValidationService
- MetricCalculatorService
- SearchTermClassifierService
- RulesEngine
- RecommendationService
- CampaignPlanService
- NegativeKeywordService
- MonitoringService
- AuditLogService

### Metric Rules
Recalculate these metrics:
- CTR = clicks / impressions
- CPC = spend / clicks
- CVR = orders / clicks
- ACOS = spend / sales
- ROAS = sales / spend

Handle divide-by-zero safely.
If spend > 0 and sales = 0, do not set ACOS to 0. Mark it as "Spend with No Sales".

### Search Term Classification
Classify terms into:
- keyword
- ASIN/product target
- branded term
- competitor term
- generic category term
- irrelevant term
- low-data term
- duplicate term

ASINs must not be treated like normal keyword campaigns.

### Recommendation Rules
Every recommendation must include:
- action type
- search term or target
- product/campaign context
- reason list
- risk level
- confidence level
- blocked reason if unsafe
- requires approval boolean

### UI Principles
The UI must be step-by-step, spacious, and review-focused.
Each recommendation needs a "Why?" drawer.
Show warnings before campaign creation.
Show total possible daily budget before launch.

### Testing Requirements
Every backend rule must have unit tests.
File upload and metric calculation must have edge-case tests.
Include tests for:
- missing columns
- hidden spaces in columns
- blank ACOS
- zero sales
- zero clicks
- ASIN search terms
- duplicate rows
- wrong currency
- wrong marketplace
- low-data terms

### Definition of Done
A task is not complete until:
- code is implemented
- tests are added or updated
- lint/build passes
- risky assumptions are documented
- UI states for loading/error/empty/success are handled
