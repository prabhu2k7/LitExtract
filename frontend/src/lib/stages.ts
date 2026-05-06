// Mirrors the server-side PIPELINE_STAGES constant. Used as a static fallback
// when /api/stages hasn't been fetched yet, and to render the friendly stage
// label + cumulative percent progress.

export const STAGE_DEFS: Array<{ name: string; label: string; cum_pct: number }> = [
  { name: "queued",                   label: "Queued",                  cum_pct: 0   },
  { name: "parsing_pdf",              label: "Reading PDF",             cum_pct: 3   },
  { name: "classifying",              label: "Classifying study",      cum_pct: 5   },
  { name: "extracting_study_details", label: "Extracting study details", cum_pct: 20 },
  { name: "extracting_bm_details",    label: "Extracting biomarkers",   cum_pct: 35 },
  { name: "extracting_bm_results",    label: "Extracting results",      cum_pct: 70 },
  { name: "extracting_inferences",    label: "Extracting inferences",   cum_pct: 95 },
  { name: "writing_excel",            label: "Compiling output",        cum_pct: 100 },
  { name: "done",                     label: "Complete",                cum_pct: 100 },
  { name: "cached",                   label: "Cached",                  cum_pct: 100 },
];

export function stageLabel(name: string | null | undefined): string {
  const hit = STAGE_DEFS.find((s) => s.name === name);
  return hit?.label ?? (name ?? "Working");
}

export function stagePct(name: string | null | undefined): number {
  const hit = STAGE_DEFS.find((s) => s.name === name);
  return hit?.cum_pct ?? 0;
}

export function fmtDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  const s = Math.round(ms / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rest = s % 60;
  return rest === 0 ? `${m}m` : `${m}m ${rest}s`;
}

/**
 * ETA estimate based on rolling average duration and how long this run has
 * already been running. Returns null when avg is unknown.
 */
export function estimateRemainingMs(
  avgDurationMs: number | null | undefined,
  elapsedMs: number | null | undefined,
  progressPct: number | null | undefined
): number | null {
  if (!avgDurationMs) return null;
  const elapsed = elapsedMs ?? 0;

  // Two estimates, pick the more conservative:
  //   1) avg - elapsed
  //   2) elapsed * (100 - pct) / pct  (extrapolate from how far we are)
  const fromAvg = Math.max(0, avgDurationMs - elapsed);
  let fromProgress: number | null = null;
  if (progressPct && progressPct > 5 && progressPct < 95 && elapsed > 0) {
    fromProgress = Math.max(0, (elapsed * (100 - progressPct)) / progressPct);
  }
  if (fromProgress == null) return fromAvg;
  return Math.max(fromAvg, fromProgress);
}
