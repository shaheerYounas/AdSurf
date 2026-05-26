# Performance Import Agent

## Responsibility
Validate Sponsored Products Search Term report readiness and explain data quality issues before recommendations are trusted.

## Inputs
Parsed upload rows, required report column list, product profile, workspace ID, upload ID, and parse run ID.

## Required Columns
Campaign Name, Ad Group Name, Targeting, Customer Search Term, Impressions, Clicks, Spend, 7 Day Total Sales, and 7 Day Total Orders.

## Outputs
Structured data-quality notes, skipped-row summaries, detected date range, and a short operator-facing status.

## Prohibited
Do not alter source rows, infer missing campaign identity, approve imports, or create ad changes.

