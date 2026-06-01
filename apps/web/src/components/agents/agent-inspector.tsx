"use client";

import { useMemo, useState } from "react";
import {
  Bot,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  FileInput,
  LockKeyhole,
  SlidersHorizontal,
  TerminalSquare,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSkeleton } from "@/components/ui/loading-spinner";
import { Select as SelectMenu } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { humanize } from "@/lib/utils";
import type {
  AgentConfig,
  AgentDefinition,
  AgentEvent,
  AgentRun,
} from "@/lib/api/agents";
import type { Recommendation } from "@/lib/api/monitoring";

type InspectorTab =
  | "Overview"
  | "Configuration"
  | "Prompt / Business Goal"
  | "Input Data"
  | "Output"
  | "Recommendations"
  | "Permissions"
  | "Trace";

const tabs: InspectorTab[] = [
  "Overview",
  "Configuration",
  "Prompt / Business Goal",
  "Input Data",
  "Output",
  "Recommendations",
  "Permissions",
  "Trace",
];

const MODE_OPTIONS = [
  { value: "deterministic", label: "Deterministic" },
  { value: "ai", label: "AI" },
  { value: "hybrid", label: "Hybrid" },
];

const PROVIDER_OPTIONS = [
  { value: "openai", label: "OpenAI" },
  { value: "anthropic", label: "Anthropic" },
  { value: "deepseek", label: "DeepSeek" },
  { value: "google", label: "Google" },
  { value: "local", label: "Local" },
];

const STRICTNESS_OPTIONS = [
  { value: "conservative", label: "Conservative" },
  { value: "balanced", label: "Balanced" },
  { value: "aggressive", label: "Aggressive" },
];

const CONFIDENCE_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const DEPTH_OPTIONS = [
  { value: "quick", label: "Quick" },
  { value: "standard", label: "Standard" },
  { value: "deep", label: "Deep" },
];

export function AgentInspector({
  agent,
  config,
  run,
  events,
  recommendations,
  advancedMode,
  isLoading,
  onConfigChange,
  onToggleAgent,
}: {
  agent?: AgentDefinition;
  config?: AgentConfig;
  run?: AgentRun;
  events: AgentEvent[];
  recommendations: Recommendation[];
  advancedMode: boolean;
  isLoading?: boolean;
  onConfigChange: (patch: Partial<AgentConfig>) => void;
  onToggleAgent: () => void;
}) {
  const [activeTab, setActiveTab] = useState<InspectorTab>("Overview");
  const relatedRecommendations = useMemo(
    () => relatedForAgent(recommendations, run, agent?.agent_id),
    [agent?.agent_id, recommendations, run],
  );
  if (!agent) {
    return (
      <aside className="w-full rounded-3xl border border-white/10 bg-white p-5 shadow-xl dark:bg-slate-950/80 sm:p-6">
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Select an agent or workflow node to inspect its configuration,
          permissions, trace, and output.
        </p>
      </aside>
    );
  }

  return (
    <aside className="w-full min-w-0 rounded-3xl border border-white/60 bg-white p-5 shadow-xl shadow-slate-950/10 dark:border-white/10 dark:bg-slate-950/85 sm:p-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-1 gap-3">
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-slate-950 text-white shadow-lg shadow-indigo-950/20 dark:bg-white dark:text-slate-950">
            {agent.task_type === "decision" ? (
              <BrainCircuit size={22} />
            ) : (
              <Bot size={21} />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="break-words text-lg font-semibold text-slate-950 dark:text-white">
              {agent.display_name}
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
              {agent.description}
            </p>
          </div>
        </div>
        <Button
          className="shrink-0 px-3"
          onClick={onToggleAgent}
          type="button"
          variant={config?.enabled === false ? "success" : "neutral"}
        >
          {config?.enabled === false ? "Enable" : "Disable"}
        </Button>
      </div>

      <div className="mt-5 flex flex-wrap gap-2">
        <StatusChip
          status={
            run?.status ?? (config?.enabled === false ? "paused" : "waiting")
          }
        />
        <Pill>{MODE_OPTIONS.find((o) => o.value === config?.mode)?.label ?? config?.mode ?? "Hybrid"}</Pill>
        <Pill>{PROVIDER_OPTIONS.find((o) => o.value === config?.provider)?.label ?? config?.provider ?? "DeepSeek"}</Pill>
        <Pill>{config?.strictness_level ? humanize(config.strictness_level) : "Balanced"}</Pill>
      </div>

      {/* Inspector tabs — horizontal scroll without ugly scrollbar */}
      <div className="mt-5 -mx-1 overflow-x-auto px-1 pb-1 scrollbar-none" role="tablist" aria-label="Inspector tabs">
        <div className="flex gap-2 min-w-max">
          {tabs.map((tab) => (
            <button
              className={`shrink-0 rounded-full border px-3 py-2 text-xs font-semibold leading-none outline-none transition focus-visible:ring-2 focus-visible:ring-indigo-300 ${
                activeTab === tab
                  ? "border-indigo-300 bg-indigo-600 text-white shadow-lg shadow-indigo-950/20 dark:border-indigo-300 dark:bg-indigo-300 dark:text-indigo-950"
                  : "border-slate-200 bg-white text-slate-700 hover:border-indigo-200 dark:border-white/10 dark:bg-white/5 dark:text-slate-200"
              }`}
              key={tab}
              onClick={() => setActiveTab(tab)}
              role="tab"
              aria-selected={activeTab === tab}
              type="button"
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-5">
        {activeTab === "Overview" ? (
          <Overview
            agent={agent}
            config={config}
            run={run}
            recommendationCount={relatedRecommendations.length}
          />
        ) : null}
        {activeTab === "Configuration" ? (
          <Configuration config={config} isLoading={isLoading} onConfigChange={onConfigChange} />
        ) : null}
        {activeTab === "Prompt / Business Goal" ? (
          <PromptBusinessGoal
            config={config}
            onConfigChange={onConfigChange}
          />
        ) : null}
        {activeTab === "Input Data" ? (
          <JsonPanel
            icon={<FileInput size={16} />}
            label="Input Data"
            value={
              run?.input_json ?? {
                dependencies: agent.input_dependencies,
                data_access: agent.allowed_actions,
              }
            }
            advancedMode={advancedMode}
          />
        ) : null}
        {activeTab === "Output" ? (
          <JsonPanel
            icon={<TerminalSquare size={16} />}
            label="Recent Output"
            value={
              run?.output_json ?? { output_type: agent.output_type }
            }
            advancedMode={advancedMode}
          />
        ) : null}
        {activeTab === "Recommendations" ? (
          <RelatedRecommendations recommendations={relatedRecommendations} />
        ) : null}
        {activeTab === "Permissions" ? <Permissions /> : null}
        {activeTab === "Trace" ? (
          <TraceEvents
            events={events.filter(
              (event) =>
                event.agent_id === agent.agent_id ||
                event.agent_run_id === run?.id,
            )}
          />
        ) : null}
      </div>
    </aside>
  );
}

function Overview({
  agent,
  config,
  run,
  recommendationCount,
}: {
  agent: AgentDefinition;
  config?: AgentConfig;
  run?: AgentRun;
  recommendationCount: number;
}) {
  return (
    <div className="space-y-4">
      <InfoGrid
        items={[
          ["Role", agent.task_type],
          ["Goal", agent.output_type],
          ["Current status", run?.status ?? "idle"],
          ["Current task", currentTask(agent.agent_id)],
          [
            "Provider / Model",
            `${PROVIDER_OPTIONS.find((o) => o.value === (config?.provider ?? run?.provider))?.label ?? config?.provider ?? run?.provider ?? "DeepSeek"} / ${config?.model ?? run?.model ?? "default"}`,
          ],
          [
            "Last run",
            run?.created_at
              ? new Date(run.created_at).toLocaleString()
              : "Not yet",
          ],
          [
            "Recommendations",
            String(
              recommendationCount || run?.recommendation_ids?.length || 0,
            ),
          ],
          [
            "Latency",
            run?.latency_ms ? `${run.latency_ms} ms` : "Not reported",
          ],
        ]}
      />
    </div>
  );
}

function Configuration({
  config,
  isLoading,
  onConfigChange,
}: {
  config?: AgentConfig;
  isLoading?: boolean;
  onConfigChange: (patch: Partial<AgentConfig>) => void;
}) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (!config) {
    if (isLoading) {
      return (
        <div className="space-y-4">
          <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
            <div className="h-5 w-32 animate-pulse rounded-xl bg-slate-200 dark:bg-white/10" />
          </div>
          <LoadingSkeleton lines={6} />
        </div>
      );
    }
    return (
      <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-6 text-center dark:border-white/15 dark:bg-white/5">
        <p className="text-sm font-semibold text-slate-600 dark:text-slate-300">
          No configuration saved yet.
        </p>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          The agent works with default settings. Save any changes below to create a configuration record.
        </p>
      </div>
    );
  }

  const usesAi = config.mode === "ai" || config.mode === "hybrid";
  const modeBannerClass = config.mode === "ai"
    ? "border-indigo-200 bg-indigo-50 text-indigo-900 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100"
    : config.mode === "deterministic"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100"
      : "border-violet-200 bg-violet-50 text-violet-900 dark:border-violet-300/25 dark:bg-violet-300/10 dark:text-violet-100";
  const modeBannerText = config.mode === "ai"
    ? "AI Mode — Provider, Model, and AI confidence thresholds are required. Recommendations are generated by the LLM with deterministic fallback on AI failure."
    : config.mode === "deterministic"
      ? "Deterministic Mode — Rule-based only. No AI calls, no Provider/Model required. Faster, fully reproducible, and AI-free."
      : "Hybrid Mode — Rules run first; AI fills in edge cases only. Provider, Model, and AI thresholds still apply when AI is invoked.";

  return (
    <div className="space-y-6">
      {/* Enabled toggle */}
      <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
        <Switch
          label="Enabled"
          checked={config.enabled}
          onChange={(enabled) => onConfigChange({ enabled })}
          helperText={
            config.enabled
              ? "Agent is active and will process when triggered."
              : "Agent is paused. It will not consume resources or process data."
          }
        />
      </div>

      {/* Mode dropdown — primary control */}
      <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-950/40">
        <Select
          label="Mode"
          value={config.mode}
          options={MODE_OPTIONS}
          onChange={(mode) =>
            onConfigChange({ mode: mode as AgentConfig["mode"] })
          }
        />
        <div className={`mt-3 rounded-xl border px-3 py-2 text-xs font-semibold leading-relaxed ${modeBannerClass}`}>
          {modeBannerText}
        </div>
      </div>

      {/* AI-specific settings — visible only when mode uses AI */}
      {usesAi ? (
        <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
          <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            AI Provider Settings
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Select
              label="Provider"
              value={config.provider}
              options={PROVIDER_OPTIONS}
              onChange={(provider) =>
                onConfigChange({ provider: provider as AgentConfig["provider"] })
              }
              helperText="AI provider for reasoning calls."
            />
            <TextInput
              label="Model"
              value={config.model ?? ""}
              onChange={(model) => onConfigChange({ model: model || null })}
              placeholder="deepseek-chat"
            />
          </div>
        </div>
      ) : (
        <div className="rounded-2xl border border-dashed border-emerald-200 bg-emerald-50/40 p-4 text-xs text-emerald-900 dark:border-emerald-300/25 dark:bg-emerald-300/5 dark:text-emerald-100">
          Provider and Model are disabled in deterministic mode. Rules calculate every decision.
        </div>
      )}

      {/* Analysis depth — always shown */}
      <div className="grid gap-4 sm:grid-cols-2">
        <Select
          label="Analysis depth"
          value={config.analysis_depth}
          options={DEPTH_OPTIONS}
          onChange={(analysis_depth) =>
            onConfigChange({
              analysis_depth: analysis_depth as AgentConfig["analysis_depth"],
            })
          }
          helperText="How thoroughly the agent examines the data."
        />
      </div>

      {/* Advanced Settings Accordion */}
      <button
        type="button"
        onClick={() => setShowAdvanced(!showAdvanced)}
        className="flex w-full items-center justify-between rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 dark:border-white/10 dark:bg-white/5 dark:text-slate-200 dark:hover:border-white/20"
      >
        <span className="inline-flex items-center gap-2">
          <SlidersHorizontal size={14} />
          Advanced Settings
        </span>
        <ChevronDown
          size={16}
          className={`shrink-0 text-slate-400 transition-transform dark:text-slate-500 ${showAdvanced ? "rotate-180" : ""}`}
        />
      </button>

      {showAdvanced && (
        <div className="grid gap-4 sm:grid-cols-2">
          <Select
            label="Strictness"
            value={config.strictness_level}
            options={STRICTNESS_OPTIONS}
            onChange={(strictness_level) =>
              onConfigChange({
                strictness_level:
                  strictness_level as AgentConfig["strictness_level"],
              })
            }
            helperText="How conservative the agent should be when making decisions."
          />
          <Select
            label="Confidence threshold"
            value={config.confidence_threshold}
            options={CONFIDENCE_OPTIONS}
            onChange={(confidence_threshold) =>
              onConfigChange({
                confidence_threshold:
                  confidence_threshold as AgentConfig["confidence_threshold"],
              })
            }
            helperText="Minimum AI confidence needed to proceed with a recommendation."
          />
          <NumberInput
            label="Max recommendations"
            value={config.max_recommendations}
            onChange={(max_recommendations) =>
              onConfigChange({ max_recommendations })
            }
          />
          <NumberInput
            label="Max rows per AI call"
            value={config.max_rows_per_ai_call}
            onChange={(max_rows_per_ai_call) =>
              onConfigChange({ max_rows_per_ai_call })
            }
          />
          <NumberInput
            label="Max products per run"
            value={config.max_products_per_run}
            onChange={(max_products_per_run) =>
              onConfigChange({ max_products_per_run })
            }
          />
        </div>
      )}

      <Fieldset title="Data Scope">
        <ToggleGrid
          config={config}
          onConfigChange={onConfigChange}
          fields={[
            "include_account_level_analysis",
            "include_product_level_analysis",
            "include_campaign_level_analysis",
            "include_keyword_level_analysis",
            "include_search_term_level_analysis",
          ]}
        />
      </Fieldset>
      <Fieldset title="Recommendation Toggles">
        <ToggleGrid
          config={config}
          onConfigChange={onConfigChange}
          fields={[
            "allow_keep_running",
            "allow_increase_bid",
            "allow_decrease_bid",
            "allow_pause_review",
            "allow_negative_exact",
            "allow_negative_phrase",
            "allow_move_to_exact",
            "allow_budget_review",
            "allow_data_quality_review",
          ]}
        />
      </Fieldset>
      <Fieldset title="Risk Controls">
        <div className="grid gap-4 sm:grid-cols-2">
          <TextInput
            label="Max bid increase multiplier"
            value={String(config.max_bid_increase_multiplier ?? "")}
            onChange={(value) =>
              onConfigChange({
                max_bid_increase_multiplier: value,
              } as Partial<AgentConfig>)
            }
          />
          <TextInput
            label="Max bid decrease multiplier"
            value={String(config.max_bid_decrease_multiplier ?? "")}
            onChange={(value) =>
              onConfigChange({
                max_bid_decrease_multiplier: value,
              } as Partial<AgentConfig>)
            }
          />
          <NumberInput
            label="Min clicks before action"
            value={config.require_min_clicks_before_action}
            onChange={(require_min_clicks_before_action) =>
              onConfigChange({ require_min_clicks_before_action })
            }
          />
          <TextInput
            label="Min spend before action"
            value={String(config.require_min_spend_before_action ?? "")}
            onChange={(value) =>
              onConfigChange({
                require_min_spend_before_action: value,
              } as Partial<AgentConfig>)
            }
          />
          <TextInput
            label="Target ACOS override"
            value={String(config.target_acos_override ?? "")}
            onChange={(value) =>
              onConfigChange({
                target_acos_override: value || null,
              } as Partial<AgentConfig>)
            }
          />
          <NumberInput
            label="Min orders for scaling"
            value={config.min_orders_for_scaling}
            onChange={(min_orders_for_scaling) =>
              onConfigChange({ min_orders_for_scaling })
            }
          />
          <TextInput
            label="Min ROAS for scaling"
            value={String(config.min_roas_for_scaling ?? "")}
            onChange={(value) =>
              onConfigChange({
                min_roas_for_scaling: value,
              } as Partial<AgentConfig>)
            }
          />
          <Switch
            label="Require high confidence for pause"
            checked={config.require_high_confidence_for_pause}
            onChange={(require_high_confidence_for_pause) =>
              onConfigChange({ require_high_confidence_for_pause })
            }
          />
          <Switch
            label="Require high confidence for negative keywords"
            checked={config.require_high_confidence_for_negative_keywords}
            onChange={(require_high_confidence_for_negative_keywords) =>
              onConfigChange({
                require_high_confidence_for_negative_keywords,
              })
            }
          />
        </div>
      </Fieldset>
    </div>
  );
}

function PromptBusinessGoal({
  config,
  onConfigChange,
}: {
  config?: AgentConfig;
  onConfigChange: (patch: Partial<AgentConfig>) => void;
}) {
  if (!config) return null;
  const OPTIMIZATION_OPTIONS = [
    { value: "reduce_wasted_spend", label: "Reduce Wasted Spend" },
    { value: "increase_sales", label: "Increase Sales" },
    { value: "improve_roas", label: "Improve ROAS" },
    { value: "launch_new_products", label: "Launch New Products" },
    { value: "scale_winners", label: "Scale Winners" },
    { value: "conservative_profitability", label: "Conservative Profitability" },
  ];
  const EXPLANATION_OPTIONS = [
    { value: "simple", label: "Simple" },
    { value: "normal", label: "Normal" },
    { value: "expert", label: "Expert" },
  ];
  return (
    <div className="space-y-4">
      <TextArea
        label="Custom business goal"
        value={String(config.custom_business_goal ?? "")}
        onChange={(custom_business_goal) =>
          onConfigChange({
            custom_business_goal,
          } as Partial<AgentConfig>)
        }
      />
      <Select
        label="Optimization goal"
        value={config.optimization_goal}
        options={OPTIMIZATION_OPTIONS}
        onChange={(optimization_goal) =>
          onConfigChange({
            optimization_goal,
          } as Partial<AgentConfig>)
        }
      />
      <TextArea
        label="Brand safety notes"
        value={String(config.brand_safety_notes ?? "")}
        onChange={(brand_safety_notes) =>
          onConfigChange({
            brand_safety_notes,
          } as Partial<AgentConfig>)
        }
      />
      <TextArea
        label="Competitor notes"
        value={String(config.competitor_notes ?? "")}
        onChange={(competitor_notes) =>
          onConfigChange({ competitor_notes } as Partial<AgentConfig>)
        }
      />
      <TextArea
        label="Product margin notes"
        value={String(config.product_margin_notes ?? "")}
        onChange={(product_margin_notes) =>
          onConfigChange({
            product_margin_notes,
          } as Partial<AgentConfig>)
        }
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Select
          label="Explanation detail"
          value={config.explanation_detail}
          options={EXPLANATION_OPTIONS}
          onChange={(explanation_detail) =>
            onConfigChange({
              explanation_detail:
                explanation_detail as AgentConfig["explanation_detail"],
            })
          }
        />
        <TextInput
          label="Recommendation language"
          value={String(config.recommendation_language ?? "en")}
          onChange={(recommendation_language) =>
            onConfigChange({
              recommendation_language,
            } as Partial<AgentConfig>)
          }
        />
      </div>
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100">
        API keys and provider secrets are not accepted in this form.
      </div>
    </div>
  );
}

function RelatedRecommendations({
  recommendations,
}: {
  recommendations: Recommendation[];
}) {
  return (
    <div className="space-y-3">
      {recommendations.length ? (
        recommendations.slice(0, 6).map((item) => (
          <article
            className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/5"
            key={item.id}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Pill>{humanize(item.recommendation_type)}</Pill>
              <Pill>{item.priority}</Pill>
              <Pill>{item.confidence}</Pill>
            </div>
            <p className="mt-3 text-sm font-semibold text-slate-950 dark:text-white">
              {item.campaign_name || "Account recommendation"}
            </p>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
              {item.explanation_json?.summary ?? "Recommendation needs review."}
            </p>
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-semibold text-indigo-700 dark:text-indigo-200">
                Why this recommendation?
              </summary>
              <pre className="mt-2 max-h-44 overflow-auto whitespace-pre-wrap rounded-2xl bg-slate-50 p-3 text-xs dark:bg-slate-950/70">
                {JSON.stringify(
                  item.current_metric_snapshot_json ||
                    item.input_metrics_json,
                  null,
                  2,
                )}
              </pre>
            </details>
          </article>
        ))
      ) : (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          No related recommendations yet.
        </p>
      )}
    </div>
  );
}

function Permissions() {
  const allowed = [
    "Can read uploaded reports",
    "Can analyze metrics",
    "Can create recommendation records",
  ];
  const blocked = [
    "Cannot approve recommendations",
    "Cannot reject recommendations",
    "Cannot execute Amazon Ads API changes",
    "Cannot mutate live campaigns",
    "Cannot hide evidence",
  ];
  return (
    <div className="space-y-4">
      <PermissionList title="Allowed" items={allowed} positive />
      <PermissionList title="Blocked" items={blocked} />
    </div>
  );
}

function PermissionList({
  title,
  items,
  positive = false,
}: {
  title: string;
  items: string[];
  positive?: boolean;
}) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/5">
      <p className="font-semibold text-slate-950 dark:text-white">{title}</p>
      <ul className="mt-3 space-y-2">
        {items.map((item) => (
          <li
            className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200"
            key={item}
          >
            {positive ? (
              <CheckCircle2 className="text-emerald-500" size={16} />
            ) : (
              <LockKeyhole className="text-amber-500" size={16} />
            )}
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function TraceEvents({ events }: { events: AgentEvent[] }) {
  return events.length ? (
    <div className="space-y-2">
      {events.map((event) => (
        <div
          className="rounded-2xl border border-slate-200 bg-white p-3 text-sm dark:border-white/10 dark:bg-white/5"
          key={event.id}
        >
          <p className="font-semibold text-slate-950 dark:text-white">
            {humanize(event.event_type)}
          </p>
          <p className="mt-1 text-slate-600 dark:text-slate-300">
            {event.message}
          </p>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {new Date(event.created_at).toLocaleString()}
          </p>
        </div>
      ))}
    </div>
  ) : (
    <p className="text-sm text-slate-600 dark:text-slate-300">
      No trace events for this agent yet.
    </p>
  );
}

function JsonPanel({
  icon,
  label,
  value,
  advancedMode,
}: {
  icon: React.ReactNode;
  label: string;
  value: unknown;
  advancedMode: boolean;
}) {
  return (
    <div className="min-w-0 rounded-2xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-white/5">
      <p className="flex items-center gap-2 font-semibold text-slate-950 dark:text-white">
        {icon}
        {label}
      </p>
      {advancedMode ? (
        <pre className="mt-3 max-h-80 overflow-auto whitespace-pre-wrap break-words rounded-2xl bg-slate-50 p-3 text-xs text-slate-700 dark:bg-slate-950/70 dark:text-slate-200">
          {JSON.stringify(value, null, 2)}
        </pre>
      ) : (
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">
          Switch to Advanced Mode to inspect raw JSON input and output.
        </p>
      )}
    </div>
  );
}

function ToggleGrid({
  config,
  fields,
  onConfigChange,
}: {
  config: AgentConfig;
  fields: string[];
  onConfigChange: (patch: Partial<AgentConfig>) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {fields.map((field) => (
        <Switch
          key={field}
          label={humanize(field)}
          checked={Boolean(config[field as keyof AgentConfig])}
          onChange={(value) =>
            onConfigChange({ [field]: value } as Partial<AgentConfig>)
          }
        />
      ))}
    </div>
  );
}

function Fieldset({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <fieldset className="rounded-2xl border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
      <legend className="px-2 text-sm font-semibold text-slate-950 dark:text-white">
        {title}
      </legend>
      {children}
    </fieldset>
  );
}

function InfoGrid({ items }: { items: Array<[string, string]> }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {items.map(([label, value]) => (
        <div
          className="min-w-0 rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-white/5"
          key={label}
        >
          <p className="text-xs font-semibold uppercase text-slate-500 dark:text-slate-400">
            {label}
          </p>
          <p className="mt-1 break-words text-sm font-semibold text-slate-900 dark:text-white">
            {value}
          </p>
        </div>
      ))}
    </div>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
  helperText,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  helperText?: string;
}) {
  return (
    <SelectMenu
      label={label}
      value={value}
      options={options}
      onChange={onChange}
      helperText={helperText}
    />
  );
}

function TextInput({
  label,
  value,
  placeholder,
  onChange,
}: {
  label: string;
  value: string;
  placeholder?: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1.5">
      <span className="block text-xs font-semibold text-slate-600 dark:text-slate-300">
        {label}
      </span>
      <input
        className="min-h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-slate-950/40 dark:text-white dark:placeholder:text-slate-500 dark:hover:border-white/20 dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20"
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        value={value}
      />
    </label>
  );
}

function NumberInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
}) {
  return (
    <label className="space-y-1.5">
      <span className="block text-xs font-semibold text-slate-600 dark:text-slate-300">
        {label}
      </span>
      <input
        className="min-h-11 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-slate-950/40 dark:text-white dark:placeholder:text-slate-500 dark:hover:border-white/20 dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20"
        min={0}
        onChange={(event) => onChange(Number(event.target.value))}
        type="number"
        value={value ?? 0}
      />
    </label>
  );
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="space-y-1.5">
      <span className="block text-xs font-semibold text-slate-600 dark:text-slate-300">
        {label}
      </span>
      <textarea
        className="min-h-24 w-full rounded-2xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 shadow-sm outline-none transition placeholder:text-slate-400 hover:border-slate-300 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-slate-950/40 dark:text-white dark:placeholder:text-slate-500 dark:hover:border-white/20 dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20"
        onChange={(event) => onChange(event.target.value)}
        value={value}
      />
    </label>
  );
}

function StatusChip({ status }: { status: string }) {
  const tone =
    status === "failed"
      ? "border-red-300 bg-red-50 text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100"
      : status === "running" || status === "queued"
        ? "border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100"
        : status === "paused"
          ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100"
          : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100";
  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-xs font-semibold ${tone}`}
    >
      {humanize(status)}
    </span>
  );
}

function Pill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-slate-200 bg-slate-100 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:border-white/10 dark:bg-white/10 dark:text-slate-200">
      {children}
    </span>
  );
}

function currentTask(agentId: string) {
  const tasks: Record<string, string> = {
    report_upload_node: "Waiting for report upload",
    import_data_quality_agent: "Validate report rows, columns, and data quality",
    entity_resolution_agent: "Map campaigns, ad groups, ASINs, SKUs, and search terms",
    metrics_normalization_agent: "Calculate CPC, CTR, CVR, ACOS, ROAS deterministically",
    account_strategy_agent: "Determine optimization goal and risk policy",
    search_term_mining_agent: "Classify search terms: harvest, negative, watch, ignore",
    bid_optimization_agent: "Recommend bid changes with evidence",
    negative_keyword_agent: "Recommend negative exact/phrase candidates",
    budget_reallocation_agent: "Recommend budget shifts across campaigns",
    campaign_structure_agent: "Recommend structural campaign changes",
    risk_policy_validator_agent: "Validate every recommendation against safety rules",
    human_approval_agent: "Route recommendations to humans",
    bulk_change_compiler_agent: "Compile approved changes into Amazon bulk export",
    learning_feedback_agent: "Compare prior recommendations with new metrics",
    stakeholder_reporting_agent: "Prepare executive and approver summary",
    // Legacy
    ai_recommendation_brain_agent: "Create approval-gated recommendation JSON (legacy)",
  };
  return tasks[agentId] ?? "Inspect evidence and workflow status";
}

function relatedForAgent(
  recommendations: Recommendation[],
  run?: AgentRun,
  agentId?: string,
) {
  const runIds = new Set(run?.recommendation_ids ?? []);
  if (runIds.size)
    return recommendations.filter((item) => runIds.has(item.id));
  if (!agentId) return recommendations.slice(0, 3);
  if (agentId.includes("negative"))
    return recommendations.filter((item) =>
      item.recommendation_type.includes("negative"),
    );
  if (agentId.includes("bid"))
    return recommendations.filter((item) =>
      item.recommendation_type.includes("bid"),
    );
  if (agentId.includes("budget"))
    return recommendations.filter((item) =>
      item.recommendation_type.includes("budget"),
    );
  if (agentId.includes("pause"))
    return recommendations.filter((item) =>
      item.recommendation_type.includes("pause"),
    );
  return recommendations.slice(0, 3);
}