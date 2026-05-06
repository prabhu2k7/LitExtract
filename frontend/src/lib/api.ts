// Thin fetch wrappers for the FastAPI backend. Vite dev proxy forwards /api -> :8765.

import { authHeaders } from "./apiKey";

export type JobState = "queued" | "processing" | "complete" | "failed";

export interface DuplicateRef {
  upload_id: string;
  display_id: string;
  original_filename: string;
  uploaded_at: string;
}

export interface UploadResponse {
  paper_id: string;        // alias of display_id, for legacy code paths
  display_id: string;
  upload_id: string;
  pmid: string | null;
  filename: string;
  size_bytes: number;
  state: JobState;
  cached?: boolean;
  cached_from?: { display_id: string; uploaded_at: string } | null;
  training_mode?: boolean;
  force_rerun?: boolean;
  duplicate_of?: DuplicateRef | null;
}

export interface UploadOptions {
  forceRerun?: boolean;
  trainingMode?: boolean;
}

export interface Classification {
  disease: string | null;
  disease_confidence: number;
  confidence_level: string;
  study_types: string[];
  bm_types: string[];
}

export interface CostTotals {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

export interface SheetCounts {
  Study_Details: number;
  BM_Details: number;
  BM_Results: number;
  Inferences: number;
}

export interface StatusResponse {
  paper_id: string;
  display_id: string;
  upload_id: string | null;
  pmid: string | null;
  filename: string | null;
  state: JobState;
  stage: string;
  stage_label?: string;
  progress_pct?: number;
  elapsed_ms?: number | null;
  updated_at?: string;
  counts?: SheetCounts;
  classification?: Classification;
  cost?: CostTotals;
  error?: string;
}

export interface StageInfo {
  name: string;
  label: string;
  share_pct: number;
  cum_pct: number;
}

export interface StagesResponse {
  stages: StageInfo[];
}

export interface EtaResponse {
  avg_duration_ms: number | null;
  min_duration_ms?: number;
  max_duration_ms?: number;
  samples: number;
  window: number;
}

export type SheetName = "Study_Details" | "BM_Details" | "BM_Results" | "Inferences";

export interface ResultsResponse {
  paper_id: string;
  display_id: string;
  upload_id: string | null;
  pmid: string | null;
  filename: string | null;
  uploaded_at?: string;
  completed_at?: string;
  duration_ms?: number;
  extracted: Record<SheetName, Array<Record<string, unknown>>>;
  counts: SheetCounts;
  meta: {
    run_id?: string;
    run_datetime?: string;
    llm_model?: string;
    disease?: string;
    study_types?: string[];
    bm_types?: string[];
    confidence?: string;
    extraction_cost_usd?: number;
    extraction_input_tokens?: number;
    extraction_output_tokens?: number;
    [k: string]: unknown;
  };
}

export interface HistoryItem {
  display_id: string;
  upload_id: string;
  pmid: string | null;
  filename: string | null;
  state: JobState;
  uploaded_at: string;
  completed_at: string | null;
  duration_ms: number | null;
  disease: string | null;
  study_types: string[];
  bm_types: string[];
  confidence: string | null;
  model: string | null;
  study_details_count: number | null;
  bm_details_count: number | null;
  bm_results_count: number | null;
  inferences_count: number | null;
  extraction_cost_usd: number | null;
  error_message: string | null;
}

export interface HistoryResponse {
  items: HistoryItem[];
  count: number;
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (body?.detail) detail = body.detail;
    } catch {
      /* ignore */
    }
    const err = new Error(detail) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

export async function uploadPdf(
  file: File,
  opts: UploadOptions = {}
): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);
  if (opts.forceRerun) fd.append("force_rerun", "true");
  if (opts.trainingMode) fd.append("training_mode", "true");
  const res = await fetch("/api/upload", {
    method: "POST",
    body: fd,
    headers: { ...authHeaders() },
  });
  return jsonOrThrow<UploadResponse>(res);
}

// ---- API-key validation -----------------------------------------------

export interface TestKeyResponse {
  ok: boolean;
  reason?: "missing" | "invalid" | "openai_error" | "network";
  message?: string;
  key_masked?: string;
  default_model?: string;
  model_available?: boolean;
  models_count?: number;
}

/**
 * Validate the supplied API key against OpenAI without consuming meaningful
 * tokens (hits /v1/models). Always resolves with a result object — even on
 * network or auth errors — so callers don't need try/catch for routine flows.
 */
export async function testApiKey(key?: string): Promise<TestKeyResponse> {
  const headers: Record<string, string> = {};
  if (key) headers["X-OpenAI-Api-Key"] = key;
  else Object.assign(headers, authHeaders());
  const res = await fetch("/api/test-key", { method: "POST", headers });
  return jsonOrThrow<TestKeyResponse>(res);
}

export async function getStages(): Promise<StagesResponse> {
  const res = await fetch("/api/stages");
  return jsonOrThrow<StagesResponse>(res);
}

export async function getEta(): Promise<EtaResponse> {
  const res = await fetch("/api/eta");
  return jsonOrThrow<EtaResponse>(res);
}

export async function getStatus(paperId: string): Promise<StatusResponse> {
  const res = await fetch(`/api/status/${encodeURIComponent(paperId)}`);
  return jsonOrThrow<StatusResponse>(res);
}

export async function getResults(paperId: string): Promise<ResultsResponse> {
  const res = await fetch(`/api/results/${encodeURIComponent(paperId)}`);
  return jsonOrThrow<ResultsResponse>(res);
}

export async function getHistory(): Promise<HistoryResponse> {
  const res = await fetch("/api/history");
  return jsonOrThrow<HistoryResponse>(res);
}

export function downloadUrl(paperId: string): string {
  return `/api/download/${encodeURIComponent(paperId)}`;
}

export function downloadCsvUrl(paperId: string): string {
  return `/api/download/${encodeURIComponent(paperId)}/findings.csv`;
}

export function downloadJsonUrl(paperId: string): string {
  return `/api/download/${encodeURIComponent(paperId)}/json`;
}

// ---- Biomarkers (corpus-level aggregation) -----------------------------

export interface BiomarkerResultRow {
  pubmed_id: string;
  outcome_name: string | null;
  statistical_test: string | null;
  value_type: string | null;
  r_value: string | number | null;
  r_ci_lower: string | number | null;
  r_ci_upper: string | number | null;
  p_value_prefix: string | null;
  p_value: string | number | null;
  significance_call: string | null;
  br_application: string | null;
  specimen: string | null;
  methodology_technique: string | null;
}

export interface BiomarkerInferenceRow {
  pubmed_id: string;
  br_application: string | null;
  evidence_statement: string | null;
  bm_outcome: string | null;
  source_excerpt: string | null;
  source_section: string | null;
}

export interface BiomarkerItem {
  canonical_name: string;
  display_name: string;
  biomarker_name_std: string | null;
  biomarker_type: string | null;
  biomarker_nature: string | null;
  paper_ids: string[];
  paper_count: number;
  diseases: string[];
  outcomes: string[];
  applications: string[];
  result_rows: number;
  significant_results: number;
  significance_rate_pct: number | null;
  first_seen: string | null;
  last_seen: string | null;
  results: BiomarkerResultRow[];
  inferences: BiomarkerInferenceRow[];
}

export interface BiomarkersResponse {
  items: BiomarkerItem[];
  count: number;
  papers_scanned: number;
}

export async function getBiomarkers(): Promise<BiomarkersResponse> {
  const res = await fetch("/api/biomarkers");
  return jsonOrThrow<BiomarkersResponse>(res);
}
