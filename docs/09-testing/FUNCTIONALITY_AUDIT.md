# AdSurf Functionality Audit

## Phase 1 - Local Health And Startup

### Startup Commands
| Surface | Command |
| --- | --- |
| Full local app | `npm run dev` from repo root. The launcher starts API and web together and prints the selected URLs. |
| API | `npm run dev:api` from repo root, or `python -m uvicorn apps.api.app.main:app --reload --host 127.0.0.1 --port 8720` |
| Web | `npm run dev:web` from repo root, or `npm --prefix apps/web run dev` |
| Upload worker | Local dev can run `POST /v1/dev/process-upload-jobs`; worker class is `apps.api.app.services.upload_processing_worker.UploadProcessingWorker`. |
| Monitoring worker | Local dev can run `POST /v1/dev/process-monitoring-jobs`; worker class is `apps.api.app.services.monitoring_worker.MonitoringWorker`. |
| API tests | `python -m pytest` or `npm run test:api` |
| Web tests | `npm --prefix apps/web test -- --run` |
| E2E tests | `npm --prefix apps/web run test:e2e` after API and web are running |
| Migrations | Apply Supabase migrations in order from `supabase/migrations`; for local Supabase use `supabase db push` or reset/reapply locally. |

### Required Environment
| Variable | Required for | Current notes |
| --- | --- | --- |
| `APP_ENV=local` | Enables fake storage defaults and local dev worker endpoints. | If absent, storage defaults to Supabase and dev worker endpoints are disabled. |
| `DATABASE_URL` | Database-backed product, upload, monitoring, account import, agent, and recommendation flows. | Running DB was reachable, but missing latest migrations. |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend API base URL. | Defaults to `http://localhost:8720`; `npm run dev` injects the selected API port when fallback moves upward. |
| `NEXT_PUBLIC_LOCAL_WORKSPACE_ID` | Local workspace ID. | Defaults to `00000000-0000-0000-0000-000000000001`. |
| `STORAGE_ADAPTER=fake` | Local file writes without Supabase Storage. | Recommended for local upload testing. |
| `LOCAL_UPLOAD_STORAGE_ROOT` | Fake storage root. | Defaults to `.local-storage/uploads`. |
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_STORAGE_BUCKET_UPLOADS` | Supabase Storage mode. | Required only when `STORAGE_ADAPTER=supabase`. |
| `DEEPSEEK_API_KEY` | AI mode with DeepSeek. | Missing key should produce a clear AI configuration error; deterministic fallback remains available. |

### Health Check Results
- API health endpoint: `GET http://127.0.0.1:8720/health` returns the API envelope with `success: true` and `data.status: "ok"` when the default API port is available; otherwise use the URL printed by the launcher.
- Frontend routes `/dashboard` and `/agents` return HTTP 200.
- Database connection works, but the live DB was missing migrations for account-level upload modes and agent tables.
- Storage mode works after DB migrations when using local fake storage or a configured Supabase storage backend.

## Phase 2 - User-Visible Feature Checklist

### A. App Shell / Navigation
- [x] Dashboard link renders.
- [x] Agents link renders and switches main sidebar into Agent Ops mode.
- [x] Products link renders.
- [x] New product link renders.
- [x] Recommendations link renders.
- [ ] Approvals page link is present only inside Agent Ops anchors, not a dedicated route yet.
- [ ] Settings page link is present only inside Agent Ops anchors, not a dedicated route yet.
- [x] Agent Ops sidebar links point to real Agent Control Center sections where implemented.
- [x] Main menu link returns the sidebar to global navigation.

### B. Dashboard
- [x] Loads workspace summary.
- [x] Refresh button calls the API and shows loading.
- [x] Product counts show.
- [x] Upload counts show.
- [x] Pending recommendations show.
- [x] Error state appears if API fails.
- [x] Empty states appear if no data.

### C. Products
- [x] Product list loads.
- [x] Create product form opens.
- [x] Create product API client is tested.
- [x] Product detail routes exist.
- [ ] Full browser create-product E2E still needs a database-seeded run.
- [x] Validation errors are handled by backend envelope and frontend form surfaces.

### D. Single-Product Upload Flow
- [x] Backend supports product upload init/object/confirm.
- [x] Upload records and object writes are covered by backend tests.
- [x] Upload parsing worker processes queued jobs.
- [ ] Frontend single-product upload still needs the same progress-step polish added to Agent upload.

### E. Account-Level / Agent Control Center Upload Flow
- [x] Choose report file.
- [x] Upload button enables after file selection.
- [x] Button click calls `uploadReport`.
- [x] Loading/progress state appears for init, store, confirm, process, and import creation.
- [x] Frontend sends requests to `/uploads/init`, `/uploads/{id}/object`, `/uploads/{id}/confirm`, `/dev/process-upload-jobs`, and `/account-imports`.
- [x] Backend creates upload and account import records.
- [x] File bytes are stored.
- [x] Report type detection runs.
- [x] Product/entity grouping runs.
- [x] Success message appears with import ID, row count, and entity count.
- [x] Failure message appears with migration/storage/worker hint.
- [x] User sees API base URL, workspace ID, and latest import ID in the upload card.

### F. Agent Control Center
- [x] Agent cards load.
- [x] Agent configs load.
- [x] Workflow canvas loads.
- [x] Inspector opens when agent clicked.
- [x] Config update API client is tested.
- [x] Pause/resume/stop/rerun API client is tested.
- [x] Account import Run Analysis calls a real backend workflow endpoint and creates agent runs/recommendations.
- [ ] Rerun from selected agent needs live import workflow E2E coverage.
- [x] Trace timeline renders.
- [x] Approval checkpoints render.
- [x] Simple/Advanced mode works.
- [x] Controls with no eligible import/run now show visible operator feedback instead of silently doing nothing.

### G. AI Recommendation Flow
- [x] DeepSeek prompt/config plumbing has unit coverage.
- [x] Deterministic fallback has backend coverage.
- [x] AI output validation has backend coverage.
- [x] Invalid AI output is rejected safely.
- [ ] Missing DeepSeek key should be verified in a browser flow.
- [x] Account-level deterministic agent workflow has backend coverage and browser smoke coverage.

### H. Recommendations
- [x] List loads.
- [x] Approve/reject API client functions are tested.
- [x] Backend recommendation approval does not execute live Amazon Ads changes.
- [ ] Browser note-required approve/reject flow needs E2E coverage with seeded recommendations.

### I. Approvals
- [ ] Dedicated approvals page is not implemented yet.
- [x] Agent Control Center approval checkpoint section renders pending recommendation cards.

### J. Workers
- [x] Upload parsing worker works.
- [x] Monitoring worker works.
- [ ] Agent workflow worker is not a separate worker yet; agent actions are API/service mediated.
- [ ] Failed job visibility/retry UI needs implementation.

## Phase 3 - Upload Flow Findings And Fixes

### Findings
1. `apps/api/app/api/v1/account_imports.py` had a Python syntax error in `create_account_import`, which prevented the route from being importable in a fresh API process.
2. The running database was missing `202605270001`, `202605270002`, and `202605270003` migration effects. `upload_source_type` only contained `competitor_keyword_research` and `amazon_ads_sp_search_term_report`, so `account_bulk_report` uploads failed.
3. `202605270002_account_bulk_imports.sql` indexed `recommendations(..., entity_type)` but did not add `recommendations.entity_type` itself.
4. The frontend account upload client swallowed local dev worker failures with `console.warn`, which allowed the UI to proceed into a later, confusing account-import error.
5. Existing CSV fixtures used literal `\n` text, causing no parsed data rows.

### Fixes
1. Fixed `create_account_import` syntax and kept API errors explicit.
2. Added a generic SQLAlchemy error handler returning `DATABASE_OPERATION_FAILED` with migration guidance instead of a silent HTTP 500.
3. Added `recommendations.entity_type` to the account bulk migration.
4. Applied the missing migrations to the current local DB.
5. Rewrote CSV fixtures with real newlines and usable Amazon Ads columns.
6. Added frontend upload progress states and visible debug fields for API base URL, workspace ID, and latest import ID.
7. Changed the frontend upload client to surface local worker failures instead of swallowing them.

### Verified Live Upload Sequence
Using `tests/fixtures/amazon_ads_search_term_report.csv` against the running API:

1. `POST /v1/workspaces/{workspace_id}/uploads/init` created upload `81e0c7db-bd7f-4d76-a2e4-1c528402d0ce`.
2. `PUT /v1/workspaces/{workspace_id}/uploads/{upload_id}/object` stored file bytes.
3. `POST /v1/workspaces/{workspace_id}/uploads/{upload_id}/confirm` queued parsing.
4. `POST /v1/dev/process-upload-jobs` processed one job.
5. `POST /v1/workspaces/{workspace_id}/account-imports` created import `80cc1418-6392-40e4-b1f9-5662ed9ba629`.
6. Detection returned `sponsored_products_search_term_report`; import status was `needs_mapping`; entities created: `7`.

## Current Working Features
- Dashboard summary and refresh.
- Agent Control Center render, upload progress, report upload, parsing, report detection, account import creation, and entity grouping.
- Account-import Run Analysis endpoint: `POST /v1/workspaces/{workspace_id}/account-imports/{account_import_id}/run-analysis`.
- Account-import workflow graph endpoint: `GET /v1/workspaces/{workspace_id}/account-imports/{account_import_id}/agent-workflow`.
- Deterministic account-level agent runs create approval-only recommendations across grouped report entities.
- Product API creation path.
- Agent definition/config/run API clients.
- Recommendation approve/reject API clients.
- Upload and monitoring workers via local dev endpoints.

## Current Broken Or Incomplete Features
- Dedicated Approvals and Settings pages are not implemented.
- Single-product upload UI needs the same granular progress feedback as account upload.
- Browser-level recommendation approval/rejection needs seeded E2E data.
- Playwright Chromium is installed and the current smoke suite passes locally.

## Mock-Only Or Mostly Visual UI
- Agent templates currently prefill config values but are not a marketplace/repository.
- Workflow canvas is a non-drag visual pipeline.
- Some Agent Ops sidebar links are section anchors rather than full pages.

## Recommended Fix Order
1. Add product mapping confirmation UI for `needs_mapping` imports.
2. Upgrade single-product upload UI feedback to match account upload.
3. Seed E2E database fixtures for recommendations so approve/reject can be browser-tested.
4. Add dedicated Approvals and Settings pages or remove those links until implemented.
5. Add a separate async agent workflow worker when imports become too large for synchronous local analysis.
