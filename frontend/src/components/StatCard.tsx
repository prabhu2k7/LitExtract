import type { LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  tone?: "default" | "brand" | "accent";
}

export default function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
}: StatCardProps) {
  const toneStyles =
    tone === "brand"
      ? "border-brand-100 bg-gradient-to-br from-brand-50 to-white"
      : tone === "accent"
      ? "border-emerald-100 bg-gradient-to-br from-emerald-50 to-white"
      : "border-slate-200 bg-white";

  const iconStyles =
    tone === "brand"
      ? "text-brand-600 bg-brand-100"
      : tone === "accent"
      ? "text-emerald-600 bg-emerald-100"
      : "text-slate-600 bg-slate-100";

  return (
    <div className={`rounded-xl border ${toneStyles} p-4`}>
      <div className="flex items-start justify-between">
        <div className="text-xs font-medium text-slate-500 uppercase tracking-wide">
          {label}
        </div>
        {Icon ? (
          <div className={`w-7 h-7 rounded-md grid place-items-center ${iconStyles}`}>
            <Icon className="w-3.5 h-3.5" />
          </div>
        ) : null}
      </div>
      <div className="mt-2 text-2xl font-semibold text-slate-900 tabular-nums">
        {value}
      </div>
      {hint ? <div className="mt-1 text-xs text-slate-500">{hint}</div> : null}
    </div>
  );
}
