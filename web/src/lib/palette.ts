/** Colour as a measurement.
 *
 * Every ramp in this file maps a number to a hue, and nothing in the UI picks a colour for
 * decoration. That constraint is what lets a viewer read the waterfall without a legend
 * lookup for each panel: teal always means *measured signal*, amber always means
 * *uncertain*, red always means *missed*, green always means *confirmed*, violet always
 * means *retrieved from memory*.
 *
 * The ramps are precomputed into 256-entry `Uint8ClampedArray` LUTs because the waterfall
 * writes pixels directly into an `ImageData` buffer sixty times a second — building an
 * `rgb()` string per pixel would spend the whole frame budget in the string allocator.
 */

export const PALETTE = {
  void: "#070a0e",
  abyss: "#0b0f14",
  panel: "#111820",
  panel2: "#16202b",
  line: "#1e2a36",
  lineBright: "#2b3a4a",
  ink: "#e6edf3",
  inkDim: "#b6c2ce",
  muted: "#8b9bab",
  faint: "#5d6b7a",
  accent: "#4fd1c5",
  accentDim: "#2a8b83",
  signal: "#38bdf8",
  mag: "#a78bfa",
  warn: "#f0b429",
  bad: "#f2686b",
  good: "#63c98b",
} as const;

export type Rgb = [number, number, number];

function hexToRgb(hex: string): Rgb {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function mix(a: Rgb, b: Rgb, t: number): Rgb {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

/** Sample a multi-stop gradient at `t` in [0, 1]. */
export function sampleRamp(stops: readonly string[], t: number): Rgb {
  const clamped = Math.min(1, Math.max(0, t));
  const scaled = clamped * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(scaled));
  return mix(hexToRgb(stops[index]), hexToRgb(stops[index + 1]), scaled - index);
}

export function rgbCss(rgb: Rgb, alpha = 1): string {
  return alpha >= 1 ? `rgb(${rgb[0]} ${rgb[1]} ${rgb[2]})` : `rgb(${rgb[0]} ${rgb[1]} ${rgb[2]} / ${alpha})`;
}

/**
 * The spectrum ramp: deep background → teal → cyan → white-hot.
 *
 * This is the one ramp that is *not* linear in the input. Real e-CALLISTO margins spend
 * most of their range within a few dB of the detection threshold, so a linear map paints
 * a nearly uniform panel and hides exactly the structure the scheduler is chasing. The
 * `SPECTRUM` LUT is therefore built with a mild gamma that expands the low end.
 */
export const SPECTRUM_STOPS = [
  "#05080c",
  "#0a1a26",
  "#0f3a44",
  "#16706b",
  "#28b0a0",
  "#6fe3c8",
  "#c8fff0",
  "#ffffff",
] as const;

export const HEAT_STOPS = ["#0b0f14", "#173a5e", "#2a7bb8", "#4fd1c5", "#f0b429", "#f2686b"] as const;
export const BELIEF_STOPS = ["#0b0f14", "#1d3a4d", "#2a8b83", "#4fd1c5", "#a8f0e6"] as const;
export const UNCERTAINTY_STOPS = ["#0b0f14", "#3a2f10", "#8a6a14", "#f0b429", "#ffe6a3"] as const;
export const MEMORY_STOPS = ["#0b0f14", "#2a2350", "#5b46a8", "#a78bfa", "#ddd0ff"] as const;
export const DIVERGING_STOPS = ["#f2686b", "#8a4a52", "#1e2a36", "#3f8f6f", "#63c98b"] as const;

const LUT_SIZE = 256;

function buildLut(stops: readonly string[], gamma = 1): Uint8ClampedArray {
  const lut = new Uint8ClampedArray(LUT_SIZE * 4);
  for (let i = 0; i < LUT_SIZE; i += 1) {
    const t = (i / (LUT_SIZE - 1)) ** gamma;
    const [r, g, b] = sampleRamp(stops, t);
    lut[i * 4] = r;
    lut[i * 4 + 1] = g;
    lut[i * 4 + 2] = b;
    lut[i * 4 + 3] = 255;
  }
  return lut;
}

/** gamma 0.72 expands the bottom of the range, where real margins actually live. */
export const SPECTRUM_LUT = buildLut(SPECTRUM_STOPS, 0.72);
export const HEAT_LUT = buildLut(HEAT_STOPS);
export const BELIEF_LUT = buildLut(BELIEF_STOPS);
export const UNCERTAINTY_LUT = buildLut(UNCERTAINTY_STOPS);
export const MEMORY_LUT = buildLut(MEMORY_STOPS);

/** Index a LUT with a normalised value. Returns the byte offset, not a colour object. */
export function lutOffset(value: number): number {
  const clamped = value <= 0 ? 0 : value >= 1 ? 1 : value;
  return (clamped * (LUT_SIZE - 1) + 0.5) << 2;
}

export function rampCss(stops: readonly string[], t: number): string {
  return rgbCss(sampleRamp(stops, t));
}

/** CSS gradient for a legend strip, so the legend cannot drift from the LUT. */
export function rampGradient(stops: readonly string[], direction = "to right"): string {
  return `linear-gradient(${direction}, ${stops.join(", ")})`;
}

/**
 * Fixed colours per policy, so a line is the same colour on every screen. Assigned in
 * `ARENA_ORDER` so the weakest baseline is coolest and MAG-NTS is the accent — the eye
 * follows the same object through the arena, the ablation ladder and the Pareto plot.
 */
export const POLICY_COLORS: Record<string, string> = {
  "round-robin": "#5d6b7a",
  random: "#8b9bab",
  ucb: "#38bdf8",
  thompson: "#a78bfa",
  nts: "#f0b429",
  "mag-nts": "#4fd1c5",
  dqn: "#f2686b",
  sac: "#63c98b",
};

export function policyColor(name: string): string {
  const base = name.split("[")[0];
  return POLICY_COLORS[base] ?? PALETTE.muted;
}

/** Ablation rungs are shades of the accent: further from full policy → dimmer. */
export function ablationColor(index: number, total: number): string {
  return rampCss(["#2a3f4d", PALETTE.accentDim, PALETTE.accent], total <= 1 ? 1 : index / (total - 1));
}

export const SEVERITY_COLORS = {
  info: PALETTE.muted,
  success: PALETTE.good,
  warning: PALETTE.warn,
  critical: PALETTE.bad,
  insight: PALETTE.mag,
} as const;

/** The eight MAG-NTS terms. Positive terms take warm-to-teal, penalties take red. */
export const FACTOR_COLORS: Record<string, string> = {
  detection: PALETTE.accent,
  information: PALETTE.signal,
  memory: PALETTE.mag,
  periodicity: "#7dd3fc",
  uncertainty: PALETTE.warn,
  recency: "#c084fc",
  cost: PALETTE.bad,
  switching: "#fb7185",
};
