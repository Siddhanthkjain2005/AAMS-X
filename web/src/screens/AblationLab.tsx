/** Ablation Lab — what each component of the stack is actually worth.
 *
 * The server's ladder is additive, not subtractive: it starts at `NTS` with memory,
 * information gain, change detection, periodicity, the temporal encoder and uncertainty
 * exploration all switched off, then adds them back one at a time, and finishes at
 * `Full MAG-NTS`. Every rung is compared against the `NTS` floor with the same seeds. So
 * the number this screen exists to show is Δ-versus-floor per rung, and the ladder chart
 * is ordered the way the ladder is built rather than sorted by size — sorting it would
 * hide that `NTS+Memory+IG` is a *combination* rung and invite reading the two single-
 * component rungs as if their effects simply add.
 *
 * A rung can improve the mean and still fail both tests. Those are drawn as a hollow
 * delta, because a component that cannot be distinguished from noise at five seeds is a
 * finding, not a gap in the chart.
 */

import { Layers, TrendingDown, TrendingUp } from "lucide-react";
import { useState } from "react";

import type { BatchResult, Comparison } from "@/api/types";
import { BatchLauncher } from "@/components/eval/BatchLauncher";
import { ComparisonTable } from "@/components/eval/ComparisonTable";
import { MetricTable } from "@/components/eval/MetricTable";
import { meanOf, useBatchResult } from "@/components/eval/useBatchResult";
import { Chart, errorBarSeries } from "@/components/viz/Chart";
import { Badge, EmptyState, ErrorState, LoadingState, Panel, Select, Stat } from "@/components/ui";
import { higherIsBetter, int, metricLabel, num, pct, pvalue, signed } from "@/lib/format";
import { PALETTE, ablationColor } from "@/lib/palette";
import { useSession } from "@/state/session";

/** The rung that every other rung is measured against, set by `POST /experiments/ablation`. */
const FLOOR = "NTS";

const LADDER_METRICS = [
  "sustained_detection_probability",
  "event_detection_probability",
  "cumulative_reward",
  "time_to_detect_capped",
  "detection_rate",
  "false_alarm_rate",
  "detections_per_cost",
  "oracle_ratio",
] as const;

export default function AblationLab() {
  const batchId = useSession((state) => state.batchId);
  const view = useBatchResult(batchId);
  const [metric, setMetric] = useState<string>(LADDER_METRICS[0]);
  const result = view.result;

  const floorValue = result ? meanOf(result, FLOOR, metric) : null;
  const fullValue = result ? meanOf(result, "Full MAG-NTS", metric) : null;
  const fullRow = result
    ? result.comparisons.find((row) => row.treatment === "Full MAG-NTS" && row.metric === metric)
    : undefined;
  const significantRungs = result
    ? new Set(result.comparisons.filter((row) => row.significant).map((row) => row.treatment)).size
    : 0;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[340px_1fr]">
        <div className="flex flex-col gap-3">
          <Panel title="Run the ladder" subtitle="seven rungs, identical seeds on each">
            <BatchLauncher kind="ablation" view={view} />
          </Panel>

          <Panel title="How to read a rung" subtitle="the ladder is additive">
            <ul className="flex flex-col gap-2 text-[10.5px] leading-relaxed text-muted">
              <li>
                <span className="mono text-ink-dim">NTS</span> — the floor. Neural Thompson
                sampling with the whole associative and predictive stack switched off. Every Δ on
                this screen is against this rung.
              </li>
              <li>
                <span className="mono text-ink-dim">NTS+Memory</span>,{" "}
                <span className="mono text-ink-dim">NTS+IG</span>,{" "}
                <span className="mono text-ink-dim">NTS+ChangeDetection</span>,{" "}
                <span className="mono text-ink-dim">NTS+Periodicity</span> — one component added
                back at a time.
              </li>
              <li>
                <span className="mono text-ink-dim">NTS+Memory+IG</span> — the interaction rung.
                If it beats the sum of the two single rungs, the components are complementary; if
                it does not, they are partly redundant.
              </li>
              <li>
                <span className="mono text-ink-dim">Full MAG-NTS</span> — everything on. This is
                the policy every other screen runs.
              </li>
            </ul>
          </Panel>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          {!batchId ? (
            <Panel className="min-h-72 flex-1">
              <EmptyState
                title="No ladder loaded"
                detail="The brief calls this mandatory, and it is the only screen that can say which part of the architecture earns its place. Run one on the left."
                icon={<Layers className="size-5 text-faint" />}
              />
            </Panel>
          ) : view.loading ? (
            <Panel className="min-h-72 flex-1">
              <LoadingState label="Climbing the ladder" />
            </Panel>
          ) : view.error ? (
            <Panel className="min-h-72 flex-1">
              <ErrorState error={new Error(view.error)} />
            </Panel>
          ) : !result ? (
            <Panel className="min-h-72 flex-1">
              <EmptyState
                title="The ladder has not reported yet"
                detail="Aggregates appear once every rung has run every seed."
              />
            </Panel>
          ) : (
            <>
              <Panel flush>
                <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-4">
                  <Stat
                    label="Rungs"
                    value={int(result.variants.length)}
                    hint={`${int(result.n_runs[FLOOR] ?? 0)} seeds each · ${result.scenario.split} split`}
                    tone="ink"
                  />
                  <Stat
                    label={`${metricLabel(metric)} at the floor`}
                    value={floorValue === null ? "—" : num(floorValue, 3)}
                    hint="NTS with the stack switched off"
                    tone="ink"
                  />
                  <Stat
                    label="Full MAG-NTS"
                    value={fullValue === null ? "—" : num(fullValue, 3)}
                    hint={
                      floorValue !== null && fullValue !== null
                        ? `${signed(fullValue - floorValue, 3)} against the floor`
                        : "not reported on this ladder"
                    }
                    tone={
                      fullRow?.significant
                        ? higherIsBetter(metric) === fullRow.difference > 0
                          ? "good"
                          : "bad"
                        : "warn"
                    }
                  />
                  <Stat
                    label="Rungs with a significant Δ"
                    value={`${int(significantRungs)} / ${int(Math.max(0, result.variants.length - 1))}`}
                    hint="on at least one headline metric, both tests at α = 0.05"
                    tone={significantRungs > 0 ? "accent" : "warn"}
                  />
                </div>
              </Panel>

              <Panel
                title="The ladder"
                subtitle={`${metricLabel(metric)} per rung, 95% interval, floor drawn as the dashed line`}
                actions={
                  <Select
                    value={metric}
                    onChange={setMetric}
                    className="h-7 w-52 text-[11px]"
                    options={LADDER_METRICS.map((entry) => ({
                      value: entry,
                      label: metricLabel(entry),
                    }))}
                  />
                }
                flush
              >
                <LadderChart result={result} metric={metric} />
              </Panel>

              <Panel
                title="What each component bought"
                subtitle={`Δ against the ${FLOOR} floor on ${metricLabel(metric)}`}
              >
                <ContributionList result={result} metric={metric} />
              </Panel>

              <Panel
                title="Every rung, every headline metric"
                subtitle="mean ± sem over the same seeds"
                actions={<Badge tone="neutral">{result.scenario.scenario_id}</Badge>}
              >
                <MetricTable result={result} colourVariants={false} />
              </Panel>

              <Panel
                title={`Significance against ${FLOOR}`}
                subtitle="Welch's t and Mann-Whitney U, both required"
              >
                <ComparisonTable comparisons={result.comparisons} />
              </Panel>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function LadderChart({ result, metric }: { result: BatchResult; metric: string }) {
  const rows = result.variants.map((variant) => result.aggregates[variant]?.[metric] ?? null);
  if (!rows.some(Boolean)) {
    return (
      <div className="px-4 py-8">
        <EmptyState
          title={`No rung reported ${metricLabel(metric)}`}
          detail="Left blank rather than zeroed — a rung that did not report a metric did not score zero on it."
        />
      </div>
    );
  }
  const floor = result.aggregates[FLOOR]?.[metric]?.mean ?? null;
  const bars = rows.map((row, index) => ({
    value: row?.mean ?? 0,
    itemStyle: {
      color: ablationColor(index, result.variants.length),
      borderRadius: [0, 3, 3, 0],
    },
  }));
  const intervals: [number, number, number][] = rows.map((row, index) => [
    index,
    row?.ci_low ?? 0,
    row?.ci_high ?? 0,
  ]);

  return (
    <Chart
      height={54 + result.variants.length * 30}
      option={{
        grid: { left: 132, right: 28, top: 12, bottom: 34 },
        xAxis: { type: "value", name: metricLabel(metric), nameGap: 22, nameLocation: "middle" },
        yAxis: {
          type: "category",
          data: result.variants,
          axisLabel: { fontSize: 10, color: PALETTE.inkDim },
          inverse: true,
        },
        tooltip: {
          trigger: "axis",
          formatter: (params: { dataIndex: number }[]) => {
            const index = params[0]?.dataIndex ?? 0;
            const row = rows[index];
            if (!row) return "no value";
            const delta = floor === null ? null : row.mean - floor;
            return [
              `<b>${result.variants[index]}</b>`,
              `mean ${num(row.mean, 4)} · n = ${row.n}`,
              `95% CI [${num(row.ci_low, 4)}, ${num(row.ci_high, 4)}]`,
              delta === null ? "" : `vs ${FLOOR}: ${signed(delta, 4)}`,
            ]
              .filter(Boolean)
              .join("<br/>");
          },
        },
        series: [
          {
            type: "bar",
            data: bars,
            barMaxWidth: 18,
            markLine:
              floor === null
                ? undefined
                : {
                    silent: true,
                    symbol: "none",
                    label: { show: true, formatter: FLOOR, color: PALETTE.faint, fontSize: 9 },
                    lineStyle: { color: PALETTE.warn, type: "dashed", width: 1 },
                    data: [{ xAxis: floor }],
                  },
          },
          errorBarSeries(intervals, PALETTE.ink, true),
        ],
      }}
    />
  );
}

function ContributionList({ result, metric }: { result: BatchResult; metric: string }) {
  const higher = higherIsBetter(metric);
  const rows: (Comparison | null)[] = result.variants
    .filter((variant) => variant !== FLOOR)
    .map(
      (variant) =>
        result.comparisons.find((row) => row.treatment === variant && row.metric === metric) ?? null,
    );

  if (!rows.some(Boolean)) {
    return (
      <p className="text-[11px] leading-relaxed text-faint">
        This batch carries no comparison for {metricLabel(metric)} — the ladder ran, but the metric
        was not among the ones the server tested.
      </p>
    );
  }

  const widest = Math.max(...rows.map((row) => (row ? Math.abs(row.relative) : 0)), 0.01);

  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((row, index) => {
        const variant = result.variants.filter((entry) => entry !== FLOOR)[index];
        if (!row) {
          return (
            <div key={variant} className="mono flex items-center gap-2 text-[10.5px] text-faint">
              <span className="w-40 truncate">{variant}</span>
              <span>not compared on this metric</span>
            </div>
          );
        }
        const good = higher === row.difference > 0;
        const colour = row.significant ? (good ? PALETTE.good : PALETTE.bad) : PALETTE.muted;
        const width = (Math.abs(row.relative) / widest) * 100;
        return (
          <div key={variant} className="flex items-center gap-2">
            <span className="mono w-40 shrink-0 truncate text-[10.5px] text-ink-dim">{variant}</span>
            <div className="relative h-4 min-w-0 flex-1 overflow-hidden rounded bg-void">
              <div
                className="absolute inset-y-0.5 left-0 rounded transition-[width] duration-300"
                style={{
                  width: `${Math.max(1.5, width)}%`,
                  background: row.significant ? colour : "transparent",
                  border: row.significant ? undefined : `1px dashed ${colour}`,
                }}
              />
            </div>
            <span className="mono w-44 shrink-0 text-right text-[10px] whitespace-nowrap">
              <span style={{ color: colour }}>
                {signed(row.difference, 3)} ({pct(row.relative, 1)})
              </span>
              <span className="ml-1.5 text-faint">
                d {num(row.cohens_d, 2)} · p {pvalue(Math.max(row.welch_p, row.mannwhitney_p))}
              </span>
            </span>
            {row.significant ? (
              good ? (
                <TrendingUp className="size-3.5 shrink-0 text-good" />
              ) : (
                <TrendingDown className="size-3.5 shrink-0 text-bad" />
              )
            ) : (
              <span className="w-3.5 shrink-0" />
            )}
          </div>
        );
      })}
      <p className="mt-1.5 text-[10px] leading-relaxed text-faint">
        Bar length is the relative change against the {FLOOR} floor. A hollow, dashed bar means the
        difference did not clear both tests at α = 0.05 — the component moved the mean but not
        distinguishably from seed noise at this sample size. The p shown is the larger of the two,
        because the verdict needs both.
      </p>
    </div>
  );
}
