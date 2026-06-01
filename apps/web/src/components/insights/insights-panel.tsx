"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  Calculator,
  GitBranch,
  Lightbulb,
  Loader2,
  TrendingDown,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  ShieldCheck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { defaultWorkspaceId } from "@/lib/api/client";

type BacktestResult = {
  workspace_id?: string;
  recommendation_id: string;
  recommendation_type: string;
  campaign_name: string;
  window_days: number;
  pre: { spend: number; sales: number; acos: number | null; orders: number; clicks: number };
  projected: { spend: number; sales: number; acos: number | null; orders: number; clicks: number };
  deltas: { spend_pct: number; sales_pct: number; acos_pct: number };
  confidence: { cvr_interval_low: number | null; cvr_interval_high: number | null; level: number };
  data_quality: string;
  days_with_data: number;
  warnings: string[];
  summary: string;
};

type PlannerResult = {
  strategy_mode: string;
  data_quality_score: number;
  bid_optimization: string;
  negative_keyword: string;
  budget_reallocation: string;
  campaign_structure: string;
  skip_reasons: Record<string, string>;
  reasoning: string;
  warnings: string[];
};

type SignificanceResult = {
  recommendation_id: string;
  recommendation_type: string;
  overall_passed: boolean;
  requires_more_data: boolean;
  wilson_cvr_lower: number;
  wilson_cvr_upper: number;
  minimum_clicks_met: boolean;
  minimum_spend_met: boolean;
  minimum_orders_met: boolean;
  errors: string[];
  warnings: string[];
  checks: Array<{ name: string; passed: boolean; value: number; threshold: number; detail: string; is_warning: boolean }>;
};

type CalibrationParam = {
  rule_name: string;
  parameter: string;
  original_value: number;
  bounded_min: number;
  bounded_max: number;
  description: string;
};

type CalibrationStatus = {
  workspace_id: string;
  total_parameters: number;
  parameters: CalibrationParam[];
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function localAuthHeaders(workspaceId: string): Record<string, string> {
  return {
    "x-test-workspaces": workspaceId,
    "x-user-id": "dev-user",
  };
}

export function InsightsPanel({ workspaceId = defaultWorkspaceId, recommendationId }: { workspaceId?: string; recommendationId?: string }) {
  const [planner, setPlanner] = useState<PlannerResult | null>(null);
  const [significance, setSignificance] = useState<SignificanceResult | null>(null);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [calibration, setCalibration] = useState<CalibrationStatus | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"planner" | "significance" | "backtest" | "calibration">("planner");

  // Planner params
  const [dqScore, setDqScore] = useState(0.85);
  const [strategyMode, setStrategyMode] = useState("profit");
  const [searchTerms, setSearchTerms] = useState(50);
  const [campaigns, setCampaigns] = useState(8);
  const [wastefulTerms, setWastefulTerms] = useState(12);

  // Backtest window
  const [backtestDays, setBacktestDays] = useState(14);

  async function loadInsight(endpoint: string, key: string) {
    setMessage(null);
    setIsLoading(true);
    try {
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}${endpoint}`, {
        headers: { ...localAuthHeaders(workspaceId), "Content-Type": "application/json" },
      });
      if (!response.ok) throw new Error(`Failed to load ${key}`);
      const json = await response.json();
      const data = json.data ?? json;
      if (key === "planner") setPlanner(data);
      if (key === "significance") setSignificance(data);
      if (key === "backtest") setBacktest(data);
      if (key === "calibration") setCalibration(data);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : `${key} could not be loaded.`);
    } finally {
      setIsLoading(false);
    }
  }

  async function runPlanner() {
    setMessage(null);
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        data_quality_score: String(dqScore),
        strategy_mode: strategyMode,
        search_term_count: String(searchTerms),
        campaign_count: String(campaigns),
        wasteful_term_count: String(wastefulTerms),
      });
      const response = await fetch(`${apiBaseUrl}/v1/workspaces/${workspaceId}/planner/evaluate?${params}`, {
        method: "POST",
        headers: localAuthHeaders(workspaceId),
      });
      if (!response.ok) throw new Error("Planner could not be evaluated.");
      const json = await response.json();
      setPlanner(json.data);
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Planner evaluation failed.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Tab bar */}
      <div className="flex flex-wrap gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-1.5 dark:border-white/10 dark:bg-white/5">
        {([
          { key: "planner", label: "Planner", icon: <GitBranch size={15} /> },
          { key: "significance", label: "Significance", icon: <Calculator size={15} /> },
          { key: "backtest", label: "Backtest", icon: <BarChart3 size={15} /> },
          { key: "calibration", label: "Calibration", icon: <Lightbulb size={15} /> },
        ] as const).map(({ key, label, icon }) => (
          <button
            key={key}
            className={`flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm font-semibold transition ${activeTab === key ? "bg-white text-slate-950 shadow-sm dark:bg-white/90 dark:text-slate-950" : "text-slate-600 hover:text-slate-950 dark:text-slate-300 dark:hover:text-white"}`}
            onClick={() => setActiveTab(key)}
            type="button"
          >
            {icon} {label}
          </button>
        ))}
      </div>

      {/* Planner Tab */}
      {activeTab === "planner" && (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
          <div className="flex items-center gap-3 mb-4">
            <GitBranch size={20} className="text-indigo-600 dark:text-indigo-300" />
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Agent Planner</h2>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-5">
            The planner decides which optimization agents (bid, negatives, budget, structure) should run based on data quality and strategy.
          </p>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-5">
            <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Data Quality Score
              <input className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" type="number" min={0} max={1} step={0.05} value={dqScore} onChange={(e) => setDqScore(Number(e.target.value))} />
            </label>
            <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Strategy
              <select className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" value={strategyMode} onChange={(e) => setStrategyMode(e.target.value)}>
                {["profit", "growth", "launch", "brand_defense", "cleanup"].map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Search Terms
              <input className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" type="number" min={0} value={searchTerms} onChange={(e) => setSearchTerms(Number(e.target.value))} />
            </label>
            <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Campaigns
              <input className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" type="number" min={0} value={campaigns} onChange={(e) => setCampaigns(Number(e.target.value))} />
            </label>
            <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
              Wasteful Terms
              <input className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" type="number" min={0} value={wastefulTerms} onChange={(e) => setWastefulTerms(Number(e.target.value))} />
            </label>
          </div>

          <Button onClick={runPlanner} disabled={isLoading} type="button" variant="primary">
            {isLoading ? <Loader2 className="animate-spin" size={16} /> : <GitBranch size={16} />}
            {isLoading ? "Evaluating..." : "Run Planner"}
          </Button>

          {planner && (
            <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { agent: "Bid Optimization", decision: planner.bid_optimization },
                { agent: "Negative Keywords", decision: planner.negative_keyword },
                { agent: "Budget Reallocation", decision: planner.budget_reallocation },
                { agent: "Campaign Structure", decision: planner.campaign_structure },
              ].map(({ agent, decision }) => (
                <div key={agent} className={`rounded-2xl border p-4 ${decision === "run" ? "border-emerald-200 bg-emerald-50 dark:border-emerald-300/25 dark:bg-emerald-300/10" : decision === "skip" ? "border-red-200 bg-red-50 dark:border-red-300/25 dark:bg-red-300/10" : "border-amber-200 bg-amber-50 dark:border-amber-300/25 dark:bg-amber-300/10"}`}>
                  <div className="flex items-center gap-2 text-xs font-semibold">
                    {decision === "run" ? <CheckCircle2 size={14} className="text-emerald-600" /> : decision === "skip" ? <XCircle size={14} className="text-red-600" /> : <AlertTriangle size={14} className="text-amber-600" />}
                    {agent}
                  </div>
                  <span className="mt-1 block text-lg font-bold uppercase text-slate-900 dark:text-white">{decision}</span>
                </div>
              ))}
              {planner.reasoning && (
                <div className="col-span-full mt-2 rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                  <strong>Reasoning:</strong> {planner.reasoning}
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Significance Tab */}
      {activeTab === "significance" && (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
          <div className="flex items-center gap-3 mb-4">
            <Calculator size={20} className="text-violet-600 dark:text-violet-300" />
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Statistical Significance Gate</h2>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-5">
            Wilson lower-bound CVR, minimum click/spend gates, and evidence quality checks. Recommendations that fail these checks require more data before action.
          </p>

          {recommendationId ? (
            <Button onClick={() => loadInsight(`/recommendations/${recommendationId}/significance`, "significance")} disabled={isLoading} type="button" variant="primary">
              {isLoading ? <Loader2 className="animate-spin" size={16} /> : <ShieldCheck size={16} />}
              {isLoading ? "Checking..." : "Run Significance Check"}
            </Button>
          ) : (
            <p className="text-xs text-slate-500 dark:text-slate-400">Select a recommendation first to run significance checks.</p>
          )}

          {significance && (
            <div className="mt-5 space-y-3">
              <div className={`rounded-2xl border p-4 ${significance.overall_passed ? "border-emerald-200 bg-emerald-50 dark:border-emerald-300/25 dark:bg-emerald-300/10" : "border-red-200 bg-red-50 dark:border-red-300/25 dark:bg-red-300/10"}`}>
                <span className="text-lg font-bold">{significance.overall_passed ? "✓ Passed" : "✗ Failed"}</span>
                <div className="mt-2 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-semibold">
                  <span>Wilson CVR: {significance.wilson_cvr_lower.toFixed(4)} – {significance.wilson_cvr_upper.toFixed(4)}</span>
                  <span className={significance.minimum_clicks_met ? "text-emerald-700" : "text-red-700"}>Min clicks: {significance.minimum_clicks_met ? "✓" : "✗"}</span>
                  <span className={significance.minimum_spend_met ? "text-emerald-700" : "text-red-700"}>Min spend: {significance.minimum_spend_met ? "✓" : "✗"}</span>
                  <span className={significance.minimum_orders_met ? "text-emerald-700" : "text-red-700"}>Min orders: {significance.minimum_orders_met ? "✓" : "✗"}</span>
                </div>
              </div>
              {significance.checks.map((c, i) => (
                <div key={i} className={`rounded-xl border px-4 py-2 text-xs ${c.passed ? "border-slate-200 bg-white dark:border-white/10 dark:bg-white/5" : c.is_warning ? "border-amber-200 bg-amber-50 dark:border-amber-300/25 dark:bg-amber-300/10" : "border-red-200 bg-red-50 dark:border-red-300/25 dark:bg-red-300/10"}`}>
                  <span className="font-semibold">{c.name}</span>: {c.detail || `value=${c.value}, threshold=${c.threshold}`}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Backtest Tab */}
      {activeTab === "backtest" && (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
          <div className="flex items-center gap-3 mb-4">
            <BarChart3 size={20} className="text-blue-600 dark:text-blue-300" />
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Backtest Simulation</h2>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-5">
            Projects what would have happened if this recommendation were applied N days ago, using historical daily snapshots.
          </p>

          {recommendationId ? (
            <div className="flex items-end gap-3 mb-5">
              <label className="flex flex-col gap-1 text-xs font-semibold text-slate-600 dark:text-slate-300">
                Window Days
                <select className="rounded-xl border border-slate-200 bg-white px-3 py-2 text-sm text-slate-950 dark:border-white/10 dark:bg-white/5 dark:text-white" value={backtestDays} onChange={(e) => setBacktestDays(Number(e.target.value))}>
                  {[7, 14, 30, 60].map((d) => (
                    <option key={d} value={d}>{d} days</option>
                  ))}
                </select>
              </label>
              <Button onClick={() => loadInsight(`/recommendations/${recommendationId}/backtest?window_days=${backtestDays}`, "backtest")} disabled={isLoading} type="button" variant="primary">
                {isLoading ? <Loader2 className="animate-spin" size={16} /> : <TrendingUp size={16} />}
                {isLoading ? "Simulating..." : "Run Backtest"}
              </Button>
            </div>
          ) : (
            <p className="text-xs text-slate-500 dark:text-slate-400">Select a recommendation first to run backtest simulation.</p>
          )}

          {backtest && (
            <div className="mt-5 space-y-4">
              <div className="rounded-2xl border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900 dark:border-blue-300/25 dark:bg-blue-300/10 dark:text-blue-100">
                {backtest.summary}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: "Pre ACOS", value: backtest.pre.acos != null ? `${backtest.pre.acos.toFixed(1)}%` : "n/a", icon: <TrendingDown size={14} /> },
                  { label: "Projected ACOS", value: backtest.projected.acos != null ? `${backtest.projected.acos.toFixed(1)}%` : "n/a", icon: <TrendingUp size={14} /> },
                  { label: "ACOS Delta", value: `${backtest.deltas.acos_pct.toFixed(1)}%`, icon: backtest.deltas.acos_pct < 0 ? <TrendingDown size={14} className="text-emerald-500" /> : <TrendingUp size={14} className="text-red-500" /> },
                  { label: "Sales Delta", value: `${backtest.deltas.sales_pct.toFixed(1)}%`, icon: backtest.deltas.sales_pct > 0 ? <TrendingUp size={14} className="text-emerald-500" /> : <TrendingDown size={14} className="text-red-500" /> },
                ].map(({ label, value, icon }) => (
                  <div key={label} className="rounded-2xl border border-slate-200 bg-white p-3 dark:border-white/10 dark:bg-white/5">
                    <div className="flex items-center gap-1.5 text-xs text-slate-500 dark:text-slate-400">
                      {icon} {label}
                    </div>
                    <div className="mt-1 text-xl font-bold text-slate-950 dark:text-white">{value}</div>
                  </div>
                ))}
              </div>
              {backtest.confidence.cvr_interval_low != null && (
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
                  95% CI: CVR {backtest.confidence.cvr_interval_low?.toFixed(2)} – {backtest.confidence.cvr_interval_high?.toFixed(2)}
                  {' · '}Data quality: {backtest.data_quality}
                  {' · '}{backtest.days_with_data} days of data
                </div>
              )}
            </div>
          )}
        </section>
      )}

      {/* Calibration Tab */}
      {activeTab === "calibration" && (
        <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
          <div className="flex items-center gap-3 mb-4">
            <Lightbulb size={20} className="text-amber-600 dark:text-amber-300" />
            <h2 className="text-lg font-semibold text-slate-950 dark:text-white">Rule Calibration</h2>
          </div>
          <p className="text-sm text-slate-600 dark:text-slate-300 mb-5">
            Deterministic rule thresholds that can be adjusted ±20% based on learning feedback outcomes. All adjustments are bounded and require ≥5 observations.
          </p>

          <Button onClick={() => loadInsight("/calibration/status", "calibration")} disabled={isLoading} type="button" variant="primary">
            {isLoading ? <Loader2 className="animate-spin" size={16} /> : <Lightbulb size={16} />}
            {isLoading ? "Loading..." : "View Calibration"}
          </Button>

          {calibration && (
            <div className="mt-5 space-y-2">
              <p className="text-sm text-slate-600 dark:text-slate-300">{calibration.total_parameters} calibratable parameters</p>
              <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-white/10">
                <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-white/10">
                  <thead className="bg-slate-50 text-left font-semibold text-slate-500 dark:bg-white/5 dark:text-slate-400">
                    <tr>
                      <th className="px-3 py-2">Rule</th>
                      <th className="px-3 py-2">Parameter</th>
                      <th className="px-3 py-2">Original</th>
                      <th className="px-3 py-2">Min</th>
                      <th className="px-3 py-2">Max</th>
                      <th className="px-3 py-2">Description</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-white/5">
                    {calibration.parameters.map((p, i) => (
                      <tr key={i} className="text-slate-700 dark:text-slate-300">
                        <td className="px-3 py-2 font-semibold">{p.rule_name}</td>
                        <td className="px-3 py-2">{p.parameter}</td>
                        <td className="px-3 py-2">{p.original_value}</td>
                        <td className="px-3 py-2">{p.bounded_min}</td>
                        <td className="px-3 py-2">{p.bounded_max}</td>
                        <td className="px-3 py-2 max-w-[200px] truncate">{p.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {message && (
        <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100">
          {message}
        </div>
      )}
    </div>
  );
}

export function InsightsPanelCard({ title, workspaceId, recommendationId }: { title: string; workspaceId?: string; recommendationId?: string }) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
      <div className="flex items-center gap-3 mb-4">
        <BarChart3 size={20} className="text-indigo-600 dark:text-indigo-300" />
        <h2 className="text-lg font-semibold text-slate-950 dark:text-white">{title}</h2>
      </div>
      <InsightsPanel workspaceId={workspaceId} recommendationId={recommendationId} />
    </section>
  );
}