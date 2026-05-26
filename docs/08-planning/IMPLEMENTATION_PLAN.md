# Implementation Plan

## Sequence
| Step | Work |
| --- | --- |
| 1 | In progress: scaffold Next.js, FastAPI, shared config, migrations, and test tooling. |
| 2 | In progress: implement database-backed product profiles, auth adapter boundary, workspace membership checks, and foundation RLS policies. |
| 3 | In progress: build and harden upload metadata records, signed upload initialization, confirmation, and `process_upload` job skeleton. |
| 4 | In progress: implement file-processing ingestion foundation and parsed row/error storage; column mapping and scoring remain later. |
| 5 | In progress: implement column discovery and manual column mapping snapshots; keyword scoring and review remain later. |
| 6 | In progress: implement deterministic keyword relevance scoring from approved manual mappings; campaign generation remains later. |
| 7 | In progress: implement keyword review, manual overrides with required reasons, and approved keyword set snapshots; campaign generation remains later. |
| 8 | In progress: implement campaign generation, negatives, and campaign plan review. |
| 9 | In progress: implement bulk sheet export and approval. |
| 10 | Implement monitoring imports and recommendation rules. |
| 11 | Harden audit logs, observability, deployment, and E2E tests. |

## Constraint
Each step updates docs when behavior diverges from this foundation.

## Batch 3 Boundary
Batch 3 stops at upload lifecycle metadata and queued jobs. File parsing, column mapping, keyword scoring, campaign generation, bulk export generation, monitoring, recommendations, and Amazon Ads API work remain Batch 4 or later.

## Batch 3.1 Cleanup
Batch 3.1 hardens upload/product workspace integrity, upload init idempotency identity comparison, confirm state transitions, and job/audit conflict behavior before Batch 4 begins.

## Batch 4 Boundary
Batch 4 claims `process_upload`, reads storage through an adapter, parses CSV/XLS/XLSX into raw JSON rows and parse errors, and updates statuses. It stops before AI agents, semantic column mapping, keyword scoring, relevance scoring, campaign generation, exports, monitoring, recommendations, or Amazon Ads API integration.

## Batch 4.1 Cleanup
Batch 4.1 is limited to parser and parse-storage hardening: composite parse run/row/error database integrity, extension plus MIME validation, and bounded XLSX row streaming with no formula execution. It does not start Batch 5 and does not implement AI agents, semantic column mapping, keyword scoring, relevance scoring, campaign generation, exports, monitoring, recommendations, or Amazon Ads API integration.

## Batch 5 Boundary
Batch 5 discovers parsed columns, stores deterministic column profiles, validates manual mappings for `search_term`, `search_volume`, and 1-10 `competitor_rank_columns`, and lets owner/admin/analyst approve a valid manual mapping snapshot. It does not implement AI agents, semantic AI column mapping, keyword scoring, relevance scoring, Amazon verification, campaign generation, bulk sheet export, monitoring, recommendations, or Amazon Ads API integration.

## Batch 6 Boundary
Batch 6 uses approved manual mappings to transform parsed rows into keyword candidates and calculate deterministic Relevance Score from competitor ranks. It rejects scores `0` through `2`, approves scores `3` through `10`, stores row-level scoring errors, and exposes scoring runs/candidate reads. It does not implement AI agents, semantic relevance judgment, Amazon verification, campaign generation, bulk sheet export, monitoring, recommendations, or Amazon Ads API integration.

## Batch 7 Boundary
Batch 7 lets users review scored keyword candidates, create manual approve/reject overrides with required reasons, and create locked approved keyword set snapshots from effective approved candidates. Approved keyword sets become the source of truth for a future campaign generation batch. Batch 7 does not implement AI agents, Amazon verification, campaign generation, bulk sheet export, monitoring, recommendations, or Amazon Ads API integration.

## Batch 8 Campaign Planning
Batch 8 consumes locked `approved_keyword_sets` and snapshot items only. It generates a Hero campaign from the highest relevance score with search-volume tie-break, then groups remaining approved keywords into Exact, Phrase, and Broad campaign structures. Phrase campaigns include Negative Exact rows and Broad campaigns include Negative Phrase rows for review. Campaign plans require explicit approval with a note before export.

## Batch 9 Bulk Export
Batch 9 generates CSV bulk sheet rows from approved campaign plans only. Export generation requires a separate explicit approval note, writes an approved export record, stores the CSV through the configured storage adapter, and audits the approval. It does not execute Amazon Ads API changes.
