import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("reports page", () => {
  it("renders a workspace report library backed by upload and analysis data", () => {
    const pageSource = readFileSync("src/app/reports/page.tsx", "utf-8");
    const componentSource = readFileSync("src/components/reports/report-library.tsx", "utf-8");
    const sidebarSource = readFileSync("src/components/app-sidebar.tsx", "utf-8");

    expect(pageSource).toContain("ReportLibrary");
    expect(componentSource).toContain("getUploads");
    expect(componentSource).toContain("getUploadParseRuns");
    expect(componentSource).toContain("listAccountImports");
    expect(componentSource).toContain("getProductMonitoring");
    expect(componentSource).toContain("getRecommendations");
    expect(componentSource).toContain('upload.source_type === "amazon_ads_sp_search_term_report"');
    expect(componentSource).toContain("Open monitoring");
    expect(componentSource).toContain("Manage uploaded resources");
    expect(componentSource).toContain("ResourceActionCard");
    expect(sidebarSource).toContain("/reports");
  });
});
