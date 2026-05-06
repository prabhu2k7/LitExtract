import { Fragment, useMemo, useState } from "react";
import { ChevronDown, ChevronRight, Quote } from "lucide-react";

interface DataTableProps {
  rows: Array<Record<string, unknown>>;
  preferredColumns?: string[];
  emptyMessage?: string;
}

const SOURCE_FIELDS = ["source_excerpt", "source_section"];

function fmtCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  if (typeof v === "object") {
    try {
      return JSON.stringify(v);
    } catch {
      return String(v);
    }
  }
  return String(v);
}

function humanColumn(name: string): string {
  return name
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export default function DataTable({
  rows,
  preferredColumns,
  emptyMessage = "No rows extracted.",
}: DataTableProps) {
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});

  const columns = useMemo(() => {
    const seen = new Set<string>(SOURCE_FIELDS); // hide source_* from main grid
    const ordered: string[] = [];
    if (preferredColumns) {
      for (const c of preferredColumns) {
        if (!seen.has(c)) {
          seen.add(c);
          ordered.push(c);
        }
      }
    }
    for (const r of rows) {
      for (const k of Object.keys(r)) {
        if (!seen.has(k)) {
          seen.add(k);
          ordered.push(k);
        }
      }
    }
    return ordered;
  }, [rows, preferredColumns]);

  const hasAnySource = useMemo(
    () => rows.some((r) => fmtCell(r.source_excerpt) || fmtCell(r.source_section)),
    [rows]
  );

  if (!rows || rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-white p-10 text-center">
        <div className="text-sm text-slate-500">{emptyMessage}</div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              {hasAnySource && (
                <th className="w-8 px-2 py-2.5 border-b border-slate-200" />
              )}
              {columns.map((c) => (
                <th
                  key={c}
                  className="text-left font-medium px-3 py-2.5 whitespace-nowrap border-b border-slate-200"
                >
                  {humanColumn(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => {
              const sourceExcerpt = fmtCell(r.source_excerpt);
              const sourceSection = fmtCell(r.source_section);
              const hasSource = !!(sourceExcerpt || sourceSection);
              const isOpen = expanded[i] ?? false;
              return (
                <Fragment key={i}>
                  <tr className="border-b border-slate-100 last:border-b-0 hover:bg-slate-50/60">
                    {hasAnySource && (
                      <td className="px-2 py-2.5 align-top">
                        {hasSource ? (
                          <button
                            type="button"
                            onClick={() =>
                              setExpanded((s) => ({ ...s, [i]: !isOpen }))
                            }
                            className="text-slate-400 hover:text-brand-700"
                            aria-label={isOpen ? "Hide source" : "Show source"}
                            title="Show source quote"
                          >
                            {isOpen ? (
                              <ChevronDown className="w-3.5 h-3.5" />
                            ) : (
                              <ChevronRight className="w-3.5 h-3.5" />
                            )}
                          </button>
                        ) : null}
                      </td>
                    )}
                    {columns.map((c) => {
                      const val = fmtCell(r[c]);
                      return (
                        <td
                          key={c}
                          className="px-3 py-2.5 text-slate-700 align-top max-w-[24rem]"
                          title={val}
                        >
                          <div className="truncate">
                            {val || <span className="text-slate-300">—</span>}
                          </div>
                        </td>
                      );
                    })}
                  </tr>
                  {hasAnySource && hasSource && isOpen && (
                    <tr className="bg-brand-50/30 border-b border-slate-100 last:border-b-0">
                      <td />
                      <td colSpan={columns.length} className="px-3 py-3">
                        <div className="flex items-start gap-2">
                          <Quote className="w-3.5 h-3.5 text-brand-600 mt-1 shrink-0" />
                          <div className="flex-1 min-w-0">
                            <div className="text-[11px] uppercase tracking-wide text-brand-700 font-semibold">
                              Source
                              {sourceSection && (
                                <span className="ml-1 text-slate-500 normal-case font-normal">
                                  · {sourceSection}
                                </span>
                              )}
                            </div>
                            <div className="mt-1 text-sm text-slate-800 italic leading-relaxed">
                              {sourceExcerpt || (
                                <span className="text-slate-400">
                                  No quote provided.
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
