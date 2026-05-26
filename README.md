# Amazon Ads AI Automation Control Center

Documentation-first foundation for a SaaS product that helps Amazon sellers and agencies automate Amazon Ads research, campaign planning, bulk sheet export, monitoring, and approval-controlled optimization.

## Product Principle
AI agents do not directly execute dangerous changes. Rules calculate. AI explains. Humans approve. The system logs every decision.

## MVP Workflow
| Step | Outcome |
| --- | --- |
| Product profile | Customer defines ASIN, marketplace, default budget, default bid, and campaign preferences. |
| Research upload | Customer uploads competitor keyword CSV/XLSX. |
| Cleaning and mapping | System normalizes rows, maps columns, and flags unusable data. |
| Relevance scoring | Rule engine calculates competitor-based relevance score. |
| Keyword approval | Customer reviews approved and rejected terms. |
| Campaign planning | System creates Hero, Exact, Phrase, Broad, and negative keyword structure. |
| Bulk export | Customer approves and downloads Amazon bulk sheet. |
| Monitoring | System tracks performance for 14 days from uploaded reports or later API data. |
| Recommendations | System recommends bid increases, pauses, negatives, and locks through approval queue. |

## Recommended Stack
| Layer | MVP choice |
| --- | --- |
| Frontend | Next.js, TypeScript, Tailwind CSS, shadcn/ui, Recharts |
| Backend | FastAPI, Python |
| Database | Supabase PostgreSQL |
| Storage | Supabase Storage |
| Processing | Pandas, openpyxl |
| Workers | Python background workers |
| Auth | Supabase Auth |
| AI | Provider-agnostic abstraction |
| First execution | Amazon bulk sheet export |
| Later execution | Amazon Ads API |
| Testing | pytest, Vitest, Playwright |

## Documentation Map
Start with [docs/00-index.md](docs/00-index.md). For operator instructions, use the [User Guide](docs/06-ui-ux/USER_GUIDE.md). Core rules live in `docs/02-domain`; architecture contracts live in `docs/03-architecture`; agent guardrails live in `docs/04-ai-agents`.

## Current State
The repository now contains an implementation foundation for the documented MVP workflow:

- Next.js product, upload, mapping, keyword review, campaign plan, and bulk export screens.
- FastAPI product, upload, parse, column mapping, scoring, keyword review, campaign plan, and bulk export APIs.
- Supabase migrations through campaign/export tables with workspace-scoped RLS policies.
- Local/test header auth and fake storage for development, with staging/production auth and Supabase storage still failing closed until fully configured.

## Contribution Rule
Future code changes must update documentation when behavior changes. Business rules, API contracts, database schema, approval flows, and AI guardrails are part of the product contract.
