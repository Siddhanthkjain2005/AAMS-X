/** The ECharts wrapper, with this console's theme applied once.
 *
 * Every statistical chart in the app goes through here so axis colours, tooltip styling
 * and the tabular-figures font are decided in one place. Two conventions are enforced
 * rather than left to each caller: the grid is tight (a research chart is mostly data),
 * and animation is off for anything that updates while a run streams — a 400 ms ease on a
 * live series reads as lag, not polish.
 */

import ReactECharts from "echarts-for-react";
import type { CSSProperties } from "react";

import { PALETTE } from "@/lib/palette";

const AXIS = {
  axisLine: { lineStyle: { color: PALETTE.line } },
  axisTick: { show: false },
  axisLabel: { color: PALETTE.faint, fontSize: 10, fontFamily: "var(--font-mono)" },
  splitLine: { lineStyle: { color: PALETTE.line, type: "dashed" as const, opacity: 0.55 } },
  nameTextStyle: { color: PALETTE.muted, fontSize: 10 },
};

/** Merged under every option. Callers override by simply setting the same key. */
export const CHART_BASE = {
  backgroundColor: "transparent",
  animationDuration: 260,
  textStyle: { color: PALETTE.inkDim, fontFamily: "var(--font-sans)", fontSize: 11 },
  grid: { left: 46, right: 16, top: 24, bottom: 30, containLabel: false },
  tooltip: {
    backgroundColor: "rgba(11, 15, 20, 0.96)",
    borderColor: PALETTE.lineBright,
    borderWidth: 1,
    padding: [7, 10],
    textStyle: { color: PALETTE.ink, fontSize: 11, fontFamily: "var(--font-mono)" },
    axisPointer: { lineStyle: { color: PALETTE.lineBright }, crossStyle: { color: PALETTE.lineBright } },
  },
  legend: {
    textStyle: { color: PALETTE.muted, fontSize: 10, fontFamily: "var(--font-mono)" },
    inactiveColor: PALETTE.faint,
    itemWidth: 12,
    itemHeight: 8,
  },
  xAxis: AXIS,
  yAxis: AXIS,
};

function deepMerge<T extends Record<string, unknown>>(base: T, patch: Record<string, unknown>): T {
  const out: Record<string, unknown> = { ...base };
  for (const [key, value] of Object.entries(patch)) {
    const prior = out[key];
    const mergeable =
      value !== null &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      prior !== null &&
      typeof prior === "object" &&
      !Array.isArray(prior);
    out[key] = mergeable
      ? deepMerge(prior as Record<string, unknown>, value as Record<string, unknown>)
      : value;
  }
  return out as T;
}

export function Chart({
  option,
  height = 240,
  className,
  style,
  onEvents,
  live = false,
}: {
  option: Record<string, unknown>;
  height?: number | string;
  className?: string;
  style?: CSSProperties;
  onEvents?: Record<string, (params: never) => void>;
  /** Set while the series is being appended to from a stream: disables transitions. */
  live?: boolean;
}) {
  const merged = deepMerge(CHART_BASE, option);
  if (live) (merged as Record<string, unknown>).animation = false;
  return (
    <ReactECharts
      option={merged}
      notMerge
      lazyUpdate
      className={className}
      style={{ height, width: "100%", ...style }}
      opts={{ renderer: "canvas" }}
      onEvents={onEvents}
    />
  );
}

/** An error-bar series drawn as a custom renderer — ECharts has no built-in one. */
export function errorBarSeries(
  data: [number, number, number][],
  colour: string,
  horizontal = false,
): Record<string, unknown> {
  return {
    type: "custom",
    silent: true,
    z: 5,
    renderItem: (
      _params: unknown,
      api: {
        value: (index: number) => number;
        coord: (point: number[]) => number[];
        size: (value: number[]) => number[];
        style: (extra: Record<string, unknown>) => Record<string, unknown>;
      },
    ) => {
      const index = api.value(0);
      const low = api.value(1);
      const high = api.value(2);
      const cap = 5;
      const [aX, aY] = horizontal ? api.coord([low, index]) : api.coord([index, low]);
      const [bX, bY] = horizontal ? api.coord([high, index]) : api.coord([index, high]);
      const shapes = horizontal
        ? [
            { x1: aX, y1: aY, x2: bX, y2: bY },
            { x1: aX, y1: aY - cap, x2: aX, y2: aY + cap },
            { x1: bX, y1: bY - cap, x2: bX, y2: bY + cap },
          ]
        : [
            { x1: aX, y1: aY, x2: bX, y2: bY },
            { x1: aX - cap, y1: aY, x2: aX + cap, y2: aY },
            { x1: bX - cap, y1: bY, x2: bX + cap, y2: bY },
          ];
      return {
        type: "group",
        children: shapes.map((shape) => ({
          type: "line",
          shape,
          style: api.style({ stroke: colour, lineWidth: 1.25, fill: undefined }),
        })),
      };
    },
    encode: { x: horizontal ? [1, 2] : 0, y: horizontal ? 0 : [1, 2] },
    data,
  };
}
