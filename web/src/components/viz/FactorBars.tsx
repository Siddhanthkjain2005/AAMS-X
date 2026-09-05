/** The decision, term by term.
 *
 * MAG-NTS scores a window as a weighted sum of eight terms, and the whole claim of the
 * project is that the sum is inspectable. So the bars are drawn from
 * `factors["contribution.<term>"]` — the *weighted* contributions, signed — and the panel
 * prints their total next to `final_action_value`. If those two ever disagree the
 * explanation is wrong, and this is where it shows.
 *
 * Bars are centred on zero because two of the eight terms (cost, switching) are always
 * negative: drawing them from a left edge would make a penalty look like a reward.
 */

import { motion } from "framer-motion";

import { FACTOR_TERMS, type DecisionFactors } from "@/api/types";
import { cn } from "@/lib/cn";
import { num, signed } from "@/lib/format";
import { FACTOR_COLORS } from "@/lib/palette";

/** The evidence line under each term: what the raw signal was before weighting. */
const EVIDENCE: Record<string, { key: keyof DecisionFactors & string; label: string }> = {
  detection: { key: "predicted_activity", label: "predicted activity" },
  information: { key: "information_gain", label: "expected bits" },
  memory: { key: "memory_similarity", label: "recall similarity" },
  periodicity: { key: "periodicity_score", label: "cycle phase" },
  uncertainty: { key: "uncertainty", label: "posterior entropy" },
  recency: { key: "staleness", label: "staleness" },
  cost: { key: "sensing_cost", label: "sensing cost" },
  switching: { key: "switching_penalty", label: "tuning penalty" },
};

export function FactorBars({
  factors,
  className,
  compact = false,
}: {
  factors: DecisionFactors;
  className?: string;
  compact?: boolean;
}) {
  const contributions = FACTOR_TERMS.map((term) => ({
    term,
    value: factors[`contribution.${term}`] ?? 0,
    evidence: factors[EVIDENCE[term].key] ?? 0,
    evidenceLabel: EVIDENCE[term].label,
  }));
  const scale = Math.max(0.05, ...contributions.map((entry) => Math.abs(entry.value)));

  return (
    <div className={cn("flex flex-col gap-1.5", className)}>
      {contributions.map((entry) => {
        const fraction = Math.abs(entry.value) / scale / 2;
        const positive = entry.value >= 0;
        return (
          <div key={entry.term} className="grid grid-cols-[86px_1fr_58px] items-center gap-2">
            <span className="truncate text-[11px] text-ink-dim capitalize">{entry.term}</span>
            <div className="relative h-3.5 rounded bg-void/80">
              <span className="absolute inset-y-0 left-1/2 w-px bg-line-bright" />
              <motion.span
                className="absolute inset-y-0.5 rounded-sm"
                style={{
                  background: FACTOR_COLORS[entry.term],
                  left: positive ? "50%" : undefined,
                  right: positive ? undefined : "50%",
                }}
                animate={{ width: `${fraction * 100}%` }}
                transition={{ type: "spring", stiffness: 260, damping: 30 }}
              />
            </div>
            <span
              className="mono text-right text-[11px] tabular-nums"
              style={{ color: FACTOR_COLORS[entry.term] }}
            >
              {signed(entry.value, 3)}
            </span>
            {!compact && (
              <span className="col-span-3 -mt-1 pl-[86px] text-[9.5px] text-faint">
                {entry.evidenceLabel} {num(entry.evidence, 3)}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

/** Sum of the eight weighted terms. Should equal `final_action_value`. */
export function contributionTotal(factors: DecisionFactors): number {
  return FACTOR_TERMS.reduce((total, term) => total + (factors[`contribution.${term}`] ?? 0), 0);
}
