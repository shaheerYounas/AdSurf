# File Processing Architecture

## Responsibilities
| Component | Responsibility |
| --- | --- |
| API | Creates upload record, validates file type, creates worker job. |
| Storage | Stores original file in tenant-scoped private path. |
| File worker | Reads CSV/XLSX, normalizes rows, detects columns, writes parsed rows. |
| Column mapping agent | Suggests canonical mappings with confidence and reasons. |
| User | Reviews low-confidence mappings before scoring. |

## Canonical Columns
search_term, search_volume, suggested_bid, competitor_rank_1 through competitor_rank_10, marketplace, source.

## Failure Handling
- Unsupported file types are rejected before storage finalization.
- Bad rows are quarantined with row number and reason.
- Mapping uncertainty requires user review.
- Original files are never overwritten.

