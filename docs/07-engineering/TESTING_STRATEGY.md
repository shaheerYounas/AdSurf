# Testing Strategy

## Explicit Test Categories
| Category | Purpose |
| --- | --- |
| Domain rule unit tests | Prove deterministic Amazon Ads business rules. |
| Relevance score tests | Verify competitor rank scoring and rejection thresholds. |
| Campaign grouping tests | Verify Hero removal, sorting, grouping, and leftovers. |
| Negative keyword mapping tests | Verify Phrase/Exact and Broad/Phrase negative structures. |
| ACOS divide-by-zero tests | Verify `No sales` and no numeric ACOS when sales are zero. |
| Golden-file bulk sheet tests | Compare generated exports against expected fixtures. |
| Upload fixture tests | Validate CSV/XLSX variations, missing columns, duplicate terms, and bad rows. |
| API contract tests | Verify envelopes, schemas, auth, idempotency, conflicts, pagination. |
| RLS/security tests | Prove workspace isolation and role permissions. |
| Worker retry/idempotency tests | Prove retries, stale recovery, dead letter, and no duplicated side effects. |
| AI mock/schema validation tests | Verify strict schema, retry-on-invalid, refusal, and prompt-injection handling. |
| Accessibility tests | Verify approval flows and keyword tables are keyboard and screen-reader friendly. |
| Migration/constraint tests | Verify migrations, foreign keys, unique constraints, indexes, and enum behavior. |

## Required Unit Tests
| Business rule | Required tests |
| --- | --- |
| Relevance score | Counts ranks under 15; excludes rank 15; handles missing ranks. |
| Rejection | Scores 0, 1, and 2 reject; scores 3-10 eligible. |
| Hero keyword | Hero Score uses relevance score times search volume; tie-breakers are relevance score, search volume, alphabetical order. |
| Grouping | Remaining keywords batch into 5 to 7; leftover terms attach to previous group if possible without exceeding 7. |
| Campaign generation | Exact, Phrase, Broad created for each group. |
| Negatives | Phrase gets Negative Exact; Broad gets Negative Phrase. |
| Defaults | Budget $10 and bid $1.00 when not overridden. |
| Bid recommendation | Low spend plus low traffic recommends 10% increase. |
| Bid safety | Clicks >= 10 and sales = 0 blocks bid increase and recommends review/negative analysis. |
| Lock recommendation | Day 7 sales > 0 and ACOS below target recommends lock/watch. |
| ACOS handling | Sales = 0 never produces numeric ACOS. |
| Approval safety | No customer-impacting state change without approval. |

## Integration Tests
Upload parsing, column mapping, scoring, keyword approval, campaign plan generation, bulk export validation, monitoring ingestion, recommendation creation, and approval queue decisions.

## E2E Tests
Customer journey from product profile through upload, keyword approval, campaign review, bulk export approval, monitoring, recommendation approval, and audit log verification.

## Golden-File Rule
Generated bulk sheet output must match expected fixture files except timestamps and generated IDs. Tests must normalize timestamp and generated ID fields before comparison.

## Security And RLS Acceptance
- Users cannot read or write another workspace's products, uploads, keywords, plans, exports, recommendations, approvals, or audit logs.
- `viewer` cannot mutate state.
- `approver` can approve only permitted approval objects.
- Service-role worker operations still write workspace_id and audit events.

## Batch 2 Tests
- Product profile repository create/list/get/update behavior is tested through the repository boundary.
- Workspace-scoped API tests cover missing auth, missing membership, read roles, write roles, and cross-workspace isolation.
- Staging/production tests prove local/test placeholder auth cannot be used as a production fallback.
- RLS migration tests verify foundation tables have RLS enabled and no broad public policies are introduced.

## Batch 2.1 Hardening Tests
- Missing or unknown `APP_ENV` fails closed for workspace-scoped auth.
- Local/test auth uses `x-test-workspaces` role-per-workspace mappings.
- Optional live RLS tests apply migrations to a disposable local database and verify product profile isolation, viewer write blocking, non-member denial, and non-recursive `workspace_members` reads.

Run the optional live RLS test with:

```bash
$env:RLS_TEST_DATABASE_URL="postgresql://postgres:postgres@localhost:54322/postgres"
python -m pytest tests/integration/test_rls_integration.py
```

The live RLS test skips unless a localhost database URL is provided.

## Batch 3 Upload Tests
- Upload initialization covers success, unsupported MIME type, unsupported extension, oversized files, missing idempotency, duplicate idempotency, role permissions, cross-workspace denial, and safe storage path generation.
- Upload confirmation covers `process_upload` job creation and duplicate confirmation without duplicate jobs.
- Frontend smoke tests cover the uploads page shell and shared upload constraints.

## Batch 3.1 Hardening Tests
- Migration tests verify composite upload/product workspace integrity.
- Upload init tests verify idempotency identity conflicts for product, filename, MIME type, file size, source type, and post-queue replay.
- Confirm tests verify only initialized uploads can be queued, queued replays return the existing job, active/terminal states return `409`, and duplicate confirms create one job plus one `job.queued` audit entry.

## Batch 4 Parser And Worker Tests
- Parser tests cover CSV success, XLSX success, empty file failure, row/column limits, stable row hash, empty values as null, first non-empty worksheet selection, and prompt-injection text stored as data.
- Worker tests cover successful `process_upload`, failed parsing status updates, parse rows pagination, and cross-workspace parse run denial.
- Migration tests verify parse tables, read-only RLS shape, row/error constraints, and upload integrity foreign keys.

## Batch 4.1 Cleanup Tests
- Migration tests verify the parse run composite identity constraint and composite foreign keys from parsed rows/errors back to the owning parse run workspace/product/upload.
- Parser tests verify extension and MIME type validation both fail closed using the Batch 3 accepted constants.
- XLSX parser tests verify row and column limits fail during parsing, first non-empty worksheet selection is preserved, date-formatted cells normalize to ISO dates, and formula cells are not executed or replaced with cached evaluated results.
- Batch 4.1 remains parse-only: no semantic column mapping, keyword scoring, relevance scoring, campaign generation, exports, monitoring, recommendations, AI agents, or Amazon Ads API behavior is tested or implemented.

## Batch 5 Manual Column Mapping Tests
- Migration tests verify column profile, profile-column, and manual mapping tables, composite scope foreign keys, uniqueness constraints, and non-broad RLS.
- Column profile tests cover generation success, idempotency, blocked generation before a succeeded parse, original column preservation, normalized names, sample value limit, and inferred text/numeric/date types.
- Manual mapping validation tests cover valid mappings, missing `search_term`, missing `search_volume`, missing competitor ranks, duplicate role columns, non-numeric search volume/rank columns, rank-name semantic rejection for unrelated numeric metrics, numeric-like text warnings, invalid mapping approval failure, approval superseding, role denial for viewer/approver, and cross-workspace denial.
- Frontend tests cover the mapping page, boundary message, manual field controls, and upload-page link after parse success.
- Batch 5 remains manual and deterministic: no AI agents, semantic auto-mapping, keyword scoring, relevance scoring, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API behavior is tested or implemented.

## Batch 6 Keyword Relevance Scoring Tests
- Migration tests verify scoring run and keyword candidate tables, composite scope foreign keys, idempotency/version uniqueness, useful indexes, and non-broad RLS.
- Rule tests verify rank `< 15` counting, rank `15` exclusion, scores `0`, `1`, and `2` rejected, scores `3+` approved, blank ranks not counted, non-numeric rank warnings, blank search term errors, negative search volume errors, and impossible rank errors.
- API tests verify scoring requires an approved mapping, invalid/draft mappings cannot be scored, owner/admin/analyst can trigger scoring, viewer/approver cannot trigger scoring, duplicate search terms are preserved, cross-workspace scoring is blocked, candidate filters and pagination work, idempotent replay returns the existing run, idempotency mismatch returns `409`, and audit events are created once for replay.
- Frontend tests cover the approved-mapping scoring button, scoring boundary message, scoring summary, candidate table labels, and absence of campaign generation controls.
- Batch 6 remains deterministic scoring only: no AI agents, semantic relevance judgment, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API behavior is tested or implemented.

## Batch 7 Keyword Review Tests
- Migration tests verify keyword override and approved keyword set tables, composite scope foreign keys, non-blank override reasons, snapshot item constraints, and non-broad RLS.
- API tests verify owner/admin/analyst can create overrides and approved keyword sets, viewer/approver cannot create overrides, reasons are required, whitespace-only reasons are rejected, error candidates cannot be overridden, effective status reflects overrides, duplicate overrides return `409`, review filters work, cross-workspace access is blocked, and audit events are written once per action.
- Approved keyword set tests verify snapshots include effective approved candidates, exclude rejected and error candidates, include override-approved candidates, exclude override-rejected candidates, reject zero-approved snapshots, paginate items, and remain unchanged after later overrides.
- Frontend tests cover the review table labels, override reason modal text, campaign-generation boundary message, approved keyword set controls, and absence of campaign builder/export buttons.
- Batch 7 remains keyword review and snapshot only: no AI agents, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API behavior is tested or implemented.

Run backend tests with:

```bash
python -m pytest -p no:cacheprovider tests/unit tests/integration
```

Run frontend tests with:

```bash
npm --workspace apps/web run test
```
