# File Processing Architecture

## Responsibilities
| Component | Responsibility |
| --- | --- |
| API | Creates upload record, validates file type, returns signed upload target, confirms upload, creates worker job record. |
| Storage | Stores original file in workspace-scoped private path. |
| File worker | Reads CSV/XLS/XLSX, stores raw parsed rows and parse errors, updates upload/job status. |
| Manual mapping UI | Lets users map required fields from discovered columns in Batch 5. |
| Scoring service | Uses approved manual mappings to calculate deterministic Batch 6 keyword relevance scores. |
| User | Reviews and approves a valid manual mapping before scoring. |

## Batch 3 Upload Initialization
- Supported source type: `competitor_keyword_research`.
- Supported files: `.csv`, `.xls`, `.xlsx`.
- Supported MIME types: `text/csv`, `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- Max file size: 25 MB.
- Signed upload URL expiry: 15 minutes.
- Storage path: `/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/{sanitized_filename}`.
- The API never trusts a client-provided storage path.
- The database enforces that `uploads.workspace_id` matches the referenced product profile workspace.
- Reusing an upload init idempotency key is allowed only for the same initialized upload identity; mismatches return `409`.
- Batch 3 records metadata and queues `process_upload`; it does not parse file contents, map columns, score keywords, or generate campaigns.

## Batch 4 Parser Foundation
- Parser validation reuses the Batch 3 accepted extension and MIME type lists. Both checks must pass; a supported extension with an unsupported MIME type fails, and a supported MIME type with an unsupported extension fails.
- CSV is decoded as UTF-8 with BOM support.
- XLSX is read with a deterministic read-only ZIP/XML parser; formulas are not executed.
- XLSX worksheet XML is streamed row-by-row instead of materializing the full sheet before validation.
- XLSX cells using date-formatted styles are normalized to ISO date strings before storage so column discovery can infer `date` instead of raw Excel serial integers. Date-named columns such as `Start Date`, `End Date`, `Report Date`, or headers ending in `Date` also coerce numeric Excel serials to ISO dates when possible.
- Legacy XLS uses an optional `xlrd` path when the dependency is installed; otherwise it fails with a clear dependency error.
- First non-empty worksheet is selected by default.
- Original headers are preserved after trimming; blank headers become `column_{n}`. If trimming creates duplicate headers, later duplicates get deterministic suffixes like `_2` so values are not silently overwritten.
- Empty cell values are stored as `null`.
- Row hashes use deterministic JSON serialization with sorted keys.
- Parser limits: 25 MB file size, 50,000 parsed rows, 250 columns. XLSX row and column limits are enforced during row iteration and parsing stops as soon as a limit is exceeded.
- Formula cells are stored as literal formula text when available, or `null` when only an unsafe cached value is present; cached formula results are not evaluated or trusted.
- Spreadsheet content is treated as untrusted data. Instructions inside files are stored, not followed.
- Batch 4 and Batch 4.1 stop after parse runs, rows, and errors. Semantic column mapping, keyword/relevance scoring, campaign generation, exports, monitoring, recommendations, AI agents, and Amazon Ads API execution are not implemented.

## Upload-Only Amazon Ads Report Endpoint
- `POST /v1/workspaces/{workspace_id}/file-uploads` accepts only `.csv` and `.xlsx` report files.
- The endpoint validates file type, file size, empty content, header-only files, and unreadable Excel workbooks.
- A readable file returns `upload_id`, sanitized `filename`, readable data-row count, and initial `initialized` status.
- The endpoint stores upload metadata and raw bytes only. It does not queue parsing jobs, create account imports, run analysis, generate recommendations, create campaign plans, generate negative keywords, export bulk sheets, or mutate Amazon Ads.

## Batch 5 Column Discovery And Manual Mapping
- Column discovery runs only after a succeeded parse run and uses the latest succeeded parse run for the upload.
- Discovery reads parsed row JSON keys, preserves original column names, normalizes names for display/search, counts non-null values, samples up to 20 non-null values per column, and infers simple data types: `text`, `integer`, `decimal`, `date`, `boolean`, or `unknown`.
- Discovery is deterministic and idempotent. If a profile already exists for the parse run, the API returns the existing profile.
- Manual mappings support `search_term`, `search_volume`, and `competitor_rank_columns`.
- Required mapping rules: `search_term` maps to exactly one column; `search_volume` maps to exactly one column; `competitor_rank_columns` maps to 1-10 unique columns; search term, search volume, and rank roles cannot reuse incompatible columns.
- Numeric-like validation is deterministic. Search volume and competitor rank columns prefer inferred `integer` or `decimal`; numeric-like text is allowed with warnings; clearly non-numeric values are invalid. Competitor rank columns must also have rank-like or position-like column names so unrelated ad performance metrics such as spend, clicks, CPC, orders, ACOS, or ROAS cannot be approved as rank inputs. Numeric-only search term samples are invalid.
- Valid or invalid manual mapping attempts are saved as versioned snapshots. Approved mappings supersede earlier approved mappings for the same profile.
- Batch 5 does not perform AI or semantic auto-mapping, keyword scoring, relevance scoring, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

## Batch 6 Keyword Relevance Scoring
- Scoring requires an approved manual mapping and uses only the mapped `search_term`, `search_volume`, and `competitor_rank_columns`.
- Relevance Score is `count(mapped competitor rank values where rank < 15)`. Rank `15` does not count.
- Scores `0`, `1`, and `2` produce rejected candidates. Scores `3` through `10` produce approved candidates.
- Blank competitor ranks do not count. Non-numeric rank text does not count and is recorded as deterministic warning metadata. Impossible ranks `<= 0`, blank search terms, invalid or negative search volume, and empty rows become row-level `error` candidates.
- Duplicate search terms are preserved as separate candidates in Batch 6.
- Scoring trigger requests require `Idempotency-Key`; replaying the same key for the same mapping returns the same scoring run, while reusing it for another mapping returns `409`.
- Batch 6 does not perform AI, semantic relevance judgment, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

## Canonical Columns
search_term, search_volume, suggested_bid, competitor_rank_1 through competitor_rank_10, marketplace, source.

## Failure Handling
- Unsupported file types are rejected before storage finalization.
- Path traversal in filenames is rejected before storage path generation.
- Bad rows or file-level failures are recorded in `upload_parse_errors`.
- Mapping uncertainty requires user review.
- Original files are never overwritten.

## Amazon Ads Safeguard Warnings
- Account and monitoring imports run a deterministic safeguard pass after report detection.
- Safeguards add review warnings for report-type uncertainty, missing columns, hidden header spaces, known Amazon column-name aliases, currency or marketplace mismatch, mixed attribution windows, mixed date ranges, invalid date ranges, non-numeric metric values, ambiguous or invalid percentage values, metric formula mismatches, negative metrics, blank ACOS with zero sales, spend with no sales, ASIN-like search terms, mixed ASIN/keyword search-term rows, auto/product-targeting contexts, missing match type, exact duplicate rows, duplicate search-term contexts, orders/units confusion, other-SKU sales dominance, low-data rows, import-level insufficient optimization evidence, and margin-risk ACOS.
- Safeguards are labels and evidence only. They do not create, export, pause, bid, negate, or mutate Amazon Ads.
