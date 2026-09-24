/** Command Center — the screen the demo opens on.
 *
 * Reading order is deliberate. The KPI strip is the claim (how much of the band's activity
 * was actually caught, and at what cost). The waterfall under it is the evidence, streaming.
 * The right rail is the control. The bottom row is the trend, so a judge can see that the
 * reward curve is still climbing while the regret curve flattens.
 *
 * Every number here comes from the current frame — nothing is accumulated in the browser,
 * because a browser-side total that drifts from the server's would be indistinguishable
 * from a scheduler that scored differently. That constraint decides the labels: `hits`,
 * `false_alarms`, `oracle_best` and `band_truth` are all *per-step* quantities in the frame
 * contract, so they are labelled per step. Only `cumulative_reward` and `cumulative_regret`
 * are running totals, and only those two are shown as such.
 */

import { Activity, Crosshair, Layers3, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { useScenario } from "@/api/queries";
import { FactorBars, contributionTotal } from "@/components/viz/FactorBars";
import { RampLegend } from "@/components/viz/RampLegend";
import { RegionBars } from "@/components/viz/RegionBars";
import { Sparkline } from "@/components/viz/Sparkline";
import { Waterfall } from "@/components/viz/Waterfall";
import { LaunchPanel } from "@/components/run/LaunchPanel";
import { RunStatusBar } from "@/components/run/RunStatusBar";
import { Badge, Button, EmptyState, LiveDot, Panel, Stat } from "@/components/ui";
import { db, int, num, pct, regionLabel, signed } from "@/lib/format";
import { BELIEF_LUT, PALETTE, SPECTRUM_LUT, UNCERTAINTY_LUT } from "@/lib/palette";
import { useLive } from "@/state/LiveProvider";
import { useActiveFrame } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

export default function CommandCenter() {
  const { state, frames } = useLive();
  const frame = useActiveFrame();
  const experimentId = useSession((session) => session.experimentId);
  const scenarioId = state.session?.scenario_id ?? null;
  const scenario = useScenario(scenarioId);

  const nRegions = scenario.data?.n_regions ?? frame?.belief.length ?? 32;
  const centres = scenario.data?.segments_measured?.[0]?.grid?.centre_mhz;
  const flagsThisStep = frame ? frame.hits + frame.false_alarms : 0;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <RunStatusBar />

      {/* The claim. */}
      <Panel flush className="shrink-0">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-4 xl:grid-cols-8">
          <Stat
            label="Step"
            value={frame ? int(frame.step) : "—"}
            hint={frame ? `t + ${num(frame.t_sec, 1)} s` : "waiting for the first frame"}
            tone="ink"
          />
          <Stat
            label="Hits this step"
            value={frame ? int(frame.hits) : "—"}
            hint={frame ? `of ${int(frame.oracle_best)} the oracle could have caught here` : undefined}
            tone="good"
          />
          <Stat
            label="False alarms"
            value={frame ? int(frame.false_alarms) : "—"}
            hint={frame ? `${int(flagsThisStep)} flags raised this step` : undefined}
            tone={frame && frame.false_alarms > frame.hits ? "bad" : "ink"}
          />
          <Stat
            label="Cumulative reward"
            value={frame ? num(frame.cumulative_reward, 1) : "—"}
            hint="interpretable multi-objective sum"
            tone="accent"
          />
          <Stat
            label="Regret vs oracle"
            value={frame ? num(frame.cumulative_regret, 1) : "—"}
            hint="lower is better; oracle sees the truth"
            tone="warn"
          />
          <Stat
            label="Budget left"
            value={frame ? num(frame.budget_remaining, 0) : "—"}
            hint="Σ c(a_t) ≤ B"
            tone={frame && frame.budget_remaining <= 0 ? "bad" : "signal"}
          />
          <Stat
            label="Recall"
            value={frame ? num(frame.memory.similarity, 2) : "—"}
            hint={
              frame?.memory.recognised
                ? `context #${frame.memory.prototype_id} · ${frame.memory.label}`
                : "no context recognised yet"
            }
            tone={frame?.memory.recognised ? "mag" : "ink"}
          />
          <Stat
            label="Period"
            value={frame && frame.periodicity.period_steps > 0 ? int(frame.periodicity.period_steps) : "—"}
            hint={
              frame && frame.periodicity.period_steps > 0
                ? `strength ${num(frame.periodicity.strength, 2)}`
                : "no cycle mined yet"
            }
            tone="signal"
          />
        </div>
      </Panel>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_340px]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            flush
            title="Live spectrum intelligence waterfall"
            subtitle={
              scenario.data
                ? `${scenario.data.name} · ${nRegions} regions · ${scenario.data.time_bin} s bins`
                : "measured margin above each region's own detection threshold"
            }
            actions={
              <>
                <RampLegend
                  lut={SPECTRUM_LUT}
                  min={0}
                  max={14}
                  unit="dB"
                  label="margin"
                  className="w-40"
                />
                {frame && !frame.available && <Badge tone="warn">archive gap</Badge>}
                <Badge tone={state.status === "streaming" ? "accent" : "neutral"}>
                  <LiveDot active={state.status === "streaming"} />
                  {state.status}
                </Badge>
              </>
            }
            className="min-h-72 flex-1"
          >
            {experimentId ? (
              <Waterfall frames={frames} nRegions={nRegions} centreMhz={centres} />
            ) : (
              <EmptyState
                title="No stream yet"
                detail="Configure a scenario on the right and run an episode. The waterfall paints what the receiver measured, not a simulation of it."
                icon={<Activity className="size-5 text-faint" />}
              />
            )}
          </Panel>

          <Panel
            flush
            title="Band state now"
            subtitle="posterior occupancy per region, with the observed window outlined"
            actions={
              <>
                <RampLegend lut={BELIEF_LUT} min={0} max={1} label="belief" className="w-28" />
                <RampLegend
                  lut={UNCERTAINTY_LUT}
                  min={0}
                  max={1}
                  label="uncertainty"
                  className="w-28"
                />
              </>
            }
            className="shrink-0"
          >
            {frame ? (
              <div className="flex flex-col gap-1 px-1 pb-1">
                <RegionBars
                  frames={frames}
                  frame={frame}
                  select={(f) => f.belief}
                  lut={BELIEF_LUT}
                  height={64}
                  showTruth={false}
                />
                <RegionBars
                  frames={frames}
                  frame={frame}
                  select={(f) => f.uncertainty}
                  lut={UNCERTAINTY_LUT}
                  height={34}
                  highlightObserved={false}
                />
                <div className="mono flex justify-between px-0.5 text-[9px] text-faint">
                  <span>{regionLabel(0, centres?.[0])}</span>
                  <span>
                    window {frame.regions.map((region) => region).join(" · ")}
                  </span>
                  <span>{regionLabel(nRegions - 1, centres?.[nRegions - 1])}</span>
                </div>
              </div>
            ) : (
              <div className="px-4 py-6 text-center text-[11px] text-faint">
                the posterior appears with the first frame
              </div>
            )}
          </Panel>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel title="Launch" subtitle="real cached recordings only">
            <LaunchPanel compact />
          </Panel>

          <Panel
            title="This decision"
            subtitle="weighted terms behind the chosen window"
            className="min-h-0 flex-1"
            actions={
              frame ? (
                <Link to="/decision">
                  <Button size="sm" variant="subtle" icon={<Crosshair className="size-3" />}>
                    Inspect
                  </Button>
                </Link>
              ) : null
            }
          >
            {frame ? (
              <div className="flex flex-col gap-3">
                <div className="flex items-baseline justify-between">
                  <span className="mono text-[11px] text-muted">
                    window {frame.regions[0]}–{frame.regions[frame.regions.length - 1]}
                  </span>
                  <span className="mono text-sm text-ink">
                    V = {num(frame.action_value, 3)}
                    <span className="ml-1.5 text-[10px] text-faint">
                      Σ terms {signed(contributionTotal(frame.factors), 3)}
                    </span>
                  </span>
                </div>
                <FactorBars factors={frame.factors} compact />
                {frame.notes.length > 0 && (
                  <ul className="flex flex-col gap-1 border-t border-line pt-2">
                    {frame.notes.slice(0, 4).map((note) => (
                      <li key={note} className="text-[10.5px] leading-snug text-muted">
                        · {note}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <EmptyState
                title="No decision to explain yet"
                detail="Each step the scheduler scores every candidate window; the eight weighted terms appear here."
                icon={<Sparkles className="size-5 text-faint" />}
              />
            )}
          </Panel>
        </div>
      </div>

      <div className="grid shrink-0 grid-cols-2 gap-3 xl:grid-cols-4">
        <TrendPanel
          label="Cumulative reward"
          value={frame ? num(frame.cumulative_reward, 1) : "—"}
          colour={PALETTE.accent}
          frames={frames}
          select={(f) => f.cumulative_reward}
        />
        <TrendPanel
          label="Cumulative regret"
          value={frame ? num(frame.cumulative_regret, 1) : "—"}
          colour={PALETTE.warn}
          frames={frames}
          select={(f) => f.cumulative_regret}
        />
        <TrendPanel
          label="Hits per step"
          value={frame ? int(frame.hits) : "—"}
          colour={PALETTE.good}
          frames={frames}
          select={(f) => f.hits}
          hint="in-window detections at each step, not a running total"
        />
        <TrendPanel
          label="Change score"
          value={frame ? num(frame.change.score, 2) : "—"}
          colour={PALETTE.bad}
          frames={frames}
          select={(f) => f.change.score}
          hint={
            frame
              ? `${frame.change.change_steps.length} detected · ${int(frame.change.steps_since_change)} steps since`
              : undefined
          }
        />
      </div>

      {frame && (
        <p className="mono shrink-0 px-1 text-[10px] leading-relaxed text-faint">
          <Layers3 className="mr-1 inline size-3" />
          measured margin {db(Math.max(...frame.measured_db, 0))} peak this step · exploration rate{" "}
          {pct(frame.exploration_rate)} · {int(frame.band_truth)} of {nRegions} regions occupied,
          oracle ceiling {int(frame.oracle_best)} in-window detections · truth is sealed from the
          scheduler and used only to score it
        </p>
      )}
    </div>
  );
}

function TrendPanel({
  label,
  value,
  colour,
  frames,
  select,
  hint,
}: {
  label: string;
  value: string;
  colour: string;
  frames: ReturnType<typeof useLive>["frames"];
  select: (frame: NonNullable<ReturnType<typeof useActiveFrame>>) => number;
  hint?: string;
}) {
  return (
    <Panel flush className="overflow-hidden">
      <div className="flex items-baseline justify-between px-3.5 pt-3">
        <span className="eyebrow">{label}</span>
        <span className="mono text-sm font-semibold" style={{ color: colour }}>
          {value}
        </span>
      </div>
      {hint && <p className="mono px-3.5 pt-0.5 text-[9px] text-faint">{hint}</p>}
      <Sparkline frames={frames} value={select} colour={colour} height={54} zeroLine />
    </Panel>
  );
}
