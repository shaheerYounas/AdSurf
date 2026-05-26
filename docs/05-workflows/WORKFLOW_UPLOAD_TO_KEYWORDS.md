# Workflow: Upload To Keywords

## Steps
| Step | Responsible party | Output |
| --- | --- | --- |
| Create product profile | User | Product defaults and marketplace. |
| Upload CSV/XLSX | User/API | Private file and upload record. |
| Parse file | File worker | Parsed rows and row issues. |
| Suggest mappings | Column Mapping Agent | Canonical mapping proposal. |
| Confirm mappings | User | Reviewed mapping record. |
| Score keywords | Rule engine | Candidate statuses and relevance scores. |
| Review keywords | User | Approved or rejected keyword set. |

## Acceptance Criteria
- Original upload is preserved.
- Required mappings are confirmed before scoring.
- Scores 0, 1, and 2 are rejected.
- Approval history records keyword review decisions.
