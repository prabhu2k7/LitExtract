import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Inbox, Download, FileText, AlertCircle } from "lucide-react";
import { getHistory, downloadUrl } from "../lib/api";
import Spinner from "../components/Spinner";
import Pill from "../components/Pill";

export default function HistoryPage() {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["history"],
    queryFn: getHistory,
    refetchInterval: 5000,
  });

  return (
    <div className="max-w-7xl mx-auto fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Extraction history
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          All papers processed in this workspace.
        </p>
      </div>

      {isLoading && (
        <div className="grid place-items-center h-40">
          <Spinner label="Loading history…" />
        </div>
      )}

      {isError && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-5 text-rose-800">
          <div className="font-medium">Could not load history</div>
          <div className="text-sm mt-1">{(error as Error | undefined)?.message}</div>
        </div>
      )}

      {data && data.items.length === 0 && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-12 text-center">
          <div className="mx-auto w-12 h-12 rounded-full bg-slate-100 grid place-items-center">
            <Inbox className="w-5 h-5 text-slate-500" />
          </div>
          <div className="mt-3 text-sm font-medium text-slate-900">
            No extractions yet
          </div>
          <div className="mt-1 text-xs text-slate-500">
            Upload your first PDF to populate this list.
          </div>
          <Link
            to="/upload"
            className="mt-4 inline-flex items-center gap-1 text-sm font-medium text-brand-700 hover:text-brand-800"
          >
            Go to Upload <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      )}

      {data && data.items.length > 0 && (
        <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-600">
                <tr>
                  <th className="text-left font-medium px-3 py-2.5 border-b border-slate-200">
                    Paper
                  </th>
                  <th className="text-left font-medium px-3 py-2.5 border-b border-slate-200">
                    When
                  </th>
                  <th className="text-left font-medium px-3 py-2.5 border-b border-slate-200">
                    Disease
                  </th>
                  <th className="text-left font-medium px-3 py-2.5 border-b border-slate-200">
                    Tags
                  </th>
                  <th className="text-right font-medium px-3 py-2.5 border-b border-slate-200">
                    Study
                  </th>
                  <th className="text-right font-medium px-3 py-2.5 border-b border-slate-200">
                    BM·D
                  </th>
                  <th className="text-right font-medium px-3 py-2.5 border-b border-slate-200">
                    BM·R
                  </th>
                  <th className="text-right font-medium px-3 py-2.5 border-b border-slate-200">
                    Infer
                  </th>
                  <th className="text-right font-medium px-3 py-2.5 border-b border-slate-200">
                    Cost
                  </th>
                  <th className="text-right font-medium px-3 py-2.5 border-b border-slate-200"></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((it) => (
                  <tr
                    key={it.upload_id || it.display_id}
                    className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/60"
                  >
                    <td className="px-3 py-2.5 align-top max-w-[22rem]">
                      <div className="flex items-start gap-2 min-w-0">
                        <div className="w-7 h-7 shrink-0 rounded-md bg-slate-100 grid place-items-center mt-0.5">
                          <FileText className="w-3.5 h-3.5 text-slate-600" />
                        </div>
                        <div className="min-w-0">
                          <Link
                            to={`/results/${encodeURIComponent(it.display_id)}`}
                            className="block text-brand-700 hover:text-brand-800 font-medium truncate"
                            title={it.filename ?? it.display_id}
                          >
                            {it.filename ?? it.display_id}
                          </Link>
                          <div className="mt-0.5 text-[11px] text-slate-500 font-mono flex items-center gap-2">
                            <span title="Display ID — used in URLs and Excel">
                              {it.display_id}
                            </span>
                            {it.pmid && (
                              <span
                                className="px-1.5 rounded bg-brand-50 text-brand-700"
                                title="Detected PubMed ID"
                              >
                                PMID {it.pmid}
                              </span>
                            )}
                          </div>
                          {it.state === "failed" && (
                            <div className="mt-1 text-[11px] text-rose-700 flex items-center gap-1">
                              <AlertCircle className="w-3 h-3" /> failed
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 align-top text-slate-700 whitespace-nowrap">
                      {formatDate(it.uploaded_at)}
                    </td>
                    <td className="px-3 py-2.5 align-top">
                      {it.disease ? (
                        <Pill tone="brand">{it.disease.replace(/_/g, " ")}</Pill>
                      ) : (
                        <span className="text-slate-300">—</span>
                      )}
                    </td>
                    <td className="px-3 py-2.5 align-top">
                      <div className="flex flex-wrap gap-1">
                        {(it.study_types ?? []).map((t) => (
                          <Pill key={t} tone="slate">
                            {t.replace(/_/g, " ")}
                          </Pill>
                        ))}
                        {(it.bm_types ?? []).map((t) => (
                          <Pill key={t} tone="emerald">
                            {t.replace(/_/g, " ")}
                          </Pill>
                        ))}
                      </div>
                    </td>
                    <td className="px-3 py-2.5 align-top text-right tabular-nums">
                      {it.study_details_count ?? 0}
                    </td>
                    <td className="px-3 py-2.5 align-top text-right tabular-nums">
                      {it.bm_details_count ?? 0}
                    </td>
                    <td className="px-3 py-2.5 align-top text-right tabular-nums">
                      {it.bm_results_count ?? 0}
                    </td>
                    <td className="px-3 py-2.5 align-top text-right tabular-nums">
                      {it.inferences_count ?? 0}
                    </td>
                    <td className="px-3 py-2.5 align-top text-right tabular-nums text-slate-700">
                      {it.extraction_cost_usd != null
                        ? `$${it.extraction_cost_usd.toFixed(4)}`
                        : "—"}
                    </td>
                    <td className="px-3 py-2.5 align-top text-right whitespace-nowrap">
                      {it.state === "complete" ? (
                        <a
                          href={downloadUrl(it.display_id)}
                          className="inline-flex items-center gap-1 text-xs text-slate-600 hover:text-brand-700"
                          title="Download Excel"
                        >
                          <Download className="w-3.5 h-3.5" />
                          Excel
                        </a>
                      ) : (
                        <span className="text-[11px] text-slate-400">
                          {it.state}
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const d = new Date(iso.replace(" ", "T") + "Z");
    if (isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
