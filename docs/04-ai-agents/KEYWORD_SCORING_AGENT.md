# Keyword Scoring Agent

## Responsibility
Explain keyword relevance score results and rejection reasons in customer-friendly language.

## Important Boundary
The agent does not calculate the Relevance Score. The rule engine calculates `count(top_10_competitors where organic_rank < 15)` and rejects scores 0, 1, and 2.

## Outputs
| Output | Requirement |
| --- | --- |
| Explanation | References score, competitor counts, and threshold. |
| Review note | Helps user understand approval or rejection. |

## Acceptance Criteria
Explanations match stored rule output and never contradict the score status.

