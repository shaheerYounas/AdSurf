import { afterEach, describe, expect, it, vi } from "vitest";
import { uploadAccountReport } from "./account-imports";
import { controlAgentRun, getAccountImportAgentWorkflow, getAgents, updateAgentConfig } from "./agents";
import { decideRecommendation, runAccountImportAnalysis } from "./monitoring";
import { createProductProfile, getDashboardSummary } from "./products";

const workspaceId = "00000000-0000-0000-0000-000000000001";

function ok(data: unknown) {
  return new Response(JSON.stringify({ success: true, data }), { status: 200, headers: { "Content-Type": "application/json" } });
}

function created(data: unknown) {
  return new Response(JSON.stringify({ success: true, data }), { status: 201, headers: { "Content-Type": "application/json" } });
}

function fail(message = "Nope", status = 400) {
  return new Response(JSON.stringify({ success: false, error: { message } }), { status, headers: { "Content-Type": "application/json" } });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("frontend API clients", () => {
  it("uploads an account report through init, object write, confirm, processing, and import creation", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(created({ upload_id: "upload-1", storage_path: "/workspaces/ws/account-imports/uploads/upload-1/raw/report.csv" }))
      .mockResolvedValueOnce(ok({ status: "initialized" }))
      .mockResolvedValueOnce(ok({ status: "queued_for_processing", job_id: "job-1" }))
      .mockResolvedValueOnce(ok({ processed: 1 }))
      .mockResolvedValueOnce(ok({ import_record: { id: "import-1", status: "ready_for_analysis", detected_report_type: "sponsored_products_search_term_report", detection_confidence: "high", total_rows: 2, processed_rows: 2, error_rows: 0 }, detection: { detected_report_type: "sponsored_products_search_term_report", confidence: "high", required_columns_present: true, missing_columns: [], available_entity_levels: ["account"], product_identifiers_available: [] }, entities: [], product_mapping_suggestions: [] }));
    const progress: string[] = [];

    const result = await uploadAccountReport(new File(["Campaign Name\nCamp1\n"], "report.csv", { type: "text/csv" }), workspaceId, {
      onProgress: (step) => progress.push(step),
    });

    expect(result.import_record.id).toBe("import-1");
    expect(progress).toEqual(["initializing_upload", "storing_file", "confirming_upload", "processing_file", "creating_account_import"]);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining(`/v1/workspaces/${workspaceId}/uploads/init`), expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, expect.stringContaining(`/v1/workspaces/${workspaceId}/uploads/upload-1/object`), expect.objectContaining({ method: "PUT" }));
    expect(fetchMock).toHaveBeenNthCalledWith(3, expect.stringContaining(`/v1/workspaces/${workspaceId}/uploads/upload-1/confirm`), expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(4, expect.stringContaining("/v1/dev/process-upload-jobs"), expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(5, expect.stringContaining(`/v1/workspaces/${workspaceId}/account-imports`), expect.objectContaining({ method: "POST" }));
  });

  it("surfaces account report upload failures", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(fail("Database operation failed. Check migrations.", 503));

    await expect(uploadAccountReport(new File(["x"], "report.csv", { type: "text/csv" }), workspaceId)).rejects.toThrow("Database operation failed. Check migrations.");
  });

  it("loads agents", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(ok([{ agent_id: "report_upload_node" }]));

    await expect(getAgents(workspaceId)).resolves.toEqual([{ agent_id: "report_upload_node" }]);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining(`/v1/workspaces/${workspaceId}/agents`), expect.objectContaining({ cache: "no-store" }));
  });

  it("updates agent config", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(ok({ agent_id: "metrics_analysis_agent", mode: "hybrid" }));

    await updateAgentConfig("metrics_analysis_agent", { reason: "test", mode: "hybrid" }, workspaceId);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/agent-configs/metrics_analysis_agent"), expect.objectContaining({ method: "PATCH", body: expect.stringContaining("\"reason\":\"test\"") }));
  });

  it("controls agent runs", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(ok({ id: "run-1", status: "paused" }));

    await controlAgentRun("run-1", "pause", "testing", workspaceId);
    expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/agent-runs/run-1/pause"), expect.objectContaining({ method: "POST", body: JSON.stringify({ reason: "testing" }) }));
  });

  it("runs account import analysis and loads account workflow", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(ok({ account_import_id: "import-1", status: "succeeded", run_count: 11, recommendation_count: 3, execution_boundary: "no_live_amazon_change" }))
      .mockResolvedValueOnce(ok({ monitoring_import_id: "import-1", nodes: [], edges: [], events: [] }));

    await runAccountImportAnalysis("import-1", workspaceId);
    await getAccountImportAgentWorkflow("import-1", workspaceId);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining(`/v1/workspaces/${workspaceId}/account-imports/import-1/run-analysis`), expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, expect.stringContaining(`/v1/workspaces/${workspaceId}/account-imports/import-1/agent-workflow`), expect.objectContaining({ cache: "no-store" }));
  });

  it("creates products and loads dashboard summary", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(created({ id: "product-1", product_name: "Shoe" }))
      .mockResolvedValueOnce(ok({ products: [], product_count: 0, upload_count: 0, upload_counts: {}, pending_recommendation_count: 0, recommendation_counts: {}, top_recommendations: [] }));

    await createProductProfile({ product_name: "Shoe", marketplace: "US", currency: "USD", target_acos: "0.25", default_budget: "25", default_bid: "0.75" }, workspaceId);
    await getDashboardSummary(workspaceId);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining(`/v1/workspaces/${workspaceId}/products`), expect.objectContaining({ method: "POST" }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, expect.stringContaining(`/v1/workspaces/${workspaceId}/dashboard-summary`), expect.objectContaining({ cache: "no-store" }));
  });

  it("approves and rejects recommendations", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(ok({ id: "rec-1", status: "approved" }))
      .mockResolvedValueOnce(ok({ id: "rec-2", status: "rejected" }));

    await decideRecommendation("rec-1", "approve", "looks good", workspaceId);
    await decideRecommendation("rec-2", "reject", "not enough evidence", workspaceId);
    expect(fetchMock).toHaveBeenNthCalledWith(1, expect.stringContaining("/recommendations/rec-1/approve"), expect.objectContaining({ method: "POST", body: JSON.stringify({ note: "looks good" }) }));
    expect(fetchMock).toHaveBeenNthCalledWith(2, expect.stringContaining("/recommendations/rec-2/reject"), expect.objectContaining({ method: "POST", body: JSON.stringify({ note: "not enough evidence" }) }));
  });
});
