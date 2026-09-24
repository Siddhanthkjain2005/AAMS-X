import { AlertTriangle, Database, Loader2, SearchX } from "lucide-react";
import type { ReactNode } from "react";

import { ApiError } from "@/api/client";
import { cn } from "@/lib/cn";
import { Button } from "./Button";

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin text-accent", className)} />;
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex h-full min-h-32 flex-col items-center justify-center gap-3 text-muted">
      <Spinner className="size-5" />
      <span className="eyebrow">{label}</span>
    </div>
  );
}

/**
 * The error panel. A 503 from this API is not a crash — it means the offline cache or the
 * window index is missing, and the fix is a command. Showing that command is the whole
 * point: the alternative would be a UI that silently falls back to invented data, which
 * this project does not do.
 */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const apiError = error instanceof ApiError ? error : null;
  const detail =
    apiError?.detail ?? (error instanceof Error ? error.message : "something went wrong");
  const missingData = apiError?.isDataMissing ?? false;
  return (
    <div
      className={cn(
        "flex h-full min-h-32 flex-col items-center justify-center gap-3 px-6 text-center",
        className,
      )}
    >
      {missingData ? (
        <Database className="size-6 text-warn" />
      ) : (
        <AlertTriangle className="size-6 text-bad" />
      )}
      <p className="max-w-lg text-xs leading-relaxed text-ink-dim">{detail}</p>
      {missingData && (
        <pre className="mono max-w-lg overflow-x-auto rounded-md border border-line bg-void px-3 py-2 text-left text-[10px] text-muted">
          make data{"\n"}make index
        </pre>
      )}
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  detail,
  action,
  icon,
}: {
  title: string;
  detail?: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex h-full min-h-32 flex-col items-center justify-center gap-2.5 px-6 text-center">
      {icon ?? <SearchX className="size-5 text-faint" />}
      <p className="text-xs font-medium text-ink-dim">{title}</p>
      {detail && <p className="max-w-md text-[11px] leading-relaxed text-faint">{detail}</p>}
      {action}
    </div>
  );
}

/** A determinate progress bar. Used for run progress and for batch job counts. */
export function ProgressBar({
  value,
  tone = "accent",
  className,
  showSweep = false,
}: {
  value: number;
  tone?: "accent" | "mag" | "warn";
  className?: string;
  showSweep?: boolean;
}) {
  const colour = { accent: "bg-accent", mag: "bg-mag", warn: "bg-warn" }[tone];
  return (
    <div className={cn("relative h-1 overflow-hidden rounded-full bg-line", className)}>
      <div
        className={cn("h-full rounded-full transition-[width] duration-200 ease-out", colour)}
        style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }}
      />
      {showSweep && (
        <div className="absolute inset-0 animate-sweep bg-gradient-to-r from-transparent via-white/15 to-transparent" />
      )}
    </div>
  );
}
