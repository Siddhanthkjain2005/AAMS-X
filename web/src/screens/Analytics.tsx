/** Analytics & Pareto — the screen that decides whether a difference is real.
 *
 * The Arena shows who led. This screen answers the harder question, and it is built around
 * three distinctions that a prettier dashboard would blur.
 *
 * *Significant* means both tests rejected. The server sets `Comparison.significant` only
 * when Welch's t **and** Mann-Whitney U reject at alpha = 0.05, and the matrix below
 * colours by effect size but outlines by that conjunction — so a large `d` with a split
 * verdict is visibly a large effect that six seeds cannot confirm, not a win.
 *
 * *On the frontier* means non-dominated in **all** objectives the server scored, which is
 * not the same as non-dominated in the two you happen to be looking at. The 2D plot draws
 * the projection's own non-dominated path as a line and rings the points that survive the
 * full comparison; when those disagree, the disagreement is the information.
 *
 * *Every comparison shares one control.* `POST /experiments/arena` fixes it at `nts`, so
 * this screen can rank arms against that control and nothing else. There is no MAG-NTS
 * versus UCB p-value to be had from a batch, and computing one from two independent
 * aggregates would be a different test wearing the same name.
 */

import { Html, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import {
  Axis3d,
  Boxes,
  GitCompare,
  Scale,
  Sigma,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState } from "react";
import * as THREE from "three";

import { useHistory } from "@/api/queries";
import {
  HEADLINE_METRICS,
  type BatchResult,
  type Comparison,
  type ParetoFrontier,
} from "@/api/types";
import { ComparisonTable } from "@/components/eval/ComparisonTable";
import { useBatchResult } from "@/components/eval/useBatchResult";
import { Chart } from "@/components/viz/Chart";
import {
  Badge,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  Select,
  Stat,
  Tabs,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import {
  higherIsBetter,
  isoClock,
  metricLabel,
  ms,
  num,
  policyLabel,
  pvalue,
  signed,
} from "@/lib/format";
import {
  DIVERGING_STOPS,
  PALETTE,
  policyColor,
  rampCss,
  sampleRamp,
  rgbCss,
} from "@/lib/palette";
import { useSession } from "@/state/session";

/** Cohen's d conventions. The bands are Cohen's own, not tuned to flatter a result. */
const D_LARGE = 0.8;
const D_CEILING = 2;

type View = "frontier" | "space";

export default function Analytics() {
  const batchId = useSession((session) => session.batchId);
  const setBatchId = useSession((session) => session.setBatchId);
  const view = useBatchResult(batchId);
  const history = useHistory({ limit: 30 });
  const [metric, setMetric] = useState<string>(
    "sustained_detection_probability",
  );

  const result = view.result;
  const batches = (history.data?.experiments ?? []).filter(
    (record) => record.kind === "arena" || record.kind === "ablation",
  );

  const significant = result
    ? result.comparisons.filter((row) => row.significant)
    : [];
  const split = result
    ? result.comparisons.filter(
        (row) =>
          row.significant === false &&
          (row.welch_p < 0.05 || row.mannwhitney_p < 0.05),
      )
    : [];
  const seeds = result
    ? Math.min(...result.variants.map((variant) => result.n_runs[variant] ?? 0))
    : 0;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <Panel flush className="shrink-0">
        <div className="flex flex-wrap items-end gap-4 p-3.5">
          <div className="min-w-64">
            <span className="eyebrow">Batch</span>
            <Select
              value={batchId ?? ""}
              onChange={(next) => setBatchId(next || null)}
              options={[
                {
                  value: "",
                  label: batches.length
                    ? "select a batch…"
                    : "no batches recorded yet",
                },
                ...batches.map((record) => ({
                  value: record.experiment_id,
                  label: `${record.kind} · ${record.scenario_id} · ${isoClock(record.created_at)} · ${record.status}`,
                })),
              ]}
              className="mt-1"
            />
          </div>
          <Stat
            label="Arms"
            value={result ? String(result.variants.length) : "—"}
            hint={
              result
                ? `control · ${policyLabel(result.comparisons[0]?.control ?? "nts")}`
                : "—"
            }
            tone="ink"
          />
          <Stat
            label="Seeds per arm"
            value={seeds ? String(seeds) : "—"}
            hint={
              seeds && seeds < 5
                ? "thin for a rank test"
                : "identical seeds across arms"
            }
            tone={seeds && seeds < 5 ? "warn" : "good"}
          />
          <Stat
            label="Significant results"
            value={result ? String(significant.length) : "—"}
            hint="both tests reject at α = 0.05"
            tone="accent"
          />
          <Stat
            label="Split verdicts"
            value={result ? String(split.length) : "—"}
            hint="one test rejected, one did not — reported as no result"
            tone={split.length > 0 ? "warn" : "ink"}
          />
          <Stat
            label="On the frontier"
            value={result?.pareto ? String(result.pareto.frontier.length) : "—"}
            hint={
              result?.pareto?.vacuous
                ? "vacuous — an axis is missing everywhere"
                : "non-dominated across every objective"
            }
            tone={result?.pareto?.vacuous ? "bad" : "mag"}
          />
        </div>
      </Panel>

      {!batchId ? (
        <Panel className="min-h-96 flex-1">
          <EmptyState
            title="No batch selected"
            detail="Pick a recorded arena or ablation batch above, or run one from the Arena screen. Significance needs several seeds per arm, so a single episode cannot appear here."
            icon={<Sigma className="size-5 text-faint" />}
          />
        </Panel>
      ) : view.loading ? (
        <Panel className="min-h-96 flex-1">
          <LoadingState
            label={view.running ? "batch still running" : "loading the batch"}
          />
        </Panel>
      ) : view.error ? (
        <Panel className="min-h-96 flex-1">
          <ErrorState error={view.error} />
        </Panel>
      ) : !result ? (
        <Panel className="min-h-96 flex-1">
          <EmptyState
            title="This batch has no aggregate yet"
            detail="Aggregates and comparisons are written when every seed of every arm has finished. Until then there is nothing to test."
            icon={<Boxes className="size-5 text-faint" />}
          />
        </Panel>
      ) : (
        <AnalyticsBody result={result} metric={metric} onMetric={setMetric} />
      )}
    </div>
  );
}

function AnalyticsBody({
  result,
  metric,
  onMetric,
}: {
  result: BatchResult;
  metric: string;
  onMetric: (metric: string) => void;
}) {
  const [view, setView] = useState<View>("frontier");
  const pareto = result.pareto ?? null;
  const rows = result.comparisons.filter((row) => row.metric === metric);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_360px]">
      <div className="flex min-h-0 flex-col gap-3">
        <Panel
          flush
          title="Objective space"
          subtitle="detection against its costs — no single winner is claimed"
          actions={
            <Tabs
              value={view}
              onChange={setView}
              tabs={[
                { value: "frontier", label: "Frontier" },
                { value: "space", label: "3D" },
              ]}
            />
          }
          className="min-h-80 flex-1"
        >
          {!pareto ? (
            <EmptyState
              title="No frontier in this record"
              detail="The frontier is attached by the live engine, so a batch reloaded from the registry's JSON artefact may not carry one. Re-running the batch produces it."
              icon={<Axis3d className="size-5 text-faint" />}
            />
          ) : view === "frontier" ? (
            <ParetoPlot pareto={pareto} />
          ) : (
            <ParetoSpace3D pareto={pareto} />
          )}
        </Panel>

        <Panel
          flush
          title="Significance × effect size"
          subtitle="colour is Cohen's d against the control; an outline means both tests rejected"
          className="shrink-0"
        >
          <SignificanceMatrix
            result={result}
            metric={metric}
            onMetric={onMetric}
          />
        </Panel>

        <Panel
          flush
          title={`Comparisons · ${metricLabel(metric)}`}
          subtitle="both p-values, always — a single asterisk hides the interesting case"
          className="shrink-0"
        >
          {rows.length === 0 ? (
            <p className="px-4 py-5 text-center text-[11px] text-faint">
              No comparison was recorded for this metric. Either no arm reported
              it, or the batch predates it.
            </p>
          ) : (
            <ComparisonTable comparisons={rows} className="px-3.5 pb-3" />
          )}
        </Panel>
      </div>

      <div className="flex min-h-0 flex-col gap-3 overflow-auto">
        <Panel
          flush
          title="Effect size"
          subtitle={`Cohen's d · ${metricLabel(metric)}`}
          actions={
            <Select
              value={metric}
              onChange={onMetric}
              options={(HEADLINE_METRICS as readonly string[]).map((name) => ({
                value: name,
                label: metricLabel(name),
              }))}
              className="w-44"
            />
          }
        >
          <EffectSizeBars rows={rows} metric={metric} />
        </Panel>

        <Panel
          title="The cost of deciding"
          subtitle="p95 decision latency against detection"
        >
          <LatencyScatter result={result} />
        </Panel>

        <Panel
          title="What counts as a result"
          subtitle="the rule, not a preference"
        >
          <div className="flex flex-col gap-2 text-[10.5px] leading-relaxed text-muted">
            <p>
              A difference is reported as significant only when Welch's{" "}
              <em>t</em> and Mann-Whitney U both reject at α = 0.05. Welch alone
              is sensitive to a single lucky seed; the rank test alone is blunt
              at this sample size. Requiring both costs statistical power, and
              that is the trade being made deliberately.
            </p>
            <p>
              Cohen's <em>d</em> is reported beside every verdict because a
              non-significant large effect and a non-significant tiny one mean
              different things: the first is a candidate for more seeds, the
              second is a dead end.
            </p>
            <p className="mono text-[9.5px] text-faint">
              n ={" "}
              {Math.min(...result.variants.map((v) => result.n_runs[v] ?? 0))}{" "}
              seeds per arm · control{" "}
              {policyLabel(result.comparisons[0]?.control ?? "nts")} · every arm
              ran the same seeds on the same recordings
            </p>
          </div>
        </Panel>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * The frontier, in two dimensions at a time.
 * ------------------------------------------------------------------------- */

interface PlotPoint {
  label: string;
  x: number;
  y: number;
  onFrontier: boolean;
  dominatedBy: string[];
}

type Direction = "maximise" | "minimise";

const noWorse = (a: number, b: number, direction: Direction) =>
  direction === "maximise" ? a >= b : a <= b;
const better = (a: number, b: number, direction: Direction) =>
  direction === "maximise" ? a > b : a < b;

/**
 * Non-dominated in *this projection only*. The server's frontier is computed over every
 * objective it scored; a point can be dominated in all four and still survive a
 * two-axis view, which is exactly why this is drawn as a separate line rather than
 * substituted for `pareto.frontier`.
 */
function nonDominated(
  points: PlotPoint[],
  xDir: Direction,
  yDir: Direction,
): PlotPoint[] {
  return points.filter(
    (point) =>
      !points.some(
        (other) =>
          other !== point &&
          noWorse(other.x, point.x, xDir) &&
          noWorse(other.y, point.y, yDir) &&
          (better(other.x, point.x, xDir) || better(other.y, point.y, yDir)),
      ),
  );
}

function ParetoPlot({ pareto }: { pareto: ParetoFrontier }) {
  const objectives = pareto.objectives;
  const [xMetric, setXMetric] = useState(
    objectives[1]?.metric ?? objectives[0]?.metric ?? "",
  );
  const [yMetric, setYMetric] = useState(objectives[0]?.metric ?? "");

  const xAxis =
    objectives.find((entry) => entry.metric === xMetric) ?? objectives[0];
  const yAxis =
    objectives.find((entry) => entry.metric === yMetric) ??
    objectives[1] ??
    objectives[0];

  const points: PlotPoint[] = useMemo(() => {
    if (!xAxis || !yAxis) return [];
    return pareto.points
      .map((point) => ({
        label: point.label,
        x: point.values[xAxis.metric],
        y: point.values[yAxis.metric],
        onFrontier: point.on_frontier,
        dominatedBy: point.dominated_by,
      }))
      .filter(
        (point): point is PlotPoint =>
          point.x !== undefined && point.y !== undefined,
      );
  }, [pareto.points, xAxis, yAxis]);

  const projected = useMemo(
    () =>
      xAxis && yAxis
        ? nonDominated(points, xAxis.direction, yAxis.direction)
        : [],
    [points, xAxis, yAxis],
  );
  const projectedLabels = new Set(projected.map((point) => point.label));
  const disagreement = points.filter(
    (point) => point.onFrontier !== projectedLabels.has(point.label),
  );

  if (!xAxis || !yAxis) {
    return (
      <EmptyState
        title="Objective space is empty"
        detail="The frontier record carries no objectives, which happens when none of the four Pareto metrics was collected."
        icon={<Axis3d className="size-5 text-faint" />}
      />
    );
  }

  const line = [...projected].sort((a, b) => a.x - b.x);

  return (
    <div className="flex h-full min-h-0 flex-col">
      {(pareto.vacuous || pareto.axes_missing.length > 0) && (
        <div className="mx-3 mt-2 flex items-start gap-2 rounded-md border border-warn/40 bg-warn/8 px-2.5 py-2">
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0 text-warn" />
          <p className="text-[10px] leading-relaxed text-warn">
            {pareto.vacuous
              ? "This frontier is vacuous: every point is missing the same axis, so nothing can dominate anything. A full frontier here means the comparison could not be made — not that every policy is optimal."
              : `Missing from every point: ${pareto.axes_missing.map(metricLabel).join(", ")}. The frontier was computed on the remaining axes only.`}
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2 px-3 pt-2">
        <label className="flex flex-col gap-1">
          <span className="eyebrow">x</span>
          <Select
            value={xMetric}
            onChange={setXMetric}
            options={objectives.map((entry) => ({
              value: entry.metric,
              label: entry.label,
            }))}
            className="w-52"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="eyebrow">y</span>
          <Select
            value={yMetric}
            onChange={setYMetric}
            options={objectives.map((entry) => ({
              value: entry.metric,
              label: entry.label,
            }))}
            className="w-52"
          />
        </label>
        <div className="mono flex flex-col gap-0.5 pb-1 text-[9px] text-faint">
          <span>
            ○ ringed · non-dominated across all {objectives.length} objectives (
            {pareto.frontier.length})
          </span>
          <span>
            — line · non-dominated in this 2D projection ({projected.length})
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1">
        <Chart
          height="100%"
          option={{
            grid: { left: 62, right: 92, top: 22, bottom: 46 },
            tooltip: {
              trigger: "item",
              formatter: (params: {
                data?: { name?: string; value?: number[] };
              }) => {
                const name = params.data?.name ?? "";
                const point = points.find((entry) => entry.label === name);
                if (!point) return name;
                return [
                  `<b>${policyLabel(name)}</b>`,
                  `${xAxis.label}: ${num(point.x, 4)}`,
                  `${yAxis.label}: ${num(point.y, 4)}`,
                  point.onFrontier
                    ? "on the full frontier"
                    : `dominated by ${point.dominatedBy.map(policyLabel).join(", ") || "—"}`,
                ].join("<br/>");
              },
            },
            xAxis: {
              type: "value",
              name: `${xAxis.label} ${xAxis.direction === "maximise" ? "↑" : "↓"}`,
              nameLocation: "middle",
              nameGap: 26,
              scale: true,
            },
            yAxis: {
              type: "value",
              name: `${yAxis.label} ${yAxis.direction === "maximise" ? "↑" : "↓"}`,
              nameLocation: "middle",
              nameGap: 46,
              scale: true,
            },
            series: [
              {
                type: "line",
                silent: true,
                showSymbol: false,
                lineStyle: {
                  color: PALETTE.accentDim,
                  width: 1.5,
                  type: "dashed",
                },
                data: line.map((point) => [point.x, point.y]),
                z: 2,
              },
              {
                type: "scatter",
                z: 6,
                symbolSize: (
                  _value: unknown,
                  params: { data: { onFrontier: boolean } },
                ) => (params.data.onFrontier ? 19 : 11),
                label: {
                  show: true,
                  position: "right",
                  distance: 8,
                  color: PALETTE.inkDim,
                  fontSize: 10,
                  fontFamily: "var(--font-mono)",
                  formatter: (params: { data: { name: string } }) =>
                    policyLabel(params.data.name),
                },
                data: points.map((point) => ({
                  name: point.label,
                  value: [point.x, point.y],
                  onFrontier: point.onFrontier,
                  itemStyle: {
                    color: point.onFrontier
                      ? policyColor(point.label)
                      : "transparent",
                    borderColor: policyColor(point.label),
                    borderWidth: point.onFrontier ? 2.5 : 1.5,
                    opacity: point.onFrontier ? 1 : 0.85,
                  },
                })),
              },
            ],
          }}
        />
      </div>

      <p className="mono px-3.5 pb-2 text-[9px] leading-relaxed text-faint">
        {disagreement.length > 0
          ? `${disagreement.length} point(s) disagree between the full frontier and this projection — dropping two objectives changes who is dominated, which is the argument for reading all four.`
          : "The projection and the full frontier agree on every point here."}
      </p>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Three objectives at once. Position is the measured value; nothing is inverted to make
 * a corner mean "best", because a viewer who reads a coordinate off this plot should get
 * the number that was measured. Which direction is better is written on the axis.
 * ------------------------------------------------------------------------- */

const CUBE = 6;

interface SpacePoint {
  label: string;
  coords: [number, number, number];
  values: number[];
  onFrontier: boolean;
}

function ParetoSpace3D({ pareto }: { pareto: ParetoFrontier }) {
  const axes = pareto.objectives.slice(0, 3);

  const points = useMemo<SpacePoint[]>(() => {
    if (axes.length < 3) return [];
    const usable = pareto.points.filter((point) =>
      axes.every((axis) => point.values[axis.metric] !== undefined),
    );
    // Normalise each axis over the points that exist, so a tight cluster still spreads
    // across the cube instead of collapsing into one corner.
    const ranges = axes.map((axis) => {
      const values = usable.map((point) => point.values[axis.metric] as number);
      const low = Math.min(...values);
      const high = Math.max(...values);
      return { low, span: high - low || 1 };
    });
    return usable.map((point) => {
      const values = axes.map((axis) => point.values[axis.metric] as number);
      const scaled = values.map(
        (value, index) =>
          ((value - ranges[index].low) / ranges[index].span - 0.5) * CUBE,
      );
      return {
        label: point.label,
        coords: [scaled[0], scaled[1], scaled[2]] as [number, number, number],
        values,
        onFrontier: point.on_frontier,
      };
    });
  }, [axes, pareto.points]);

  if (axes.length < 3) {
    return (
      <EmptyState
        title="Three objectives are needed for this view"
        detail={`This batch scored ${axes.length}. The 2D frontier shows what it does have.`}
        icon={<Axis3d className="size-5 text-faint" />}
      />
    );
  }

  return (
    <div className="relative h-full min-h-0">
      <Canvas camera={{ position: [8.5, 6.5, 9.5], fov: 42 }} dpr={[1, 2]}>
        <ambientLight intensity={0.7} />
        <pointLight position={[8, 10, 8]} intensity={70} color="#8fe9e0" />
        <pointLight position={[-8, 4, -6]} intensity={40} color="#a78bfa" />
        <AxisCage />
        <gridHelper
          args={[CUBE * 1.6, 16, PALETTE.line, "#0e1620"]}
          position={[0, -CUBE / 2, 0]}
        />
        {points.map((point) => (
          <SpaceMarker key={point.label} point={point} />
        ))}
        {axes.map((axis, index) => (
          <Html
            key={axis.metric}
            position={
              index === 0
                ? [CUBE / 2 + 0.6, -CUBE / 2, 0]
                : index === 1
                  ? [-CUBE / 2, CUBE / 2 + 0.5, 0]
                  : [-CUBE / 2, -CUBE / 2, CUBE / 2 + 0.6]
            }
            center
            style={{ pointerEvents: "none" }}
          >
            <span className="mono rounded bg-void/85 px-1.5 py-0.5 text-[9px] whitespace-nowrap text-muted">
              {axis.label} {axis.direction === "maximise" ? "↑" : "↓"}
            </span>
          </Html>
        ))}
        <OrbitControls
          enablePan={false}
          minDistance={7}
          maxDistance={22}
          autoRotate
          autoRotateSpeed={0.35}
        />
      </Canvas>
      <p className="mono pointer-events-none absolute bottom-2 left-3 text-[9px] leading-relaxed text-faint">
        each axis normalised over the arms present · solid = non-dominated
        across all {pareto.objectives.length} objectives · hollow = dominated ·
        drag to orbit
      </p>
    </div>
  );
}

/** One arm in objective space, with a drop line so its floor position is readable. */
function SpaceMarker({ point }: { point: SpacePoint }) {
  const colour = policyColor(point.label);
  const [x, y, z] = point.coords;
  return (
    <group position={[x, y, z]}>
      <mesh>
        <sphereGeometry args={[point.onFrontier ? 0.28 : 0.19, 24, 24]} />
        <meshStandardMaterial
          color={colour}
          emissive={colour}
          emissiveIntensity={point.onFrontier ? 0.85 : 0.25}
          roughness={0.35}
          transparent={!point.onFrontier}
          opacity={point.onFrontier ? 1 : 0.5}
        />
      </mesh>
      {point.onFrontier && (
        <mesh>
          <sphereGeometry args={[0.46, 20, 20]} />
          <meshBasicMaterial
            color={colour}
            wireframe
            transparent
            opacity={0.28}
          />
        </mesh>
      )}
      <mesh position={[0, (-CUBE / 2 - y) / 2, 0]}>
        <cylinderGeometry args={[0.012, 0.012, Math.abs(-CUBE / 2 - y), 6]} />
        <meshBasicMaterial color={colour} transparent opacity={0.3} />
      </mesh>
      <Html
        center
        distanceFactor={11}
        position={[0, 0.55, 0]}
        style={{ pointerEvents: "none" }}
      >
        <span
          className="mono rounded bg-void/85 px-1 py-0.5 text-[10px] whitespace-nowrap"
          style={{ color: colour }}
        >
          {policyLabel(point.label)}
          <span className="ml-1 text-faint">
            {point.values.map((value) => num(value, 3)).join(" / ")}
          </span>
        </span>
      </Html>
    </group>
  );
}

/** The cube edges. Built as one `LineSegments` and mounted as a primitive. */
function AxisCage() {
  const cage = useMemo(() => {
    const half = CUBE / 2;
    const corners: [number, number, number][] = [
      [-half, -half, -half],
      [half, -half, -half],
      [half, -half, half],
      [-half, -half, half],
      [-half, half, -half],
      [half, half, -half],
      [half, half, half],
      [-half, half, half],
    ];
    const edges = [
      [0, 1],
      [1, 2],
      [2, 3],
      [3, 0],
      [4, 5],
      [5, 6],
      [6, 7],
      [7, 4],
      [0, 4],
      [1, 5],
      [2, 6],
      [3, 7],
    ];
    const positions = new Float32Array(edges.length * 6);
    edges.forEach(([a, b], index) => {
      positions.set(corners[a], index * 6);
      positions.set(corners[b], index * 6 + 3);
    });
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    const material = new THREE.LineBasicMaterial({
      color: PALETTE.lineBright,
      transparent: true,
      opacity: 0.45,
    });
    return new THREE.LineSegments(geometry, material);
  }, []);
  return <primitive object={cage} />;
}

/* ---------------------------------------------------------------------------
 * Effect size as colour, significance as an outline.
 *
 * Orientation matters more than the number's sign: a negative `d` on regret is an
 * improvement and a positive one on false alarms is not, so every cell is oriented by
 * `higherIsBetter(metric)` before it is coloured. Green therefore always means "better
 * than the control", whichever way the underlying metric runs.
 * ------------------------------------------------------------------------- */

function cellColour(orientedD: number): string {
  const t = Math.max(0, Math.min(1, orientedD / (2 * D_CEILING) + 0.5));
  return rgbCss(sampleRamp(DIVERGING_STOPS, t), 0.9);
}

function SignificanceMatrix({
  result,
  metric,
  onMetric,
}: {
  result: BatchResult;
  metric: string;
  onMetric: (metric: string) => void;
}) {
  const treatments = useMemo(() => {
    const seen = new Set(result.comparisons.map((row) => row.treatment));
    return result.variants.filter((variant) => seen.has(variant));
  }, [result]);

  const metrics = (HEADLINE_METRICS as readonly string[]).filter((name) =>
    result.comparisons.some((row) => row.metric === name),
  );

  const index = useMemo(() => {
    const map = new Map<string, Comparison>();
    for (const row of result.comparisons)
      map.set(`${row.metric}|${row.treatment}`, row);
    return map;
  }, [result.comparisons]);

  if (treatments.length === 0 || metrics.length === 0) {
    return (
      <EmptyState
        title="No comparisons in this batch"
        detail="Comparisons need at least two arms with the same seeds. A single-arm batch has aggregates but nothing to test them against."
        icon={<GitCompare className="size-5 text-faint" />}
      />
    );
  }

  return (
    <div className="min-w-0 overflow-x-auto px-3.5 pb-3">
      <table className="w-full border-collapse text-[11px]">
        <thead>
          <tr className="border-b border-line-bright">
            <th className="eyebrow sticky left-0 z-1 bg-panel py-2 pr-3 text-left">
              Metric
            </th>
            {treatments.map((treatment) => (
              <th key={treatment} className="px-1 py-2 text-center">
                <span
                  className="mono text-[10px] font-semibold whitespace-nowrap"
                  style={{ color: policyColor(treatment) }}
                >
                  {policyLabel(treatment)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {metrics.map((name) => {
            const higher = higherIsBetter(name);
            return (
              <tr key={name} className="border-b border-line/60 last:border-0">
                <td className="sticky left-0 z-1 bg-panel py-1 pr-3">
                  <button
                    type="button"
                    onClick={() => onMetric(name)}
                    className={cn(
                      "text-left text-[10.5px] transition-colors hover:text-accent",
                      name === metric
                        ? "font-semibold text-accent"
                        : "text-ink-dim",
                    )}
                  >
                    {metricLabel(name)}
                    <span className="ml-1 text-faint">
                      {higher ? "↑" : "↓"}
                    </span>
                  </button>
                </td>
                {treatments.map((treatment) => {
                  const row = index.get(`${name}|${treatment}`);
                  if (!row) {
                    return (
                      <td
                        key={treatment}
                        className="px-1 py-1 text-center text-faint"
                      >
                        ·
                      </td>
                    );
                  }
                  const oriented = higher ? row.cohens_d : -row.cohens_d;
                  const strong = Math.abs(row.cohens_d) >= D_LARGE;
                  return (
                    <td key={treatment} className="px-1 py-1">
                      <button
                        type="button"
                        onClick={() => onMetric(name)}
                        title={[
                          `${policyLabel(treatment)} vs ${policyLabel(row.control)}`,
                          `${metricLabel(name)} Δ ${signed(row.difference, 4)}`,
                          `d = ${signed(row.cohens_d, 2)}`,
                          `Welch p = ${pvalue(row.welch_p)}`,
                          `MWU p = ${pvalue(row.mannwhitney_p)}`,
                          row.significant
                            ? "both tests reject at α = 0.05"
                            : "not significant under the conjunction rule",
                        ].join(" · ")}
                        className={cn(
                          "mono flex h-7 w-full items-center justify-center rounded text-[10px] tabular-nums transition-transform hover:scale-[1.06]",
                          row.significant ? "ring-1 ring-ink/80" : "ring-0",
                        )}
                        style={{
                          background: cellColour(oriented),
                          color:
                            Math.abs(oriented) > 0.55
                              ? "#07100e"
                              : PALETTE.inkDim,
                        }}
                      >
                        {signed(row.cohens_d, 2)}
                        {strong && !row.significant && (
                          <span className="ml-0.5 opacity-70">·</span>
                        )}
                      </button>
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>

      <div className="mt-2 flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1.5">
          <span className="mono text-[9px] text-faint">worse</span>
          <span
            className="h-2 w-28 rounded-full"
            style={{
              background: `linear-gradient(to right, ${[0, 0.25, 0.5, 0.75, 1]
                .map((t) => rampCss(DIVERGING_STOPS, t))
                .join(", ")})`,
            }}
          />
          <span className="mono text-[9px] text-faint">
            better · |d| ≤ {D_CEILING}
          </span>
        </div>
        <span className="mono flex items-center gap-1 text-[9px] text-faint">
          <span className="inline-block size-2.5 rounded-sm ring-1 ring-ink/80" />
          outlined = both tests reject
        </span>
        <span className="mono text-[9px] text-faint">
          · = |d| ≥ {D_LARGE} but not significant — a large effect this many
          seeds cannot confirm
        </span>
      </div>
    </div>
  );
}

/** Cohen's d per arm for one metric, with the verdict beside it rather than implied by it. */
function EffectSizeBars({
  rows,
  metric,
}: {
  rows: Comparison[];
  metric: string;
}) {
  if (rows.length === 0) {
    return (
      <EmptyState
        title="Nothing to size"
        detail="No arm reported this metric in this batch."
        icon={<Scale className="size-5 text-faint" />}
      />
    );
  }
  const higher = higherIsBetter(metric);
  const ordered = [...rows].sort(
    (a, b) => Math.abs(b.cohens_d) - Math.abs(a.cohens_d),
  );
  const widest = Math.max(
    D_LARGE,
    ...ordered.map((row) => Math.abs(row.cohens_d)),
  );

  return (
    <div className="flex flex-col gap-2">
      {ordered.map((row) => {
        const oriented = higher ? row.cohens_d : -row.cohens_d;
        const fraction = Math.min(1, Math.abs(row.cohens_d) / widest);
        return (
          <div key={row.treatment} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-2">
              <span
                className="mono truncate text-[10.5px]"
                style={{ color: policyColor(row.treatment) }}
              >
                {policyLabel(row.treatment)}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="mono text-[10.5px] tabular-nums text-ink-dim">
                  d {signed(row.cohens_d, 2)}
                </span>
                {row.significant ? (
                  <Badge tone={oriented > 0 ? "good" : "bad"}>
                    {oriented > 0 ? "wins" : "loses"}
                  </Badge>
                ) : Math.abs(row.cohens_d) >= D_LARGE ? (
                  <Badge tone="warn">unconfirmed</Badge>
                ) : (
                  <Badge tone="neutral">n.s.</Badge>
                )}
              </span>
            </div>
            {/* A centre-anchored bar: the midline is the control, so direction is visible. */}
            <div className="relative h-1.5 overflow-hidden rounded-full bg-line/70">
              <span className="absolute top-0 bottom-0 left-1/2 w-px bg-line-bright" />
              <span
                className="absolute top-0 bottom-0 rounded-full"
                style={{
                  background: cellColour(oriented),
                  width: `${(fraction * 100) / 2}%`,
                  left: oriented >= 0 ? "50%" : undefined,
                  right: oriented < 0 ? "50%" : undefined,
                }}
              />
            </div>
            <span className="mono text-[9px] text-faint">
              Δ {signed(row.difference, 4)} · rel{" "}
              {signed(row.relative * 100, 1)}% · Welch {pvalue(row.welch_p)} ·
              MWU {pvalue(row.mannwhitney_p)} · n {row.n_treatment}/
              {row.n_control}
            </span>
          </div>
        );
      })}
      <p className="mono border-t border-line pt-2 text-[9px] leading-relaxed text-faint">
        Bars point right when the arm is better than the control on this metric,
        whichever direction the metric itself improves in. |d| ≥ {D_LARGE} is
        Cohen's "large".
      </p>
    </div>
  );
}

/**
 * Latency against detection. The one plot on this screen whose x-axis does not reproduce:
 * `Latency` is in-process wall clock on whatever machine ran the batch, so the *ordering*
 * of the arms is the claim and the absolute milliseconds are not (docs/LIMITATIONS.md §7).
 */
function LatencyScatter({ result }: { result: BatchResult }) {
  const points = result.variants
    .map((variant) => {
      const latency = result.latency[variant];
      const sdp =
        result.aggregates[variant]?.sustained_detection_probability?.mean;
      const reward = result.aggregates[variant]?.cumulative_reward?.mean;
      if (!latency || sdp === undefined || !Number.isFinite(sdp)) return null;
      return { variant, p95: latency.p95, sdp, reward: reward ?? 0 };
    })
    .filter(
      (
        entry,
      ): entry is {
        variant: string;
        p95: number;
        sdp: number;
        reward: number;
      } => Boolean(entry),
    );

  if (points.length === 0) {
    return (
      <p className="text-[10.5px] leading-relaxed text-faint">
        This batch recorded no per-decision latency, so the trade cannot be
        drawn.
      </p>
    );
  }

  const rewards = points.map((point) => point.reward);
  const lowReward = Math.min(...rewards);
  const rewardSpan = Math.max(...rewards) - lowReward || 1;

  return (
    <div className="flex flex-col gap-1.5">
      <Chart
        height={190}
        option={{
          grid: { left: 52, right: 18, top: 16, bottom: 38 },
          tooltip: {
            trigger: "item",
            formatter: (params: { data?: { name?: string } }) => {
              const point = points.find(
                (entry) => entry.variant === params.data?.name,
              );
              if (!point) return "";
              return [
                `<b>${policyLabel(point.variant)}</b>`,
                `p95 latency: ${ms(point.p95)}`,
                `sustained detection: ${num(point.sdp, 4)}`,
                `cumulative reward: ${num(point.reward, 2)}`,
              ].join("<br/>");
            },
          },
          xAxis: {
            type: "value",
            name: "p95 ms per decision ↓",
            nameLocation: "middle",
            nameGap: 24,
            scale: true,
          },
          yAxis: {
            type: "value",
            name: "SDP ↑",
            nameLocation: "middle",
            nameGap: 38,
            scale: true,
          },
          series: [
            {
              type: "scatter",
              symbolSize: (_v: unknown, params: { data: { reward: number } }) =>
                9 + ((params.data.reward - lowReward) / rewardSpan) * 16,
              label: {
                show: true,
                position: "top",
                color: PALETTE.faint,
                fontSize: 9,
                fontFamily: "var(--font-mono)",
                formatter: (params: { data: { name: string } }) =>
                  policyLabel(params.data.name),
              },
              data: points.map((point) => ({
                name: point.variant,
                value: [point.p95, point.sdp],
                reward: point.reward,
                itemStyle: { color: policyColor(point.variant), opacity: 0.9 },
              })),
            },
          ],
        }}
      />
      <p className="mono text-[9px] leading-relaxed text-faint">
        marker area ∝ cumulative reward. Latency is in-process wall clock on the
        machine that ran the batch — the ranking is the measurement, the
        milliseconds are not portable.
      </p>
    </div>
  );
}
