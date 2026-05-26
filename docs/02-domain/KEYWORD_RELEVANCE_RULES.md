# Keyword Relevance Rules

## Definition
Relevance Score equals `count(top_10_competitors where organic_rank < 15)`.

Batch 6 calculates Relevance Score deterministically from an approved manual column mapping snapshot that identifies `search_term`, `search_volume`, and 1-10 competitor rank columns. Batch 7 adds manual keyword review, override reasons, and immutable approved keyword set snapshots. It does not use AI, semantic relevance judgment, Amazon verification, campaign generation, exports, monitoring, recommendations, or Amazon Ads API execution.

## Required Input Shape
| Field | Required | Notes |
| --- | --- | --- |
| search_term | Yes | Trimmed search term. Duplicate terms are preserved as separate candidates in Batch 6. |
| competitor_rank_1..10 | Yes for scoring | Mapped organic rank values. MVP accepts 1-10 mapped rank columns. |
| search_volume | Yes | Parsed as non-negative numeric data. |
| suggested_bid | Optional | Used for campaign bid defaulting. |

## Score Outcome
| Score | Status | Reason |
| --- | --- | --- |
| 0 | Rejected | No top competitors rank organically under 15. |
| 1 | Rejected | Weak competitor presence. |
| 2 | Rejected | Below launch relevance threshold. |
| 3-10 | Approved candidate | Eligible for customer review and campaign planning. |

## Row Validation
| Condition | Batch 6 behavior |
| --- | --- |
| Missing or blank `search_term` | Store row as `error` with `missing_search_term`. |
| Invalid or negative `search_volume` | Store row as `error` with `invalid_search_volume`. |
| Blank competitor rank | Treat as not ranking and do not count. |
| Non-numeric competitor rank text | Treat as not ranking and store deterministic warning metadata in `competitor_rank_values_json`. |
| Competitor rank `<= 0` | Store row as `error` with `invalid_competitor_rank`. |
| Empty row | Store row as `error` with `empty_row`. |
| Duplicate search term | Preserve as a separate candidate; no dedupe in Batch 6. |

## API And Idempotency
Scoring is triggered from an approved mapping with `POST /v1/workspaces/{workspace_id}/column-mappings/{mapping_id}/score` and requires `Idempotency-Key`. Replaying the same key for the same mapping returns the original scoring run. Reusing the key for another mapping returns `409`.

## Batch 7 Keyword Review
Effective status is deterministic:

| Condition | Effective status |
| --- | --- |
| No override exists | `keyword_candidates.scoring_status` |
| Override exists | `keyword_candidate_overrides.new_status` |

Users with `owner`, `admin`, or `analyst` role can override scored candidates from `approved` to `rejected` or from `rejected` to `approved`. Override reasons are required and trimmed; blank or whitespace-only reasons are rejected. Candidates with `scoring_status = error` cannot be overridden or included in approved keyword sets in the MVP.

Approved keyword sets are locked snapshots created from all candidates whose effective status is `approved` at creation time. Snapshot items store the search term, search volume, relevance score, original scoring status, final approved status, and override id when applicable. Later overrides do not mutate existing snapshots.

Approved keyword sets are the source of truth for future campaign generation. Campaign generation is not implemented in Batch 7.

## Tests Required
- Score counts only organic ranks under 15.
- Rank 15 does not count.
- Missing competitor rank values are treated as not counted and flagged.
- Scores 0, 1, and 2 are rejected.
- Scores 3 through 10 are eligible for approval.
- Approved mappings are required before scoring.
- Idempotent scoring replay does not duplicate audit events or candidates.
- Batch 6 creates no campaign generation side effects.
- Batch 7 override tests cover reason requirements, role checks, effective status, error-candidate denial, and duplicate override conflicts.
- Batch 7 approved keyword set tests cover effective approved inclusion, rejected/error exclusion, override inclusion/exclusion, zero-approved conflict, pagination, immutability after later overrides, cross-workspace denial, and audit events.
