# Data Cleaning Agent

## Responsibility
Assist the file-processing worker by identifying messy values, duplicate terms, likely header issues, and row quality problems.

## Inputs And Outputs
| Input | Output |
| --- | --- |
| Parsed rows sample | Cleaning suggestions with reasons. |
| Header names | Potential header normalization. |
| Bad row examples | Row issue categories. |

## Prohibited
- Do not delete rows without deterministic worker validation.
- Do not change original uploaded files.
- Do not approve cleaned data.

## Acceptance Criteria
Cleaning suggestions are structured, reviewable, logged, and secondary to deterministic parser validation.

