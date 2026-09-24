/** Per-region bars: belief, uncertainty, staleness, or any other per-region vector.
 *
 * One canvas, one rAF loop, and the vector is read straight from the frame — so this can
 * sit beside the waterfall without adding a React render per frame. The observed window
 * for the current step is outlined rather than recoloured, because the bar's colour is
 * already carrying the quantity and a second encoding on the same channel would be a lie.
 */

import { useEffect, useRef } from "react";

import type { Frame } from "@/api/types";
import type { FrameRing } from "@/api/stream";
import { useAnimationFrame } from "@/hooks/useExperimentStream";
import { useMeasure } from "@/hooks/useMeasure";
import { cn } from "@/lib/cn";
import { PALETTE, lutOffset } from "@/lib/palette";

export interface RegionBarsProps {
  frames: FrameRing | null;
  /** Frozen frame to draw instead of the live edge — the scrub cursor. */
  frame?: Frame | null;
  select: (frame: Frame) => number[] | null | undefined;
  lut: Uint8ClampedArray;
  /** Normalise the value before indexing the LUT. Defaults to identity on [0, 1]. */
  scale?: (value: number) => number;
  /** Outline the regions measured at this step. */
  highlightObserved?: boolean;
  /** Mark truly occupied regions with a hairline — evaluation view only. */
  showTruth?: boolean;
  className?: string;
  height?: number;
  horizontal?: boolean;
}

export function RegionBars({
  frames,
  frame,
  select,
  lut,
  scale,
  highlightObserved = true,
  showTruth = false,
  className,
  height = 92,
  horizontal = false,
}: RegionBarsProps) {
  const [wrapRef, size] = useMeasure<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const selectRef = useRef(select);
  selectRef.current = select;
  const scaleRef = useRef(scale);
  scaleRef.current = scale;

  const dpr = Math.min(2, globalThis.devicePixelRatio ?? 1);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || size.width < 8) return;
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round((horizontal ? size.height || height : height) * dpr);
  }, [size.width, size.height, height, dpr, horizontal]);

  useAnimationFrame(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const source = frame ?? frames?.at(-1) ?? null;
    if (!source) return;
    const values = selectRef.current(source);
    if (!values || !values.length) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const width = canvas.width;
    const tall = canvas.height;
    context.clearRect(0, 0, width, tall);

    const n = values.length;
    const observed = new Set(source.regions);
    const normalise = scaleRef.current ?? ((value: number) => value);

    if (horizontal) {
      const rowHeight = tall / n;
      for (let i = 0; i < n; i += 1) {
        const t = normalise(values[i] ?? 0);
        const offset = lutOffset(t);
        const y = tall - (i + 1) * rowHeight;
        context.fillStyle = `rgb(${lut[offset]} ${lut[offset + 1]} ${lut[offset + 2]})`;
        context.fillRect(0, y + rowHeight * 0.12, Math.max(1, t * width), rowHeight * 0.76);
        if (highlightObserved && observed.has(i)) {
          context.strokeStyle = PALETTE.accent;
          context.lineWidth = dpr;
          context.strokeRect(0.5 * dpr, y + rowHeight * 0.12, width - dpr, rowHeight * 0.76);
        }
      }
      return;
    }

    const columnWidth = width / n;
    for (let i = 0; i < n; i += 1) {
      const t = normalise(values[i] ?? 0);
      const offset = lutOffset(t);
      const barHeight = Math.max(1, t * (tall - 2 * dpr));
      const x = i * columnWidth;
      context.fillStyle = `rgb(${lut[offset]} ${lut[offset + 1]} ${lut[offset + 2]})`;
      context.fillRect(x + columnWidth * 0.1, tall - barHeight, columnWidth * 0.8, barHeight);

      if (showTruth && source.true_occupied[i]) {
        context.fillStyle = PALETTE.bad;
        context.fillRect(x + columnWidth * 0.1, tall - 1.5 * dpr, columnWidth * 0.8, 1.5 * dpr);
      }
      if (highlightObserved && observed.has(i)) {
        context.strokeStyle = PALETTE.accent;
        context.lineWidth = dpr;
        context.beginPath();
        context.moveTo(x + columnWidth * 0.1, tall - barHeight - 2 * dpr);
        context.lineTo(x + columnWidth * 0.9, tall - barHeight - 2 * dpr);
        context.stroke();
      }
    }
  }, Boolean(frames) || Boolean(frame));

  return (
    <div
      ref={wrapRef}
      className={cn("w-full", className)}
      style={horizontal ? undefined : { height }}
    >
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}
