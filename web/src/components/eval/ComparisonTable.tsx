/** Significance, stated with both tests visible.
 *
 * The project's rule is that a difference counts only when Welch's t *and* Mann-Whitney U
 * both reject at alpha = 0.05, so both p-values are columns here rather than a single
 * asterisk. A row whose two tests disagree is shown as "split", which is the interesting
 * case and the one a single-test table would hide.
 */

import { Check, Minus, Split as SplitIcon } from "lucide-react";

import type { Comparison } from "@/api/types";
import { cn } from "@/lib/cn";
import { higherIsBetter, metricLabel, num, policyLabel, pvalue, signed } from "@/lib/format";

const ALPHA = 0.05;

export function ComparisonTable({
  comparisons,
  className,
}: {
  comparisons: Comparison[];
  className?: string;
}) {
  return (
    <div className={cn("min-w-0 overflow-x-auto", className)}>
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-line-bright">
            {["Metric", "Treatment vs control", "Δ", "rel", "Welch p", "MWU p", "d", ""].map(
              (heading, index) => (
                <th
                  key={heading || index}
                  className={cn("eyebrow py-2 whitespace-nowrap", index > 1 ? "px-2.5 text-right" : "pr-3 text-left")}
                >
                  {heading}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {comparisons.map((row) => {
            const welch = row.welch_p < ALPHA;
            const mwu = row.mannwhitney_p < ALPHA;
            const improved = higherIsBetter(row.metric) === (row.difference > 0);
            return (
              <tr
                key={`${row.metric}:${row.treatment}:${row.control}`}
                className="border-b border-line/70 last:border-0 hover:bg-panel-2/40"
              >
                <td className="py-1.5 pr-3 text-ink-dim">{metricLabel(row.metric)}</td>
                <td className="mono py-1.5 pr-3 whitespace-nowrap text-muted">
                  {policyLabel(row.treatment)}
                  <span className="text-faint"> vs </span>
                  {policyLabel(row.control)}
                </td>
                <td
                  className={cn(
                    "mono px-2.5 py-1.5 text-right tabular-nums",
                    row.significant ? (improved ? "text-good" : "text-bad") : "text-muted",
                  )}
                >
                  {signed(row.difference, 3)}
                </td>
                <td className="mono px-2.5 py-1.5 text-right tabular-nums text-muted">
                  {Number.isFinite(row.relative) ? `${signed(row.relative * 100, 1)}%` : "—"}
                </td>
                <td
                  className={cn(
                    "mono px-2.5 py-1.5 text-right tabular-nums",
                    welch ? "text-ink" : "text-faint",
                  )}
                >
                  {pvalue(row.welch_p)}
                </td>
                <td
                  className={cn(
                    "mono px-2.5 py-1.5 text-right tabular-nums",
                    mwu ? "text-ink" : "text-faint",
                  )}
                >
                  {pvalue(row.mannwhitney_p)}
                </td>
                <td className="mono px-2.5 py-1.5 text-right tabular-nums text-muted">
                  {num(row.cohens_d, 2)}
                </td>
                <td className="px-2 py-1.5 text-right">
                  {row.significant ? (
                    <span title="both tests reject">
                      <Check className="inline size-3.5 text-good" />
                    </span>
                  ) : welch !== mwu ? (
                    <span title="the two tests disagree">
                      <SplitIcon className="inline size-3.5 text-warn" />
                    </span>
                  ) : (
                    <span title="neither test rejects">
                      <Minus className="inline size-3.5 text-faint" />
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mono mt-2 text-[9.5px] leading-relaxed text-faint">
        significant = Welch's t and Mann-Whitney U both reject at α = {ALPHA}. d is Cohen's d.
        A split row means the two tests disagree and the difference is not claimed.
      </p>
    </div>
  );
}
