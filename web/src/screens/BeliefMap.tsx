/** Belief Map — the posterior the scheduler actually reasons over.
 *
 * Nothing on this screen is a measurement. That is the point: a receiver with a 4-region
 * window measures four regions per step and *infers* the other twenty-eight, and the
 * quality of that inference is what makes active sensing work. So the three fields are
 * shown side by side against time — what the system believes, how unsure it is, and how
 * long since it last looked — because a confident belief over a stale region is exactly
 * the failure mode the uncertainty term exists to prevent.
 *
 * The truth overlay is opt-in and off by default. It is available because the run stores
 * it for scoring; it is off because leaving it on invites reading the posterior as if the
 * scheduler could see it, which it cannot (`env.sealed()`).
 */

import { Boxes, Clock, Eye, EyeOff } from "lucide-react";
import { useState } from "react";

import { useScenario } from "@/api/queries";
import { isEpisodeResult, type Frame } from "@/api/types";
import { NoRun } from "@/components/run/NoRun";
import { RunStatusBar } from "@/components/run/RunStatusBar";
import { Button, Panel, Stat, Tabs } from "@/components/ui";
import { FieldWaterfall } from "@/components/viz/FieldWaterfall";
import { RampLegend } from "@/components/viz/RampLegend";
import { RegionBars } from "@/components/viz/RegionBars";
import { Sparkline } from "@/components/viz/Sparkline";
import { Surface3D } from "@/components/viz/Surface3D";
import { cn } from "@/lib/cn";
import { int, num, pct, regionLabel } from "@/lib/format";
import { BELIEF_LUT, HEAT_LUT, PALETTE, UNCERTAINTY_LUT } from "@/lib/palette";
import { useActiveFrame, useLive } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

/** Staleness is unbounded in steps; this is the ceiling the ramp saturates at. */
const STALENESS_CEILING = 40;

type View = "field" | "surface";

export default function BeliefMap() {
  const { state, frames } = useLive();
  const frame = useActiveFrame();
  const experimentId = useSession((session) => session.experimentId);
  const scenario = useScenario(state.session?.scenario_id ?? null);
  const [showTruth, setShowTruth] = useState(false);
  const [view, setView] = useState<View>("field");

  const nRegions = scenario.data?.n_regions ?? frame?.belief.length ?? 32;
  const centres = scenario.data?.segments_measured?.[0]?.grid?.centre_mhz;
  const snapshot = isEpisodeResult(state.result) ? state.result.context_snapshot.belief : null;

  if (!experimentId) {
    return (
      <div className="p-4">
        <Panel className="min-h-96">
          <NoRun what="belief map" />
        </Panel>
      </div>
    );
  }

  const meanBelief = frame ? mean(frame.belief) : null;
  const meanUncertainty = frame ? mean(frame.uncertainty) : null;
  const maxStale = frame ? Math.max(...frame.staleness, 0) : null;
  const unseen = frame ? frame.staleness.filter((value) => value >= STALENESS_CEILING).length : 0;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <RunStatusBar />

      <Panel flush className="shrink-0">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-3 xl:grid-cols-6">
          <Stat
            label="Mean belief"
            value={meanBelief === null ? "—" : num(meanBelief, 3)}
            hint="posterior P(occupied) across the band"
            tone="accent"
          />
          <Stat
            label="Mean uncertainty"
            value={meanUncertainty === null ? "—" : num(meanUncertainty, 3)}
            hint="what the exploration term reads"
            tone="warn"
          />
          <Stat
            label="Stalest region"
            value={maxStale === null ? "—" : int(maxStale)}
            hint="steps since that region was measured"
            tone={maxStale !== null && maxStale > STALENESS_CEILING ? "bad" : "ink"}
          />
          <Stat
            label="Cold regions"
            value={frame ? int(unseen) : "—"}
            hint={`of ${nRegions} · ≥ ${STALENESS_CEILING} steps unobserved`}
            tone={unseen > nRegions / 2 ? "warn" : "ink"}
          />
          <Stat
            label="Occupied now"
            value={frame ? int(frame.band_truth) : "—"}
            hint={`of ${nRegions} regions · sealed truth, scoring only`}
            tone="mag"
          />
          <Stat
            label="Exploration rate"
            value={frame ? pct(frame.exploration_rate) : "—"}
            hint={
              frame?.change.flag
                ? `boosted ×${num(1 + frame.change.exploration_boost, 2)} by change`
                : "no change flagged"
            }
            tone={frame?.change.flag ? "bad" : "signal"}
          />
        </div>
      </Panel>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_360px]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            flush
            title={view === "field" ? "Posterior against time" : "Posterior as terrain"}
            subtitle="every cell is inference — the receiver measured only the marked window"
            actions={
              <>
                <Tabs
                  value={view}
                  onChange={setView}
                  tabs={[
                    { value: "field", label: "Field" },
                    { value: "surface", label: "3D" },
                  ]}
                />
                <RampLegend lut={BELIEF_LUT} min={0} max={1} label="P(occupied)" className="w-32" />
              </>
            }
            className="min-h-64 flex-1"
          >
            {view === "field" ? (
              <FieldWaterfall
                frames={frames}
                nRegions={nRegions}
                select={(f) => f.belief}
                lut={BELIEF_LUT}
                label="belief"
              />
            ) : (
              <Surface3D
                frames={frames}
                nRegions={nRegions}
                select={(f, region) => f.belief[region] ?? 0}
                lut={BELIEF_LUT}
                caption="height = posterior P(occupied) · entirely inferred · drag to orbit"
              />
            )}
          </Panel>

          <div className="grid shrink-0 grid-cols-1 gap-3 md:grid-cols-2">
            <Panel
              flush
              title="Uncertainty"
              subtitle="posterior spread, the exploration driver"
              actions={
                <RampLegend lut={UNCERTAINTY_LUT} min={0} max={1} label="σ" className="w-24" />
              }
            >
              <div className="h-28">
                <FieldWaterfall
                  frames={frames}
                  nRegions={nRegions}
                  select={(f) => f.uncertainty}
                  lut={UNCERTAINTY_LUT}
                  markObserved={false}
                />
              </div>
            </Panel>
            <Panel
              flush
              title="Staleness"
              subtitle={`steps since last measured · saturates at ${STALENESS_CEILING}`}
              actions={
                <RampLegend
                  lut={HEAT_LUT}
                  min={0}
                  max={STALENESS_CEILING}
                  unit="steps"
                  label="age"
                  className="w-28"
                />
              }
            >
              <div className="h-28">
                <FieldWaterfall
                  frames={frames}
                  nRegions={nRegions}
                  select={(f) => f.staleness}
                  lut={HEAT_LUT}
                  scale={(value) => value / STALENESS_CEILING}
                  markObserved={false}
                />
              </div>
            </Panel>
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            flush
            title="Band state at this step"
            subtitle={frame ? `step ${int(frame.step)}` : "waiting"}
            actions={
              <Button
                size="sm"
                variant={showTruth ? "primary" : "subtle"}
                icon={showTruth ? <Eye className="size-3" /> : <EyeOff className="size-3" />}
                onClick={() => setShowTruth((prior) => !prior)}
              >
                truth
              </Button>
            }
          >
            {frame ? (
              <div className="flex flex-col gap-2 px-2 pb-2">
                <FieldLabel text="belief" colour={PALETTE.accent} />
                <RegionBars
                  frames={frames}
                  frame={frame}
                  select={(f) => f.belief}
                  lut={BELIEF_LUT}
                  height={72}
                  showTruth={showTruth}
                />
                <FieldLabel text="uncertainty" colour={PALETTE.warn} />
                <RegionBars
                  frames={frames}
                  frame={frame}
                  select={(f) => f.uncertainty}
                  lut={UNCERTAINTY_LUT}
                  height={44}
                  highlightObserved={false}
                />
                <FieldLabel text="staleness" colour="#f2686b" />
                <RegionBars
                  frames={frames}
                  frame={frame}
                  select={(f) => f.staleness}
                  lut={HEAT_LUT}
                  scale={(value) => value / STALENESS_CEILING}
                  height={44}
                  highlightObserved={false}
                />
                <div className="mono flex justify-between px-0.5 text-[9px] text-faint">
                  <span>{regionLabel(0, centres?.[0])}</span>
                  <span className="text-accent">window {frame.regions.join(" · ")}</span>
                  <span>{regionLabel(nRegions - 1, centres?.[nRegions - 1])}</span>
                </div>
              </div>
            ) : (
              <p className="px-4 py-6 text-center text-[11px] text-faint">
                the posterior appears with the first frame
              </p>
            )}
          </Panel>

          <Panel
            flush
            title="Belief error against truth"
            subtitle="|P(occupied) − occupied|, averaged over the band"
          >
            <Sparkline
              frames={frames}
              value={(f) => beliefError(f)}
              colour={PALETTE.mag}
              domain={[0, 1]}
              height={70}
            />
            <p className="mono px-3.5 pb-2.5 text-[9px] leading-relaxed text-faint">
              computed in the browser from the sealed truth the run streams for scoring. The
              scheduler never sees this curve.
            </p>
          </Panel>

          <Panel title="Decomposition" subtitle="aleatoric vs epistemic" className="shrink-0">
            {snapshot ? (
              <div className="flex flex-col gap-2">
                <SplitRow
                  label="Aleatoric"
                  hint="noise in the channel — irreducible by looking again"
                  value={mean(snapshot.aleatoric)}
                  colour={PALETTE.signal}
                />
                <SplitRow
                  label="Epistemic"
                  hint="ignorance — this is what an observation buys down"
                  value={mean(snapshot.epistemic)}
                  colour={PALETTE.warn}
                />
                <SplitRow
                  label="Mean hit rate"
                  hint="fraction of observations that found signal"
                  value={mean(snapshot.hit_rate)}
                  colour={PALETTE.good}
                />
                <p className="mono mt-1 text-[9px] leading-relaxed text-faint">
                  <Clock className="mr-1 inline size-2.5" />
                  from the run's final context snapshot at step {int(
                    isEpisodeResult(state.result) ? state.result.context_snapshot.step : 0,
                  )}
                  , not from the live edge — the split is recorded once, at the end.
                </p>
              </div>
            ) : (
              <p className="text-[11px] leading-relaxed text-faint">
                <Boxes className="mr-1 inline size-3" />
                The aleatoric / epistemic split is written into the run's context snapshot when
                it finishes. It appears here once this run completes.
              </p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}

function FieldLabel({ text, colour }: { text: string; colour: string }) {
  return (
    <span className="mono flex items-center gap-1.5 text-[9px] tracking-widest text-faint uppercase">
      <span className="size-1.5 rounded-full" style={{ background: colour }} />
      {text}
    </span>
  );
}

function SplitRow({
  label,
  hint,
  value,
  colour,
}: {
  label: string;
  hint: string;
  value: number;
  colour: string;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-[11px] text-ink-dim">{label}</span>
        <span className="mono text-[11px] tabular-nums" style={{ color: colour }}>
          {num(value, 3)}
        </span>
      </div>
      <div className="h-1 overflow-hidden rounded-full bg-line">
        <div
          className={cn("h-full rounded-full")}
          style={{ width: `${Math.min(1, value) * 100}%`, background: colour }}
        />
      </div>
      <span className="text-[9.5px] leading-snug text-faint">{hint}</span>
    </div>
  );
}

function mean(values: number[] | undefined): number {
  if (!values || values.length === 0) return 0;
  let total = 0;
  for (const value of values) total += value;
  return total / values.length;
}

/** Mean absolute error of the posterior against the sealed truth for one frame. */
function beliefError(frame: Frame): number {
  const n = Math.min(frame.belief.length, frame.true_occupied.length);
  if (n === 0) return 0;
  let total = 0;
  for (let i = 0; i < n; i += 1) {
    total += Math.abs(frame.belief[i] - (frame.true_occupied[i] ? 1 : 0));
  }
  return total / n;
}
