import type { ReactNode } from "react";

type Tone = "slate" | "brand" | "emerald" | "amber" | "rose";

const toneClasses: Record<Tone, string> = {
  slate: "bg-slate-100 text-slate-700 border-slate-200",
  brand: "bg-brand-50 text-brand-700 border-brand-200",
  emerald: "bg-emerald-50 text-emerald-700 border-emerald-200",
  amber: "bg-amber-50 text-amber-700 border-amber-200",
  rose: "bg-rose-50 text-rose-700 border-rose-200",
};

export default function Pill({
  tone = "slate",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full border ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}
