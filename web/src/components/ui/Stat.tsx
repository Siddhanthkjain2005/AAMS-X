import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

/**
 * One measured number. The `hint` line is not decoration — it is where the units, the
 * denominator or the "of N seeds" lives, so a number on screen is never ambiguous about
 * what it counted.
 */
export function Stat({
  label,
  value,
  hint,
  tone = "ink",
  trend,
  className,
  children,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "ink" | "accent" | "good" | "warn" | "bad" | "mag" | "signal";
  trend?: ReactNode;
  className?: string;
  children?: ReactNode;
}) {
  const colour = {
    ink: "text-ink",
    accent: "text-accent",
    good: "text-good",
    warn: "text-warn",
    bad: "text-bad",
    mag: "text-mag",
    signal: "text-signal",
  }[tone];
  return (
    <div className={cn("flex min-w-0 flex-col justify-between gap-1", className)}>
      <span className="eyebrow truncate">{label}</span>
      <span className="flex items-baseline gap-2">
        <span className={cn("mono text-2xl leading-none font-semibold tabular-nums", colour)}>
          {value}
        </span>
        {trend}
      </span>
      {hint && <span className="mono truncate text-[10px] text-faint">{hint}</span>}
      {children}
    </div>
  );
}
