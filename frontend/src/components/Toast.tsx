import { useEffect, useState, useCallback, createContext, useContext, type ReactNode } from "react";
import { CheckCircle2, AlertCircle, X, Info } from "lucide-react";

type ToastTone = "success" | "error" | "info";
interface ToastItem { id: string; tone: ToastTone; title: string; body?: string; }

interface ToastApi {
  show: (t: Omit<ToastItem, "id">) => void;
  success: (title: string, body?: string) => void;
  error:   (title: string, body?: string) => void;
  info:    (title: string, body?: string) => void;
}

const ToastCtx = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const ctx = useContext(ToastCtx);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);

  const remove = useCallback((id: string) => {
    setItems((s) => s.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((t: Omit<ToastItem, "id">) => {
    const id = `t_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;
    setItems((s) => [...s, { ...t, id }]);
    setTimeout(() => remove(id), 5000);
  }, [remove]);

  const api: ToastApi = {
    show,
    success: (title, body) => show({ tone: "success", title, body }),
    error:   (title, body) => show({ tone: "error",   title, body }),
    info:    (title, body) => show({ tone: "info",    title, body }),
  };

  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-2 w-80">
        {items.map((t) => (
          <ToastCard key={t.id} item={t} onDismiss={() => remove(t.id)} />
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

function ToastCard({ item, onDismiss }: { item: ToastItem; onDismiss: () => void }) {
  const [in_, setIn] = useState(false);
  useEffect(() => { setIn(true); }, []);

  const Icon = item.tone === "success" ? CheckCircle2 : item.tone === "error" ? AlertCircle : Info;
  const ring =
    item.tone === "success" ? "border-emerald-200 bg-emerald-50" :
    item.tone === "error"   ? "border-rose-200 bg-rose-50" :
                              "border-brand-200 bg-brand-50";
  const iconColor =
    item.tone === "success" ? "text-emerald-600" :
    item.tone === "error"   ? "text-rose-600" :
                              "text-brand-600";
  const titleColor =
    item.tone === "success" ? "text-emerald-900" :
    item.tone === "error"   ? "text-rose-900" :
                              "text-brand-900";

  return (
    <div
      className={`pointer-events-auto rounded-xl border ${ring} p-3 shadow-md transition-all duration-200 ${
        in_ ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2"
      }`}
    >
      <div className="flex items-start gap-2">
        <Icon className={`w-4 h-4 mt-0.5 shrink-0 ${iconColor}`} />
        <div className="flex-1 min-w-0">
          <div className={`text-sm font-medium ${titleColor}`}>{item.title}</div>
          {item.body && (
            <div className="text-xs text-slate-600 mt-0.5 leading-snug">{item.body}</div>
          )}
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-slate-400 hover:text-slate-600 shrink-0"
          aria-label="Dismiss"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
