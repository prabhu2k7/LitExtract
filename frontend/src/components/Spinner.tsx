import { Loader2 } from "lucide-react";

interface SpinnerProps {
  label?: string;
  size?: "sm" | "md" | "lg";
}

export default function Spinner({ label, size = "md" }: SpinnerProps) {
  const sz = size === "sm" ? "w-4 h-4" : size === "lg" ? "w-8 h-8" : "w-5 h-5";
  return (
    <div className="inline-flex items-center gap-2 text-slate-600">
      <Loader2 className={`${sz} animate-spin text-brand-600`} />
      {label ? <span className="text-sm">{label}</span> : null}
    </div>
  );
}
