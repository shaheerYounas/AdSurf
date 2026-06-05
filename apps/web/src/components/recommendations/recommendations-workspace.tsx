"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardCheck,
  Eye,
  FileDown,
  Filter,
  Info,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ErrorNotice } from "@/components/ui/error-notice";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { Modal } from "@/components/ui/modal";
import { Select } from "@/components/ui/select";
import { defaultWorkspaceId, formatApiError } from "@/lib/api/client";
import { decideRecommendation, getRecommendations, type Recommendation } from "@/lib/api/monitoring";
import { getCachedData, setCachedData } from "@/lib/prefetch";
import { cn, humanize } from "@/lib/utils";
import {
  emptyRecommendationFilters,
  filterRecommendations,
  isRecommendationExportable,
  recommendationActionClass,
  recommendationActionClassLabel,
  recommendationActionTitle,
  recommendationConfidenceLabel,
  recommendationEvidenceChips,
  recommendationExportReason,
  recommendationExportableLabel,
  recommendationFriendlyReason,
  recommendationMetricSnapshot,
  recommendationPriorityLabel,
  recommendationSourceLabel,
  recommendationStatusLabel,
  recommendationSummaryCounts,
  recommendationTechnicalReason,
  recommendationTechnicalSource,
  recommendationTypeLabel,
  type RecommendationActionClass,
  type RecommendationFilters,
} from "@/lib/recommendation-helpers";

const pageSize = 25;

const statusOptions = [
  { value: "", label: "All statuses" },
  { value: "pending_approval", label: "Pending approval" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "superseded", label: "Superseded" },
];

const priorityOptions = [
  { value: "", label: "All priorities" },
  { value: "critical_high", label: "Critical/high" },
  { value: "critical", label: "Critical" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
];

const recommendationTypeOptions = [
  { value: "", label: "All recommendation types" },
  { value: "negative_keywords", label: "Negative keywords" },
  { value: "bid_changes", label: "Bid changes" },
  { value: "add_negative_exact", label: "Add negative exact" },
  { value: "add_negative_phrase", label: "Add negative phrase" },
  { value: "increase_bid", label: "Increase bid" },
  { value: "decrease_bid", label: "Decrease bid" },
  { value: "move_to_exact", label: "Move to exact" },
  { value: "pause_review", label: "Pause review" },
  { value: "watch_lock", label: "Watch only" },
  { value: "keep_running", label: "Keep running" },
  { value: "budget_review", label: "Budget review" },
  { value: "data_quality_review", label: "Data check needed" },
];

const actionClassOptions = [
  { value: "", label: "All action classes" },
  { value: "actionable", label: "Actionable" },
  { value: "review_only", label: "Review-only" },
  { value: "watch_only", label: "Watch-only" },
  { value: "data_quality", label: "Data quality" },
  { value: "budget_review", label: "Budget review" },
];

const exportableOptions = [
  { value: "", label: "All export states" },
  { value: "exportable", label: "Exportable only" },
  { value: "non_exportable", label: "Non-exportable" },
];

const confidenceOptions = [
  { value: "", label: "All confidence levels" },
  { value: "very_high", label: "Very high" },
  { value: "high", label: "High" },
  { value: "medium", label: "Medium" },
  { value: "low", label: "Low" },
  { value: "very_low", label: "Very low" },
  { value: "insufficient_data", label: "Insufficient data" },
];

const quickFilters: Array<{ label: string; patch: Partial<RecommendationFilters> }> = [
  { label: "Pending approval", patch: { status: "pending_approval" } },
  { label: "Actionable", patch: { actionClass: "actionable" } },
  { label: "Exportable", patch: { exportability: "exportable" } },
  { label: "Critical/high", patch: { priority: "critical_high" } },
  { label: "Data checks", patch: { actionClass: "data_quality" } },
  { label: "Negative keywords", patch: { recommendationType: "negative_keywords" } },
  { label: "Bid changes", patch: { recommendationType: "bid_changes" } },
  { label: "Move to exact", patch: { recommendationType: "move_to_exact" } },
];

type DecisionTarget = {
  recommendation: Recommendation;
  decision: "approve" | "reject";
};

export function RecommendationsWorkspace() {
  const workspaceId = defaultWorkspaceId;
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [filters, setFilters] = useState<RecommendationFilters>(emptyRecommendationFilters);
  const [decisionTarget, setDecisionTarget] = useState<DecisionTarget | null>(null);
  const [detailsTarget, setDetailsTarget] = useState<Recommendation | null>(null);
  const [note, setNote] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [errorTitle, setErrorTitle] = useState<string>("Failed to refresh recommendations");
  const [decisionError, setDecisionError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingDecision, setIsSavingDecision] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setPage(1);
  }, [filters]);

  const filtered = useMemo(() => filterRecommendations(recommendations, filters), [filters, recommendations]);
  const summary = useMemo(() => recommendationSummaryCounts(recommendations), [recommendations]);
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * pageSize;
  const visibleRecommendations = filtered.slice(pageStart, pageStart + pageSize);
  const hasActiveFilters = Object.values(filters).some((value) => value !== "");

  async function load(options: { force?: boolean } = {}) {
    setErrorMessage(null);
    setErrorTitle(options.force ? "Failed to refresh recommendations" : "Failed to load recommendations");
    setStatusMessage(null);

    if (!options.force) {
      const cached = getCachedData<Recommendation[]>("recommendations:list");
      if (cached) {
        setRecommendations(cached);
        setIsLoading(false);
        return;
      }
    }

    setIsLoading(true);
    try {
      const data = await getRecommendations(workspaceId);
      setCachedData("recommendations:list", data, 60_000);
      setRecommendations(data);
    } catch (caught) {
      setErrorMessage(formatApiError(caught, "Recommendations could not be loaded."));
    } finally {
      setIsLoading(false);
    }
  }

  async function saveDecision() {
    if (!decisionTarget) return;
    setErrorMessage(null);
    setDecisionError(null);
    setStatusMessage(null);
    setIsSavingDecision(true);
    try {
      const updated = await decideRecommendation(decisionTarget.recommendation.id, decisionTarget.decision, note, workspaceId);
      setRecommendations((current) => {
        const next = current.map((item) => (item.id === updated.id ? updated : item));
        setCachedData("recommendations:list", next, 60_000);
        return next;
      });
      setStatusMessage(`${decisionTarget.decision === "approve" ? "Approval" : "Rejection"} saved. No live Amazon Ads change was made.`);
      setDecisionTarget(null);
      setNote("");
    } catch (caught) {
      const formatted = formatApiError(caught, "Recommendation decision could not be saved.");
      setDecisionError(formatted);
      setErrorTitle("Recommendation decision could not be saved");
      setErrorMessage(formatted);
    } finally {
      setIsSavingDecision(false);
    }
  }

  function updateFilter<K extends keyof RecommendationFilters>(key: K, value: RecommendationFilters[K]) {
    setFilters((current) => ({ ...current, [key]: value }));
  }

  function applyQuickFilter(patch: Partial<RecommendationFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
  }

  function clearFilters() {
    setFilters(emptyRecommendationFilters);
  }

  return (
    <div className="space-y-6">
      <SafetyBanner />

      <section aria-label="Recommendation summary" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SummaryCard icon={ClipboardCheck} label="Total recommendations" value={summary.total} tone="slate" />
        <SummaryCard icon={CheckCircle2} label="Actionable recommendations" value={summary.actionable} tone="emerald" />
        <SummaryCard icon={Info} label="Review-only insights" value={summary.reviewOnly} tone="sky" />
        <SummaryCard icon={FileDown} label="Exportable actions" value={summary.exportable} tone="indigo" />
        <SummaryCard icon={AlertTriangle} label="Pending approval" value={summary.pending} tone="amber" />
        <SummaryCard icon={CheckCircle2} label="Approved" value={summary.approved} tone="emerald" />
        <SummaryCard icon={XCircle} label="Rejected" value={summary.rejected} tone="rose" />
        <SummaryCard icon={ShieldCheck} label="Critical/high priority" value={summary.criticalHigh} tone="red" />
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950/70" aria-label="Recommendation filters">
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold text-slate-900 dark:text-white">
              <SlidersHorizontal aria-hidden="true" size={18} />
              Filters
            </div>
            <div className="flex flex-wrap gap-2">
              <Button disabled={isLoading} onClick={() => load({ force: true })} size="sm" type="button" variant="secondary">
                <RefreshCw aria-hidden="true" size={14} />
                Refresh
              </Button>
              <Button disabled={!hasActiveFilters} onClick={clearFilters} size="sm" type="button" variant="secondary">
                <Filter aria-hidden="true" size={14} />
                Clear filters
              </Button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2" aria-label="Quick filters">
            {quickFilters.map((filter) => (
              <QuickFilterButton
                active={quickFilterIsActive(filters, filter.patch)}
                key={filter.label}
                label={filter.label}
                onClick={() => applyQuickFilter(filter.patch)}
              />
            ))}
          </div>

          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            <Select label="Status" onChange={(value) => updateFilter("status", value)} options={statusOptions} value={filters.status} />
            <Select label="Priority" onChange={(value) => updateFilter("priority", value)} options={priorityOptions} value={filters.priority} />
            <Select label="Recommendation type" onChange={(value) => updateFilter("recommendationType", value)} options={recommendationTypeOptions} value={filters.recommendationType} />
            <Select label="Action class" onChange={(value) => updateFilter("actionClass", value as RecommendationFilters["actionClass"])} options={actionClassOptions} value={filters.actionClass} />
            <Select label="Exportable" onChange={(value) => updateFilter("exportability", value as RecommendationFilters["exportability"])} options={exportableOptions} value={filters.exportability} />
            <Select label="Confidence" onChange={(value) => updateFilter("confidence", value)} options={confidenceOptions} value={filters.confidence} />
            <FilterInput
              icon={Search}
              label="Campaign search"
              onChange={(value) => updateFilter("campaignQuery", value)}
              placeholder="Campaign or ad group"
              value={filters.campaignQuery}
            />
            <FilterInput
              icon={Search}
              label="Search term search"
              onChange={(value) => updateFilter("searchTermQuery", value)}
              placeholder="Search term or target"
              value={filters.searchTermQuery}
            />
            <FilterInput label="Minimum spend" onChange={(value) => updateFilter("minSpend", value)} placeholder="0.00" type="number" value={filters.minSpend} />
            <FilterInput label="Minimum clicks" onChange={(value) => updateFilter("minClicks", value)} placeholder="0" type="number" value={filters.minClicks} />
            <FilterInput label="Minimum orders" onChange={(value) => updateFilter("minOrders", value)} placeholder="0" type="number" value={filters.minOrders} />
          </div>
        </div>

        {statusMessage ? (
          <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100">
            {statusMessage}
          </p>
        ) : null}
        {errorMessage && recommendations.length ? (
          <ErrorNotice className="mt-4" message={errorMessage} onAction={() => load({ force: true })} title={errorTitle} />
        ) : null}
      </section>

      {isLoading && !recommendations.length ? (
        <LoadingSpinner message="Loading recommendations" subtext="Preparing the approval queue and evidence snapshot." />
      ) : errorMessage && !recommendations.length ? (
        <ErrorNotice message={errorMessage} onAction={() => load({ force: true })} title="Failed to load recommendations" />
      ) : !recommendations.length ? (
        <EmptyState title="No recommendations found" message="No recommendations need review yet. Run monitoring analysis after importing a Sponsored Products Search Term report." />
      ) : !filtered.length ? (
        <EmptyState title="No results for current filters" message="Try clearing a quick filter, lowering a minimum metric, or broadening the campaign/search-term text." />
      ) : (
        <RecommendationTable
          filteredCount={filtered.length}
          isLoading={isLoading}
          onApprove={(recommendation) => setDecisionTarget({ recommendation, decision: "approve" })}
          onReject={(recommendation) => setDecisionTarget({ recommendation, decision: "reject" })}
          onViewDetails={setDetailsTarget}
          recommendations={visibleRecommendations}
          totalCount={recommendations.length}
        />
      )}

      {recommendations.length && filtered.length > pageSize ? (
        <Pagination currentPage={currentPage} filteredCount={filtered.length} onPageChange={setPage} pageCount={pageCount} pageSize={pageSize} />
      ) : null}

      <DecisionModal
        decisionTarget={decisionTarget}
        isSaving={isSavingDecision}
        note={note}
        onClose={() => {
          if (!isSavingDecision) {
            setDecisionTarget(null);
            setDecisionError(null);
            setNote("");
          }
        }}
        error={decisionError}
        onNoteChange={setNote}
        onSave={saveDecision}
      />

      <DetailsModal recommendation={detailsTarget} onClose={() => setDetailsTarget(null)} />
    </div>
  );
}

function RecommendationTable({
  filteredCount,
  isLoading,
  onApprove,
  onReject,
  onViewDetails,
  recommendations,
  totalCount,
}: {
  filteredCount: number;
  isLoading: boolean;
  onApprove: (recommendation: Recommendation) => void;
  onReject: (recommendation: Recommendation) => void;
  onViewDetails: (recommendation: Recommendation) => void;
  recommendations: Recommendation[];
  totalCount: number;
}) {
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white shadow-sm dark:border-white/10 dark:bg-slate-950/70" aria-label="Recommendation approval queue">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-white/10">
        <div>
          <h2 className="text-sm font-semibold text-slate-950 dark:text-white">Recommendation review queue</h2>
          <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Showing {filteredCount.toLocaleString("en-US")} of {totalCount.toLocaleString("en-US")} recommendations. No live Amazon Ads changes have been made.
          </p>
        </div>
        {isLoading ? <LoadingSpinner iconOnly size="sm" /> : null}
      </div>

      <div className="overflow-x-auto">
        <table className="min-w-[1360px] table-fixed divide-y divide-slate-200 text-left text-sm dark:divide-white/10">
          <thead className="sticky top-0 z-10 bg-slate-50 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:bg-slate-900 dark:text-slate-400">
            <tr>
              <th className="w-28 px-4 py-3">Priority</th>
              <th className="w-72 px-4 py-3">Recommendation</th>
              <th className="w-48 px-4 py-3">Search term</th>
              <th className="w-56 px-4 py-3">Campaign / Ad group</th>
              <th className="w-64 px-4 py-3">Evidence</th>
              <th className="w-44 px-4 py-3">Recommended action</th>
              <th className="w-32 px-4 py-3">Confidence</th>
              <th className="w-28 px-4 py-3">Exportable</th>
              <th className="w-36 px-4 py-3">Status</th>
              <th className="w-52 px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-white/5">
            {recommendations.map((recommendation) => (
              <RecommendationRow
                key={recommendation.id}
                onApprove={onApprove}
                onReject={onReject}
                onViewDetails={onViewDetails}
                recommendation={recommendation}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RecommendationRow({
  onApprove,
  onReject,
  onViewDetails,
  recommendation,
}: {
  onApprove: (recommendation: Recommendation) => void;
  onReject: (recommendation: Recommendation) => void;
  onViewDetails: (recommendation: Recommendation) => void;
  recommendation: Recommendation;
}) {
  const actionClass = recommendationActionClass(recommendation);
  const pending = isPending(recommendation.status);

  return (
    <tr className="align-top transition hover:bg-slate-50/80 dark:hover:bg-white/[0.03]">
      <td className="px-4 py-4">
        <Badge className={priorityClass(recommendation.priority)}>{recommendationPriorityLabel(recommendation.priority)}</Badge>
      </td>
      <td className="px-4 py-4">
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            <Badge className={actionClassClass(actionClass)}>{recommendationActionClassLabel(actionClass)}</Badge>
            <Badge className="border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300">
              {recommendationSourceLabel(recommendation)}
            </Badge>
          </div>
          <p className="font-semibold leading-5 text-slate-950 dark:text-white">{recommendationTypeLabel(recommendation)}</p>
          <p
            className="text-xs leading-5 text-slate-600 dark:text-slate-300"
            style={{ display: "-webkit-box", WebkitLineClamp: 3, WebkitBoxOrient: "vertical", overflow: "hidden" }}
          >
            {recommendationFriendlyReason(recommendation)}
          </p>
        </div>
      </td>
      <td className="px-4 py-4">
        <p className="whitespace-normal break-normal text-sm font-semibold leading-5 text-slate-900 dark:text-white" title={recommendation.customer_search_term ?? recommendation.targeting ?? ""}>
          {recommendation.customer_search_term || recommendation.targeting || "—"}
        </p>
        {recommendation.targeting && recommendation.targeting !== recommendation.customer_search_term ? (
          <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400" title={recommendation.targeting}>
            Target: {recommendation.targeting}
          </p>
        ) : null}
      </td>
      <td className="px-4 py-4">
        <p className="truncate font-medium text-slate-900 dark:text-white" title={recommendation.campaign_name ?? ""}>
          {recommendation.campaign_name || "Account-level"}
        </p>
        <p className="mt-1 truncate text-xs text-slate-500 dark:text-slate-400" title={recommendation.ad_group_name ?? ""}>
          {recommendation.ad_group_name || "No ad group"}
        </p>
      </td>
      <td className="px-4 py-4">
        <MetricChips recommendation={recommendation} compact />
      </td>
      <td className="px-4 py-4">
        <p className="font-semibold text-slate-900 dark:text-white">{recommendationTypeLabel(recommendation)}</p>
        <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-slate-400">{isRecommendationExportable(recommendation) ? "Manual export after approval" : "Review only"}</p>
      </td>
      <td className="px-4 py-4">
        <Badge className={confidenceClass(recommendation.confidence)}>{recommendationConfidenceLabel(recommendation.confidence)}</Badge>
      </td>
      <td className="px-4 py-4">
        <Badge className={isRecommendationExportable(recommendation) ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100" : "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300"}>
          {recommendationExportableLabel(recommendation)}
        </Badge>
      </td>
      <td className="px-4 py-4">
        <Badge className={statusClass(recommendation.status)}>{recommendationStatusLabel(recommendation.status)}</Badge>
      </td>
      <td className="px-4 py-4">
        <div className="flex flex-wrap gap-2">
          {pending ? (
            <>
              <Button onClick={() => onApprove(recommendation)} size="sm" type="button" variant="success">
                <CheckCircle2 aria-hidden="true" size={14} />
                Approve
              </Button>
              <Button onClick={() => onReject(recommendation)} size="sm" type="button" variant="danger">
                <XCircle aria-hidden="true" size={14} />
                Reject
              </Button>
            </>
          ) : (
            <Button disabled size="sm" title="Decision changes are not supported by the current approval API." type="button" variant="secondary">
              Change decision
            </Button>
          )}
          <Button onClick={() => onViewDetails(recommendation)} size="sm" type="button" variant="secondary">
            <Eye aria-hidden="true" size={14} />
            View details
          </Button>
        </div>
      </td>
    </tr>
  );
}

function DecisionModal({
  decisionTarget,
  error,
  isSaving,
  note,
  onClose,
  onNoteChange,
  onSave,
}: {
  decisionTarget: DecisionTarget | null;
  error: string | null;
  isSaving: boolean;
  note: string;
  onClose: () => void;
  onNoteChange: (value: string) => void;
  onSave: () => void;
}) {
  const recommendation = decisionTarget?.recommendation ?? null;
  const decisionLabel = decisionTarget?.decision === "approve" ? "Approve" : "Reject";

  return (
    <Modal
      open={decisionTarget !== null}
      onClose={onClose}
      title={recommendation ? `${decisionLabel} recommendation` : "Recommendation decision"}
      description={recommendation ? recommendationActionTitle(recommendation) : undefined}
      size="lg"
    >
      {recommendation ? (
        <div className="space-y-4">
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100">
            <div className="flex gap-2">
              <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0" size={16} />
              <p>
                No Amazon Ads API call will be made. This records a human decision only; approved actions must be exported and uploaded manually.
              </p>
            </div>
          </div>

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">Evidence</p>
            <div className="mt-2">
              <MetricChips recommendation={recommendation} />
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-3">
            <DecisionFact label="Risk note" value={riskNote(recommendation)} />
            <DecisionFact label="Exportable" value={`${recommendationExportableLabel(recommendation)}. ${recommendationExportReason(recommendation)}`} />
            <DecisionFact label="Required approval" value="A note is required before this decision is saved to the audit trail." />
          </div>

          <label className="block">
            <span className="mb-2 block text-xs font-bold text-slate-600 dark:text-slate-300">Decision note</span>
            <textarea
              className="block h-28 w-full rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-950 outline-none transition hover:border-slate-300 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100 dark:border-white/10 dark:bg-white/5 dark:text-white dark:hover:border-white/20 dark:focus:border-indigo-400 dark:focus:ring-indigo-400/20"
              onChange={(event) => onNoteChange(event.target.value)}
              placeholder="Add a note explaining your decision..."
              value={note}
            />
          </label>

          <div className="flex flex-wrap gap-2">
            <Button disabled={!note.trim() || isSaving} onClick={onSave} type="button" variant={decisionTarget?.decision === "approve" ? "success" : "danger"}>
              {isSaving ? <Loader2 aria-hidden="true" className="animate-spin" size={16} /> : decisionTarget?.decision === "approve" ? <CheckCircle2 aria-hidden="true" size={16} /> : <XCircle aria-hidden="true" size={16} />}
              {isSaving ? "Saving..." : `Confirm ${decisionLabel.toLowerCase()}`}
            </Button>
            <Button disabled={isSaving} onClick={onClose} type="button" variant="secondary">
              Cancel
            </Button>
          </div>
          {error ? (
            <p className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm font-medium text-rose-800 dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100" role="alert">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </Modal>
  );
}

function DetailsModal({ recommendation, onClose }: { recommendation: Recommendation | null; onClose: () => void }) {
  return (
    <Modal
      open={recommendation !== null}
      onClose={onClose}
      title={recommendation ? recommendationActionTitle(recommendation) : "Recommendation details"}
      description="Advanced details are kept here so the queue stays focused on seller decisions."
      size="xl"
    >
      {recommendation ? (
        <div className="space-y-5">
          <div className="rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-3 text-sm text-indigo-900 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100">
            <div className="flex gap-2">
              <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0" size={16} />
              <p>No live Amazon Ads change was made. Approval updates AdSurf state and audit records only.</p>
            </div>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <DetailFact label="Full campaign name" value={recommendation.campaign_name || "Account-level"} />
            <DetailFact label="Full ad group name" value={recommendation.ad_group_name || "No ad group"} />
            <DetailFact label="Search term" value={recommendation.customer_search_term || "—"} />
            <DetailFact label="Targeting" value={recommendation.targeting || "—"} />
          </div>

          <section>
            <h3 className="text-sm font-semibold text-slate-950 dark:text-white">Metric snapshot</h3>
            <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {recommendationMetricSnapshot(recommendation).map((chip) => (
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 dark:border-white/10 dark:bg-white/5" key={chip.key}>
                  <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{chip.label}</p>
                  <p className="mt-1 font-semibold tabular-nums text-slate-950 dark:text-white">{chip.value}</p>
                </div>
              ))}
            </div>
          </section>

          <div className="grid gap-3 md:grid-cols-2">
            <DetailFact label="User-friendly reason" value={recommendationFriendlyReason(recommendation)} />
            <DetailFact label="Raw technical reason" value={recommendationTechnicalReason(recommendation)} />
            <DetailFact label="Rule name" value={recommendation.rule_name || "—"} />
            <DetailFact label="Model/source" value={recommendationTechnicalSource(recommendation)} />
            <DetailFact label="Recommendation ID" value={recommendation.id} />
            <DetailFact label="Upload/import ID" value={recommendation.monitoring_import_id || recommendation.account_import_id || "—"} />
            <DetailFact label="Export eligibility" value={recommendationExportableLabel(recommendation)} />
            <DetailFact label="Why exportable or not" value={recommendationExportReason(recommendation)} />
          </div>

          <section className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
            <h3 className="text-sm font-semibold text-slate-950 dark:text-white">Approval / rejection history</h3>
            {recommendation.decision_note || recommendation.decided_at || recommendation.decided_by ? (
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
                <HistoryItem label="Status" value={recommendationStatusLabel(recommendation.status)} />
                <HistoryItem label="Actor" value={recommendation.decided_by || "Recorded by API"} />
                <HistoryItem label="Decision time" value={formatDateTime(recommendation.decided_at)} />
                <div className="sm:col-span-3">
                  <HistoryItem label="Decision note" value={recommendation.decision_note || "No note returned with this record."} />
                </div>
              </dl>
            ) : (
              <p className="mt-2 text-sm text-slate-600 dark:text-slate-300">No approval decision has been recorded yet.</p>
            )}
          </section>

          <details className="rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-white/10 dark:bg-white/5">
            <summary className="cursor-pointer text-sm font-semibold text-slate-950 dark:text-white">Advanced technical payload</summary>
            <div className="mt-3 grid gap-3 lg:grid-cols-2">
              <JsonBlock label="Evidence JSON" value={recommendation.evidence_json} />
              <JsonBlock label="Proposed action JSON" value={recommendation.proposed_action_json} />
              <JsonBlock label="Explanation JSON" value={recommendation.explanation_json} />
              <JsonBlock label="Approval boundary" value={recommendation.approval_boundary ?? { requires_human_approval: true, executes_live_amazon_change: false }} />
            </div>
          </details>
        </div>
      ) : null}
    </Modal>
  );
}

function SafetyBanner() {
  return (
    <section className="rounded-lg border border-emerald-200 bg-emerald-50 px-5 py-4 text-emerald-950 shadow-sm dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 gap-3">
          <ShieldCheck aria-hidden="true" className="mt-0.5 shrink-0" size={20} />
          <div>
            <h2 className="text-sm font-semibold">No live Amazon Ads changes have been made.</h2>
            <p className="mt-1 text-sm leading-6 text-emerald-800 dark:text-emerald-100/85">
              Approved actions must be exported and uploaded manually.
            </p>
          </div>
        </div>
        <Badge className="self-start border-emerald-300 bg-white/70 text-emerald-800 dark:border-emerald-300/30 dark:bg-emerald-300/10 dark:text-emerald-100 sm:self-center">
          Manual export only
        </Badge>
      </div>
    </section>
  );
}

function SummaryCard({ icon: Icon, label, tone, value }: { icon: typeof ClipboardCheck; label: string; tone: string; value: number }) {
  return (
    <article className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm dark:border-white/10 dark:bg-slate-950/70">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums text-slate-950 dark:text-white">{value.toLocaleString("en-US")}</p>
        </div>
        <span className={cn("inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border", summaryIconClass(tone))}>
          <Icon aria-hidden="true" size={17} />
        </span>
      </div>
    </article>
  );
}

function MetricChips({ compact = false, recommendation }: { compact?: boolean; recommendation: Recommendation }) {
  const chips = recommendationEvidenceChips(recommendation);
  return (
    <div className="flex flex-wrap gap-1.5">
      {chips.map((chip) => (
        <span
          className={cn(
            "inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 font-medium text-slate-700 dark:border-white/10 dark:bg-white/5 dark:text-slate-200",
            compact ? "px-2 py-1 text-[11px]" : "px-2.5 py-1.5 text-xs",
          )}
          key={chip.key}
        >
          <span className="text-slate-500 dark:text-slate-400">{chip.label}</span>
          <span className="tabular-nums text-slate-950 dark:text-white">{chip.value}</span>
        </span>
      ))}
    </div>
  );
}

function FilterInput({
  icon: Icon,
  label,
  onChange,
  placeholder,
  type = "text",
  value,
}: {
  icon?: typeof Search;
  label: string;
  onChange: (value: string) => void;
  placeholder: string;
  type?: "text" | "number";
  value: string;
}) {
  return (
    <label className="block min-w-[10.5rem]">
      <span className="mb-2 block text-xs font-bold text-slate-600 dark:text-slate-300">{label}</span>
      <span className="relative block">
        {Icon ? <Icon aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={15} /> : null}
        <input
          className={cn(
            "min-h-12 w-full rounded-2xl border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-950 shadow-sm outline-none transition",
            "hover:border-indigo-200 hover:bg-slate-50 focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100",
            "dark:border-white/10 dark:bg-slate-950/70 dark:text-white dark:hover:border-indigo-300/35 dark:hover:bg-white/5 dark:focus:border-indigo-300 dark:focus:ring-indigo-400/20",
            Icon && "pl-9",
          )}
          min={type === "number" ? 0 : undefined}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          step={type === "number" ? "any" : undefined}
          type={type}
          value={value}
        />
      </span>
    </label>
  );
}

function QuickFilterButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      className={cn(
        "min-h-9 rounded-full border px-3 text-xs font-semibold transition",
        active
          ? "border-indigo-300 bg-indigo-50 text-indigo-800 dark:border-indigo-300/40 dark:bg-indigo-300/15 dark:text-indigo-100"
          : "border-slate-200 bg-slate-50 text-slate-600 hover:border-slate-300 hover:text-slate-900 dark:border-white/10 dark:bg-white/5 dark:text-slate-300 dark:hover:border-white/20 dark:hover:text-white",
      )}
      onClick={onClick}
      type="button"
    >
      {label}
    </button>
  );
}

function EmptyState({ message, title }: { message: string; title: string }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-8 text-center shadow-sm dark:border-white/10 dark:bg-slate-950/70">
      <Info aria-hidden="true" className="mx-auto text-slate-400 dark:text-slate-500" size={24} />
      <h2 className="mt-3 text-base font-semibold text-slate-950 dark:text-white">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-600 dark:text-slate-300">{message}</p>
    </section>
  );
}

function Pagination({
  currentPage,
  filteredCount,
  onPageChange,
  pageCount,
  pageSize,
}: {
  currentPage: number;
  filteredCount: number;
  onPageChange: (page: number) => void;
  pageCount: number;
  pageSize: number;
}) {
  const start = (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, filteredCount);

  return (
    <nav className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm dark:border-white/10 dark:bg-slate-950/70 sm:flex-row sm:items-center sm:justify-between" aria-label="Recommendation pagination">
      <p className="text-slate-600 dark:text-slate-300">
        Showing {start.toLocaleString("en-US")} to {end.toLocaleString("en-US")} of {filteredCount.toLocaleString("en-US")}
      </p>
      <div className="flex gap-2">
        <Button disabled={currentPage <= 1} onClick={() => onPageChange(currentPage - 1)} size="sm" type="button" variant="secondary">
          Previous
        </Button>
        <span className="inline-flex min-h-9 items-center rounded-full border border-slate-200 px-3 text-xs font-semibold text-slate-600 dark:border-white/10 dark:text-slate-300">
          Page {currentPage} of {pageCount}
        </span>
        <Button disabled={currentPage >= pageCount} onClick={() => onPageChange(currentPage + 1)} size="sm" type="button" variant="secondary">
          Next
        </Button>
      </div>
    </nav>
  );
}

function Badge({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cn("inline-flex whitespace-nowrap rounded-md border px-2 py-1 text-xs font-semibold", className)}>{children}</span>;
}

function DecisionFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5">
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-sm leading-5 text-slate-800 dark:text-slate-100">{value}</p>
    </div>
  );
}

function DetailFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-white/10 dark:bg-white/5">
      <p className="text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-1 break-words text-sm leading-6 text-slate-900 dark:text-white">{value}</p>
    </div>
  );
}

function HistoryItem({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</dt>
      <dd className="mt-1 break-words text-sm text-slate-900 dark:text-white">{value}</dd>
    </div>
  );
}

function JsonBlock({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="min-w-0">
      <p className="mb-2 text-xs font-semibold text-slate-500 dark:text-slate-400">{label}</p>
      <pre className="max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white p-3 text-xs leading-5 text-slate-700 dark:border-white/10 dark:bg-slate-950 dark:text-slate-200">
        {JSON.stringify(value ?? {}, null, 2)}
      </pre>
    </div>
  );
}

function quickFilterIsActive(filters: RecommendationFilters, patch: Partial<RecommendationFilters>) {
  return Object.entries(patch).every(([key, value]) => filters[key as keyof RecommendationFilters] === value);
}

function isPending(status: string) {
  return status === "pending" || status === "pending_approval";
}

function riskNote(recommendation: Recommendation): string {
  const priority = recommendationPriorityLabel(recommendation.priority);
  const risk = recommendation.risk_level ? humanize(recommendation.risk_level) : priority;
  if (recommendationActionClass(recommendation) === "data_quality") {
    return "Data quality risk. Review the metrics before approving any optimization.";
  }
  if (!isRecommendationExportable(recommendation)) {
    return `${risk} priority review-only item. Approval records intent but does not create an export action.`;
  }
  return `${risk} priority recommendation. Approval only makes it eligible for a manual export.`;
}

function formatDateTime(value?: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function summaryIconClass(tone: string) {
  const classes: Record<string, string> = {
    slate: "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-200",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100",
    sky: "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-300/25 dark:bg-sky-300/10 dark:text-sky-100",
    indigo: "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100",
    amber: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100",
    rose: "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100",
    red: "border-red-200 bg-red-50 text-red-700 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100",
  };
  return classes[tone] ?? classes.slate;
}

function priorityClass(priority: string) {
  if (priority === "critical") return "border-red-200 bg-red-50 text-red-700 dark:border-red-300/25 dark:bg-red-300/10 dark:text-red-100";
  if (priority === "high") return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100";
  if (priority === "medium") return "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-300/25 dark:bg-sky-300/10 dark:text-sky-100";
  return "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300";
}

function confidenceClass(confidence: string) {
  if (confidence === "very_high" || confidence === "high") return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100";
  if (confidence === "medium") return "border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-300/25 dark:bg-indigo-300/10 dark:text-indigo-100";
  if (confidence === "insufficient_data") return "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100";
  return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100";
}

function statusClass(status: string) {
  if (status === "approved") return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100";
  if (status === "rejected") return "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100";
  if (isPending(status)) return "border-violet-200 bg-violet-50 text-violet-700 dark:border-violet-300/25 dark:bg-violet-300/10 dark:text-violet-100";
  return "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300";
}

function actionClassClass(actionClass: RecommendationActionClass) {
  if (actionClass === "actionable") return "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-300/25 dark:bg-emerald-300/10 dark:text-emerald-100";
  if (actionClass === "data_quality") return "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-300/25 dark:bg-rose-300/10 dark:text-rose-100";
  if (actionClass === "budget_review") return "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-300/25 dark:bg-amber-300/10 dark:text-amber-100";
  if (actionClass === "watch_only") return "border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-300/25 dark:bg-sky-300/10 dark:text-sky-100";
  return "border-slate-200 bg-slate-50 text-slate-600 dark:border-white/10 dark:bg-white/5 dark:text-slate-300";
}
