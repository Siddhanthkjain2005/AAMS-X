/** The batch results table: thirteen headline metrics × N arms.
 *
 * Three rules, all of them about not overstating what six seeds can support.
 * `mean ± sem` is printed rather than the mean alone, because two arms whose intervals
 * overlap are not distinguishable and the table should show that. The winner of each row
 * is marked, but only in the arrow column — a bold number in a cell reads as "significant"
 * to a skimming eye, and winning a mean is not significance. A metric no arm reported is
 * shown as an em dash row, not dropped, so a missing measurement stays visible.
 */

import { ArrowDown, ArrowUp } from "lucide-react";

import { HEADLINE_METRICS, type BatchResult } from "@/api/types";
import { cn } from "@/lib/cn";
import { higherIsBetter, metricLabel, num, policyLabel } from "@/lib/format";
import { policyColor } from "@/lib/palette";
import { bestVariant, meanOf } from "./useBatchResult";

/** Metrics whose natural scale is a probability; printed with three decimals. */
const THREE_DECIMALS = new Set([
  "sustained_detection_probability",
  "event_detection_probability",
  "detection_rate",
  "false_alarm_rate",
  "precision",
  "oracle_ratio",
  "band_coverage",
  "information_per_observation",
  "detections_per_cost",
]);

function decimalsFor(metric: string): number {
  if (THREE_DECIMALS.has(metric)) return 3;
  if (metric.includes("delay") || metric.startsWith("time_to_detect")) return 1;
  return 2;
}

export function MetricTable({
  result,
  metrics = HEADLINE_METRICS as readonly string[],
  colourVariants = true,
  className,
}: {
  result: BatchResult;
  metrics?: readonly string[];
  /** Arena arms get their policy colour; ablation rungs are all MAG-NTS, so pass false. */
  colourVariants?: boolean;
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 overflow-x-auto", className)}>
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-line-bright">
            <th className="eyebrow sticky left-0 z-1 bg-panel py-2 pr-3 text-left">Metric</th>
            <th className="w-6" />
            {result.variants.map((variant) => (
              <th key={variant} className="px-2.5 py-2 text-right">
                <span
                  className="mono text-[10.5px] font-semibold whitespace-nowrap"
                  style={{ color: colourVariants ? policyColor(variant) : undefined }}
                >
                  {policyLabel(variant)}
                </span>
                <span className="mono block text-[9px] font-normal text-faint">
                  n = {result.n_runs[variant] ?? 0}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((metric) => {
            const higher = higherIsBetter(metric);
            const winner = bestVariant(result, metric, higher);
            const decimals = decimalsFor(metric);
            return (
              <tr key={metric} className="border-b border-line/70 last:border-0 hover:bg-panel-2/40">
                <td className="sticky left-0 z-1 bg-panel py-1.5 pr-3 text-ink-dim">
                  {metricLabel(metric)}
                </td>
                <td className="pr-1 text-faint" title={higher ? "higher is better" : "lower is better"}>
                  {higher ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />}
                </td>
                {result.variants.map((variant) => {
                  const aggregate = result.aggregates[variant]?.[metric];
                  const value = meanOf(result, variant, metric);
                  const isWinner = variant === winner && result.variants.length > 1;
                  return (
                    <td
                      key={variant}
                      className={cn(
                        "mono px-2.5 py-1.5 text-right tabular-nums whitespace-nowrap",
                        isWinner ? "text-ink" : "text-muted",
                      )}
                    >
                      {value === null ? (
                        <span className="text-faint">—</span>
                      ) : (
                        <>
                          <span className={isWinner ? "font-semibold" : undefined}>
                            {num(value, decimals)}
                          </span>
                          {aggregate && aggregate.n > 1 && (
                            <span className="ml-1 text-[9.5px] text-faint">
                              ±{num(aggregate.sem, decimals)}
                            </span>
                          )}
                        </>
                      )}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mono mt-2 text-[9.5px] leading-relaxed text-faint">
        mean ± standard error over seeds. A marked cell won its row's mean — that is not the
        same as a significant difference, which only the comparison table can say.
      </p>
    </div>
  );
}
