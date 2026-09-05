/** Decision Inspector — why this window, term by term.
 *
 * The claim MAG-NTS makes is that it is explainable, and this screen is where that claim is
 * either kept or exposed. Three things are on screen at once:
 *
 *  1. the *score landscape* — every candidate window's value across the band, so the choice
 *     is visible as a choice among alternatives rather than as an assertion;
 *  2. the *decomposition* — the eight weighted contributions for the window that won, with
 *     their raw evidence beside them, so a term can be traced back to a measurement;
 *  3. the *arithmetic check* — Σ contributions printed next to `final_action_value`. If the
 *     explanation did not produce the decision, the mismatch shows here instead of hiding.
 *
 * The reward panel is deliberately separate from the value panel. `action_value` is what the
 * scheduler expected before it looked; `reward` is what the environment paid afterwards.
 * Presenting them as one number is the most common way an "explainable" dashboard lies.
 */

import { AlertTriangle, ArrowRight, Check, Crosshair, Scale } from "lucide-react";

import { useScenario } from "@/api/queries";
import { FACTOR_TERMS, type DecisionFactors, type Frame } from "@/api/types";
import { NoRun } from "@/components/run/NoRun";
import { RunStatusBar } from "@/components/run/RunStatusBar";
import { Badge, Panel, Stat } from "@/components/ui";
import { FactorBars, contributionTotal } from "@/components/viz/FactorBars";
import { FieldWaterfall } from "@/components/viz/FieldWaterfall";
import { RampLegend } from "@/components/viz/RampLegend";
import { RegionBars } from "@/components/viz/RegionBars";
import { Sparkline } from "@/components/viz/Sparkline";
import { cn } from "@/lib/cn";
import { db, int, num, pct, regionLabel, signed } from "@/lib/format";
import { FACTOR_COLORS, HEAT_LUT, PALETTE } from "@/lib/palette";
import { useActiveFrame, useLive } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

/** Raw evidence, in the order it enters the score. Label, key, formatter. */
const EVIDENCE: [string, keyof DecisionFactors | string, (value: number) => string][] = [
  ["Predicted activity", "predicted_activity", (v) => num(v, 3)],
  ["Posterior confidence", "posterior_confidence", (v) => num(v, 3)],
  ["Information gain (bits)", "information_gain", (v) => num(v, 4)],
  ["Memory similarity", "memory_similarity", (v) => num(v, 3)],
  ["Periodicity score", "periodicity_score", (v) => num(v, 3)],
  ["Uncertainty", "uncertainty", (v) => num(v, 3)],
  ["Staleness", "staleness", (v) => num(v, 2)],
  ["Sensing cost", "sensing_cost", (v) => num(v, 3)],
  ["Switching penalty", "switching_penalty", (v) => num(v, 3)],
  ["Sampled rate (Thompson)", "sampled_rate", (v) => num(v, 3)],
  ["Steps since observed", "steps_since_observed", (v) => int(v)],
  ["Steps since change", "steps_since_change", (v) => int(v)],
  ["Budget pressure", "budget_pressure", (v) => num(v, 3)],
];

export default function DecisionInspector() {
  const { state, frames } = useLive();
  const frame = useActiveFrame();
  const experimentId = useSession((session) => session.experimentId);
  const scenario = useScenario(state.session?.scenario_id ?? null);

  const nRegions = scenario.data?.n_regions ?? frame?.belief.length ?? 32;
  const centres = scenario.data?.segments_measured?.[0]?.grid?.centre_mhz;

  if (!experimentId) {
    return (
      <div className="p-4">
        <Panel className="min-h-96">
          <NoRun what="decision" />
        </Panel>
      </div>
    );
  }

  if (!frame) {
    return (
      <div className="flex min-h-full flex-col gap-3 p-4">
        <RunStatusBar />
        <Panel className="min-h-80">
          <NoRun what="decision" />
        </Panel>
      </div>
    );
  }

  const total = contributionTotal(frame.factors);
  const stated = frame.factors.final_action_value ?? frame.action_value;
  const mismatch = Math.abs(total - stated);
  const consistent = mismatch < 1e-6;
  const hasLandscape = Array.isArray(frame.per_region_value) && frame.per_region_value.length > 0;
  const chose = frame.regions;
  // `oracle_best` is the best achievable in-window detection *count* for this step, not a
  // region index. Reading it as an index would invent a "pick" the run never recorded.
  const oracleCeiling = frame.oracle_best;
  const matchedOracle = frame.hits >= oracleCeiling;
  const measuredPeak = frame.measured_db.length > 0 ? Math.max(...frame.measured_db) : null;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <RunStatusBar />

      <Panel flush className="shrink-0">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-3 xl:grid-cols-6">
          <Stat
            label="Chosen window"
            value={`${chose[0] ?? "—"}–${chose[chose.length - 1] ?? "—"}`}
            hint={centres ? regionLabel(chose[0] ?? 0, centres[chose[0] ?? 0]) : `${chose.length} regions`}
            tone="accent"
          />
          <Stat
            label="Action value"
            value={num(stated, 3)}
            hint="expected value before looking"
            tone="ink"
          />
          <Stat
            label="Reward paid"
            value={signed(frame.reward, 3)}
            hint="what the environment actually returned"
            tone={frame.reward >= 0 ? "good" : "bad"}
          />
          <Stat
            label="Hits / oracle ceiling"
            value={`${int(frame.hits)} / ${int(oracleCeiling)}`}
            hint={
              matchedOracle
                ? "matched the best any window could have done"
                : `${int(oracleCeiling - frame.hits)} charged to regret this step`
            }
            tone={matchedOracle ? "good" : "warn"}
          />
          <Stat
            label="Measured peak"
            value={frame.available ? db(measuredPeak) : "—"}
            hint={frame.available ? "above this region's threshold" : "archive gap at this step"}
            tone={frame.available ? "signal" : "bad"}
          />
          <Stat
            label="Budget pressure"
            value={num(frame.factors.budget_pressure ?? 0, 3)}
            hint={`${num(frame.budget_remaining, 0)} left of Σ c(a_t) ≤ B`}
            tone={frame.budget_remaining <= 0 ? "bad" : "ink"}
          />
        </div>
      </Panel>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            flush
            title="Score landscape"
            subtitle="value of every candidate window this step · the chosen one is outlined"
            actions={
              hasLandscape ? (
                <RampLegend lut={HEAT_LUT} min={0} max={1} label="normalised value" className="w-36" />
              ) : (
                <Badge tone="neutral">this scheduler scores one window</Badge>
              )
            }
            className="shrink-0"
          >
            {hasLandscape ? (
              <div className="flex flex-col gap-1 px-2 pb-2">
                <RegionBars
                  frames={frames}
                  frame={frame}
                  select={(f) => f.per_region_value}
                  lut={HEAT_LUT}
                  scale={normaliser(frame.per_region_value as number[])}
                  height={104}
                />
                <div className="mono flex justify-between px-0.5 text-[9px] text-faint">
                  <span>{regionLabel(0, centres?.[0])}</span>
                  <span className="text-accent">chose {chose.join(" · ")}</span>
                  <span>{regionLabel(nRegions - 1, centres?.[nRegions - 1])}</span>
                </div>
              </div>
            ) : (
              <p className="px-4 py-6 text-[11px] leading-relaxed text-faint">
                Round-robin and random do not compute a per-window score, so there is no
                landscape to draw. The decomposition below still shows what the run recorded.
              </p>
            )}
          </Panel>

          <Panel
            flush
            title="Score landscape against time"
            subtitle="how the candidate ranking moved — bright bands are windows the policy kept wanting"
            className="min-h-40 flex-1"
          >
            {hasLandscape ? (
              <FieldWaterfall
                frames={frames}
                nRegions={nRegions}
                select={(f) => f.per_region_value}
                lut={HEAT_LUT}
                scale={(value) => Math.max(0, Math.min(1, value))}
                label="candidate value"
              />
            ) : (
              <div className="flex h-full items-center justify-center px-6 text-center text-[11px] text-faint">
                no per-window score recorded for this policy
              </div>
            )}
          </Panel>

          <div className="grid shrink-0 grid-cols-1 gap-3 md:grid-cols-2">
            <Panel flush title="Action value" subtitle="expected, per step">
              <Sparkline
                frames={frames}
                value={(f: Frame) => f.action_value}
                colour={PALETTE.accent}
                height={62}
                zeroLine
              />
            </Panel>
            <Panel flush title="Reward" subtitle="paid, per step">
              <Sparkline
                frames={frames}
                value={(f: Frame) => f.reward}
                colour={PALETTE.good}
                height={62}
                zeroLine
              />
            </Panel>
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            title="Why this window"
            subtitle="eight weighted contributions · cost and switching are penalties"
            actions={
              <Badge tone={consistent ? "good" : "bad"}>
                {consistent ? <Check className="size-3" /> : <AlertTriangle className="size-3" />}
                Σ {signed(total, 3)}
              </Badge>
            }
          >
            <FactorBars factors={frame.factors} />
            {!consistent && (
              <p className="mono mt-3 rounded-md border border-bad/40 bg-bad/8 px-2.5 py-2 text-[10px] leading-relaxed text-bad">
                the eight contributions sum to {num(total, 6)} but the run recorded a final
                action value of {num(stated, 6)} — a gap of {num(mismatch, 6)}. The explanation
                does not reproduce the decision, so do not trust the decomposition on this step.
              </p>
            )}
          </Panel>

          <Panel title="Raw evidence" subtitle="the measurements behind the terms">
            <dl className="grid grid-cols-1 gap-x-4 gap-y-1">
              {EVIDENCE.map(([label, key, format]) => {
                const value = frame.factors[key as string];
                const term = FACTOR_TERMS.find((candidate) => key.toString().startsWith(candidate));
                return (
                  <div
                    key={label}
                    className="flex items-baseline justify-between gap-3 border-b border-line/50 py-1 last:border-0"
                  >
                    <dt className="flex min-w-0 items-center gap-1.5 text-[11px] text-muted">
                      {term && (
                        <span
                          className="size-1.5 shrink-0 rounded-full"
                          style={{ background: FACTOR_COLORS[term] }}
                        />
                      )}
                      <span className="truncate">{label}</span>
                    </dt>
                    <dd className="mono shrink-0 text-[11px] tabular-nums text-ink">
                      {value === undefined ? "—" : format(value)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </Panel>

          <Panel
            title="Reward paid"
            subtitle="the additive objective, term by term"
            actions={
              <Badge tone="neutral">
                <Scale className="size-3" />
                {signed(frame.reward, 3)}
              </Badge>
            }
          >
            <ul className="flex flex-col gap-1.5">
              {Object.entries(frame.reward_terms).map(([term, value]) => (
                <li key={term} className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-[10.5px] text-muted capitalize">
                    {term.replace(/_/g, " ")}
                  </span>
                  <span className="relative h-1.5 flex-1 rounded-full bg-line">
                    <span
                      className={cn(
                        "absolute top-0 h-1.5 rounded-full",
                        value >= 0 ? "left-1/2" : "right-1/2",
                      )}
                      style={{
                        width: `${Math.min(50, Math.abs(value) * 50)}%`,
                        background: value >= 0 ? PALETTE.good : PALETTE.bad,
                      }}
                    />
                    <span className="absolute top-[-2px] left-1/2 h-2.5 w-px bg-line-bright" />
                  </span>
                  <span className="mono w-14 shrink-0 text-right text-[10.5px] tabular-nums text-ink">
                    {signed(value, 3)}
                  </span>
                </li>
              ))}
            </ul>
            <p className="mono mt-2.5 text-[9px] leading-relaxed text-faint">
              action value is an expectation formed before looking; reward is what the
              environment paid after. They are different quantities and are never added.
            </p>
          </Panel>

          {frame.notes.length > 0 && (
            <Panel title="Policy notes" subtitle="logged by the scheduler at this step">
              <ul className="flex flex-col gap-1.5">
                {frame.notes.map((note) => (
                  <li key={note} className="flex gap-1.5 text-[11px] leading-snug text-muted">
                    <ArrowRight className="mt-0.5 size-3 shrink-0 text-accent-dim" />
                    <span>{note}</span>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="Counterfactual" subtitle="what the oracle would have done" className="shrink-0">
            <div className="flex items-center gap-3">
              <Crosshair className={cn("size-4", matchedOracle ? "text-good" : "text-warn")} />
              <p className="text-[11px] leading-relaxed text-muted">
                {matchedOracle
                  ? `The best any window could have done this step was ${int(oracleCeiling)} in-window detections, and the chosen window ${chose.join("/")} got ${int(frame.hits)}. Nothing was given up here.`
                  : `The best any window could have done this step was ${int(oracleCeiling)}; the chosen window ${chose.join("/")} got ${int(frame.hits)}. The shortfall of ${int(oracleCeiling - frame.hits)} is charged to regret, now at ${num(frame.cumulative_regret, 2)}.`}
              </p>
            </div>
            <p className="mono mt-2 text-[9px] leading-relaxed text-faint">
              the oracle ceiling is computed from the sealed truth, so it is a scoring reference
              rather than a policy the system could run. {int(frame.band_truth)} regions were
              occupied band-wide; the receiver sees {chose.length} per step. Exploration rate{" "}
              {pct(frame.exploration_rate)}.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  );
}

/** Normalise a landscape onto [0, 1] using its own min/max, so shape survives scale. */
function normaliser(values: number[]): (value: number) => number {
  let low = Infinity;
  let high = -Infinity;
  for (const value of values) {
    if (!Number.isFinite(value)) continue;
    if (value < low) low = value;
    if (value > high) high = value;
  }
  const span = high - low;
  if (!Number.isFinite(span) || span <= 0) return () => 0.5;
  return (value) => (value - low) / span;
}
