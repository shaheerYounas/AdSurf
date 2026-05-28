# Manual QA Checklist

Use this checklist after starting the API and web app locally.

## Start Services
| Action | Expected result | If failed |
| --- | --- | --- |
| Run `npm run dev:api`. | API listens on `http://127.0.0.1:8000`. | Check Python deps, `APP_ENV`, `DATABASE_URL`, and import errors. |
| Run `npm run dev:web`. | Web app listens on `http://127.0.0.1:3000`. | Check Node version and `npm install`. |
| Open `http://127.0.0.1:8000/health`. | JSON response has `success: true` and `status: ok`. | Restart API and inspect terminal logs. |
| Apply migrations. | `upload_source_type` includes `account_bulk_report`; account import tables exist. | Run Supabase migrations in order; check `docs/09-testing/FUNCTIONALITY_AUDIT.md`. |

## Dashboard
| Action | Expected result | If failed |
| --- | --- | --- |
| Open `/dashboard`. | Dashboard shell, metric cards, safety copy, products, checklist, and recommendation queue render. | Check web console and API `/dashboard-summary`. |
| Click Refresh. | Button disables/spins briefly; data refreshes or readable error appears. | Check API base URL shown by frontend config and backend logs. |

## Product Workflow
| Action | Expected result | If failed |
| --- | --- | --- |
| Open `/products/new`. | Product form renders. | Check route and frontend build. |
| Create a product. | Product saves and appears in product list/detail. | Check validation message, product API route, and database migrations. |

## Account Report Upload
| Action | Expected result | If failed |
| --- | --- | --- |
| Open `/agents`. | Agent Ops sidebar and Agent Control Center render. | Check app sidebar and `/agents` route. |
| Select `tests/fixtures/amazon_ads_search_term_report.csv`. | Upload button becomes enabled. | Confirm file input accepts `.csv`. |
| Click Upload report. | Progress states appear: creating upload, storing file, queueing parser, processing rows, creating account import. | Check browser network tab for failed request. |
| Wait for completion. | Success message shows import ID, processed rows, and entity count. | If migration error appears, apply latest Supabase migrations. If worker error appears, run local upload worker endpoint or set `APP_ENV=local`. |
| Review workflow canvas. | Report Detection Agent is selected or visible as next step. | Check account import response and selected agent state. |
| Click Run analysis. | Account agents run, workflow nodes update, trace events appear, and pending recommendations are created. | Check `POST /v1/workspaces/{workspace_id}/account-imports/{account_import_id}/run-analysis` and backend logs. |

## Agent Controls
| Action | Expected result | If failed |
| --- | --- | --- |
| Click an agent card. | Inspector changes to that agent. | Check React console errors. |
| Toggle Simple/Advanced Mode. | Advanced-only sections such as templates appear/disappear. | Check local component state. |
| Click Run analysis before uploading/opening an import. | A visible message explains that a report or import-level workflow is required. | Check Agent Control Center message state. |
| Click Pause/Resume/Stop/Rerun when runs exist. | API request is sent and success/error feedback appears. | Check `/agent-runs/{id}/{action}` route and selected run status. |

## Recommendations And Approval
| Action | Expected result | If failed |
| --- | --- | --- |
| Open `/recommendations`. | Recommendation list or empty state renders with safety boundary. | Check `/recommendations` API response. |
| Approve a recommendation with a note. | Status becomes approved and audit record is written. | Check note is not blank and user role is approver/admin/owner/analyst as allowed. |
| Reject a recommendation with a note. | Status becomes rejected and audit record is written. | Check API error envelope. |
| Confirm live execution. | UI still says no live Amazon Ads change executed. | Any live mutation behavior is a release blocker. |

## Workers
| Action | Expected result | If failed |
| --- | --- | --- |
| Run `POST /v1/dev/process-upload-jobs`. | Queued upload jobs are processed. | Check `APP_ENV=local` and storage object exists. |
| Run `POST /v1/dev/process-monitoring-jobs`. | Queued monitoring imports are processed. | Check monitoring import status and upload source type. |

## Final Safety Check
| Action | Expected result | If failed |
| --- | --- | --- |
| Search UI for recommendation safety copy. | "Recommendation only", "Requires human approval", and "No live Amazon Ads change executed" are visible in relevant flows. | Add the safety copy before release. |
| Review network calls during approval. | No Amazon Ads mutation endpoint is called. | Stop release and remove mutation path. |
