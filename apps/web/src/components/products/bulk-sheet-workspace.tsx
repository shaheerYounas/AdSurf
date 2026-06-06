"use client";

/**
 * Bulk Sheet Workspace
 *
 * Upload an Amazon Bulk Operations XLSX → parse → show full account snapshot.
 * Three tabs: Campaigns / Keywords / Product Ads
 *
 * Stateless from the backend's perspective: the file is parsed on upload and
 * the snapshot is held in component state only. Nothing is persisted.
 */

import { useState, useCallback, useRef } from "react";
import { parseBulkSheet, type BulkSheetSnapshot, type BulkCampaign, type BulkKeyword } from "@/lib/api/bulk-sheet";
import { formatApiError, defaultWorkspaceId } from "@/lib/api/client";
import { detectAmazonFileType } from "@/lib/amazon-file-detector";

// ─── Tab type ───────────────────────────────────────────────────────────────

type Tab = "campaigns" | "ad_groups" | "keywords" | "targets" | "product_ads";

// ─── Helpers ────────────────────────────────────────────────────────────────

function StatusDot({ status }: { status: string }) {
  const s = status.toLowerCase();
  if (s === "enabled") return <span className="inline-block w-2 h-2 rounded-full bg-green-500 mr-1.5" title="Enabled" />;
  if (s === "paused") return <span className="inline-block w-2 h-2 rounded-full bg-amber-400 mr-1.5" title="Paused" />;
  return <span className="inline-block w-2 h-2 rounded-full bg-gray-300 mr-1.5" title={status} />;
}

function MatchTypeBadge({ matchType }: { matchType: string }) {
  const mt = matchType.toLowerCase();
  const cls =
    mt === "exact"
      ? "bg-blue-100 text-blue-800 border border-blue-200"
      : mt === "phrase"
        ? "bg-purple-100 text-purple-800 border border-purple-200"
        : "bg-gray-100 text-gray-700 border border-gray-200";
  return (
    <span className={`inline-block px-1.5 py-0.5 rounded text-[10px] font-medium uppercase tracking-wide ${cls}`}>
      {matchType || "—"}
    </span>
  );
}

function BidCell({ bid }: { bid: number | null }) {
  if (bid == null) return <span className="text-gray-400">—</span>;
  return <span>${Number(bid).toFixed(2)}</span>;
}

// ─── Stats Bar ──────────────────────────────────────────────────────────────

function StatsBar({ snap }: { snap: BulkSheetSnapshot }) {
  const { stats } = snap;
  const items = [
    { label: "Campaigns", value: stats.total_campaigns, sub: `${stats.active_campaigns} active` },
    { label: "Ad Groups", value: stats.total_ad_groups },
    { label: "Keywords", value: stats.total_keywords },
    { label: "Targets", value: stats.total_targets },
    { label: "Product Ads", value: stats.total_product_ads },
    { label: "Neg. Keywords", value: stats.total_negative_keywords },
  ];
  return (
    <div className="grid grid-cols-3 sm:grid-cols-6 gap-3 mb-6">
      {items.map(({ label, value, sub }) => (
        <div key={label} className="rounded-lg border border-gray-200 bg-white px-4 py-3 text-center shadow-sm">
          <p className="text-2xl font-semibold text-gray-900">{value.toLocaleString()}</p>
          <p className="text-xs text-gray-500 mt-0.5">{label}</p>
          {sub && <p className="text-[10px] text-green-600 mt-0.5">{sub}</p>}
        </div>
      ))}
    </div>
  );
}

// ─── Campaigns Tab ──────────────────────────────────────────────────────────

function CampaignsTab({ campaigns }: { campaigns: BulkCampaign[] }) {
  if (!campaigns.length)
    return <p className="text-sm text-gray-500 py-8 text-center">No campaigns found in this file.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-2.5">Status</th>
            <th className="px-4 py-2.5">Campaign Name</th>
            <th className="px-4 py-2.5">Daily Budget</th>
            <th className="px-4 py-2.5">Targeting</th>
            <th className="px-4 py-2.5">Bidding Strategy</th>
            <th className="px-4 py-2.5">Start Date</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {campaigns.map((c, i) => (
            <tr key={c.campaign_id || i} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-2.5">
                <StatusDot status={c.status} />
                <span className="text-gray-600 capitalize text-xs">{c.status}</span>
              </td>
              <td className="px-4 py-2.5 font-medium text-gray-900 max-w-xs truncate">{c.name}</td>
              <td className="px-4 py-2.5 text-gray-700">
                {c.daily_budget != null ? `$${Number(c.daily_budget).toFixed(2)}` : "—"}
              </td>
              <td className="px-4 py-2.5 text-gray-500 capitalize">{c.targeting_type || "—"}</td>
              <td className="px-4 py-2.5 text-gray-500">{c.bidding_strategy || "—"}</td>
              <td className="px-4 py-2.5 text-gray-500">{c.start_date || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Keywords Tab ────────────────────────────────────────────────────────────

function KeywordsTab({ keywords }: { keywords: BulkKeyword[] }) {
  const [search, setSearch] = useState("");
  const [filterMatchType, setFilterMatchType] = useState<"" | "exact" | "phrase" | "broad">("");

  const filtered = keywords.filter((kw) => {
    const textOk = !search || kw.keyword_text.toLowerCase().includes(search.toLowerCase());
    const mtOk = !filterMatchType || kw.match_type.toLowerCase() === filterMatchType;
    return textOk && mtOk;
  });

  if (!keywords.length)
    return <p className="text-sm text-gray-500 py-8 text-center">No keywords found in this file.</p>;

  return (
    <div className="space-y-3">
      <div className="flex gap-3 flex-wrap">
        <input
          type="text"
          placeholder="Search keywords..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 min-w-[180px] rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        />
        <select
          value={filterMatchType}
          onChange={(e) => setFilterMatchType(e.target.value as "" | "exact" | "phrase" | "broad")}
          className="rounded-md border border-gray-300 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <option value="">All match types</option>
          <option value="exact">Exact</option>
          <option value="phrase">Phrase</option>
          <option value="broad">Broad</option>
        </select>
        <span className="self-center text-xs text-gray-500">{filtered.length.toLocaleString()} keywords</span>
      </div>
      <div className="overflow-x-auto rounded-md border border-gray-200">
        <table className="min-w-full text-sm border-collapse">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
              <th className="px-4 py-2.5">Status</th>
              <th className="px-4 py-2.5">Keyword</th>
              <th className="px-4 py-2.5">Match Type</th>
              <th className="px-4 py-2.5 text-right">Bid</th>
              <th className="px-4 py-2.5">Campaign</th>
              <th className="px-4 py-2.5">Ad Group</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {filtered.slice(0, 500).map((kw, i) => (
              <tr key={kw.keyword_id || i} className="hover:bg-gray-50 transition-colors">
                <td className="px-4 py-2">
                  <StatusDot status={kw.status} />
                </td>
                <td className="px-4 py-2 font-medium text-gray-900">{kw.keyword_text}</td>
                <td className="px-4 py-2"><MatchTypeBadge matchType={kw.match_type} /></td>
                <td className="px-4 py-2 text-right tabular-nums text-gray-700"><BidCell bid={kw.bid} /></td>
                <td className="px-4 py-2 text-gray-500 max-w-[180px] truncate">{kw.campaign_name}</td>
                <td className="px-4 py-2 text-gray-500 max-w-[160px] truncate">{kw.ad_group_name}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length > 500 && (
          <p className="text-xs text-gray-500 text-center py-2 border-t border-gray-100">
            Showing first 500 of {filtered.length.toLocaleString()} keywords.
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Ad Groups Tab ───────────────────────────────────────────────────────────

function AdGroupsTab({ adGroups }: { adGroups: BulkSheetSnapshot["ad_groups"] }) {
  if (!adGroups.length)
    return <p className="text-sm text-gray-500 py-8 text-center">No ad groups found in this file.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
            <th className="px-4 py-2.5">Status</th>
            <th className="px-4 py-2.5">Ad Group Name</th>
            <th className="px-4 py-2.5 text-right">Default Bid</th>
            <th className="px-4 py-2.5">Campaign</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {adGroups.map((ag, i) => (
            <tr key={ag.ad_group_id || i} className="hover:bg-gray-50 transition-colors">
              <td className="px-4 py-2.5">
                <StatusDot status={ag.status} />
                <span className="text-gray-600 capitalize text-xs">{ag.status}</span>
              </td>
              <td className="px-4 py-2.5 font-medium text-gray-900">{ag.name}</td>
              <td className="px-4 py-2.5 text-right tabular-nums text-gray-700"><BidCell bid={ag.default_bid} /></td>
              <td className="px-4 py-2.5 text-gray-500 max-w-xs truncate">{ag.campaign_name}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ─── Upload Zone ─────────────────────────────────────────────────────────────

function UploadZone({
  onFile,
  isLoading,
}: {
  onFile: (file: File) => void;
  isLoading: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const f = e.dataTransfer.files[0];
      if (f) onFile(f);
    },
    [onFile],
  );

  return (
    <div
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={() => !isLoading && inputRef.current?.click()}
      className={`border-2 border-dashed rounded-xl p-12 text-center cursor-pointer transition-colors select-none
        ${dragging ? "border-indigo-400 bg-indigo-50" : "border-gray-300 bg-gray-50 hover:border-gray-400 hover:bg-gray-100"}
        ${isLoading ? "pointer-events-none opacity-60" : ""}`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.csv"
        className="hidden"
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onFile(f); e.target.value = ""; }}
      />
      {isLoading ? (
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 rounded-full border-2 border-indigo-500 border-t-transparent animate-spin" />
          <p className="text-sm text-gray-600">Parsing bulk sheet…</p>
        </div>
      ) : (
        <>
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-indigo-100">
            <svg className="h-7 w-7 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
            </svg>
          </div>
          <p className="text-base font-semibold text-gray-800">Drop your Bulk Operations file here</p>
          <p className="mt-1 text-sm text-gray-500">
            or <span className="text-indigo-600 font-medium">browse</span> to upload
          </p>
          <p className="mt-3 text-xs text-gray-400">
            Amazon Seller Central → Advertising → Bulk Operations → Download (.xlsx)
          </p>
          <p className="mt-1 text-xs text-gray-400">
            Filename pattern: <code className="font-mono bg-gray-200 px-1 rounded">bulk-&#123;accountId&#125;-&#123;date&#125;.xlsx</code>
          </p>
        </>
      )}
    </div>
  );
}

// ─── Wrong File Banner ────────────────────────────────────────────────────────

function WrongFileBanner({ hint, onDismiss }: { hint: string; onDismiss: () => void }) {
  return (
    <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 flex items-start gap-3">
      <span className="text-amber-500 text-xl flex-shrink-0">⚠</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-amber-900">Wrong workflow</p>
        <p className="text-sm text-amber-800 mt-0.5">{hint}</p>
      </div>
      <button onClick={onDismiss} className="text-amber-500 hover:text-amber-700 text-sm flex-shrink-0">
        Dismiss
      </button>
    </div>
  );
}

// ─── Main component ──────────────────────────────────────────────────────────

export function BulkSheetWorkspace() {
  const [workspaceId] = useState(defaultWorkspaceId);
  const [snapshot, setSnapshot] = useState<BulkSheetSnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [wrongFileHint, setWrongFileHint] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("campaigns");

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setWrongFileHint(null);

      // Client-side file type check — surface misrouted files immediately
      const detection = detectAmazonFileType(file.name);
      if (
        detection.type === "SP_SEARCH_TERM_REPORT" ||
        detection.type === "SP_TARGETING_REPORT" ||
        detection.type === "SP_CAMPAIGN_REPORT" ||
        detection.type === "SP_ADVERTISED_PRODUCT" ||
        detection.type === "SB_REPORT" ||
        detection.type === "SD_REPORT"
      ) {
        setWrongFileHint(detection.hint);
        return;
      }

      setIsLoading(true);
      try {
        const snap = await parseBulkSheet(workspaceId, file);
        setSnapshot(snap);
        setActiveTab("campaigns");
      } catch (err) {
        setError(formatApiError(err));
      } finally {
        setIsLoading(false);
      }
    },
    [workspaceId],
  );

  const reset = useCallback(() => {
    setSnapshot(null);
    setError(null);
    setWrongFileHint(null);
  }, []);

  const TABS: Array<{ id: Tab; label: string; count?: number }> = snapshot
    ? [
        { id: "campaigns", label: "Campaigns", count: snapshot.campaigns.length },
        { id: "ad_groups", label: "Ad Groups", count: snapshot.ad_groups.length },
        { id: "keywords", label: "Keywords", count: snapshot.keywords.length },
        { id: "targets", label: "Targets", count: snapshot.targets.length },
        { id: "product_ads", label: "Product Ads", count: snapshot.product_ads.length },
      ]
    : [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold text-gray-900">Bulk Sheet Viewer</h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Inspect your current Amazon account structure — campaigns, ad groups, and keyword bids.
          </p>
        </div>
        {snapshot && (
          <button
            onClick={reset}
            className="text-sm text-gray-500 hover:text-gray-800 underline underline-offset-2"
          >
            Upload another file
          </button>
        )}
      </div>

      {wrongFileHint && (
        <WrongFileBanner hint={wrongFileHint} onDismiss={() => setWrongFileHint(null)} />
      )}

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <span className="font-semibold">Error: </span>{error}
        </div>
      )}

      {!snapshot && (
        <UploadZone onFile={handleFile} isLoading={isLoading} />
      )}

      {snapshot && (
        <div className="space-y-5">
          {/* Header row */}
          <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm text-gray-600">
            <span className="font-medium text-gray-800">{snapshot.filename}</span>
            {snapshot.account_id && (
              <span>Account: <code className="font-mono text-xs bg-gray-100 px-1.5 py-0.5 rounded">{snapshot.account_id}</code></span>
            )}
            {snapshot.date_range_start && snapshot.date_range_end && (
              <span>{snapshot.date_range_start} → {snapshot.date_range_end}</span>
            )}
          </div>

          {snapshot.warnings.length > 0 && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {snapshot.warnings.map((w, i) => <p key={i}>{w}</p>)}
            </div>
          )}

          <StatsBar snap={snapshot} />

          {/* Tab bar */}
          <div className="border-b border-gray-200 flex gap-1 overflow-x-auto">
            {TABS.map(({ id, label, count }) => (
              <button
                key={id}
                onClick={() => setActiveTab(id)}
                className={`px-4 py-2 text-sm font-medium whitespace-nowrap border-b-2 transition-colors
                  ${activeTab === id
                    ? "border-indigo-600 text-indigo-700"
                    : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
                  }`}
              >
                {label}
                {count != null && (
                  <span className="ml-1.5 rounded-full bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600">
                    {count.toLocaleString()}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="rounded-lg border border-gray-200 bg-white overflow-hidden shadow-sm">
            {activeTab === "campaigns" && <CampaignsTab campaigns={snapshot.campaigns} />}
            {activeTab === "ad_groups" && <AdGroupsTab adGroups={snapshot.ad_groups} />}
            {activeTab === "keywords" && <KeywordsTab keywords={snapshot.keywords} />}
            {activeTab === "targets" && (
              snapshot.targets.length === 0
                ? <p className="text-sm text-gray-500 py-8 text-center">No product targets in this file.</p>
                : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-2.5">Status</th>
                          <th className="px-4 py-2.5">Expression</th>
                          <th className="px-4 py-2.5 text-right">Bid</th>
                          <th className="px-4 py-2.5">Campaign</th>
                          <th className="px-4 py-2.5">Ad Group</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {snapshot.targets.map((t, i) => (
                          <tr key={t.target_id || i} className="hover:bg-gray-50">
                            <td className="px-4 py-2"><StatusDot status={t.status} /></td>
                            <td className="px-4 py-2 font-medium text-gray-900 max-w-xs truncate">{t.expression}</td>
                            <td className="px-4 py-2 text-right tabular-nums text-gray-700"><BidCell bid={t.bid} /></td>
                            <td className="px-4 py-2 text-gray-500 max-w-[180px] truncate">{t.campaign_name}</td>
                            <td className="px-4 py-2 text-gray-500 max-w-[160px] truncate">{t.ad_group_name}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
            )}
            {activeTab === "product_ads" && (
              snapshot.product_ads.length === 0
                ? <p className="text-sm text-gray-500 py-8 text-center">No product ads in this file.</p>
                : (
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-sm border-collapse">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-200 text-left text-xs font-medium text-gray-500 uppercase tracking-wide">
                          <th className="px-4 py-2.5">Status</th>
                          <th className="px-4 py-2.5">ASIN</th>
                          <th className="px-4 py-2.5">SKU</th>
                          <th className="px-4 py-2.5">Campaign</th>
                          <th className="px-4 py-2.5">Ad Group</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-gray-100">
                        {snapshot.product_ads.map((ad, i) => (
                          <tr key={ad.ad_id || i} className="hover:bg-gray-50">
                            <td className="px-4 py-2"><StatusDot status={ad.status} /></td>
                            <td className="px-4 py-2 font-mono text-xs text-gray-700">{ad.asin || "—"}</td>
                            <td className="px-4 py-2 font-mono text-xs text-gray-700">{ad.sku || "—"}</td>
                            <td className="px-4 py-2 text-gray-500 max-w-[180px] truncate">{ad.campaign_name}</td>
                            <td className="px-4 py-2 text-gray-500 max-w-[160px] truncate">{ad.ad_group_name}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
            )}
          </div>
        </div>
      )}
    </div>
  );
}
