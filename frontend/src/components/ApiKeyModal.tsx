import { useEffect } from "react";
import { createPortal } from "react-dom";
import { KeyRound, X } from "lucide-react";
import ApiKeyForm from "./ApiKeyForm";

interface ApiKeyModalProps {
  open: boolean;
  onClose: () => void;
  /** Title customization for context-specific prompts. */
  title?: string;
  /** Subtitle / contextual lead-in. */
  subtitle?: string;
  /** Called after a successful save — typical use: re-trigger the queued action. */
  onSaved?: () => void;
}

export default function ApiKeyModal({
  open,
  onClose,
  title = "OpenAI API key required",
  subtitle = "Biomarker Research is open source — bring your own key. We never store it on our servers.",
  onSaved,
}: ApiKeyModalProps) {
  // Body-scroll lock + Esc to close
  useEffect(() => {
    if (!open) return;
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
  }, [open, onClose]);

  if (!open) return null;

  const node = (
    <div
      className="fixed inset-0 z-[70] bg-slate-950/55 backdrop-blur-sm grid place-items-start sm:place-items-center p-4 overflow-y-auto"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-labelledby="api-key-modal-title"
    >
      <div
        className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden mt-12 sm:mt-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-gradient-to-br from-brand-700 via-brand-800 to-brand-950 text-white px-6 py-5 relative overflow-hidden">
          <div className="absolute -right-8 -top-8 w-40 h-40 rounded-full bg-white/5 blur-3xl pointer-events-none" />
          <div className="relative flex items-start justify-between gap-3">
            <div className="flex items-start gap-3 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-white/15 backdrop-blur-sm grid place-items-center ring-1 ring-white/20 shrink-0">
                <KeyRound className="w-5 h-5 text-white" />
              </div>
              <div className="min-w-0">
                <div
                  id="api-key-modal-title"
                  className="text-base font-semibold leading-tight"
                >
                  {title}
                </div>
                <div className="text-xs text-brand-100/90 mt-0.5 leading-snug">
                  {subtitle}
                </div>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-white/70 hover:text-white p-1 rounded shrink-0"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="p-6">
          <ApiKeyForm
            compact={false}
            onSaved={() => {
              onSaved?.();
              // Close shortly after a successful save so user sees the
              // "saved" confirmation banner briefly.
              setTimeout(onClose, 800);
            }}
          />
        </div>
      </div>
    </div>
  );

  return createPortal(node, document.body);
}
