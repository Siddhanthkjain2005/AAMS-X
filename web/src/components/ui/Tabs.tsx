import { cn } from "@/lib/cn";

export function Tabs<T extends string>({
  value,
  onChange,
  tabs,
  className,
}: {
  value: T;
  onChange: (value: T) => void;
  tabs: { value: T; label: string; count?: number }[];
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cn("flex items-center gap-1 rounded-md border border-line bg-void p-0.5", className)}
    >
      {tabs.map((tab) => {
        const active = tab.value === value;
        return (
          <button
            key={tab.value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(tab.value)}
            className={cn(
              "rounded px-2.5 py-1 text-[11px] font-semibold tracking-wide transition-colors",
              active ? "bg-accent/15 text-accent" : "text-muted hover:bg-panel-2 hover:text-ink-dim",
            )}
          >
            {tab.label}
            {tab.count !== undefined && (
              <span className="mono ml-1.5 text-[10px] text-faint">{tab.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}
