# Metrics Glossary

| Metric | Definition | Used for |
| --- | --- | --- |
| Impressions | Number of ad views | Traffic health. |
| Clicks | Number of ad clicks | Traffic and CTR. |
| Spend | Advertising cost | Budget and pause decisions. |
| Sales | Attributed revenue | ACOS and performance. |
| Orders | Attributed conversions | Conversion assessment. |
| CPC | Spend divided by clicks | Bid efficiency. |
| CTR | Clicks divided by impressions | Relevance signal. |
| CVR | Orders divided by clicks | Conversion signal. |
| ACOS | Spend divided by sales | Lock and pause review. |
| ROAS | Sales divided by spend | Performance efficiency review. |
| Relevance Score | Count of top 10 competitors with organic rank under 15 | Keyword approval. |

## Calculation Ownership
Metrics are calculated by deterministic backend rules. AI may explain metrics but must not be the sole calculator or source of truth.

## Validation Rules
- Uploaded Amazon metric fields are treated as evidence, not source-of-truth calculations.
- The backend recalculates CTR as `Clicks / Impressions`, CPC as `Spend / Clicks`, CVR as `Orders / Clicks`, ACOS as `Spend / Sales`, and ROAS as `Sales / Spend`.
- When uploaded values differ materially from recalculated values, the import receives a data-quality warning for human review.
- If sales are zero, ACOS is undefined and must not be displayed or interpreted as `0%`.
- Orders and units are separate values; a mismatch is expected in some cases and must not be treated as a calculation error.
