"use client";

import { AlertTriangle, CheckCircle2, ChevronDown, Clock3, Loader2, Pause, SkipForward, Square } from "lucide-react";
import type { AgentEvent, AgentRun } from "@/lib/api/agents";

const eventTone: Record<string, string> = {
  agent_queued: "border-sky-300 bg-sky-50 text-sky-800 dark:border-sky-300/25 dark:bg-sky-300/10 dark:text-sky-100",
  agent_started: "border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100",
  input_prepared: "border-cyan-300 bg-cyan-50 text-cyan-800 dark:border-cyan-300/25 dark:bg-cyan-300/10 dark:text-cyan-100",
  model_called: "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-300/25 dark:bg-violet-300/10 dark:text-violet-100",
  output_received: "border-blue-300 bg-blue-50 text-blue-800 dark:border-blue-300/25 dark:bg-blue-300/10 dark:text-blue-100",
  output_validated: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
  recommendations_created: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
  waiting_for_human: "border-violet-300 bg-violet-50 text-violet-800 dark:border-violet-300/25 dark:bg-violet-300/10 dark:text-violet-100",
  agent_succeeded: "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
  agent_failed: "border-red-300 bg-red-50 text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100",
  agent_skipped: "border-slate-300 bg-slate-50 text-slate-700 dark:border-white/15 dark:bg-white/10 dark:text-slate-200",
  agent_paused: "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100",
  agent_stopped: "border-zinc-300 bg-zinc-100 text-zinc-800 dark:border-white/15 dark:bg-white/10 dark:text-zinc-100",
  fallback_used: "border-orange-300 bg-orange-50 text-orange-800 dark:border-orange-300/25 dark:bg-orange-300/10 dark:text-orange-100",
};

export function AgentTraceTimeline({ events, runs }: { events: AgentEvent[]; runs: AgentRun[] }) {
  const fallbackEvents = events.length ? events : runs.slice(0, 8).map((run) => runToEvent(run));
  return (
    <section className="overflow-hidden rounded-3xl border border-slate-200/80 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/70">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 dark:border-white/10">
        <div>
          <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Trace Timeline</h2>
          <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Execution feed across model calls, validation, fallback, and approval checkpoints.</p>
        </div>
      </div>
      <div className="max-h-[520px] overflow-auto">
        {fallbackEvents.length ? (
          <ol className="divide-y divide-slate-100 dark:divide-white/10">
            {fallbackEvents.map((event, index) => (
              <li className="px-5 py-4" key={event.id}>
                <details className="group">
                  <summary className="flex cursor-pointer list-none items-start gap-4 rounded-2xl p-2 outline-none transition hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-indigo-400 dark:hover:bg-white/5">
                    <span className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-white">
                      {eventIcon(event.event_type)}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2">
                        <span className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${eventTone[event.event_type] ?? eventTone.agent_queued}`}>{humanize(event.event_type)}</span>
                        <span className="text-sm font-semibold text-slate-950 dark:text-white">{humanize(event.agent_id)}</span>
                        <span className="text-xs text-slate-500 dark:text-slate-400">{formatTime(event.created_at)}</span>
                      </span>
                      <span className="mt-2 block text-sm leading-6 text-slate-600 dark:text-slate-300">{event.message}</span>
                    </span>
                    <ChevronDown className="mt-2 text-slate-400 transition group-open:rotate-180" size={16} />
                  </summary>
                  <div className="ml-14 mt-3 grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 md:grid-cols-3">
                    <TraceFact label="Provider/model" value={providerModel(event)} />
                    <TraceFact label="Latency" value={latency(event)} />
                    <TraceFact label="Cost" value={String(event.metadata_json?.cost ?? "Not reported")} />
                    <div className="md:col-span-3">
                      <p className="font-semibold text-slate-900 dark:text-white">Output summary</p>
                      <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded-2xl bg-white p-3 text-xs dark:bg-slate-950/70">{JSON.stringify(event.metadata_json ?? {}, null, 2)}</pre>
                    </div>
                  </div>
                </details>
              </li>
            ))}
          </ol>
        ) : (
          <div className="px-5 py-12 text-sm text-slate-600 dark:text-slate-300">No trace events yet. Run analysis to populate agent started, model called, validation, fallback, and approval-needed events.</div>
        )}
      </div>
    </section>
  );
}

function TraceFact({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-semibold text-slate-900 dark:text-white">{label}</p>
      <p className="mt-1 text-slate-600 dark:text-slate-300">{value}</p>
    </div>
  );
}

function runToEvent(run: AgentRun): AgentEvent {
  return {
    id: `run-${run.id}`,
    agent_id: run.agent_id,
    agent_run_id: run.id,
    monitoring_import_id: run.monitoring_import_id,
    event_type: run.status === "failed" ? "agent_failed" : run.status === "skipped" ? "agent_skipped" : run.status === "paused" ? "agent_paused" : run.status === "stopped" ? "agent_stopped" : "agent_succeeded",
    message: run.status === "failed" ? "Agent run ended with validation errors or provider failure." : `Agent run finished with status ${run.status}.`,
    metadata_json: {
      provider: run.provider,
      model: run.model,
      latency_ms: run.latency_ms,
      recommendation_ids: run.recommendation_ids,
      validation_errors: run.error_json?.validation_errors ?? [],
      execution_boundary: "no_live_amazon_change",
    },
    created_at: run.created_at,
  };
}

function eventIcon(eventType: string) {
  if (eventType.includes("failed")) return <AlertTriangle size={17} />;
  if (eventType.includes("paused")) return <Pause size={17} />;
  if (eventType.includes("stopped")) return <Square size={17} />;
  if (eventType.includes("skipped")) return <SkipForward size={17} />;
  if (eventType.includes("started") || eventType.includes("called")) return <Loader2 size={17} />;
  if (eventType.includes("succeeded") || eventType.includes("validated")) return <CheckCircle2 size={17} />;
  return <Clock3 size={17} />;
}

function providerModel(event: AgentEvent) {
  const provider = event.metadata_json?.provider;
  const model = event.metadata_json?.model;
  return provider || model ? `${provider ?? "unknown"} / ${model ?? "unknown"}` : "Not reported";
}

function latency(event: AgentEvent) {
  const value = event.metadata_json?.latency_ms;
  return typeof value === "number" ? `${value} ms` : "Not reported";
}

function formatTime(value: string) {
  return new Date(value).toLocaleString();
}

function humanize(value: string) {
  return value.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}
