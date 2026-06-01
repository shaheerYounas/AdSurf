"use client";

import { useMemo } from "react";

/** A single checkpoint on the 14-day observation timeline. */
type TimelineCheckpoint = {
  label: string;
  day: number;
  status: "pending" | "active" | "completed" | "warning" | "error";
  detail?: string;
  acosDelta?: number;
  salesDelta?: number;
};

/** Campaign lock state from the backend. */
type CampaignLockInfo = {
  campaignName: string;
  lockState: "unlocked" | "locked_pending" | "locked_active" | "locked_cooldown" | "expired";
  recommendationType: string;
  appliedChange: string;
  appliedAt: string | null;
  lockUntil: string | null;
  day7Checkpoint: string | null;
  day14Checkpoint: string | null;
  createdAt: string;
};

function statusBadge(status: TimelineCheckpoint["status"]) {
  const styles: Record<TimelineCheckpoint["status"], string> = {
    pending: "bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
    active: "bg-indigo-50 text-indigo-700 border-indigo-200 dark:bg-indigo-400/10 dark:text-indigo-300 dark:border-indigo-400/30",
    completed: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-400/10 dark:text-emerald-300 dark:border-emerald-400/30",
    warning: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-400/10 dark:text-amber-300 dark:border-amber-400/30",
    error: "bg-red-50 text-red-700 border-red-200 dark:bg-red-400/10 dark:text-red-300 dark:border-red-400/30",
  };
  return `inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${styles[status]}`;
}

function deltaLabel(value: number | undefined, suffix = "%") {
  if (value === undefined || value === null) return null;
  const sign = value > 0 ? "+" : "";
  const color = value > 0 ? "text-red-600 dark:text-red-400" : value < 0 ? "text-emerald-600 dark:text-emerald-400" : "text-slate-500";
  return <span className={`ml-1 text-xs font-semibold ${color}`}>{sign}{value.toFixed(1)}{suffix}</span>;
}

export function Phase3Timeline({
  campaignLock,
  backtestSummary,
}: {
  campaignLock?: CampaignLockInfo | null;
  backtestSummary?: {
    projectedAcos: number | null;
    projectedSpend: number;
    projectedSales: number;
    acosDeltaPct: number;
    spendDeltaPct: number;
    salesDeltaPct: number;
    dataQuality: string;
    daysWithData: number;
    summary: string;
  } | null;
}) {
  const checkpoints: TimelineCheckpoint[] = useMemo(() => {
    const points: TimelineCheckpoint[] = [];

    if (!campaignLock || campaignLock.lockState === "unlocked" || campaignLock.lockState === "expired") {
      return points;
    }

    // Day 0: Decision made
    points.push({
      label: "Decision",
      day: 0,
      status: "completed",
      detail: campaignLock.appliedChange,
    });

    // Day 7 checkpoint
    const day7Complete = !!campaignLock.day7Checkpoint;
    points.push({
      label: "Day 7 Checkpoint",
      day: 7,
      status: day7Complete ? "completed" : campaignLock.lockState === "locked_active" ? "active" : "pending",
      detail: day7Complete ? "ACOS checkpoint passed" : "Evaluating ACOS trend at day 7",
    });

    // Day 14 outcome
    const day14Complete = !!campaignLock.day14Checkpoint;
    points.push({
      label: "Day 14 Outcome",
      day: 14,
      status: day14Complete ? "completed" : "pending",
      detail: day14Complete ? "Full evaluation complete" : "Awaiting full observation window",
    });

    // Backtest projection if available
    if (backtestSummary && backtestSummary.dataQuality !== "insufficient") {
      const acosStatus = backtestSummary.acosDeltaPct < 0 ? "completed" : backtestSummary.acosDeltaPct > 10 ? "warning" : "pending";
      points.push({
        label: "Projected Impact",
        day: backtestSummary.daysWithData,
        status: acosStatus,
        detail: backtestSummary.summary,
        acosDelta: backtestSummary.acosDeltaPct,
        salesDelta: backtestSummary.salesDeltaPct,
      });
    }

    return points;
  }, [campaignLock, backtestSummary]);

  if (!campaignLock || campaignLock.lockState === "unlocked" || campaignLock.lockState === "expired") {
    return null;
  }

  const lockStateLabels: Record<string, { label: string; color: string }> = {
    locked_pending: { label: "Pending Approval", color: "text-amber-600 dark:text-amber-400" },
    locked_active: { label: "In Observation", color: "text-indigo-600 dark:text-indigo-400" },
    locked_cooldown: { label: "Evaluating", color: "text-slate-600 dark:text-slate-400" },
    expired: { label: "Complete", color: "text-emerald-600 dark:text-emerald-400" },
  };

  const lockLabel = lockStateLabels[campaignLock.lockState] ?? { label: campaignLock.lockState, color: "text-slate-600" };

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70">
      <div className="mb-4 flex items-center gap-3">
        <h3 className="text-sm font-semibold text-slate-900 dark:text-white">14-Day Observation Timeline</h3>
        <span className={`text-xs font-medium ${lockLabel.color}`}>{lockLabel.label}</span>
      </div>

      <p className="mb-4 text-xs text-slate-500 dark:text-slate-400">
        Campaign <span className="font-medium text-slate-700 dark:text-slate-300">{campaignLock.campaignName}</span> is locked for{" "}
        {campaignLock.recommendationType.replace(/_/g, " ")}. No conflicting changes are permitted until the observation window closes.
      </p>

      {/* Timeline */}
      <div className="relative">
        {/* Horizontal track */}
        <div className="absolute left-0 top-4 h-0.5 w-full bg-slate-200 dark:bg-slate-700" />

        <div className="relative flex justify-between">
          {checkpoints.map((point, idx) => (
            <div key={idx} className="flex flex-col items-center" style={{ width: `${100 / Math.max(checkpoints.length, 1)}%` }}>
              {/* Dot */}
              <div
                className={`z-10 flex h-8 w-8 items-center justify-center rounded-full border-2 ${
                  point.status === "completed"
                    ? "border-emerald-500 bg-emerald-100 dark:border-emerald-400 dark:bg-emerald-400/20"
                    : point.status === "active"
                    ? "border-indigo-500 bg-indigo-100 dark:border-indigo-400 dark:bg-indigo-400/20"
                    : point.status === "warning"
                    ? "border-amber-500 bg-amber-100 dark:border-amber-400 dark:bg-amber-400/20"
                    : "border-slate-300 bg-white dark:border-slate-600 dark:bg-slate-800"
                }`}
              >
                <span className="text-xs font-bold text-slate-700 dark:text-slate-300">{point.day}</span>
              </div>
              <p className="mt-2 text-center text-xs font-medium text-slate-700 dark:text-slate-300">{point.label}</p>
              {point.detail && <p className="mt-1 text-center text-[10px] text-slate-500 dark:text-slate-400 leading-tight">{point.detail}</p>}
              <span className="mt-1">{statusBadge(point.status)}</span>
              {point.acosDelta !== undefined && (
                <p className="mt-1 text-xs">
                  ACOS {deltaLabel(point.acosDelta)}
                  {point.salesDelta !== undefined && <> / Sales {deltaLabel(point.salesDelta)}</>}
                </p>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Backtest summary card */}
      {backtestSummary && backtestSummary.dataQuality !== "insufficient" && (
        <div className="mt-6 rounded-lg border border-indigo-100 bg-indigo-50/50 p-4 dark:border-indigo-400/20 dark:bg-indigo-400/5">
          <p className="text-xs font-semibold text-indigo-700 dark:text-indigo-300">Backtest Projection</p>
          <div className="mt-2 grid grid-cols-3 gap-3">
            <div>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">Projected ACOS</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                {backtestSummary.projectedAcos?.toFixed(1) ?? "N/A"}%
              </p>
              {deltaLabel(backtestSummary.acosDeltaPct)}
            </div>
            <div>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">Projected Spend</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                ${backtestSummary.projectedSpend.toFixed(2)}
              </p>
              {deltaLabel(backtestSummary.spendDeltaPct)}
            </div>
            <div>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">Projected Sales</p>
              <p className="text-sm font-semibold text-slate-900 dark:text-white">
                ${backtestSummary.projectedSales.toFixed(2)}
              </p>
              {deltaLabel(backtestSummary.salesDeltaPct)}
            </div>
          </div>
          <p className="mt-2 text-[11px] text-slate-500 dark:text-slate-400">
            Based on {backtestSummary.daysWithData} days of historical data. {backtestSummary.summary}
          </p>
        </div>
      )}
    </div>
  );
}