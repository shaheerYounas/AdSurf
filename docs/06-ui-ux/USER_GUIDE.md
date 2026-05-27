# User Guide

## Purpose
This guide explains how sellers, agency operators, analysts, and approvers use the Amazon Ads AI Automation Control Center from product setup through upload parsing, keyword review, campaign planning, and bulk sheet export.

The app is designed around one operating rule: recommendations and exports require human review. The system can calculate, organize, explain, and prepare files, but it does not make live Amazon Ads changes by itself.

## Who Uses The App
| Role | Typical work |
| --- | --- |
| owner | Owns workspace setup, team access, approvals, and audit review. |
| admin | Runs product, upload, campaign, approval, and export workflows. |
| analyst | Prepares products, uploads reports, maps columns, scores keywords, and drafts campaign plans. |
| approver | Reviews evidence, approves keyword sets, campaign plans, recommendations, and exports. |
| viewer | Reads dashboards, products, uploads, plans, monitoring, and audit history where permitted. |

## Main Navigation
| Page | Use it for |
| --- | --- |
| Dashboard | See workspace product counts, upload processing status, product continuation links, and the launch checklist. |
| Agents | Inspect and control monitoring agents, workflow graphs, run outputs, and configuration. |
| Products | Create and open product profiles. |
| Product Detail | Review a product's marketplace, bids, budgets, upload status, and next-step workflow links. |
| Uploads | Add CSV/XLSX research files and monitor parsing status. |
| Mapping | Generate column profiles, map source columns, score keywords, review candidates, and create approved keyword sets. |
| Campaign Plan | Generate and inspect campaign structures from approved keyword sets. |
| Bulk Exports | Validate, approve, and download Amazon bulk sheet files. |
| Recommendations | Review DeepSeek AI or deterministic fallback optimization suggestions with deterministic metric evidence. |
| Approvals | Review pending and historical approval records. |
| Settings | Manage workspace, team, and account configuration. |

## Before You Start
Prepare these inputs:

- Product name.
- Marketplace, such as `US`.
- Currency, such as `USD`.
- Default daily budget.
- Default keyword bid.
- Target ACOS.
- Competitor keyword research file, search term report, or other supported CSV/XLSX source.

Recommended upload files should include columns for search term or keyword, spend, clicks, orders, sales, impressions, and campaign context when available. The app can still parse files with extra columns, but scoring and campaign generation require the key keyword and performance fields to be mapped.

## Workflow Overview
| Step | Result |
| --- | --- |
| Create product | Product defaults are saved for later scoring, bidding, and campaign generation. |
| Upload research file | Raw file metadata is stored and the file is queued for parsing. |
| Parse upload | Rows are normalized, stored, and checked for errors. |
| Generate column profile | The app summarizes source columns, sample values, and inferred data types. |
| Map columns | A user connects source columns to canonical app fields. |
| Approve mapping | The mapping snapshot becomes the reviewed input for scoring. |
| Score keywords | Deterministic rules assign relevance and review status. |
| Review keyword candidates | Users approve, reject, or override candidates with reasons. |
| Create approved keyword set | Approved terms are frozen as a versioned input. |
| Generate campaign plan | Rules create Hero, Exact, Phrase, Broad, and negative structures. |
| Approve plan | A human confirms the plan before export. |
| Generate bulk export | The app creates an Amazon bulk sheet for download. |
| Import performance report | A processed Sponsored Products Search Term report becomes monitoring evidence. |
| Generate recommendations | DeepSeek AI creates keep-running, bid, pause-review, negative-keyword, move-to-exact, watch-lock, budget-review, and data-quality recommendations when configured. Deterministic rules remain available as fallback. |
| Decide recommendations | A human approves or rejects each recommendation with a note. |

## Dashboard Loading
The dashboard uses a single workspace summary request for product counts, upload status, and pending recommendations. While the request is in flight, skeleton cards and loading icons show that the app is working. If the dashboard feels slow, check API health, Supabase latency, and whether database migrations with dashboard performance indexes have been applied.

## Create A Product
1. Open `Products`.
2. Select the action to create a new product.
3. Enter the product name.
4. Set marketplace and currency.
5. Enter target ACOS, default budget, and default bid.
6. Save the product.

The product should appear in the product list immediately. If it does not, check that the backend is running, the workspace is selected, and the current user has product access.

## Upload A Research File
1. Open a product.
2. Go to `Uploads`.
3. Choose a CSV or XLSX file.
4. Confirm the upload.
5. Wait for the status to change from queued or processing to processed.

Common statuses:

| Status | Meaning |
| --- | --- |
| initialized | Upload metadata exists, but the file is not confirmed yet. |
| queued_for_processing | The file is ready for the parser. |
| processing | The parser is reading and normalizing rows. |
| processed | Parsing succeeded and rows are available for mapping. |
| failed | Parsing failed and needs review. |

For the current local demo data, the two sponsored-products search term report files are imported under the product `Sponsored Products Search Term Reports Demo`.

## Review Parse Results
After processing:

1. Open the upload.
2. Review parse run status.
3. Confirm row counts and error counts.
4. If there are errors, inspect the error rows before mapping.

A successful parse run should show:

- File type.
- Selected sheet name for XLSX files.
- Total rows.
- Total columns.
- Parsed row count.
- Error row count.

Parsing only validates that rows can be read and normalized. It does not mean the app knows which source column represents each business field yet.

## Generate And Review Column Profile
1. Open the upload's mapping page.
2. Generate or load the column profile.
3. Review each source column.
4. Use sample values and inferred data types to understand the file.

The profile helps identify columns such as:

- Customer Search Term.
- Spend.
- Clicks.
- Impressions.
- Orders.
- Sales.
- ACOS.
- ROAS.
- Campaign Name.
- Ad Group Name.

If a profile takes longer for a large file, wait for the request to finish and reload the page. Profiles are stored after generation.

## Map Columns
On the mapping page:

1. Select the source column for each required canonical field.
2. Map optional fields when they exist.
3. Save the mapping draft.
4. Fix any validation errors.
5. Approve the mapping snapshot.

The app requires a reviewed mapping before deterministic keyword scoring can run. This keeps the scoring step auditable and prevents ambiguous columns from silently affecting keyword decisions.

## Score Keywords
After mapping approval:

1. Run keyword scoring.
2. Review the generated candidates.
3. Check each candidate's score, reason, and status.

Scoring is deterministic. The AI may summarize or explain, but the business decision comes from rules. Scores `0`, `1`, and `2` are rejected by default according to the domain workflow.

## Review Keyword Candidates
Use the keyword review tools to:

- Filter candidates by status.
- Approve high-relevance terms.
- Reject weak or irrelevant terms.
- Add overrides with a reason.
- Create an approved keyword set snapshot.

Every manual override should include a clear reason. This protects the audit trail and helps approvers understand why a rule outcome changed.

## Create A Campaign Plan
After an approved keyword set exists:

1. Generate a campaign plan.
2. Review the Hero keyword.
3. Review Exact, Phrase, and Broad groups.
4. Review negative keyword structure.
5. Confirm bids and budgets.
6. Submit the plan for approval.

Campaign generation follows deterministic rules:

- One Hero keyword is selected.
- Remaining approved terms are grouped.
- Rejected terms are excluded.
- Negative Exact and Negative Phrase rows are created where rules require them.

## Approve A Campaign Plan
Approvers should inspect:

- Source product.
- Approved keyword set version.
- Hero keyword.
- Grouped terms.
- Negative terms.
- Default bid and budget.
- Rule version or generation metadata.

Approval means the plan can be used for export. It does not mean live Amazon Ads changes are executed.

## Generate And Download Bulk Export
1. Open the approved campaign plan or export page.
2. Validate export readiness.
3. Review generated row counts and any validation issues.
4. Add an approval note.
5. Approve the export.
6. Download the Amazon bulk sheet file.

The MVP execution mode is bulk sheet export. Users still upload the generated file to Amazon Ads themselves or through a later approved integration. The app must not silently launch campaigns, change bids, pause campaigns, or add negatives without a separate explicit approval record.

## Monitoring And Recommendations
Monitoring is designed for post-launch review. The current implementation supports Amazon Sponsored Products Search Term report XLSX/CSV files exported from Amazon Ads. The user uploads the report through the normal upload flow, waits for parsing to complete, then opens the product monitoring page to create a monitoring import.

Recommendations may include:

- Keep running.
- Increase bid.
- Decrease bid.
- Pause review.
- Add negative exact.
- Add negative phrase.
- Move to exact.
- Watch lock.
- Data quality review.
- Budget review.

Recommendations require approval before any customer-impacting action or export is produced.

## Import A Sponsored Products Search Term Report
1. Export a Sponsored Products Search Term report from Amazon Ads.
2. Open the product that owns the running ads.
3. Upload the file with source type `amazon_ads_sp_search_term_report`.
4. Confirm the upload and wait until parsing is processed.
5. Open `Performance report to recommendations`.
6. Select or enter the processed upload ID.
7. Create the monitoring import.
8. Run the local monitoring worker in development or wait for the monitoring worker in deployed environments.

The app validates required columns such as Campaign Name, Ad Group Name, Targeting, Customer Search Term, Impressions, Clicks, Spend, Sales, and Orders. Missing required columns stop recommendation generation. Optional metrics such as ACOS, ROAS, Units, CTR, CPC, CVR, Start Date, and End Date are normalized when present, and missing derived metrics are calculated from base metrics when possible.

## Agent Control Center
Open `Agents` to upload an Amazon Ads report, inspect the agent team, run analysis, review trace events, and send recommendations through human approval checkpoints. You can also open a monitoring import and choose `Open Agent Control Center` for import-specific workflow details.

When `Agents` is opened, the main AdSurf sidebar changes into an Agent Ops sub-menu. Use `Main menu` at the top of that sidebar to return to Dashboard, Products, New product, and the rest of the global navigation.

The Agent Control Center shows:

- An upload-first entry point for account-level reports and bulk sheets.
- A normal Upload Amazon Ads Report card at the top of the workflow with file picker, upload button, Simple/Advanced Mode toggle, and safety labels.
- Simple Mode for everyday users and Advanced Mode for operators who need raw input/output, template, and deep configuration context.
- Agent Team Dashboard cards with status, current task, mode, provider/model, strictness, confidence threshold, tools/data access, memory/context limits, permissions, cost/time, recommendation count, last run, and error state.
- A Visual Workflow Canvas showing Report Upload, Report Detection, Product Resolution, Metrics Analysis, AI Recommendation Brain, Bid Optimization, Negative Keyword, Budget Allocation, Pause Review, Stakeholder Reporting, and Human Approval.
- A right Agent Inspector on wide desktop screens, or a full-width inspector below the workflow on narrower screens. Inspector tabs wrap cleanly and include Overview, Configuration, Prompt / Business Goal, Input Data, Output, Recommendations, Permissions, Trace, and Safety.
- A Trace Timeline with events such as queued, started, input prepared, model called, output received, validation passed or failed, recommendations created, waiting for human approval, fallback used, stopped, paused, or failed.
- Human Approval Checkpoints with recommendation cards, metric evidence, risk chips, proposed actions, and approve/reject/edit controls.
- Agent Templates that prefill configuration for conservative profitability, growth scaling, wasted spend cleanup, launch review, or agency audit work.
- Control buttons for run analysis, pause all, resume all, stop all, rerun failed, configure agents, view approvals, and rerun from a selected agent.

Owner/admin users can change agent configuration. Analysts can run, rerun, pause, resume, and stop agents. Approvers and viewers can inspect outputs. These controls never grant agents permission to approve, reject, or execute Amazon Ads changes.

Every recommendation card and approval checkpoint repeats the safety boundary: `Recommendation only`, `Requires human approval`, and `No live Amazon Ads change executed`.

## Review AI Recommendations
Open `Recommendations` to review the queue. Each row shows:

- Priority.
- Decision source, such as DeepSeek AI or deterministic fallback.
- DeepSeek model when an AI recommendation was saved.
- Recommendation type.
- Campaign and ad group.
- Targeting or customer search term.
- Metric evidence such as spend, clicks, sales, orders, ACOS, ROAS, CTR, and CVR.
- Proposed action.
- Confidence and reasoning summary.
- Requires human approval.
- No live Amazon Ads change executed.
- Current status.

Use filters to focus by source, status, priority, or recommendation type. Approve or reject only after checking the evidence. Evidence includes normalized row metrics plus search-term, target, ad-group, campaign, and report rollups in `evidence_json`. AI recommendations also show `ai_provider`, `ai_model`, `ai_run_id`, and AI evidence. A note is required, and the decision updates the app audit trail only. It does not execute a bid change, pause an ad, add a negative keyword, generate an export, or call the Amazon Ads API.

## Agent Council Boundary
The agent council is the recommendation and explanation layer for monitoring:

- Monitoring Recommendation Brain uses DeepSeek to generate recommendation decisions from uploaded report evidence.
- Performance Import Agent explains report shape and data quality.
- Metrics Analysis Agent summarizes spend, traffic, sales, ACOS, ROAS, CTR, and CVR.
- Bid Optimization Agent explains bid increase/decrease and watch-lock recommendations.
- Negative Keyword Agent explains wasted-spend search terms.
- Pause Review Agent explains stop/pause-review candidates.
- Stakeholder Reporting Agent writes dashboard-friendly summaries.

DeepSeek AI may create recommendation records only after backend validation passes. Deterministic rules calculate metrics and remain available as fallback. AI may not approve, reject, execute, mutate live Amazon Ads accounts, or replace human review. Humans approve or reject recommendations.

## Approval Rules
Approval records should clearly answer:

- What object is being approved.
- Who approved it.
- When it was approved.
- Which source data and rule version produced it.
- What impact the approval has.
- Whether the result is export-only or would affect live execution in future versions.

If approval evidence is missing, do not proceed to export.

## Audit Trail
The system records customer-impacting decisions and workflow milestones. Operators should use audit history to answer:

- Which file produced this keyword?
- Which mapping was approved?
- Which scoring rules were used?
- Who overrode a keyword decision?
- Which approved keyword set fed the campaign plan?
- Who approved the campaign plan or export?

## Local Demo Guide
For local development, the app can be opened at:

- Web app: `http://127.0.0.1:3000/products`
- API health: `http://127.0.0.1:8000/health`

The local demo workspace uses a fixed workspace and user ID configured in development files. Local upload bytes may use fake storage while Supabase PostgreSQL stores metadata, parsed rows, mappings, approvals, and campaign/export records.

To use real Supabase Storage instead of fake local storage, configure a valid Supabase service-role key and uploads bucket. Keep service-role keys out of Git.

## Troubleshooting
| Symptom | What to check |
| --- | --- |
| Product list is empty | Confirm the API is running, `DATABASE_URL` is valid, migrations are applied, and the user has workspace membership. |
| Upload stays queued | Run the file-processing worker or local dev processing endpoint. |
| Upload fails | Check file type, file size, parser errors, and whether the original file bytes were written to storage. |
| Column profile is slow | Large remote database reads can take time. Wait, then reload and check whether the profile was saved. |
| Scoring is unavailable | Confirm the upload is processed and a valid mapping snapshot is approved. |
| Monitoring import cannot start | Confirm the report upload is processed and belongs to the selected product. |
| Recommendations are empty | Confirm the monitoring worker ran and the report upload source type is `amazon_ads_sp_search_term_report`. Phase 1 should create one pending recommendation per normalized report row. |
| Approval is blocked | Confirm your role is owner, admin, analyst, or approver and your note is not blank. |
| Campaign plan cannot export | Confirm the keyword set and campaign plan are approved. |
| Export download is blocked | Confirm export validation passed and an explicit export approval exists. |
| Supabase Storage fails locally | Replace the service-role key and confirm the configured bucket exists. |

## Operator Checklist
Before handing work to an approver:

- Product defaults are complete.
- Upload status is processed.
- Parse run has expected rows and low or zero errors.
- Column profile is generated.
- Required columns are mapped.
- Mapping snapshot is approved.
- Keyword scoring has run.
- Overrides include reasons.
- Approved keyword set is created.
- Campaign plan is generated and ready for review.
- Sponsored Products Search Term report is processed when post-launch monitoring is needed.
- Monitoring import succeeded and recommendations have evidence.
- Recommendation approval notes explain the human decision.

Before downloading an export:

- Campaign plan is approved.
- Export validation passed.
- Approval note is saved.
- Downloaded file is the current approved export version.
## Account Bulk Upload

The main workflow begins in the Agent Control Center with **Upload Amazon Ads Report**.

1. Choose a CSV/XLS/XLSX Amazon Ads report or bulk sheet.
2. AdSurf uploads and parses the file.
3. AdSurf detects the report type and available entity levels.
4. AdSurf groups rows by account, product, campaign, ad group, target, and search term where columns allow it.
5. Review product mapping suggestions for new or unknown ASINs/SKUs.
6. Configure agents, then run analysis.
7. Review grouped recommendations and approve or reject with notes.

Single-product uploads still exist on product pages for focused keyword and monitoring workflows. Account bulk upload is the preferred path for sellers and agencies managing many products.

Approving a recommendation does not mutate live Amazon Ads.
