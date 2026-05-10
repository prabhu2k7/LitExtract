import { NavLink, Link } from "react-router-dom";
import { Microscope, Upload, History, Activity, Info, Sparkles, Beaker, Settings, KeyRound, ShieldCheck } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  getApiKey,
  maskedDisplay,
  subscribeKeyChanges,
} from "../lib/apiKey";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-3 px-3 py-2 rounded-lg text-sm font-medium transition-all ${
    isActive
      ? "bg-brand-50 text-brand-800 shadow-sm"
      : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"
  }`;

interface HealthResponse {
  ok: boolean;
  model: string;
  provider: string;
  byok_required?: boolean;
}

export default function Layout({ children }: { children: ReactNode }) {
  const { data: health, isError } = useQuery<HealthResponse>({
    queryKey: ["health"],
    queryFn: () => fetch("/api/health").then((r) => r.json()),
    refetchInterval: 15000,
    retry: 0,
  });

  const online = !!health?.ok && !isError;

  // Live-track key state so the sidebar pill updates whenever the key
  // changes (set, cleared, expired in another tab via storage event).
  const [keyMasked, setKeyMasked] = useState<string | null>(() =>
    getApiKey() ? maskedDisplay(getApiKey()) : null
  );
  useEffect(() => {
    return subscribeKeyChanges(() => {
      const k = getApiKey();
      setKeyMasked(k ? maskedDisplay(k) : null);
    });
  }, []);

  return (
    <div className="min-h-screen flex">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 bg-white border-r border-slate-200 flex flex-col">
        <Link
          to="/"
          className="px-5 py-5 border-b border-slate-200 flex items-center gap-2.5 group"
        >
          <div className="relative w-10 h-10 rounded-xl bg-gradient-to-br from-brand-600 via-brand-700 to-brand-900 flex items-center justify-center shadow-md shadow-brand-900/15 group-hover:shadow-lg group-hover:shadow-brand-900/20 transition-shadow">
            <Microscope className="w-5 h-5 text-white" />
            <div className="absolute -top-1 -right-1 w-3 h-3 rounded-full bg-accent-500 ring-2 ring-white" />
          </div>
          <div>
            <div className="text-base font-semibold text-slate-900 leading-tight tracking-tight">
              Biomarker Research
            </div>
            <div className="text-[11px] text-slate-500 leading-tight">
              Oncology Extraction
            </div>
          </div>
        </Link>

        <nav className="flex-1 p-3 space-y-1">
          <NavLink to="/upload" className={navLinkClass}>
            <Upload className="w-4 h-4" />
            Upload
          </NavLink>
          <NavLink to="/history" className={navLinkClass}>
            <History className="w-4 h-4" />
            History
          </NavLink>
          <NavLink to="/biomarkers" className={navLinkClass}>
            <Beaker className="w-4 h-4" />
            Biomarkers
          </NavLink>
          <NavLink to="/validation" className={navLinkClass}>
            <ShieldCheck className="w-4 h-4" />
            Validation
          </NavLink>
          <NavLink to="/settings" className={navLinkClass}>
            <Settings className="w-4 h-4" />
            Settings
          </NavLink>
          <NavLink to="/about" className={navLinkClass}>
            <Info className="w-4 h-4" />
            About
          </NavLink>
        </nav>

        <div className="p-3 border-t border-slate-200 space-y-2">
          <div className="rounded-lg bg-gradient-to-br from-brand-50 to-accent-500/5 border border-brand-100 p-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-brand-800">
              <Sparkles className="w-3.5 h-3.5" />
              4-Agent Pipeline
            </div>
            <div className="mt-1 text-[11px] text-slate-600 leading-snug">
              Study · Biomarkers · Results · Inferences — all in one workbook.
            </div>
          </div>

          {/* API-key pill — masked, clickable to settings */}
          <Link
            to="/settings"
            className={`flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px] transition-colors ${
              keyMasked
                ? "text-slate-600 hover:bg-slate-100"
                : "text-amber-700 bg-amber-50/60 hover:bg-amber-50"
            }`}
            title={keyMasked ? "API key set — click to manage" : "No API key set — click to add"}
          >
            <KeyRound className="w-3 h-3 shrink-0" />
            <span className="truncate font-mono">
              {keyMasked ?? "No API key"}
            </span>
          </Link>

          <div className="flex items-center gap-2 px-2 py-1.5 text-[11px] text-slate-500">
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                online ? "bg-emerald-500 animate-pulse" : "bg-rose-500"
              }`}
            />
            <span>{online ? `Online · ${health?.model}` : "Backend offline"}</span>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="h-14 border-b border-slate-200 bg-white/85 backdrop-blur-sm flex items-center justify-between px-6 sticky top-0 z-10">
          <div className="text-sm text-slate-500">
            Pharma Research &nbsp;/&nbsp;{" "}
            <span className="text-slate-900 font-medium">Biomarker Extraction</span>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <Activity className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-500">v0.1 · {health?.provider ?? "—"}</span>
          </div>
        </header>
        <div className="flex-1 p-6 overflow-y-auto">{children}</div>
      </main>
    </div>
  );
}
