/** Number and label formatting.
 *
 * One rule runs through this file: *never print more precision than the quantity has.*
 * A probability estimated from six seeds gets three decimals, a p-value gets four, and a
 * wall-clock latency gets two — because latency is the one published measurement in this
 * project that does not reproduce run to run (docs/LIMITATIONS.md §7). Formatting is
 * where that honesty is either kept or quietly thrown away.
 */

const NBSP = " ";

export function num(value: number | null | undefined, decimals = 2): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return value.toFixed(decimals);
}

export function int(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return Math.round(value).toLocaleString("en-US");
}

/** A probability as a percentage. Three significant decimals is the honest ceiling here. */
export function pct(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return `${(value * 100).toFixed(decimals)}%`;
}

export function signed(value: number, decimals = 2): string {
  if (!Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  return `${sign}${Math.abs(value).toFixed(decimals)}`;
}

/** p-values below the smallest MWU value at n=6 are reported as a bound, not a fiction. */
export function pvalue(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  if (value < 0.0001) return "<0.0001";
  return value.toFixed(4);
}

export function ms(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return `${value.toFixed(2)}${NBSP}ms`;
}

export function db(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(decimals)}${NBSP}dB`;
}

export function mhz(value: number | null | undefined, decimals = 1): string {
  if (value === null || value === undefined || !Number.isFinite(value))
    return "—";
  return `${value.toFixed(decimals)}${NBSP}MHz`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds))
    return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  if (minutes < 60)
    return `${minutes}m${NBSP}${String(rest).padStart(2, "0")}s`;
  return `${Math.floor(minutes / 60)}h${NBSP}${String(minutes % 60).padStart(2, "0")}m`;
}

export function bytes(value: number): string {
  if (!Number.isFinite(value)) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let scaled = value;
  let unit = 0;
  while (scaled >= 1024 && unit < units.length - 1) {
    scaled /= 1024;
    unit += 1;
  }
  return `${scaled.toFixed(scaled < 10 && unit > 0 ? 1 : 0)}${NBSP}${units[unit]}`;
}

/** `1755102550.4` (server epoch seconds) → local wall clock. */
export function clock(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "—";
  return new Date(epochSeconds * 1000).toLocaleTimeString("en-GB", {
    hour12: false,
  });
}

export function timestamp(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "—";
  return new Date(epochSeconds * 1000).toLocaleString("en-GB", {
    hour12: false,
  });
}

/**
 * The registry stores times as ISO text while a live session reports epoch floats, and
 * `GET /experiments/{id}` can return either. These four helpers exist so that difference
 * is handled once instead of at every call site — passing an ISO string to `clock()`
 * multiplies a string by 1000 and prints "Invalid Date", which is how this was found.
 */
export function isoOrEpochSeconds(
  value: number | string | null | undefined,
): number | null {
  if (value === null || value === undefined || value === "") return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed / 1000;
}

/** ISO (or epoch) → local wall clock, time only. */
export function isoClock(value: number | string | null | undefined): string {
  return clock(isoOrEpochSeconds(value));
}

/** ISO (or epoch) → local date and time. */
export function isoStamp(value: number | string | null | undefined): string {
  return timestamp(isoOrEpochSeconds(value));
}

/** Elapsed seconds between two stamps of either shape, or null if one is missing. */
export function isoElapsed(
  from: number | string | null | undefined,
  to: number | string | null | undefined,
): number | null {
  const a = isoOrEpochSeconds(from);
  const b = isoOrEpochSeconds(to);
  return a === null || b === null ? null : b - a;
}

/** `R07 · 118.4 MHz` — the same region label the Python side prints. */
export function regionLabel(region: number, centreMhz?: number): string {
  const index = `R${String(region).padStart(2, "0")}`;
  return centreMhz === undefined
    ? index
    : `${index}${NBSP}·${NBSP}${centreMhz.toFixed(1)} MHz`;
}

/** The scheduler keys the API uses. Anything else is already a display label. */
const SCHEDULER_KEYS = new Set([
  "round-robin",
  "random",
  "ucb",
  "thompson",
  "nts",
  "mag-nts",
  "dqn",
  "sac",
]);

/**
 * Turn `mag-nts` / `mag-nts[no-memory]` into something a slide can show.
 *
 * Batch variant keys are not all scheduler keys: the ablation ladder names its rungs
 * `NTS+Memory`, `Full MAG-NTS` and so on, server-side, already capitalised for display.
 * Upper-casing those would print `NTS+MEMORY`, so an unrecognised key is returned as it
 * came — the server chose that string deliberately and the browser should not restyle it.
 */
export function policyLabel(name: string): string {
  const [base, ablation] = name.split("[");
  if (!SCHEDULER_KEYS.has(base)) return name;
  const pretty = base === "mag-nts" ? "MAG-NTS" : base.toUpperCase();
  return ablation ? `${pretty} · ${ablation.replace("]", "")}` : pretty;
}

export function metricLabel(metric: string): string {
  return METRIC_LABELS[metric] ?? metric.replace(/_/g, " ");
}

/** Display names for the thirteen headline metrics, plus the ones the KPI row uses. */
export const METRIC_LABELS: Record<string, string> = {
  cumulative_reward: "Cumulative reward",
  cumulative_regret: "Cumulative regret",
  sustained_detection_probability: "Sustained detection",
  event_detection_probability: "Event detection",
  sustained_detection_delay: "Sustained TTD",
  time_to_detect_capped: "Time to detect (capped)",
  detection_rate: "Detection rate",
  false_alarm_rate: "False-alarm rate",
  detections_per_cost: "Detections per unit cost",
  information_per_observation: "Bits per observation",
  oracle_ratio: "Oracle ratio",
  band_coverage: "Band coverage",
  sensing_cost: "Sensing cost",
  precision: "Precision",
  mean_detection_delay: "Mean detection delay",
  regret_per_step: "Regret per step",
};

/** Which direction is better, for colouring a delta. Regret and cost are minimised. */
export function higherIsBetter(metric: string): boolean {
  return !(
    metric.includes("regret") ||
    metric.includes("cost") ||
    metric.includes("delay") ||
    metric.includes("false_alarm") ||
    metric.startsWith("time_to_detect")
  );
}
