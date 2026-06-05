import type { Recommendation } from "@/lib/api/monitoring";

export type RecommendationActionClass = "actionable" | "review_only" | "watch_only" | "data_quality" | "budget_review";

export type ExportabilityFilter = "" | "exportable" | "non_exportable";

export type RecommendationFilters = {
  status: string;
  priority: string;
  recommendationType: string;
  actionClass: "" | RecommendationActionClass;
  exportability: ExportabilityFilter;
  confidence: string;
  campaignQuery: string;
  searchTermQuery: string;
  minSpend: string;
  minClicks: string;
  minOrders: string;
};

export type RecommendationMetricKey = "spend" | "sales" | "clicks" | "orders" | "acos" | "roas" | "cvr" | "ctr" | "impressions";

export type RecommendationMetricChip = {
  key: RecommendationMetricKey;
  label: string;
  value: string;
  rawValue: unknown;
};

export type RecommendationSummaryCounts = {
  total: number;
  actionable: number;
  reviewOnly: number;
  exportable: number;
  pending: number;
  approved: number;
  rejected: number;
  criticalHigh: number;
};

export const exportableRecommendationTypes = new Set([
  "add_negative_exact",
  "add_negative_phrase",
  "increase_bid",
  "decrease_bid",
  "move_to_exact",
]);

const recommendationTypeLabels: Record<string, string> = {
  add_negative_exact: "Add negative exact",
  add_negative_phrase: "Add negative phrase",
  increase_bid: "Increase bid",
  decrease_bid: "Decrease bid",
  move_to_exact: "Move to exact",
  pause_review: "Pause review",
  watch_lock: "Watch only",
  watch_only: "Watch only",
  keep_running: "Keep running",
  budget_review: "Budget review",
  data_quality_review: "Data check needed",
  data_quality_warning: "Data check needed",
};

const actionClassLabels: Record<RecommendationActionClass, string> = {
  actionable: "Actionable",
  review_only: "Review only",
  watch_only: "Watch only",
  data_quality: "Data quality",
  budget_review: "Budget review",
};

const metricLabels: Record<RecommendationMetricKey, string> = {
  spend: "Spend",
  sales: "Sales",
  clicks: "Clicks",
  orders: "Orders",
  acos: "ACOS",
  roas: "ROAS",
  cvr: "CVR",
  ctr: "CTR",
  impressions: "Impressions",
};

const metricAliases: Record<RecommendationMetricKey, string[]> = {
  spend: ["spend", "cost", "7_day_total_spend"],
  sales: ["sales", "revenue", "total_sales", "7_day_total_sales", "seven_day_total_sales"],
  clicks: ["clicks", "click"],
  orders: ["orders", "order_count", "purchases", "7_day_total_orders", "seven_day_total_orders"],
  acos: ["acos", "advertising_cost_of_sales"],
  roas: ["roas", "return_on_ad_spend"],
  cvr: ["cvr", "conversion_rate", "conversionrate"],
  ctr: ["ctr", "click_through_rate", "clickthroughrate"],
  impressions: ["impressions", "impression"],
};

const defaultEvidenceMetricKeys: RecommendationMetricKey[] = ["spend", "sales", "clicks", "orders", "acos", "roas", "cvr"];

export const emptyRecommendationFilters: RecommendationFilters = {
  status: "",
  priority: "",
  recommendationType: "",
  actionClass: "",
  exportability: "",
  confidence: "",
  campaignQuery: "",
  searchTermQuery: "",
  minSpend: "",
  minClicks: "",
  minOrders: "",
};

export function recommendationTypeLabel(recOrType: Recommendation | string | null | undefined): string {
  const type = typeof recOrType === "string" ? normalizeText(recOrType) : normalizeText(recOrType?.recommendation_type);

  if (!type) return "Recommendation";
  if (recommendationTypeLabels[type]) return recommendationTypeLabels[type];
  if (type.includes("data_quality") || type.includes("inconsistent_metrics")) return recommendationTypeLabels.data_quality_review;
  if (type.includes("negative") && type.includes("phrase")) return recommendationTypeLabels.add_negative_phrase;
  if (type.includes("negative")) return recommendationTypeLabels.add_negative_exact;
  if (type.includes("increase") && type.includes("bid")) return recommendationTypeLabels.increase_bid;
  if (type.includes("decrease") && type.includes("bid")) return recommendationTypeLabels.decrease_bid;
  if (type.includes("exact") && (type.includes("move") || type.includes("harvest"))) return recommendationTypeLabels.move_to_exact;
  if (type.includes("budget")) return recommendationTypeLabels.budget_review;
  if (type.includes("watch") || type.includes("no_action")) return recommendationTypeLabels.watch_lock;

  return humanizeInternal(type);
}

export function recommendationActionClass(rec: Recommendation): RecommendationActionClass {
  const type = normalizeText(rec.recommendation_type);
  const ruleName = normalizeText(rec.rule_name);

  if (type.includes("data_quality") || ruleName.includes("data_quality") || ruleName.includes("inconsistent_metrics")) {
    return "data_quality";
  }
  if (type === "budget_review" || type.includes("budget")) return "budget_review";
  if (type === "watch_lock" || type === "watch_only" || type === "keep_running" || type === "no_action_low_data") {
    return "watch_only";
  }
  if (exportableRecommendationTypes.has(type)) return "actionable";
  return "review_only";
}

export function recommendationActionClassLabel(actionClass: RecommendationActionClass): string {
  return actionClassLabels[actionClass];
}

export function isRecommendationExportable(rec: Recommendation): boolean {
  return exportableRecommendationTypes.has(normalizeText(rec.recommendation_type));
}

export function recommendationExportableLabel(rec: Recommendation): "Yes" | "No" {
  return isRecommendationExportable(rec) ? "Yes" : "No";
}

export function recommendationExportReason(rec: Recommendation): string {
  const type = normalizeText(rec.recommendation_type);
  const actionClass = recommendationActionClass(rec);

  if (isRecommendationExportable(rec)) {
    return "Eligible for a manual bulk-sheet export after human approval. No Amazon Ads API call is made.";
  }
  if (actionClass === "data_quality") return "Data checks must be reviewed before optimization actions can be exported.";
  if (actionClass === "budget_review") return "Budget review is advisory in this MVP and does not create a bulk-sheet action.";
  if (type === "pause_review") return "Pause decisions are review-only in this MVP and require separate campaign review.";
  if (type === "keep_running" || type === "watch_lock" || type === "watch_only") {
    return "Watch and keep-running insights do not create export rows.";
  }
  return "This recommendation type is not one of the exportable MVP action types.";
}

export function recommendationSourceLabel(rec: Recommendation): "AI assisted" | "Rules engine" {
  const source = normalizeText(rec.decision_source || rec.evidence_json?.decision_source || rec.explanation_json?.decision_source);
  const provider = normalizeText(rec.evidence_json?.ai_provider || rec.explanation_json?.ai_provider);
  const model = normalizeText(rec.evidence_json?.ai_model || rec.explanation_json?.ai_model);

  if (source.includes("deepseek") || provider.includes("deepseek") || model.includes("deepseek") || source.includes("ai_reasoning")) {
    return "AI assisted";
  }
  if (
    source.includes("deterministic") ||
    source.includes("fallback") ||
    source.includes("rule") ||
    source.includes("langgraph_deterministic")
  ) {
    return "Rules engine";
  }
  if (provider || model) return "AI assisted";
  return "Rules engine";
}

export function recommendationTechnicalSource(rec: Recommendation): string {
  const parts = [
    rec.decision_source,
    rec.evidence_json?.decision_source,
    rec.explanation_json?.decision_source,
    rec.evidence_json?.ai_provider || rec.explanation_json?.ai_provider,
    rec.evidence_json?.ai_model || rec.explanation_json?.ai_model,
  ]
    .map((item) => String(item ?? "").trim())
    .filter(Boolean);

  return Array.from(new Set(parts)).join(" / ") || "deterministic_rules";
}

export function recommendationStatusLabel(status: string | null | undefined): string {
  const normalized = normalizeText(status);
  if (normalized === "pending" || normalized === "pending_approval") return "Pending approval";
  if (normalized === "approved") return "Approved";
  if (normalized === "rejected") return "Rejected";
  if (normalized === "superseded") return "Superseded";
  return humanizeInternal(normalized || "unknown");
}

export function recommendationPriorityLabel(priority: string | null | undefined): string {
  return humanizeInternal(normalizeText(priority) || "priority");
}

export function recommendationConfidenceLabel(confidence: string | null | undefined): string {
  const normalized = normalizeText(confidence);
  if (normalized === "very_high") return "Very high";
  if (normalized === "very_low") return "Very low";
  if (normalized === "insufficient_data") return "Insufficient data";
  return humanizeInternal(normalized || "Unknown");
}

export function getRecommendationMetric(rec: Recommendation, key: RecommendationMetricKey): unknown {
  const sources = [
    rec.current_metric_snapshot_json,
    rec.input_metrics_json,
    rec.evidence_json?.metrics,
    rec.evidence_json?.metric_snapshot,
    rec.explanation_json?.advanced_details?.metric_snapshot,
  ];

  for (const source of sources) {
    const value = getMetricFromRecord(source, metricAliases[key]);
    if (value !== undefined && value !== null && String(value).trim() !== "") return value;
  }
  return null;
}

export function getRecommendationMetricNumber(rec: Recommendation, key: RecommendationMetricKey): number | null {
  return toNumber(getRecommendationMetric(rec, key));
}

export function formatRecommendationMetric(key: RecommendationMetricKey, value: unknown): string {
  if (value === null || value === undefined || String(value).trim() === "") return "—";

  if (key === "spend" || key === "sales") return formatCurrencyForReview(value);
  if (key === "clicks" || key === "orders" || key === "impressions") return formatIntegerForReview(value);
  if (key === "acos" || key === "cvr" || key === "ctr") return formatPercentForReview(value);
  if (key === "roas") return formatRoasForReview(value);
  return String(value);
}

export function recommendationEvidenceChips(
  rec: Recommendation,
  keys: RecommendationMetricKey[] = defaultEvidenceMetricKeys,
): RecommendationMetricChip[] {
  return keys.map((key) => {
    const rawValue = getRecommendationMetric(rec, key);
    return {
      key,
      label: metricLabels[key],
      value: formatRecommendationMetric(key, rawValue),
      rawValue,
    };
  });
}

export function recommendationMetricSnapshot(rec: Recommendation): RecommendationMetricChip[] {
  return recommendationEvidenceChips(rec, ["spend", "sales", "clicks", "orders", "impressions", "acos", "roas", "cvr", "ctr"]);
}

export function recommendationFriendlyReason(rec: Recommendation): string {
  const type = normalizeText(rec.recommendation_type);
  const ruleName = normalizeText(rec.rule_name);
  const spend = getRecommendationMetricNumber(rec, "spend");
  const clicks = getRecommendationMetricNumber(rec, "clicks");
  const orders = getRecommendationMetricNumber(rec, "orders");

  if (orders !== null && clicks !== null && orders > clicks) {
    return "Orders are higher than clicks, which can happen from Amazon attribution timing, but this row should be reviewed before bid changes.";
  }
  if (type.includes("data_quality") || ruleName.includes("data_quality") || ruleName.includes("inconsistent_metrics")) {
    return "Metrics need review before optimization. This row may have attribution or reporting inconsistencies.";
  }
  if (spend !== null && spend > 0 && (orders ?? 0) === 0 && (type.includes("negative") || type === "pause_review")) {
    return "This search term spent money without producing orders. Review it for a possible negative keyword.";
  }
  if (type === "increase_bid") {
    return "This term is converting below the target ACOS and may have room to scale.";
  }
  if (type === "decrease_bid") {
    return "This term has sales but is above the target ACOS, so the bid may need to be reduced.";
  }
  if (type === "move_to_exact" || type.includes("harvest_search_term_to_exact")) {
    return "This converting customer search term may be worth harvesting into an exact match keyword.";
  }
  if (type === "budget_review") {
    return "Budget pressure or efficiency needs a human review before any budget-sensitive change is planned.";
  }
  if (type === "keep_running") {
    return "Performance does not need an optimization action right now. Keep monitoring before changing bids or negatives.";
  }
  if (type === "watch_lock" || type === "watch_only") {
    return "The system recommends watching this item while more performance data accumulates.";
  }
  if (type === "pause_review") {
    return "This item needs a pause review, but no pause action will be exported from this queue.";
  }
  return "Review the metric evidence and approval boundary before deciding.";
}

export function recommendationTechnicalReason(rec: Recommendation): string {
  return [
    rec.explanation_json?.summary,
    rec.explanation_json?.why_flagged,
    rec.explanation_json?.evidence,
    rec.explanation_json?.recommended_action,
  ]
    .map((item) => String(item ?? "").trim())
    .filter(Boolean)
    .join(" ")
    || rec.rule_name
    || "No raw technical explanation was provided.";
}

export function recommendationActionTitle(rec: Recommendation): string {
  const label = recommendationTypeLabel(rec);
  const term = String(rec.customer_search_term || rec.targeting || "").trim();
  return term ? `${label}: ${term}` : label;
}

export function recommendationSummaryCounts(recommendations: Recommendation[]): RecommendationSummaryCounts {
  return recommendations.reduce(
    (summary, rec) => {
      const status = normalizeText(rec.status);
      const actionClass = recommendationActionClass(rec);
      summary.total += 1;
      if (actionClass === "actionable") summary.actionable += 1;
      if (actionClass !== "actionable") summary.reviewOnly += 1;
      if (isRecommendationExportable(rec)) summary.exportable += 1;
      if (status === "pending" || status === "pending_approval") summary.pending += 1;
      if (status === "approved") summary.approved += 1;
      if (status === "rejected") summary.rejected += 1;
      if (["critical", "high"].includes(normalizeText(rec.priority))) summary.criticalHigh += 1;
      return summary;
    },
    { total: 0, actionable: 0, reviewOnly: 0, exportable: 0, pending: 0, approved: 0, rejected: 0, criticalHigh: 0 },
  );
}

export function recommendationMatchesFilters(rec: Recommendation, filters: RecommendationFilters): boolean {
  const status = normalizeText(rec.status);
  const type = normalizeText(rec.recommendation_type);
  const priority = normalizeText(rec.priority);
  const confidence = normalizeText(rec.confidence);
  const actionClass = recommendationActionClass(rec);
  const spend = getRecommendationMetricNumber(rec, "spend") ?? 0;
  const clicks = getRecommendationMetricNumber(rec, "clicks") ?? 0;
  const orders = getRecommendationMetricNumber(rec, "orders") ?? 0;
  const campaignQuery = filters.campaignQuery.trim().toLowerCase();
  const searchTermQuery = filters.searchTermQuery.trim().toLowerCase();

  if (filters.status) {
    const targetStatus = normalizeText(filters.status);
    if (targetStatus === "pending_approval") {
      if (status !== "pending_approval" && status !== "pending") return false;
    } else if (status !== targetStatus) {
      return false;
    }
  }
  if (filters.priority) {
    const targetPriority = normalizeText(filters.priority);
    if (targetPriority === "critical_high") {
      if (priority !== "critical" && priority !== "high") return false;
    } else if (priority !== targetPriority) {
      return false;
    }
  }
  if (filters.recommendationType) {
    const targetType = normalizeText(filters.recommendationType);
    if (targetType === "negative_keywords") {
      if (type !== "add_negative_exact" && type !== "add_negative_phrase") return false;
    } else if (targetType === "bid_changes") {
      if (type !== "increase_bid" && type !== "decrease_bid") return false;
    } else if (type !== targetType) {
      return false;
    }
  }
  if (filters.actionClass && actionClass !== filters.actionClass) return false;
  if (filters.exportability === "exportable" && !isRecommendationExportable(rec)) return false;
  if (filters.exportability === "non_exportable" && isRecommendationExportable(rec)) return false;
  if (filters.confidence && confidence !== normalizeText(filters.confidence)) return false;
  if (campaignQuery && !`${rec.campaign_name ?? ""} ${rec.ad_group_name ?? ""}`.toLowerCase().includes(campaignQuery)) return false;
  if (searchTermQuery && !`${rec.customer_search_term ?? ""} ${rec.targeting ?? ""}`.toLowerCase().includes(searchTermQuery)) return false;
  if (!meetsMinimum(spend, filters.minSpend)) return false;
  if (!meetsMinimum(clicks, filters.minClicks)) return false;
  if (!meetsMinimum(orders, filters.minOrders)) return false;

  return true;
}

export function filterRecommendations(recommendations: Recommendation[], filters: RecommendationFilters): Recommendation[] {
  return recommendations.filter((rec) => recommendationMatchesFilters(rec, filters));
}

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

function getMetricFromRecord(source: unknown, aliases: string[]): unknown {
  if (!isRecord(source)) return undefined;
  const normalizedAliases = new Set(aliases.map(normalizeMetricKey));
  for (const [key, value] of Object.entries(source)) {
    if (normalizedAliases.has(normalizeMetricKey(key))) return value;
  }
  return undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function normalizeText(value: unknown): string {
  return String(value ?? "").trim().toLowerCase();
}

function normalizeMetricKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined || String(value).trim() === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const cleaned = String(value).replace(/[$,%x,\s]/g, "");
  const parsed = Number.parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}

function formatCurrencyForReview(value: unknown): string {
  const number = toNumber(value);
  if (number === null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(number);
}

function formatIntegerForReview(value: unknown): string {
  const number = toNumber(value);
  if (number === null) return "—";
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(Math.round(number));
}

function formatPercentForReview(value: unknown): string {
  const text = String(value ?? "");
  const number = toNumber(value);
  if (number === null) return "—";
  const percent = text.includes("%") ? number : number * 100;
  return `${new Intl.NumberFormat("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 2 }).format(percent)}%`;
}

function formatRoasForReview(value: unknown): string {
  const number = toNumber(value);
  if (number === null) return "—";
  return `${number.toFixed(2)}x`;
}

function meetsMinimum(value: number, filterValue: string): boolean {
  const minimum = Number.parseFloat(filterValue);
  if (!Number.isFinite(minimum)) return true;
  return value >= minimum;
}

function humanizeInternal(value: string): string {
  const brands: Record<string, string> = {
    ai: "AI",
    acos: "ACOS",
    roas: "ROAS",
    cvr: "CVR",
    ctr: "CTR",
    asin: "ASIN",
  };
  const normalized = value.replace(/-/g, "_");
  if (brands[normalized]) return brands[normalized];
  return normalized
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}
