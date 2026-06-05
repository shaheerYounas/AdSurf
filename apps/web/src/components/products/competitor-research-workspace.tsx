"use client";

/**
 * Competitor research workspace.
 *
 * Allows the user to:
 * 1. Choose keywords (seeds, or auto-pull from high-spend / move-to-exact recommendations)
 * 2. Configure run settings (marketplace, limits, delays)
 * 3. Start a VISIBLE browser session (headless=false by default)
 * 4. Watch progress in real time (polling)
 * 5. Review per-keyword AI insights with opportunity/strength scores
 * 6. See CAPTCHA pause banner and resume when ready
 *
 * SAFETY:
 *  - Only public Amazon search result pages are read.
 *  - If Amazon shows a CAPTCHA, the run pauses and shows a banner.
 *    The user must complete verification manually then click Resume.
 *  - No Amazon Ads live changes are made.
 *  - Approved actions remain export-only.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import {
  createCompetitorResearchRun,
  startCompetitorResearchRun,
  controlCompetitorResearchRun,
  getCompetitorResearchRun,
  type CompetitorResearchRun,
  type CompetitorResearchRunDetail,
  type CompetitorResearchKeyword,
  type CompetitorAiInsight,
  type CompetitorResearchRunSettings,
} from "@/lib/api/products";
import { formatApiError } from "@/lib/api/client";

interface Props {
  productId?: string;
}

// ─── Sub-components ────────────────────────────────────────────────────────────

function ScoreBadge({ score, label }: { score?: number; label?: string }) {
  if (score === undefined || score === null) return <span className="text-slate-400">—</span>;
  const color =
    score >= 70
      ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300"
      : score >= 40
      ? "bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300"
      : "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300";
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-semibold ${color}`}>
      {score}
      {label && <span className="font-normal opacity-70">{label}</span>}
    </span>
  );
}

function KeywordStatusDot({ status }: { status: string }) {
  const color: Record<string, string> = {
    queued: "bg-slate-400",
    running: "bg-indigo-500 animate-pulse",
    succeeded: "bg-emerald-500",
    failed: "bg-red-500",
    skipped: "bg-slate-300",
  };
  return (
    <span className={`inline-block h-2 w-2 rounded-full ${color[status] ?? "bg-slate-400"}`} />
  );
}

function RunStatusBanner({ run, onResume, onCancel }: { run: CompetitorResearchRun; onResume: () => void; onCancel: () => void }) {
  if (run.status === "paused_manual_verification") {
    return (
      <div className="rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-950/30">
        <p className="font-semibold text-amber-900 dark:text-amber-300">⚠️ Manual verification required</p>
        <p className="mt-1 text-sm text-amber-700 dark:text-amber-400">
          Amazon has shown a verification challenge in the browser window.
          Please complete it manually, then click <strong>Resume</strong> to continue.
          This tool does not bypass CAPTCHA or bot protection.
        </p>
        {run.paused_reason && (
          <p className="mt-1 text-xs text-amber-600 dark:text-amber-500">{run.paused_reason}</p>
        )}
        <div className="mt-3 flex gap-2">
          <button onClick={onResume} className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700">
            Resume
          </button>
          <button onClick={onCancel} className="rounded-lg border border-amber-300 px-4 py-2 text-sm text-amber-800 hover:bg-amber-100 dark:border-amber-600 dark:text-amber-300">
            Cancel run
          </button>
        </div>
      </div>
    );
  }
  if (run.status === "running") {
    return (
      <div className="rounded-xl border border-indigo-200 bg-indigo-50 p-3 dark:border-indigo-700 dark:bg-indigo-950/20">
        <p className="text-sm font-medium text-indigo-800 dark:text-indigo-300">
          🔍 Researching {run.keywords_completed} / {run.keywords_total} keywords…
          <span className="ml-2 text-indigo-500">{run.products_captured} products captured</span>
        </p>
      </div>
    );
  }
  if (run.status === "succeeded") {
    return (
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3 dark:border-emerald-700 dark:bg-emerald-950/20">
        <p className="text-sm font-medium text-emerald-800 dark:text-emerald-300">
          ✅ Research complete — {run.keywords_completed} keywords · {run.products_captured} products captured
        </p>
      </div>
    );
  }
  if (run.status === "failed") {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-3 dark:border-red-700 dark:bg-red-950/20">
        <p className="text-sm font-medium text-red-800 dark:text-red-300">
          ❌ Run failed: {run.error_message || "Unknown error"}
        </p>
      </div>
    );
  }
  return null;
}

// ─── Main component ────────────────────────────────────────────────────────────

export function CompetitorResearchWorkspace({ productId }: Props) {
  // Setup state
  const [keywordsText, setKeywordsText] = useState("");
  const [includeHighSpend, setIncludeHighSpend] = useState(true);
  const [includeMoveToExact, setIncludeMoveToExact] = useState(true);
  const [marketplace, setMarketplace] = useState("US");
  const [maxKeywords, setMaxKeywords] = useState(20);
  const [maxCompetitors, setMaxCompetitors] = useState(10);

  // Run state
  const [run, setRun] = useState<CompetitorResearchRunDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pollingActive, setPollingActive] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Polling ────────────────────────────────────────────────────────────────

  const pollRun = useCallback(async () => {
    if (!run) return;
    try {
      const updated = await getCompetitorResearchRun(run.id);
      setRun(updated);
      if (updated.status !== "running") {
        stopPolling();
      }
    } catch {
      // Non-fatal — keep polling
    }
  }, [run]);

  function startPolling() {
    setPollingActive(true);
    pollRef.current = setInterval(pollRun, 4000);
  }

  function stopPolling() {
    setPollingActive(false);
    if (pollRef.current) clearInterval(pollRef.current);
  }

  useEffect(() => {
    if (pollingActive) {
      pollRef.current = setInterval(pollRun, 4000);
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [pollRun, pollingActive]);

  // ── Create + start ─────────────────────────────────────────────────────────

  async function handleCreate() {
    setLoading(true);
    setError(null);
    try {
      const seeds = keywordsText
        .split(/[\n,]+/)
        .map((s) => s.trim())
        .filter(Boolean);

      const settings: CompetitorResearchRunSettings = {
        marketplace,
        max_keywords_per_run: maxKeywords,
        max_competitors_per_keyword: maxCompetitors,
        headless: false, // Always visible — user supervises
      };

      const created = await createCompetitorResearchRun({
        product_id: productId,
        settings,
        seed_keywords: seeds,
        include_high_spend_terms: includeHighSpend,
        include_move_to_exact_terms: includeMoveToExact,
      });

      // Fetch full detail
      const detail = await getCompetitorResearchRun(created.id);
      setRun(detail);
    } catch (err) {
      setError(formatApiError(err, "Failed to create research run."));
    } finally {
      setLoading(false);
    }
  }

  async function handleStart() {
    if (!run) return;
    setStarting(true);
    setError(null);
    try {
      const result = await startCompetitorResearchRun(run.id);
      const detail = await getCompetitorResearchRun(run.id);
      setRun(detail);
      if (result.run.status === "running") {
        startPolling();
      }
    } catch (err) {
      setError(formatApiError(err, "Failed to start run."));
    } finally {
      setStarting(false);
    }
  }

  async function handleResume() {
    if (!run) return;
    try {
      await controlCompetitorResearchRun(run.id, "resume");
      const detail = await getCompetitorResearchRun(run.id);
      setRun(detail);
      startPolling();
    } catch (err) {
      setError(formatApiError(err, "Failed to resume run."));
    }
  }

  async function handleCancel() {
    if (!run) return;
    try {
      await controlCompetitorResearchRun(run.id, "cancel");
      const detail = await getCompetitorResearchRun(run.id);
      setRun(detail);
      stopPolling();
    } catch (err) {
      setError(formatApiError(err, "Failed to cancel run."));
    }
  }

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-white">Competitor research</h1>
        <p className="mt-1 text-sm text-slate-500">
          Open a visible browser session, search Amazon for your keywords, and get AI analysis per keyword.
        </p>
      </div>

      {/* Safety banner */}
      <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/20 dark:text-blue-300">
        🔒 <strong>Research assistant only.</strong> This tool reads public Amazon search pages in a visible browser.
        No Amazon Ads changes are made. Approved actions remain export-only. If Amazon shows a CAPTCHA, the run pauses —
        it is never bypassed.
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-800 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      )}

      {/* Run status banner */}
      {run && (
        <RunStatusBanner run={run} onResume={handleResume} onCancel={handleCancel} />
      )}

      {/* Setup panel (shown when no run yet) */}
      {!run && (
        <div className="rounded-xl border border-slate-200 bg-white p-6 dark:border-slate-700 dark:bg-slate-800 space-y-5">
          <h2 className="font-semibold text-slate-900 dark:text-white">Set up research run</h2>

          {/* Keyword input */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300">
              Seed keywords <span className="text-slate-400">(one per line or comma-separated)</span>
            </label>
            <textarea
              rows={4}
              value={keywordsText}
              onChange={(e) => setKeywordsText(e.target.value)}
              placeholder="e.g. organic coffee pods&#10;k-cup variety pack&#10;espresso capsules"
              className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-white"
            />
          </div>

          {/* Auto-keyword sources */}
          <div className="flex flex-wrap gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeHighSpend}
                onChange={(e) => setIncludeHighSpend(e.target.checked)}
                className="rounded border-slate-300"
              />
              <span className="text-slate-700 dark:text-slate-300">
                Include high-spend search terms from ads data
              </span>
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={includeMoveToExact}
                onChange={(e) => setIncludeMoveToExact(e.target.checked)}
                className="rounded border-slate-300"
              />
              <span className="text-slate-700 dark:text-slate-300">
                Include move-to-exact keyword recommendations
              </span>
            </label>
          </div>

          {/* Settings row */}
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">Marketplace</label>
              <select
                value={marketplace}
                onChange={(e) => setMarketplace(e.target.value)}
                className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-white"
              >
                <option value="US">Amazon US</option>
                <option value="CA">Amazon CA</option>
                <option value="UK">Amazon UK</option>
                <option value="DE">Amazon DE</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">Max keywords</label>
              <input
                type="number"
                min={1}
                max={50}
                value={maxKeywords}
                onChange={(e) => setMaxKeywords(Number(e.target.value))}
                className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-white"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 dark:text-slate-300">Competitors per keyword</label>
              <input
                type="number"
                min={1}
                max={20}
                value={maxCompetitors}
                onChange={(e) => setMaxCompetitors(Number(e.target.value))}
                className="mt-1 w-full rounded border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-600 dark:bg-slate-700 dark:text-white"
              />
            </div>
          </div>

          <button
            onClick={handleCreate}
            disabled={loading}
            className="rounded-lg bg-indigo-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {loading ? "Setting up…" : "Build keyword queue →"}
          </button>
        </div>
      )}

      {/* Keyword queue + start button */}
      {run && run.status === "queued" && (
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800 space-y-0">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <div>
              <h2 className="font-semibold text-slate-900 dark:text-white">
                {run.keywords_total} keyword{run.keywords_total !== 1 ? "s" : ""} queued
              </h2>
              <p className="text-xs text-slate-500">
                A visible browser window will open. You can watch Amazon searches happen in real time.
              </p>
            </div>
            <button
              onClick={handleStart}
              disabled={starting}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {starting ? "Opening browser…" : "▶ Start research"}
            </button>
          </div>
          <KeywordQueueTable keywords={run.keywords} />
        </div>
      )}

      {/* Live progress + keyword table */}
      {run && run.status === "running" && (
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
          <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <h2 className="font-semibold text-slate-900 dark:text-white">Keyword progress</h2>
          </div>
          <KeywordQueueTable keywords={run.keywords} />
        </div>
      )}

      {/* AI Insights table */}
      {run && run.insights.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
          <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <h2 className="font-semibold text-slate-900 dark:text-white">
              AI keyword insights
            </h2>
            <p className="text-xs text-slate-500">
              Generated by AI from SERP data. Conservative estimates — multi-signal decisions only.
            </p>
          </div>
          <InsightsTable insights={run.insights} />
        </div>
      )}

      {/* Completed keyword table */}
      {run && run.status === "succeeded" && run.insights.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
          <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-700">
            <h2 className="font-semibold text-slate-900 dark:text-white">Keyword results</h2>
          </div>
          <KeywordQueueTable keywords={run.keywords} />
        </div>
      )}

      {/* New run button */}
      {run && run.status !== "queued" && run.status !== "running" && (
        <button
          onClick={() => { setRun(null); setError(null); }}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700"
        >
          Start a new run
        </button>
      )}
    </div>
  );
}

// ─── Keyword queue table ───────────────────────────────────────────────────────

function KeywordQueueTable({ keywords }: { keywords: CompetitorResearchKeyword[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">#</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Keyword</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Source</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Status</th>
            <th className="px-4 py-2 text-right font-medium text-slate-600 dark:text-slate-400">Organic</th>
            <th className="px-4 py-2 text-right font-medium text-slate-600 dark:text-slate-400">Sponsored</th>
          </tr>
        </thead>
        <tbody>
          {keywords.map((kw) => (
            <tr key={kw.id} className="border-b border-slate-100 last:border-0 dark:border-slate-700/50">
              <td className="px-4 py-2 text-slate-400">{kw.priority_rank + 1}</td>
              <td className="px-4 py-2 font-medium text-slate-800 dark:text-slate-200">{kw.keyword}</td>
              <td className="px-4 py-2 text-xs text-slate-500">
                {kw.keyword_source?.replace(/_/g, " ") ?? "—"}
              </td>
              <td className="px-4 py-2">
                <span className="flex items-center gap-1.5">
                  <KeywordStatusDot status={kw.status} />
                  <span className="capitalize text-slate-600 dark:text-slate-400">{kw.status}</span>
                </span>
              </td>
              <td className="px-4 py-2 text-right text-slate-500">{kw.organic_count ?? "—"}</td>
              <td className="px-4 py-2 text-right text-slate-500">{kw.sponsored_count ?? "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Insights table ────────────────────────────────────────────────────────────

function InsightsTable({ insights }: { insights: CompetitorAiInsight[] }) {
  const [expanded, setExpanded] = useState<string | null>(null);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800/60">
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Keyword</th>
            <th className="px-4 py-2 text-center font-medium text-slate-600 dark:text-slate-400">Opportunity</th>
            <th className="px-4 py-2 text-center font-medium text-slate-600 dark:text-slate-400">Comp. strength</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Sponsored</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Price range</th>
            <th className="px-4 py-2 text-left font-medium text-slate-600 dark:text-slate-400">Action</th>
          </tr>
        </thead>
        <tbody>
          {insights.map((insight) => (
            <>
              <tr
                key={insight.id}
                className="cursor-pointer border-b border-slate-100 hover:bg-slate-50 last:border-0 dark:border-slate-700/50 dark:hover:bg-slate-800/40"
                onClick={() => setExpanded(expanded === insight.id ? null : insight.id)}
              >
                <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200">
                  <span className="mr-1 text-xs text-slate-400">{expanded === insight.id ? "▾" : "▸"}</span>
                  {insight.keyword}
                </td>
                <td className="px-4 py-3 text-center">
                  <ScoreBadge score={insight.opportunity_score} />
                </td>
                <td className="px-4 py-3 text-center">
                  <ScoreBadge score={insight.competitor_strength_score} />
                </td>
                <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-400">
                  {insight.sponsored_intensity ?? "—"}
                </td>
                <td className="px-4 py-3 text-sm text-slate-600 dark:text-slate-400">
                  {insight.avg_price_range ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <ActionChip action={insight.action_recommendation} />
                </td>
              </tr>
              {expanded === insight.id && (
                <tr key={`${insight.id}-detail`} className="border-b border-slate-100 dark:border-slate-700/50">
                  <td colSpan={6} className="bg-slate-50 px-6 py-4 dark:bg-slate-800/40">
                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <p className="font-medium text-slate-700 dark:text-slate-300">Summary</p>
                        <p className="mt-1 text-slate-600 dark:text-slate-400">{insight.full_summary ?? "No summary available."}</p>
                      </div>
                      <div className="space-y-2">
                        {insight.recommended_ad_strategy && (
                          <div>
                            <p className="text-xs font-medium text-slate-500">Recommended strategy</p>
                            <p className="text-slate-700 dark:text-slate-300">{insight.recommended_ad_strategy}</p>
                          </div>
                        )}
                        {insight.listing_improvement && (
                          <div>
                            <p className="text-xs font-medium text-slate-500">Listing improvement</p>
                            <p className="text-slate-700 dark:text-slate-300">{insight.listing_improvement}</p>
                          </div>
                        )}
                        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                          {insight.avg_review_count && <span>Avg reviews: {insight.avg_review_count}</span>}
                          {insight.organic_difficulty && <span>Organic difficulty: {insight.organic_difficulty}</span>}
                          {insight.product_market_fit && <span>Market fit: {insight.product_market_fit}</span>}
                          <span>Source: {insight.ai_provider ?? "heuristic"}</span>
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ActionChip({ action }: { action?: string }) {
  if (!action) return <span className="text-slate-400">—</span>;
  const colors: Record<string, string> = {
    increase_bid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400",
    decrease_bid: "bg-amber-100 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
    move_to_exact: "bg-blue-100 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
    keep_running: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400",
    watch: "bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-400",
    avoid: "bg-red-100 text-red-700 dark:bg-red-900/20 dark:text-red-400",
  };
  const labels: Record<string, string> = {
    increase_bid: "Increase bid",
    decrease_bid: "Decrease bid",
    move_to_exact: "Harvest to exact",
    keep_running: "Keep running",
    watch: "Watch",
    avoid: "Avoid",
  };
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors[action] ?? "bg-slate-100 text-slate-600"}`}>
      {labels[action] ?? action.replace(/_/g, " ")}
    </span>
  );
}
