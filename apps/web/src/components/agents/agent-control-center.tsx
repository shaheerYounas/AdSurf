"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  BarChart3,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  Eye,
  FileSearch,
  GitBranch,
  Layers3,
  ListOrdered,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Square,
  UploadCloud,
  X,
  AlertTriangle,
  Info,
  ShieldCheck,
} from "lucide-react";
import { AgentInspector } from "@/components/agents/agent-inspector";
import { AgentTraceTimeline } from "@/components/agents/agent-trace-timeline";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/select";
import { defaultWorkspaceId } from "@/lib/api/client";
import {
  controlAgentRun,
  getAccountImportAgentWorkflow,
  getAgentConfigs,
  getAgentRuns,
  getAgentWorkflow,
  getAgents,
  rerunFromAgent,
  updateAgentConfig,
  type AgentConfig,
  type AgentDefinition,
  type AgentEvent,
  type AgentRun,
  type AgentWorkflow,
} from "@/lib/api/agents";
import { uploadAccountReport, type AccountImportResponse, type UploadAccountReportProgress } from "@/lib/api/account-imports";
import { decideRecommendation, getRecommendations, runAccountImportAnalysis, runMonitoringAnalysis, type Recommendation } from "@/lib/api/monitoring";
import { controlWorkflow, getWorkflow, getWorkflowEvents, type WorkflowEvent, type WorkflowSummary } from "@/lib/api/workflows";
import { formatMetricValue, fixMetricLabel } from "@/lib/formatters";
import {
  recommendationTitle,
  recommendationReason,
  recommendedAction,
  recommendationWarnings,
  approvalImpact,
  recommendationDisplayName,
} from "@/lib/recommendation-helpers";

type ControlAction = "pause" | "resume" | "stop" | "rerun";
type ViewMode = "pipeline" | "canvas";
type UploadStatusMessage = { kind: "idle" | "loading" | "success" | "error"; text: string; detail?: string };

const workflowOrder = [
  "report_upload_node",
  "import_data_quality_agent",
  "entity_resolution_agent",
  "metrics_normalization_agent",
  "account_strategy_agent",
  "search_term_mining_agent",
  "bid_optimization_agent",
  "negative_keyword_agent",
  "budget_reallocation_agent",
  "campaign_structure_agent",
  "risk_policy_validator_agent",
  "human_approval_agent",
  "bulk_change_compiler_agent",
  "learning_feedback_agent",
  "stakeholder_reporting_agent",
];

const fallbackAgents: AgentDefinition[] = [
  definition("report_upload_node", "Report Upload", "Receives Amazon Ads reports or bulk sheets and starts the account workflow.", "start", "uploaded_report"),
  definition("import_data_quality_agent", "Import & Data Quality Agent", "Checks uploaded reports for missing columns, wrong date ranges, mixed marketplaces, and other data quality issues.", "validation", "data_quality_report"),
  definition("entity_resolution_agent", "Entity Resolution Agent", "Maps campaigns, ad groups, SKUs, ASINs, search terms, keywords, and targeting expressions.", "mapping", "entity_mapping"),
  definition("metrics_normalization_agent", "Metrics Normalization Agent", "Calculates spend, sales, orders, CPC, CTR, CVR, ACOS, ROAS, CPA deterministically.", "analysis", "normalized_metrics"),
  definition("account_strategy_agent", "Account Strategy Agent", "Determines the optimization goal: profit, growth, launch, cleanup, brand defense.", "strategy", "strategy_configuration"),
  definition("search_term_mining_agent", "Search Term Mining Agent", "Classifies search terms: harvest, keep, negative, watch, ignore, brand defense, competitor term.", "analysis", "search_term_classifications"),
  definition("bid_optimization_agent", "Bid Optimization Agent", "Generates bid increase/decrease/set actions with current bid, recommended bid, and evidence.", "decision", "bid_recommendations"),
  definition("negative_keyword_agent", "Negative Keyword Agent", "Reviews wasted search terms and generates negative exact/phrase recommendations.", "decision", "negative_keyword_recommendations"),
  definition("budget_reallocation_agent", "Budget Reallocation Agent", "Recommends budget shifts: out-of-budget profitable campaigns, spending-but-unprofitable, no impressions.", "decision", "budget_recommendations"),
  definition("campaign_structure_agent", "Campaign Structure Agent", "Recommends moving converting terms to exact, separating branded/non-branded, isolating hero terms.", "decision", "campaign_structure_recommendations"),
  definition("risk_policy_validator_agent", "Risk & Policy Validator Agent", "Rejects unsafe actions: bid increase above max, pause with little data, recommendations without evidence.", "validation", "validation_report"),
  definition("human_approval_agent", "Human Approval Agent", "Routes recommendations to humans and prevents automatic approval.", "approval", "approval_queue"),
  definition("bulk_change_compiler_agent", "Bulk Change Compiler Agent", "Generates approved-changes table, bulk upload file, audit log, before/after, and rollback reference.", "export", "bulk_export"),
  definition("learning_feedback_agent", "Learning & Feedback Agent", "Tracks whether implemented changes improved metrics. Builds optimization memory over time.", "analysis", "learning_report"),
  definition("stakeholder_reporting_agent", "Stakeholder Reporting Agent", "Produces executive summaries and approver notes.", "reporting", "stakeholder_summary"),
];

const templates = [
  ["Conservative Profitability Team", "High confidence thresholds, strict pause/negative controls, profit-first recommendations."],
  ["Growth Scaling Team", "Deeper analysis, scaling toggles, winner expansion, and campaign-level opportunities."],
  ["Wasted Spend Cleanup Team", "Focuses on no-order spend, negative keywords, and pause-review candidates."],
  ["Launch Campaign Review Team", "Protects new products with conservative evidence thresholds and data-quality checks."],
  ["Agency Account Audit Team", "Account-wide audit view for products, campaigns, budgets, and approver summaries."],
];

const statusTone: Record<string, string> = {
  idle: "border-slate-300 bg-slate-100 text-slate-700 dark:border-white/15 dark:bg-white/10 dark:text-slate-200",
  waiting: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100",
  running: "border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100",
  queued: "border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100",
  completed: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
  succeeded: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
  failed: "border-red-300 bg-red-50 text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100",
  paused: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100",
  stopped: "border-zinc-300 bg-zinc-100 text-zinc-800 dark:border-white/15 dark:bg-white/10 dark:text-zinc-100",
  approval_needed: "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-300/25 dark:bg-violet-300/10 dark:text-violet-100",
  skipped: "border-slate-300 bg-slate-50 text-slate-700 dark:border-white/15 dark:bg-white/10 dark:text-slate-200",
};

export function AgentControlCenter({ productId, importId }: { productId?: string; importId?: string }) {
  const workspaceId = defaultWorkspaceId;
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [workflow, setWorkflow] = useState<AgentWorkflow | null>(null);
  const [durableWorkflow, setDurableWorkflow] = useState<WorkflowSummary | null>(null);
  const [workflowEvents, setWorkflowEvents] = useState<WorkflowEvent[]>([]);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("report_upload_node");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [drawerAgentId, setDrawerAgentId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [accountImport, setAccountImport] = useState<AccountImportResponse | null>(null);
  const [uploadStatus, setUploadStatus] = useState<UploadStatusMessage>({ kind: "idle", text: "No report uploaded yet." });
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [isRunningAnalysis, setIsRunningAnalysis] = useState(false);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>("pipeline");
  const [environmentMode, setEnvironmentMode] = useState<AgentConfig["mode"]>("hybrid");
  const activeImportId = accountImport?.import_record.id ?? importId ?? null;
  const activeWorkflowId = accountImport?.workflow_id ?? durableWorkflow?.workflow.id ?? null;
  const activeImportKind: "account" | "monitoring" | null = accountImport ? "account" : importId ? "monitoring" : null;

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const agentCatalog = useMemo(() => mergeAgents(agents), [agents]);
  const configByAgent = useMemo(() => new Map(configs.map((config) => [config.agent_id, config])), [configs]);
  const latestRunByAgent = useMemo(() => {
    const map = new Map<string, AgentRun>();
    for (const run of runs) if (!map.has(run.agent_id)) map.set(run.agent_id, run);
    return map;
  }, [runs]);
  const workflowNodes = useMemo(() => buildWorkflowNodes({ agentCatalog, configByAgent, latestRunByAgent, workflow, recommendations }), [agentCatalog, configByAgent, latestRunByAgent, workflow, recommendations]);
  const workflowEdges = useMemo(() => buildWorkflowEdges(workflow), [workflow]);
  const selectedAgent = agentCatalog.find((agent) => agent.agent_id === selectedAgentId) ?? agentCatalog[0];
  const drawerAgent = drawerAgentId ? (agentCatalog.find((a) => a.agent_id === drawerAgentId) ?? null) : null;
  const drawerRun = drawerAgentId ? (latestRunByAgent.get(drawerAgentId) ?? null) : null;
  const drawerConfig = drawerAgentId ? (configByAgent.get(drawerAgentId) ?? undefined) : undefined;
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? latestRunByAgent.get(selectedAgent?.agent_id ?? "");
  const selectedConfig = selectedAgent ? configByAgent.get(selectedAgent.agent_id) : undefined;
  const visibleEvents = workflowEvents.length ? workflowEvents.map(workflowEventToAgentEvent) : workflow?.events ?? runs.map(runToEvent);
  const pendingApprovals = recommendations.filter((item) => item.status === "pending_approval" || item.status === "pending");
  const highPriorityApprovals = pendingApprovals.filter((item) => ["critical", "high"].includes(item.priority));
  const dangerousApprovals = pendingApprovals.filter((item) => ["pause_review", "add_negative_exact", "add_negative_phrase", "decrease_bid"].includes(item.recommendation_type));
  const activeCount = workflowNodes.filter((node) => ["running", "queued"].includes(node.status)).length;
  const failedCount = workflowNodes.filter((node) => node.status === "failed").length;
  const completedCount = workflowNodes.filter((node) => ["completed", "succeeded"].includes(node.status)).length;

  async function load(importOverride?: { id: string; kind: "account" | "monitoring"; workflowId?: string | null }) {
    const workflowImportId = importOverride?.id ?? activeImportId;
    const workflowImportKind = importOverride?.kind ?? activeImportKind;
    setIsLoading(true);
    setMessage(null);
    try {
      const [agentsResult, configsResult, runsResult, recommendationsResult] = await Promise.allSettled([
        getAgents(workspaceId),
        getAgentConfigs(workspaceId, productId),
        getAgentRuns(workspaceId, workflowImportId ?? undefined),
        getRecommendations(workspaceId),
      ]);
      if (agentsResult.status === "rejected") throw agentsResult.reason;
      if (configsResult.status === "rejected") throw configsResult.reason;
      if (runsResult.status === "rejected") throw runsResult.reason;
      const loadedAgents = agentsResult.value;
      const loadedConfigs = configsResult.value;
      const loadedRuns = runsResult.value;
      const loadedRecommendations = recommendationsResult.status === "fulfilled" ? recommendationsResult.value : [];
      setAgents(loadedAgents);
      setConfigs(loadedConfigs);
      setRuns(loadedRuns);
      setRecommendations(loadedRecommendations);
      if (workflowImportId && workflowImportKind === "account") setWorkflow(await getAccountImportAgentWorkflow(workflowImportId, workspaceId));
      if (workflowImportId && workflowImportKind === "monitoring") setWorkflow(await getAgentWorkflow(workflowImportId, workspaceId));
      const workflowId = importOverride?.workflowId ?? accountImport?.workflow_id ?? durableWorkflow?.workflow.id ?? null;
      if (workflowId) {
        const [summary, events] = await Promise.all([getWorkflow(workflowId, workspaceId), getWorkflowEvents(workflowId, workspaceId)]);
        setDurableWorkflow(summary);
        setWorkflowEvents(events);
      }
      setEnvironmentMode(loadedConfigs[0]?.mode ?? "hybrid");
      if (recommendationsResult.status === "rejected") {
        setMessage(recommendationsResult.reason instanceof Error ? recommendationsResult.reason.message : "Recommendations could not be loaded.");
      }
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Agent Control Center could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadReport() {
    if (!selectedFile) {
      setUploadStatus({ kind: "error", text: "Choose a CSV, XLS, or XLSX Amazon Ads report before uploading." });
      return;
    }
    setIsUploading(true);
    setMessage(null);
    setUploadStatus({ kind: "loading", text: "Starting upload.", detail: selectedFile.name });
    try {
      const result = await uploadAccountReport(selectedFile, workspaceId, {
        onProgress: (step: UploadAccountReportProgress, detail?: string) => {
          setUploadStatus({ kind: "loading", text: uploadStepLabel(step), detail });
        },
      });
      setAccountImport(result);
      setDurableWorkflow(null);
      setWorkflowEvents([]);
      setSelectedAgentId("report_detection_agent");
      setUploadStatus({
        kind: "success",
        text: "Report uploaded, parsed, detected, and grouped.",
        detail: `Import ${result.import_record.id}${result.workflow_id ? ` · Workflow ${result.workflow_id}` : ""} · ${result.import_record.processed_rows} rows · ${result.entities.length} entities`,
      });
      setMessage("Report detected, entities grouped, and product mapping suggestions prepared.");
      setWorkflow(null);
      await load({ id: result.import_record.id, kind: "account", workflowId: result.workflow_id });
    } catch (caught) {
      if (process.env.NODE_ENV !== "production") console.error("Account report upload failed", caught);
      const text = caught instanceof Error ? caught.message : "Account report upload could not be completed.";
      setUploadStatus({ kind: "error", text, detail: "Check API health, migrations, storage, and worker processing." });
      setMessage(text);
    } finally {
      setIsUploading(false);
    }
  }

  async function saveConfig(agentId: string, patch: Partial<AgentConfig>) {
    setMessage(null);
    try {
      setIsSavingConfig(true);
      await updateAgentConfig(agentId, { ...patch, product_id: productId ?? null, reason: "Updated from Agent Control Center" }, workspaceId);
      setMessage("Agent configuration saved.");
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Agent configuration could not be saved.");
    } finally {
      setIsSavingConfig(false);
    }
  }

  async function updateEnvironmentMode(mode: AgentConfig["mode"]) {
    setEnvironmentMode(mode);
    setIsSavingConfig(true);
    setMessage(`Saving ${mode} mode across agents.`);
    try {
      const knownAgentIds = new Set(agentCatalog.map((agent) => agent.agent_id));
      const targetAgentIds = new Set<string>(knownAgentIds);
      for (const config of configs) if (knownAgentIds.has(config.agent_id)) targetAgentIds.add(config.agent_id);
      const results = await Promise.allSettled(
        Array.from(targetAgentIds).map((agentId) =>
          updateAgentConfig(agentId, { mode, product_id: productId ?? null, reason: "Environment mode updated from top bar" }, workspaceId),
        ),
      );
      const failures = results.filter((r) => r.status === "rejected").length;
      if (failures === results.length) throw new Error("Environment mode could not be saved.");
      setMessage(failures
        ? `Environment mode saved as ${mode} for ${results.length - failures} of ${results.length} agents. ${failures} unsupported agents were skipped.`
        : `Environment mode saved as ${mode}.`);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Environment mode could not be saved.");
    } finally {
      setIsSavingConfig(false);
    }
  }

  function openDrawer(agentId: string, runId?: string | null) {
    setDrawerAgentId(agentId);
    if (runId) setSelectedRunId(runId);
  }

  function closeDrawer() {
    setDrawerAgentId(null);
  }

  function openTrace(agentId?: string, runId?: string | null) {
    if (agentId) setSelectedAgentId(agentId);
    setSelectedRunId(runId ?? null);
    document.getElementById("agent-trace-timeline")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function controlActiveWorkflow(action: ControlAction) {
    if (!activeWorkflowId) return false;
    setMessage(`${action} requested for workflow ${activeWorkflowId}.`);
    try {
      await controlWorkflow(activeWorkflowId, action, `${action} requested from Agent Control Center`, workspaceId);
      const [summary, events] = await Promise.all([getWorkflow(activeWorkflowId, workspaceId), getWorkflowEvents(activeWorkflowId, workspaceId)]);
      setDurableWorkflow(summary);
      setWorkflowEvents(events);
      setMessage(`Workflow ${action} saved. No live Amazon Ads change executed.`);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : `Workflow ${action} could not be saved.`);
    }
    return true;
  }

  async function toggleAgent(agentId: string) {
    const current = configByAgent.get(agentId);
    if (!current) {
      setMessage("Agent configuration is still loading. Try again in a moment.");
      return;
    }
    await saveConfig(agentId, { enabled: !current.enabled });
  }

  async function control(run: AgentRun | undefined, action: ControlAction) {
    if (!run) {
      setMessage("No agent run is available for this action yet. Upload a report and run analysis first.");
      return;
    }
    setMessage(null);
    try {
      await controlAgentRun(run.id, action, `${action} requested from Agent Control Center`, workspaceId);
      setMessage(`Agent ${action} request saved.`);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : `Agent ${action} request could not be saved.`);
    }
  }

  async function rerunHere(agentId: string) {
    if (!importId) {
      setMessage("Select an import-level workflow before rerunning from a specific agent.");
      return;
    }
    try {
      await rerunFromAgent(importId, agentId, "Rerun from this agent onward", workspaceId);
      setMessage("Agent rerun queued.");
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Agent rerun could not be queued.");
    }
  }

  async function applyTemplate(name: string) {
    const patch = templatePatch(name);
    setMessage(null);
    try {
      await Promise.all(agentCatalog.map((agent) => updateAgentConfig(agent.agent_id, { ...patch, product_id: productId ?? null, reason: `${name} template applied` }, workspaceId)));
      setMessage(`${name} applied to all agents.`);
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : `${name} could not be applied.`);
    }
  }

  async function decide(recommendationId: string, decision: "approve" | "reject") {
    setMessage(null);
    const previous = recommendations;
    setRecommendations((current) => current.map((item) => item.id === recommendationId ? { ...item, status: decision === "approve" ? "approved" : "rejected" } : item));
    try {
      await decideRecommendation(recommendationId, decision, `${decision} from Agent Control Center after human review.`, workspaceId);
      setMessage(`Recommendation ${decision} recorded. No live Amazon Ads change executed.`);
      await load();
    } catch (caught) {
      setRecommendations(previous);
      setMessage(caught instanceof Error ? caught.message : `Recommendation ${decision} could not be saved.`);
      throw caught;
    }
  }

  async function runAnalysis() {
    if (!activeImportId || !activeImportKind) {
      setMessage("Upload a report or open an import-level workflow before running analysis.");
      return;
    }
    setIsRunningAnalysis(true);
    setMessage("Running agents across the selected import. Recommendation only; human approval is required.");
    try {
      if (activeImportKind === "account" && activeWorkflowId) {
        await controlWorkflow(activeWorkflowId, "rerun", "Run analysis requested from Agent Control Center", workspaceId);
        setMessage(`Workflow rerun queued for ${activeWorkflowId}. No live Amazon Ads change executed.`);
      } else if (activeImportKind === "account") {
        const result = await runAccountImportAnalysis(activeImportId, workspaceId);
        setMessage(`Agent analysis completed: ${result.run_count} agents ran and ${result.recommendation_count} recommendations were created. No live Amazon Ads change executed.`);
      } else {
        await runMonitoringAnalysis(activeImportId, workspaceId);
        setMessage("Monitoring analysis queued. No live Amazon Ads change executed.");
      }
      await load();
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Analysis could not be started.");
    } finally {
      setIsRunningAnalysis(false);
    }
  }

  return (
    <main className="mx-auto min-w-0 max-w-[1600px] space-y-8">
      <TopCommandBar
        environmentMode={environmentMode}
        isLoading={isLoading || isRunningAnalysis || isSavingConfig}
        onEnvironmentChange={updateEnvironmentMode}
        onRefresh={load}
        onRunAnalysis={runAnalysis}
        onBulkControl={async (action) => {
          if (await controlActiveWorkflow(action)) return;
          const targetRuns = runs.filter((run) => {
            if (action === "resume") return run.status === "paused";
            if (action === "rerun") return run.status === "failed";
            return ["running", "queued", "failed", "paused"].includes(run.status);
          });
          if (!targetRuns.length) {
            setMessage(`No eligible agent runs found for "${action}". Upload a report and run analysis first, or select an import with matching run status.`);
            return;
          }
          setMessage(`${action} requested for ${targetRuns.length} agent runs.`);
          void Promise.all(targetRuns.map((run) => controlAgentRun(run.id, action, `${action} all from Agent Control Center`, workspaceId))).then(() => {
            setMessage(`${action} saved for ${targetRuns.length} agent runs. No live Amazon Ads change executed.`);
            return load();
          }).catch((caught) => setMessage(caught instanceof Error ? caught.message : `Bulk ${action} could not be saved.`));
        }}
        onViewApprovals={() => document.getElementById("approval-checkpoints")?.scrollIntoView({ behavior: "smooth" })}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
      />

      {message ? <div className="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-semibold text-indigo-900 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">{message}</div> : null}

      <section className="min-w-0 space-y-8">
        <HeroUpload
          accountImport={accountImport}
          completedCount={completedCount}
          failedCount={failedCount}
          activeCount={activeCount}
          pendingApprovals={pendingApprovals.length}
          selectedFile={selectedFile}
          isUploading={isUploading}
          onFileChange={setSelectedFile}
          onUpload={uploadReport}
          viewMode={viewMode}
          onViewModeChange={setViewMode}
          uploadStatus={uploadStatus}
          workspaceId={workspaceId}
        />

        {viewMode === "pipeline" ? (
          agents.length === 0 && isLoading ? (
            <div className="space-y-3 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-6">
              <div className="mb-4 space-y-2">
                <div className="h-5 w-32 animate-pulse rounded-xl bg-slate-200 dark:bg-white/10" />
                <div className="h-4 w-48 animate-pulse rounded-xl bg-slate-200 dark:bg-white/10" />
              </div>
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="h-20 animate-pulse rounded-2xl bg-slate-200 dark:bg-white/10" />
              ))}
            </div>
          ) : (
            <SimplePipelineView
              agents={agentCatalog}
              configByAgent={configByAgent}
              latestRunByAgent={latestRunByAgent}
              selectedAgentId={selectedAgentId}
              onSelect={(agentId, runId) => {
                setSelectedAgentId(agentId);
                setSelectedRunId(runId ?? null);
              }}
              onOpenDrawer={(agentId, runId) => openDrawer(agentId, runId)}
            />
          )
        ) : (
          <>
            {workflowNodes.length === 0 && isLoading ? (
              <div className="space-y-3 rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-6">
                <div className="mb-4 space-y-2">
                  <div className="h-5 w-40 animate-pulse rounded-xl bg-slate-200 dark:bg-white/10" />
                  <div className="h-4 w-64 animate-pulse rounded-xl bg-slate-200 dark:bg-white/10" />
                </div>
                <div className="flex gap-4 overflow-hidden">
                  {Array.from({ length: 3 }).map((_, i) => (
                    <div key={i} className="h-44 w-[220px] shrink-0 animate-pulse rounded-3xl bg-slate-200 dark:bg-white/10" />
                  ))}
                </div>
              </div>
            ) : (
              <WorkflowCanvas nodes={workflowNodes} edges={workflowEdges} selectedAgentId={selectedAgentId} onSelect={setSelectedAgentId} />
            )}

            {agents.length === 0 && isLoading ? (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
                {Array.from({ length: 6 }).map((_, i) => (
                  <div key={i} className="h-64 animate-pulse rounded-3xl bg-slate-200 dark:bg-white/10" />
                ))}
              </div>
            ) : (
              <AgentTeamDashboard
                agents={agentCatalog}
                configByAgent={configByAgent}
                latestRunByAgent={latestRunByAgent}
                selectedAgentId={selectedAgentId}
                onSelect={(agentId, runId) => {
                  setSelectedAgentId(agentId);
                  setSelectedRunId(runId ?? null);
                }}
                onOpenDrawer={(agentId, runId) => openDrawer(agentId, runId)}
                onViewTrace={(agentId, runId) => openTrace(agentId, runId)}
              />
            )}
          </>
        )}

        <ApprovalCheckpointSummary
          pendingApprovals={pendingApprovals}
          highPriorityCount={highPriorityApprovals.length}
          dangerousCount={dangerousApprovals.length}
          onDecision={decide}
        />

        <div id="agent-trace-timeline">
          <AgentTraceTimeline events={visibleEvents} runs={runs} />
        </div>

        {viewMode === "canvas" ? <AgentTemplates onApply={applyTemplate} /> : null}
      </section>

      {/* Agent Details Drawer */}
      {drawerAgent && (
        <>
          <div className="fixed inset-0 z-40 bg-slate-950/30 backdrop-blur-sm transition-opacity" onClick={closeDrawer} />
          <aside className="fixed inset-y-0 right-0 z-50 w-full max-w-lg overflow-auto border-l border-slate-200 bg-white shadow-2xl shadow-slate-950/20 dark:border-white/10 dark:bg-slate-950 sm:max-w-xl">
            <div className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200 bg-white/95 px-5 py-4 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/95">
              <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Agent Details</h2>
              <button
                className="flex h-9 w-9 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition hover:bg-slate-100 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:bg-white/10"
                onClick={closeDrawer}
                type="button"
                aria-label="Close drawer"
              >
                <X size={18} />
              </button>
            </div>
            <div className="p-5">
              <AgentInspector
                agent={drawerAgent}
                config={drawerConfig}
                run={drawerRun ?? undefined}
                events={visibleEvents}
                recommendations={recommendations}
                advancedMode={true}
                isLoading={isLoading}
                onConfigChange={(patch) => saveConfig(drawerAgent.agent_id, patch)}
                onToggleAgent={() => toggleAgent(drawerAgent.agent_id)}
              />
            </div>
          </aside>
        </>
      )}
    </main>
  );
}

function TopCommandBar({ environmentMode, isLoading, onEnvironmentChange, onRefresh, onRunAnalysis, onBulkControl, onViewApprovals, viewMode, onViewModeChange }: { environmentMode: AgentConfig["mode"]; isLoading: boolean; onEnvironmentChange: (mode: AgentConfig["mode"]) => void; onRefresh: () => void; onRunAnalysis: () => void; onBulkControl: (action: ControlAction) => void | Promise<void>; onViewApprovals: () => void; viewMode: ViewMode; onViewModeChange: (mode: ViewMode) => void }) {
  const [bulkOpen, setBulkOpen] = useState(false);
  const bulkButtonRef = useRef<HTMLButtonElement>(null);
  const [dropdownStyle, setDropdownStyle] = useState<React.CSSProperties>({});

  const openBulk = useCallback(() => {
    if (bulkOpen) {
      setBulkOpen(false);
      return;
    }
    const rect = bulkButtonRef.current?.getBoundingClientRect();
    if (rect) {
      setDropdownStyle({
        position: "fixed",
        top: rect.bottom + 8,
        right: window.innerWidth - rect.right,
        zIndex: 9999,
      });
    }
    setBulkOpen(true);
  }, [bulkOpen]);

  useEffect(() => {
    if (!bulkOpen) return;
    function handleResizeOrScroll() {
      const rect = bulkButtonRef.current?.getBoundingClientRect();
      if (rect) {
        setDropdownStyle({
          position: "fixed",
          top: rect.bottom + 8,
          right: window.innerWidth - rect.right,
          zIndex: 9999,
        });
      }
    }
    window.addEventListener("resize", handleResizeOrScroll);
    window.addEventListener("scroll", handleResizeOrScroll, true);
    return () => {
      window.removeEventListener("resize", handleResizeOrScroll);
      window.removeEventListener("scroll", handleResizeOrScroll, true);
    };
  }, [bulkOpen]);

  return (
    <section className="rounded-3xl border border-white/70 bg-white/90 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/5 sm:px-5 sm:py-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-white">Agent Control Center</h1>
          <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-300">Upload Amazon Ads reports and review AI recommendations before any action is taken.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Select
            options={[
              { value: "deterministic", label: "Deterministic" },
              { value: "ai", label: "AI" },
              { value: "hybrid", label: "Hybrid" },
            ]}
            value={environmentMode}
            onChange={(v) => onEnvironmentChange(v as AgentConfig["mode"])}
            className="w-[170px]"
          />
          <Button onClick={onRunAnalysis} type="button" variant="primary"><Play size={15} /> Run analysis</Button>

          <span ref={bulkButtonRef} className="inline-flex">
            <Button onClick={openBulk} size="sm" type="button" variant="secondary">
              <Pause size={14} />
              <span>Bulk</span>
              <ChevronDown size={12} className={`shrink-0 text-slate-400 transition-transform ${bulkOpen ? "rotate-180" : ""}`} />
            </Button>
          </span>

          {bulkOpen && createPortal(
            <>
              <div className="fixed inset-0 z-[9998]" onClick={() => setBulkOpen(false)} />
              <div style={dropdownStyle} className="w-56 rounded-2xl border border-slate-200 bg-white py-2 shadow-xl shadow-slate-950/10 dark:border-white/10 dark:bg-slate-900">
                <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-400 dark:text-slate-500">
                  Bulk Actions
                </div>
                {([
                  { action: "pause" as ControlAction, label: "Pause all", icon: <Pause size={15} />, desc: "Pause eligible agent runs" },
                  { action: "resume" as ControlAction, label: "Resume all", icon: <Play size={15} />, desc: "Resume paused agent runs" },
                  { action: "stop" as ControlAction, label: "Stop all", icon: <Square size={15} />, desc: "Stop active agent runs" },
                  { action: "rerun" as ControlAction, label: "Rerun failed", icon: <RotateCcw size={15} />, desc: "Rerun failed agent runs" },
                ]).map(({ action, label, icon, desc }) => (
                  <button
                    key={action}
                    className="flex w-full items-start gap-3 px-3 py-2.5 text-left transition hover:bg-slate-100 dark:hover:bg-white/10"
                    onClick={() => { onBulkControl(action); setBulkOpen(false); }}
                    type="button"
                  >
                    <span className="mt-0.5 shrink-0 text-slate-400 dark:text-slate-500">{icon}</span>
                    <div className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-slate-700 dark:text-slate-200">{label}</span>
                      <span className="block text-[11px] text-slate-500 dark:text-slate-400">{desc}</span>
                    </div>
                  </button>
                ))}
              </div>
            </>,
            document.body
          )}

          <Button onClick={onViewApprovals} size="sm" type="button" variant="accent"><ClipboardCheck size={14} /> Approvals</Button>
        </div>
      </div>
    </section>
  );
}

function HeroUpload({ accountImport, completedCount, failedCount, activeCount, pendingApprovals, selectedFile, isUploading, viewMode, onViewModeChange, onFileChange, onUpload, uploadStatus, workspaceId }: { accountImport: AccountImportResponse | null; completedCount: number; failedCount: number; activeCount: number; pendingApprovals: number; selectedFile: File | null; isUploading: boolean; viewMode: ViewMode; onViewModeChange: (mode: ViewMode) => void; onFileChange: (file: File | null) => void; onUpload: () => void; uploadStatus: UploadStatusMessage; workspaceId: string }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-8" id="reports">
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:gap-8">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-800 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
            <UploadCloud size={14} /> Start analysis
          </div>
          <h2 className="heading-fluid mt-4 font-semibold tracking-tight text-slate-950 dark:text-white">Upload Amazon Ads Report</h2>
          <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">
            Upload an account-level report or bulk sheet. AdSurf detects report types, groups entities, and prepares AI recommendations — all behind human approval.
          </p>
          {uploadStatus.kind !== "idle" ? (
            <div className={`mt-4 rounded-2xl border px-4 py-3 text-sm font-semibold ${uploadStatusClass(uploadStatus.kind)}`}>
              <div className="flex items-center gap-2">
                {uploadStatus.kind === "loading" ? <Loader2 className="animate-spin" size={16} /> : null}
                <span className="break-words">{uploadStatus.text}</span>
              </div>
              {uploadStatus.detail ? <p className="mt-1 break-words text-xs font-medium opacity-80">{uploadStatus.detail}</p> : null}
            </div>
          ) : null}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StepMetric label="Completed" value={completedCount} />
            <StepMetric label="Running" value={activeCount} />
            <StepMetric label="Failed" value={failedCount} />
            <StepMetric label="Needs approval" value={pendingApprovals} />
          </div>
          {accountImport ? (
            <div className="mt-6 rounded-2xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-950 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
              <p className="break-words font-semibold">{humanize(accountImport.detection.detected_report_type)} · {accountImport.import_record.status}</p>
              <p className="mt-1 break-words leading-6">{accountImport.import_record.processed_rows} rows grouped across {accountImport.entities.length} entities. {accountImport.product_mapping_suggestions.length} product mappings need review.</p>
            </div>
          ) : null}
        </div>
        <div className="min-w-0 rounded-3xl border border-slate-200 bg-slate-50 p-5 dark:border-white/10 dark:bg-white/5">
          <label className="block text-sm font-semibold text-slate-900 dark:text-white">
            Report file
            <input className="mt-2 block min-h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-full file:border-0 file:bg-slate-950 file:px-3 file:py-1 file:text-white focus:outline-none focus:ring-2 focus:ring-indigo-300 dark:border-white/10 dark:bg-slate-950/70 dark:text-white dark:file:bg-white dark:file:text-slate-950" onChange={(event) => onFileChange(event.target.files?.[0] ?? null)} type="file" accept=".csv,.xls,.xlsx" />
          </label>
          <Button className="mt-3 w-full" disabled={!selectedFile || isUploading} onClick={onUpload} type="button">
            {isUploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
            {isUploading ? "Uploading report..." : "Upload report"}
          </Button>
          <div className="mt-5 rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-950/70">
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Agent view</p>
            <div className="flex flex-col rounded-full border border-slate-200 bg-slate-100 p-1 dark:border-white/10 dark:bg-white/5 sm:flex-row" role="tablist" aria-label="Agent view mode">
              <button
                className={`flex-1 inline-flex min-h-9 items-center justify-center gap-2 rounded-full px-3 py-1.5 text-center text-xs font-semibold leading-snug outline-none transition focus-visible:ring-2 focus-visible:ring-indigo-300 sm:text-sm ${viewMode === "pipeline" ? "bg-indigo-600 text-white shadow-sm dark:bg-indigo-300 dark:text-indigo-950" : "bg-transparent text-slate-700 hover:bg-white dark:text-slate-200 dark:hover:bg-white/10"}`}
                onClick={() => onViewModeChange("pipeline")}
                role="tab"
                aria-selected={viewMode === "pipeline"}
                type="button"
              >
                <ListOrdered size={15} />
                Simple Pipeline
              </button>
              <button
                className={`flex-1 inline-flex min-h-9 items-center justify-center gap-2 rounded-full px-3 py-1.5 text-center text-xs font-semibold leading-snug outline-none transition focus-visible:ring-2 focus-visible:ring-indigo-300 sm:text-sm ${viewMode === "canvas" ? "bg-indigo-600 text-white shadow-sm dark:bg-indigo-300 dark:text-indigo-950" : "bg-transparent text-slate-700 hover:bg-white dark:text-slate-200 dark:hover:bg-white/10"}`}
                onClick={() => onViewModeChange("canvas")}
                role="tab"
                aria-selected={viewMode === "canvas"}
                type="button"
              >
                <GitBranch size={15} />
                Visual Canvas
              </button>
            </div>
            <p className="mt-3 text-[11px] leading-relaxed text-slate-500 dark:text-slate-400">
              {viewMode === "pipeline"
                ? "A clean step-by-step view of the agent pipeline. Click any agent card to open its full details."
                : "The full visual workflow canvas with horizontal agent layout. Best for exploring data flows between agents."}
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function SimplePipelineView({ agents, configByAgent, latestRunByAgent, selectedAgentId, onSelect, onOpenDrawer }: { agents: AgentDefinition[]; configByAgent: Map<string, AgentConfig>; latestRunByAgent: Map<string, AgentRun>; selectedAgentId: string; onSelect: (agentId: string, runId?: string) => void; onOpenDrawer: (agentId: string, runId?: string) => void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Agent Pipeline</p>
          <h2 className="heading-fluid mt-1 font-semibold tracking-tight text-slate-950 dark:text-white">Step-by-step analysis pipeline</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Agents run in sequence. Click any card for full details, configuration, and recommendations.</p>
        </div>
        <Badge>Approval-controlled workflow</Badge>
      </div>
      <div className="space-y-3">
        {workflowOrder.map((agentId, index) => {
          const agent = agents.find((item) => item.agent_id === agentId) ?? fallbackAgents.find((item) => item.agent_id === agentId)!;
          const config = configByAgent.get(agentId);
          const run = latestRunByAgent.get(agentId);
          const status = displayStatus(run?.status, agentId, config);
          const isActive = selectedAgentId === agentId;
          return (
            <div key={agentId} className="flex items-start gap-3">
              <div className="flex shrink-0 flex-col items-center">
                <button
                  className={`flex h-10 w-10 items-center justify-center rounded-xl transition ${isActive ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/25 dark:bg-indigo-300 dark:text-indigo-950" : "bg-slate-100 text-slate-600 hover:bg-slate-200 dark:bg-white/10 dark:text-slate-300 dark:hover:bg-white/20"}`}
                  onClick={() => onSelect(agentId, run?.id)}
                  type="button"
                >
                  {agentIcon(agentId)}
                </button>
                {index < workflowOrder.length - 1 && (
                  <div className={`my-1 w-0.5 flex-1 min-h-[20px] rounded-full ${["completed", "succeeded"].includes(status) ? "bg-emerald-300 dark:bg-emerald-500/40" : "running" === status || "queued" === status ? "bg-indigo-300 dark:bg-indigo-500/40" : "bg-slate-200 dark:bg-white/10"}`} />
                )}
              </div>
              <button
                className={`flex-1 min-w-0 rounded-2xl border p-4 text-left transition hover:-translate-y-0.5 hover:shadow-md ${isActive ? "border-indigo-400/60 bg-indigo-50 shadow-sm shadow-indigo-500/10 dark:border-indigo-400 dark:bg-indigo-500/10" : nodeClass(status)}`}
                onClick={() => onOpenDrawer(agentId, run?.id)}
                type="button"
              >
                <div className="flex flex-wrap items-center gap-3">
                  <h3 className="text-sm font-semibold text-slate-950 dark:text-white">{agent.display_name}</h3>
                  <StatusBadge status={status} />
                  <span className="text-xs font-medium text-slate-500 dark:text-slate-400">{humanize(agent.task_type)}</span>
                </div>
                <p className="mt-1.5 text-sm text-slate-600 dark:text-slate-300">{currentTask(agentId)}</p>
                <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                  <span className="font-semibold text-indigo-600 dark:text-indigo-200">{run?.recommendation_ids?.length ?? 0} recommendations</span>
                  {run?.created_at ? <span className="text-slate-500 dark:text-slate-400">{new Date(run.created_at).toLocaleDateString()}</span> : null}
                </div>
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function AgentTeamDashboard({ agents, configByAgent, latestRunByAgent, selectedAgentId, onSelect, onOpenDrawer, onViewTrace }: { agents: AgentDefinition[]; configByAgent: Map<string, AgentConfig>; latestRunByAgent: Map<string, AgentRun>; selectedAgentId: string; onSelect: (agentId: string, runId?: string) => void; onOpenDrawer: (agentId: string, runId?: string) => void; onViewTrace: (agentId: string, runId?: string) => void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-8">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400 sm:text-sm">Agent Team Dashboard</p>
          <h2 className="heading-fluid mt-1 break-words font-semibold tracking-tight text-slate-950 dark:text-white">Operational agent cards</h2>
        </div>
        <Badge>Approval-controlled workflow</Badge>
      </div>
      <div className="grid grid-cols-1 items-stretch gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {workflowOrder.map((agentId) => {
          const agent = agents.find((item) => item.agent_id === agentId) ?? fallbackAgents.find((item) => item.agent_id === agentId)!;
          const config = configByAgent.get(agentId);
          const run = latestRunByAgent.get(agentId);
          return <AgentCard agent={agent} config={config} run={run} selected={selectedAgentId === agentId} onSelect={() => onSelect(agentId, run?.id)} onOpenDrawer={onOpenDrawer} onViewTrace={onViewTrace} key={agentId} />;
        })}
      </div>
    </section>
  );
}

function AgentCard({ agent, config, run, selected, onSelect, onOpenDrawer, onViewTrace }: { agent: AgentDefinition; config?: AgentConfig; run?: AgentRun; selected: boolean; onSelect: () => void; onOpenDrawer?: (agentId: string, runId?: string) => void; onViewTrace?: (agentId: string, runId?: string) => void }) {
  const status = displayStatus(run?.status, agent.agent_id, config);
  return (
    <article className={`flex h-full min-w-0 flex-col rounded-3xl border p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg ${selected ? "border-indigo-400/60 bg-indigo-100/70 shadow-md shadow-indigo-500/10 dark:border-indigo-400 dark:bg-indigo-500/15 dark:shadow-lg dark:shadow-indigo-500/20" : "border-slate-200 bg-white hover:border-indigo-200 dark:border-white/10 dark:bg-slate-800/50 dark:hover:bg-slate-700/50"}`}>
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-white dark:text-slate-950">{agentIcon(agent.agent_id)}</span>
        <StatusBadge status={status} />
      </div>
      <h3 className="mt-4 break-words text-base font-semibold leading-6 text-slate-950 dark:text-white">{agent.display_name}</h3>
      <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Role: {humanize(agent.task_type)}</p>
      <p className="mt-2 line-clamp-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{agent.description}</p>
      <div className="mt-4 grid gap-2 text-xs">
        <AgentFact label="Current task" value={currentTask(agent.agent_id)} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <Badge>{run?.recommendation_ids?.length ?? 0} recommendations</Badge>
      </div>
      {run?.error_json && Object.keys(run.error_json).length ? <p className="mt-3 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100">Error state: validation or provider issue</p> : null}
      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        <Button className="flex-1 min-w-[7.5rem] px-3" onClick={() => onOpenDrawer ? onOpenDrawer(agent.agent_id, run?.id) : onSelect()} type="button" variant="primary"><Eye size={16} /> Details</Button>
        <Button className="flex-1 min-w-[7.5rem] px-3" onClick={() => onViewTrace ? onViewTrace(agent.agent_id, run?.id) : onSelect()} type="button" variant="secondary"><Eye size={16} /> Trace</Button>
      </div>
    </article>
  );
}

function WorkflowCanvas({ nodes, edges, selectedAgentId, onSelect }: { nodes: CanvasNode[]; edges: CanvasEdge[]; selectedAgentId: string; onSelect: (agentId: string) => void }) {
  return (
    <section className="min-w-0 overflow-hidden rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-[radial-gradient(circle_at_top_right,_rgba(34,211,238,0.18),_transparent_35%),linear-gradient(135deg,#020617,#111827_45%,#1e1b4b)] dark:shadow-xl dark:shadow-slate-950/20 sm:p-8" id="workflow-canvas">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-600 sm:text-sm dark:text-indigo-200">Visual Workflow Canvas</p>
          <h2 className="heading-fluid mt-1 truncate font-semibold tracking-tight text-slate-950 dark:text-white">How agents pass data to approval</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <CanvasLegend status="running" label="Running" />
          <CanvasLegend status="completed" label="Completed" />
          <CanvasLegend status="failed" label="Failed" />
          <CanvasLegend status="approval_needed" label="Approval needed" />
        </div>
      </div>
      <div className="-mx-1 overflow-x-auto pb-3" role="region" aria-label="Workflow canvas, scrollable horizontally">
        <div className="flex min-w-max items-stretch gap-4 px-1">
          {nodes.map((node, index) => (
            <div className="flex items-center gap-4" key={node.agent_id}>
              <button className={`group flex h-full w-[220px] flex-col rounded-3xl border p-4 text-left outline-none transition hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-indigo-300 dark:focus-visible:ring-white ${node.agent_id === selectedAgentId ? "border-indigo-300 bg-indigo-50 shadow-lg dark:border-indigo-400 dark:bg-indigo-500/15 dark:shadow-2xl dark:shadow-indigo-500/30" : nodeClass(node.status)}`} onClick={() => onSelect(node.agent_id)} type="button">
                <div className="flex items-center justify-between gap-3">
                  <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl ${nodeIconClass(node.status)}`}>{agentIcon(node.agent_id)}</span>
                  <StatusBadge status={node.status} />
                </div>
                <p className={`mt-4 break-words text-sm font-semibold leading-5 text-slate-950 dark:text-white`}>{node.display_name}</p>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-slate-600 dark:text-indigo-100">{node.current_task}</p>
                <p className="mt-auto pt-3 text-xs font-semibold text-indigo-600 dark:text-indigo-200">{node.recommendations_created} recommendations</p>
              </button>
              {index < nodes.length - 1 ? <WorkflowEdge edge={edges[index]} active={["running", "completed", "succeeded"].includes(node.status)} /> : null}
            </div>
          ))}
        </div>
      </div>
      <p className="mt-2 text-[11px] text-slate-500 sm:hidden dark:text-indigo-200/80">Swipe horizontally to see the full pipeline.</p>
    </section>
  );
}

function ApprovalCheckpointSummary({ pendingApprovals, highPriorityCount, dangerousCount, onDecision }: { pendingApprovals: Recommendation[]; highPriorityCount: number; dangerousCount: number; onDecision: (recommendationId: string, decision: "approve" | "reject") => Promise<void> | void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-8" id="approval-checkpoints">
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-violet-600 dark:text-violet-200 sm:text-sm">Human Approval Checkpoints</p>
          <h2 className="heading-fluid mt-1 break-words font-semibold tracking-tight text-slate-950 dark:text-white">{pendingApprovals.length} recommendations waiting approval</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge>{highPriorityCount} high priority</Badge>
          <Badge>{dangerousCount} risky actions</Badge>
          <Badge>AI confidence visible</Badge>
        </div>
      </div>
      <div className="mt-6 grid items-stretch gap-4 lg:grid-cols-2">
        {pendingApprovals.slice(0, 4).map((item) => <ApprovalCard recommendation={item} key={item.id} onDecision={onDecision} />)}
        {!pendingApprovals.length ? <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-600 dark:border-white/15 dark:text-slate-300">No pending approvals yet. Recommendations created by agents will appear here as business-friendly cards with metric evidence and risk notes.</div> : null}
      </div>
    </section>
  );
}

function ApprovalCard({ recommendation, onDecision }: { recommendation: Recommendation; onDecision: (recommendationId: string, decision: "approve" | "reject") => Promise<void> | void }) {
  const [pending, setPending] = useState<"approve" | "reject" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const title = recommendationTitle(recommendation);
  const reason = recommendationReason(recommendation);
  const action = recommendedAction(recommendation);
  const warnings = recommendationWarnings(recommendation);
  const impact = approvalImpact(recommendation);
  const displayName = recommendationDisplayName(recommendation);
  const metrics = recommendation.current_metric_snapshot_json || recommendation.input_metrics_json || {};

  async function handle(decision: "approve" | "reject") {
    if (pending) return;
    setPending(decision);
    setError(null);
    try {
      await Promise.resolve(onDecision(recommendation.id, decision));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : `Recommendation ${decision} could not be saved.`);
    } finally {
      setPending(null);
    }
  }

  return (
    <article className="flex h-full min-w-0 flex-col rounded-2xl border border-slate-200 bg-white p-5 shadow-sm transition dark:border-white/10 dark:bg-slate-900/80">
      {/* Header: Type label + status */}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-semibold text-violet-700 dark:border-violet-300/25 dark:bg-violet-300/10 dark:text-violet-100">
          <ShieldCheck size={13} /> Recommendation
        </span>
        <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${priorityBadgeClass(recommendation.priority)}`}>
          {recommendation.priority === "critical" || recommendation.priority === "high" ? <AlertTriangle size={12} /> : <Info size={12} />}
          Priority: {humanize(recommendation.priority)}
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
          Confidence: {humanize(recommendation.confidence)}
        </span>
      </div>

      {/* Headline */}
      <h3 className="text-lg font-bold tracking-tight text-slate-950 dark:text-white">{title}</h3>

      {/* Subtitle: entity display name */}
      {displayName && displayName !== "Account-level recommendation" && (
        <p className="mt-1 text-sm font-medium text-slate-500 dark:text-slate-400">{displayName}</p>
      )}

      {/* Recommended action chip */}
      <div className="mt-3 inline-flex items-center gap-1.5 self-start rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
        <Play size={12} /> {action}
      </div>

      {/* Reason */}
      <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-300">{reason}</p>

      {/* Key metrics chips */}
      {Object.keys(metrics).length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {Object.entries(metrics)
            .slice(0, 6)
            .map(([key, value]) => (
              <span
                key={key}
                className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs dark:border-white/10 dark:bg-white/5"
                title={`${fixMetricLabel(key)}: ${formatMetricValue(key, value)}`}
              >
                <span className="font-medium text-slate-500 dark:text-slate-400">{fixMetricLabel(key)}</span>
                <span className="font-semibold text-slate-800 dark:text-white">{formatMetricValue(key, value)}</span>
              </span>
            ))}
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {warnings.map((warning, i) => (
            <div
              key={i}
              className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
                warning.kind === "warning"
                  ? "border border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100"
                  : "border border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-300/25 dark:bg-blue-300/10 dark:text-blue-100"
              }`}
            >
              {warning.kind === "warning" ? <AlertTriangle size={13} className="mt-0.5 shrink-0" /> : <Info size={13} className="mt-0.5 shrink-0" />}
              <span>{warning.message}</span>
            </div>
          ))}
        </div>
      )}

      {/* Approval impact */}
      <div className="mt-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 text-xs leading-relaxed text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
        <ShieldCheck size={13} className="mb-1 inline-block text-indigo-500" /> {impact}
      </div>

      {/* Advanced details (collapsible) */}
      <div className="mt-3 border-t border-slate-100 pt-3 dark:border-white/10">
        <button
          className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-xs font-semibold text-slate-500 transition hover:bg-slate-50 dark:text-slate-400 dark:hover:bg-white/5"
          onClick={() => setAdvancedOpen(!advancedOpen)}
          type="button"
        >
          <span className="inline-flex items-center gap-1.5">
            <ChevronRight size={13} className={`transition-transform ${advancedOpen ? "rotate-90" : ""}`} />
            View advanced details
          </span>
          <span className="text-[10px] font-normal text-slate-400">IDs, source, thresholds</span>
        </button>
        {advancedOpen && (
          <div className="mt-3 space-y-3 rounded-xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-slate-950/70">
            {/* Internal IDs */}
            <div className="grid gap-2 text-[11px] sm:grid-cols-2">
              {recommendation.evidence_json?.campaign_id && (
                <AgentFact label="Campaign ID" value={String(recommendation.evidence_json.campaign_id)} />
              )}
              {recommendation.evidence_json?.portfolio_id && (
                <AgentFact label="Portfolio ID" value={String(recommendation.evidence_json.portfolio_id)} />
              )}
              {recommendation.evidence_json?.ad_group_id && (
                <AgentFact label="Ad Group ID" value={String(recommendation.evidence_json.ad_group_id)} />
              )}
              {recommendation.evidence_json?.target_id && (
                <AgentFact label="Target ID" value={String(recommendation.evidence_json.target_id)} />
              )}
              {recommendation.id && (
                <AgentFact label="Recommendation ID" value={recommendation.id} />
              )}
            </div>

            {/* Extra info */}
            <div className="grid gap-2 text-[11px] sm:grid-cols-2">
              <AgentFact label="Product/ASIN" value={String(recommendation.evidence_json?.asin ?? recommendation.product_id ?? "Not linked")} />
              <AgentFact label="Ad group" value={recommendation.ad_group_name || "Not specified"} />
              <AgentFact label="Target/search term" value={recommendation.customer_search_term || recommendation.targeting || "Not specified"} />
              <AgentFact label="Agent source" value={String(recommendation.evidence_json?.decision_source ?? recommendation.rule_name)} />
              <AgentFact label="Mode" value={String(recommendation.decision_source ?? recommendation.evidence_json?.mode ?? "—")} />
              <AgentFact label="Rule name" value={recommendation.rule_name || "—"} />
              <AgentFact label="Export status" value={recommendation.status || "—"} />
            </div>

            {/* Thresholds */}
            {recommendation.evidence_json?.thresholds && Object.keys(recommendation.evidence_json.thresholds as object).length > 0 && (
              <div>
                <p className="mb-1 text-[11px] font-semibold text-slate-500 dark:text-slate-400">Thresholds</p>
                <div className="flex flex-wrap gap-1.5">
                  {Object.entries(recommendation.evidence_json.thresholds as Record<string, unknown>).map(([k, v]) => (
                    <span key={k} className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] dark:border-white/10 dark:bg-slate-900">
                      <span className="text-slate-500">{fixMetricLabel(k)}:</span>
                      <span className="font-semibold text-slate-700 dark:text-slate-200">{String(v)}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Source rows */}
            {recommendation.evidence_json?.source_rows != null && (
              <AgentFact label="Source rows" value={String(recommendation.evidence_json.source_rows)} />
            )}
            {recommendation.evidence_json?.row_count != null && (
              <AgentFact label="Row count" value={String(recommendation.evidence_json.row_count)} />
            )}

            {/* Validator result */}
            {recommendation.evidence_json?.validator_result != null && (
              <AgentFact label="Validator result" value={String(recommendation.evidence_json.validator_result)} />
            )}

            {/* Full metric table */}
            <details>
              <summary className="cursor-pointer text-xs font-semibold text-indigo-600 dark:text-indigo-200">Full metric table</summary>
              <div className="mt-2 overflow-x-auto rounded-xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-950/70">
                <MetricTable metrics={metrics} />
              </div>
            </details>
          </div>
        )}
      </div>

      {/* Buttons */}
      <div className="mt-auto flex flex-wrap gap-2 pt-4">
        <Button
          className="flex-1 min-w-[8rem]"
          disabled={pending !== null}
          onClick={() => handle("approve")}
          type="button"
          variant="success"
        >
          {pending === "approve" ? <Loader2 className="animate-spin" size={16} /> : <CheckCircle2 size={16} />}
          {pending === "approve" ? "Approving..." : "Approve recommendation"}
        </Button>
        <Button
          className="flex-1 min-w-[8rem]"
          disabled={pending !== null}
          onClick={() => handle("reject")}
          type="button"
          variant="danger"
        >
          {pending === "reject" ? <Loader2 className="animate-spin" size={16} /> : <Square size={16} />}
          {pending === "reject" ? "Rejecting..." : "Reject recommendation"}
        </Button>
      </div>
      {error ? (
        <p className="mt-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100">
          {error}
        </p>
      ) : null}
    </article>
  );
}

function AgentTemplates({ onApply }: { onApply: (name: string) => void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-8" id="agent-settings">
      <div className="mb-5">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Agent Templates</p>
        <h2 className="heading-fluid mt-1 font-semibold tracking-tight text-slate-950 dark:text-white">Future-ready team presets</h2>
      </div>
      <div className="grid items-stretch gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {templates.map(([name, description]) => (
          <article className="flex h-full min-w-0 flex-col rounded-3xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5" key={name}>
            <p className="break-words font-semibold text-slate-950 dark:text-white">{name}</p>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{description}</p>
            <Button className="mt-auto self-start" onClick={() => onApply(name)} type="button" variant="secondary">Apply template</Button>
          </article>
        ))}
      </div>
    </section>
  );
}

type CanvasNode = {
  agent_id: string;
  display_name: string;
  status: string;
  current_task: string;
  recommendations_created: number;
};

type CanvasEdge = {
  source_agent_id: string;
  target_agent_id: string;
  status: string;
  data_passed_summary: string[];
};

function buildWorkflowNodes({ agentCatalog, configByAgent, latestRunByAgent, workflow, recommendations }: { agentCatalog: AgentDefinition[]; configByAgent: Map<string, AgentConfig>; latestRunByAgent: Map<string, AgentRun>; workflow: AgentWorkflow | null; recommendations: Recommendation[] }): CanvasNode[] {
  const workflowMap = new Map((workflow?.nodes ?? []).map((node) => [node.agent_id, node]));
  return workflowOrder.map((agentId) => {
    const agent = agentCatalog.find((item) => item.agent_id === agentId) ?? fallbackAgents.find((item) => item.agent_id === agentId)!;
    const workflowNode = workflowMap.get(agentId);
    const run = latestRunByAgent.get(agentId);
    return {
      agent_id: agentId,
      display_name: agent.display_name,
      status: displayStatus(workflowNode?.status ?? run?.status, agentId, configByAgent.get(agentId), recommendations),
      current_task: currentTask(agentId),
      recommendations_created: workflowNode?.recommendations_created ?? run?.recommendation_ids?.length ?? (agentId === "human_approval_agent" ? recommendations.filter((item) => item.status === "pending_approval").length : 0),
    };
  });
}

function buildWorkflowEdges(workflow: AgentWorkflow | null): CanvasEdge[] {
  if (workflow?.edges?.length) return workflow.edges;
  return workflowOrder.slice(0, -1).map((source, index) => ({
    source_agent_id: source,
    target_agent_id: workflowOrder[index + 1],
    status: index < 3 ? "ready" : "waiting_for_dependency",
    data_passed_summary: edgeSummary(source, workflowOrder[index + 1]),
  }));
}

function mergeAgents(loaded: AgentDefinition[]) {
  const map = new Map<string, AgentDefinition>();
  for (const agent of fallbackAgents) map.set(agent.agent_id, agent);
  for (const agent of loaded) map.set(agent.agent_id, agent);
  return workflowOrder.map((agentId) => map.get(agentId)!).filter(Boolean);
}

function definition(agent_id: string, display_name: string, description: string, task_type: string, output_type: string): AgentDefinition {
  return { agent_id, display_name, description, task_type, output_type, enabled_by_default: true, allowed_actions: ["run", "pause", "stop", "rerun", "view_input", "view_output", "view_logs"], input_dependencies: [], can_mutate_live_amazon_ads: false };
}

function workflowEventToAgentEvent(event: WorkflowEvent): AgentEvent {
  return {
    id: event.id,
    agent_id: event.agent_id ?? "unknown",
    agent_run_id: event.workflow_id,
    monitoring_import_id: null,
    event_type: event.event_type,
    message: event.message,
    metadata_json: {
      ...event.metadata_json,
      provider: event.provider,
      model: event.model,
      latency_ms: event.latency_ms,
    },
    created_at: event.created_at,
  };
}

function runToEvent(run: AgentRun): AgentEvent {
  return { id: `event-${run.id}`, agent_id: run.agent_id, agent_run_id: run.id, monitoring_import_id: run.monitoring_import_id, event_type: run.status === "failed" ? "agent_failed" : "agent_succeeded", message: `${run.agent_name} finished with status ${run.status}.`, metadata_json: { provider: run.provider, model: run.model, latency_ms: run.latency_ms, validation_errors: run.error_json?.validation_errors ?? [], recommendation_ids: run.recommendation_ids }, created_at: run.created_at };
}

function displayStatus(status?: string, agentId?: string, config?: AgentConfig, recommendations: Recommendation[] = []) {
  if (agentId === "human_approval_agent" && recommendations.some((item) => item.status === "pending_approval")) return "approval_needed";
  if (config?.enabled === false) return "paused";
  if (status === "succeeded") return "completed";
  if (status) return status;
  if (agentId === "report_upload_node") return "waiting";
  return "idle";
}

function uploadStepLabel(step: UploadAccountReportProgress) {
  const labels: Record<UploadAccountReportProgress, string> = {
    initializing_upload: "Creating upload record.",
    storing_file: "Storing report file.",
    confirming_upload: "Queueing parser job.",
    processing_file: "Processing report rows.",
    creating_account_import: "Creating account import and grouping entities.",
  };
  return labels[step];
}

function uploadStatusClass(kind: UploadStatusMessage["kind"]) {
  if (kind === "success") return "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100";
  if (kind === "error") return "border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100";
  if (kind === "loading") return "border-indigo-200 bg-indigo-50 text-indigo-900 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100";
  return "border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200";
}

function edgeSummary(source: string, target: string) {
  const summaries: Record<string, string[]> = {
    "report_upload_node:import_data_quality_agent": ["headers", "sample rows", "file metadata"],
    "import_data_quality_agent:entity_resolution_agent": ["quality flags", "row count", "column map"],
    "entity_resolution_agent:metrics_normalization_agent": ["entity mapping", "ASIN/SKU groups", "campaign groups"],
    "metrics_normalization_agent:account_strategy_agent": ["normalized metrics", "spend/sales", "ACOS/ROAS"],
    "account_strategy_agent:search_term_mining_agent": ["strategy mode", "risk policy", "thresholds"],
    "search_term_mining_agent:bid_optimization_agent": ["search term classes", "winners", "wasters"],
    "search_term_mining_agent:negative_keyword_agent": ["wasted terms", "negative candidates"],
    "bid_optimization_agent:risk_policy_validator_agent": ["bid candidates", "evidence", "risk notes"],
    "negative_keyword_agent:risk_policy_validator_agent": ["negative candidates", "evidence"],
    "budget_reallocation_agent:risk_policy_validator_agent": ["budget shifts", "evidence"],
    "campaign_structure_agent:risk_policy_validator_agent": ["structural changes", "evidence"],
    "risk_policy_validator_agent:human_approval_agent": ["validated set", "rejected set"],
    "human_approval_agent:bulk_change_compiler_agent": ["approved changes", "audit trail"],
    "bulk_change_compiler_agent:learning_feedback_agent": ["applied changes", "before/after"],
    "learning_feedback_agent:stakeholder_reporting_agent": ["impact metrics", "outcome history"],
  };
  return summaries[`${source}:${target}`] ?? ["validated evidence", "recommendation context"];
}

function templatePatch(name: string): Partial<AgentConfig> {
  if (name.includes("Growth")) return { strictness_level: "aggressive", confidence_threshold: "medium", analysis_depth: "deep", include_campaign_level_analysis: true, include_search_term_level_analysis: true, allow_increase_bid: true };
  if (name.includes("Cleanup")) return { strictness_level: "balanced", confidence_threshold: "high", analysis_depth: "standard", allow_negative_exact: true, allow_negative_phrase: true, allow_pause_review: true };
  if (name.includes("Launch")) return { strictness_level: "conservative", confidence_threshold: "high", analysis_depth: "quick", require_high_confidence_for_pause: true, allow_data_quality_review: true };
  if (name.includes("Agency")) return { strictness_level: "balanced", confidence_threshold: "medium", analysis_depth: "deep", include_account_level_analysis: true, include_product_level_analysis: true, include_campaign_level_analysis: true };
  return { strictness_level: "conservative", confidence_threshold: "high", analysis_depth: "standard", allow_decrease_bid: true, allow_budget_review: true };
}

function agentIcon(agentId: string) {
  if (agentId.includes("brain")) return <BrainCircuit size={20} />;
  if (agentId.includes("detection")) return <FileSearch size={20} />;
  if (agentId.includes("resolution")) return <Layers3 size={20} />;
  if (agentId.includes("metrics")) return <BarChart3 size={20} />;
  if (agentId.includes("approval")) return <ClipboardCheck size={20} />;
  if (agentId.includes("upload")) return <UploadCloud size={20} />;
  return <Bot size={20} />;
}

function currentTask(agentId: string) {
  const tasks: Record<string, string> = {
    report_upload_node: "Waiting for report upload",
    import_data_quality_agent: "Validate report rows, columns, and data quality",
    entity_resolution_agent: "Map campaigns, ad groups, ASINs, SKUs, and search terms",
    metrics_normalization_agent: "Calculate CPC, CTR, CVR, ACOS, ROAS deterministically",
    account_strategy_agent: "Determine optimization goal and risk policy",
    search_term_mining_agent: "Classify search terms: harvest, negative, watch, ignore",
    bid_optimization_agent: "Recommend bid increase/decrease with evidence",
    negative_keyword_agent: "Recommend negative exact/phrase candidates",
    budget_reallocation_agent: "Recommend budget shifts across campaigns",
    campaign_structure_agent: "Recommend structural campaign changes",
    risk_policy_validator_agent: "Validate every recommendation against safety rules",
    human_approval_agent: "Route recommendations to approval queue",
    bulk_change_compiler_agent: "Compile approved changes into Amazon bulk export",
    learning_feedback_agent: "Compare prior recommendations with new metrics",
    stakeholder_reporting_agent: "Create summaries and approver notes",
    // Legacy
    ai_recommendation_brain_agent: "Generate strict JSON recommendations (legacy)",
  };
  return tasks[agentId] ?? "Inspect evidence";
}

function WorkflowEdge({ edge, active }: { edge?: CanvasEdge; active: boolean }) {
  return (
    <div className="w-28 shrink-0">
      <div className={`h-1 rounded-full ${active ? "bg-gradient-to-r from-emerald-300 via-cyan-300 to-indigo-300 shadow-lg shadow-cyan-500/40" : "bg-slate-200 dark:bg-white/20"}`} />
      <p className="mt-2 line-clamp-2 text-center text-[11px] font-medium text-slate-500 dark:text-indigo-100">{edge?.data_passed_summary?.slice(0, 2).join(" + ") ?? "evidence"}</p>
    </div>
  );
}

function CanvasLegend({ status, label }: { status: string; label: string }) {
  return <span className="inline-flex items-center gap-2 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-slate-600 dark:border-white/15 dark:bg-white/10 dark:text-indigo-50"><span className={`h-2.5 w-2.5 rounded-full ${dotClass(status)}`} />{label}</span>;
}

function nodeClass(status: string) {
  if (status === "failed") return "border-red-200 bg-red-50 dark:border-red-400/40 dark:bg-red-500/10 dark:shadow-red-500/15";
  if (status === "approval_needed") return "border-violet-200 bg-violet-50 dark:border-violet-300/50 dark:bg-violet-400/15 dark:shadow-violet-500/25";
  if (status === "completed" || status === "succeeded") return "border-emerald-200 bg-emerald-50 dark:border-emerald-300/40 dark:bg-emerald-400/10 dark:shadow-emerald-500/15";
  if (status === "running" || status === "queued") return "border-indigo-200 bg-indigo-50 dark:border-indigo-300/50 dark:bg-indigo-400/15 dark:shadow-indigo-500/25";
  if (status === "paused" || status === "waiting") return "border-amber-200 bg-amber-50 dark:border-amber-300/40 dark:bg-amber-400/10 dark:shadow-amber-500/15";
  return "border-slate-200 bg-white dark:border-white/10 dark:bg-slate-800/50 dark:shadow-slate-950/10";
}

function nodeIconClass(status: string) {
  if (status === "failed") return "bg-red-100 text-red-700 dark:bg-red-400 dark:text-white";
  if (status === "approval_needed") return "bg-violet-100 text-violet-700 dark:bg-violet-300 dark:text-violet-950";
  if (status === "completed" || status === "succeeded") return "bg-emerald-100 text-emerald-700 dark:bg-emerald-300 dark:text-emerald-950";
  if (status === "running" || status === "queued") return "bg-indigo-100 text-indigo-700 dark:bg-indigo-300 dark:text-indigo-950";
  if (status === "paused" || status === "waiting") return "bg-amber-100 text-amber-700 dark:bg-amber-300 dark:text-amber-950";
  return "bg-slate-200 text-slate-700 dark:bg-white/15 dark:text-white";
}

function dotClass(status: string) {
  if (status === "failed") return "bg-red-400";
  if (status === "approval_needed") return "bg-violet-300";
  if (status === "completed") return "bg-emerald-300";
  if (status === "running") return "bg-indigo-300";
  return "bg-amber-300";
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone[status] ?? statusTone.idle}`}>{humanize(status)}</span>;
}

function AgentFact({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-white/10 dark:bg-slate-950/50"><p className="font-semibold text-slate-500 dark:text-slate-400">{label}</p><p className="mt-1 break-words text-slate-900 dark:text-white">{value}</p></div>;
}

function StepMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="min-w-0 rounded-2xl border border-slate-200 bg-slate-50 p-2 sm:p-3 dark:border-white/10 dark:bg-white/5">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400 sm:text-xs">{label}</p>
      <p className="mt-1 font-semibold tabular-nums leading-tight text-slate-950 dark:text-white" style={{ fontSize: "clamp(1.125rem, 2.5vw, 1.5rem)" }}>{value}</p>
    </div>
  );
}

function MetricTable({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics).slice(0, 8);
  return <table className="w-full text-left text-xs"><tbody>{entries.map(([key, value]) => <tr className="border-b border-slate-100 last:border-0 dark:border-white/10" key={key}><th className="py-2 pr-3 font-semibold text-slate-600 dark:text-slate-300">{humanize(key)}</th><td className="py-2 text-slate-950 dark:text-white">{String(value)}</td></tr>)}</tbody></table>;
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="inline-flex rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200">{children}</span>;
}

function priorityBadgeClass(priority: string) {
  if (priority === "critical") return "border-red-200 bg-red-50 text-red-700 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100";
  if (priority === "high") return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100";
  if (priority === "medium") return "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-300/25 dark:bg-blue-300/10 dark:text-blue-100";
  return "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300";
}

function humanize(value: string) {
  const display: Record<string, string> = {
    ai: "AI", deepseek: "DeepSeek", openai: "OpenAI", roas: "ROAS", acos: "ACOS", asin: "ASIN", sku: "SKU",
  };
  const lower = value.toLowerCase();
  if (display[lower]) return display[lower];
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
