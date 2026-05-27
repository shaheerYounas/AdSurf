"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronRight,
  Eye,
  FileText,
  GitBranch,
  Loader2,
  Pause,
  Play,
  RotateCcw,
  Settings,
  ShieldCheck,
  Sparkles,
  Square,
  ToggleLeft,
  ToggleRight,
  WandSparkles,
} from "lucide-react";
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
  type AgentRun,
  type AgentWorkflow,
} from "@/lib/api/agents";

type ControlAction = "pause" | "resume" | "stop" | "rerun";

const statusTone: Record<string, string> = {
  succeeded: "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-100",
  running: "border-indigo-200 bg-indigo-50 text-indigo-800 dark:border-indigo-300/20 dark:bg-indigo-300/10 dark:text-indigo-100",
  queued: "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-300/20 dark:bg-sky-300/10 dark:text-sky-100",
  paused: "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-100",
  stopped: "border-slate-200 bg-slate-100 text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200",
  failed: "border-red-200 bg-red-50 text-red-800 dark:border-red-300/20 dark:bg-red-300/10 dark:text-red-100",
  skipped: "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300",
  pending: "border-slate-200 bg-white text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300",
};

export function AgentControlCenter({ productId, importId }: { productId?: string; importId?: string }) {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [agents, setAgents] = useState<AgentDefinition[]>([]);
  const [configs, setConfigs] = useState<AgentConfig[]>([]);
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [workflow, setWorkflow] = useState<AgentWorkflow | null>(null);
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const configByAgent = useMemo(() => new Map(configs.map((config) => [config.agent_id, config])), [configs]);
  const latestRunByAgent = useMemo(() => {
    const map = new Map<string, AgentRun>();
    for (const run of runs) if (!map.has(run.agent_id)) map.set(run.agent_id, run);
    return map;
  }, [runs]);
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? (selectedAgentId ? latestRunByAgent.get(selectedAgentId) : undefined);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? agents[0];
  const activeCount = runs.filter((run) => ["running", "queued"].includes(run.status)).length;
  const pendingRecommendations = runs.reduce((total, run) => total + (run.recommendation_ids?.length ?? 0), 0);
  const disabledCount = configs.filter((config) => !config.enabled).length;

  async function load() {
    setMessage(null);
    setIsLoading(true);
    try {
      const [loadedAgents, loadedConfigs, loadedRuns] = await Promise.all([getAgents(workspaceId), getAgentConfigs(workspaceId, productId), getAgentRuns(workspaceId, importId)]);
      setAgents(loadedAgents);
      setConfigs(loadedConfigs);
      setRuns(loadedRuns);
      if (importId) setWorkflow(await getAgentWorkflow(importId, workspaceId));
      setSelectedAgentId((current) => current || loadedAgents[0]?.agent_id || null);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Agent Control Center could not be loaded.");
    } finally {
      setIsLoading(false);
    }
  }

  async function toggleAgent(agentId: string) {
    const current = configByAgent.get(agentId);
    if (!current) return;
    await updateAgentConfig(agentId, { enabled: !current.enabled, reason: current.enabled ? "Disabled from Agent Control Center" : "Enabled from Agent Control Center", product_id: productId ?? null }, workspaceId);
    await load();
  }

  async function saveConfig(agentId: string, patch: Partial<AgentConfig>) {
    await updateAgentConfig(agentId, { ...patch, product_id: productId ?? null, reason: "Updated from Agent Control Center" }, workspaceId);
    await load();
  }

  async function control(runId: string, action: ControlAction) {
    await controlAgentRun(runId, action, `${action} requested from Agent Control Center`, workspaceId);
    await load();
  }

  async function rerunHere(agentId: string) {
    if (!importId) return;
    await rerunFromAgent(importId, agentId, "Rerun from this agent onward", workspaceId);
    await load();
  }

  return (
    <div className="space-y-6">
      <section className="glass-panel overflow-hidden rounded-[2rem] p-5 sm:p-6">
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_360px]">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-200/70 bg-indigo-50/80 px-3 py-1 text-xs font-bold uppercase tracking-[0.2em] text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-300/10 dark:text-indigo-200">
              <WandSparkles size={14} /> AI-native workflow
            </div>
            <h3 className="mt-4 text-3xl font-semibold tracking-[-0.04em] text-slate-950 dark:text-white sm:text-4xl">Watch and control every agent before recommendations reach approval.</h3>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600 dark:text-slate-300">
              Agents can inspect uploaded Amazon Ads data, pass evidence to each other, and generate recommendations. Users stay in control: pause, stop, rerun, configure, inspect evidence, and approve only when ready.
            </p>
            <div className="mt-5 flex flex-wrap gap-2">
              <SafetyPill icon={<ShieldCheck size={15} />} text="Recommendation only" />
              <SafetyPill icon={<Eye size={15} />} text="Evidence visible" />
              <SafetyPill icon={<CheckCircle2 size={15} />} text="Human approval required" />
            </div>
          </div>
          <div className="rounded-[1.5rem] border border-white/60 bg-white/70 p-4 shadow-sm dark:border-white/10 dark:bg-white/5">
            <label className="space-y-2 text-sm font-semibold text-slate-700 dark:text-slate-200">
              Workspace ID
              <input className="block w-full rounded-2xl border border-slate-200 bg-white/90 px-4 py-3 font-mono text-sm text-slate-950 shadow-inner outline-none transition focus:border-indigo-300 dark:border-white/10 dark:bg-slate-950/40 dark:text-white" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
            </label>
            <Button className="mt-3 w-full" disabled={isLoading} onClick={load} type="button">
              {isLoading ? <Loader2 className="animate-spin" size={16} /> : <RotateCcw size={16} />}
              Refresh control center
            </Button>
            {message ? <p className="mt-3 rounded-2xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-300/20 dark:bg-red-300/10 dark:text-red-100">{message}</p> : null}
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-4">
        <MetricCard label="Registered agents" value={agents.length} icon={<Bot size={18} />} />
        <MetricCard label="Active or queued" value={activeCount} icon={<Sparkles size={18} />} />
        <MetricCard label="Linked outputs" value={pendingRecommendations} icon={<FileText size={18} />} />
        <MetricCard label="Disabled agents" value={disabledCount} icon={<ToggleLeft size={18} />} />
      </div>

      <section className="space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Agent overview</p>
            <h3 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">Operational cards</h3>
          </div>
          <p className="max-w-xl text-sm text-slate-600 dark:text-slate-300">Each card shows status, mode, strictness, and outputs so new users can understand what the agent is doing.</p>
        </div>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => {
            const config = configByAgent.get(agent.agent_id);
            const run = latestRunByAgent.get(agent.agent_id);
            const status = run?.status ?? (config?.enabled ? "pending" : "skipped");
            const selected = selectedAgentId === agent.agent_id;
            return (
              <button
                className={`motion-safe-lift rounded-[1.5rem] border p-5 text-left shadow-sm backdrop-blur transition ${selected ? "border-indigo-300 bg-indigo-50/80 shadow-indigo-950/10 dark:border-indigo-300/40 dark:bg-indigo-300/10" : "border-white/60 bg-white/75 hover:border-indigo-200 hover:bg-white/90 dark:border-white/10 dark:bg-white/5 dark:hover:bg-white/10"}`}
                key={agent.agent_id}
                onClick={() => { setSelectedAgentId(agent.agent_id); setSelectedRunId(run?.id ?? null); }}
                type="button"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex gap-3">
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-slate-950/10 dark:bg-white dark:text-slate-950">
                      {agent.task_type === "decision" ? <BrainCircuit size={20} /> : <Bot size={19} />}
                    </span>
                    <div>
                      <p className="font-semibold text-slate-950 dark:text-white">{agent.display_name}</p>
                      <p className="mt-1 line-clamp-3 text-sm leading-6 text-slate-600 dark:text-slate-300">{agent.description}</p>
                    </div>
                  </div>
                  {config?.enabled ? <ToggleRight className="text-emerald-600" size={24} /> : <ToggleLeft className="text-slate-400" size={24} />}
                </div>
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  <Badge tone={status}>{status}</Badge>
                  <Badge>{config?.mode ?? "hybrid"}</Badge>
                  <Badge>{config?.strictness_level ?? "balanced"}</Badge>
                  <Badge>{run?.recommendation_ids.length ?? 0} outputs</Badge>
                </div>
                <div className="mt-4 flex items-center justify-between gap-3 border-t border-slate-200/70 pt-3 text-xs text-slate-500 dark:border-white/10 dark:text-slate-400">
                  <span>Last run {run?.created_at ? new Date(run.created_at).toLocaleString() : "not yet"}</span>
                  {run?.error_json && Object.keys(run.error_json).length ? <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-300"><AlertTriangle size={13} /> Review</span> : null}
                </div>
              </button>
            );
          })}
        </div>
      </section>

      {workflow ? <WorkflowGraph workflow={workflow} onSelect={setSelectedAgentId} /> : <EmptyWorkflowNotice />}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_440px]">
        <div className="premium-card overflow-hidden rounded-[1.75rem]">
          <div className="flex items-center justify-between gap-3 border-b border-slate-200/70 px-5 py-4 dark:border-white/10">
            <div>
              <p className="flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-white"><GitBranch size={16} /> Agent timeline</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">A chronological audit trail of agent events for the selected import.</p>
            </div>
          </div>
          {workflow?.events.length ? (
            <ol className="divide-y divide-slate-100 dark:divide-white/10">
              {workflow.events.map((event, index) => (
                <li className="grid gap-3 px-5 py-4 text-sm sm:grid-cols-[36px_minmax(0,1fr)]" key={event.id}>
                  <span className="flex h-9 w-9 items-center justify-center rounded-full border border-indigo-200 bg-indigo-50 text-xs font-bold text-indigo-700 dark:border-indigo-300/20 dark:bg-indigo-300/10 dark:text-indigo-100">{index + 1}</span>
                  <div>
                    <p className="font-semibold text-slate-950 dark:text-white">{humanize(event.event_type)} · {humanize(event.agent_id)}</p>
                    <p className="mt-1 text-slate-600 dark:text-slate-300">{event.message}</p>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{new Date(event.created_at).toLocaleString()}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : <p className="px-5 py-10 text-sm text-slate-600 dark:text-slate-300">Open an import-level agent page to see chronological events.</p>}
        </div>

        {selectedAgent ? (
          <aside className="premium-card rounded-[1.75rem] p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 text-lg font-semibold text-slate-950 dark:text-white"><Bot size={18} /> {selectedAgent.display_name}</p>
                <p className="mt-2 text-sm leading-6 text-slate-600 dark:text-slate-300">{selectedAgent.description}</p>
              </div>
              <Button className="bg-slate-800 px-3 dark:bg-white" onClick={() => toggleAgent(selectedAgent.agent_id)} type="button">{configByAgent.get(selectedAgent.agent_id)?.enabled ? "Disable" : "Enable"}</Button>
            </div>

            <ConfigPanel config={configByAgent.get(selectedAgent.agent_id)} onSave={(patch) => saveConfig(selectedAgent.agent_id, patch)} />
            <RunControls importId={importId} onControl={control} onRerunHere={() => rerunHere(selectedAgent.agent_id)} run={selectedRun} />

            <div className="mt-5 space-y-3">
              <JsonBlock label="Input evidence" value={selectedRun?.input_json ?? { dependencies: selectedAgent.input_dependencies }} />
              <JsonBlock label="Agent output" value={selectedRun?.output_json ?? { output_type: selectedAgent.output_type }} />
              <JsonBlock label="Safety boundary" value={{ recommendation_only: true, requires_human_approval: true, can_mutate_live_amazon_ads: false, cannot_approve_or_reject: true }} />
            </div>
          </aside>
        ) : null}
      </section>
    </div>
  );
}

function WorkflowGraph({ workflow, onSelect }: { workflow: AgentWorkflow; onSelect: (agentId: string) => void }) {
  return (
    <section className="premium-card rounded-[1.75rem] p-5">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400">Agent workflow graph</p>
          <h3 className="mt-1 text-2xl font-semibold tracking-tight text-slate-950 dark:text-white">How agents pass evidence</h3>
        </div>
        <Badge>Import {workflow.monitoring_import_id.slice(0, 8)}</Badge>
      </div>
      <div className="flex snap-x gap-3 overflow-x-auto pb-2">
        {workflow.nodes.map((node, index) => (
          <div className="flex shrink-0 items-center gap-3" key={node.agent_id}>
            <button className="min-h-32 w-56 rounded-[1.35rem] border border-slate-200 bg-white/80 p-4 text-left shadow-sm transition hover:-translate-y-0.5 hover:border-indigo-200 hover:shadow-lg dark:border-white/10 dark:bg-white/5" onClick={() => onSelect(node.agent_id)} type="button">
              <Badge tone={node.status}>{node.status}</Badge>
              <p className="mt-3 text-sm font-semibold text-slate-950 dark:text-white">{node.display_name}</p>
              <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{node.mode} · {node.strictness_level}</p>
              <p className="mt-3 text-xs text-slate-600 dark:text-slate-300">{node.recommendations_created} outputs created</p>
            </button>
            {index < workflow.nodes.length - 1 ? <ChevronRight className="text-slate-400" size={20} /> : null}
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-3 md:grid-cols-2">
        {workflow.edges.map((edge) => (
          <div className="rounded-[1.25rem] border border-slate-200/80 bg-slate-50/80 p-4 text-xs text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300" key={`${edge.source_agent_id}-${edge.target_agent_id}`}>
            <p className="font-semibold text-slate-950 dark:text-white">{humanize(edge.source_agent_id)} → {humanize(edge.target_agent_id)}</p>
            <p className="mt-2"><span className="font-medium">Status:</span> {edge.status}</p>
            <p className="mt-2 leading-5"><span className="font-medium">Data passed:</span> {edge.data_passed_summary.join(", ")}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function EmptyWorkflowNotice() {
  return (
    <section className="rounded-[1.75rem] border border-dashed border-slate-300 bg-white/55 p-6 text-sm text-slate-600 backdrop-blur dark:border-white/15 dark:bg-white/5 dark:text-slate-300">
      <p className="flex items-center gap-2 font-semibold text-slate-900 dark:text-white"><GitBranch size={16} /> Workflow graph appears after selecting a monitoring import.</p>
      <p className="mt-2">The workspace-level Agents page shows configuration and latest runs. Import-level pages show the full agent-to-agent evidence flow.</p>
    </section>
  );
}

function ConfigPanel({ config, onSave }: { config?: AgentConfig; onSave: (patch: Partial<AgentConfig>) => void }) {
  if (!config) return null;
  return (
    <div className="mt-5 rounded-[1.25rem] border border-slate-200 bg-slate-50/80 p-4 dark:border-white/10 dark:bg-white/5">
      <p className="mb-3 flex items-center gap-2 text-sm font-semibold text-slate-950 dark:text-white"><Settings size={15} /> Performance controls</p>
      <div className="grid gap-3 text-sm">
        <Select label="Mode" onChange={(mode) => onSave({ mode: mode as AgentConfig["mode"] })} options={["deterministic", "ai", "hybrid"]} value={config.mode} />
        <Select label="Strictness" onChange={(strictness_level) => onSave({ strictness_level: strictness_level as AgentConfig["strictness_level"] })} options={["conservative", "balanced", "aggressive"]} value={config.strictness_level} />
        <Select label="Confidence" onChange={(confidence_threshold) => onSave({ confidence_threshold: confidence_threshold as AgentConfig["confidence_threshold"] })} options={["low", "medium", "high"]} value={config.confidence_threshold} />
      </div>
    </div>
  );
}

function RunControls({ importId, run, onControl, onRerunHere }: { importId?: string; run?: AgentRun; onControl: (runId: string, action: ControlAction) => void; onRerunHere: () => void }) {
  return (
    <div className="mt-5 rounded-[1.25rem] border border-slate-200 bg-white/70 p-4 dark:border-white/10 dark:bg-white/5">
      <p className="mb-3 text-sm font-semibold text-slate-950 dark:text-white">Run controls</p>
      <div className="flex flex-wrap gap-2">
        <Button disabled={!run} onClick={() => run && onControl(run.id, "pause")} type="button"><Pause size={14} /> Pause</Button>
        <Button disabled={!run} onClick={() => run && onControl(run.id, "resume")} type="button"><Play size={14} /> Resume</Button>
        <Button className="bg-slate-800 dark:bg-white" disabled={!run} onClick={() => run && onControl(run.id, "stop")} type="button"><Square size={14} /> Stop</Button>
        <Button disabled={!run} onClick={() => run && onControl(run.id, "rerun")} type="button"><RotateCcw size={14} /> Rerun</Button>
        <Button className="bg-indigo-600 hover:bg-indigo-500 dark:bg-indigo-200 dark:text-indigo-950" disabled={!importId} onClick={onRerunHere} type="button">Rerun from here</Button>
      </div>
      <p className="mt-3 text-xs leading-5 text-slate-500 dark:text-slate-400">Controls update app workflow state and audit logs. They do not execute Amazon Ads changes.</p>
    </div>
  );
}

function MetricCard({ icon, label, value }: { icon: React.ReactNode; label: string; value: number }) {
  return (
    <div className="premium-card motion-safe-lift rounded-[1.5rem] p-5">
      <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">{icon}{label}</div>
      <p className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white">{value}</p>
    </div>
  );
}

function SafetyPill({ icon, text }: { icon: React.ReactNode; text: string }) {
  return <span className="inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 dark:border-emerald-300/20 dark:bg-emerald-300/10 dark:text-emerald-100">{icon}{text}</span>;
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="rounded-[1.25rem] border border-slate-200 bg-slate-50/80 p-3 dark:border-white/10 dark:bg-white/5">
      <summary className="cursor-pointer text-sm font-semibold text-slate-950 dark:text-white">{label}</summary>
      <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap rounded-2xl bg-white/80 p-3 text-xs text-slate-700 dark:bg-slate-950/50 dark:text-slate-200">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function Select({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (value: string) => void }) {
  return (
    <label className="space-y-1">
      <span className="block text-xs font-semibold text-slate-600 dark:text-slate-300">{label}</span>
      <select className="w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-slate-950 outline-none transition focus:border-indigo-300 dark:border-white/10 dark:bg-slate-950/40 dark:text-white" onChange={(event) => onChange(event.target.value)} value={value}>
        {options.map((option) => <option key={option} value={option}>{humanize(option)}</option>)}
      </select>
    </label>
  );
}

function Badge({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-semibold ${statusTone[tone ?? ""] ?? "border-slate-200 bg-slate-100 text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200"}`}>{children}</span>;
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
