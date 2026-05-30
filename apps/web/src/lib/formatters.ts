// Human-friendly metric formatters for recommendation cards and dashboards.

/**
 * Format a decimal ACOS value (e.g., 0.2589) to a percentage string (e.g., "25.89%").
 */
export function formatACOS(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  return `${(num * 100).toFixed(2)}%`;
}

/**
 * Format a decimal ROAS value (e.g., 3.8628) to a multiplier string (e.g., "3.86x").
 */
export function formatROAS(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  return `${num.toFixed(2)}x`;
}

/**
 * Format a numeric value as US currency (e.g., 6295.16 → "$6,295.16").
 */
export function formatCurrency(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const num = typeof value === "string" ? parseFloat(value) : value;
  if (isNaN(num)) return "—";
  return `$${num.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/**
 * Format a number with locale grouping (e.g., 1495 → "1,495").
 */
export function formatInteger(value: number | string | null | undefined): string {
  if (value == null) return "—";
  const num = typeof value === "string" ? parseInt(value, 10) : Math.round(value);
  if (isNaN(num)) return "—";
  return num.toLocaleString("en-US");
}

/**
 * Format any metric value by key name. Falls back to raw string if unknown.
 */
export function formatMetricValue(key: string, value: unknown): string {
  const lower = key.toLowerCase();
  if (lower.includes("acos") || lower.includes("acoss") || lower === "cpa_percentage") {
    return formatACOS(value as number | string | null);
  }
  if (lower.includes("roas")) {
    return formatROAS(value as number | string | null);
  }
  if (
    lower.includes("spend") ||
    lower.includes("sales") ||
    lower.includes("cost") ||
    lower.includes("revenue") ||
    lower.includes("budget") ||
    lower.includes("cpc") ||
    lower.includes("cpa") ||
    lower === "avg_order_value"
  ) {
    return formatCurrency(value as number | string | null);
  }
  if (
    lower.includes("click") ||
    lower.includes("impression") ||
    lower.includes("order") ||
    lower.includes("conversion") ||
    lower.includes("row") ||
    lower.includes("count")
  ) {
    return formatInteger(value as number | string | null);
  }
  if (typeof value === "number") {
    // If it looks like a decimal ratio, show as percent
    if (value < 1 && value > -1 && value !== 0) return formatACOS(value);
    return formatInteger(value);
  }
  return String(value ?? "—");
}

/**
 * Fix common typo labels (e.g., "Spnd" → "Spend").
 */
export function fixMetricLabel(key: string): string {
  const fixes: Record<string, string> = {
    spnd: "Spend",
    impr: "Impressions",
    clks: "Clicks",
    ordrs: "Orders",
    sls: "Sales",
  };
  const lower = key.replace(/_/g, "").toLowerCase();
  if (fixes[lower]) return fixes[lower];

  // General humanize: replace underscores, capitalize each word
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (l) => l.toUpperCase());
}