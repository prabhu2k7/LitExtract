import { useState, type ReactNode } from "react";

interface Tab {
  id: string;
  label: string;
  count?: number;
  content: ReactNode;
}

interface TabsProps {
  tabs: Tab[];
  defaultTab?: string;
}

export default function Tabs({ tabs, defaultTab }: TabsProps) {
  const [active, setActive] = useState(defaultTab ?? tabs[0]?.id);
  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div>
      <div className="border-b border-slate-200 flex gap-1 overflow-x-auto">
        {tabs.map((t) => {
          const isActive = t.id === active;
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActive(t.id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 -mb-px whitespace-nowrap transition-colors ${
                isActive
                  ? "border-brand-600 text-brand-700"
                  : "border-transparent text-slate-600 hover:text-slate-900"
              }`}
            >
              {t.label}
              {typeof t.count === "number" ? (
                <span
                  className={`ml-2 inline-flex items-center justify-center min-w-[1.5rem] h-5 px-1.5 rounded-full text-[11px] tabular-nums ${
                    isActive
                      ? "bg-brand-100 text-brand-800"
                      : "bg-slate-100 text-slate-700"
                  }`}
                >
                  {t.count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>
      <div className="pt-5">{activeTab?.content}</div>
    </div>
  );
}
