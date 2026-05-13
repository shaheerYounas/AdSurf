# Database Schema

## Table Overview
| Table | Purpose | Key relationships |
| --- | --- | --- |
| tenants | Workspace for seller or agency | Has users, profiles, files, plans. |
| tenant_members | User membership and role | Links auth user to tenant. |
| product_profiles | Advertised product settings | Owns uploads and plans. |
| file_uploads | Original CSV/XLSX/report files | Source for parsed rows and snapshots. |
| parsed_file_rows | Normalized uploaded rows | Links to file upload. |
| column_mappings | User/AI mapping decisions | Links upload to canonical columns. |
| keyword_candidates | Candidate search terms | Scored and reviewed. |
| relevance_scores | Rule result per candidate | Links inputs and rule version. |
| approved_keywords | Frozen approved keyword set | Used by campaign plans. |
| campaign_plans | Draft generated campaign plan | Requires approval for export. |
| campaign_groups | Hero or keyword batches | Contains generated campaigns. |
| bulk_exports | Generated Amazon bulk sheets | Links approved plan and storage file. |
| monitoring_snapshots | Campaign performance metrics | Feeds recommendations. |
| recommendations | Rule-generated optimization proposals | Requires approval/rejection. |
| approvals | Human approval records | Links actor, object, decision. |
| audit_logs | Immutable event log | Records decisions and actor context. |
| ai_runs | AI calls and structured outputs | Stores provider/model/schema metadata. |
| worker_jobs | Background job queue records | Tracks processing state and retries. |

## Core Columns
| Table | Required columns |
| --- | --- |
| tenants | id, name, type, created_at, updated_at |
| tenant_members | id, tenant_id, user_id, role, status, created_at |
| product_profiles | id, tenant_id, asin, marketplace, product_name, default_daily_budget, default_bid, status |
| file_uploads | id, tenant_id, product_profile_id, file_type, storage_path, status, uploaded_by |
| keyword_candidates | id, tenant_id, product_profile_id, upload_id, search_term, normalized_term, search_volume, suggested_bid, status |
| relevance_scores | id, keyword_candidate_id, score, rule_version, competitor_rank_inputs_json, rejection_reason |
| campaign_plans | id, tenant_id, product_profile_id, status, rule_version, created_by, approved_at |
| campaign_groups | id, campaign_plan_id, group_type, group_index, match_type_set, keywords_json |
| bulk_exports | id, tenant_id, campaign_plan_id, storage_path, status, approved_by, approved_at |
| recommendations | id, tenant_id, product_profile_id, campaign_plan_id, type, status, rule_name, input_metrics_json, proposed_action_json |
| approvals | id, tenant_id, object_type, object_id, decision, actor_user_id, notes, created_at |
| audit_logs | id, tenant_id, actor_user_id, event_type, object_type, object_id, metadata_json, created_at |
| ai_runs | id, tenant_id, agent_name, provider, model, input_hash, output_json, status, created_at |
| worker_jobs | id, tenant_id, job_type, status, payload_json, attempts, last_error, created_at, updated_at |

## Relationship Rules
- Every tenant-owned table includes `tenant_id`.
- Approval and audit rows are append-only.
- Generated campaign and export rows reference immutable approved keyword sets or plan versions.
- Row-level security must enforce tenant membership.

