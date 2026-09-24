/** Read a batch (arena or ablation ladder) whether it is running or long finished.
 *
 * Two sources, because a batch has two lives. While it runs, the websocket is the only
 * place the `done/total` job counter exists. Once it is over, the session eventually falls
 * out of the server's memory and the registry row is the only place the result exists. So
 * this subscribes to the socket *and* queries the registry, and prefers whichever actually
 * has a result — never showing a partial aggregate as if it were the final one.
 */

import { useExperiment } from "@/api/queries";
import { useExperimentStream } from "@/hooks/useExperimentStream";
import { isBatchResult, type BatchResult } from "@/api/types";

export interface BatchView {
  result: BatchResult | null;
  /** `done`/`total` episodes while running, else null. */
  progress: { done: number; total: number } | null;
  status: string;
  running: boolean;
  error: string | null;
  loading: boolean;
  /** When the run started. ISO from the registry, epoch seconds from a live session. */
  createdAt: number | string | null;
}

export function useBatchResult(batchId: string | null): BatchView {
  const live = useExperimentStream(batchId);
  const stored = useExperiment(batchId, { staleTime: 30_000 });

  const liveResult = isBatchResult(live.state.result)
    ? live.state.result
    : null;
  const storedResult = isBatchResult(stored.data?.result ?? null)
    ? (stored.data?.result as BatchResult)
    : null;
  const status = live.state.session?.status ?? stored.data?.status ?? "unknown";
  const running = status === "running" || status === "queued";

  return {
    result: liveResult ?? storedResult,
    progress: live.state.batch,
    status: String(status),
    running,
    error: live.state.error ?? stored.data?.error ?? null,
    loading:
      Boolean(batchId) &&
      !liveResult &&
      !storedResult &&
      (stored.isLoading || running),
    createdAt: stored.data?.created_at ?? stored.data?.started_at ?? null,
  };
}

/** Mean of an aggregate, or null when the metric was not collected for that arm. */
export function meanOf(
  result: BatchResult,
  variant: string,
  metric: string,
): number | null {
  const value = result.aggregates[variant]?.[metric]?.mean;
  return value === undefined || !Number.isFinite(value) ? null : value;
}

/** The variant that wins a metric, honouring the metric's own direction. */
export function bestVariant(
  result: BatchResult,
  metric: string,
  higherWins: boolean,
): string | null {
  let best: string | null = null;
  let bestValue = higherWins ? -Infinity : Infinity;
  for (const variant of result.variants) {
    const value = meanOf(result, variant, metric);
    if (value === null) continue;
    if (higherWins ? value > bestValue : value < bestValue) {
      bestValue = value;
      best = variant;
    }
  }
  return best;
}
