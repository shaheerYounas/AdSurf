import type { Recommendation } from "@/lib/api/monitoring";

/**
 * Human-friendly title for a recommendation type. Avoids exposing internal IDs.
 */
export function recommendationTitle(rec: Recommendation): string {
  const type = rec.recommendation_type?.toLowerCase() ?? "";
  const entityType = rec.entity_type?.toLowerCase() ?? "";

  // Budget review variants
  if (type === "budget_review" || type === "budget review") {
    const acos = parseFloat(String(rec.current_metric_snapshot_json?.acos ?? rec.input_metrics_json?.acos ?? "0"));
    const roas = parseFloat(String(rec.current_metric_snapshot_json?.roas ?? rec.input_metrics_json?.roas ?? "0"));
    if (!isNaN(acos) && acos > 0 && acos < 0.15) return "Budget review required";
    if (!isNaN(roas) && roas > 3) return "Profitable campaign needs review";
    if (!isNaN(acos) && acos > 0.40) return "High ACOS campaign needs review";
    return "Budget review required";
  }

  if (type === "budget_increase") return "Budget increase recommended";
  if (type === "budget_decrease") return "Budget decrease recommended";

  // Bid
  if (type === "decrease_bid" || type === "bid_decrease") return "Bid decrease recommended";
  if (type === "increase_bid" || type === "bid_increase") return "Bid increase recommended";

  // Pause
  if (type === "pause_review" || type === "pause_campaign" || type === "pause_ad_group") return "Pause review candidate";

  // Negatives
  if (type === "add_negative_exact" || type === "add_negative_phrase" || type === "negative_keyword") return "Negative keyword candidate";

  // Wasted spend
  if (type === "wasted_spend" || type === "search_term_review") return "Search term may be wasted spend";

  // General positive actions
  if (type === "scale" || type === "increase_budget") return "Scaling opportunity identified";
  if (type === "protect" || type === "budget_protection") return "Budget protection recommended";

  // Campaign review
  if (type.includes("campaign") && (type.includes("review") || type.includes("check"))) return "Campaign review required";

  // ASIN / product
  if (entityType === "asin" || type.includes("product") || type.includes("asin")) return "Product review recommended";

  // Fallback: humanize the type
  return type
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
}

/**
 * Plain-English reason for a recommendation.
 */
export function recommendationReason(rec: Recommendation): string {
  const type = rec.recommendation_type?.toLowerCase() ?? "";

  // If the API returned a summary, use it
  if (rec.explanation_json?.summary) return rec.explanation_json.summary;

  // Budget review
  if (type === "budget_review" || type === "budget review") {
    const acos = parseFloat(String(rec.current_metric_snapshot_json?.acos ?? rec.input_metrics_json?.acos ?? "0"));
    const roas = parseFloat(String(rec.current_metric_snapshot_json?.roas ?? rec.input_metrics_json?.roas ?? "0"));
    if (!isNaN(acos) && acos > 0 && acos < 0.15) {
      return "This campaign is performing efficiently and may deserve budget review or protection.";
    }
    if ((!isNaN(acos) && acos > 0.40) || (!isNaN(roas) && roas > 0 && roas < 1.5)) {
      return "This campaign has weak efficiency and should not receive more budget without review.";
    }
    return "Manual budget review required. The system found important performance evidence but did not create an automatic budget change.";
  }

  if (type === "decrease_bid") return "Performance data suggests a lower bid may improve efficiency.";
  if (type === "increase_bid") return "Performance data suggests a higher bid may capture more profitable traffic.";

  if (type === "pause_review" || type === "pause_campaign") return "This entity has low or zero conversions and may be wasting spend.";
  if (type === "add_negative_exact" || type === "add_negative_phrase" || type === "negative_keyword") return "This search term has high spend with no orders and may be a negative keyword candidate.";

  if (type === "wasted_spend" || type === "search_term_review") return "This search term has clicks but low or no conversions, indicating possible wasted spend.";

  // Fallback
  return "Review metric evidence before deciding.";
}

/**
 * Recommended action text for the card.
 */
export function recommendedAction(rec: Recommendation): string {
  const type = rec.recommendation_type?.toLowerCase() ?? "";

  if (type === "budget_review" || type === "budget review") return "Review budget allocation";
  if (type === "budget_increase") return "Consider increasing budget";
  if (type === "budget_decrease") return "Consider decreasing budget";
  if (type === "decrease_bid") return "Decrease bid";
  if (type === "increase_bid") return "Increase bid";
  if (type === "pause_review" || type === "pause_campaign") return "Review for pause";
  if (type === "add_negative_exact") return "Add as exact negative keyword";
  if (type === "add_negative_phrase") return "Add as phrase negative keyword";
  if (type === "negative_keyword") return "Add negative keyword";
  if (type === "wasted_spend" || type === "search_term_review") return "Review wasted spend";
  if (type === "scale") return "Scale campaign";
  if (type === "protect" || type === "budget_protection") return "Protect budget";

  return "Review and decide";
}

/**
 * Warnings to display on the recommendation card.
 */
export function recommendationWarnings(rec: Recommendation): { message: string; kind: "info" | "warning" | "error" }[] {
  const warnings: { message: string; kind: "info" | "warning" | "error" }[] = [];

  // Product not linked
  const asin = rec.evidence_json?.asin ?? rec.product_id;
  if (asin == null || asin === "Not linked" || String(asin).trim() === "") {
    warnings.push({ message: "Product not linked — review required before export.", kind: "warning" });
  }

  // Check if review-only
  const proposedAction = rec.proposed_action_json ?? {};
  const isReviewOnly =
    rec.recommendation_type === "budget_review" ||
    rec.recommendation_type === "pause_review" ||
    rec.recommendation_type === "search_term_review" ||
    rec.recommendation_type === "wasted_spend" ||
    (!proposedAction || Object.keys(proposedAction).length === 0);
  if (isReviewOnly) {
    warnings.push({ message: "Review-only: no automatic change will be made.", kind: "info" });
  }

  // Deterministic source
  const source = rec.evidence_json?.decision_source ?? rec.decision_source ?? "";
  if (source === "deterministic" || source === "rule_engine" || rec.rule_name) {
    warnings.push({ message: "Generated by deterministic rules from uploaded report metrics.", kind: "info" });
  }

  return warnings;
}

/**
 * Approval impact message.
 */
export function approvalImpact(rec: Recommendation): string {
  if (rec.proposed_action_json && Object.keys(rec.proposed_action_json).length > 0) {
    return "Approving this recommendation adds it to your approved export/review list. It will not change Amazon Ads automatically.";
  }
  return "Approving this recommendation adds it to your approved export/review list. It will not change Amazon Ads automatically.";
}

/**
 * Display name for a recommendation (avoids internal IDs in the main title).
 */
export function recommendationDisplayName(rec: Recommendation): string {
  if (rec.campaign_name && rec.campaign_name.length > 0) return rec.campaign_name;
  if (rec.ad_group_name && rec.ad_group_name.length > 0) return rec.ad_group_name;
  if (rec.customer_search_term && rec.customer_search_term.length > 0) return rec.customer_search_term;
  return "Account-level recommendation";
}