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
| Recommendations | Review AI-assisted and rules-engine optimization suggestions with seller-friendly evidence, export eligibility, and approval-only safety boundaries. |
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
| Generate recommendations | AI-assisted reasoning can create keep-running, bid, pause-review, negative-keyword, move-to-exact, watch-lock, budget-review, and data-quality recommendations when configured. Deterministic rules remain available as fallback. |
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

## Upload A Product File
1. Open a product.
2. Go to `Uploads`.
3. Choose a CSV or XLSX file.
4. Choose the report type.
   Use `Competitor keyword research` for keyword mapping and campaign planning. Use `Sponsored Products Search Term report` for monitoring imports and recommendation generation.
5. Confirm the upload.
6. Wait for the status to change from queued or processing to processed.

Common statuses:

| Status | Meaning |
| --- | --- |
| initialized | Upload metadata exists, but the file is not confirmed yet. |
| queued_for_processing | The file is ready for the parser. |
| processing | The parser is reading and normalizing rows. |
| processed | Parsing succeeded and rows are available for mapping. |
| failed | Parsing failed and needs review. |

Processed competitor research files open the column mapping workflow. Processed Sponsored Products Search Term reports open the product monitoring workflow so the user can create a monitoring import from the parsed report.

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

## Competitor Direct Phases
The competitor workflow can be run as Full Flow or as a single phase.

Phase 1 uploads, cleans, scores, and verifies competitor research. After scoring, run the Amazon browser verification agent. The agent opens Amazon result pages, captures visible top-result titles/ASINs, and AdSurf automatically checks whether at least three original competitors appear in the top 15 results. The agent does not log in, bypass browser challenges, use stealth scraping, call PAAPI, or execute Amazon Ads changes.

Competitor rank columns can use direct rank labels such as `Organic Rank` or named competitor labels such as `Competitor A Rank`, `Competitor B Rank`, and `Competitor C Rank`. The cleaner stores these rank values before scoring so the deterministic scorer can approve rows with at least three competitors ranking under 15.

Phase 2 prepares campaign rows only when the upload already has rows that are both `scoring_status=approved` and `verification_status=verified`.

Phase 3 runs the deterministic 14-day monitoring simulation from a campaign name. Any bid or lock output remains a pending recommendation or watch status until reviewed.

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
3. Upload the file and choose `Sponsored Products Search Term report` as the report type. The upload is saved with source type `amazon_ads_sp_search_term_report`.
4. Confirm the upload and wait until parsing is processed.
5. Open `Performance report to recommendations`.
6. Select or enter the processed upload ID.
7. Create the monitoring import.
8. Run the local monitoring worker in development or wait for the monitoring worker in deployed environments.

The app validates required base columns such as Campaign Name, Ad Group Name, Targeting, Customer Search Term, Impressions, Clicks, Spend, Sales or 7 Day Total Sales, and Orders or 7 Day Total Orders. Missing required base columns stop recommendation generation. Optional metrics such as ACOS, ROAS, Units, CTR, CPC, CVR, Start Date, and End Date are normalized when present, and missing derived metrics are calculated from base metrics when possible.

## Agent Control Center
Open `Agents` to upload an Amazon Ads report, inspect the agent team, run analysis, review trace events, and send recommendations through human approval checkpoints. You can also open a monitoring import and choose `Open Agent Control Center` for import-specific workflow details.

When `Agents` is opened, the main AdSurf sidebar changes into an Agent Ops sub-menu. Use `Main menu` at the top of that sidebar to return to Dashboard, Products, New product, and the rest of the global navigation.

The Agent Control Center shows:

- An upload-first entry point for account-level reports and bulk sheets.
- A normal Upload Amazon Ads Report card at the top of the workflow with file picker, upload button, Simple/Advanced Mode toggle, and safety labels. The button stays disabled until a file is selected and then sends the file to the backend multipart workflow endpoint.
- Simple Mode for everyday users and Advanced Mode for operators who need raw input/output, template, and deep configuration context.
- Agent Team Dashboard cards with status, current task, mode, provider/model, strictness, confidence threshold, tools/data access, memory/context limits, permissions, cost/time, recommendation count, last run, and error state.
- A Visual Workflow Canvas showing Report Upload, Report Detection, Product Resolution, Metrics Analysis, AI Recommendation Brain, Bid Optimization, Negative Keyword, Budget Allocation, Pause Review, Stakeholder Reporting, and Human Approval.
- A right Agent Inspector on wide desktop screens, or a full-width inspector below the workflow on narrower screens. Inspector tabs wrap cleanly and include Overview, Configuration, Prompt / Business Goal, Input Data, Output, Recommendations, Permissions, Trace, and Safety.
- A Trace Timeline with events such as queued, started, input prepared, model called, output received, validation passed or failed, recommendations created, waiting for human approval, fallback used, stopped, paused, or failed. Upload-created workflows also have durable workflow events available from the workflow status API.
- Human Approval Checkpoints with recommendation cards, metric evidence, risk chips, proposed actions, and approve/reject controls.
- Agent Templates that prefill configuration for conservative profitability, growth scaling, wasted spend cleanup, launch review, or agency audit work.
- Control buttons for run analysis, pause all, resume all, stop all, rerun failed, configure agents, view approvals, and rerun from a selected agent. Account-level Run analysis creates deterministic agent runs and approval-only recommendations from grouped report entities.

Owner/admin users can change agent configuration. Analysts can run, rerun, pause, resume, and stop agents. Approvers and viewers can inspect outputs. These controls never grant agents permission to approve, reject, or execute Amazon Ads changes.

Every recommendation card and approval checkpoint repeats the safety boundary: `Recommendation only`, `Requires human approval`, and `No live Amazon Ads change executed`.

## Review AI Recommendations
Open `Recommendations` to review the queue. Summary cards show total recommendations, actionable items, review-only insights, exportable actions, pending approvals, approved, rejected, and critical/high-priority counts.

Each row shows priority, a seller-friendly recommendation, search term, campaign/ad group, compact metric evidence, recommended action, confidence, exportability, status, and actions. Raw technical rule names and model names are not shown in the main table.

Use filters to focus by status, priority, recommendation type, action class, exportability, confidence, campaign text, search-term text, minimum spend, minimum clicks, and minimum orders. Quick filters cover pending approval, actionable, exportable, critical/high, data checks, negative keywords, bid changes, and move-to-exact recommendations.

Choose `View details` for full campaign/ad group names, metric snapshot, user-friendly reason, raw technical reason, rule name, model/source, recommendation ID, import ID, export eligibility, and approval/rejection history when available. A note is required for approval or rejection. The decision updates the app audit trail only. It does not execute a bid change, pause an ad, add a negative keyword, generate an export, or call the Amazon Ads API.

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
2. AdSurf uploads the file through the account report endpoint and shows a loading state.
3. The backend stores the file, parses rows, creates the account import, creates a workflow ID, and starts the LangGraph workflow through the local queue adapter.
4. AdSurf detects the report type and available entity levels.
5. AdSurf groups rows by account, product, campaign, ad group, target, and search term where columns allow it.
6. Review product mapping suggestions for new or unknown ASINs/SKUs.
7. Watch workflow status, trace events, recommendations, and approval checkpoints update.
8. Review grouped recommendations and approve or reject with notes.

Single-product uploads still exist on product pages for focused keyword and monitoring workflows. Account bulk upload is the preferred path for sellers and agencies managing many products.

Approving a recommendation does not mutate live Amazon Ads.
