"use client";

type AgentRunDecision = "run" | "skip" | "light";

type PlannerInfo = {
  strategyMode: string;
  dataQualityScore: number;
  totalRows: number;
  warnings: string[];
  bidOptimization: AgentRunDecision;
  negativeKeyword: AgentRunDecision;
  budgetReallocation: AgentRunDecision;
  campaignStructure: AgentRunDecision;
  reasoning: string;
  skipReasons: Record<string, string>;
};

function decisionBadge(decision: AgentRunDecision) {
  const styles: Record<AgentRunDecision, string> = {
    run: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:border-emerald-400/30",
    skip: "bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
    light: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:border-amber-400/30",
  };
  return `inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${styles[decision]}`;
}

function scoreColor(score: number) {
  if (score >= 0.7) return "text-emerald-600 dark:text-emerald-400";
  if (score >= 0.4) return "text-amber-600 dark:text-amber-400";
  return "text-red-600 dark:text-red-400";
}

const agentLabels: Record<string, string> = {
  bidOptimization: "Bid Optimization",
  negativeKeyword: "Negative Keywords",
  budgetReallocation: "Budget Reallocation",
  campaignStructure: "Campaign Structure",
};

export function PlannerSummary({ planner }: { planner?: PlannerInfo | null }) {
  if (!planner) return null;

  return (
    <div className="rounded-xl border border-indigo-200 bg-gradient-to-br from-indigo-50/50 to-white p-5 dark:border-indigo-400/20 dark:from-indigo-400/5 dark:to-slate-950/70">
      <div className="flex items-center gap-3 mb-4">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">Execution Planner</h3>
        <span className="rounded-full bg-indigo-100 px-2 py-0.5 text-[10px] font-medium text-indigo-700 dark:bg-indigo-400/10 dark:text-indigo-300">
          {planner.strategyMode}
        </span>
      </div>

      {/* Data quality + row count */}
      <div className="mb-4 flex gap-4">
        <div>
          <p className="text-[10px] uppercase text-slate-500 dark:text-slate-400">Data Quality</p>
          <p className={`text-lg font-bold ${scoreColor(planner.dataQualityScore)}`}>
            {(planner.dataQualityScore * 100).toFixed(0)}%
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase text-slate-500 dark:text-slate-400">Total Rows</p>
          <p className="text-lg font-bold text-slate-900 dark:text-white">{planner.totalRows}</p>
        </div>
      </div>

      {/* Agent decisions */}
      <div className="grid grid-cols-2 gap-2">
        {Object.entries(agentLabels).map(([key, label]) => {
          const decision = (planner as Record<string, unknown>)[key] as AgentRunDecision;
          const reason = planner.skipReasons[key] || planner.skipReasons[label.toLowerCase().replace(/ /g, "_")];
          return (
            <div key={key} className="flex items-center justify-between rounded-lg border border-slate-100 bg-white p-2 dark:border-white/5 dark:bg-slate-800/30">
              <span className="text-xs text-slate-700 dark:text-slate-300">{label}</span>
              <span className="flex items-center gap-1">
                {decisionBadge(decision || "run")}
                {reason && <span className="text-[9px] text-slate-400 dark:text-slate-500 truncate max-w-[80px]" title={reason}>{reason}</span>}
              </span>
            </div>
          );
        })}
      </div>

      {/* Reasoning */}
      {planner.reasoning && (
        <p className="mt-3 text-[10px] leading-relaxed text-slate-500 dark:text-slate-400">{planner.reasoning}</p>
      )}

      {/* Warnings */}
      {planner.warnings.length > 0 && (
        <div className="mt-2 space-y-1">
          {planner.warnings.map((w, i) => (
            <p key={i} className="text-[10px] text-amber-600 dark:text-amber-400">{w}</p>
          ))}
        </div>
      )}
    </div>
  );
}