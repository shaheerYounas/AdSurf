# 5-Minute End-to-End System Execution Log

This document is a highly detailed, chronological simulated trace of the AdSurf SaaS over a 5-minute session based on the current codebase logic. It includes the frontend (`Next.js`), backend REST API (`FastAPI`), database (`PostgreSQL`/`Supabase`), background workers (`Celery`/internal loops), and external API integrations (like AI Providers).

## [00:00:00.000] - Session Start
* **[Frontend]** User lands on the web URL printed by `npm run dev` (default `http://127.0.0.1:4310/`). Next.js `layout.tsx` mounts.
* **[Frontend]** Client-side initialization. `useMemo` hooks fire in dashboard components.
* **[Frontend]** Request sent: `GET /v1/workspaces/00000000-...-0001/summary`.
* **[Backend]** `main.py` router receives request. `require_workspace_member` middleware validates auth headers.
* **[Database]** `SELECT count(*), status FROM products WHERE workspace_id = ...`
* **[Backend]** Returns `200 OK` with workspace summary data.

## [00:00:15.230] - Navigation to Agent Control Center
* **[Frontend]** User clicks "Agent Ops" sidebar link. Next.js router transitions to `/agents/page.tsx`.
* **[Frontend]** `AgentControlCenter` component mounts. `useEffect` triggers `load()`.
* **[Frontend]** Parallel fetch requests initiated:
  * `GET /v1/workspaces/.../agents`
  * `GET /v1/workspaces/.../products/None/agents/configs`
  * `GET /v1/workspaces/.../agents/runs`
  * `GET /v1/workspaces/.../monitoring/recommendations`
* **[Backend]** Routers process all 4 endpoints natively, fetching rows via `get_agent_registry`, `get_campaign_models`, etc.
* **[Backend]** Returns `200 OK` across all requests.
* **[Frontend]** React state updates -> `setAgents`, `setConfigs`, `setRuns`. Loading spinner stops.

## [00:01:05.110] - File Upload Initialization
* **[Frontend]** User selects `amazon_ads_search_term_report.csv` (15MB) from local filesystem.
* **[Frontend]** User clicks `Upload Report`. Frontend state `isUploading = true`.
* **[Frontend]** `POST /v1/workspaces/.../uploads/init` (Payload: `original_filename, mime_type, file_size_bytes`).
* **[Backend]** `initialize_account_upload` executed.
* **[Database]** `INSERT INTO uploads (id, status) VALUES (..., 'initialized')`.
* **[Storage]** Supabase client pre-signs storage path.
* **[Backend]** Returns `201 Created` with `upload_id` and `storage_path`.

## [00:01:06.400] - File Transfer & Confirmation
* **[Frontend]** `PUT /v1/workspaces/.../uploads/{upload_id}/object` with raw binary file blob.
* **[Storage]** S3-compatible backend (Supabase) receives object. Returns success.
* **[Frontend]** `POST /v1/workspaces/.../uploads/{upload_id}/confirm`.
* **[Backend]** `confirm_upload` executed. `job_repository` queues processing job. 
* **[Database]** `UPDATE uploads SET status = 'queued_for_processing'`.
* **[Backend]** Returns `200 OK`.

## [00:01:08.000] - Worker Parsing Phase
* **[Frontend]** `POST /v1/dev/process-upload-jobs` triggered to mock background worker tick.
* **[Worker]** `UploadProcessingWorker.process_one()` pulls `PROCESS_UPLOAD_JOB_TYPE`.
* **[Database]** `UPDATE jobs SET status = 'running'`.
* **[Worker]** Reads binary file from `StorageService`.
* **[Worker]** `UploadParser.parse()` streams CSV bytes into memory structures.
* **[Worker-ERROR] [00:01:10.050]** `Parse warning: Malformed CSV quote on row 452.` 
  * *Error Logged internally & row skipped.*
* **[Database]** `INSERT INTO upload_parsing_rows` (Batch insert 451 rows).
* **[Database]** `INSERT INTO upload_parsing_errors` (1 error row added).
* **[Worker]** `complete_run` updates DB. Upload moves to `status = 'processed'`.
* **[Database]** `INSERT INTO audit_logs (action="upload.parsed")`.

## [00:01:14.300] - Account Import & Type Detection
* **[Frontend]** `POST /v1/workspaces/.../account-imports` with `upload_id`.
* **[Backend]** `create_account_import` executes.
* **[Backend-Service]** `ReportTypeDetector().detect()` runs against 25 header sample rows.
* **[Backend]** *Match found:* `Search Term Report` (Confidence: High).
* **[Database]** `INSERT INTO account_imports`.
* **[Backend]** Returns `200 OK` containing detection summary and product mapping suggestions.
* **[Frontend]** UI updates: "Report detected, entities grouped, and product mapping suggestions prepared."

## [00:02:10.000] - Agent Workflow Execution
* **[Frontend]** User clicks "Run analysis".
* **[Frontend]** `POST /v1/workspaces/.../agent-runs`
* **[Backend]** Workflow Directed Acyclic Graph (DAG) evaluates.
* **[Agent 1: Metrics Analysis]** `metrics_analysis_agent` kicks in. Groups rows by Target & Keyword.
* **[Agent 2: Pause Review]** `pause_review_agent` inspects high spend/zero sales rows.
* **[Agent 3: AI Recommendation Brain]** `ai_recommendation_brain_agent` formulates input JSON.

## [00:02:45.000] - External AI Provider Invocation (Expected Failure Scenario)
* **[Backend-Service]** `DeepSeekClient` initiates HTTP call to `https://api.deepseek.com`.
* **[Network]** `POST https://api.deepseek.com/chat/completions`
* **[Backend-ERROR] [00:03:00.002]** `HTTP 502 Bad Gateway` from DeepSeek API server.
* **[Backend-Service]** AI Exception caught. 

## [00:03:01.000] - Fallback to Deterministic Rules
* **[Backend-Service]** System triggers standard safety fallback logic.
* **[Backend]** Checks `ai_recommendation_mode="deterministic_fallback"`.
* **[Backend-Rule-Engine]** Evaluates: `if spend > $15 and sales == 0: Action=Pause Keyword`.
* **[Database]** DB inserts new recommendation: `{"type": "pause_review", "entity": "keyword", "status": "pending_approval"}`
* **[Database]** DB marks agent run as `SUCCEEDED` (handled gracefully).

## [00:03:15.000] - Rendering Recommendations
* **[Frontend]** Polling returns new state: `recommendations.length > 0`.
* **[Frontend]** User navigates to Recommendations UI tab.
* **[Frontend]** UI filters map out: 1 Critical recommendation ("Pause Keyword").

## [00:04:30.000] - Human Approval Gateway
* **[Frontend]** User selects "Pause Keyword", types "Agree, spending too much" and clicks Approve.
* **[Frontend]** `POST /v1/workspaces/.../recommendations/123/approve` (Payload: `{ note: "Agree..." }`).
* **[Backend]** `approve_recommendation` route.
* **[Database]** `UPDATE recommendations SET status = 'approved', approved_at = NOW()`.
* **[Database]** `INSERT INTO audit_logs (actor="000...001", action="recommendation.approved", note="Agree...")`.
* **[Backend]** Returns `200 OK`.
* **[Frontend]** Toast notification renders: "Recommendation successfully approved. Generating export rows."

## [00:05:00.000] - Session Segment Ends
* **[System Check]** No Amazon Ads API changes have been made (System abides by Core Prime Directive of read-only + bulk sheet outputs). 
* **[Worker Tracking]** New background job spawned internally to build the Bulk Sheet export file representing the approved changes.
