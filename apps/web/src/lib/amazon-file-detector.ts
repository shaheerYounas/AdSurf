/**
 * Client-side Amazon file type detector.
 *
 * Classifies uploaded files by filename pattern so the UI can route them
 * to the correct workflow before even calling the API — giving instant
 * user feedback rather than a round-trip 422 error.
 *
 * Classification precedence:
 *  1. Filename pattern (most reliable — Amazon uses consistent naming)
 *  2. Manual fallthrough to UNKNOWN if unrecognised
 */

export type AmazonFileType =
  | "BULK_OPERATIONS"          // bulk-{accountId}-{start}-{end}-{ts}.xlsx
  | "SP_SEARCH_TERM_REPORT"    // Sponsored_Products_Search_term_report*.xlsx
  | "SP_TARGETING_REPORT"      // Sponsored_Products_Targeting_report*.xlsx
  | "SP_CAMPAIGN_REPORT"       // Sponsored_Products_Campaign_report*.xlsx
  | "SP_ADVERTISED_PRODUCT"    // Sponsored_Products_Advertised_product_report*.xlsx
  | "SB_REPORT"                // Sponsored_Brands_*_report*.xlsx
  | "SD_REPORT"                // Sponsored_Display_*_report*.xlsx
  | "BULK_PRODUCT_CATALOG"     // Generic CSV/XLSX the user intends as a product list
  | "UNKNOWN";

export type FileDetectionResult = {
  type: AmazonFileType;
  confidence: "high" | "medium" | "low";
  suggestedWorkflow: string;
  hint: string;
};

// ---------------------------------------------------------------------------
// Pattern matchers — order matters (most-specific first)
// ---------------------------------------------------------------------------

const PATTERNS: Array<{
  pattern: RegExp;
  type: AmazonFileType;
  confidence: "high" | "medium";
  suggestedWorkflow: string;
  hint: string;
}> = [
  {
    pattern: /^bulk-[a-z0-9]+-\d{8}-\d{8}-\d+\.(xlsx|csv)$/i,
    type: "BULK_OPERATIONS",
    confidence: "high",
    suggestedWorkflow: "bulk-sheet",
    hint: "Amazon Bulk Operations export — shows your full account structure (campaigns, ad groups, keywords).",
  },
  {
    pattern: /sponsored[_\s-]*products[_\s-]*search[_\s-]*term/i,
    type: "SP_SEARCH_TERM_REPORT",
    confidence: "high",
    suggestedWorkflow: "monitoring-import",
    hint: "SP Search Term Report — upload via Monitoring Import to get keyword harvest and negative keyword recommendations.",
  },
  {
    pattern: /sponsored[_\s-]*products[_\s-]*targeting/i,
    type: "SP_TARGETING_REPORT",
    confidence: "high",
    suggestedWorkflow: "monitoring-import",
    hint: "SP Targeting Report — upload via Monitoring Import to analyse keyword performance.",
  },
  {
    pattern: /sponsored[_\s-]*products[_\s-]*campaign/i,
    type: "SP_CAMPAIGN_REPORT",
    confidence: "high",
    suggestedWorkflow: "monitoring-import",
    hint: "SP Campaign Report — upload via Monitoring Import to analyse campaign performance.",
  },
  {
    pattern: /sponsored[_\s-]*products[_\s-]*advertised/i,
    type: "SP_ADVERTISED_PRODUCT",
    confidence: "high",
    suggestedWorkflow: "monitoring-import",
    hint: "SP Advertised Product Report — upload via Monitoring Import.",
  },
  {
    pattern: /sponsored[_\s-]*brands/i,
    type: "SB_REPORT",
    confidence: "high",
    suggestedWorkflow: "monitoring-import",
    hint: "Sponsored Brands report — upload via Monitoring Import.",
  },
  {
    pattern: /sponsored[_\s-]*display/i,
    type: "SD_REPORT",
    confidence: "high",
    suggestedWorkflow: "monitoring-import",
    hint: "Sponsored Display report — upload via Monitoring Import.",
  },
];

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function detectAmazonFileType(filename: string): FileDetectionResult {
  const name = filename.trim();

  for (const { pattern, type, confidence, suggestedWorkflow, hint } of PATTERNS) {
    if (pattern.test(name)) {
      return { type, confidence, suggestedWorkflow, hint };
    }
  }

  const lower = name.toLowerCase();
  if (lower.endsWith(".csv") || lower.endsWith(".xlsx")) {
    return {
      type: "BULK_PRODUCT_CATALOG",
      confidence: "low",
      suggestedWorkflow: "bulk-product-import",
      hint: "Unrecognised file — attempting to import as a product catalog.",
    };
  }

  return {
    type: "UNKNOWN",
    confidence: "low",
    suggestedWorkflow: "bulk-product-import",
    hint: "Unrecognised file type.",
  };
}

export function isBulkOperationsFile(filename: string): boolean {
  return detectAmazonFileType(filename).type === "BULK_OPERATIONS";
}

export function isSpSearchTermReport(filename: string): boolean {
  return detectAmazonFileType(filename).type === "SP_SEARCH_TERM_REPORT";
}

export function isAmazonReport(filename: string): boolean {
  const { type } = detectAmazonFileType(filename);
  return (
    type === "SP_SEARCH_TERM_REPORT" ||
    type === "SP_TARGETING_REPORT" ||
    type === "SP_CAMPAIGN_REPORT" ||
    type === "SP_ADVERTISED_PRODUCT" ||
    type === "SB_REPORT" ||
    type === "SD_REPORT"
  );
}
