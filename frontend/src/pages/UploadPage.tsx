import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  UploadCloud,
  FileText,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  X,
  Loader2,
  FileWarning,
  Info,
  Database,
  RotateCw,
  Sparkles,
  Lock,
} from "lucide-react";
import {
  uploadPdf,
  getStatus,
  getEta,
  type JobState,
  type UploadResponse,
  type StatusResponse,
} from "../lib/api";
import { hasApiKey, clearApiKey } from "../lib/apiKey";
import { stageLabel, stagePct, fmtDuration, estimateRemainingMs } from "../lib/stages";
import Pill from "../components/Pill";
import { useToast } from "../components/Toast";
import ApiKeyModal from "../components/ApiKeyModal";

type ItemPhase = "uploading" | "queued" | "processing" | "complete" | "failed" | "error";

type QueueItem = {
  localId: string;
  file: File;
  upload?: UploadResponse;
  status?: StatusResponse;
  error?: string;
};

const POLL_MS = 1500;

export default function UploadPage() {
  const [queue, setQueue] = useState<QueueItem[]>([]);
  const [forceRerun, setForceRerun] = useState(false);
  const [trainingMode, setTrainingMode] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  // Files held in waiting when we discover the key is missing — once the user
  // saves a working key, we re-enqueue them automatically.
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [keyModalOpen, setKeyModalOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const toast = useToast();
  const batchToastedRef = useRef(false);

  // Rolling-average ETA from history
  const { data: etaInfo } = useQuery({
    queryKey: ["eta"],
    queryFn: getEta,
    refetchInterval: 30_000,
  });

  const updateItem = useCallback(
    (localId: string, patch: Partial<QueueItem>) => {
      setQueue((q) =>
        q.map((it) => (it.localId === localId ? { ...it, ...patch } : it))
      );
    },
    []
  );

  const runItem = useCallback(
    async (localId: string, file: File, opts: { forceRerun: boolean; trainingMode: boolean }) => {
      try {
        const upload = await uploadPdf(file, opts);
        updateItem(localId, { upload });
        // Already complete from cache hit?
        if (upload.cached || upload.state === "complete") {
          const s = await getStatus(upload.display_id);
          updateItem(localId, { status: s });
          return;
        }
        // Poll until terminal
        for (;;) {
          const s = await getStatus(upload.display_id);
          updateItem(localId, { status: s });
          if (s.state === "complete" || s.state === "failed") break;
          await new Promise((r) => setTimeout(r, POLL_MS));
        }
      } catch (e) {
        const err = e as Error & { status?: number };
        // 401 -> bad/missing key. Clear stored key and re-prompt the user.
        if (err.status === 401) {
          clearApiKey();
          setPendingFiles((prev) => [...prev, file]);
          setQueue((q) => q.filter((it) => it.localId !== localId));
          setKeyModalOpen(true);
          toast.info(
            "API key required",
            "Enter a valid OpenAI key to continue."
          );
          return;
        }
        updateItem(localId, { error: err.message });
      }
    },
    [updateItem, toast]
  );

  const enqueue = useCallback(
    (files: FileList | File[] | null | undefined) => {
      if (!files) return;
      const accepted: File[] = [];
      for (const f of Array.from(files)) {
        if (!f.name.toLowerCase().endsWith(".pdf")) continue;
        accepted.push(f);
      }
      if (accepted.length === 0) return;

      // Block at file-drop time if no key is set. Stash the files and pop modal.
      if (!hasApiKey()) {
        setPendingFiles((prev) => [...prev, ...accepted]);
        setKeyModalOpen(true);
        return;
      }

      const next: QueueItem[] = accepted.map((file) => ({
        localId: `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        file,
      }));
      setQueue((q) => [...q, ...next]);
      batchToastedRef.current = false;
      const opts = { forceRerun, trainingMode };
      for (const it of next) runItem(it.localId, it.file, opts);
    },
    [forceRerun, trainingMode, runItem]
  );

  // After the user saves a key in the modal, re-enqueue any files that were
  // dropped before they had a key configured.
  const handleKeySaved = useCallback(() => {
    const files = pendingFiles;
    setPendingFiles([]);
    setKeyModalOpen(false);
    if (files.length === 0) return;
    const next: QueueItem[] = files.map((file) => ({
      localId: `q_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      file,
    }));
    setQueue((q) => [...q, ...next]);
    batchToastedRef.current = false;
    const opts = { forceRerun, trainingMode };
    for (const it of next) runItem(it.localId, it.file, opts);
  }, [pendingFiles, forceRerun, trainingMode, runItem]);

  // Toast once when ALL queue items have settled
  useEffect(() => {
    if (queue.length === 0) return;
    const allDone = queue.every(
      (q) =>
        q.status?.state === "complete" ||
        q.status?.state === "failed" ||
        q.error
    );
    if (allDone && !batchToastedRef.current) {
      batchToastedRef.current = true;
      const ok = queue.filter((q) => q.status?.state === "complete").length;
      const failed = queue.length - ok;
      const totalCost = queue.reduce(
        (sum, q) => sum + (q.status?.cost?.cost_usd ?? 0),
        0
      );
      if (ok && !failed) {
        toast.success(
          `${ok} extraction${ok > 1 ? "s" : ""} complete`,
          totalCost > 0 ? `Total cost · $${totalCost.toFixed(4)}` : undefined
        );
      } else if (ok && failed) {
        toast.info(
          `${ok} done · ${failed} failed`,
          "Check the failed rows below for details."
        );
      } else if (failed) {
        toast.error(`${failed} extraction${failed > 1 ? "s" : ""} failed`);
      }
    }
  }, [queue, toast]);

  const removeItem = useCallback((localId: string) => {
    setQueue((q) => q.filter((it) => it.localId !== localId));
  }, []);

  const completed = queue.filter((q) => q.status?.state === "complete");
  const allDone =
    queue.length > 0 &&
    queue.every(
      (q) => q.status?.state === "complete" || q.status?.state === "failed" || q.error
    );

  return (
    <div className="max-w-4xl mx-auto fade-in">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-slate-900 tracking-tight">
          Extract biomarker data from research papers
        </h1>
        <p className="mt-1.5 text-sm text-slate-500">
          Drop one or more PDFs. Files named after PubMed IDs (e.g.{" "}
          <code className="text-[12px] bg-slate-100 rounded px-1 py-0.5 font-mono">
            12345678.pdf
          </code>
          ) are auto-detected.
        </p>
      </div>

      {/* Options strip */}
      <div className="rounded-xl border border-slate-200 bg-white p-4 mb-4 flex flex-wrap items-start gap-x-6 gap-y-3">
        <CheckboxOption
          checked={forceRerun}
          onChange={setForceRerun}
          icon={<RotateCw className="w-3.5 h-3.5" />}
          label="Force re-extract"
          help="Bypass the SHA256 cache. Re-runs extraction even if this PDF was already processed."
        />
        <CheckboxOption
          checked={trainingMode}
          onChange={setTrainingMode}
          disabled
          icon={<Sparkles className="w-3.5 h-3.5" />}
          label={
            <span className="inline-flex items-center gap-1.5">
              Training mode
              <Lock className="w-3 h-3 text-slate-400" />
            </span>
          }
          help="Improves prompts using a gold standard (max 2 cycles). Available once gold-standard upload ships."
        />
      </div>

      {/* Dropzone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          enqueue(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`relative cursor-pointer rounded-2xl border-2 border-dashed bg-white p-10 text-center transition-colors ${
          dragOver
            ? "border-brand-500 bg-brand-50/50"
            : "border-slate-300 hover:border-brand-400 hover:bg-brand-50/30"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="hidden"
          onChange={(e) => enqueue(e.target.files)}
        />
        <div className="mx-auto w-12 h-12 rounded-full bg-brand-100 grid place-items-center">
          <UploadCloud className="w-6 h-6 text-brand-600" />
        </div>
        <div className="mt-4 text-base font-medium text-slate-900">
          Drop PDFs here, or click to browse
        </div>
        <div className="mt-1 text-xs text-slate-500">
          Multiple files · max ~30MB each
          {etaInfo?.avg_duration_ms && (
            <>
              {" · "}typical run {fmtDuration(etaInfo.avg_duration_ms)} ({etaInfo.samples} samples)
            </>
          )}
        </div>
      </div>

      {/* Queue */}
      {queue.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-sm font-medium text-slate-900">
              {completed.length} / {queue.length} complete
            </div>
            {allDone && (
              <button
                type="button"
                onClick={() => setQueue([])}
                className="text-xs text-slate-500 hover:text-slate-700"
              >
                Clear queue
              </button>
            )}
          </div>

          {queue.map((item) => (
            <QueueRow
              key={item.localId}
              item={item}
              avgMs={etaInfo?.avg_duration_ms ?? null}
              onView={(id) => navigate(`/results/${id}`)}
              onRemove={() => removeItem(item.localId)}
            />
          ))}
        </div>
      )}

      <ApiKeyModal
        open={keyModalOpen}
        onClose={() => setKeyModalOpen(false)}
        onSaved={handleKeySaved}
        title={
          pendingFiles.length > 0
            ? `OpenAI API key needed for ${pendingFiles.length} file${pendingFiles.length === 1 ? "" : "s"}`
            : "OpenAI API key required"
        }
      />
    </div>
  );
}

function CheckboxOption({
  checked,
  onChange,
  icon,
  label,
  help,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  icon: React.ReactNode;
  label: React.ReactNode;
  help: string;
  disabled?: boolean;
}) {
  return (
    <label
      className={`flex items-start gap-2 cursor-pointer ${
        disabled ? "opacity-50 cursor-not-allowed" : ""
      }`}
    >
      <input
        type="checkbox"
        className="mt-0.5 w-4 h-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <div className="text-sm">
        <div className="flex items-center gap-1.5 font-medium text-slate-900">
          {icon}
          {label}
        </div>
        <div className="text-[11px] text-slate-500 leading-snug max-w-xs">{help}</div>
      </div>
    </label>
  );
}

function QueueRow({
  item,
  avgMs,
  onView,
  onRemove,
}: {
  item: QueueItem;
  avgMs: number | null;
  onView: (displayId: string) => void;
  onRemove: () => void;
}) {
  const upload = item.upload;
  const status = item.status;
  const phase: ItemPhase = item.error
    ? "error"
    : (status?.state as ItemPhase) ?? (upload ? "queued" : "uploading");

  const isCacheHit = upload?.cached === true;
  const isComplete = phase === "complete";
  const isFailed = phase === "failed" || phase === "error";
  const isWorking = phase === "uploading" || phase === "queued" || phase === "processing";

  // Progress + ETA
  const progressPct = stagePct(status?.stage);
  const stageText = stageLabel(status?.stage);
  const elapsedMs = status?.elapsed_ms ?? null;
  const remainingMs = estimateRemainingMs(avgMs, elapsedMs, progressPct);

  return (
    <div
      className={`rounded-xl border bg-white card-hover overflow-hidden ${
        isComplete
          ? "border-emerald-200"
          : isFailed
          ? "border-rose-200"
          : "border-slate-200"
      }`}
    >
      <div className="p-4">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-start gap-3 min-w-0 flex-1">
            <div
              className={`w-9 h-9 shrink-0 rounded-md grid place-items-center ${
                isComplete
                  ? "bg-emerald-100 text-emerald-700"
                  : isFailed
                  ? "bg-rose-100 text-rose-700"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {isComplete ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : isFailed ? (
                <AlertTriangle className="w-4 h-4" />
              ) : (
                <FileText className="w-4 h-4" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div
                className="text-sm font-medium text-slate-900 truncate"
                title={item.file.name}
              >
                {item.file.name}
              </div>
              <div className="mt-0.5 text-[11px] text-slate-500 flex items-center gap-2 flex-wrap">
                <span>{(item.file.size / 1024).toFixed(1)} KB</span>
                {upload?.display_id && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span className="font-mono">{upload.display_id}</span>
                  </>
                )}
                {upload?.pmid && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span>PMID {upload.pmid}</span>
                  </>
                )}
                {isCacheHit && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span
                      className="inline-flex items-center gap-1 text-brand-700"
                      title={`Cache hit — same content as ${upload?.cached_from?.display_id}`}
                    >
                      <Database className="w-3 h-3" />
                      cached
                    </span>
                  </>
                )}
                {!isCacheHit && upload?.duplicate_of && (
                  <>
                    <span className="text-slate-300">·</span>
                    <span
                      className="inline-flex items-center gap-1 text-amber-700"
                      title={`Same content as ${upload.duplicate_of.display_id}`}
                    >
                      <FileWarning className="w-3 h-3" />
                      duplicate
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <StateBadge phase={phase} cached={isCacheHit} />
            {(isComplete || isFailed) && (
              <button
                type="button"
                onClick={onRemove}
                className="text-slate-400 hover:text-slate-600"
                aria-label="Remove from queue"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Active progress */}
        {isWorking && (
          <div className="mt-4">
            <div className="flex items-center justify-between text-[11px] text-slate-600 mb-1.5">
              <div className="inline-flex items-center gap-1.5">
                <Loader2 className="w-3 h-3 animate-spin text-brand-600" />
                <span className="font-medium text-slate-800">{stageText}</span>
              </div>
              <div className="tabular-nums font-mono">
                {elapsedMs != null ? fmtDuration(elapsedMs) : "—"}
                {remainingMs != null && remainingMs > 1000 && (
                  <>
                    {" · "}~{fmtDuration(remainingMs)} left
                  </>
                )}
              </div>
            </div>
            <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-brand-500 to-brand-600 transition-all duration-500"
                style={{ width: `${Math.max(2, progressPct)}%` }}
              />
            </div>
          </div>
        )}

        {/* Failure */}
        {isFailed && (
          <div className="mt-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-md px-3 py-2">
            {item.error || status?.error || "Extraction failed."}
          </div>
        )}
      </div>

      {/* Success footer with explicit nav */}
      {isComplete && upload?.display_id && (
        <div className="border-t border-emerald-100 bg-emerald-50/50 px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="text-xs text-slate-700 flex items-center gap-3 flex-wrap">
            {status?.counts && (
              <>
                <span>
                  <span className="font-semibold tabular-nums">
                    {status.counts.Study_Details +
                      status.counts.BM_Details +
                      status.counts.BM_Results +
                      status.counts.Inferences}
                  </span>{" "}
                  rows
                </span>
                <span className="text-slate-300">·</span>
                <span>
                  {status.counts.BM_Details} biomarker
                  {status.counts.BM_Details === 1 ? "" : "s"}
                </span>
                <span className="text-slate-300">·</span>
                <span>{status.counts.BM_Results} results</span>
              </>
            )}
            {status?.cost?.cost_usd != null && (
              <>
                <span className="text-slate-300">·</span>
                <span className="tabular-nums">${status.cost.cost_usd.toFixed(4)}</span>
              </>
            )}
            {elapsedMs != null && elapsedMs > 0 && (
              <>
                <span className="text-slate-300">·</span>
                <span className="tabular-nums">{fmtDuration(elapsedMs)}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <a
              href={`/api/download/${encodeURIComponent(upload.display_id)}`}
              className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-brand-700 px-2.5 py-1.5"
            >
              Download Excel
            </a>
            <button
              type="button"
              onClick={() => onView(upload.display_id)}
              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md text-xs font-medium bg-gradient-to-r from-brand-600 to-brand-700 text-white hover:from-brand-700 hover:to-brand-800"
            >
              View results <ArrowRight className="w-3 h-3" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function StateBadge({ phase, cached }: { phase: ItemPhase; cached?: boolean }) {
  if (phase === "complete" && cached)
    return (
      <Pill tone="brand">
        <Database className="w-3 h-3" /> Cached
      </Pill>
    );
  if (phase === "complete")
    return (
      <Pill tone="emerald">
        <CheckCircle2 className="w-3 h-3" /> Complete
      </Pill>
    );
  if (phase === "failed" || phase === "error")
    return (
      <Pill tone="rose">
        <AlertTriangle className="w-3 h-3" /> Failed
      </Pill>
    );
  if (phase === "processing")
    return (
      <Pill tone="brand">
        <Loader2 className="w-3 h-3 animate-spin" /> Processing
      </Pill>
    );
  if (phase === "uploading")
    return (
      <Pill tone="slate">
        <Loader2 className="w-3 h-3 animate-spin" /> Uploading
      </Pill>
    );
  return (
    <Pill tone="amber">
      <Info className="w-3 h-3" /> Queued
    </Pill>
  );
}
