# Test Fixtures for Real File Testing

Place the following real test files in this directory:

1. `Marketing Project Detail Plan.txt`
   - Competitor keyword research / marketing plan reference document
   - Used as requirements/compliance reference (not an ads performance report)

2. `Sponsored_Products_Search_term_report (2).xlsx`
   - Real Amazon Sponsored Products Search Term Report
   - Expected classification: `amazon_sp_search_term_report`
   - Used for monitoring/recommendation workflow testing

3. `bulk-a19yjbemeq5qup-20260511-20260512-1778596309224.xlsx`
   - Real Amazon Bulk Operations Workbook
   - Expected classification: `amazon_bulk_operations_workbook`
   - Used for bulk parsing and export-ready changes workflow

**IMPORTANT:** These files contain real Amazon Ads data. They are listed in `.gitignore` and will NOT be committed to the repository.

This directory is for manual QA testing only. Automated tests use synthetic fixtures in `tests/fixtures/`.