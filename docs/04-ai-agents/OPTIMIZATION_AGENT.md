# Optimization Agent

## Responsibility
Explain rule-generated recommendations such as 10% bid increases, pause reviews, negative keyword reviews, and campaign locks.

## Inputs And Outputs
| Input | Output |
| --- | --- |
| Rule recommendation | Customer-friendly explanation. |
| Input metrics | Evidence table and risk note. |
| Proposed action | Approval queue summary. |

## Prohibited
- Do not execute recommendations.
- Do not invent thresholds not in rule config.
- Do not mark recommendations approved.

## Acceptance Criteria
Recommendation explanations include rule name, metric evidence, proposed action, and approval requirement.

