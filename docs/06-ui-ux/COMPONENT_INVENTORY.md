# Component Inventory

| Component | Purpose |
| --- | --- |
| DashboardOverview | Shows live workspace counts, product continuation links, upload status counts, pending recommendation count, launch checklist state, and the latest recommendation queue preview. |
| ProductSetupForm | Create/edit ASIN, marketplace, currency, defaults. |
| ProductProfileForm | Backward-compatible name for product setup form if used in code. |
| ProductDetailPanel | Shows product defaults, upload status summary, and next-step workflow links for upload, mapping, scoring, campaign plan, and export. |
| UploadInitializationForm | File selection, report type selection, upload init, signed target display, confirm queue handoff, parse status summary, and workflow link after parse success. Competitor research opens manual mapping; Sponsored Products Search Term reports open monitoring import creation. |
| ParseStatusSummary | Shows parse run status, parsed rows, error rows, and column count without scoring controls. |
| UploadDropzone | Upload CSV/XLSX with validation. |
| FileUploadDropzone | Backward-compatible name for upload dropzone if used in code. |
| ColumnMappingWorkspace | Manual mapping, scoring, keyword review, approved keyword set creation, campaign plan generation/approval, and approved bulk export download workspace. |
| ColumnMappingTable | Shows discovered original column names, normalized names, inferred types, non-null counts, and sample values. |
| ManualColumnMappingForm | Maps `search_term`, `search_volume`, and `competitor_rank_columns` without AI or semantic auto-mapping. |
| KeywordScoringSummary | Shows total rows, approved candidates, rejected candidates, and row errors for a scoring run. |
| KeywordReviewTable | Review search term, search volume, relevance score, original status, effective status, rejection reason, override status, and manual override actions. |
| KeywordScoreTable | Backward-compatible name for keyword review table if used in code. |
| ScoreFilter | Filter keywords by relevance score range. |
| StatusFilter | Filter keywords by review status. |
| BulkApproveRejectControls | Approve or reject selected keyword candidates. |
| OverrideReasonModal | Capture required reason for Batch 7 keyword approve/reject overrides. |
| ApprovedKeywordSetControls | Name and create locked approved keyword set snapshots from effective approved candidates. |
| ApprovalPanel | Summarize and submit approval decisions. |
| CampaignPlanTree | Show Hero, groups, match types, negatives. |
| HeroCampaignCard | Show Hero keyword, Hero Score, budget, bid, and evidence. |
| GroupedCampaignCard | Show Exact, Phrase, Broad group campaigns and included terms. |
| NegativeKeywordPreview | Show generated Negative Exact and Negative Phrase rows before export. |
| BulkExportCard | Show export status, validation, approval, and download readiness. |
| BulkExportValidator | Show export readiness and failures. |
| MetricsChart | Show performance trends with Recharts. |
| MonitoringWorkspace | Create or reuse monitoring imports from processed Sponsored Products Search Term report uploads, trigger local processing, show trustworthy row/recommendation counts, import health severity, action vs watch breakdowns, detected advertised product groups, confidence, and top explanations. |
| RecommendationsWorkspace | Shows recommendation summary cards, safety banner, quick filters, action-class/export filters, seller-friendly metric evidence, compact approval table, details modal, and required approve/reject notes without executing Amazon Ads actions. |
| RecommendationCard | Show rule, evidence, proposed action, explanation, status, and approval controls. |
| ApprovalConfirmationDialog | Confirm approval/rejection/export decisions with impact summary. |
| ImpactSummaryPanel | Show what will be generated, exported, or recommended. |
| AuditTimeline | Show chronological decisions, jobs, approvals, and AI runs. |
| AuditLogTable | Show immutable event history. |
| JobStatusIndicator | Show queued, running, succeeded, failed, dead-letter, or cancelled state. |
| EmptyStatePanel | Show workflow-specific next action. |
| ErrorBanner | Show user-safe error and recovery action. |
| LargeTablePagination | Paginate large keyword, audit, and recommendation tables. |

Form-heavy workflow controls in `ReportLibrary`, `ProductDetailPanel`, `UploadInitializationForm`, `UploadList`, `MonitoringWorkspace`, `CompetitorWorkflow`, and `AgentControlCenter` use stable `id` and `name` attributes so browser DevTools, accessibility checks, and automated UI tests can identify file inputs, workspace fields, selectors, and text areas reliably.

## Acceptance Criteria
Components separate deterministic rule evidence from AI explanation text.

## Accessibility Requirements
- Support keyboard navigation for tables, filters, dialogs, and approval controls.
- Show visible focus states for all interactive elements.
- Provide ARIA labels for destructive or high-impact actions such as rejection, export approval, and recommendation approval.
- Use confirmation dialogs for approval, rejection, and export handoff.
- Do not rely on color-only status indicators; pair color with text, icon, or label.
