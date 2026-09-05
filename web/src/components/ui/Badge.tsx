import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

type Tone = "neutral" | "accent" | "good" | "warn" | "bad" | "mag" | "signal";

const TONES: Record<Tone, string> = {
  neutral: "border-line-bright/70 bg-panel-2 text-ink-dim",
  accent: "border-accent/40 bg-accent/10 text-accent",
  good: "border-good/40 bg-good/10 text-good",
  warn: "border-warn/40 bg-warn/10 text-warn",
  bad: "border-bad/40 bg-bad/10 text-bad",
  mag: "border-mag/40 bg-mag/10 text-mag",
  signal: "border-signal/40 bg-signal/10 text-signal",
};

export function Badge({
  children,
  tone = "neutral",
  className,
  mono = true,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  mono?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-[11px] font-medium",
        mono && "mono",
        TONES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

/** A pulsing dot for a live socket. Stops pulsing when the run is not running. */
export function LiveDot({ active, tone = "accent" }: { active: boolean; tone?: Tone }) {
  const colour = {
    accent: "bg-accent",
    good: "bg-good",
    warn: "bg-warn",
    bad: "bg-bad",
    mag: "bg-mag",
    signal: "bg-signal",
    neutral: "bg-muted",
  }[tone];
  return (
    <span className="relative inline-flex size-2 shrink-0">
      {active && (
        <span className={cn("absolute inset-0 animate-ping rounded-full opacity-70", colour)} />
      )}
      <span className={cn("relative size-2 rounded-full", active ? colour : "bg-faint")} />
    </span>
  );
}
