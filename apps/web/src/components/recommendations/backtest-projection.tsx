"use client";
import { useState } from "react";

type BacktestProjection = {
  projectedAcos: number | null; projectedSpend: number; projectedSales: number;
  acosDeltaPct: number; spendDeltaPct: number; salesDeltaPct: number;
  dataQuality: string; daysWithData: number; warnings: string[]; summary: string;
};

function deltaColor(v: number, inv = false) {
  if (v === 0) return "text-slate-500";
  return (inv ? v < 0 : v > 0) ? "text-emerald-600" : "text-red-600";
}

export function BacktestProjectionCard({ projection }: { projection: BacktestProjection | null }) {
  const [show, setShow] = useState(false);
  if (!projection) return null;

  return (
    <div className="mt-2">
      <button type="button" onClick={() => setShow(!show)}
        className="rounded-lg border border-indigo-200 bg-indigo-50 px-3 py-2 text-xs font-medium text-indigo-700 transition hover:bg-indigo-100 dark:border-indigo-400/20 dark:bg-indigo-400/10 dark:text-indigo-300">
        {show ? "Hide projected impact" : "Show projected impact"}
      </button>
      {show && (
        <div className={`mt-2 rounded-lg border p-3 ${projection.dataQuality !== "insufficient" ? "border-indigo-100 bg-indigo-50/50 dark:border-indigo-400/20 dark:bg-indigo-400/5" : "border-amber-100 bg-amber-50/50 dark:border-amber-400/20 dark:bg-amber-400/5"}`}>
          <p className="text-xs font-semibold">Counterfactual Backtest</p>
          <p className="mt-1 text-[10px] text-slate-500">If applied {projection.daysWithData} days ago:</p>
          <div className="mt-2 grid grid-cols-3 gap-2">
            <div className="rounded bg-white p-2 dark:bg-slate-800/50">
              <p className="text-[9px] uppercase text-slate-500">ACOS</p>
              <p className="text-sm font-bold">{projection.projectedAcos?.toFixed(1) ?? "N/A"}%</p>
              <p className={`text-[10px] font-medium ${deltaColor(projection.acosDeltaPct, true)}`}>{projection.acosDeltaPct > 0 ? "+" : ""}{projection.acosDeltaPct.toFixed(1)}%</p>
            </div>
            <div className="rounded bg-white p-2 dark:bg-slate-800/50">
              <p className="text-[9px] uppercase text-slate-500">Spend</p>
              <p className="text-sm font-bold">${projection.projectedSpend.toFixed(2)}</p>
              <p className={`text-[10px] font-medium ${deltaColor(projection.spendDeltaPct, true)}`}>{projection.spendDeltaPct > 0 ? "+" : ""}{projection.spendDeltaPct.toFixed(1)}%</p>
            </div>
            <div className="rounded bg-white p-2 dark:bg-slate-800/50">
              <p className="text-[9px] uppercase text-slate-500">Sales</p>
              <p className="text-sm font-bold">${projection.projectedSales.toFixed(2)}</p>
              <p className={`text-[10px] font-medium ${deltaColor(projection.salesDeltaPct)}`}>{projection.salesDeltaPct > 0 ? "+" : ""}{projection.salesDeltaPct.toFixed(1)}%</p>
            </div>
          </div>
          <p className="mt-2 text-[10px] text-slate-600">{projection.summary}</p>
          {projection.warnings.map((w, i) => <p key={i} className="text-[10px] text-amber-600">{w}</p>)}
        </div>
      )}
    </div>
  );
}