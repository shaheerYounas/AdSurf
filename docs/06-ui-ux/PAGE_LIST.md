# Page List

## Route Map
| Route | Page | Primary purpose |
| --- | --- | --- |
| `/dashboard` | Dashboard Home | See products, pending approvals, recent jobs. |
| `/products` | Product Profiles | List and manage products. |
| `/products/new` | New Product | Create product profile. |
| `/products/[productId]` | Product Detail | View product setup and workflow status. |
| `/products/[productId]/uploads` | Uploads | Initialize raw keyword uploads, confirm queued processing, and view parse-only status. |
| `/products/[productId]/uploads/[uploadId]/mapping` | Manual Column Mapping, Scoring, And Review | Generate/load column profile, map required fields manually, approve a mapping snapshot, run deterministic relevance scoring, review scored candidates, create overrides with reasons, and create locked approved keyword set snapshots. |
| `/products/[productId]/keywords` | Keyword Review | Filter, approve, reject, and override keyword candidates. |
| `/products/[productId]/campaign-plan` | Campaign Plan Detail | Inspect Hero, groups, campaigns, negatives, bids, and budgets. |
| `/products/[productId]/exports` | Bulk Exports | Validate, approve, and download bulk sheets. |
| `/products/[productId]/monitoring` | Performance Report To Recommendations | Create monitoring imports from processed Sponsored Products Search Term reports, run local processing, view status, data quality warnings, recommendation counts, and top agent explanations. |
| `/recommendations` | Agent Recommendations | Filter rule-backed recommendations, review evidence, and approve or reject with required notes. |
| `/approvals` | Approvals | Review pending and historical approval decisions. |
| `/settings/team` | Team Settings | Manage workspace members and roles. |
| `/settings/billing` | Billing Settings | Later scope placeholder for billing and plan management. |

## Implemented App Page Inventory
The current Next.js app contains 12 `page.tsx` files: 11 user-facing pages plus `/`, which redirects to `/dashboard`.

| Implemented route | Previous-page fallback |
| --- | --- |
| `/` | Redirects to `/dashboard`. |
| `/dashboard` | Workspace home. |
| `/agents` | `/dashboard`. |
| `/agent-builder` | `/agents`. |
| `/products` | `/dashboard`. |
| `/products/new` | `/products`. |
| `/products/[productId]` | `/products`. |
| `/products/[productId]/uploads` | `/products/[productId]`. |
| `/products/[productId]/uploads/[uploadId]/mapping` | `/products/[productId]/uploads`. |
| `/products/[productId]/monitoring` | `/products/[productId]`. |
| `/products/[productId]/monitoring/[importId]/agents` | `/products/[productId]/monitoring`. |
| `/recommendations` | `/dashboard`. |

## Global Previous-Page Control
Every implemented page receives the shared previous-page control from the root app layout. The control first returns users to their last internal app page stored in session history, then falls back to the deterministic route map above for direct deep links or refreshed pages.

## Role Permissions
| Role | UI access |
| --- | --- |
| owner | Full workspace access, team settings, approvals, exports, audit. |
| admin | Product, upload, keyword, campaign, export, recommendation, and audit workflows. |
| analyst | Product analysis, uploads, keyword review preparation, campaign plan generation. |
| approver | Approval queue, recommendation decisions, export approval, read access to supporting evidence. |
| viewer | Read-only dashboard, products, plans, monitoring, recommendations, and audit where permitted. |

| Page | Primary users | Main actions |
| --- | --- | --- |
| Dashboard Home | All roles | See products, pending approvals, recent jobs. |
| Product Profiles | owner/admin/analyst | Create and edit product settings. |
| Uploads | owner/admin/analyst | Initialize upload metadata, receive a signed upload target, and confirm processing queue handoff. |
| Manual Column Mapping, Scoring, And Review | owner/admin/analyst | Generate profiles, save manual mappings, approve valid mapping snapshots, run deterministic scoring, create keyword overrides, and create approved keyword set snapshots; all roles with upload read access can inspect results. |
| Keyword Review | owner/admin/analyst/approver | Approve, reject, filter, and override keyword candidates where permitted. |
| Campaign Plan Detail | owner/admin/analyst/approver | Inspect Hero, groups, campaigns, negatives. |
| Bulk Export Detail | admin | Validate, approve, and download export. |
| Monitoring | owner/admin/analyst/approver/viewer | View monitoring imports, recommendation counts, and stakeholder summaries; owner/admin/analyst can create imports. |
| Recommendation Queue | owner/admin/analyst/approver | Approve or reject recommendations with notes; viewer can read only. |
| Audit Log | owner/admin/approver/viewer | Trace decisions and approvals. |
| Settings | owner | Manage workspace, users, and defaults. |

## Acceptance Criteria
Every state-changing page includes clear loading, empty, error, and permission-denied states.
