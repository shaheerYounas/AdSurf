# Success Metrics

| Metric | Definition | MVP target direction |
| --- | --- | --- |
| Upload completion rate | Product profiles with successful parsed file after upload | Increase |
| Mapping correction rate | Percent of mappings corrected by users | Decrease over time |
| Keyword approval rate | Approved keywords divided by total valid candidates | Stable and explainable |
| Bulk export success rate | Approved plans producing valid exports | Near 100% |
| Recommendation approval rate | Recommendations accepted by users | Increase with trust |
| Time to campaign plan | Upload to generated plan duration | Decrease |
| Safety incident count | Customer-impacting action without approval | Always zero |

## Guardrail Metrics
| Guardrail | Failure condition |
| --- | --- |
| Approval bypass | Any export/action/recommendation state change without actor and approval record. |
| Tenant leakage | Any record, file, or log visible across tenants. |
| AI decision leakage | Any deterministic business decision stored only as free-form AI text. |

