# Database Schema

## Naming Decision
Use workspace language in database tables and APIs. `workspace_id` is the canonical scope column.

## Table Overview
| Table | Purpose | Key relationships |
| --- | --- | --- |
| workspaces | Workspace for seller or agency | Has users, profiles, files, plans. |
| workspace_members | User membership and role | Links auth user to workspace. |
| product_profiles | Advertised product settings | Owns uploads and plans. |
| bulk_product_imports | Temporary reviewed product-list import sessions | Owns per-row validation and commit outcomes. |
| bulk_product_import_rows | Source-numbered product import row previews | Links import rows to created/updated/skipped products. |
| uploads | Original CSV/XLSX/report file metadata | Source for later parsed rows and snapshots. |
| parsed_file_rows | Normalized uploaded rows | Links to file upload. |
| column_mappings | Later canonical mapping workflow | Links upload to canonical columns after Batch 5 manual mapping foundation. |
| keyword_scoring_runs | Deterministic scoring attempts | Links approved mapping to candidate outputs. |
| keyword_candidates | Batch 6 candidate search terms | Links source rows to relevance scores and row errors. |
| relevance_scores | Later rule result table if separated | Links inputs and rule version. |
| approved_keyword_sets | Immutable approved keyword snapshots | Used by campaign plans. |
| campaign_plans | Draft generated campaign plan | Requires approval for export. |
| campaign_groups | Hero or keyword batches | Contains generated campaigns. |
| bulk_exports | Generated Amazon bulk sheets | Links approved plan and storage file. |
| monitoring_snapshots | Campaign performance metrics | Feeds recommendations. |
| account_imports | Account-level parsed Amazon Ads report imports | Owns detected report type and grouped entities. |
| account_import_entities | Product/campaign/ad group/target/search-term groups | Links account imports to entity evidence. |
| product_mapping_suggestions | Pending product mapping suggestions | Requires user confirmation for uncertain products. |
| recommendations | Rule-generated optimization proposals | Requires approval/rejection. |
| approvals | Human approval records | Links actor, object, decision. |
| audit_logs | Immutable event log | Records decisions and actor context. |
| ai_runs | AI calls and structured outputs | Stores provider/model/schema metadata. |
| rule_versions | Versioned deterministic rule definitions | Referenced by scores, plans, exports, recommendations. |
| job_queue | Background job queue records | Tracks processing state, locking, retries. |
| outbox_events | Reliable event records for side effects | Published after transactional writes. |

Batch 1 includes `outbox_events` as infrastructure only. It establishes the reliability table for future worker side effects but does not implement event publishing or consumers yet.

Batch 2 implements product profile persistence against the database repository boundary. Local/test may use a local repository adapter only when `DATABASE_URL` is absent; staging and production require `DATABASE_URL`.

Batch 3 adds upload metadata, signed upload initialization, confirmation, and queued `process_upload` jobs. Batch 3.1 hardens upload integrity and idempotency.

Batch 4 adds parse-run metadata, parsed row storage, and parse error storage. It does not add semantic column mappings, keyword scoring, relevance scoring, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

Batch 4.1 hardens parse table integrity and parser validation only. It does not add column mapping, keyword scoring, relevance scoring, campaign generation, exports, monitoring, recommendations, AI agents, or Amazon Ads API execution.

Batch 5 adds deterministic column discovery and manual column mapping snapshots only. It does not add AI agents, semantic AI column mapping, keyword scoring, relevance scoring, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

Batch 6 adds deterministic keyword relevance scoring from approved manual mappings only. It does not add AI agents, semantic relevance judgment, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

Batch 7 adds keyword review, manual approve/reject overrides with required reasons, and locked approved keyword set snapshots only. It does not add AI agents, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

Batch 8 adds deterministic campaign plan generation from locked approved keyword set snapshots. Batch 9 adds approved CSV bulk exports from approved campaign plans. Both remain bulk-sheet-only and do not add Amazon Ads API execution.

Batch 10 adds Sponsored Products Search Term monitoring imports, normalized targeting/search-term snapshots, deterministic recommendation records, human decision records, and deterministic summary metadata. Phase 1 adds evidence JSON and the full monitoring recommendation taxonomy. Monitoring remains recommendation-only and does not execute bid changes, pauses, negatives, exports, or Amazon Ads API actions.

Bulk product imports are a preview-then-confirm workflow. Uploading a CSV/TSV/XLSX creates `bulk_product_imports` and `bulk_product_import_rows` only; product profiles are created or updated after the commit endpoint atomically claims a `ready_for_review` import. Row numbers preserve the original source file row numbers, including the header offset.

Local SQLite stores JSON fields such as monitoring import warnings, snapshot raw metrics, recommendation evidence/action/explanation payloads, AI run output, agent event metadata, competitor upload warnings/detected columns, and competitor cleaned row rank/raw metric payloads as JSON text. Repository row mappers must deserialize these values before constructing Pydantic schemas.

Local SQLite development stores JSON columns as text, so repository reads must deserialize JSON payloads before returning API models. Upload parsing, competitor uploads and cleaned rows, account imports, monitoring recommendations, workflows, jobs, audit logs, and approval gate writes also provide explicit timestamps where the local database does not supply Postgres defaults.

Custom agent builder records are workspace-owned across agents, tools, knowledge bases, links, sub-agents, threads, messages, memories, and runs. API routes validate parent ownership before listing, creating, updating, deleting, linking, or reading child records, even when the child repository method accepts only an object id.

## Core Columns
| Table | Required columns |
| --- | --- |
| workspaces | id, name, type, status, created_at, updated_at |
| workspace_members | id, workspace_id, user_id, role, status, created_at, updated_at |
| product_profiles | id, workspace_id, asin, marketplace, currency, product_name, default_daily_budget, default_bid, status, created_by, updated_by, created_at, updated_at |
| bulk_product_imports | id, workspace_id, original_filename, file_hash, status, conflict_strategy, total_rows, valid_rows, invalid_rows, duplicate_in_file_rows, already_exists_rows, created_rows, updated_rows, skipped_rows, failed_rows, detected_columns_json, workspace_default_acos, workspace_default_budget, workspace_default_bid, created_by, created_at, updated_at |
| bulk_product_import_rows | id, workspace_id, import_id, row_number, status, product_name, asin, sku, marketplace, currency, target_acos, default_budget, default_bid, brand, category, notes, product_id, validation_errors, raw_row_json, created_at |
| uploads | id, workspace_id, product_id, uploaded_by, original_filename, storage_path, mime_type, file_size_bytes, status, source_type, idempotency_key, created_at, updated_at, confirmed_at |
| upload_parse_runs | id, workspace_id, product_id, upload_id, job_id, status, parser_version, original_filename, storage_path, detected_file_type, detected_sheet_names, selected_sheet_name, total_rows, total_columns, parsed_rows_count, error_rows_count, started_at, completed_at, created_at, updated_at, error_message |
| upload_parsed_rows | id, workspace_id, product_id, upload_id, parse_run_id, row_number, row_data_json, row_hash, created_at |
| upload_parse_errors | id, workspace_id, product_id, upload_id, parse_run_id, row_number, error_code, error_message, raw_value_json, created_at |
| upload_column_profiles | id, workspace_id, product_id, upload_id, parse_run_id, status, total_columns, total_rows_sampled, created_at, updated_at |
| upload_column_profile_columns | id, workspace_id, product_id, upload_id, parse_run_id, column_profile_id, original_column_name, normalized_column_name, column_index, non_null_count, sample_values_json, inferred_data_type, created_at |
| upload_column_mappings | id, workspace_id, product_id, upload_id, parse_run_id, column_profile_id, status, mapping_version, mapping_type, mapping_json, validation_errors_json, created_by, created_at, approved_at |
| keyword_scoring_runs | id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id, status, scoring_version, rule_version_id, idempotency_key, total_rows, scored_rows, approved_count, rejected_count, error_count, started_at, completed_at, created_at, updated_at, error_message |
| keyword_candidates | id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id, scoring_run_id, source_row_id, search_term, search_volume, competitor_rank_values_json, relevance_score, scoring_status, rejection_reason, created_at, updated_at |
| keyword_candidate_overrides | id, workspace_id, product_id, scoring_run_id, keyword_candidate_id, override_action, original_scoring_status, new_status, reason, created_by, created_at |
| approved_keyword_sets | id, workspace_id, product_id, scoring_run_id, column_mapping_id, name, status, keyword_count, created_by, created_at, approved_at |
| approved_keyword_set_items | id, workspace_id, product_id, approved_keyword_set_id, scoring_run_id, keyword_candidate_id, search_term, search_volume, relevance_score, source_status, final_status, override_id, created_at |
| column_mappings | id, workspace_id, upload_id, source_column, canonical_column, confidence, status, reviewed_by, created_at, updated_at |
| relevance_scores | id, workspace_id, keyword_candidate_id, score, rule_version_id, competitor_rank_inputs_json, rejection_reason, created_at |
| campaign_plans | id, workspace_id, product_id, approved_keyword_set_id, version, status, rule_version_id, plan_json, created_by, approved_by, approval_note, approved_at, created_at, updated_at |
| campaign_groups | id, campaign_plan_id, group_type, group_index, match_type_set, keywords_json |
| bulk_exports | id, workspace_id, product_id, campaign_plan_id, storage_path, original_filename, status, rows_json, approved_by, approval_note, approved_at, created_at, updated_at |
| monitoring_imports | id, workspace_id, product_id, upload_id, parse_run_id, report_type, status, date_range_start, date_range_end, total_rows, processed_rows, error_rows, data_quality_warnings_json, error_message, created_by, created_at, updated_at |
| account_imports | id, workspace_id, upload_id, parse_run_id, report_type, status, detected_report_type, detection_confidence, total_rows, processed_rows, error_rows, data_quality_warnings_json, created_by, created_at, updated_at |
| account_import_entities | id, workspace_id, account_import_id, product_id, asin, sku, product_name, campaign_name, ad_group_name, targeting, customer_search_term, entity_type, entity_key, resolution_status, metrics_json, raw_row_refs_json, created_at |
| product_mapping_suggestions | id, workspace_id, account_import_id, asin, sku, detected_product_name, suggested_product_id, status, created_at, updated_at |
| monitoring_snapshots | id, workspace_id, product_id, monitoring_import_id, upload_id, parse_run_id, source_row_id, campaign_name, ad_group_name, targeting, match_type, customer_search_term, report_start_date, report_end_date, impressions, clicks, ctr, cpc, spend, sales, acos, roas, orders, units, cvr, raw_metrics_json, created_at |
| recommendations | id, workspace_id, product_id, monitoring_import_id, snapshot_id, recommendation_type, entity_type, status, priority, confidence, campaign_name, ad_group_name, targeting, customer_search_term, rule_version, rule_name, current_metric_snapshot_json, input_metrics_json, evidence_json, proposed_action_json, explanation_json, created_by, decided_by, decided_at, created_at, updated_at |
| recommendation_decisions | id, workspace_id, recommendation_id, decision, note, actor_user_id, created_at |
| approvals | id, workspace_id, object_type, object_id, decision, actor_user_id, actor_role, notes, idempotency_key, created_at |
| audit_logs | id, workspace_id, actor_user_id, event_type, object_type, object_id, metadata_json, created_at |
| ai_runs | id, workspace_id, product_id, agent_name, provider, model, schema_version, input_hash, output_json, status, latency_ms, created_at |
| rule_versions | id, rule_set, version, description, config_json, active_from, active_to, created_at |
| job_queue | id, workspace_id, job_type, status, payload_json, idempotency_key, attempts, locked_at, locked_by, heartbeat_at, last_error, created_at, updated_at |
| outbox_events | id, workspace_id, event_type, aggregate_type, aggregate_id, payload_json, status, published_at, created_at |

## Status Enums
| Entity | Allowed statuses |
| --- | --- |
| uploads | initialized, uploaded, queued_for_processing, processing, processed, failed, cancelled, archived |
| upload_parse_runs | running, succeeded, failed |
| upload_column_profiles | generated, failed |
| upload_column_profile_columns inferred_data_type | text, integer, decimal, date, boolean, unknown |
| upload_column_mappings | draft, valid, invalid, approved, superseded |
| upload_column_mappings mapping_type | manual |
| keyword_scoring_runs | running, succeeded, failed |
| keyword_candidates scoring_status | approved, rejected, error |
| keyword_candidate_overrides override_action | approve, reject |
| keyword_candidate_overrides new_status | approved, rejected |
| approved_keyword_sets | created, locked, superseded |
| approved_keyword_set_items final_status | approved |
| bulk_product_imports | parsing, validating, ready_for_review, creating, completed, failed, cancelled |
| bulk_product_import_rows | valid, invalid, duplicate_in_file, already_exists, skipped, created, updated, failed |
| jobs | queued, running, succeeded, failed, dead_letter, cancelled |
| campaign_plans | draft, generated, pending_approval, approved, rejected, superseded |
| bulk_exports | requested, generating, generated, pending_approval, approved, failed, expired |
| monitoring_imports | queued, processing, succeeded, failed |
| recommendations | pending_approval, approved, rejected, superseded |
| approvals | approved, rejected, revoked_for_error |

## Constraints And Indexes
| Requirement | Decision |
| --- | --- |
| Foreign keys | All relationship columns must have foreign keys with restrictive deletes unless retention policy explicitly allows cascade. |
| Uniqueness | Enforce unique normalized search term per workspace, product, upload; one monitoring import per workspace, product, upload, and report type; unique campaign plan version per product; unique export per campaign plan version unless superseded. |
| Indexes | Index workspace_id on every workspace-scoped table; index foreign keys, status fields, created_at, job status/locked_at, and recommendation status. |
| Timestamps | Every mutable table has created_at and updated_at; append-only tables have created_at. |
| Actors | User-driven mutable tables include created_by and updated_by where relevant. Approval and audit tables always include actor_user_id. |

## Money And Decimal Precision
| Value type | Database type |
| --- | --- |
| budgets, bids, spend, sales, cpc | numeric(12,4) |
| acos, roas, percentages | numeric(8,4) |

Do not store money, bids, spend, sales, CPC, ACOS, ROAS, or percentages as binary floating point values.

## RLS Shape
| Rule | Requirement |
| --- | --- |
| Workspace scope | Every workspace-scoped table must include `workspace_id`. |
| Membership | Users can only access rows through active workspace membership. |
| owner/admin | Can manage workspace settings, members, product profiles, exports, and audit access. |
| analyst | Can view workspace data and create uploads. |
| approver | Can approve or reject recommendations and export-related approvals. |
| viewer | Can read permitted workspace data without mutation. |
| Service role | Backend service role may perform worker/system operations but must still write workspace_id and audit records. |

## Batch 2 RLS Status
Foundation RLS policies are defined for `workspaces`, `workspace_members`, `product_profiles`, `audit_logs`, `rule_versions`, `job_queue`, and `outbox_events`. Batch 2.1 uses `SECURITY DEFINER` helper functions with locked `search_path` for workspace membership and role checks so policies do not recursively query `workspace_members` from its own policy. App-layer membership checks are implemented now. Full Supabase claim wiring for `auth.uid()` must be completed before relying on RLS as the only enforcement layer.

## Batch 3 Upload RLS Status
The `uploads` table has RLS enabled. Workspace members can read upload metadata. Only `owner`, `admin`, and `analyst` can insert or update upload lifecycle rows. Policies use the Batch 2.1 `SECURITY DEFINER` helper functions and do not query `workspace_members` directly from policy bodies.

## Batch 4 Parse Table RLS Status
`upload_parse_runs`, `upload_parsed_rows`, and `upload_parse_errors` have RLS enabled. Workspace members can read parse metadata and parsed data. Customer roles do not receive insert or update policies for these tables; parse writes are backend/service-role operations only.

## Batch 4 Parse Constraints
| Requirement | Decision |
| --- | --- |
| Parse run uniqueness | `upload_parse_runs.job_id` is unique. |
| Upload integrity | Parse tables carry `workspace_id`, `product_id`, and `upload_id` and reference `uploads(workspace_id, product_id, id)`. |
| Upload archive behavior | Archiving marks the upload `archived` and removes only pending queued upload jobs. Completed or failed processing jobs and parse history are preserved for auditability and later reprocess workflows. |
| Parse child integrity | `upload_parse_runs` enforces `unique(id, workspace_id, product_id, upload_id)`, and rows/errors use composite foreign keys from `(parse_run_id, workspace_id, product_id, upload_id)` to that parse run identity. Direct DB writes cannot attach row/error metadata to a different workspace, product, or upload than the owning parse run. |
| Parsed row uniqueness | `upload_parsed_rows` enforces `unique(parse_run_id, row_number)`. |
| Parsed row data | `row_data_json` and `row_hash` are required. |
| Parse errors | `error_code` and `error_message` are required; `row_number` may be null for file-level errors. |

## Batch 5 Column Mapping Constraints
| Requirement | Decision |
| --- | --- |
| Column profile lifecycle | A profile is generated from the latest succeeded parse run for an upload and is idempotent with `unique(parse_run_id)`. |
| Profile integrity | `upload_column_profiles(parse_run_id, workspace_id, product_id, upload_id)` has a composite foreign key to `upload_parse_runs(id, workspace_id, product_id, upload_id)`. |
| Profile columns integrity | `upload_column_profile_columns(column_profile_id, workspace_id, product_id, upload_id, parse_run_id)` references `upload_column_profiles(id, workspace_id, product_id, upload_id, parse_run_id)`. |
| Column uniqueness | Profile columns enforce `unique(column_profile_id, column_index)` and `unique(column_profile_id, original_column_name)`. |
| Mapping snapshots | `upload_column_mappings` stores immutable manual mapping attempts with `mapping_type = manual`, required `mapping_json`, and `unique(column_profile_id, mapping_version)`. |
| Mapping integrity | Mappings reference the same profile scope through the composite profile foreign key. |
| Mapping approval | Only `valid` mappings can become `approved`; approving one mapping supersedes prior approved mappings for the same profile. Approval does not trigger scoring. |
| Mapping validation messages | `validation_errors_json` stores both errors and warnings using a `severity` field. |

## Batch 5 Column Mapping RLS Status
`upload_column_profiles`, `upload_column_profile_columns`, and `upload_column_mappings` have RLS enabled. Workspace members can read profiles, profile columns, and mappings. Only `owner`, `admin`, and `analyst` can insert or update mappings. Customer roles do not receive insert/update policies for generated profile tables; backend/service-role operations create profiles and profile columns. No broad public policies are allowed.

## Batch 6 Keyword Scoring Constraints
| Requirement | Decision |
| --- | --- |
| Scoring run lifecycle | `keyword_scoring_runs` records one deterministic scoring attempt for an approved manual mapping and version. |
| Mapping integrity | `keyword_scoring_runs(column_mapping_id, workspace_id, product_id, upload_id, parse_run_id)` references `upload_column_mappings(id, workspace_id, product_id, upload_id, parse_run_id)`. |
| Candidate integrity | `keyword_candidates(scoring_run_id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)` references `keyword_scoring_runs(id, workspace_id, product_id, upload_id, parse_run_id, column_mapping_id)`. |
| Versioning | Scoring runs enforce `unique(column_mapping_id, scoring_version)`. |
| Idempotency | Scoring runs enforce `unique(workspace_id, idempotency_key)` for trigger replay. |
| Candidate status | Row outcomes are `approved`, `rejected`, or `error`; approved/rejected rows require a non-blank `search_term`. |
| Score range | `relevance_score` is null for row errors or an integer from `0` to `10`. |
| Indexes | Candidates are indexed by workspace/product, upload, scoring run, status, relevance score, and search term. |

## Batch 6 Keyword Scoring RLS Status
`keyword_scoring_runs` and `keyword_candidates` have RLS enabled. Workspace members can read scoring runs and candidates. Customer roles do not receive insert/update policies; backend/service-role operations create scoring rows and still write workspace scope. The API allows only `owner`, `admin`, and `analyst` to trigger scoring. No broad public policies are allowed.

## Batch 7 Keyword Review Constraints
| Requirement | Decision |
| --- | --- |
| Override integrity | `keyword_candidate_overrides(keyword_candidate_id, workspace_id, product_id, scoring_run_id)` references `keyword_candidates(id, workspace_id, product_id, scoring_run_id)`. |
| Override reason | `reason` is required and cannot be blank after trimming. |
| Override uniqueness | MVP enforces one active override per keyword candidate with `unique(keyword_candidate_id)`. |
| Effective status | If no override exists, effective status equals `keyword_candidates.scoring_status`; otherwise it equals `keyword_candidate_overrides.new_status`. |
| Error candidates | Candidates with `scoring_status = error` cannot be overridden or included in approved keyword sets in the MVP. |
| Set integrity | `approved_keyword_sets(scoring_run_id, workspace_id, product_id, column_mapping_id)` references `keyword_scoring_runs(id, workspace_id, product_id, column_mapping_id)`. |
| Item integrity | `approved_keyword_set_items(approved_keyword_set_id, workspace_id, product_id)` references `approved_keyword_sets(id, workspace_id, product_id)`, and item candidate scope references `keyword_candidates(id, workspace_id, product_id, scoring_run_id)`. |
| Snapshot immutability | Approved keyword sets are created locked with copied item values; later overrides do not mutate existing snapshot items. |
| Campaign boundary | Approved keyword sets are the source of truth for future campaign generation, but Batch 7 does not generate campaigns. |

## Batch 7 Keyword Review RLS Status
`keyword_candidate_overrides`, `approved_keyword_sets`, and `approved_keyword_set_items` have RLS enabled. Workspace members can read overrides and keyword set snapshots. Only `owner`, `admin`, and `analyst` can insert review overrides and approved keyword set records; `viewer` and `approver` cannot create them in the MVP. No broad public policies are allowed.

## Batch 8/9 Campaign And Export Constraints
| Requirement | Decision |
| --- | --- |
| Plan source | Campaign plans reference immutable `approved_keyword_sets`, not live candidates. |
| Plan status | Plans are created as `generated` and require explicit note-based approval before export. |
| Export source | Bulk exports require an approved campaign plan. |
| Export approval | Export generation requires a separate non-empty approval note and writes an audit event. |
| Execution boundary | Exports are CSV handoff only; no Amazon Ads API side effects occur. |

## Batch 8/9 RLS Status
`campaign_plans` and `bulk_exports` have RLS enabled. Workspace members can read plan/export metadata. Only `owner`, `admin`, and `analyst` can create or approve plans and exports in the current MVP implementation.

## Batch 10 Monitoring Constraints
| Requirement | Decision |
| --- | --- |
| Report type | `amazon_ads_sp_search_term_report` only for the first monitoring implementation. |
| Required input columns | Base report fields only: Campaign Name, Ad Group Name, Targeting, Customer Search Term, Impressions, Clicks, Spend, Sales or 7 Day Total Sales, and Orders or 7 Day Total Orders. |
| Derived metrics | CTR, CPC, CVR, ACOS, ROAS, Units, Start Date, and End Date are optional source fields. The worker recalculates derived metrics from base values when possible and keeps divide-by-zero behavior explicit. |
| Import source | Monitoring imports reference a processed `amazon_ads_sp_search_term_report` upload and succeeded parse run in the same workspace/product. |
| Snapshot grain | One snapshot row per campaign/ad group/targeting/search-term/date-range row from the report. |
| Source row identity | DB-backed parser rows keep their persisted `source_row_id`. In-memory parser flows used by tests and local smoke checks generate a UUID fallback so normalization still produces auditable snapshots. |
| Metrics | Impressions, clicks, CTR, CPC, spend, sales, ACOS, ROAS, orders, units, and CVR are stored as normalized numeric values. |
| Amazon aliases | Known Amazon header variants such as `7 Day Total Orders (#)` are normalized to canonical metric keys before snapshot creation. Alias handling does not suppress risk warnings. |
| Import idempotency | Monitoring imports are unique by `workspace_id`, `product_id`, `upload_id`, and `report_type`. Duplicate import requests return the existing import and do not create duplicate rows. |
| Import message severity | Import health messages use `info`, `warning`, `error`, and `critical`. Amazon alias mapping is `info`; blank ACOS/ROAS with zero sales is normal and not a warning. |
| Product detection | Detected product groups come only from advertised ASIN/SKU or campaign-owned product columns. Customer Search Term ASINs are never used for product profile creation or linking. |
| Recommendation ownership | Deterministic rules create `recommendations`; Phase 1 does not use AI for final decisions. |
| Evidence storage | `recommendations.evidence_json` stores rule version, thresholds, normalized metrics, search-term performance, target performance, ad-group performance, campaign performance, report performance, and approval boundary flags. |
| Agent runs | `ai_runs` stores explanation-layer output only, scoped to workspace and product where available. |
| Human decision | Approve/reject creates `recommendation_decisions` and updates recommendation status. |
| Execution boundary | Approval means approved for manual action or later export; no live Amazon Ads mutation occurs. |
| Auditability | Import queueing, processing, recommendation evidence, decisions, and deterministic summaries must be traceable by workspace, actor, rule version, and input hash where applicable. |
| Local adapter behavior | SQLite repository adapters deserialize stored JSON text into structured API fields and write explicit `created_at`/`updated_at` values for append-only and workflow tables that depend on Postgres defaults in Supabase. |

## Batch 10 Monitoring RLS Status
`monitoring_imports`, `monitoring_snapshots`, `recommendations`, `recommendation_decisions`, and `ai_runs` have RLS enabled. Workspace members can read monitoring evidence and agent outputs. Backend/service-role operations create imports, snapshots, recommendations, and AI run rows. Recommendation decisions are limited to `owner`, `admin`, `analyst`, and `approver` in the API, with `viewer` read-only.

## Phase 3 Monitoring View Security
`token_usage_by_workspace` aggregates `ai_runs` by workspace, provider, and model for observability. Because it lives in the public schema and reads workspace-scoped AI run data, it must be created with `security_invoker = true` so `ai_runs` RLS policies apply to the querying role. It must not be recreated as a default/security-definer public view.

## Dashboard Performance Indexes
The dashboard summary endpoint is backed by compound indexes for common workspace-scoped reads: product list by created time, upload list/counts by workspace and status, recommendation queue by workspace/product/status/priority, and agent runs by workspace/product/agent. These indexes are additive migrations and do not change RLS or approval behavior.

## Batch 3 Upload Constraints
| Requirement | Decision |
| --- | --- |
| Source type | `competitor_keyword_research` and `amazon_ads_sp_search_term_report`. |
| File types | `.csv`, `.xls`, `.xlsx`. |
| MIME types | `text/csv`, `application/vnd.ms-excel`, `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`. |
| Size limit | 25 MB. |
| Storage path | `/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/{sanitized_filename}`. |
| Uniqueness | `storage_path` unique; `idempotency_key` unique per workspace where present. |
| Product/workspace integrity | `uploads(product_id, workspace_id)` has a composite foreign key to `product_profiles(id, workspace_id)`, so direct DB writes cannot attach uploads to products in another workspace. |
| Parsing | Not implemented in Batch 3. Batch 4.1 parser validation reuses the Batch 3 accepted extension and MIME type lists and fails closed when either value is unsupported. |

## Immutability And Versioning
| Object | Rule |
| --- | --- |
| Approved keyword sets | Immutable snapshots after approval. Changes create a new set/version. |
| Campaign plans | Versioned. Regeneration creates a new version and supersedes prior draft where applicable. |
| Bulk exports | Immutable once generated. Regeneration creates a new export record. |
| Recommendations | Cannot be overwritten after approval or rejection. New evidence creates a new recommendation or supersedes pending one. |
| Audit logs | Append-only. |

## Storage Path Convention
| File type | Path |
| --- | --- |
| Raw uploads | `/workspaces/{workspace_id}/products/{product_id}/uploads/{upload_id}/raw/{filename}` |
| Generated exports | `/workspaces/{workspace_id}/products/{product_id}/exports/{export_id}/{filename}` |

## Retention
| Data | Retention |
| --- | --- |
| Raw uploads | Retained while workspace is active unless legal deletion is required. |
| Audit logs | Retained indefinitely unless legal deletion is required. |
| Generated exports | Retained at least 12 months. |

## Relationship Rules
- Every workspace-owned table includes `workspace_id`.
- Approval and audit rows are append-only.
- Generated campaign and export rows reference immutable approved keyword sets or plan versions.
- Row-level security must enforce workspace membership.
