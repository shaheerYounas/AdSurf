import { describe, it, expect } from "vitest";
import { formatACOS, formatROAS, formatCurrency, formatInteger, formatMetricValue, fixMetricLabel } from "@/lib/formatters";
import { recommendationTitle, recommendationReason, recommendedAction, recommendationWarnings, approvalImpact, recommendationDisplayName } from "@/lib/recommendation-helpers";
import type { Recommendation } from "@/lib/api/monitoring";

function makeRec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: "rec-001",
    product_id: null,
    monitoring_import_id: null,
    account_import_id: null,
    entity_key: null,
    decision_source: null,
    recommendation_type: "budget_review",
    entity_type: "campaign",
    status: "pending_approval",
    priority: "high",
    confidence: "high",
    rule_name: "",
    campaign_name: null,
    ad_group_name: null,
    targeting: null,
    customer_search_term: null,
    input_metrics_json: {},
    current_metric_snapshot_json: {},
    evidence_json: {},
    proposed_action_json: {},
    explanation_json: {},
    ...overrides,
  };
}

describe("formatACOS", () => {
  it("formats decimal ACOS to percentage", () => {
    expect(formatACOS(0.2589)).toBe("25.89%");
    expect(formatACOS(0.6016)).toBe("60.16%");
    expect(formatACOS(0)).toBe("0.00%");
  });

  it("handles null and undefined", () => {
    expect(formatACOS(null)).toBe("—");
    expect(formatACOS(undefined)).toBe("—");
  });

  it("handles string input", () => {
    expect(formatACOS("0.15")).toBe("15.00%");
  });
});

describe("formatROAS", () => {
  it("formats decimal ROAS to multiplier", () => {
    expect(formatROAS(3.8628)).toBe("3.86x");
    expect(formatROAS(0)).toBe("0.00x");
  });

  it("handles null and undefined", () => {
    expect(formatROAS(null)).toBe("—");
    expect(formatROAS(undefined)).toBe("—");
  });
});

describe("formatCurrency", () => {
  it("formats numbers to US currency", () => {
    expect(formatCurrency(6295.16)).toBe("$6,295.16");
    expect(formatCurrency(1629.7)).toBe("$1,629.70");
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("handles null and undefined", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(undefined)).toBe("—");
  });

  it("handles string input", () => {
    expect(formatCurrency("6295.16")).toBe("$6,295.16");
  });
});

describe("formatInteger", () => {
  it("formats numbers with locale grouping", () => {
    expect(formatInteger(1495)).toBe("1,495");
    expect(formatInteger(296)).toBe("296");
    expect(formatInteger(0)).toBe("0");
  });

  it("handles null and undefined", () => {
    expect(formatInteger(null)).toBe("—");
    expect(formatInteger(undefined)).toBe("—");
  });

  it("handles string input", () => {
    expect(formatInteger("1495")).toBe("1,495");
  });
});

describe("formatMetricValue", () => {
  it("formats ACOS keys as percentage", () => {
    expect(formatMetricValue("acos", 0.2589)).toBe("25.89%");
    expect(formatMetricValue("ACOS", 0.6016)).toBe("60.16%");
    expect(formatMetricValue("acos_30d", 0.15)).toBe("15.00%");
  });

  it("formats ROAS keys as multiplier", () => {
    expect(formatMetricValue("roas", 3.86)).toBe("3.86x");
    expect(formatMetricValue("ROAS_30d", 5.0)).toBe("5.00x");
  });

  it("formats spend/sales/cost keys as currency", () => {
    expect(formatMetricValue("spend", 1629.7)).toBe("$1,629.70");
    expect(formatMetricValue("sales", 6295.16)).toBe("$6,295.16");
    expect(formatMetricValue("cost", 100)).toBe("$100.00");
    expect(formatMetricValue("revenue", 5000)).toBe("$5,000.00");
    expect(formatMetricValue("cpc", 0.5)).toBe("$0.50");
    expect(formatMetricValue("budget", 10000)).toBe("$10,000.00");
  });

  it("formats click/impression/order keys as integers", () => {
    expect(formatMetricValue("clicks", 1495)).toBe("1,495");
    expect(formatMetricValue("impressions", 10000)).toBe("10,000");
    expect(formatMetricValue("orders", 296)).toBe("296");
    expect(formatMetricValue("conversions", 50)).toBe("50");
  });
});

describe("fixMetricLabel", () => {
  it("fixes common typos", () => {
    expect(fixMetricLabel("spnd")).toBe("Spend");
    expect(fixMetricLabel("impr")).toBe("Impressions");
    expect(fixMetricLabel("clks")).toBe("Clicks");
    expect(fixMetricLabel("ordrs")).toBe("Orders");
    expect(fixMetricLabel("sls")).toBe("Sales");
  });

  it("humanizes snake_case keys", () => {
    expect(fixMetricLabel("acos_30d")).toBe("Acos 30d");
    expect(fixMetricLabel("roas_7d")).toBe("Roas 7d");
  });
});

describe("recommendationTitle", () => {
  it("returns 'Budget review required' for budget_review with low ACOS", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      current_metric_snapshot_json: { acos: 0.10 },
    });
    expect(recommendationTitle(rec)).toBe("Budget review required");
  });

  it("returns 'Profitable campaign needs review' for budget_review with high ROAS", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      current_metric_snapshot_json: { roas: 4.0 },
    });
    expect(recommendationTitle(rec)).toBe("Profitable campaign needs review");
  });

  it("returns 'High ACOS campaign needs review' for budget_review with high ACOS", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      current_metric_snapshot_json: { acos: 0.50 },
    });
    expect(recommendationTitle(rec)).toBe("High ACOS campaign needs review");
  });

  it("returns human-friendly titles for bid recommendations", () => {
    expect(recommendationTitle(makeRec({ recommendation_type: "decrease_bid" }))).toBe("Bid decrease recommended");
    expect(recommendationTitle(makeRec({ recommendation_type: "increase_bid" }))).toBe("Bid increase recommended");
  });

  it("returns human-friendly titles for negative keywords", () => {
    expect(recommendationTitle(makeRec({ recommendation_type: "add_negative_exact" }))).toBe("Negative keyword candidate");
    expect(recommendationTitle(makeRec({ recommendation_type: "add_negative_phrase" }))).toBe("Negative keyword candidate");
  });

  it("returns human-friendly titles for pause review", () => {
    expect(recommendationTitle(makeRec({ recommendation_type: "pause_review" }))).toBe("Pause review candidate");
  });

  it("returns human-friendly titles for wasted spend", () => {
    expect(recommendationTitle(makeRec({ recommendation_type: "search_term_review" }))).toBe("Search term may be wasted spend");
  });

  it("does NOT use internal IDs as primary title", () => {
    // Even if campaign_name contains an ID, the title should be the type-based human label
    const rec = makeRec({
      recommendation_type: "budget_review",
      campaign_name: "SPT_APRQ8M752664_portfolio",
      current_metric_snapshot_json: { acos: 0.50 },
    });
    const title = recommendationTitle(rec);
    expect(title).not.toContain("SPT_APRQ8M752664");
    expect(title).not.toContain("APRQ8");
    expect(title).toBe("High ACOS campaign needs review");
  });
});

describe("recommendationReason", () => {
  it("explains efficient campaigns", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      current_metric_snapshot_json: { acos: 0.10, roas: 5.0 },
    });
    const reason = recommendationReason(rec);
    expect(reason).toContain("efficiently");
  });

  it("explains weak efficiency campaigns", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      current_metric_snapshot_json: { acos: 0.50 },
    });
    const reason = recommendationReason(rec);
    expect(reason).toContain("weak efficiency");
  });

  it("defaults to manual review message when no specific action", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      current_metric_snapshot_json: {},
    });
    const reason = recommendationReason(rec);
    expect(reason).toContain("Manual budget review required");
  });

  it("uses summary from explanation_json if available", () => {
    const rec = makeRec({
      recommendation_type: "budget_review",
      explanation_json: { summary: "Custom summary text" },
    });
    expect(recommendationReason(rec)).toBe("Custom summary text");
  });
});

describe("approvalImpact", () => {
  it("contains 'no live Amazon Ads change executed' message", () => {
    const rec = makeRec();
    const impact = approvalImpact(rec);
    expect(impact).toContain("will not change Amazon Ads automatically");
  });

  it("returns consistent message regardless of proposed_action", () => {
    const withAction = makeRec({ proposed_action_json: { type: "review", reason: "test" } });
    const withoutAction = makeRec({ proposed_action_json: {} });
    expect(approvalImpact(withAction)).toContain("will not change Amazon Ads automatically");
    expect(approvalImpact(withoutAction)).toContain("will not change Amazon Ads automatically");
  });
});

describe("recommendationWarnings", () => {
  it("shows product not linked warning when asin is 'Not linked'", () => {
    const rec = makeRec({
      evidence_json: { asin: "Not linked" },
      product_id: null,
    });
    const warnings = recommendationWarnings(rec);
    const productWarning = warnings.find((w) => w.message.includes("Product not linked"));
    expect(productWarning).toBeTruthy();
    expect(productWarning!.kind).toBe("warning");
  });

  it("shows review-only warning for budget_review", () => {
    const rec = makeRec({ recommendation_type: "budget_review" });
    const warnings = recommendationWarnings(rec);
    const reviewWarning = warnings.find((w) => w.message.includes("Review-only"));
    expect(reviewWarning).toBeTruthy();
    expect(reviewWarning!.kind).toBe("info");
  });

  it("shows deterministic source warning when rule_name is set", () => {
    const rec = makeRec({
      rule_name: "acos_budget_review_rule",
      evidence_json: {},
    });
    const warnings = recommendationWarnings(rec);
    const deterministicWarning = warnings.find((w) => w.message.includes("deterministic"));
    expect(deterministicWarning).toBeTruthy();
    expect(deterministicWarning!.kind).toBe("info");
  });

  it("shows deterministic source warning when decision_source is deterministic", () => {
    const rec = makeRec({
      evidence_json: { decision_source: "deterministic" },
    });
    const warnings = recommendationWarnings(rec);
    const deterministicWarning = warnings.find((w) => w.message.includes("deterministic"));
    expect(deterministicWarning).toBeTruthy();
  });
});

describe("recommendationDisplayName", () => {
  it("uses campaign name if available", () => {
    const rec = makeRec({ campaign_name: "My Campaign" });
    expect(recommendationDisplayName(rec)).toBe("My Campaign");
  });

  it("falls back to ad group name", () => {
    const rec = makeRec({ campaign_name: null, ad_group_name: "My Ad Group" });
    expect(recommendationDisplayName(rec)).toBe("My Ad Group");
  });

  it("falls back to search term", () => {
    const rec = makeRec({ campaign_name: null, ad_group_name: null, customer_search_term: "some keyword" });
    expect(recommendationDisplayName(rec)).toBe("some keyword");
  });

  it("returns default for no display name", () => {
    const rec = makeRec({ campaign_name: null, ad_group_name: null, customer_search_term: null });
    expect(recommendationDisplayName(rec)).toBe("Account-level recommendation");
  });
});