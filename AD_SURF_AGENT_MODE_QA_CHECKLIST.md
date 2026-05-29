# AdSurf Agent Mode QA Checklist

**Version:** 1.0  
**Date:** 2026-05-29  
**Purpose:** Manual testing checklist for verifying agent mode behavior (deterministic, ai, hybrid)

---

## Prerequisites

- [ ] AdSurf API running (`apps/api/`)
- [ ] AdSurf Web running (`apps/web/`)
- [ ] Database migrated (Supabase)
- [ ] Test files placed in `test-fixtures/`:
  - `Marketing Project Detail Plan.txt`
  - `Sponsored_Products_Search_term_report (2).xlsx`
  - `bulk-a19yjbemeq5qup-20260511-20260512-1778596309224.xlsx`

---

## SECTION A: Upload Test Files

### A1. Upload Sponsored Products Search Term Report

1. Open Agent Control Center (`/agents`)
2. Click file input and select `Sponsored_Products_Search_term_report (2).xlsx`
3. Click "Upload report"
4. Expected:
   - [ ] Upload status shows "Report uploaded, parsed, detected, and grouped."
   - [ ] Detection shows `amazon_sp_search_term_report`
   - [ ] Entity count > 0
   - [ ] Product mapping suggestions appear (if applicable)
   - [ ] Workflow nodes animate to "waiting"
   - [ ] No "live Amazon change" claim appears

5. Screenshot: `qa-upload-search-term-report.png`

### A2. Upload Bulk Workbook

1. Open Agent Control Center (`/agents`)
2. Click file input and select `bulk-a19yjbemeq5qup-20260511-20260512-1778596309224.xlsx`
3. Click "Upload report"
4. Expected:
   - [ ] Detection shows `amazon_bulk_operations_workbook`
   - [ ] All sheets detected
   - [ ] Sponsored Products Campaigns sheet recognized
   - [ ] SP Search Term Report sheet recognized
   - [ ] Campaign IDs, Ad Group IDs preserved

5. Screenshot: `qa-upload-bulk-workbook.png`

### A3. Attempt to Upload Unsupported File

1. Try uploading `Marketing Project Detail Plan.txt`
2. Expected:
   - [ ] Error message: "Upload file extension is not supported." (txt not in accepted list)
   - [ ] No crash, no blank screen

3. Screenshot: `qa-upload-unsupported-file.png`

---

## SECTION B: Deterministic Mode Testing

### B1. Set Deterministic Mode

1. In the Agent Control Center top bar, select "Deterministic" from the mode dropdown
2. Expected:
   - [ ] Mode selector shows "Deterministic"
   - [ ] API call is made to update all agent configs
   - [ ] Success message: "Environment mode saved as deterministic."

### B2. Run Analysis in Deterministic Mode

1. Upload a Sponsored Products Search Term Report
2. Click "Run analysis"
3. Expected:
   - [ ] All agents complete with status "succeeded" or "skipped"
   - [ ] Recommendations are generated
   - [ ] Recommendation source is `deterministic_rules` or `account_bulk_deterministic_agents`
   - [ ] No DeepSeek/LLM calls in logs
   - [ ] Metrics (ACOS, ROAS, CPC, CTR, CVR) are code-calculated
   - [ ] Evidence JSON includes thresholds used
   - [ ] All recommendations have status `pending_approval`

4. Screenshot: `qa-deterministic-results.png`

### B3. Verify Deterministic Outputs

1. Check each agent card in the dashboard
2. Expected per agent:
   - [ ] Report Upload: "completed"
   - [ ] Report Detection Agent: "completed" with correct detection
   - [ ] Product Resolution Agent: "completed" with entity counts
   - [ ] Metrics Analysis Agent: "completed" with performance rollups
   - [ ] AI Recommendation Brain: "completed" with recommendation count
   - [ ] Bid Optimization Agent: "completed" with bid recommendations
   - [ ] Negative Keyword Agent: "completed" with negative keyword candidates
   - [ ] Budget Allocation Agent: "completed" with budget review
   - [ ] Pause Review Agent: "completed" with pause candidates
   - [ ] Stakeholder Reporting Agent: "completed" with summary
   - [ ] Human Approval Agent: "approval_needed" with pending count

3. Screenshot: `qa-deterministic-agent-cards.png`

---

## SECTION C: AI Mode Testing

### C1. Set AI Mode

1. In the Agent Control Center top bar, select "AI" from the mode dropdown
2. Expected:
   - [ ] Mode selector shows "AI"
   - [ ] API call succeeds
   - [ ] Success message: "Environment mode saved as ai."

### C2. Run Analysis in AI Mode

1. Upload a Sponsored Products Search Term Report
2. Click "Run analysis"
3. Expected:
   - [ ] If DEEPSEEK_API_KEY is configured:
     - [ ] DeepSeek is called for applicable agents
     - [ ] AI-generated explanations appear in recommendation output
     - [ ] AI output is structured JSON
     - [ ] AI does NOT calculate ACOS/ROAS/CPC/CTR/CVR (those stay deterministic)
   - [ ] If DEEPSEEK_API_KEY is NOT configured:
     - [ ] Agents should NOT crash
     - [ ] Deterministic fallback should be used
     - [ ] Error should be logged but not user-facing as a crash
   - [ ] All recommendations have status `pending_approval`
   - [ ] No "live Amazon change" claim

4. Screenshot: `qa-ai-results.png`

### C3. Verify AI Safety

1. Check that:
   - [ ] AI did NOT invent metrics not in the report
   - [ ] AI did NOT auto-approve any recommendation
   - [ ] AI did NOT calculate spend/sales/ACOS (only deterministic code does)
   - [ ] AI output passes validation (no validation errors)

---

## SECTION D: Hybrid Mode Testing

### D1. Set Hybrid Mode

1. In the Agent Control Center top bar, select "Hybrid" from the mode dropdown
2. Expected:
   - [ ] Mode selector shows "Hybrid"
   - [ ] API call succeeds
   - [ ] Success message: "Environment mode saved as hybrid."

### D2. Run Analysis in Hybrid Mode

1. Upload a Sponsored Products Search Term Report
2. Click "Run analysis"
3. Expected:
   - [ ] Deterministic calculations are primary (metrics, thresholds)
   - [ ] If AI is available, explanations are AI-enhanced
   - [ ] If AI fails, deterministic fallback is used
   - [ ] All AI outputs go through risk_validator
   - [ ] Unsafe AI suggestions are rejected with reason logged
   - [ ] All recommendations have status `pending_approval`

4. Screenshot: `qa-hybrid-results.png`

---

## SECTION E: Approval Queue Testing

### E1. View Approval Queue

1. Scroll to "Human Approval Checkpoints" section
2. Expected:
   - [ ] Pending recommendations listed with type, priority, confidence
   - [ ] Metric evidence expandable per recommendation
   - [ ] Approve/Reject buttons visible

### E2. Approve a Recommendation

1. Click "Approve" on one recommendation
2. Expected:
   - [ ] Button shows loading state
   - [ ] Recommendation status changes to "approved"
   - [ ] Message: "Recommendation approve recorded. No live Amazon Ads change executed."
   - [ ] Audit log entry created

3. Screenshot: `qa-approve-recommendation.png`

### E3. Reject a Recommendation

1. Click "Reject" on one recommendation
2. Expected:
   - [ ] Button shows loading state
   - [ ] Recommendation status changes to "rejected"
   - [ ] Message confirms rejection
   - [ ] Audit log entry created

3. Screenshot: `qa-reject-recommendation.png`

---

## SECTION F: Agent Controls

### F1. Disable an Agent

1. In Agent Inspector, toggle "enabled" off for any agent
2. Expected:
   - [ ] Agent card shows "paused" status
   - [ ] Workflow node shows "skipped" on next run
   - [ ] Disabled agent produces no recommendations on next run

### F2. Rerun from Specific Agent

1. Click "Rerun" on a specific agent
2. Expected:
   - [ ] New agent run is created
   - [ ] Status is "queued"
   - [ ] Previous output preserved as `_rerun_of`

### F3. Pause/Resume/Stop Agent

1. Use bulk actions or individual controls
2. Expected:
   - [ ] Pause: agent status changes to "paused"
   - [ ] Resume: agent status changes to "queued"
   - [ ] Stop: agent status changes to "stopped"
   - [ ] Audit log records each control action

---

## SECTION G: Audit Log Verification

### G1. Check Audit Events

1. Use the Agent Trace Timeline or API to verify:
   - [ ] Upload events logged
   - [ ] Agent config changes logged
   - [ ] Agent run events logged
   - [ ] Recommendation decisions logged
   - [ ] All events have `execution_boundary: "no_live_amazon_change"`

---

## SECTION H: Export Verification

### H1. Verify No Live Changes

1. Check ALL outputs for these forbidden phrases:
   - "changed in Amazon"
   - "updated live campaign"
   - "applied to Amazon"
   - "executed in Amazon"
   - "mutated Amazon Ads"
2. Expected:
   - [ ] NONE of these phrases appear anywhere in outputs

---

## SECTION I: Cross-Mode Comparison

### I1. Same File, Different Modes

1. Upload the same Sponsored Products Search Term Report
2. Run in deterministic mode → note recommendation count and types
3. Run in AI mode → note recommendation count and types
4. Run in hybrid mode → note recommendation count and types
5. Expected:
   - [ ] Core metric calculations are IDENTICAL across all modes
   - [ ] Deterministic mode produces only rule-based recommendations
   - [ ] AI/hybrid modes may produce additional explanations but not different core metrics
   - [ ] All modes require approval

---

## SECTION J: Screenshot Capture Checklist

Capture these screenshots during testing:

- [ ] `qa-01-deterministic-mode-selected.png` - Top bar showing deterministic mode
- [ ] `qa-02-ai-mode-selected.png` - Top bar showing AI mode
- [ ] `qa-03-hybrid-mode-selected.png` - Top bar showing hybrid mode
- [ ] `qa-04-search-term-uploaded.png` - After SP search term report upload
- [ ] `qa-05-bulk-workbook-uploaded.png` - After bulk workbook upload
- [ ] `qa-06-deterministic-complete.png` - All agents complete in deterministic mode
- [ ] `qa-07-ai-complete.png` - All agents complete in AI mode
- [ ] `qa-08-hybrid-complete.png` - All agents complete in hybrid mode
- [ ] `qa-09-approval-queue.png` - Pending approvals visible
- [ ] `qa-10-approve-action.png` - After approving a recommendation
- [ ] `qa-11-reject-action.png` - After rejecting a recommendation
- [ ] `qa-12-agent-inspector.png` - Agent inspector with config
- [ ] `qa-13-workflow-canvas.png` - Workflow canvas with statuses
- [ ] `qa-14-audit-trace.png` - Audit trace timeline
- [ ] `qa-15-unsupported-file-error.png` - Error on unsupported file upload

---

## SECTION K: Common Failure Signs

Watch for:

- [ ] "500 Internal Server Error" on mode change
- [ ] Agent stuck in "running" indefinitely
- [ ] Mode selector reverting to previous value
- [ ] DeepSeek API errors not being handled gracefully
- [ ] Recommendations appearing without evidence
- [ ] Recommendations appearing without pending_approval status
- [ ] Any mention of "changed in Amazon" or "applied to Amazon"
- [ ] Blank pages after upload
- [ ] Console errors in browser dev tools
- [ ] API returning empty agent definitions
- [ ] Workflow nodes showing incorrect status
- [ ] Approval decisions not persisting after page refresh

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Tester | | | |
| Developer | | | |
| Product Owner | | | |