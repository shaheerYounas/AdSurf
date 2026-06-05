# AdSurf Amazon Ads — Complete Logic Audit Report

**Date:** 2026-06-05  
**Scope:** Full architecture inspection, business logic audit, bug fixes, test creation, backend safeguards  
**Auditor:** Claude Sonnet 4.6 (via Claude Code)

---

## 1. Data Flow Map

```
CSV Upload (Amazon SP Search Term Report)
    │
    ▼
upload_repository.create_initialized()
    │  UploadInitRequest validated (source_type whitelist enforced)
    ▼
LocalFakeStorageService.write_upload_object()
    │
    ▼
UploadProcessingWorker.process_one()
    │  upload_parsing.py → ParsedUploadRow[] (row_data_json dict)
    │  SHA-256 file hash stored (duplicate detection)
    ▼
MonitoringWorker.process_one()
    │
    ├─ normalize_sp_search_term_rows()
    │    SP column alias resolution → MonitoringSnapshot[]
    │    Multi-product detection warning (Advertised ASIN)
    │    Data quality flags: clicks>impressions, orders>clicks,
    │    spend-without-clicks, orders-without-sales, ACOS/ROAS mismatch
    │
    ├─ build_recommendations()
    │    12-rule deterministic decision tree per snapshot:
    │    [1] data_quality_review  (critical → blocks all other rules)
    │    [2] pause_review         (high spend, 0 orders)
    │    [3] add_negative_phrase  (broad waste, 0 orders)
    │    [4] add_negative_exact   (exact/phrase waste, 0 orders)
    │    [5] decrease_bid         (ACOS > 125% target, enough data)
    │    [6] budget_review        (budget_pressure signal)
    │    [7] move_to_exact        (efficient broad term, 2+ orders)
    │    [8] increase_bid         (low impressions, strong CVR, ACOS < 90% target)
    │    [9] watch_lock           (efficient, wait-and-see)
    │    [10] watch_lock          (10+ clicks, 0 orders)
    │    [11] watch_lock          (under_tested signal)
    │    [12] keep_running        (default fallback)
    │
    └─ Recommendation[] saved to DB (status = pending_approval)
         ← NEVER auto-executes Amazon changes
         ← ALL require human decision before export

User Review (Human Approval Gate)
    │
    ├─ GET /recommendations → pending list
    ├─ POST /recommendations/{id}/approve (analyst/approver role only, note required)
    └─ POST /recommendations/{id}/reject  (immutable after first decision — 409 on retry)

Bulk Export (Amazon-Ready)
    │
    ├─ validate_export_readiness() — safety gate
    │    • All recs must be approved (blocks if any pending)
    │    • Stale recs from older import → warning
    │    • Contradictory bid changes on same entity → blocks
    │    • Negative keywords missing search_term → blocks
    │    • WATCH/KEEP types in export → warning
    │
    └─ generate_bulk_sheet()
         Amazon 24-column bulk CSV
         Record Types: Keyword, Negative Keyword, Product Targeting, Campaign
         Operations: Update (bid/pause changes), Create (new negatives/harvested keywords)
         WATCH_LOCK / WATCH_ONLY / KEEP_RUNNING → produce NO rows (Amazon rejects unknown ops)
```

---

## 2. Critical Bugs Found and Fixed

### Bug 1 — `recommended_bid`, `current_bid`, `change_percent`, `match_type` Never Populated
**File:** [monitoring_rules.py](apps/api/app/services/monitoring_rules.py)  
**Severity:** High — bid CSV rows were silently empty  
**Root Cause:** `build_recommendations()` created `Recommendation` schema objects but never extracted bid values from `proposed_action_json` onto the schema's first-class fields.  
**Fix:** Extract `recommended_bid`, `current_bid`, `change_percent`, `match_type` from `proposed_action_json` and set them on the `Recommendation` object at creation time.

### Bug 2 — Bulk Export "Keyword Bid" Column Always Empty After DB Round-Trip
**File:** [bulk_export_generator.py](apps/api/app/services/bulk_export_generator.py)  
**Severity:** High — exported CSVs had blank bid values, making them invalid for Amazon  
**Root Cause:** `_recommendation_to_bulk_rows()` read `rec.recommended_bid` directly. Since these schema-only fields are not DB columns, they're always `None` after reconstruction from the database.  
**Fix:** Added `_decimal_from_action(rec, "recommended_bid")` fallback that reads from `proposed_action_json`. Same fix applied to Product Targeting Bid and MOVE_TO_EXACT harvest bid.

### Bug 3 — Summary Bid Counts Always Zero
**File:** [bulk_export_generator.py](apps/api/app/services/bulk_export_generator.py)  
**Severity:** Medium — export summary showed 0 bid changes even when CSV contained many  
**Root Cause:** Summary code counted rows by looking for `action_counts.get("Update Bid", 0)` but all bid operations use `"Operation": "Update"` (required by Amazon's format) — "Update Bid" never appears.  
**Fix:** Count by `recommendation_type.value` directly instead of by operation string.

### Bug 4 — WATCH_LOCK Rows Appeared in Bulk CSV
**File:** [bulk_export_generator.py](apps/api/app/services/bulk_export_generator.py)  
**Severity:** High — Amazon bulk importer rejects unknown Operation values  
**Root Cause:** `WATCH_LOCK` and `WATCH_ONLY` types produced rows with `"Operation": "No Change - Review Only"` which is not a valid Amazon bulk sheet operation.  
**Fix:** `WATCH_LOCK`, `WATCH_ONLY`, and `KEEP_RUNNING` now produce no CSV rows (informational only).

### Bug 5 — `generate_approval_queue_summary` High-Risk Count Always Zero
**File:** [bulk_export_generator.py](apps/api/app/services/bulk_export_generator.py)  
**Severity:** Low — dashboard summary showed incorrect risk counts  
**Root Cause:** Code filtered on `r.risk_level in {"critical", "high"}` but `risk_level` is always `None`; the priority field (`r.priority`) is what's populated.  
**Fix:** Changed to `r.priority in {"critical", "high"}`.

---

## 3. High-Risk Logic Gaps (No Bugs, But Need Awareness)

| Area | Risk | Notes |
|---|---|---|
| `recommended_bid` not in DB | High | Bid values only survive via `proposed_action_json`. Schema fields are ephemeral. |
| No export endpoint in API | Medium | `generate_bulk_sheet()` exists as a service but there is no `/export` route — callers must reconstruct Recommendation objects from API JSON before calling it. |
| `sales_with_blank_acos` triggers DQR | Medium | Any row with `sales > 0` and missing ACOS column will get `DATA_QUALITY_REVIEW`. Real Amazon reports always provide ACOS with sales. |
| Monitoring worker processes one at a time | Low | `MonitoringWorker.process_one()` is single-threaded; no concurrency concern but slow for large imports. |
| SQLite WAL mode + 5-connection pool | Low | Acceptable for development. Production should use PostgreSQL. |

---

## 4. Metric Calculation Verification

All metric calculations verified correct via unit tests:

| Metric | Formula | Zero-Safety |
|---|---|---|
| ACOS | spend / sales | Returns `None` when sales = 0 |
| ROAS | sales / spend | Returns `None` when spend = 0 |
| CPC | spend / clicks | Returns `None` when clicks = 0 |
| CTR | clicks / impressions | Returns `None` when impressions = 0 |
| CVR | orders / clicks | Returns `None` when clicks = 0 |
| CPA | spend / orders | Returns `None` when orders = 0 |

All use `_safe_divide()` which returns `None` instead of crashing on division by zero. `Decimal` arithmetic used throughout for financial precision.

---

## 5. Business Rule Verification

| Rule | Verified | Notes |
|---|---|---|
| All recs start as `pending_approval` | ✅ | Enforced in `build_recommendations()` |
| `executes_live_amazon_change: False` | ✅ | Hard-coded in every `_action()` call |
| `requires_human_approval: True` | ✅ | Hard-coded in every `_action()` call |
| Viewer role cannot approve | ✅ | 403 enforced in monitoring API |
| Approval note required | ✅ | 422 on empty note |
| Double-decision returns 409 | ✅ | Immutability enforced in `decide_recommendation()` |
| Bid increase bounded at +30% | ✅ | `MAX_BID_INCREASE_MULTIPLIER = 1.30` |
| Bid decrease floored at -40% | ✅ | `MAX_BID_DECREASE_MULTIPLIER = 0.60` |
| Minimum bid = $0.10 | ✅ | `MIN_BID = Decimal("0.1000")` |
| ASIN search terms not negated | ✅ | `_is_asin()` check in `_should_add_negative_exact()` |
| Data quality review fires first | ✅ | First check in 12-rule decision tree |

---

## 6. Files Changed

### Production Code
| File | Change |
|---|---|
| [apps/api/app/services/monitoring_rules.py](apps/api/app/services/monitoring_rules.py) | Extract bid fields from `proposed_action_json` onto schema objects in `build_recommendations()` |
| [apps/api/app/services/bulk_export_generator.py](apps/api/app/services/bulk_export_generator.py) | 5 bug fixes (bid fallback, summary counts, WATCH_LOCK rows, high-risk count, `_before_value`/`_after_value`); added `validate_export_readiness()` safety gate; added `_ACTIONABLE_TYPES` constant |

### Tests Added
| File | Coverage |
|---|---|
| [tests/unit/test_monitoring_metrics.py](tests/unit/test_monitoring_metrics.py) | 41 tests — all metric calculations, condition signals, rollup aggregation, share metrics, zero/None edge cases |
| [tests/unit/test_recommendation_edge_cases.py](tests/unit/test_recommendation_edge_cases.py) | 43 tests — all 12 rule branches, bid bounds, ASIN exclusion, status invariants |
| [tests/unit/test_bulk_export_generator.py](tests/unit/test_bulk_export_generator.py) | 32 tests — every recommendation type → CSV row, WATCH/KEEP produce no rows, summary counts |
| [tests/unit/test_export_validation.py](tests/unit/test_export_validation.py) | 10 tests — all 5 safety guards in `validate_export_readiness()` |
| [tests/unit/test_fixtures_parsing.py](tests/unit/test_fixtures_parsing.py) | 14 tests — end-to-end fixture parsing for clean/edge/dirty/multi-product CSVs |
| [tests/integration/test_full_pipeline_approve_export.py](tests/integration/test_full_pipeline_approve_export.py) | 8 tests — full create→upload→parse→recommend→approve/reject→export pipeline |

### Test Fixtures Added
| File | Purpose |
|---|---|
| [tests/fixtures/sp_search_term_clean.csv](tests/fixtures/sp_search_term_clean.csv) | 11 realistic rows for "Posture Pro" product |
| [tests/fixtures/sp_search_term_edge_cases.csv](tests/fixtures/sp_search_term_edge_cases.csv) | ASIN search terms, duplicate terms across campaigns, zero-clicks, low-data rows |
| [tests/fixtures/sp_search_term_dirty.csv](tests/fixtures/sp_search_term_dirty.csv) | Data quality issues: clicks>impressions, orders>clicks, spend-without-clicks, blank term |
| [tests/fixtures/sp_search_term_multi_product.csv](tests/fixtures/sp_search_term_multi_product.csv) | Two products (B08AAAAAA1, B08BBBBBBB) triggering MULTI_PRODUCT_REPORT_DETECTED |

### Infrastructure
| File | Change |
|---|---|
| [tests/conftest.py](tests/conftest.py) | Added repo root to `sys.path` so tests run without `PYTHONPATH` env var |

---

## 7. Test Coverage Summary

**Before this audit:** 5 unit tests for monitoring rules only.

**After this audit:**

```
Tests added:   148
Tests total:   527 passing, 20 pre-existing failures (all unrelated: Postgres migrations,
               TypeScript file checks, navigation link tests)
```

### How to Run Tests

```powershell
# From repo root: apps/api/
cd apps/api

# All new audit tests (no PYTHONPATH needed after conftest.py fix)
python -m pytest ../../tests/unit/test_monitoring_metrics.py `
                 ../../tests/unit/test_recommendation_edge_cases.py `
                 ../../tests/unit/test_bulk_export_generator.py `
                 ../../tests/unit/test_export_validation.py `
                 ../../tests/unit/test_fixtures_parsing.py `
                 ../../tests/integration/test_full_pipeline_approve_export.py `
                 -v

# Full test suite
python -m pytest ../../tests/ -q
```

---

## 8. Export Safety Gates (`validate_export_readiness`)

Added to [bulk_export_generator.py](apps/api/app/services/bulk_export_generator.py):

| Guard | Type | Behavior |
|---|---|---|
| Non-approved recommendation in set | **BLOCKS** | Export must not proceed |
| Recs from older import than current latest | Warning | User should re-run monitoring first |
| Contradictory bid (increase + decrease on same entity) | **BLOCKS** | Would confuse Amazon's bulk importer |
| Negative keyword rec missing `customer_search_term` | **BLOCKS** | Would create blank negative keyword |
| WATCH_LOCK / KEEP_RUNNING recs in export set | Warning | These produce no CSV rows |
| Pause + bid change on same entity | Warning | Conflicting intent, user should review |

Return shape:
```python
{
    "is_safe": bool,
    "blocking_errors": list[str],
    "warnings": list[str],
    "actionable_count": int,    # recs that produce CSV rows
    "total_count": int,
}
```

---

## 9. What Still Needs Manual Review

1. **No `/export` API endpoint exists.** `generate_bulk_sheet()` is a service function but cannot be called directly from the frontend via an HTTP route. An export endpoint should be added to `apps/api/app/api/v1/monitoring.py` that calls `validate_export_readiness()` first, then `generate_bulk_sheet()`.

2. **`recommended_bid` is not persisted in the DB.** The DB schema (`recommendations` table) has no `recommended_bid`, `current_bid`, `change_percent` columns. These are schema-only fields populated from `proposed_action_json` on read. This creates a fragile dependency on JSON field names. Consider adding explicit columns in a future migration.

3. **Production database (PostgreSQL) not tested.** All tests run against in-memory SQLite. The application targets PostgreSQL (based on `test_migrations.py`). The 15 migration tests fail because migration files reference Postgres-specific SQL.

4. **AI augmentation path untested.** The dual-path architecture (deterministic rules + DeepSeek/OpenAI AI augmentation) is tested only in `deterministic_fallback` mode. Integration with a live AI provider is not covered by automated tests.

5. **SHA-256 duplicate detection** — The file hash deduplication mechanism prevents re-processing the same file but does not prevent processing two different files that represent the same date range. A date-range overlap check would be safer.

---

## 10. Key Invariants That Must Never Break

These are the non-negotiable business rules embedded in the system:

```
1. executes_live_amazon_change IS ALWAYS False in proposed_action_json
2. requires_human_approval IS ALWAYS True in proposed_action_json
3. Recommendations start as pending_approval — no other initial state is valid
4. Once decided (approved/rejected), a recommendation is IMMUTABLE (409 on retry)
5. Only 'analyst', 'approver' roles can approve/reject (viewer cannot)
6. Approval note is required — empty note returns 422
7. WATCH_LOCK / KEEP_RUNNING produce ZERO CSV rows
8. Negative keyword recs MUST have customer_search_term before export
9. Contradictory bid changes (increase + decrease) on same entity MUST block export
10. ASIN search terms (B0XXXXXXXXX) are never negated
```
