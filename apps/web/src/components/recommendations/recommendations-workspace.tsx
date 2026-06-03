"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { decideRecommendation, getRecommendations, type Recommendation } from "@/lib/api/monitoring";
import { getCachedData, setCachedData } from "@/lib/prefetch";

const statusOptions = [
  { value: "pending_approval", label: "Pending approval" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

const sourceOptions = [
  { value: "deepseek_ai", label: "DeepSeek AI" },
  { value: "fallback_rules", label: "Fallback rules" },
  { value: "deterministic_rules", label: "Deterministic rules" },
];

const priorityOptions = [
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const recommendationTypeOptions = [
  { value: "keep_running", label: "Keep running" },
  { value: "increase_bid", label: "Increase bid" },
  { value: "decrease_bid", label: "Decrease bid" },
  { value: "pause_review", label: "Pause review" },
  { value: "add_negative_exact", label: "Negative exact" },
  { value: "add_negative_phrase", label: "Negative phrase" },
  { value: "move_to_exact", label: "Move to exact" },
  { value: "watch_lock", label: "Watch lock" },
  { value: "data_quality_review", label: "Data quality review" },
  { value: "budget_review", label: "Budget review" },
];

export function RecommendationsWorkspace() {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [priorityFilter, setPriorityFilter] = useState("");
  const [decisionTarget, setDecisionTarget] = useState<{ recommendation: Recommendation; decision: "approve" | "reject" } | null>(null);
  const [note, setNote] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    load();
  }, []);

  const filtered = useMemo(
    () =>
      recommendations.filter(
        (item) =>
          (!statusFilter || item.status === statusFilter) &&
          (!sourceFilter || recommendationSource(item) === sourceFilter) &&
          (!typeFilter || item.recommendation_type === typeFilter) &&
          (!priorityFilter || item.priority === priorityFilter),
      ),
    [recommendations, priorityFilter, sourceFilter, statusFilter, typeFilter],
  );

  async function load() {
    setMessage(null);

    // Return cached data immediately if prefetched in background.
    const cached = getCachedData<Recommendation[]>("recommendations:list");
    if (cached) {
      setRecommendations(cached);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    try {
      const data = await getRecommendations(workspaceId);
      setCachedData("recommendations:list", data, 60_000);
      setRecommendations(data);
    } catch (caught) {
      setMessage(formatApiError(caught, "Recommendations could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  async function saveDecision() {
    if (!decisionTarget) return;
    setMessage(null);
    setIsLoading(true);
    try {
      await decideRecommendation(decisionTarget.recommendation.id, decisionTarget.decision, note, workspaceId);
      setDecisionTarget(null);
      setNote("");
      await load();
    } catch (caught) {
      setMessage(formatApiError(caught, "Recommendation decision could not be saved."));
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div
        aria-label="Does not change Amazon Ads account. No live Amazon Ads change executed."
        className="rounded-2xl border border-slate-200 bg-white p-5 dark:border-white/10 dark:bg-slate-950/70"
      >
        <div className="flex flex-wrap items-end gap-3">
          <Select className="w-[11rem]" label="Status" onChange={setStatusFilter} options={statusOptions} value={statusFilter} placeholder="All" />
          <Select className="w-[12rem]" label="Source" onChange={setSourceFilter} options={sourceOptions} value={sourceFilter} placeholder="All" />
          <Select className="w-[10.5rem]" label="Priority" onChange={setPriorityFilter} options={priorityOptions} value={priorityFilter} placeholder="All" />
          <Select className="w-[13rem]" label="Type" onChange={setTypeFilter} options={recommendationTypeOptions} value={typeFilter} placeholder="All" />
          <Button disabled={isLoading} onClick={load} size="sm" type="button" variant="secondary">
            Refresh
          </Button>
        </div>
        {message ? <p className="mt-3 rounded-2xl bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-400/10 dark:text-red-300">{message}</p> : null}
      </div>

      <div className="overflow-x-auto rounded-md border border-slate-200 bg-white dark:border-white/10 dark:bg-slate-950/70">
        <table className="min-w-full divide-y divide-slate-200 text-sm dark:divide-white/10">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500 dark:bg-white/5 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2">Priority</th>
              <th className="px-3 py-2">Source</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Campaign</th>
              <th className="px-3 py-2">Search term</th>
              <th className="px-3 py-2">Evidence</th>
              <th className="px-3 py-2">AI reasoning</th>
              <th className="px-3 py-2">Proposed action</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/5">
            {filtered.map((recommendation) => (
              <tr key={recommendation.id}>
                <td className="px-3 py-2 font-medium text-slate-900 dark:text-white">{recommendation.priority}<br /><span className="text-xs font-normal text-slate-500 dark:text-slate-400">{recommendation.confidence} confidence</span></td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">
                  {recommendationSource(recommendation) === "deepseek_ai" ? "AI-generated recommendation" : "Deterministic fallback recommendation"}
                  <br />
                  <span className="text-xs text-slate-500 dark:text-slate-400">{recommendationModelLabel(recommendation)}</span>
                </td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{recommendation.recommendation_type}<br /><span className="text-xs text-slate-500 dark:text-slate-400">{recommendation.entity_type}</span></td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{recommendation.campaign_name}<br />{recommendation.ad_group_name}</td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{recommendation.customer_search_term}</td>
                <td className="px-3 py-2 text-slate-600 dark:text-slate-400">
                  Spend {recommendation.current_metric_snapshot_json.spend ?? recommendation.input_metrics_json.spend} / clicks {recommendation.current_metric_snapshot_json.clicks ?? recommendation.input_metrics_json.clicks} / orders {recommendation.current_metric_snapshot_json.orders ?? recommendation.input_metrics_json.orders}
                  <br />
                  ACOS {recommendation.current_metric_snapshot_json.acos ?? "n/a"} / ROAS {recommendation.current_metric_snapshot_json.roas ?? "n/a"} / CVR {recommendation.current_metric_snapshot_json.cvr ?? "n/a"}
                  <br />
                  <span className="text-slate-500 dark:text-slate-400">Rule {recommendation.rule_name}</span>
                  {aiSignals(recommendation).length ? (
                    <>
                      <br />
                      <span className="text-slate-500 dark:text-slate-400">Signals {aiSignals(recommendation).join(", ")}</span>
                    </>
                  ) : null}
                </td>
                <td className="min-w-72 px-3 py-2 text-slate-700 dark:text-slate-300">
                  {recommendation.explanation_json.summary}
                </td>
                <td className="min-w-64 px-3 py-2 text-slate-700 dark:text-slate-300">
                  {proposedActionLabel(recommendation)}
                </td>
                <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{recommendation.status}</td>
                <td className="px-3 py-2">
                  {recommendation.status === "pending_approval" ? (
                    <div className="flex gap-2">
                      <Button onClick={() => setDecisionTarget({ recommendation, decision: "approve" })} type="button" variant="success">Approve</Button>
                      <Button onClick={() => setDecisionTarget({ recommendation, decision: "reject" })} type="button" variant="danger">Reject</Button>
                    </div>
                  ) : (
                    <span className="text-slate-500 dark:text-slate-400">Decided</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!isLoading && !filtered.length ? <p className="p-8 text-sm text-slate-600 dark:text-slate-400">No recommendations match the selected filters.</p> : null}
      </div>

      <Modal
        open={decisionTarget !== null}
        onClose={() => setDecisionTarget(null)}
        title={decisionTarget?.decision === "approve" ? "Approve recommendation" : "Reject recommendation"}
        description={`${decisionTarget?.recommendation.recommendation_type ?? ""} for ${decisionTarget?.recommendation.customer_search_term ?? ""}. This records a human decision only; no Amazon Ads change is executed.`}
      >
        {/* Safety disclaimer */}
        <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:bg-amber-400/10 dark:text-amber-300">
          This records a human decision only. No Amazon Ads API call is made. Changes must be exported and uploaded to Amazon Ads manually.
        </p>
        <textarea
          className="block mt-3 h-28 w-full rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-950 outline-none transition hover:border-slate-300 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:border-white/20 dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20"
          onChange={(event) => setNote(event.target.value)}
          placeholder="Add a note explaining your decision..."
          value={note}
        />
        <div className="mt-4 flex gap-2">
          <Button disabled={!note.trim() || isLoading} onClick={saveDecision} type="button" variant={decisionTarget?.decision === "approve" ? "success" : "danger"}>
            {isLoading ? <LoadingSpinner iconOnly size="sm" /> : null}
            {isLoading ? "Saving..." : `Confirm ${decisionTarget?.decision ?? ""}`}
          </Button>
          <Button onClick={() => setDecisionTarget(null)} type="button" variant="secondary">Cancel</Button>
        </div>
      </Modal>
    </div>
  );
}

function recommendationSource(recommendation: Recommendation) {
  return String(recommendation.evidence_json.decision_source || recommendation.explanation_json.decision_source || "deterministic_rules");
}

function recommendationModelLabel(recommendation: Recommendation) {
  const provider = recommendation.evidence_json.ai_provider || recommendation.explanation_json.ai_provider;
  const model = recommendation.evidence_json.ai_model || recommendation.explanation_json.ai_model;
  if (provider && model) return `${provider} / ${model}`;
  if (provider) return String(provider);
  return "Local rules";
}

function aiSignals(recommendation: Recommendation) {
  const evidence = recommendation.evidence_json.ai_evidence;
  if (!evidence || typeof evidence !== "object" || !("main_signals" in evidence)) return [];
  const signals = (evidence as { main_signals?: unknown }).main_signals;
  return Array.isArray(signals) ? signals.map(String).slice(0, 3) : [];
}

function proposedActionLabel(recommendation: Recommendation) {
  const action = recommendation.proposed_action_json.action || recommendation.recommendation_type;
  const level = recommendation.proposed_action_json.action_level || recommendation.entity_type;
  const multiplier = recommendation.proposed_action_json.suggested_bid_multiplier;
  const negativeMatch = recommendation.proposed_action_json.negative_match_type;
  return [action, `level ${level}`, multiplier ? `bid x${multiplier}` : null, negativeMatch ? `negative ${negativeMatch}` : null].filter(Boolean).join(" / ");
}