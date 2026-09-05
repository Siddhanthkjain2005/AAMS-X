/** Algorithm Arena — MAG-NTS against the baselines on identical seeds.
 *
 * The screen is arranged so the weakest claim is hardest to make. The headline chart shows
 * a mean with its 95% interval, never a bare bar; the table prints `mean ± sem`; and the
 * verdict column comes from `Comparison.significant`, which the server sets only when
 * Welch's t *and* Mann-Whitney U both reject at alpha = 0.05. A policy can lead every mean
 * on this screen and still show no significant win, and if that is what the run produced,
 * that is what it says.
 *
 * The arena is also where the honest negative lives: `time_to_detect_capped` is censored
 * at the horizon, so a policy that never detects an event contributes the cap rather than
 * infinity. Comparing it is legitimate; reading it as a latency in seconds is not.
 *
 * One structural limit is on the screen rather than in a footnote. `POST /experiments/arena`
 * sets the control to `nts`, so every row of the comparison table is *arm vs NTS* — the
 * batch never holds arm-vs-arm samples, and inventing a MAG-NTS-vs-UCB p-value from two
 * independent aggregates would be a different (and wrong) test. A head-to-head against a
 * different control is a re-run, not a re-read.
 */

import { Swords, Trophy } from "lucide-react";

import { HEADLINE_METRICS, type BatchResult } from "@/api/types";
import { BatchLauncher } from "@/components/eval/BatchLauncher";
import { ComparisonTable } from "@/components/eval/ComparisonTable";
import { MetricTable } from "@/components/eval/MetricTable";
import { bestVariant, useBatchResult } from "@/components/eval/useBatchResult";
import { Chart, errorBarSeries } from "@/components/viz/Chart";
import { Badge, EmptyState, ErrorState, LoadingState, Panel, Stat, Tabs } from "@/components/ui";
import { higherIsBetter, int, metricLabel, ms, num, pct, policyLabel } from "@/lib/format";
import { PALETTE, policyColor } from "@/lib/palette";
import { useSession } from "@/state/session";
import { useState } from "react";

/** The four a judge asks about first. Everything else is one scroll down, in the table. */
const FEATURED = [
  "sustained_detection_probability",
  "time_to_detect_capped",
  "cumulative_reward",
  "false_alarm_rate",
] as const;

export default function Arena() {
  const batchId = useSession((state) => state.batchId);
  const view = useBatchResult(batchId);
  const [metric, setMetric] = useState<string>(FEATURED[0]);
  const result = view.result;

  const winner = result ? bestVariant(result, "sustained_detection_probability", true) : null;
  // Every comparison shares one control, so a "win" is MAG-NTS beating that control on a
  // metric in the direction that metric improves — not simply a significant difference.
  const magRows = result
    ? result.comparisons.filter((row) => row.treatment === "mag-nts" && row.significant)
    : [];
  const improved = (metric: string, difference: number) =>
    higherIsBetter(metric) ? difference > 0 : difference < 0;
  const magWins = magRows.filter((row) => improved(row.metric, row.difference)).length;
  const magLosses = magRows.length - magWins;
  const control = result?.comparisons[0]?.control ?? null;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[340px_1fr]">
        <div className="flex flex-col gap-3">
          <Panel title="Run an arena" subtitle="same recordings, same seeds, same budget">
            <BatchLauncher kind="arena" view={view} />
          </Panel>

          {result && (
            <Panel title="Decision latency" subtitle="in-process wall clock per decision">
              <div className="flex flex-col gap-1.5">
                {result.variants.map((variant) => {
                  const latency = result.latency[variant];
                  return (
                    <div key={variant} className="flex items-center justify-between gap-2">
                      <span
                        className="mono truncate text-[10.5px]"
                        style={{ color: policyColor(variant) }}
                      >
                        {policyLabel(variant)}
                      </span>
                      <span className="mono shrink-0 text-[10.5px] text-muted">
                        p50 {ms(latency?.p50)} · p95 {ms(latency?.p95)}
                      </span>
                    </div>
                  );
                })}
                <p className="mt-1 text-[10px] leading-snug text-faint">
                  Measured inside this process on this machine, so it is a shape not a spec: it
                  says MAG-NTS costs the same order as a bandit, not what it would cost on other
                  hardware.
                </p>
              </div>
            </Panel>
          )}
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          {!batchId ? (
            <Panel className="min-h-72 flex-1">
              <EmptyState
                title="No arena loaded"
                detail="Pick a scenario and run one. Six policies, the same seeds each, and every number on this screen comes out of those episodes."
                icon={<Swords className="size-5 text-faint" />}
              />
            </Panel>
          ) : view.loading ? (
            <Panel className="min-h-72 flex-1">
              <LoadingState label="Running the arena" />
            </Panel>
          ) : view.error ? (
            <Panel className="min-h-72 flex-1">
              <ErrorState error={new Error(view.error)} />
            </Panel>
          ) : !result ? (
            <Panel className="min-h-72 flex-1">
              <EmptyState
                title="The batch has not reported yet"
                detail="Aggregates appear when every episode in the batch has finished — a partial mean over a partial set of seeds would not be the statistic the table claims to show."
              />
            </Panel>
          ) : (
            <>
              <Panel flush>
                <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-4">
                  <Stat
                    label="Arms"
                    value={int(result.variants.length)}
                    hint={`${int(result.n_runs[result.variants[0]] ?? 0)} seeds each`}
                    tone="ink"
                  />
                  <Stat
                    label="Leads on sustained P(detect)"
                    value={winner ? policyLabel(winner) : "—"}
                    hint="highest mean — see the verdict column for whether it is significant"
                    tone={winner === "mag-nts" ? "good" : "warn"}
                  />
                  <Stat
                    label={`MAG-NTS wins vs ${control ? policyLabel(control) : "control"}`}
                    value={int(magWins)}
                    hint="both tests reject at α = 0.05, in the metric's good direction"
                    tone={magWins > 0 ? "good" : "ink"}
                  />
                  <Stat
                    label="Significant losses"
                    value={int(magLosses)}
                    hint={
                      magLosses
                        ? "the control was significantly better on these metrics"
                        : "none against this control"
                    }
                    tone={magLosses > 0 ? "bad" : "ink"}
                  />
                </div>
              </Panel>

              <Panel
                title={metricLabel(metric)}
                subtitle="mean over seeds, with the 95% confidence interval"
                actions={
                  <Tabs
                    value={metric}
                    onChange={setMetric}
                    tabs={FEATURED.map((entry) => ({ value: entry, label: metricLabel(entry) }))}
                  />
                }
                flush
              >
                <MetricChart result={result} metric={metric} />
              </Panel>

              <Panel
                title="All headline metrics"
                subtitle={`${HEADLINE_METRICS.length} metrics × ${result.variants.length} arms · mean ± sem`}
                actions={<Badge tone="neutral">{result.scenario.split} split</Badge>}
              >
                <MetricTable result={result} />
              </Panel>

              <Panel
                title={`Significance against the ${control ? policyLabel(control) : "control"} control`}
                subtitle="every arm is tested against the same control; both tests must reject"
                actions={
                  magWins > 0 ? (
                    <Badge tone="good">
                      <Trophy className="size-3" />
                      {magWins} significant for MAG-NTS
                    </Badge>
                  ) : (
                    <Badge tone="warn">no significant win on this batch</Badge>
                  )
                }
              >
                <ComparisonTable comparisons={result.comparisons} />
                <p className="mt-2 text-[10px] leading-relaxed text-faint">
                  Arm-vs-arm rows are absent because the batch does not hold them: the server
                  compares each arm's seeds against the control's seeds. Reading a MAG-NTS
                  advantage over UCB off two separate rows here is not a test, it is arithmetic
                  on two means.
                </p>
              </Panel>

              <Panel title="Recovery after a spliced change" subtitle="steps to re-detect, per seed">
                <RecoveryGrid result={result} />
              </Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function MetricChart({ result, metric }: { result: BatchResult; metric: string }) {
  const rows = result.variants.map((variant) => result.aggregates[variant]?.[metric] ?? null);
  const present = rows.some(Boolean);
  if (!present) {
    return (
      <div className="px-4 py-8">
        <EmptyState
          title={`No arm reported ${metricLabel(metric)}`}
          detail="The metric is left blank rather than filled with a zero, because zero is a value this run never produced."
        />
      </div>
    );
  }

  const labels = result.variants.map((variant) => policyLabel(variant));
  const bars = rows.map((row, index) => ({
    value: row?.mean ?? 0,
    itemStyle: { color: policyColor(result.variants[index]), borderRadius: [3, 3, 0, 0] },
  }));
  const intervals: [number, number, number][] = rows.map((row, index) => [
    index,
    row?.ci_low ?? 0,
    row?.ci_high ?? 0,
  ]);

  return (
    <Chart
      height={260}
      option={{
        grid: { left: 56, right: 20, top: 18, bottom: 44 },
        xAxis: { type: "category", data: labels, axisLabel: { interval: 0, rotate: 18 } },
        yAxis: { type: "value", name: metricLabel(metric), nameGap: 34, nameLocation: "middle" },
        tooltip: {
          trigger: "axis",
          formatter: (params: { dataIndex: number }[]) => {
            const index = params[0]?.dataIndex ?? 0;
            const row = rows[index];
            if (!row) return "no value";
            return [
              `<b>${labels[index]}</b>`,
              `mean ${num(row.mean, 4)}`,
              `95% CI [${num(row.ci_low, 4)}, ${num(row.ci_high, 4)}]`,
              `median ${num(row.median, 4)} · n = ${row.n}`,
            ].join("<br/>");
          },
        },
        series: [
          { type: "bar", data: bars, barMaxWidth: 46 },
          errorBarSeries(intervals, PALETTE.ink),
        ],
      }}
    />
  );
}

function RecoveryGrid({ result }: { result: BatchResult }) {
  const changePoints = result.scenario.change_points ?? [];
  if (!changePoints.length) {
    return (
      <p className="text-[11px] leading-relaxed text-faint">
        This scenario has no spliced boundary, so there is nothing to recover from. Recovery is
        only defined where a change point exists in the scenario spec.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {result.variants.map((variant) => {
        const seeds = result.recoveries[variant] ?? [];
        const entries = seeds.flatMap((recovery) => recovery.change_points);
        const recovered = entries.filter((entry) => entry.recovered);
        const delays = recovered
          .map((entry) => entry.recovered_after)
          .filter((value): value is number => value !== null);
        const mean = delays.length ? delays.reduce((a, b) => a + b, 0) / delays.length : null;
        return (
          <div key={variant} className="flex items-center gap-3">
            <span
              className="mono w-28 shrink-0 truncate text-[10.5px]"
              style={{ color: policyColor(variant) }}
            >
              {policyLabel(variant)}
            </span>
            <div className="flex min-w-0 flex-1 flex-wrap gap-1">
              {entries.map((entry, index) => (
                <span
                  key={`${entry.change_step}-${index}`}
                  title={
                    entry.recovered
                      ? `change at step ${entry.change_step}, re-detected ${entry.recovered_after} steps later`
                      : `change at step ${entry.change_step}, never re-detected within the horizon`
                  }
                  className="mono rounded px-1 py-0.5 text-[9.5px]"
                  style={{
                    background: entry.recovered ? `${PALETTE.good}22` : `${PALETTE.bad}22`,
                    color: entry.recovered ? PALETTE.good : PALETTE.bad,
                  }}
                >
                  {entry.recovered ? entry.recovered_after : "∞"}
                </span>
              ))}
            </div>
            <span className="mono shrink-0 text-[10px] text-muted">
              {mean === null ? "no recovery" : `mean ${num(mean, 1)} steps`}
              <span className="ml-1.5 text-faint">
                {pct(entries.length ? recovered.length / entries.length : 0, 0)} recovered
              </span>
            </span>
          </div>
        );
      })}
      <p className="mt-1 text-[10px] leading-relaxed text-faint">
        One box per change point per seed. `∞` means the policy did not re-detect the new regime
        before the horizon ran out; those seeds are excluded from the mean rather than counted as
        the cap, so the mean describes the runs that recovered and the percentage says how many
        did.
      </p>
    </div>
  );
}
