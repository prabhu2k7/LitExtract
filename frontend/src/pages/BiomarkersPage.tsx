import { useMemo, useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Beaker,
  ArrowRight,
  Inbox,
  X,
  ExternalLink,
  Quote,
  TrendingUp,
  Search,
  Layers,
  FileText,
  Target,
  Trophy,
} from "lucide-react";
import { getBiomarkers, type BiomarkerItem } from "../lib/api";
import Spinner from "../components/Spinner";
import Pill from "../components/Pill";

export default function BiomarkersPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["biomarkers"],
    queryFn: getBiomarkers,
    refetchInterval: 10_000,
  });

  const [activeName, setActiveName] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const filtered = useMemo(() => {
    if (!data) return [];
    const q = filter.trim().toLowerCase();
    if (!q) return data.items;
    return data.items.filter((b) => {
      return (
        b.canonical_name.toLowerCase().includes(q) ||
        b.display_name.toLowerCase().includes(q) ||
        (b.biomarker_name_std ?? "").toLowerCase().includes(q) ||
        b.diseases.some((d) => d.toLowerCase().includes(q)) ||
        b.outcomes.some((o) => o.toLowerCase().includes(q))
      );
    });
  }, [data, filter]);

  const active: BiomarkerItem | null = useMemo(() => {
    if (!data || !activeName) return null;
    return data.items.find((b) => b.canonical_name === activeName) ?? null;
  }, [data, activeName]);

  const totals = useMemo(() => {
    if (!data || data.items.length === 0) {
      return { biomarkers: 0, papers: 0, findings: 0, sigPct: null as number | null };
    }
    const findings = data.items.reduce((s, b) => s + b.result_rows, 0);
    const sig = data.items.reduce((s, b) => s + b.significant_results, 0);
    return {
      biomarkers: data.count,
      papers: data.papers_scanned,
      findings,
      sigPct: findings > 0 ? Math.round((sig / findings) * 100) : null,
    };
  }, [data]);

  const insights = useMemo(() => {
    if (!data || data.items.length === 0) return null;
    const items = data.items;
    const mostStudied = [...items].sort(
      (a, b) => b.paper_count - a.paper_count || b.result_rows - a.result_rows
    )[0];
    const highestSig = [...items]
      .filter((b) => b.result_rows >= 1)
      .sort((a, b) => (b.significance_rate_pct ?? 0) - (a.significance_rate_pct ?? 0))[0];
    const totalFindings = items.reduce((s, b) => s + b.result_rows, 0);
    return { mostStudied, highestSig, totalFindings };
  }, [data]);

  return (
    <div className="max-w-7xl mx-auto fade-in">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Biomarker registry
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Cross-paper landscape of every biomarker your corpus has touched.
        </p>
      </div>

      {/* Stat strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <SummaryStat
          icon={Beaker}
          label="Unique biomarkers"
          value={totals.biomarkers}
          tone="brand"
        />
        <SummaryStat
          icon={FileText}
          label="Papers covered"
          value={totals.papers}
        />
        <SummaryStat
          icon={Layers}
          label="Total findings"
          value={totals.findings}
        />
        <SummaryStat
          icon={TrendingUp}
          label="Avg significance"
          value={totals.sigPct == null ? "—" : `${totals.sigPct}%`}
          tone={
            totals.sigPct == null
              ? "default"
              : totals.sigPct >= 70
              ? "good"
              : totals.sigPct >= 40
              ? "warn"
              : "default"
          }
        />
      </div>

      {/* Search bar */}
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">
          {filtered.length} {filtered.length === 1 ? "biomarker" : "biomarkers"}
          {filter && ` matching "${filter}"`}
        </div>
        <div className="relative w-72">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400 pointer-events-none" />
          <input
            type="search"
            placeholder="Filter by name, disease, outcome…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-lg border border-slate-300 bg-white text-sm focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none"
          />
        </div>
      </div>

      {isLoading && (
        <div className="grid place-items-center h-40">
          <Spinner label="Loading biomarker registry…" />
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-800">
          <div className="font-medium">Could not load biomarkers</div>
          <div className="text-sm mt-1">
            {(error as Error | undefined)?.message}
          </div>
        </div>
      )}

      {data && data.items.length === 0 && <EmptyState />}

      {data && data.items.length > 0 && filtered.length === 0 && (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center text-sm text-slate-500">
          No biomarkers match{" "}
          <span className="font-mono text-slate-700">{filter}</span>.
        </div>
      )}

      {filtered.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50/80 text-slate-600 border-b border-slate-200">
                <tr>
                  <th className="text-left font-semibold px-4 py-3">
                    Biomarker
                  </th>
                  <th className="text-left font-semibold px-3 py-3">Type</th>
                  <th className="text-right font-semibold px-3 py-3">Papers</th>
                  <th className="text-left font-semibold px-3 py-3">
                    Diseases
                  </th>
                  <th className="text-left font-semibold px-3 py-3">
                    Applications
                  </th>
                  <th className="text-right font-semibold px-3 py-3">
                    Findings
                  </th>
                  <th className="text-right font-semibold px-3 py-3">
                    Significance
                  </th>
                  <th className="px-3 py-3 w-8"></th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((b) => (
                  <tr
                    key={b.canonical_name}
                    onClick={() => setActiveName(b.canonical_name)}
                    className="border-b border-slate-100 last:border-b-0 hover:bg-brand-50/40 cursor-pointer transition-colors group"
                  >
                    <td className="px-4 py-3 align-middle">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-8 h-8 shrink-0 rounded-lg bg-emerald-100 grid place-items-center group-hover:bg-emerald-200 transition-colors">
                          <Beaker className="w-4 h-4 text-emerald-700" />
                        </div>
                        <div className="min-w-0">
                          <div className="font-semibold text-slate-900">
                            {b.display_name}
                          </div>
                          {b.biomarker_name_std &&
                            b.biomarker_name_std !== b.display_name && (
                              <div className="text-[11px] text-slate-500 truncate max-w-[20rem]">
                                {b.biomarker_name_std}
                              </div>
                            )}
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-3 align-middle">
                      {b.biomarker_type ? (
                        <Pill tone="emerald">{b.biomarker_type}</Pill>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-3 align-middle text-right tabular-nums font-semibold text-slate-900">
                      {b.paper_count}
                    </td>
                    <td className="px-3 py-3 align-middle">
                      <div className="flex flex-wrap gap-1 max-w-[16rem]">
                        {b.diseases.length === 0 ? (
                          <span className="text-slate-300">—</span>
                        ) : (
                          b.diseases.slice(0, 3).map((d) => (
                            <Pill key={d} tone="brand">
                              {d}
                            </Pill>
                          ))
                        )}
                        {b.diseases.length > 3 && (
                          <span className="text-[11px] text-slate-500">
                            +{b.diseases.length - 3}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-3 py-3 align-middle">
                      <div className="flex flex-wrap gap-1">
                        {b.applications.slice(0, 3).map((a) => (
                          <Pill key={a} tone="slate">
                            {a}
                          </Pill>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-3 align-middle text-right tabular-nums">
                      {b.result_rows}
                    </td>
                    <td className="px-3 py-3 align-middle text-right">
                      {b.significance_rate_pct == null ? (
                        <span className="text-slate-300">—</span>
                      ) : (
                        <SigBar pct={b.significance_rate_pct} />
                      )}
                    </td>
                    <td className="px-3 py-3 align-middle text-right text-slate-300 group-hover:text-brand-600 transition-colors">
                      <ArrowRight className="w-3.5 h-3.5 inline" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Insights — fills the bottom of the page so it doesn't read empty */}
      {insights && (
        <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-3">
          <InsightCard
            icon={Trophy}
            tone="brand"
            label="Most studied"
            primary={insights.mostStudied.display_name}
            secondary={`${insights.mostStudied.paper_count} paper${
              insights.mostStudied.paper_count === 1 ? "" : "s"
            } · ${insights.mostStudied.result_rows} finding${
              insights.mostStudied.result_rows === 1 ? "" : "s"
            }`}
          />
          <InsightCard
            icon={Target}
            tone="emerald"
            label="Highest significance"
            primary={insights.highestSig.display_name}
            secondary={`${
              insights.highestSig.significance_rate_pct ?? 0
            }% of ${insights.highestSig.result_rows} finding${
              insights.highestSig.result_rows === 1 ? "" : "s"
            } significant`}
          />
          <InsightCard
            icon={Layers}
            tone="default"
            label="Corpus depth"
            primary={`${insights.totalFindings} findings`}
            secondary={`across ${data?.papers_scanned ?? 0} paper${
              (data?.papers_scanned ?? 0) === 1 ? "" : "s"
            }, ${data?.count ?? 0} unique biomarker${
              (data?.count ?? 0) === 1 ? "" : "s"
            }`}
          />
        </div>
      )}

      {/* Drawer */}
      {active && (
        <BiomarkerDrawer item={active} onClose={() => setActiveName(null)} />
      )}
    </div>
  );
}

function SummaryStat({
  icon: Icon,
  label,
  value,
  tone = "default",
}: {
  icon: typeof Beaker;
  label: string;
  value: number | string;
  tone?: "default" | "brand" | "good" | "warn";
}) {
  const cardStyle =
    tone === "brand"
      ? "border-brand-100 bg-gradient-to-br from-brand-50 to-white"
      : tone === "good"
      ? "border-emerald-100 bg-gradient-to-br from-emerald-50 to-white"
      : tone === "warn"
      ? "border-amber-100 bg-gradient-to-br from-amber-50 to-white"
      : "border-slate-200 bg-white";
  const iconStyle =
    tone === "brand"
      ? "bg-brand-100 text-brand-700"
      : tone === "good"
      ? "bg-emerald-100 text-emerald-700"
      : tone === "warn"
      ? "bg-amber-100 text-amber-700"
      : "bg-slate-100 text-slate-700";
  return (
    <div className={`rounded-xl border ${cardStyle} p-4 shadow-sm`}>
      <div className="flex items-start justify-between">
        <div className="text-[11px] font-medium text-slate-500 uppercase tracking-wide">
          {label}
        </div>
        <div
          className={`w-7 h-7 rounded-lg grid place-items-center ${iconStyle}`}
        >
          <Icon className="w-3.5 h-3.5" />
        </div>
      </div>
      <div className="mt-2 text-2xl font-semibold tabular-nums text-slate-900">
        {value}
      </div>
    </div>
  );
}

function SigBar({ pct }: { pct: number }) {
  const colour =
    pct >= 70 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-rose-500";
  const text =
    pct >= 70
      ? "text-emerald-700"
      : pct >= 40
      ? "text-amber-700"
      : "text-rose-700";
  return (
    <div className="inline-flex items-center gap-2 justify-end w-full">
      <div className="w-16 h-1.5 bg-slate-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${colour}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`tabular-nums font-semibold text-xs w-8 text-right ${text}`}>
        {pct}%
      </span>
    </div>
  );
}

function InsightCard({
  icon: Icon,
  label,
  primary,
  secondary,
  tone = "default",
}: {
  icon: typeof Beaker;
  label: string;
  primary: string;
  secondary: string;
  tone?: "default" | "brand" | "emerald";
}) {
  const ring =
    tone === "brand"
      ? "border-brand-100"
      : tone === "emerald"
      ? "border-emerald-100"
      : "border-slate-200";
  const iconStyle =
    tone === "brand"
      ? "bg-brand-100 text-brand-700"
      : tone === "emerald"
      ? "bg-emerald-100 text-emerald-700"
      : "bg-slate-100 text-slate-700";
  return (
    <div className={`rounded-xl border ${ring} bg-white p-4 shadow-sm`}>
      <div className="flex items-center gap-2 text-[11px] font-medium text-slate-500 uppercase tracking-wide">
        <div
          className={`w-6 h-6 rounded-md grid place-items-center ${iconStyle}`}
        >
          <Icon className="w-3 h-3" />
        </div>
        {label}
      </div>
      <div className="mt-2 text-base font-semibold text-slate-900 truncate">
        {primary}
      </div>
      <div className="mt-0.5 text-xs text-slate-500 truncate">{secondary}</div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
      <div className="mx-auto w-12 h-12 rounded-full bg-slate-100 grid place-items-center">
        <Inbox className="w-5 h-5 text-slate-500" />
      </div>
      <div className="mt-3 text-sm font-medium text-slate-900">
        No biomarkers yet
      </div>
      <div className="mt-1 text-xs text-slate-500">
        Upload a paper to populate the registry.
      </div>
      <Link
        to="/upload"
        className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800"
      >
        Go to Upload <ArrowRight className="w-3.5 h-3.5" />
      </Link>
    </div>
  );
}

function BiomarkerDrawer({
  item,
  onClose,
}: {
  item: BiomarkerItem;
  onClose: () => void;
}) {
  // Lock background scroll, listen for Esc
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  // Group results by paper
  const byPaper = useMemo(() => {
    const map = new Map<string, typeof item.results>();
    for (const r of item.results) {
      const list = map.get(r.pubmed_id) ?? [];
      list.push(r);
      map.set(r.pubmed_id, list);
    }
    return Array.from(map.entries()).sort((a, b) => a[0].localeCompare(b[0]));
  }, [item]);

  const inferencesByPaper = useMemo(() => {
    const map = new Map<string, typeof item.inferences>();
    for (const r of item.inferences) {
      const list = map.get(r.pubmed_id) ?? [];
      list.push(r);
      map.set(r.pubmed_id, list);
    }
    return map;
  }, [item]);

  const drawerNode = (
    <div
      className="fixed inset-0 z-[60] bg-slate-950/55 backdrop-blur-sm transition-opacity"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
    >
      <aside
        className="fixed right-0 top-0 bottom-0 w-full max-w-2xl bg-white shadow-[-12px_0_32px_-8px_rgba(15,23,42,0.25)] border-l border-slate-200 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer header — gradient banner so it visually claims the panel */}
        <div className="shrink-0 bg-gradient-to-br from-brand-700 via-brand-800 to-brand-950 text-white px-6 py-5 relative overflow-hidden">
          <div className="absolute -right-12 -top-12 w-48 h-48 rounded-full bg-white/5 blur-3xl pointer-events-none" />
          <div className="relative flex items-start justify-between gap-4">
            <div className="min-w-0">
              <div className="flex items-center gap-3">
                <div className="w-11 h-11 rounded-xl bg-white/15 backdrop-blur-sm grid place-items-center ring-1 ring-white/20">
                  <Beaker className="w-5 h-5 text-white" />
                </div>
                <div className="min-w-0">
                  <div className="text-xl font-semibold leading-tight tracking-tight truncate">
                    {item.display_name}
                  </div>
                  {item.biomarker_name_std &&
                    item.biomarker_name_std !== item.display_name && (
                      <div className="text-xs text-brand-100/90 truncate">
                        {item.biomarker_name_std}
                      </div>
                    )}
                </div>
              </div>
              <div className="mt-3 flex flex-wrap gap-1.5">
                {item.biomarker_type && (
                  <DrawerChip>{item.biomarker_type}</DrawerChip>
                )}
                {item.biomarker_nature && (
                  <DrawerChip>{item.biomarker_nature}</DrawerChip>
                )}
                {item.applications.map((a) => (
                  <DrawerChip key={a}>{a}</DrawerChip>
                ))}
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="shrink-0 p-1.5 rounded-md hover:bg-white/10 text-white/80 hover:text-white"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Stat strip on dark gradient */}
          <div className="relative grid grid-cols-3 gap-2 mt-5">
            <DrawerHeaderStat label="Papers" value={String(item.paper_count)} />
            <DrawerHeaderStat
              label="Findings"
              value={String(item.result_rows)}
            />
            <DrawerHeaderStat
              label="Significance"
              value={
                item.significance_rate_pct == null
                  ? "—"
                  : `${item.significance_rate_pct}%`
              }
              tone={
                item.significance_rate_pct == null
                  ? "default"
                  : item.significance_rate_pct >= 70
                  ? "good"
                  : item.significance_rate_pct >= 40
                  ? "warn"
                  : "bad"
              }
            />
          </div>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4 bg-slate-50/40">
          <div className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
            Per-paper detail · {byPaper.length} paper
            {byPaper.length === 1 ? "" : "s"}
          </div>

          {byPaper.map(([pid, results]) => (
            <div
              key={pid}
              className="rounded-xl border border-slate-200 bg-white overflow-hidden shadow-sm"
            >
              <div className="px-4 py-2.5 border-b border-slate-200 bg-slate-50/60 flex items-center justify-between">
                <div className="text-sm font-mono font-medium text-slate-900">
                  {pid}
                </div>
                <Link
                  to={`/results/${encodeURIComponent(pid)}`}
                  className="inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:text-brand-800"
                  onClick={onClose}
                >
                  Open paper <ExternalLink className="w-3 h-3" />
                </Link>
              </div>
              <div className="px-4 py-3 space-y-2">
                {results.map((r, i) => (
                  <div
                    key={i}
                    className="text-xs text-slate-700 flex flex-wrap items-baseline gap-x-2 gap-y-1 py-1"
                  >
                    <span className="font-semibold text-slate-900">
                      {r.outcome_name || "—"}
                    </span>
                    <span className="text-slate-300">·</span>
                    <span>{r.statistical_test || "—"}</span>
                    {r.value_type && (
                      <>
                        <span className="text-slate-300">·</span>
                        <span className="text-slate-600">{r.value_type}</span>
                      </>
                    )}
                    {r.r_value != null && r.r_value !== "" && (
                      <span className="font-mono text-slate-800 bg-slate-100 px-1.5 py-0.5 rounded">
                        {r.r_value}
                        {r.r_ci_lower != null && r.r_ci_upper != null && (
                          <>
                            {" ("}
                            {r.r_ci_lower}–{r.r_ci_upper}
                            {")"}
                          </>
                        )}
                      </span>
                    )}
                    {r.p_value != null && r.p_value !== "" && (
                      <span className="font-mono text-slate-700">
                        p{r.p_value_prefix || "="}
                        {r.p_value}
                      </span>
                    )}
                    {r.significance_call && (
                      <span
                        className={
                          r.significance_call.toLowerCase() === "significant"
                            ? "text-emerald-700 font-semibold"
                            : "text-slate-500"
                        }
                      >
                        {r.significance_call}
                      </span>
                    )}
                  </div>
                ))}

                {(inferencesByPaper.get(pid) ?? []).map((inf, i) => (
                  <div
                    key={`inf_${i}`}
                    className="mt-2 text-xs text-slate-700 bg-brand-50/60 border border-brand-100 rounded-lg px-3 py-2.5"
                  >
                    <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wide text-brand-700 font-semibold">
                      <Quote className="w-3 h-3" />
                      {inf.br_application || "Inference"}
                    </div>
                    {inf.evidence_statement && (
                      <div className="mt-1 italic text-slate-700 leading-relaxed">
                        {inf.evidence_statement}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </aside>
    </div>
  );

  return createPortal(drawerNode, document.body);
}

function DrawerChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center px-2 py-0.5 text-[11px] font-medium rounded-full bg-white/15 text-white border border-white/20 backdrop-blur-sm">
      {children}
    </span>
  );
}

function DrawerHeaderStat({
  label,
  value,
  tone = "default",
}: {
  label: string;
  value: string;
  tone?: "default" | "good" | "warn" | "bad";
}) {
  const valueClass =
    tone === "good"
      ? "text-emerald-300"
      : tone === "warn"
      ? "text-amber-300"
      : tone === "bad"
      ? "text-rose-300"
      : "text-white";
  return (
    <div className="rounded-lg bg-white/10 border border-white/15 backdrop-blur-sm px-3 py-2.5">
      <div className="text-[10px] uppercase tracking-wide text-brand-100/80 font-medium">
        {label}
      </div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${valueClass}`}>
        {value}
      </div>
    </div>
  );
}
