# Marketing Project Plan — Gap Analysis

Generated against: `Marketing Project Detail Plan.txt`  
Codebase inspected: `apps/api/app/services/` (keyword_scoring, campaign_generation, monitoring_rules, monitoring_worker, upload_parser, keyword_review), `apps/api/app/api/v1/` (uploads, campaigns), HTML frontend components  
Date: 2026-05-29

---

## Phase 1: Automated Market Research & Data Processing

### 1. Data Collection & Cleaning

| Attribute | Value |
|-----------|-------|
| **Requirement** | Upload raw CSV/XLSX competitor export containing top 10 competitors |
| **Found in app?** | **Yes** |
| **Evidence from code** | `apps/api/app/services/upload_parser.py` — `UploadParser` class parses CSV, XLSX, and XLS files. `apps/api/app/api/v1/uploads.py` — multipart report upload endpoint, init/confirm/put-object flow, signed URL support. |
| **Missing parts** | None. File ingestion is complete. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Auto-delete all irrelevant columns; keep only Search Volume and Organic Rank |
| **Found in app?** | **Partial** |
| **Evidence from code** | `apps/api/app/services/keyword_scoring.py` — `_score_row()` extracts `search_term`, `search_volume`, and `competitor_rank_columns` from the mapping. Columns are NOT deleted. The system parses ALL file columns into structured rows; the user must manually map which columns are `search_term`, `search_volume`, and `competitor_rank_columns` via the column mapping API (`/column-mappings`). |
| **Missing parts** | (a) No automatic column detection for search volume and organic rank columns. (b) The system stores all parsed columns and relies on the mapping step to select relevant ones. The plan's "auto-delete" behavior (removing columns automatically) is not implemented. The mapping step requires human approval. |
| **Priority** | Medium |
| **Suggested steps** | 1. Add `search_volume` and `organic_rank` column auto-discovery to `ColumnDiscoveryService` (`column_discovery.py`). 2. Add a "clean" step before scoring that projects only mapped columns. 3. Surface the auto-detected columns in the column profile UI to reduce manual mapping effort. |

---

### 2. The Relevance Scoring Engine

| Attribute | Value |
|-----------|-------|
| **Requirement** | Create a "Relevance Score" column (0–10) |
| **Found in app?** | **Yes** |
| **Evidence from code** | `apps/api/app/services/keyword_scoring.py` lines 134–155 — `relevance_score` starts at 0, increments by 1 for each competitor column where `rank < 15`. Max score equals number of competitor rank columns (up to 10 per plan spec). |
| **Missing parts** | None. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | The Rule: count how many of top 10 competitors rank in top 14 spots (rank < 15) |
| **Found in app?** | **Yes** |
| **Evidence from code** | `keyword_scoring.py` line 152: `elif rank < 15:` — increments `relevance_score` and sets `counts_for_relevance = True`. |
| **Missing parts** | None. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Auto-delete search terms scoring 0, 1, or 2 |
| **Found in app?** | **Partial** |
| **Evidence from code** | `keyword_scoring.py` line 170: `status = KeywordCandidateStatus.APPROVED if relevance_score >= 3 else KeywordCandidateStatus.REJECTED`. Terms scoring 0–2 are marked REJECTED with reason `relevance_score_X_below_threshold`. The plan says "delete" — the app marks them as rejected (soft-delete, not hard-delete). |
| **Missing parts** | The plan specifies "automatically deletes" — the app retains rejected candidates for review/override. This is actually better for transparency (AGENTS.md mandates auditability), but the plan's expectation of deletion differs. Consider adding a UI filter that hides rejected by default to match the "auto-delete" user experience. |
| **Priority** | Low (behavioral difference, not a gap; rejected filter serves the same purpose) |
| **Suggested steps** | 1. Default the scoring results list to show only APPROVED candidates. 2. Provide a filter toggle to show rejected/error rows. |

---

### 3. Automated Verification (The "Manual" Check)

| Attribute | Value |
|-----------|-------|
| **Requirement** | Automatically search Amazon for remaining terms |
| **Found in app?** | **No** |
| **Evidence from code** | No Amazon search/scraping or Product Advertising API integration exists. The `deepseek_client.py` and `ai_recommendation_brain.py` provide AI-powered analysis of uploaded performance reports, but do NOT query Amazon's live search results. No Amazon Ads API or PAAPI client is present. |
| **Missing parts** | Entire Amazon search verification step is absent — no HTTP client, no scraping, no PAAPI integration, no search result parsing. |
| **Priority** | **High** |
| **Suggested steps** | 1. Evaluate whether to use Amazon PAAPI (Product Advertising API 5.0) `SearchItems` or scrape (not recommended for production). 2. Build a `CompetitorVerificationService` that takes approved keyword candidates, searches Amazon, parses top 10-15 organic results, and checks for presence of target competitors. 3. Add a verification status (`VERIFIED`, `UNVERIFIED`) to keyword candidates. 4. Integrate into the workflow after scoring but before approved-keyword-set creation. 5. Respect rate limits (PAAPI has 1 TPS default). |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Check top 10–15 results for 3–5 of your original competitors; mark "Approved" or discard |
| **Found in app?** | **No** |
| **Evidence from code** | No competitor list management exists. No concept of "original chosen competitors" in the database schema or product profile. |
| **Missing parts** | Requires a competitor list model (stored per product), a verification check endpoint, and integration with the keyword review pipeline. |
| **Priority** | **High** (depends on Amazon search integration) |
| **Suggested steps** | 1. Add competitor profiles to the product schema (ASIN/name list). 2. Implement verification logic: count how many product competitors appear in search results. 3. Threshold: >= 3 matches → mark VERIFIED; < 3 → mark UNVERIFIED (discarded). 4. Wire into the keyword review UI. |

---

## Phase 2: Automated Campaign Creation

### 1. The Naming Convention System

| Attribute | Value |
|-----------|-------|
| **Requirement** | Campaign naming: ProductName / AdType / Targeting / MatchType / Keyword/Group / Date |
| **Found in app?** | **Partial** |
| **Evidence from code** | `apps/api/app/services/campaign_generation.py` lines 157–159: `_campaign_name()` produces `"ProductName - G{group_index} - {MatchType}"`. The ad group name follows `"ProductName - G{group_index}"` (line 162–164). |
| **Missing parts** | The plan specifies 6 components: Product Name, Ad Type (SP), Targeting (Manual), Match Type, Keyword/Group, Date. The current implementation only includes Product Name, Group index, and Match Type. Missing: Ad Type prefix (SP), Targeting type (Manual), Date suffix (May 11). |
| **Priority** | Medium |
| **Suggested steps** | 1. Update `_campaign_name()` to include static prefix `SP - Manual -` and a date suffix from `datetime.now(UTC)`. 2. Format: `"SP - Manual - {product_name} - G{group_index} - {match_type} - {date_str}"`. 3. For the hero campaign, use keyword name instead of group number: `"SP - Manual - {product_name} - {hero_keyword} - Exact - {date_str}"`. 4. Update `build_bulk_export_rows()` test fixtures to match new names. |

---

### 2. Building the "Hero" Campaign

| Attribute | Value |
|-----------|-------|
| **Requirement** | Isolate most important search term into dedicated 1:1:1 campaign |
| **Found in app?** | **Yes** |
| **Evidence from code** | `campaign_generation.py` lines 18–35: `hero_item = sorted_items[0]` (sorted by relevance_score then search_volume descending). Creates campaign with group_index=0, match_type="Hero", and exactly one keyword. Structure is 1 Campaign → 1 Ad Group → 1 Keyword in the bulk export output. |
| **Missing parts** | None. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Budget: $10 automatically; Bid: $1.00 or Amazon's suggested bid |
| **Found in app?** | **Partial** |
| **Evidence from code** | `campaign_generation.py` line 9: `DEFAULT_DAILY_BUDGET = Decimal("10.0000")` and line 10: `DEFAULT_BID = Decimal("1.0000")`. The product profile's `default_budget` and `default_bid` fields take priority if set. |
| **Missing parts** | (a) Amazon's suggested bid is NOT pulled — only the hardcoded $1.00 or product profile's `default_bid` is used. The plan says "or pulls Amazon's suggested estimated bid." (b) No Amazon Ads API integration exists to retrieve suggested bid. |
| **Priority** | Low for MVP (hardcoded $1.00 is acceptable); Medium for full version |
| **Suggested steps** | 1. Later integration: Amazon Ads API `getKeywordBidRecommendations` or `getAdGroupBidRecommendations`. 2. For now, document that the bid is fixed at $1.00 unless overridden in product profile. |

---

### 3. Building the Grouped Campaigns

| Attribute | Value |
|-----------|-------|
| **Requirement** | Divide remaining approved terms into batches of 5–7 |
| **Found in app?** | **Yes** |
| **Evidence from code** | `campaign_generation.py` lines 141–146: `_keyword_batches()` batches by 7. If items ≤ 7, returns single batch. Otherwise splits into chunks of 7. |
| **Missing parts** | The plan says "5 to 7 words" — the code always uses 7. A configurable batch size would better match the plan's flexibility. |
| **Priority** | Low |
| **Suggested steps** | 1. Add a `keyword_batch_size` field to the product profile (default 7, min 5, max 7). 2. Pass it to `_keyword_batches()`. |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Create Exact, Phrase, and Broad match campaigns for each batch |
| **Found in app?** | **Yes** |
| **Evidence from code** | `campaign_generation.py` lines 40–49: loops `("Exact", "Phrase", "Broad")` for each batch, creating one campaign per match type. Each campaign gets `$10` daily budget and all keywords from the batch. |
| **Missing parts** | None. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Negative Exact in Phrase campaigns (to prevent stealing traffic from Exact) |
| **Found in app?** | **Yes** |
| **Evidence from code** | `campaign_generation.py` lines 149–154: `_negative_keywords(match_type="Phrase")` returns `Negative Exact` entries for every keyword in the batch with rule `"phrase_exact_overlap_prevention"`. |
| **Missing parts** | None. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Negative Phrase in Broad campaigns (to force Broad to hunt for new terms) |
| **Found in app?** | **Yes** |
| **Evidence from code** | `campaign_generation.py` line 153: `match_type="Broad"` returns `Negative Phrase` entries with rule `"broad_phrase_overlap_prevention"`. |
| **Missing parts** | None. |
| **Priority** | Low (feature complete) |
| **Suggested steps** | N/A |

---

## Phase 3: The 14-Day Automated Monitoring System

### 1. The First 7 Days (Budget Consumption Check)

| Attribute | Value |
|-----------|-------|
| **Requirement** | Monitor $10 daily budget for every campaign |
| **Found in app?** | **Partial** |
| **Evidence from code** | `apps/api/app/services/monitoring_rules.py` lines 218–322: `_recommendation_for()` evaluates spend, budget, and performance at the search-term level. The `condition_signals()` function in `monitoring_metrics.py` provides budget pressure signals. However, this is per-snapshot analysis, not time-series budget tracking over 7 consecutive days. |
| **Missing parts** | (a) No daily budget consumption tracking — monitoring_metrics.py computes rollup aggregates per import, not per-day time series. (b) No concept of "7 consecutive days" or daily budget check cadence. (c) The current system imports a single snapshot file, not streaming daily data. |
| **Priority** | **High** |
| **Suggested steps** | 1. Add a `daily_budget_consumption` table that tracks per-campaign spend by date. 2. Implement a daily import workflow (scheduled job) that pulls performance reports every 24 hours. 3. Add a 7-day rolling window check in `monitoring_rules.py` that triggers if cumulative daily budget consumption < $70 (7 × $10) over the window. 4. Create a `budget_consumption_low` recommendation type. |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | Auto-increase bid by 10% daily until budget is consumed |
| **Found in app?** | **Partial** |
| **Evidence from code** | `monitoring_rules.py` lines 298–306: `INCREASE_BID` recommendation with `bid_multiplier = 1.10` triggers on `low_traffic_low_spend` (impressions >= 10, clicks < 3, spend <= $5). Lines 307–315: also triggers on `strong_conversion_low_impressions` or `strong_converter`. |
| **Missing parts** | (a) The trigger condition does NOT match the plan's "budget not being fully consumed" logic — it's based on low impressions/clicks/spend, not on daily budget consumption rate. (b) No daily cumulative increase — it's a one-time recommendation per import, not a "repeat daily until budget is consumed" loop. (c) The plan requires 10% increase repeating daily — this needs temporal state tracking. |
| **Priority** | **High** |
| **Suggested steps** | 1. Change the `INCREASE_BID` trigger to check: `daily_spend < daily_budget * 0.80` (budget not being consumed). 2. Add a `previous_bid` field to track the last applied bid. 3. Implement repetitive daily recommendation: each day the budget is under-consumed, suggest another 10% increase on top of the previously suggested bid. 4. Add a cap (e.g., max 5 consecutive increases = 1.61× original bid). |

---

### 2. Day 7 Evaluation (The Profitability Check)

| Attribute | Value |
|-----------|-------|
| **Requirement** | After exactly 7 days, calculate ACOS |
| **Found in app?** | **No** |
| **Evidence from code** | No 7-day checkpoint logic exists. `monitoring_rules.py` evaluates every snapshot on import, not on a fixed 7-day cycle. `monitoring_worker.py` processes one import at a time with no date-accumulation logic. |
| **Missing parts** | Entire 7-day evaluation cycle is absent. No date-window aggregation, no 7-day ACOS calculation, no temporal checkpoint system. |
| **Priority** | **High** |
| **Suggested steps** | 1. Build a `CampaignDay7Checkpoint` model that aggregates metrics for each campaign over its first 7 days. 2. Implement a scheduled job that runs on day 7 for each campaign, calculating cumulative ACOS = total_spend_7d / total_sales_7d. 3. Create a `day_7_acos_evaluation` recommendation type with the ACOS < 50% check. |

---

| Attribute | Value |
|-----------|-------|
| **Requirement** | If ACOS < 50%, lock campaign — make zero changes for Days 8–14 |
| **Found in app?** | **No** |
| **Evidence from code** | No "lock" concept exists. The `WATCH_LOCK` recommendation type (`monitoring_rules.py` lines 282–297) is triggered by `acos <= target_acos * 0.80` with 2+ orders — a different condition entirely. No campaign freeze, no 14-day window, no 50% ACOS threshold check. |
| **Missing parts** | (a) 50% ACOS threshold is a fixed business rule not present in the code (code uses `target_acos * 1.25` for decrease and `target_acos * 0.80` for watch lock). (b) No campaign lock/freeze state. (c) No Days 8–14 monitoring window that overrides normal recommendation generation. |
| **Priority** | **High** |
| **Suggested steps** | 1. Add a `campaign_lock` status with `locked_until` date to the campaign or monitoring state. 2. Implement the Day 7 check: if ACOS_7d < 50%, set `campaign_lock` with `locked_until = today + 7 days`. 3. Modify `_recommendation_for()` to skip locked campaigns — return `KEEP_RUNNING` with `reason = "locked_after_day7_acos_check"` during the lock period. 4. After Day 14, unlock and resume normal monitoring. |

---

## Summary

### Feature Completeness by Phase

| Phase | Complete | Partial | Missing | Overall |
|-------|----------|---------|----------|---------|
| Phase 1: Research & Processing | 3 | 2 | 2 | ~50% — core scoring works, Amazon verification not built |
| Phase 2: Campaign Creation | 6 | 2 | 0 | ~75% — campaign structure solid, naming convention needs polish |
| Phase 3: 14-Day Monitoring | 0 | 2 | 4 | ~15% — rule-based recommendations exist, but 7/14-day cycle not implemented |

### Critical Gaps (Priority: High)

1. **Amazon search cross-check (automated verification)** — No PAAPI or scraping integration. Phase 1 is incomplete without it.
2. **7-day budget consumption tracking** — No daily time-series data or 7-day rolling window logic.
3. **Day 7 ACOS evaluation + campaign lock** — No checkpoint system, no 50% ACOS threshold, no lock mechanism.
4. **Repetitive 10% bid increase loop** — Bid increases are one-time, not daily-cumulative.

### What Exists and Works Well

- File upload, parsing (CSV/XLSX/XLS), and processing pipeline
- Relevance scoring engine (0–10, rank < 15 rule)
- Keyword review with overrides, approved keyword sets
- Campaign plan generation: hero + grouped (Exact/Phrase/Broad) with $10/$1.00 defaults
- Negative keyword overlap prevention (Negative Exact in Phrase, Negative Phrase in Broad)
- Bulk CSV export with Campaign/Ad Group/Keyword/Negative rows
- Deterministic monitoring rules (11 recommendation types with ACOS, spend, clicks thresholds)
- Human approval requirement on all recommendations
- Agent control center UI with workflow canvas

### Alignment with AGENTS.md Principles

The existing codebase respects the AGENTS.md prime directives:
- ✅ No live Amazon Ads API execution — all recommendations require human approval
- ✅ Deterministic decision rules — monitoring_rules.py uses explicit thresholds, not free-form AI
- ✅ Audit logging — every action records workspace, actor, entity, and details
- ✅ Workspace isolation — all queries are workspace-scoped
- ✅ MVP restraint — bulk sheet export workflows exist before API automation

The key gaps (Amazon search, 14-day monitoring) represent the natural next milestones per the product roadmap described in the plan document.