// API-key store. The single point of truth for the user's OpenAI key in the
// browser. Audit by grepping for "litextract.openai_key" — these are the only
// places it appears.
//
// SECURITY MODEL
// - Storage: localStorage (default) or sessionStorage (opt-out for shared
//   devices). Plain text — see SECURITY.md for the threat-model rationale.
// - Transit: sent as `X-OpenAI-Api-Key` request header on protected calls only.
// - Server: never persisted; held only in memory for the duration of a request.
//
// External callers should use {get,set,clear,maskedDisplay,authHeaders}.
// Avoid building strings containing the raw key for logging or analytics.

const STORAGE_KEY = "litextract.openai_key";
const REMEMBER_KEY = "litextract.openai_key.remember";

type Storage = typeof window.localStorage;

function pickStorage(remember: boolean): Storage {
  return remember ? window.localStorage : window.sessionStorage;
}

/** Resolve which storage currently holds the key, if any. */
function activeStorage(): Storage | null {
  if (typeof window === "undefined") return null;
  if (window.localStorage.getItem(STORAGE_KEY)) return window.localStorage;
  if (window.sessionStorage.getItem(STORAGE_KEY)) return window.sessionStorage;
  return null;
}

export function getApiKey(): string | null {
  const s = activeStorage();
  if (!s) return null;
  const v = s.getItem(STORAGE_KEY);
  return v && v.trim() ? v.trim() : null;
}

export function hasApiKey(): boolean {
  return getApiKey() !== null;
}

/**
 * Persist the key. `remember=true` -> localStorage (across sessions);
 * `remember=false` -> sessionStorage (forgotten on tab close).
 *
 * Always clears whichever store is NOT being used so we never end up with
 * the same key in both places.
 */
export function setApiKey(key: string, remember: boolean = true): void {
  const trimmed = (key || "").trim();
  if (!trimmed) {
    clearApiKey();
    return;
  }
  const target = pickStorage(remember);
  const other = pickStorage(!remember);
  other.removeItem(STORAGE_KEY);
  target.setItem(STORAGE_KEY, trimmed);
  // Track the persistence choice so the UI can render the right "remember me"
  // state on reload.
  window.localStorage.setItem(REMEMBER_KEY, remember ? "1" : "0");
  notifyKeyChanged();
}

export function clearApiKey(): void {
  window.localStorage.removeItem(STORAGE_KEY);
  window.sessionStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(REMEMBER_KEY);
  notifyKeyChanged();
}

export function isRemembered(): boolean {
  if (typeof window === "undefined") return true;
  // Default: if the key is in localStorage we treat it as remembered.
  if (window.localStorage.getItem(STORAGE_KEY)) return true;
  if (window.sessionStorage.getItem(STORAGE_KEY)) return false;
  return window.localStorage.getItem(REMEMBER_KEY) !== "0";
}

/** Masked form for display in the UI. NEVER log the unmasked value. */
export function maskedDisplay(key: string | null | undefined): string {
  if (!key) return "no key set";
  const trimmed = key.trim();
  if (trimmed.length < 8) return "sk-…";
  const tail = trimmed.slice(-4);
  return `sk-•••…${tail}`;
}

/** Headers to merge into a protected fetch. Never adds the header if no key. */
export function authHeaders(): Record<string, string> {
  const k = getApiKey();
  return k ? { "X-OpenAI-Api-Key": k } : {};
}

/**
 * Validate the format only (cheap client-side check). Server-side validation
 * happens via /api/test-key. We accept anything starting with "sk-" and at
 * least 20 chars to allow for future formats.
 */
export function looksValidShape(key: string): boolean {
  const trimmed = (key || "").trim();
  return /^sk-[A-Za-z0-9_\-]{16,}$/.test(trimmed);
}

// ----- Cross-component change events -----
// Any component can subscribe to know when the key was set/cleared.

type Listener = () => void;
const listeners = new Set<Listener>();

function notifyKeyChanged() {
  for (const l of listeners) {
    try {
      l();
    } catch {
      /* noop */
    }
  }
}

export function subscribeKeyChanges(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

// React across browser tabs (storage events fire only in OTHER tabs)
if (typeof window !== "undefined") {
  window.addEventListener("storage", (e) => {
    if (e.key === STORAGE_KEY || e.key === REMEMBER_KEY) {
      notifyKeyChanged();
    }
  });
}
