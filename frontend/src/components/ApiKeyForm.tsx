import { useEffect, useState } from "react";
import {
  KeyRound,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Eye,
  EyeOff,
  ExternalLink,
  ShieldCheck,
} from "lucide-react";
import {
  getApiKey,
  setApiKey,
  clearApiKey,
  isRemembered,
  maskedDisplay,
  looksValidShape,
} from "../lib/apiKey";
import { testApiKey, type TestKeyResponse } from "../lib/api";

interface ApiKeyFormProps {
  /** Called after the user successfully saves a working key. */
  onSaved?: () => void;
  /** Hide the "Get a key" external link (e.g. inside a modal). */
  compact?: boolean;
}

type Status =
  | { kind: "idle" }
  | { kind: "testing" }
  | { kind: "ok"; resp: TestKeyResponse }
  | { kind: "error"; resp: TestKeyResponse }
  | { kind: "saved"; resp: TestKeyResponse };

export default function ApiKeyForm({ onSaved, compact = false }: ApiKeyFormProps) {
  const [draft, setDraft] = useState("");
  const [reveal, setReveal] = useState(false);
  const [remember, setRemember] = useState(true);
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [storedKey, setStoredKey] = useState<string | null>(null);

  // Hydrate UI from existing storage on mount
  useEffect(() => {
    const k = getApiKey();
    setStoredKey(k);
    setRemember(isRemembered());
  }, []);

  const hasStored = !!storedKey;

  async function handleTest() {
    const candidate = (draft || storedKey || "").trim();
    if (!candidate) return;
    setStatus({ kind: "testing" });
    try {
      const resp = await testApiKey(candidate);
      setStatus(resp.ok ? { kind: "ok", resp } : { kind: "error", resp });
    } catch (e) {
      setStatus({
        kind: "error",
        resp: { ok: false, message: (e as Error).message },
      });
    }
  }

  async function handleSave() {
    const candidate = draft.trim();
    if (!candidate) return;
    if (!looksValidShape(candidate)) {
      setStatus({
        kind: "error",
        resp: {
          ok: false,
          reason: "invalid",
          message: "Doesn't look like an OpenAI key (should start with sk-).",
        },
      });
      return;
    }
    setStatus({ kind: "testing" });
    let resp: TestKeyResponse;
    try {
      resp = await testApiKey(candidate);
    } catch (e) {
      setStatus({
        kind: "error",
        resp: { ok: false, message: (e as Error).message },
      });
      return;
    }
    if (!resp.ok) {
      setStatus({ kind: "error", resp });
      return;
    }
    // Persist only after the key passes validation.
    setApiKey(candidate, remember);
    setStoredKey(candidate);
    setDraft("");
    setStatus({ kind: "saved", resp });
    onSaved?.();
  }

  function handleClear() {
    clearApiKey();
    setStoredKey(null);
    setDraft("");
    setStatus({ kind: "idle" });
  }

  // ---- render ----
  return (
    <div>
      <label className="block text-xs font-medium text-slate-700 mb-1.5">
        OpenAI API key
      </label>

      <div className="relative">
        <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
        <input
          type={reveal ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          // The browser's password manager won't try to save this; that's
          // intentional. Plus aria-autocomplete=none silences a11y warnings.
          aria-autocomplete="none"
          placeholder={
            hasStored ? maskedDisplay(storedKey) : "sk-proj-..."
          }
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            // Reset transient status while typing
            if (status.kind !== "idle" && status.kind !== "saved") {
              setStatus({ kind: "idle" });
            }
          }}
          className="w-full pl-9 pr-20 py-2 rounded-lg border border-slate-300 bg-white text-sm font-mono focus:border-brand-500 focus:ring-2 focus:ring-brand-100 outline-none"
        />
        <button
          type="button"
          onClick={() => setReveal((v) => !v)}
          className="absolute right-2 top-1/2 -translate-y-1/2 inline-flex items-center gap-1 text-[11px] text-slate-500 hover:text-slate-700 px-2 py-1 rounded"
          aria-label={reveal ? "Hide key" : "Show key"}
        >
          {reveal ? (
            <>
              <EyeOff className="w-3 h-3" /> Hide
            </>
          ) : (
            <>
              <Eye className="w-3 h-3" /> Show
            </>
          )}
        </button>
      </div>

      <label className="mt-3 flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          className="mt-0.5 w-4 h-4 rounded border-slate-300 text-brand-600 focus:ring-brand-500"
          checked={remember}
          onChange={(e) => setRemember(e.target.checked)}
        />
        <div className="text-xs">
          <div className="font-medium text-slate-900">
            Remember this key in my browser
          </div>
          <div className="text-slate-500 leading-snug">
            On = persists across sessions (localStorage). Off = forgotten when
            you close the tab (sessionStorage).
          </div>
        </div>
      </label>

      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleSave}
          disabled={!draft.trim() || status.kind === "testing"}
          className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-gradient-to-r from-brand-600 to-brand-700 hover:from-brand-700 hover:to-brand-800 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
        >
          {status.kind === "testing" ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Testing…
            </>
          ) : (
            <>Save & verify</>
          )}
        </button>
        <button
          type="button"
          onClick={handleTest}
          disabled={(!draft.trim() && !hasStored) || status.kind === "testing"}
          className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium disabled:opacity-50"
        >
          Test
        </button>
        {hasStored && (
          <button
            type="button"
            onClick={handleClear}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-rose-200 bg-white hover:bg-rose-50 text-rose-700 text-sm font-medium ml-auto"
          >
            Clear key
          </button>
        )}
      </div>

      {/* Status messages */}
      {status.kind === "ok" && (
        <StatusBanner
          tone="info"
          icon={CheckCircle2}
          title="Key works"
          body={
            status.resp.model_available
              ? `${status.resp.default_model} is available on this key.`
              : `${status.resp.models_count ?? 0} model${
                  (status.resp.models_count ?? 0) === 1 ? "" : "s"
                } visible. Click "Save & verify" to keep it.`
          }
        />
      )}

      {status.kind === "saved" && (
        <StatusBanner
          tone="success"
          icon={CheckCircle2}
          title={`Saved · ${status.resp.key_masked}`}
          body="Key stored in your browser. The server never persists it."
        />
      )}

      {status.kind === "error" && (
        <StatusBanner
          tone="error"
          icon={AlertTriangle}
          title={
            status.resp.reason === "invalid"
              ? "Key rejected by OpenAI"
              : status.resp.reason === "missing"
              ? "Missing key"
              : status.resp.reason === "network"
              ? "Network error"
              : "Could not verify"
          }
          body={status.resp.message ?? "Unknown error."}
        />
      )}

      {/* Helper / privacy footer */}
      <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50/60 px-3 py-2.5 text-[11px] text-slate-600 leading-relaxed">
        <div className="flex items-start gap-2">
          <ShieldCheck className="w-3.5 h-3.5 text-emerald-600 mt-0.5 shrink-0" />
          <div>
            <span className="font-medium text-slate-800">
              Stored only in your browser.
            </span>{" "}
            Sent as a request header (TLS-encrypted) on each upload. The
            server never persists your key — not in databases, files, or logs.
            Anyone with access to your browser can read it.
            {!compact && (
              <>
                <br />
                <a
                  href="https://platform.openai.com/api-keys"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-0.5 text-brand-700 hover:text-brand-800 mt-1.5"
                >
                  Get a key at platform.openai.com{" "}
                  <ExternalLink className="w-3 h-3" />
                </a>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatusBanner({
  tone,
  icon: Icon,
  title,
  body,
}: {
  tone: "info" | "success" | "error";
  icon: typeof CheckCircle2;
  title: string;
  body: string;
}) {
  const cls =
    tone === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : tone === "error"
      ? "border-rose-200 bg-rose-50 text-rose-800"
      : "border-brand-200 bg-brand-50 text-brand-800";
  const iconColor =
    tone === "success"
      ? "text-emerald-600"
      : tone === "error"
      ? "text-rose-600"
      : "text-brand-600";
  return (
    <div className={`mt-3 rounded-lg border ${cls} px-3 py-2 flex items-start gap-2 text-sm`}>
      <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${iconColor}`} />
      <div className="min-w-0">
        <div className="font-medium">{title}</div>
        <div className="text-xs mt-0.5 opacity-90 leading-snug">{body}</div>
      </div>
    </div>
  );
}
