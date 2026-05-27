"use client";

import { useEffect, useMemo, useState } from "react";
import { Bot, GitBranch, Pause, Play, RotateCcw, Settings, Square, ToggleLeft, ToggleRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { defaultWorkspaceId } from "@/lib/api/client";
import { controlAgentRun, getAgentConfigs, getAgentRuns, getAgentWorkflow, getAgents, rerunFromAgent, updateAgentConfig, type AgentConfig, type AgentDefinition, type AgentRun, type AgentWorkflow } from "@/lib/api/agents";

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
  }, []);

  const configByAgent = useMemo(() => new Map(configs.map((config) => [config.agent_id, config])), [configs]);
  const latestRunByAgent = useMemo(() => {
    const map = new Map<string, AgentRun>();
    for (const run of runs) if (!map.has(run.agent_id)) map.set(run.agent_id, run);
    return map;
  }, [runs]);
  const selectedRun = runs.find((run) => run.id === selectedRunId) ?? (selectedAgentId ? latestRunByAgent.get(selectedAgentId) : undefined);
  const selectedAgent = agents.find((agent) => agent.agent_id === selectedAgentId) ?? agents[0];

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

  async function control(runId: string, action: "pause" | "resume" | "stop" | "rerun") {
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
      <div className="rounded-md border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-2 text-sm font-medium text-slate-700">
            Workspace ID
            <input className="block w-72 rounded-md border border-slate-300 px-3 py-2 font-mono text-sm" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
          </label>
          <Button disabled={isLoading} onClick={load} type="button">Refresh</Button>
        </div>
        <p className="mt-3 text-sm text-slate-600">Agents can analyze uploaded Amazon Ads data and create recommendations, but cannot approve, reject, or execute live Amazon Ads changes.</p>
        {message ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p> : null}
      </div>

      <section className="space-y-3">
        <p className="text-sm font-medium text-slate-900">Agent Overview</p>
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {agents.map((agent) => {
          const config = configByAgent.get(agent.agent_id);
          const run = latestRunByAgent.get(agent.agent_id);
          return (
            <button className="rounded-md border border-slate-200 bg-white p-5 text-left hover:border-slate-400" key={agent.agent_id} onClick={() => { setSelectedAgentId(agent.agent_id); setSelectedRunId(run?.id ?? null); }} type="button">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="font-semibold text-slate-950">{agent.display_name}</p>
                  <p className="mt-1 text-sm text-slate-600">{agent.description}</p>
                </div>
                {config?.enabled ? <ToggleRight className="text-emerald-700" size={22} /> : <ToggleLeft className="text-slate-400" size={22} />}
              </div>
              <div className="mt-4 flex flex-wrap gap-2 text-xs">
                <Badge>{run?.status ?? (config?.enabled ? "pending" : "skipped")}</Badge>
                <Badge>{config?.mode ?? "hybrid"}</Badge>
                <Badge>{config?.strictness_level ?? "balanced"}</Badge>
                <Badge>{run?.recommendation_ids.length ?? 0} recommendations</Badge>
              </div>
              <p className="mt-3 text-xs text-slate-500">Last run {run?.created_at ? new Date(run.created_at).toLocaleString() : "not yet run"}</p>
              {run?.error_json && Object.keys(run.error_json).length ? <p className="mt-2 text-xs text-red-700">Errors or validation warnings present</p> : null}
            </button>
          );
        })}
        </div>
      </section>

      {workflow ? <WorkflowGraph workflow={workflow} onSelect={setSelectedAgentId} /> : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_420px]">
        <div className="rounded-md border border-slate-200 bg-white">
          <div className="border-b border-slate-200 px-5 py-4">
            <p className="flex items-center gap-2 text-sm font-medium text-slate-900"><GitBranch size={16} /> Agent Timeline</p>
          </div>
          {workflow?.events.length ? (
            <ol className="divide-y divide-slate-100">
              {workflow.events.map((event) => (
                <li className="px-5 py-3 text-sm" key={event.id}>
                  <p className="font-medium text-slate-900">{event.event_type} / {event.agent_id}</p>
                  <p className="text-slate-600">{event.message}</p>
                  <p className="text-xs text-slate-500">{new Date(event.created_at).toLocaleString()}</p>
                </li>
              ))}
            </ol>
          ) : <p className="px-5 py-8 text-sm text-slate-600">Select an import-level agent page to see chronological events.</p>}
        </div>

        {selectedAgent ? (
          <aside className="rounded-md border border-slate-200 bg-white p-5">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="flex items-center gap-2 font-semibold text-slate-950"><Bot size={18} /> {selectedAgent.display_name}</p>
                <p className="mt-1 text-sm text-slate-600">{selectedAgent.description}</p>
              </div>
              <Button className="bg-slate-700" onClick={() => toggleAgent(selectedAgent.agent_id)} type="button">{configByAgent.get(selectedAgent.agent_id)?.enabled ? "Disable" : "Enable"}</Button>
            </div>

            <ConfigPanel config={configByAgent.get(selectedAgent.agent_id)} onSave={(patch) => saveConfig(selectedAgent.agent_id, patch)} />
            <RunControls importId={importId} onControl={control} onRerunHere={() => rerunHere(selectedAgent.agent_id)} run={selectedRun} />

            <div className="mt-5 space-y-3">
              <JsonBlock label="Input" value={selectedRun?.input_json ?? { dependencies: selectedAgent.input_dependencies }} />
              <JsonBlock label="Output" value={selectedRun?.output_json ?? { output_type: selectedAgent.output_type }} />
              <JsonBlock label="Safety" value={{ requires_human_approval: true, can_mutate_live_amazon_ads: false, cannot_approve_or_reject: true }} />
            </div>
          </aside>
        ) : null}
      </section>
    </div>
  );
}

function WorkflowGraph({ workflow, onSelect }: { workflow: AgentWorkflow; onSelect: (agentId: string) => void }) {
  return (
    <section className="rounded-md border border-slate-200 bg-white p-5">
      <p className="mb-4 text-sm font-medium text-slate-900">Agent Workflow Graph</p>
      <div className="flex flex-wrap items-stretch gap-2">
        {workflow.nodes.map((node, index) => (
          <div className="flex items-center gap-2" key={node.agent_id}>
            <button className="min-w-40 rounded-md border border-slate-200 px-3 py-3 text-left hover:bg-slate-50" onClick={() => onSelect(node.agent_id)} type="button">
              <p className="text-sm font-medium text-slate-950">{node.display_name}</p>
              <p className="mt-1 text-xs text-slate-500">{node.status} / {node.recommendations_created} outputs</p>
            </button>
            {index < workflow.nodes.length - 1 ? <span className="text-slate-400">→</span> : null}
          </div>
        ))}
      </div>
      <div className="mt-5 grid gap-2 md:grid-cols-2">
        {workflow.edges.map((edge) => (
          <div className="rounded-md border border-slate-100 bg-slate-50 p-3 text-xs text-slate-700" key={`${edge.source_agent_id}-${edge.target_agent_id}`}>
            <p className="font-medium text-slate-900">{edge.source_agent_id} → {edge.target_agent_id}</p>
            <p className="mt-1">Status {edge.status}</p>
            <p className="mt-1">Data passed: {edge.data_passed_summary.join(", ")}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ConfigPanel({ config, onSave }: { config?: AgentConfig; onSave: (patch: Partial<AgentConfig>) => void }) {
  if (!config) return null;
  return (
    <div className="mt-5 rounded-md border border-slate-100 bg-slate-50 p-4">
      <p className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-900"><Settings size={15} /> Configuration</p>
      <div className="grid gap-3 text-sm">
        <Select label="Mode" onChange={(mode) => onSave({ mode: mode as AgentConfig["mode"] })} options={["deterministic", "ai", "hybrid"]} value={config.mode} />
        <Select label="Strictness" onChange={(strictness_level) => onSave({ strictness_level: strictness_level as AgentConfig["strictness_level"] })} options={["conservative", "balanced", "aggressive"]} value={config.strictness_level} />
        <Select label="Confidence" onChange={(confidence_threshold) => onSave({ confidence_threshold: confidence_threshold as AgentConfig["confidence_threshold"] })} options={["low", "medium", "high"]} value={config.confidence_threshold} />
      </div>
    </div>
  );
}

function RunControls({ importId, run, onControl, onRerunHere }: { importId?: string; run?: AgentRun; onControl: (runId: string, action: "pause" | "resume" | "stop" | "rerun") => void; onRerunHere: () => void }) {
  return (
    <div className="mt-5 flex flex-wrap gap-2">
      <Button disabled={!run} onClick={() => run && onControl(run.id, "pause")} type="button"><Pause size={14} /> Pause</Button>
      <Button disabled={!run} onClick={() => run && onControl(run.id, "resume")} type="button"><Play size={14} /> Resume</Button>
      <Button className="bg-slate-700" disabled={!run} onClick={() => run && onControl(run.id, "stop")} type="button"><Square size={14} /> Stop</Button>
      <Button disabled={!run} onClick={() => run && onControl(run.id, "rerun")} type="button"><RotateCcw size={14} /> Rerun</Button>
      <Button className="bg-slate-700" disabled={!importId} onClick={onRerunHere} type="button">Rerun from here</Button>
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="rounded-md border border-slate-100 bg-slate-50 p-3">
      <summary className="cursor-pointer text-sm font-medium text-slate-900">{label}</summary>
      <pre className="mt-3 max-h-64 overflow-auto whitespace-pre-wrap text-xs text-slate-700">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function Select({ label, options, value, onChange }: { label: string; options: string[]; value: string; onChange: (value: string) => void }) {
  return (
    <label className="space-y-1">
      <span className="block text-xs font-medium text-slate-600">{label}</span>
      <select className="w-full rounded-md border border-slate-300 px-2 py-2" onChange={(event) => onChange(event.target.value)} value={value}>
        {options.map((option) => <option key={option} value={option}>{option}</option>)}
      </select>
    </label>
  );
}

function Badge({ children }: { children: React.ReactNode }) {
  return <span className="rounded bg-slate-100 px-2 py-1 text-slate-700">{children}</span>;
}
