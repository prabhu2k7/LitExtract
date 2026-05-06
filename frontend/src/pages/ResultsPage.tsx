import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Download,
  ArrowLeft,
  FileText,
  Beaker,
  BarChart3,
  Lightbulb,
  Database,
  DollarSign,
  Layers,
  FileSpreadsheet,
  FileJson,
  Table2,
} from "lucide-react";
import {
  downloadUrl,
  downloadCsvUrl,
  downloadJsonUrl,
  getResults,
  type SheetName,
} from "../lib/api";
import StatCard from "../components/StatCard";
import Tabs from "../components/Tabs";
import DataTable from "../components/DataTable";
import Pill from "../components/Pill";
import { SkeletonStatCards, SkeletonTable, Skeleton } from "../components/Skeleton";

const PREFERRED_COLUMNS: Record<SheetName, string[]> = {
  Study_Details: [
    "study_type",
    "disease_name",
    "patient_count",
    "geographical_region",
    "gender_distribution",
    "age_range",
    "follow_up_duration",
    "treatment_regimen",
  ],
  BM_Details: [
    "biomarker_name",
    "biomarker_type",
    "biomarker_nature",
    "biomarker_name_std",
    "biomarker_name_type",
  ],
  BM_Results: [
    "biomarker_name",
    "outcome_name",
    "bm_outcome_association",
    "outcome_direction",
    "statistical_test",
    "value_type",
    "p_value",
    "significance_call",
    "specimen",
    "methodology_technique",
  ],
  Inferences: [
    "biomarker_name",
    "br_application",
    "evidence_statement",
    "bm_outcome",
  ],
};

export default function ResultsPage() {
  const { paperId } = useParams<{ paperId: string }>();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["results", paperId],
    queryFn: () => getResults(paperId!),
    enabled: !!paperId,
  });

  if (!paperId) return null;

  if (isLoading) {
    return (
      <div className="max-w-7xl mx-auto fade-in">
        <div className="mb-6">
          <Skeleton className="h-3 w-12 mb-3" />
          <Skeleton className="h-7 w-72" />
          <div className="mt-3 flex gap-2">
            <Skeleton className="h-5 w-24 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
            <Skeleton className="h-5 w-28 rounded-full" />
          </div>
        </div>
        <SkeletonStatCards />
        <SkeletonStatCards />
        <SkeletonTable />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className="rounded-xl border border-rose-200 bg-rose-50 p-6 text-rose-800">
        <div className="font-medium">Could not load results</div>
        <div className="text-sm mt-1">{(error as Error | undefined)?.message}</div>
        <Link to="/upload" className="text-sm mt-3 inline-flex items-center gap-1 text-rose-700 hover:underline">
          <ArrowLeft className="w-3.5 h-3.5" /> Back to upload
        </Link>
      </div>
    );
  }

  const { extracted, counts, meta } = data;
  const totalRows =
    counts.Study_Details + counts.BM_Details + counts.BM_Results + counts.Inferences;
  const cost = meta?.extraction_cost_usd as number | undefined;
  const inputTokens = meta?.extraction_input_tokens as number | undefined;
  const outputTokens = meta?.extraction_output_tokens as number | undefined;

  return (
    <div className="max-w-7xl mx-auto fade-in">
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-6">
        <div className="min-w-0 flex-1">
          <Link
            to="/upload"
            className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-700"
          >
            <ArrowLeft className="w-3 h-3" /> Back
          </Link>
          <h1
            className="mt-1 text-2xl font-semibold text-slate-900 truncate tracking-tight"
            title={data.filename ?? paperId}
          >
            {data.filename ?? paperId}
          </h1>
          <div className="mt-1 text-[11px] text-slate-500 flex items-center gap-2 font-mono">
            <span title="Display identifier (used in URLs and Excel)">
              ID · {data.display_id}
            </span>
            {data.pmid && (
              <>
                <span className="text-slate-300">·</span>
                <span title="Detected PubMed ID">PMID {data.pmid}</span>
              </>
            )}
            {data.upload_id && (
              <>
                <span className="text-slate-300">·</span>
                <span
                  className="text-slate-400 cursor-help"
                  title={`Internal upload UUID: ${data.upload_id}`}
                >
                  upload {data.upload_id.slice(0, 8)}…
                </span>
              </>
            )}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            {meta?.disease ? (
              <Pill tone="brand">{String(meta.disease).replace(/_/g, " ")}</Pill>
            ) : null}
            {(meta?.study_types ?? []).map((t) => (
              <Pill key={t} tone="slate">
                {t.replace(/_/g, " ")}
              </Pill>
            ))}
            {(meta?.bm_types ?? []).map((t) => (
              <Pill key={t} tone="emerald">
                {t.replace(/_/g, " ")}
              </Pill>
            ))}
            {meta?.confidence ? (
              <Pill tone="amber">conf · {meta.confidence}</Pill>
            ) : null}
            {meta?.llm_model ? (
              <Pill tone="slate">{String(meta.llm_model)}</Pill>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <a
            href={downloadUrl(paperId)}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gradient-to-r from-brand-600 to-brand-700 hover:from-brand-700 hover:to-brand-800 text-white text-sm font-medium shadow-sm hover:shadow-md transition-all"
            title="4-sheet workbook (Study, Biomarkers, Results, Inferences)"
          >
            <FileSpreadsheet className="w-4 h-4" />
            Excel
          </a>
          <a
            href={downloadCsvUrl(paperId)}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium transition-colors"
            title="One row per finding — best for pivot tables / Power BI / Tableau"
          >
            <Table2 className="w-4 h-4" />
            CSV
          </a>
          <a
            href={downloadJsonUrl(paperId)}
            className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium transition-colors"
            title="Full extraction with metadata — for programmatic use"
          >
            <FileJson className="w-4 h-4" />
            JSON
          </a>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard
          icon={Layers}
          label="Total rows"
          value={totalRows}
          tone="brand"
          hint="across 4 sheets"
        />
        <StatCard
          icon={Database}
          label="Cost"
          value={cost != null ? `$${cost.toFixed(4)}` : "—"}
          hint={
            inputTokens != null
              ? `${inputTokens.toLocaleString()} in · ${(outputTokens ?? 0).toLocaleString()} out`
              : undefined
          }
        />
        <StatCard
          icon={DollarSign}
          label="Tokens used"
          value={
            inputTokens != null
              ? ((inputTokens ?? 0) + (outputTokens ?? 0)).toLocaleString()
              : "—"
          }
          hint="input + output"
        />
        <StatCard
          icon={BarChart3}
          label="Run"
          value={meta?.run_datetime ? formatDate(String(meta.run_datetime)) : "—"}
          hint={meta?.run_id ? String(meta.run_id).slice(-12) : undefined}
        />
      </div>

      {/* Sheet count summary tiles */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <SheetTile icon={FileText} label="Study Details" value={counts.Study_Details} />
        <SheetTile icon={Beaker} label="BM Details" value={counts.BM_Details} />
        <SheetTile icon={BarChart3} label="BM Results" value={counts.BM_Results} />
        <SheetTile icon={Lightbulb} label="Inferences" value={counts.Inferences} />
      </div>

      {/* Tabs */}
      <Tabs
        tabs={[
          {
            id: "study",
            label: "Study Details",
            count: counts.Study_Details,
            content: (
              <DataTable
                rows={extracted.Study_Details ?? []}
                preferredColumns={PREFERRED_COLUMNS.Study_Details}
              />
            ),
          },
          {
            id: "bm_details",
            label: "BM Details",
            count: counts.BM_Details,
            content: (
              <DataTable
                rows={extracted.BM_Details ?? []}
                preferredColumns={PREFERRED_COLUMNS.BM_Details}
              />
            ),
          },
          {
            id: "bm_results",
            label: "BM Results",
            count: counts.BM_Results,
            content: (
              <DataTable
                rows={extracted.BM_Results ?? []}
                preferredColumns={PREFERRED_COLUMNS.BM_Results}
              />
            ),
          },
          {
            id: "inferences",
            label: "Inferences",
            count: counts.Inferences,
            content: (
              <DataTable
                rows={extracted.Inferences ?? []}
                preferredColumns={PREFERRED_COLUMNS.Inferences}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

function SheetTile({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof FileText;
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 flex items-center gap-3">
      <div className="w-9 h-9 rounded-md bg-slate-100 grid place-items-center">
        <Icon className="w-4 h-4 text-slate-600" />
      </div>
      <div className="min-w-0">
        <div className="text-xs text-slate-500">{label}</div>
        <div className="text-lg font-semibold tabular-nums text-slate-900">{value}</div>
      </div>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso.replace(" ", "T") + "Z");
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
