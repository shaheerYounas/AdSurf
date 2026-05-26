"use client";

import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { defaultWorkspaceId } from "@/lib/api/client";
import { decideRecommendation, getRecommendations, type Recommendation } from "@/lib/api/monitoring";

export function RecommendationsWorkspace() {
  const [workspaceId, setWorkspaceId] = useState(defaultWorkspaceId);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [statusFilter, setStatusFilter] = useState("");
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
    () => recommendations.filter((item) => (!statusFilter || item.status === statusFilter) && (!typeFilter || item.recommendation_type === typeFilter) && (!priorityFilter || item.priority === priorityFilter)),
    [recommendations, priorityFilter, statusFilter, typeFilter],
  );

  async function load() {
    setMessage(null);
    setIsLoading(true);
    try {
      setRecommendations(await getRecommendations(workspaceId));
    } catch (caught) {
      setMessage(caught instanceof Error ? caught.message : "Recommendations could not be loaded.");
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
      setMessage(caught instanceof Error ? caught.message : "Recommendation decision could not be saved.");
      setIsLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="rounded-md border border-slate-200 bg-white p-5">
        <div className="flex flex-wrap items-end gap-3">
          <label className="space-y-2 text-sm font-medium text-slate-700">
            Workspace ID
            <input className="block w-72 rounded-md border border-slate-300 px-3 py-2 font-mono text-sm" onChange={(event) => setWorkspaceId(event.target.value)} value={workspaceId} />
          </label>
          <Filter label="Status" onChange={setStatusFilter} options={["pending_approval", "approved", "rejected"]} value={statusFilter} />
          <Filter label="Priority" onChange={setPriorityFilter} options={["critical", "high", "medium", "low"]} value={priorityFilter} />
          <Filter label="Type" onChange={setTypeFilter} options={["keep_running", "increase_bid", "decrease_bid", "pause_review", "add_negative_exact", "add_negative_phrase", "move_to_exact", "watch_lock", "data_quality_review", "budget_review"]} value={typeFilter} />
          <Button className="bg-slate-700" disabled={isLoading} onClick={load} type="button">
            Refresh
          </Button>
        </div>
        {message ? <p className="mt-3 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{message}</p> : null}
      </div>

      <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold uppercase text-slate-500">
            <tr>
              <th className="px-3 py-2">Priority</th>
              <th className="px-3 py-2">Type</th>
              <th className="px-3 py-2">Campaign</th>
              <th className="px-3 py-2">Search term</th>
              <th className="px-3 py-2">Evidence</th>
              <th className="px-3 py-2">Rule explanation</th>
              <th className="px-3 py-2">Status</th>
              <th className="px-3 py-2">Decision</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filtered.map((recommendation) => (
              <tr key={recommendation.id}>
                <td className="px-3 py-2 font-medium text-slate-900">{recommendation.priority}<br /><span className="text-xs font-normal text-slate-500">{recommendation.confidence} confidence</span></td>
                <td className="px-3 py-2 text-slate-700">{recommendation.recommendation_type}<br /><span className="text-xs text-slate-500">{recommendation.entity_type}</span></td>
                <td className="px-3 py-2 text-slate-700">{recommendation.campaign_name}<br />{recommendation.ad_group_name}</td>
                <td className="px-3 py-2 text-slate-700">{recommendation.customer_search_term}</td>
                <td className="px-3 py-2 text-slate-600">
                  Spend {recommendation.current_metric_snapshot_json.spend ?? recommendation.input_metrics_json.spend} / clicks {recommendation.current_metric_snapshot_json.clicks ?? recommendation.input_metrics_json.clicks} / orders {recommendation.current_metric_snapshot_json.orders ?? recommendation.input_metrics_json.orders}
                  <br />
                  ACOS {recommendation.current_metric_snapshot_json.acos ?? "n/a"} / ROAS {recommendation.current_metric_snapshot_json.roas ?? "n/a"} / CVR {recommendation.current_metric_snapshot_json.cvr ?? "n/a"}
                  <br />
                  <span className="text-slate-500">Rule {recommendation.rule_name}</span>
                </td>
                <td className="min-w-72 px-3 py-2 text-slate-700">
                  {recommendation.explanation_json.summary}
                  <div className="mt-2 flex flex-wrap gap-1 text-xs">
                    <span className="rounded bg-amber-50 px-2 py-1 text-amber-800">Recommendation only</span>
                    <span className="rounded bg-slate-100 px-2 py-1 text-slate-700">Requires human approval</span>
                    <span className="rounded bg-emerald-50 px-2 py-1 text-emerald-800">Does not change Amazon Ads account</span>
                  </div>
                </td>
                <td className="px-3 py-2 text-slate-700">{recommendation.status}</td>
                <td className="px-3 py-2">
                  {recommendation.status === "pending_approval" ? (
                    <div className="flex gap-2">
                      <Button onClick={() => setDecisionTarget({ recommendation, decision: "approve" })} type="button">Approve</Button>
                      <Button className="bg-slate-700" onClick={() => setDecisionTarget({ recommendation, decision: "reject" })} type="button">Reject</Button>
                    </div>
                  ) : (
                    <span className="text-slate-500">Decided</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length ? <p className="p-8 text-sm text-slate-600">No recommendations match the selected filters.</p> : null}
      </div>

      {decisionTarget ? (
        <div className="rounded-md border border-slate-300 bg-white p-5 shadow-sm">
          <p className="font-medium text-slate-900">{decisionTarget.decision === "approve" ? "Approve recommendation" : "Reject recommendation"}</p>
          <p className="mt-1 text-sm text-slate-600">{decisionTarget.recommendation.recommendation_type} for {decisionTarget.recommendation.customer_search_term}. This records a human decision only; no Amazon Ads change is executed.</p>
          <textarea className="mt-3 block h-24 w-full rounded-md border border-slate-300 px-3 py-2 text-sm" onChange={(event) => setNote(event.target.value)} value={note} />
          <div className="mt-3 flex gap-2">
            <Button disabled={!note.trim() || isLoading} onClick={saveDecision} type="button">Save decision</Button>
            <Button className="bg-slate-700" onClick={() => setDecisionTarget(null)} type="button">Cancel</Button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function Filter({ label, onChange, options, value }: { label: string; onChange: (value: string) => void; options: string[]; value: string }) {
  return (
    <label className="space-y-2 text-sm font-medium text-slate-700">
      {label}
      <select className="block rounded-md border border-slate-300 px-3 py-2 text-sm" onChange={(event) => onChange(event.target.value)} value={value}>
        <option value="">All</option>
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}
