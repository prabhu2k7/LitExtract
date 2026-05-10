import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Award,
  Target,
  CheckCircle2,
  ExternalLink,
  X,
  AlertCircle,
  ShieldCheck,
  Download,
  Upload,
  ArrowRight,
} from "lucide-react";
import {
  getValidationSummary,
  getValidationHistory,
  getValidationPaper,
  validationPaperDownloadUrl,
  validationSummaryDownloadUrl,
  type ValidationPaperRow,
  type ValidationVersion,
} from "../lib/api";
import StatCard from "../components/StatCard";
import Pill from "../components/Pill";
import Spinner from "../components/Spinner";

const STATUS_TONE: Record<ValidationPaperRow["status"], "emerald" | "brand" | "amber" | "rose" | "slate"> = {
  perfect: "emerald",
  high: "brand",
  partial: "amber",
  miss: "rose",
  no_extraction: "slate",
};

const STATUS_LABEL: Record<ValidationPaperRow["status"], string> = {
  perfect: "100%",
  high: "High",
  partial: "Partial",
  miss: "Miss",
  no_extraction: "No run",
};

function fmt(n: number | null | undefined, suffix = ""): string {
  if (n === null || n === undefined) return "–";
  return `${n.toFixed(1)}${suffix}`;
}

export default function ValidationPage() {
  const [openPmid, setOpenPmid] = useState<string | null>(null);

  const summary = useQuery({
    queryKey: ["validation", "summary"],
    queryFn: getValidationSummary,
  });

  const history = useQuery({
    queryKey: ["validation", "history"],
    queryFn: getValidationHistory,
  });

  if (summary.isLoading || history.isLoading) {
    return (
      <div className="grid place-items-center h-60">
        <Spinner label="Loading validation data…" />
      </div>
    );
  }

  if (summary.isError || !summary.data?.available) {
    return (
      <div className="max-w-3xl mx-auto rounded-xl border border-amber-200 bg-amber-50 p-5 text-amber-900">
        <div className="font-medium">Validation set not available</div>
        <div className="mt-1 text-sm">
          The benchmark folder ({summary.data?.validation_dir ?? "showcase_10"})
          isn't reachable on this server. Validation requires a local goldset
          built via <code className="text-xs">scripts/build_goldset.py</code>.
        </div>
      </div>
    );
  }

  const agg = summary.data.aggregate;
  const papers = summary.data.papers;
  const versions = history.data?.versions ?? [];

  return (
    <div className="max-w-7xl mx-auto fade-in space-y-8">
      {/* ---- Header ---- */}
      <div className="flex flex-col lg:flex-row gap-4 lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-brand-700" />
            <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
              Validation against CIViC gold standard
            </h1>
          </div>
          <p className="mt-2 text-sm text-slate-600 max-w-3xl">
            Independent benchmark on 10 oncology papers. Gold biomarkers come from{" "}
            <a
              href="https://civicdb.org/"
              target="_blank"
              rel="noreferrer"
              className="text-brand-700 hover:underline inline-flex items-center gap-0.5"
            >
              CIViC <ExternalLink className="w-3 h-3" />
            </a>
            {" "}— a public, peer-curated cancer evidence database. Click any row
            to audit gold-vs-extracted side-by-side.
          </p>
        </div>
        <a
          href={validationSummaryDownloadUrl()}
          download
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-slate-200 text-sm font-medium text-slate-700 hover:bg-slate-50 hover:border-slate-300 shadow-sm whitespace-nowrap"
        >
          <Download className="w-4 h-4" />
          Download benchmark Excel
        </a>
      </div>

      {/* ---- "Try with your paper" CTA ---- */}
      <Link
        to="/upload"
        className="block group rounded-2xl border border-brand-200 bg-gradient-to-r from-brand-50 via-brand-50/60 to-accent-500/5 p-5 hover:border-brand-300 hover:shadow-sm transition"
      >
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white border border-brand-200 grid place-items-center shrink-0">
              <Upload className="w-4 h-4 text-brand-700" />
            </div>
            <div>
              <div className="text-sm font-semibold text-slate-900">
                Try Biomarker Research on your own paper
              </div>
              <div className="text-xs text-slate-600 mt-0.5">
                Upload a PDF — results come back in under 90 seconds. Bring your own gold standard and we'll add it to this benchmark in 48 hours.
              </div>
            </div>
          </div>
          <ArrowRight className="w-4 h-4 text-brand-700 group-hover:translate-x-0.5 transition-transform shrink-0" />
        </div>
      </Link>

      {/* ---- Headline metrics ---- */}
      {agg && (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <StatCard
            label="Canonical recall (median)"
            value={`${agg.median_canonical.toFixed(0)}%`}
            hint={`Mean ${agg.mean_canonical.toFixed(1)}% across ${agg.papers_scored} papers`}
            icon={Target}
            tone="brand"
          />
          <StatCard
            label="Papers at 100% canonical"
            value={`${agg.papers_at_100_canon}/${agg.papers_total}`}
            hint={`${agg.papers_at_80_canon}/${agg.papers_total} ≥ 80%`}
            icon={CheckCircle2}
            tone="accent"
          />
          <StatCard
            label="Full F1 (median)"
            value={fmt(agg.median_f1)}
            hint={`Bounded by CIViC sparsity — see methodology`}
            icon={Award}
          />
          <StatCard
            label="Best paper F1"
            value={fmt(agg.max_f1)}
            hint={`Mean ${fmt(agg.mean_f1)}`}
          />
        </div>
      )}

      {/* ---- Methodology callout ---- */}
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm">
        <div className="font-medium text-slate-900 mb-1">Why two metrics?</div>
        <div className="text-slate-700 leading-relaxed">
          <span className="font-semibold">Canonical Biomarker Recall</span> —
          per paper, did we extract the headline gene/variant CIViC encodes?
          This is the pharma-facing number. <span className="font-semibold">Full
          F1</span> compares all 32 fields strictly against CIViC's sparse
          drug-evidence rows; the extractor pulls every biomarker measured in
          the paper, so F1 is mathematically capped around 25-50%. F1 is here
          for diagnostic comparison, not as a marketing number.
        </div>
      </div>

      {/* ---- Version timeline ---- */}
      {versions.length > 0 && (
        <VersionTimeline versions={versions} />
      )}

      {/* ---- Per-paper table ---- */}
      <div>
        <div className="mb-3 flex items-baseline justify-between">
          <h2 className="text-base font-semibold text-slate-900">
            Per-paper results
          </h2>
          <div className="text-xs text-slate-500">
            Click a row to open the gold-vs-extracted audit drawer
          </div>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-600">
              <tr className="text-left">
                <th className="px-4 py-2.5 font-medium">PMID</th>
                <th className="px-4 py-2.5 font-medium">Slot</th>
                <th className="px-4 py-2.5 font-medium text-right">CIViC rows</th>
                <th className="px-4 py-2.5 font-medium text-right">Extracted</th>
                <th className="px-4 py-2.5 font-medium text-right">Canonical %</th>
                <th className="px-4 py-2.5 font-medium text-right">F1</th>
                <th className="px-4 py-2.5 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {papers.map((p) => (
                <tr
                  key={p.pmid}
                  onClick={() => setOpenPmid(p.pmid)}
                  className="cursor-pointer hover:bg-slate-50 transition-colors"
                >
                  <td className="px-4 py-3 font-mono text-xs text-slate-700">{p.pmid}</td>
                  <td className="px-4 py-3 text-slate-900 font-medium">{p.slot}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                    {p.gold_total}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                    {p.extracted_total}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums font-semibold text-slate-900">
                    {fmt(p.canonical_recall, "%")}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums text-slate-600">
                    {fmt(p.f1)}
                  </td>
                  <td className="px-4 py-3">
                    <Pill tone={STATUS_TONE[p.status]}>
                      {STATUS_LABEL[p.status]}
                      {p.canonical_missed.length > 0 ? (
                        <span className="ml-1 opacity-70">· missed {p.canonical_missed.join(", ")}</span>
                      ) : null}
                    </Pill>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ---- Drawer ---- */}
      {openPmid && (
        <PaperDrawer pmid={openPmid} onClose={() => setOpenPmid(null)} />
      )}
    </div>
  );
}


// ---- Version timeline component ----

function VersionTimeline({ versions }: { versions: ValidationVersion[] }) {
  return (
    <div>
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-base font-semibold text-slate-900">
          Version history
        </h2>
        <div className="text-xs text-slate-500">
          How metrics evolved across normalisation + extraction iterations
        </div>
      </div>
      <div className="overflow-x-auto">
        <div className="flex gap-3 min-w-full">
          {versions.map((v) => (
            <div
              key={v.version}
              className="flex-1 min-w-[220px] rounded-xl border border-slate-200 bg-white p-3"
            >
              <div className="flex items-center justify-between">
                <div className="text-xs font-mono text-brand-700">{v.version}</div>
                <div className="text-[11px] text-slate-500">{v.date}</div>
              </div>
              <div className="mt-1 text-sm font-semibold text-slate-900">
                {v.label}
              </div>
              <div className="mt-3 grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <div className="text-slate-500 uppercase tracking-wide">Canon</div>
                  <div className="font-semibold text-slate-900 tabular-nums">
                    {v.median_canonical_recall === null
                      ? "—"
                      : `${v.median_canonical_recall.toFixed(0)}%`}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 uppercase tracking-wide">F1</div>
                  <div className="font-semibold text-slate-900 tabular-nums">
                    {v.median_f1 === null ? "—" : v.median_f1.toFixed(1)}
                  </div>
                </div>
              </div>
              <ul className="mt-3 space-y-1 text-[11px] text-slate-600">
                {v.changes.slice(0, 3).map((c, i) => (
                  <li key={i} className="flex gap-1">
                    <span className="text-slate-400">·</span>
                    <span className="line-clamp-2">{c}</span>
                  </li>
                ))}
                {v.changes.length > 3 ? (
                  <li className="text-slate-400">+{v.changes.length - 3} more</li>
                ) : null}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}


// ---- Paper detail drawer ----

function PaperDrawer({ pmid, onClose }: { pmid: string; onClose: () => void }) {
  const detail = useQuery({
    queryKey: ["validation", "paper", pmid],
    queryFn: () => getValidationPaper(pmid),
  });

  return (
    <div className="fixed inset-0 z-40 flex">
      {/* Backdrop */}
      <div
        className="flex-1 bg-slate-900/40 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Drawer */}
      <div className="w-full max-w-3xl bg-white shadow-2xl overflow-y-auto border-l border-slate-200">
        <div className="sticky top-0 bg-white border-b border-slate-200 px-6 py-4 flex items-center justify-between z-10">
          <div>
            <div className="text-xs text-slate-500">PMID {pmid}</div>
            <div className="text-lg font-semibold text-slate-900">
              {detail.data?.slot ?? "Loading…"}
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 text-slate-500"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {detail.isLoading && (
          <div className="grid place-items-center h-60">
            <Spinner />
          </div>
        )}

        {detail.data && (
          <div className="p-6 space-y-6">
            {/* Audit links */}
            <div className="flex flex-wrap gap-2 text-xs">
              <a
                href={detail.data.pubmed_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
              >
                PubMed <ExternalLink className="w-3 h-3" />
              </a>
              {detail.data.pmc_url && (
                <a
                  href={detail.data.pmc_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
                >
                  PMC fulltext <ExternalLink className="w-3 h-3" />
                </a>
              )}
              {detail.data.civic_evidence_count > 0 && (
                <Pill tone="brand">
                  {detail.data.civic_evidence_count} CIViC evidence rows
                </Pill>
              )}
              <a
                href={validationPaperDownloadUrl(pmid)}
                download
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full border border-brand-200 bg-brand-50 text-brand-700 hover:bg-brand-100 ml-auto"
              >
                <Download className="w-3 h-3" /> Download audit pack
              </a>
            </div>

            {/* CIViC verify links — proves the gold isn't ours */}
            {detail.data.civic_profiles?.length > 0 && (
              <div className="rounded-lg border border-brand-100 bg-gradient-to-br from-brand-50/60 to-white p-3">
                <div className="text-[11px] font-semibold text-brand-800 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                  <ShieldCheck className="w-3 h-3" />
                  Verify the gold standard on CIViC
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {detail.data.civic_profiles.slice(0, 12).map((p) => (
                    <a
                      key={p.civic_url || p.molecular_profile}
                      href={p.civic_url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1 px-2 py-0.5 text-[11px] rounded-full border border-slate-200 bg-white text-slate-700 hover:border-brand-300 hover:text-brand-700"
                      title={`${p.disease}${p.therapies ? ` · ${p.therapies}` : ""}`}
                    >
                      {p.molecular_profile}
                      <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                    </a>
                  ))}
                  {detail.data.civic_profiles.length > 12 ? (
                    <span className="text-[11px] text-slate-500 self-center">
                      +{detail.data.civic_profiles.length - 12} more
                    </span>
                  ) : null}
                </div>
                <div className="mt-2 text-[11px] text-slate-500">
                  Each pill links to CIViC's molecular-profile page so you can
                  verify the gold standard independently.
                </div>
              </div>
            )}

            {/* Scores */}
            {detail.data.scores && (
              <div className="grid grid-cols-4 gap-2 text-xs">
                <ScoreChip label="Canonical" v={detail.data.scores.canonical_recall} suffix="%" />
                <ScoreChip label="F1" v={detail.data.scores.f1} />
                <ScoreChip label="Recall" v={detail.data.scores.row_recall} suffix="%" />
                <ScoreChip label="Precision" v={detail.data.scores.field_precision} suffix="%" />
              </div>
            )}

            {/* Canonical biomarker comparison */}
            <div>
              <div className="text-sm font-semibold text-slate-900 mb-2">
                Canonical biomarkers (gene-level)
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">
                    Gold (CIViC)
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.data.canonical.gold.length === 0 ? (
                      <span className="text-xs text-slate-400">no gold rows</span>
                    ) : (
                      detail.data.canonical.gold.map((g) => {
                        const captured = detail.data!.canonical.captured.includes(g);
                        return (
                          <Pill key={g} tone={captured ? "emerald" : "rose"}>
                            {captured ? "✓" : "✗"} {g}
                          </Pill>
                        );
                      })
                    )}
                  </div>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
                  <div className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1.5">
                    Extracted
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {detail.data.canonical.ext.length === 0 ? (
                      <span className="text-xs text-slate-400">no extracted rows</span>
                    ) : (
                      detail.data.canonical.ext.map((e) => {
                        const inGold = detail.data!.canonical.gold.includes(e);
                        return (
                          <Pill key={e} tone={inGold ? "emerald" : "slate"}>
                            {e}
                          </Pill>
                        );
                      })
                    )}
                  </div>
                </div>
              </div>

              {detail.data.canonical.missed.length > 0 && (
                <div className="mt-2 flex items-start gap-2 rounded-lg bg-rose-50 border border-rose-200 p-2.5 text-xs text-rose-800">
                  <AlertCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <div>
                    <span className="font-medium">Missed by extractor:</span>{" "}
                    {detail.data.canonical.missed.join(", ")}
                  </div>
                </div>
              )}
            </div>

            {/* Side-by-side rows */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <SideBySidePanel
                title="Gold standard rows (CIViC)"
                rows={detail.data.gold}
                emptyHint="no gold rows for this PMID"
              />
              <SideBySidePanel
                title="Our extraction"
                rows={detail.data.extracted}
                emptyHint="no extraction cached"
                showQuotes
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function ScoreChip({ label, v, suffix = "" }: { label: string; v: number; suffix?: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-2 text-center">
      <div className="text-[10px] text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="text-base font-semibold text-slate-900 tabular-nums">
        {v.toFixed(1)}{suffix}
      </div>
    </div>
  );
}


function SideBySidePanel({
  title,
  rows,
  emptyHint,
  showQuotes,
}: {
  title: string;
  rows: { sheet: string; biomarker_raw: string; biomarker_normalized: string;
          disease: string; therapy: string; significance: string;
          br_application: string; outcome: string;
          source_excerpt?: string; source_section?: string }[];
  emptyHint: string;
  showQuotes?: boolean;
}) {
  return (
    <div className="rounded-lg border border-slate-200 overflow-hidden">
      <div className="px-3 py-2 bg-slate-50 border-b border-slate-200 text-xs font-semibold text-slate-700 flex items-center justify-between">
        <span>{title} <span className="text-slate-400">({rows.length})</span></span>
        {showQuotes && rows.length > 0 ? (
          <span className="text-[10px] font-normal text-emerald-700">
            ✓ every row has a verbatim quote
          </span>
        ) : null}
      </div>
      <div className="max-h-96 overflow-y-auto">
        {rows.length === 0 ? (
          <div className="px-3 py-6 text-xs text-slate-400 text-center">{emptyHint}</div>
        ) : (
          <ul className="divide-y divide-slate-100">
            {rows.map((r, i) => (
              <li key={i} className="px-3 py-2 hover:bg-slate-50">
                <div className="flex items-start gap-2 text-[11px]">
                  <span className="font-mono text-slate-400 shrink-0 w-10">
                    {r.sheet.replace("BM_", "").slice(0, 4)}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="font-medium text-slate-900">
                        {r.biomarker_raw || <span className="text-slate-300">—</span>}
                      </span>
                      <span className="font-mono text-[10px] text-slate-500">
                        norm: {r.biomarker_normalized || "—"}
                      </span>
                    </div>
                    {[r.therapy, r.significance, r.br_application, r.outcome]
                      .filter(Boolean).length > 0 && (
                      <div className="mt-0.5 text-slate-600">
                        {[r.therapy, r.significance, r.br_application, r.outcome]
                          .filter(Boolean).join(" · ")}
                      </div>
                    )}
                    {showQuotes && r.source_excerpt ? (
                      <div className="mt-1.5 rounded bg-emerald-50 border border-emerald-100 px-2 py-1 text-[10.5px] text-emerald-900 leading-snug">
                        <span className="font-semibold">
                          {r.source_section || "source"}:
                        </span>{" "}
                        <span className="italic">"{r.source_excerpt}"</span>
                      </div>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
