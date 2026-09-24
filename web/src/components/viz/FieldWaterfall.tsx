/** A scrolling time × region heat of any per-region field.
 *
 * The spectrum waterfall is deliberately its own component: it has to distinguish measured
 * from inferred, and that logic should not be parameterised away. This one is for fields
 * that are *entirely* inferred — the posterior, the uncertainty, the staleness clock — where
 * every cell has the same epistemic status and the only question is how it evolves. Same
 * scroll-one-column-per-frame technique, so the cost per frame is one column of writes.
 *
 * The observed window is marked with a tick on the live edge rather than by recolouring the
 * cell: these fields are what the scheduler *believed*, and painting the measurement into
 * them would blur the distinction the belief map exists to show.
 */

import { useEffect, useRef } from "react";

import type { FrameRing } from "@/api/stream";
import type { Frame } from "@/api/types";
import { useAnimationFrame } from "@/hooks/useExperimentStream";
import { useMeasure } from "@/hooks/useMeasure";
import { cn } from "@/lib/cn";
import { PALETTE, lutOffset } from "@/lib/palette";

interface State {
  image: ImageData | null;
  lastStep: number;
}

export function FieldWaterfall({
  frames,
  nRegions,
  select,
  lut,
  scale,
  markObserved = true,
  columnWidth = 2,
  label,
  className,
}: {
  frames: FrameRing | null;
  nRegions: number;
  select: (frame: Frame) => number[] | null | undefined;
  lut: Uint8ClampedArray;
  /** Map the raw value onto [0, 1]. Identity by default. */
  scale?: (value: number) => number;
  markObserved?: boolean;
  columnWidth?: number;
  label?: string;
  className?: string;
}) {
  const [wrapRef, size] = useMeasure<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<State>({ image: null, lastStep: -1 });
  const selectRef = useRef(select);
  const scaleRef = useRef(scale);
  selectRef.current = select;
  scaleRef.current = scale;

  const columns = Math.max(16, Math.floor(size.width / columnWidth));

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || columns < 16 || nRegions < 1) return;
    const context = canvas.getContext("2d", { alpha: false });
    if (!context) return;
    canvas.width = columns;
    canvas.height = nRegions;
    const image = context.createImageData(columns, nRegions);
    // The floor is the ramp's own zero rather than black: a field reading zero everywhere
    // should look like zero *on this scale*, which is what the legend beside it claims.
    const zero = lutOffset(0);
    for (let i = 0; i < image.data.length; i += 4) {
      image.data[i] = lut[zero];
      image.data[i + 1] = lut[zero + 1];
      image.data[i + 2] = lut[zero + 2];
      image.data[i + 3] = 255;
    }
    stateRef.current = { image, lastStep: -1 };

    // Replay whatever the ring already holds, so switching screens or resizing a panel
    // does not blank a field that has history behind it.
    for (const frame of frames?.tail(columns) ?? []) {
      writeColumn(stateRef.current, frame, nRegions, columns, selectRef.current, lut, scaleRef.current);
    }
    context.putImageData(image, 0, 0);
  }, [columns, nRegions, lut, frames]);

  useAnimationFrame(() => {
    const canvas = canvasRef.current;
    const state = stateRef.current;
    if (!canvas || !state.image || !frames) return;
    const latest = frames.at(-1);
    if (!latest || latest.step === state.lastStep) return;

    const behind = state.lastStep < 0 ? 1 : Math.min(frames.size, latest.step - state.lastStep);
    for (const frame of frames.tail(Math.max(1, behind))) {
      if (frame.step <= state.lastStep) continue;
      writeColumn(state, frame, nRegions, columns, selectRef.current, lut, scaleRef.current);
    }
    canvas.getContext("2d", { alpha: false })?.putImageData(state.image, 0, 0);
  }, Boolean(frames));

  const latest = frames?.at(-1);

  return (
    <div ref={wrapRef} className={cn("relative h-full min-h-16 w-full overflow-hidden bg-void", className)}>
      <canvas
        ref={canvasRef}
        className="absolute inset-0 h-full w-full"
        style={{ imageRendering: "pixelated" }}
        role="img"
        aria-label={label ?? "Per-region field against time"}
      />
      {markObserved && latest && nRegions > 0 && (
        <div className="pointer-events-none absolute inset-y-0 right-0 w-1.5">
          {latest.regions.map((region) => (
            <span
              key={region}
              className="absolute right-0 w-1.5"
              style={{
                // Bottom-anchored because region 0 is the bottom row of the image.
                bottom: `${(region / nRegions) * 100}%`,
                height: `${Math.max(1.2, 100 / nRegions)}%`,
                background: PALETTE.accent,
              }}
            />
          ))}
        </div>
      )}
      <div
        className="pointer-events-none absolute inset-y-0 right-0 w-px"
        style={{ background: PALETTE.accent, opacity: 0.6 }}
      />
      {label && (
        <span className="mono pointer-events-none absolute top-1 left-2 text-[9px] text-faint">
          {label}
        </span>
      )}
    </div>
  );
}

function writeColumn(
  state: State,
  frame: Frame,
  nRegions: number,
  columns: number,
  select: (frame: Frame) => number[] | null | undefined,
  lut: Uint8ClampedArray,
  scale?: (value: number) => number,
): void {
  const image = state.image;
  if (!image) return;
  const data = image.data;
  const rowStride = columns * 4;
  for (let row = 0; row < nRegions; row += 1) {
    const start = row * rowStride;
    data.copyWithin(start, start + 4, start + rowStride);
  }

  const values = select(frame) ?? [];
  const x = columns - 1;
  for (let region = 0; region < nRegions; region += 1) {
    // Flipped so frequency increases upward, as everywhere else in the console.
    const offset = (nRegions - 1 - region) * rowStride + x * 4;
    const raw = values[region] ?? 0;
    const index = lutOffset(scale ? scale(raw) : raw);
    data[offset] = lut[index];
    data[offset + 1] = lut[index + 1];
    data[offset + 2] = lut[index + 2];
    data[offset + 3] = 255;
  }
  state.lastStep = frame.step;
}
