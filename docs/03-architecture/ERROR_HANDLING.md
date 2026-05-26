# Error Handling

## Error Categories
| Category | Example | User response |
| --- | --- | --- |
| Validation | Missing search term column | Explain required field and next action. |
| Authorization | Cross-workspace access | Return forbidden without leaking object existence. |
| Processing | Bad spreadsheet row | Show row-level issue summary. |
| Rule | No approved keywords | Explain why campaign plan cannot be generated. |
| AI | Provider timeout | Fall back to manual review or retry. |
| Export | Invalid bulk sheet row | Block export and list validation failures. |

## Acceptance Criteria
- Errors are actionable for customers and diagnostic for engineers.
- Sensitive internals, keys, and workspace data are never exposed in client errors.
- Retryable worker errors are marked retryable.
