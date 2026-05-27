"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  BarChart3,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Eye,
  FileSearch,
  Layers3,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Settings,
  ShieldCheck,
  Square,
  UploadCloud,
} from "lucide-react";
import { AgentInspector } from "@/components/agents/agent-inspector";
import { AgentTraceTimeline } from "@/components/agents/agent-trace-timeline";
import { Button } from "@/components/ui/button";
import { defaultWorkspaceId } from "@/lib/api/client";
import {
  controlAgentRun,
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
import { uploadAccountReport, type AccountImportResponse } from "@/lib/api/account-imports";
import { decideRecommendation, getRecommendations, type Recommendation } from "@/lib/api/monitoring";

type ControlAction = "pause" | "resume" | "stop" | "rerun";
type ExperienceMode = "simple" | "advanced";

const workflowOrder = [
  "report_upload_node",
  "report_detection_agent",
  "product_resolution_agent",
  "metrics_analysis_agent",
  "ai_recommendation_brain_agent",
  "bid_optimization_agent",
  "negative_keyword_agent",
  "budget_allocation_agent",
  "pause_review_agent",
  "stakeholder_reporting_agent",
  "human_approval_agent",
];

const fallbackAgents: AgentDefinition[] = [
  definition("report_upload_node", "Report Upload", "Receives Amazon Ads reports or bulk sheets and starts the account workflow.", "start", "uploaded_report"),
  definition("report_detection_agent", "Report Detection Agent", "Detects report type, confidence, required columns, and analysis readiness.", "validation", "report_detection_summary"),
  definition("product_resolution_agent", "Product Resolution Agent", "Maps ASINs, SKUs, product names, and unknown product groups.", "mapping", "product_mapping_suggestions"),
  definition("metrics_analysis_agent", "Metrics Analysis Agent", "Calculates account, product, campaign, target, and search-term metrics.", "analysis", "performance_rollups"),
  definition("ai_recommendation_brain_agent", "AI Recommendation Brain", "Creates strict JSON recommendation decisions from grouped metrics.", "decision", "recommendation_json"),
  definition("bid_optimization_agent", "Bid Optimization Agent", "Reviews bid-related recommendations across products and campaigns.", "specialist", "bid_recommendation_review"),
  definition("negative_keyword_agent", "Negative Keyword Agent", "Reviews wasted search terms and negative keyword candidates.", "specialist", "negative_keyword_review"),
  definition("budget_allocation_agent", "Budget Allocation Agent", "Reviews budget pressure and reallocation opportunities.", "specialist", "budget_review"),
  definition("pause_review_agent", "Pause Review Agent", "Identifies campaigns, ad groups, or targets that may need pause review.", "specialist", "pause_review"),
  definition("stakeholder_reporting_agent", "Stakeholder Reporting Agent", "Produces executive summaries and approver notes.", "reporting", "stakeholder_summary"),
  definition("human_approval_agent", "Human Approval Agent", "Routes recommendations to humans and prevents automatic approval.", "approval", "approval_queue"),
];

const templates = [
  ["Conservative Profitability Team", "High confidence thresholds, strict pause/negative controls, profit-first recommendations."],
  ["Growth Scaling Team", "Deeper analysis, scaling toggles, winner expansion, and campaign-level opportunities."],
  ["Wasted Spend Cleanup Team", "Focuses on no-order spend, negative keywords, and pause-review candidates."],
  ["Launch Campaign Review Team", "Protects new products with conservative evidence thresholds and data-quality checks."],
  ["Agency Account Audit Team", "Account-wide audit view for products, campaigns, budgets, and approver summaries."],
];
const experienceLabels: Record<ExperienceMode, string> = { simple: "Simple Mode", advanced: "Advanced Mode" };

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
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("report_upload_node");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [accountImport, setAccountImport] = useState<AccountImportResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isUploading, setIsUploading] = useState(false);
  const [experienceMode, setExperienceMode] = useState<ExperienceMode>("simple");
  const [environmentMode, setEnvironmentMode] = useState<AgentConfig["mode"]>("hybrid");

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
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? latestRunByAgent.get(selectedAgent?.agent_id ?? "");
  const selectedConfig = selectedAgent ? configByAgent.get(selectedAgent.agent_id) : undefined;
  const visibleEvents = workflow?.events ?? runs.map(runToEvent);
  const pendingApprovals = recommendations.filter((item) => item.status === "pending_approval" || item.status === "pending");
  const highPriorityApprovals = pendingApprovals.filter((item) => ["critical", "high"].includes(item.priority));
  const dangerousApprovals = pendingApprovals.filter((item) => ["pause_review", "add_negative_exact", "add_negative_phrase", "decrease_bid"].includes(item.recommendation_type));
  const activeCount = workflowNodes.filter((node) => ["running", "queued"].includes(node.status)).length;
  const failedCount = workflowNodes.filter((node) => node.status === "failed").length;
  const completedCount = workflowNodes.filter((node) => ["completed", "succeeded"].includes(node.status)).length;

  async function load() {
    setIsLoading(true);
    setMessage(null);
    try {
      const [loadedAgents, loadedConfigs, loadedRuns, loadedRecommendations] = await Promise.all([
        getAgents(workspaceId),
        getAgentConfigs(workspaceId, productId),
        getAgentRuns(workspaceId, importId),
        getRecommendations(workspaceId).catch(() => []),
      ]);
      setAgents(loadedAgents);
      setConfigs(loadedConfigs);
      setRuns(loadedRuns);
      setRecommendations(loadedRecommendations);
      if (importId) setWorkflow(await getAgentWorkflow(importId, workspaceId));
      setEnvironmentMode(loadedConfigs[0]?.mode ?? "hybrid");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Agent Control Center could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  async function uploadReport() {
    if (!selectedFile) return;
    setIsUploading(true);
    setMessage(null);
    try {
      const result = await uploadAccountReport(selectedFile, workspaceId);
      setAccountImport(result);
      setSelectedAgentId("report_detection_agent");
      setMessage("Report detected, entities grouped, and product mapping suggestions prepared.");
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Account report upload could not be completed.");
    } finally {
      setIsUploading(false);
    }
  }

  async function saveConfig(agentId: string, patch: Partial<AgentConfig>) {
    await updateAgentConfig(agentId, { ...patch, product_id: productId ?? null, reason: "Updated from Agent Control Center" }, workspaceId);
    await load();
  }

  async function toggleAgent(agentId: string) {
    const current = configByAgent.get(agentId);
    if (!current) return;
    await saveConfig(agentId, { enabled: !current.enabled });
  }

  async function control(run: AgentRun | undefined, action: ControlAction) {
    if (!run) return;
    await controlAgentRun(run.id, action, `${action} requested from Agent Control Center`, workspaceId);
    await load();
  }

  async function rerunHere(agentId: string) {
    if (!importId) {
      setMessage("Select an import-level workflow before rerunning from a specific agent.");
      return;
    }
    await rerunFromAgent(importId, agentId, "Rerun from this agent onward", workspaceId);
    await load();
  }

  async function applyTemplate(name: string) {
    const patch = templatePatch(name);
    await Promise.all(agentCatalog.map((agent) => updateAgentConfig(agent.agent_id, { ...patch, product_id: productId ?? null, reason: `${name} template applied` }, workspaceId).catch(() => undefined)));
    await load();
  }

  async function decide(recommendationId: string, decision: "approve" | "reject") {
    await decideRecommendation(recommendationId, decision, `${decision} from Agent Control Center after human review.`, workspaceId);
    await load();
  }

  return (
    <div className="min-h-screen rounded-[1.75rem] bg-slate-100 p-3 text-slate-950 dark:bg-slate-950 dark:text-white sm:p-4 lg:p-5">
      <main className="min-w-0 space-y-6">
          <TopCommandBar
            environmentMode={environmentMode}
            isLoading={isLoading}
            onEnvironmentChange={(mode) => {
              setEnvironmentMode(mode);
              void Promise.all(configs.map((config) => updateAgentConfig(config.agent_id, { mode, product_id: productId ?? null, reason: "Environment mode updated from top bar" }, workspaceId))).then(load);
            }}
            onRefresh={load}
            onRunAnalysis={() => setMessage("Run analysis is queued from import-level workflows; select an import to run the full pipeline.")}
            onBulkControl={(action) => {
              const targetRuns = runs.filter((run) => {
                if (action === "resume") return run.status === "paused";
                if (action === "rerun") return run.status === "failed";
                return ["running", "queued", "failed", "paused"].includes(run.status);
              });
              void Promise.all(targetRuns.map((run) => controlAgentRun(run.id, action, `${action} all from Agent Control Center`, workspaceId).catch(() => undefined))).then(load);
            }}
            onViewApprovals={() => document.getElementById("approval-checkpoints")?.scrollIntoView({ behavior: "smooth" })}
          />

          {message ? <div className="rounded-2xl border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm font-semibold text-indigo-900 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">{message}</div> : null}

          <section className="grid min-w-0 items-start gap-6 2xl:grid-cols-[minmax(0,1fr)_400px]">
            <div className="min-w-0 space-y-6">
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
                experienceMode={experienceMode}
                onExperienceModeChange={setExperienceMode}
                uploadMessage={message}
              />

              <WorkflowCanvas nodes={workflowNodes} edges={workflowEdges} selectedAgentId={selectedAgentId} onSelect={setSelectedAgentId} />

              <AgentTeamDashboard
                agents={agentCatalog}
                configByAgent={configByAgent}
                latestRunByAgent={latestRunByAgent}
                selectedAgentId={selectedAgentId}
                onSelect={(agentId, runId) => {
                  setSelectedAgentId(agentId);
                  setSelectedRunId(runId ?? null);
                }}
              />

              <ApprovalCheckpointSummary
                pendingApprovals={pendingApprovals}
                highPriorityCount={highPriorityApprovals.length}
                dangerousCount={dangerousApprovals.length}
                onDecision={decide}
              />

              <AgentTraceTimeline events={visibleEvents} runs={runs} />

              {experienceMode === "advanced" ? <AgentTemplates onApply={applyTemplate} /> : null}
            </div>

            <div className="min-w-0 2xl:sticky 2xl:top-6 2xl:max-h-[calc(100vh-3rem)] 2xl:overflow-auto">
              <AgentInspector
                agent={selectedAgent}
                config={selectedConfig}
                run={selectedRun}
                events={visibleEvents}
                recommendations={recommendations}
                advancedMode={experienceMode === "advanced"}
                onConfigChange={(patch) => selectedAgent && saveConfig(selectedAgent.agent_id, patch)}
                onToggleAgent={() => selectedAgent && toggleAgent(selectedAgent.agent_id)}
              />
            </div>
          </section>
        </main>
    </div>
  );
}

function TopCommandBar({ environmentMode, isLoading, onEnvironmentChange, onRefresh, onRunAnalysis, onBulkControl, onViewApprovals }: { environmentMode: AgentConfig["mode"]; isLoading: boolean; onEnvironmentChange: (mode: AgentConfig["mode"]) => void; onRefresh: () => void; onRunAnalysis: () => void; onBulkControl: (action: ControlAction) => void; onViewApprovals: () => void }) {
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 rounded-3xl border border-white/70 bg-white/90 px-4 py-3 shadow-sm backdrop-blur-xl dark:border-white/10 dark:bg-white/5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-950 dark:text-white">Agent Control Center</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">Multi-agent operations for Amazon Ads recommendations and approvals.</p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select className="min-h-10 rounded-full border border-slate-200 bg-white px-3 text-sm font-semibold text-slate-950 outline-none focus:ring-2 focus:ring-indigo-300 dark:border-white/10 dark:bg-slate-950/70 dark:text-white" onChange={(event) => onEnvironmentChange(event.target.value as AgentConfig["mode"])} value={environmentMode} aria-label="Environment mode selector">
          <option value="deterministic">Deterministic</option>
          <option value="ai">AI</option>
          <option value="hybrid">Hybrid</option>
        </select>
        <Button onClick={onRunAnalysis} type="button"><Play size={16} /> Run analysis</Button>
        <Button className="bg-amber-600 hover:bg-amber-500 dark:bg-amber-200 dark:text-amber-950" onClick={() => onBulkControl("pause")} type="button"><Pause size={16} /> Pause all</Button>
        <Button className="bg-emerald-700 hover:bg-emerald-600 dark:bg-emerald-200 dark:text-emerald-950" onClick={() => onBulkControl("resume")} type="button"><Play size={16} /> Resume all</Button>
        <Button className="bg-zinc-800 hover:bg-zinc-700 dark:bg-zinc-200 dark:text-zinc-950" onClick={() => onBulkControl("stop")} type="button"><Square size={16} /> Stop all</Button>
        <Button onClick={() => onBulkControl("rerun")} type="button"><RotateCcw size={16} /> Rerun failed</Button>
        <Button onClick={onRefresh} disabled={isLoading} type="button">{isLoading ? <Loader2 className="animate-spin" size={16} /> : <Settings size={16} />} Configure agents</Button>
        <Button className="bg-violet-700 hover:bg-violet-600 dark:bg-violet-200 dark:text-violet-950" onClick={onViewApprovals} type="button"><ClipboardCheck size={16} /> View approvals</Button>
      </div>
    </section>
  );
}

function HeroUpload({ accountImport, completedCount, failedCount, activeCount, pendingApprovals, selectedFile, isUploading, experienceMode, onExperienceModeChange, onFileChange, onUpload, uploadMessage }: { accountImport: AccountImportResponse | null; completedCount: number; failedCount: number; activeCount: number; pendingApprovals: number; selectedFile: File | null; isUploading: boolean; experienceMode: ExperienceMode; onExperienceModeChange: (mode: ExperienceMode) => void; onFileChange: (file: File | null) => void; onUpload: () => void; uploadMessage?: string | null }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/70 sm:p-6" id="reports">
      <div className="grid gap-5">
        <div className="min-w-0">
          <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-800 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
            <UploadCloud size={14} /> Start analysis
          </div>
          <h2 className="mt-4 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Upload Amazon Ads Report</h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
            Upload an account-level report or bulk sheet, then AdSurf will detect report type, group entities, prepare agent inputs, and keep every recommendation behind human approval.
          </p>
          {uploadMessage && (
            <div className="mt-4 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-medium text-rose-900 dark:border-rose-900/50 dark:bg-rose-900/20 dark:text-rose-200">
              {uploadMessage}
            </div>
          )}
          <div className="mt-5 grid grid-cols-[repeat(auto-fit,minmax(130px,1fr))] gap-3">
            <StepMetric label="Completed" value={completedCount} />
            <StepMetric label="Running" value={activeCount} />
            <StepMetric label="Failed" value={failedCount} />
            <StepMetric label="Needs approval" value={pendingApprovals} />
          </div>
          {accountImport ? (
            <div className="mt-5 rounded-2xl border border-indigo-200 bg-indigo-50 p-4 text-sm text-indigo-950 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
              <p className="font-semibold">{humanize(accountImport.detection.detected_report_type)} · {accountImport.import_record.status}</p>
              <p className="mt-1 leading-6">{accountImport.import_record.processed_rows} rows grouped across {accountImport.entities.length} entities. {accountImport.product_mapping_suggestions.length} product mappings need review.</p>
            </div>
          ) : null}
        </div>
        <div className="rounded-3xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
          <label className="block text-sm font-semibold text-slate-900 dark:text-white">
            Report file
            <input className="mt-2 block min-h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 file:mr-3 file:rounded-full file:border-0 file:bg-slate-950 file:px-3 file:py-1 file:text-white focus:outline-none focus:ring-2 focus:ring-indigo-300 dark:border-white/10 dark:bg-slate-950/70 dark:text-white dark:file:bg-white dark:file:text-slate-950" onChange={(event) => onFileChange(event.target.files?.[0] ?? null)} type="file" accept=".csv,.xls,.xlsx" />
          </label>
          <Button className="mt-3 w-full" disabled={!selectedFile || isUploading} onClick={onUpload} type="button">
            {isUploading ? <Loader2 className="animate-spin" size={16} /> : <UploadCloud size={16} />}
            Upload report
          </Button>
          <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-950/70">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">View mode</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              {(["simple", "advanced"] as ExperienceMode[]).map((mode) => (
                <button className={`min-h-10 rounded-full border px-3 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-indigo-300 ${experienceMode === mode ? "border-indigo-300 bg-indigo-600 text-white shadow-sm dark:bg-indigo-300 dark:text-indigo-950" : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"}`} key={mode} onClick={() => onExperienceModeChange(mode)} type="button">{experienceLabels[mode]}</button>
              ))}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2">
            <SafetyPill light text="Recommendation only" />
            <SafetyPill light text="Requires human approval" />
            <SafetyPill light text="No live Amazon Ads change executed" />
          </div>
        </div>
      </div>
    </section>
  );
}

function AgentTeamDashboard({ agents, configByAgent, latestRunByAgent, selectedAgentId, onSelect }: { agents: AgentDefinition[]; configByAgent: Map<string, AgentConfig>; latestRunByAgent: Map<string, AgentRun>; selectedAgentId: string; onSelect: (agentId: string, runId?: string) => void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Agent Team Dashboard</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Operational agent cards</h2>
        </div>
        <Badge>Approval-controlled workflow</Badge>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-4">
        {workflowOrder.map((agentId) => {
          const agent = agents.find((item) => item.agent_id === agentId) ?? fallbackAgents.find((item) => item.agent_id === agentId)!;
          const config = configByAgent.get(agentId);
          const run = latestRunByAgent.get(agentId);
          return <AgentCard agent={agent} config={config} run={run} selected={selectedAgentId === agentId} onSelect={() => onSelect(agentId, run?.id)} key={agentId} />;
        })}
      </div>
    </section>
  );
}

function AgentCard({ agent, config, run, selected, onSelect }: { agent: AgentDefinition; config?: AgentConfig; run?: AgentRun; selected: boolean; onSelect: () => void }) {
  const status = displayStatus(run?.status, agent.agent_id, config);
  return (
    <article className={`min-w-[280px] rounded-3xl border p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-lg ${selected ? "border-indigo-300 bg-indigo-50 shadow-indigo-950/10 dark:border-indigo-300/40 dark:bg-indigo-300/10" : "border-slate-200 bg-white hover:border-indigo-200 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"}`}>
      <div className="flex items-start justify-between gap-3">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-950 text-white dark:bg-white dark:text-slate-950">{agentIcon(agent.agent_id)}</span>
        <StatusBadge status={status} />
      </div>
      <h3 className="mt-4 text-base font-semibold leading-6 text-slate-950 dark:text-white">{agent.display_name}</h3>
      <p className="mt-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Role: {humanize(agent.task_type)}</p>
      <p className="mt-2 line-clamp-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{agent.description}</p>
      <div className="mt-4 grid gap-2 text-xs">
        <AgentFact label="Current task" value={currentTask(agent.agent_id)} />
        <AgentFact label="Model/provider" value={`${config?.provider ?? run?.provider ?? "deepseek"} / ${config?.model ?? run?.model ?? "default"}`} />
        <AgentFact label="Mode" value={`${config?.mode ?? "hybrid"} · ${config?.strictness_level ?? "balanced"} · ${config?.confidence_threshold ?? "medium"}`} />
        <AgentFact label="Tools/data access" value={toolsFor(agent.agent_id)} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2 text-xs">
        <Badge>{run?.recommendation_ids?.length ?? 0} recommendations</Badge>
        <Badge>{run?.latency_ms ? `${run.latency_ms} ms` : "cost/time n/a"}</Badge>
        <Badge>{run?.created_at ? new Date(run.created_at).toLocaleDateString() : "no run"}</Badge>
      </div>
      {run?.error_json && Object.keys(run.error_json).length ? <p className="mt-3 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-semibold text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100">Error state: validation or provider issue</p> : null}
      <div className="mt-4 flex flex-wrap gap-2">
        <Button className="px-3" onClick={onSelect} type="button"><Settings size={16} /> Configure</Button>
        <Button className="bg-white px-3 text-slate-950 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-white/10 dark:text-white dark:ring-white/10" onClick={onSelect} type="button"><Eye size={16} /> View trace</Button>
      </div>
    </article>
  );
}

function WorkflowCanvas({ nodes, edges, selectedAgentId, onSelect }: { nodes: CanvasNode[]; edges: CanvasEdge[]; selectedAgentId: string; onSelect: (agentId: string) => void }) {
  return (
    <section className="min-w-0 overflow-hidden rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top_right,_rgba(34,211,238,0.18),_transparent_35%),linear-gradient(135deg,#020617,#111827_45%,#1e1b4b)] p-5 shadow-xl shadow-slate-950/20 sm:p-6" id="workflow-canvas">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-indigo-200">Visual Workflow Canvas</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-white">How agents pass data to approval</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <CanvasLegend status="running" label="Running" />
          <CanvasLegend status="completed" label="Completed" />
          <CanvasLegend status="failed" label="Failed" />
          <CanvasLegend status="approval_needed" label="Approval needed" />
        </div>
      </div>
      <div className="overflow-x-auto pb-3">
        <div className="flex min-w-max items-center gap-4">
          {nodes.map((node, index) => (
            <div className="flex items-center gap-4" key={node.agent_id}>
              <button className={`group min-w-[220px] max-w-[240px] rounded-3xl border p-4 text-left outline-none transition hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-white ${node.agent_id === selectedAgentId ? "border-white bg-white/18 shadow-2xl shadow-indigo-500/30" : nodeClass(node.status)}`} onClick={() => onSelect(node.agent_id)} type="button">
                <div className="flex items-center justify-between gap-3">
                  <span className={`flex h-11 w-11 items-center justify-center rounded-2xl ${nodeIconClass(node.status)}`}>{agentIcon(node.agent_id)}</span>
                  <StatusBadge status={node.status} />
                </div>
                <p className="mt-4 text-sm font-semibold leading-5 text-white">{node.display_name}</p>
                <p className="mt-2 line-clamp-2 text-xs leading-5 text-indigo-100">{node.current_task}</p>
                <p className="mt-3 text-xs font-semibold text-indigo-200">{node.recommendations_created} recommendations</p>
              </button>
              {index < nodes.length - 1 ? <WorkflowEdge edge={edges[index]} active={["running", "completed", "succeeded"].includes(node.status)} /> : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ApprovalCheckpointSummary({ pendingApprovals, highPriorityCount, dangerousCount, onDecision }: { pendingApprovals: Recommendation[]; highPriorityCount: number; dangerousCount: number; onDecision: (recommendationId: string, decision: "approve" | "reject") => void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/70" id="approval-checkpoints">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-violet-600 dark:text-violet-200">Human Approval Checkpoints</p>
          <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">{pendingApprovals.length} recommendations waiting approval</h2>
        </div>
        <div className="flex flex-wrap gap-2">
          <Badge>{highPriorityCount} high priority</Badge>
          <Badge>{dangerousCount} risky actions</Badge>
          <Badge>AI confidence visible</Badge>
        </div>
      </div>
      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        {pendingApprovals.slice(0, 4).map((item) => <ApprovalCard recommendation={item} key={item.id} onDecision={onDecision} />)}
        {!pendingApprovals.length ? <div className="rounded-2xl border border-dashed border-slate-300 p-6 text-sm text-slate-600 dark:border-white/15 dark:text-slate-300">No pending approvals yet. Recommendations created by agents will appear here as business-friendly cards with metric evidence and risk notes.</div> : null}
      </div>
    </section>
  );
}

function ApprovalCard({ recommendation, onDecision }: { recommendation: Recommendation; onDecision: (recommendationId: string, decision: "approve" | "reject") => void }) {
  return (
    <article className="rounded-3xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
      <div className="flex flex-wrap gap-2">
        <Badge>{humanize(recommendation.recommendation_type)}</Badge>
        <Badge>{recommendation.priority}</Badge>
        <Badge>{recommendation.confidence}</Badge>
      </div>
      <h3 className="mt-3 text-base font-semibold text-slate-950 dark:text-white">{recommendation.campaign_name || "Account-level recommendation"}</h3>
      <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">{recommendation.explanation_json?.summary ?? "Review metric evidence before deciding."}</p>
      <div className="mt-3 grid gap-2 text-xs md:grid-cols-2">
        <AgentFact label="Product/ASIN" value={String(recommendation.evidence_json?.asin ?? recommendation.product_id ?? "Not linked")} />
        <AgentFact label="Ad group" value={recommendation.ad_group_name || "Not specified"} />
        <AgentFact label="Target/search term" value={recommendation.customer_search_term || recommendation.targeting || "Not specified"} />
        <AgentFact label="Agent source" value={String(recommendation.evidence_json?.decision_source ?? recommendation.rule_name)} />
      </div>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm font-semibold text-indigo-700 dark:text-indigo-200">Why this recommendation?</summary>
        <div className="mt-3 overflow-x-auto rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-slate-950/70">
          <MetricTable metrics={recommendation.current_metric_snapshot_json || recommendation.input_metrics_json} />
        </div>
      </details>
      <div className="mt-3 flex flex-wrap gap-2">
        <SafetyPill light text="Recommendation only" />
        <SafetyPill light text="Requires human approval" />
        <SafetyPill light text="No live Amazon Ads change executed" />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Button onClick={() => onDecision(recommendation.id, "approve")} type="button"><CheckCircle2 size={16} /> Approve</Button>
        <Button className="bg-red-700 hover:bg-red-600 dark:bg-red-200 dark:text-red-950" onClick={() => onDecision(recommendation.id, "reject")} type="button"><Square size={16} /> Reject</Button>
        <Button className="bg-white text-slate-950 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-white/10 dark:text-white dark:ring-white/10" type="button"><Settings size={16} /> Edit</Button>
      </div>
    </article>
  );
}

function AgentTemplates({ onApply }: { onApply: (name: string) => void }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm dark:border-white/10 dark:bg-slate-950/70" id="agent-settings">
      <div className="mb-4">
        <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Agent Templates</p>
        <h2 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Future-ready team presets</h2>
      </div>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-3">
        {templates.map(([name, description]) => (
          <article className="rounded-3xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5" key={name}>
            <p className="font-semibold text-slate-950 dark:text-white">{name}</p>
            <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{description}</p>
            <Button className="mt-4 bg-white text-slate-950 ring-1 ring-slate-200 hover:bg-slate-50 dark:bg-white/10 dark:text-white dark:ring-white/10" onClick={() => onApply(name)} type="button">Apply template</Button>
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

function edgeSummary(source: string, target: string) {
  const summaries: Record<string, string[]> = {
    "report_upload_node:report_detection_agent": ["headers", "sample rows", "file metadata"],
    "report_detection_agent:product_resolution_agent": ["report type", "missing columns", "entity levels"],
    "product_resolution_agent:metrics_analysis_agent": ["ASIN/SKU groups", "campaign groups", "mapping suggestions"],
    "metrics_analysis_agent:ai_recommendation_brain_agent": ["grouped metrics", "winners", "wasters", "quality warnings"],
    "ai_recommendation_brain_agent:bid_optimization_agent": ["bid candidates", "confidence", "risk notes"],
    "ai_recommendation_brain_agent:negative_keyword_agent": ["wasted search terms", "negative candidates"],
    "ai_recommendation_brain_agent:budget_allocation_agent": ["budget pressure", "spend/sales shares"],
    "ai_recommendation_brain_agent:pause_review_agent": ["zero-order spend", "pause candidates"],
    "stakeholder_reporting_agent:human_approval_agent": ["approver notes", "recommendation queue"],
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
    report_detection_agent: "Detect report type and missing columns",
    product_resolution_agent: "Resolve ASINs, SKUs, and product mappings",
    metrics_analysis_agent: "Analyze account, product, campaign, keyword, and search-term metrics",
    ai_recommendation_brain_agent: "Generate strict JSON recommendations",
    bid_optimization_agent: "Review bid increase/decrease risk",
    negative_keyword_agent: "Review wasted search terms",
    budget_allocation_agent: "Review budget pressure",
    pause_review_agent: "Review pause candidates",
    stakeholder_reporting_agent: "Create summaries and approver notes",
    human_approval_agent: "Route recommendations to approval queue",
  };
  return tasks[agentId] ?? "Inspect evidence";
}

function toolsFor(agentId: string) {
  if (agentId.includes("brain")) return "DeepSeek, grouped metrics, validation schema";
  if (agentId.includes("approval")) return "Recommendation queue, audit trail";
  if (agentId.includes("detection") || agentId.includes("resolution")) return "Parsed reports, product profiles";
  return "Reports, rollups, recommendation evidence";
}

function WorkflowEdge({ edge, active }: { edge?: CanvasEdge; active: boolean }) {
  return (
    <div className="w-28 shrink-0">
      <div className={`h-1 rounded-full ${active ? "bg-gradient-to-r from-emerald-300 via-cyan-300 to-indigo-300 shadow-lg shadow-cyan-500/40" : "bg-white/20"}`} />
      <p className="mt-2 line-clamp-2 text-center text-[11px] font-medium text-indigo-100">{edge?.data_passed_summary?.slice(0, 2).join(" + ") ?? "evidence"}</p>
    </div>
  );
}

function CanvasLegend({ status, label }: { status: string; label: string }) {
  return <span className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/10 px-3 py-1.5 text-xs font-semibold text-indigo-50"><span className={`h-2.5 w-2.5 rounded-full ${dotClass(status)}`} />{label}</span>;
}

function nodeClass(status: string) {
  if (status === "failed") return "border-red-400/40 bg-red-500/10 shadow-red-500/15";
  if (status === "approval_needed") return "border-violet-300/50 bg-violet-400/15 shadow-violet-500/25";
  if (status === "completed" || status === "succeeded") return "border-emerald-300/40 bg-emerald-400/10 shadow-emerald-500/15";
  if (status === "running" || status === "queued") return "border-indigo-300/50 bg-indigo-400/15 shadow-indigo-500/25";
  if (status === "paused" || status === "waiting") return "border-amber-300/40 bg-amber-400/10 shadow-amber-500/15";
  return "border-white/10 bg-white/8 shadow-slate-950/10";
}

function nodeIconClass(status: string) {
  if (status === "failed") return "bg-red-400 text-white";
  if (status === "approval_needed") return "bg-violet-300 text-violet-950";
  if (status === "completed" || status === "succeeded") return "bg-emerald-300 text-emerald-950";
  if (status === "running" || status === "queued") return "bg-indigo-300 text-indigo-950";
  if (status === "paused" || status === "waiting") return "bg-amber-300 text-amber-950";
  return "bg-white/15 text-white";
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
  return <div className="rounded-2xl border border-slate-200 bg-slate-50 px-3 py-2 dark:border-white/10 dark:bg-slate-950/50"><p className="font-semibold text-slate-500 dark:text-slate-400">{label}</p><p className="mt-1 text-slate-900 dark:text-white">{value}</p></div>;
}

function StepMetric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-2xl border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5"><p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p><p className="mt-1 text-2xl font-semibold text-slate-950 dark:text-white">{value}</p></div>;
}

function MetricTable({ metrics }: { metrics: Record<string, unknown> }) {
  const entries = Object.entries(metrics).slice(0, 8);
  return <table className="w-full text-left text-xs"><tbody>{entries.map(([key, value]) => <tr className="border-b border-slate-100 last:border-0 dark:border-white/10" key={key}><th className="py-2 pr-3 font-semibold text-slate-600 dark:text-slate-300">{humanize(key)}</th><td className="py-2 text-slate-950 dark:text-white">{String(value)}</td></tr>)}</tbody></table>;
}

function SafetyPill({ text, light = false }: { text: string; light?: boolean }) {
  return <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold ${light ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100" : "border-white/15 bg-white/10 text-emerald-50"}`}><ShieldCheck size={14} /> {text}</span>;
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="inline-flex rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200">{children}</span>;
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
