/** LIVE SPECTRUM INTELLIGENCE WATERFALL — the console's signature instrument.
 *
 * Design constraints that shaped the implementation:
 *
 * *It must hold 60 FPS while frames stream at 30 Hz.*  So the history lives in an
 * offscreen `ImageData` whose pixels are written directly from a colour LUT, and each new
 * frame shifts the image by one column instead of redrawing the past. Cost per frame is
 * one column of writes plus one `putImageData`, independent of how much history is shown.
 *
 * *It must not lie about what was measured.*  A real receiver with a 4-region window sees
 * four regions per step, not the whole band, so only those columns get fresh paint. The
 * rest of the column is the *belief* — visibly dimmer, drawn from the same value but with
 * reduced alpha — so a viewer can always tell measurement from inference. Regions the
 * scheduler has never visited stay near-black, which is the honest picture of a receiver
 * that cannot see the whole band at once.
 *
 * *An archive gap is a gap.*  `available: false` means the recording had no data at that
 * step; the column is painted as a dark hatch rather than as silence, because "no
 * measurement" and "measured, nothing there" are different claims.
 */

import { useEffect, useRef } from "react";

import type { Frame } from "@/api/types";
import type { FrameRing } from "@/api/stream";
import { useAnimationFrame } from "@/hooks/useExperimentStream";
import { useMeasure } from "@/hooks/useMeasure";
import { PALETTE, SPECTRUM_LUT, lutOffset } from "@/lib/palette";
import { cn } from "@/lib/cn";

/** dB above threshold that saturates the ramp. Real margins rarely exceed this. */
const MARGIN_CEILING_DB = 14;

interface WaterfallProps {
  frames: FrameRing | null;
  nRegions: number;
  /** Region centre frequencies, for the axis. Falls back to region indices. */
  centreMhz?: number[];
  /** Draw the sealed ground truth as a thin overlay stripe. Off during a live demo. */
  showTruth?: boolean;
  className?: string;
  /** Height of one history column in device pixels. 1 = maximum time depth. */
  columnWidth?: number;
}

interface RenderState {
  image: ImageData | null;
  /** Last frame step written, so a re-render does not double-write the same column. */
  lastStep: number;
  cursor: number;
}

export function Waterfall({
  frames,
  nRegions,
  centreMhz,
  showTruth = false,
  className,
  columnWidth = 2,
}: WaterfallProps) {
  const [wrapRef, size] = useMeasure<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<RenderState>({ image: null, lastStep: -1, cursor: 0 });

  const columns = Math.max(16, Math.floor(size.width / columnWidth));

  // Rebuild the buffer whenever the geometry changes, then replay whatever history the
  // ring already holds so a resize (or a screen switch) does not blank the instrument.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || columns < 16 || nRegions < 1) return;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) return;
    canvas.width = columns;
    canvas.height = nRegions;
    const image = context.createImageData(columns, nRegions);
    // Fill with the ramp's floor rather than transparent black, so an empty instrument
    // reads as "no signal yet" instead of a hole in the panel.
    for (let i = 0; i < image.data.length; i += 4) {
      image.data[i] = SPECTRUM_LUT[0];
      image.data[i + 1] = SPECTRUM_LUT[1];
      image.data[i + 2] = SPECTRUM_LUT[2];
      image.data[i + 3] = 255;
    }
    stateRef.current = { image, lastStep: -1, cursor: 0 };

    const history = frames?.tail(columns) ?? [];
    for (const frame of history) writeColumn(stateRef.current, frame, nRegions, columns, showTruth);
    context.putImageData(image, 0, 0);
  }, [columns, nRegions, frames, showTruth]);

  useAnimationFrame(() => {
    const canvas = canvasRef.current;
    const state = stateRef.current;
    if (!canvas || !state.image || !frames) return;
    const latest = frames.at(-1);
    if (!latest || latest.step === state.lastStep) return;

    // Catch up rather than jump: if two frames landed inside one animation frame, both
    // columns are drawn, so the time axis stays proportional to steps and never skips.
    const behind = state.lastStep < 0 ? 1 : Math.min(frames.size, latest.step - state.lastStep);
    const backlog = frames.tail(Math.max(1, behind));
    for (const frame of backlog) {
      if (frame.step <= state.lastStep) continue;
      writeColumn(state, frame, nRegions, columns, showTruth);
    }
    const context = canvas.getContext("2d", { alpha: false });
    context?.putImageData(state.image, 0, 0);
  }, Boolean(frames));

  const labels = axisLabels(nRegions, centreMhz);

  return (
    <div className={cn("relative flex h-full min-h-0 w-full", className)}>
      <div className="mono flex w-16 shrink-0 flex-col justify-between border-r border-line py-0.5 pr-1.5 text-right text-[9px] text-faint">
        {labels.map((label) => (
          <span key={label.region} className="leading-none">
            {label.text}
          </span>
        ))}
      </div>
      <div ref={wrapRef} className="relative min-w-0 flex-1 overflow-hidden bg-void">
        <canvas
          ref={canvasRef}
          className="absolute inset-0 h-full w-full"
          // The buffer is one pixel per region; letting the GPU stretch it keeps the
          // instrument sharp horizontally while smoothing the frequency axis.
          style={{ imageRendering: "pixelated" }}
          aria-label="Live spectrum waterfall: frequency region against time, colour is dB above each region's detection threshold"
          role="img"
        />
        {/* The live edge. The waterfall scrolls right-to-left, so "now" is the right edge. */}
        <div
          className="pointer-events-none absolute inset-y-0 right-0 w-px"
          style={{ background: PALETTE.accent, boxShadow: `0 0 12px ${PALETTE.accent}` }}
        />
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-l from-transparent via-transparent to-abyss/70" />
      </div>
    </div>
  );
}

/** Write one frame into the rightmost column, scrolling the image left by one pixel. */
function writeColumn(
  state: RenderState,
  frame: Frame,
  nRegions: number,
  columns: number,
  showTruth: boolean,
): void {
  const image = state.image;
  if (!image) return;
  const data = image.data;
  const rowStride = columns * 4;

  // Scroll: move every row one pixel left. copyWithin is a memmove, so this is one pass
  // over the buffer per frame — cheap enough at 60 Hz for the sizes here.
  for (let row = 0; row < nRegions; row += 1) {
    const start = row * rowStride;
    data.copyWithin(start, start + 4, start + rowStride);
  }

  const x = columns - 1;
  const measured = new Set(frame.regions);

  for (let region = 0; region < nRegions; region += 1) {
    // Row 0 is the top of the image and the axis labels put the highest region there, so
    // the region index is flipped on the way in. Getting this backwards would mirror the
    // whole instrument against its own frequency axis.
    const offset = (nRegions - 1 - region) * rowStride + x * 4;
    if (!frame.available) {
      // Archive gap: a visible hatch, not silence.
      const dark = region % 2 === 0 ? 26 : 14;
      data[offset] = dark;
      data[offset + 1] = dark + 4;
      data[offset + 2] = dark + 8;
      data[offset + 3] = 255;
      continue;
    }

    if (measured.has(region)) {
      const index = frame.regions.indexOf(region);
      const marginDb = frame.measured_db[index] ?? 0;
      const lut = lutOffset(Math.max(0, marginDb) / MARGIN_CEILING_DB);
      data[offset] = SPECTRUM_LUT[lut];
      data[offset + 1] = SPECTRUM_LUT[lut + 1];
      data[offset + 2] = SPECTRUM_LUT[lut + 2];
      data[offset + 3] = 255;
      continue;
    }

    // Not measured this step: show the belief, dimmed, so inference never masquerades
    // as measurement. 0.34 is the largest factor at which the two are still obviously
    // different at a glance on this palette.
    const belief = frame.belief[region] ?? 0;
    const lut = lutOffset(belief * 0.55);
    data[offset] = SPECTRUM_LUT[lut] * 0.34;
    data[offset + 1] = SPECTRUM_LUT[lut + 1] * 0.34;
    data[offset + 2] = SPECTRUM_LUT[lut + 2] * 0.34;
    data[offset + 3] = 255;

    if (showTruth && frame.true_occupied[region]) {
      // A faint red floor under an occupied region the receiver did not look at: the
      // missed-opportunity channel, only shown when truth is explicitly enabled.
      data[offset] = Math.min(255, data[offset] + 46);
      data[offset + 1] = Math.max(0, data[offset + 1] - 6);
      data[offset + 2] = Math.max(0, data[offset + 2] - 6);
    }
  }

  state.lastStep = frame.step;
  state.cursor += 1;
}

function axisLabels(nRegions: number, centreMhz?: number[]) {
  const count = Math.min(8, nRegions);
  const out: { region: number; text: string }[] = [];
  for (let i = 0; i < count; i += 1) {
    // Top row is the highest region index so frequency increases upward, matching the
    // convention every spectrum plot in the docs uses.
    const region = Math.round((nRegions - 1) * (1 - i / Math.max(1, count - 1)));
    const centre = centreMhz?.[region];
    out.push({
      region,
      text: centre === undefined ? `R${region}` : `${centre.toFixed(0)}`,
    });
  }
  return out;
}
