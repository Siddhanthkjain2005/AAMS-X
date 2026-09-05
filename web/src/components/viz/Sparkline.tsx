/** A trailing curve over the frame ring, drawn on canvas inside its own rAF loop.
 *
 * Deliberately not ECharts: these run four-up beside a 60 FPS waterfall and are redrawn
 * from the ring on every animation frame. A charting library would allocate a data array
 * per redraw; this walks the ring in place and strokes one path.
 */

import { useEffect, useRef } from "react";

import type { FrameRing } from "@/api/stream";
import type { Frame } from "@/api/types";
import { useAnimationFrame } from "@/hooks/useExperimentStream";
import { useMeasure } from "@/hooks/useMeasure";
import { cn } from "@/lib/cn";

export interface SparklineProps {
  frames: FrameRing | null;
  /** What to plot. Called once per retained frame per redraw, so keep it arithmetic. */
  value: (frame: Frame) => number;
  colour: string;
  /** Trailing window in frames. */
  window?: number;
  /** Fix the vertical scale instead of auto-ranging — for values that are already [0, 1]. */
  domain?: [number, number];
  /** Shade the area under the curve. Off for a pair drawn in the same panel. */
  fill?: boolean;
  /** Draw a zero line when the range spans it, so a negative excursion is legible. */
  zeroLine?: boolean;
  className?: string;
  height?: number;
}

export function Sparkline({
  frames,
  value,
  colour,
  window = 600,
  domain,
  fill = true,
  zeroLine = false,
  className,
  height = 56,
}: SparklineProps) {
  const [wrapRef, size] = useMeasure<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const valueRef = useRef(value);
  valueRef.current = value;

  const dpr = Math.min(2, window > 0 ? (globalThis.devicePixelRatio ?? 1) : 1);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || size.width < 8) return;
    canvas.width = Math.round(size.width * dpr);
    canvas.height = Math.round(height * dpr);
  }, [size.width, height, dpr]);

  useAnimationFrame(() => {
    const canvas = canvasRef.current;
    if (!canvas || !frames || frames.size === 0 || size.width < 8) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    const width = canvas.width;
    const tall = canvas.height;
    context.clearRect(0, 0, width, tall);

    const count = Math.min(window, frames.size);
    const first = frames.size - count;

    let low = domain ? domain[0] : Number.POSITIVE_INFINITY;
    let high = domain ? domain[1] : Number.NEGATIVE_INFINITY;
    if (!domain) {
      for (let i = 0; i < count; i += 1) {
        const frame = frames.at(first + i);
        if (!frame) continue;
        const v = valueRef.current(frame);
        if (v < low) low = v;
        if (v > high) high = v;
      }
      if (!Number.isFinite(low) || !Number.isFinite(high)) return;
      if (high - low < 1e-9) {
        high += 0.5;
        low -= 0.5;
      } else {
        const pad = (high - low) * 0.08;
        high += pad;
        low -= pad;
      }
    }

    const span = high - low || 1;
    const x = (i: number) => (count === 1 ? width : (i / (count - 1)) * width);
    const y = (v: number) => tall - ((v - low) / span) * tall;

    if (zeroLine && low < 0 && high > 0) {
      context.strokeStyle = "rgb(43 58 74 / 0.9)";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(0, y(0));
      context.lineTo(width, y(0));
      context.stroke();
    }

    context.beginPath();
    for (let i = 0; i < count; i += 1) {
      const frame = frames.at(first + i);
      if (!frame) continue;
      const py = y(valueRef.current(frame));
      if (i === 0) context.moveTo(x(i), py);
      else context.lineTo(x(i), py);
    }

    if (fill) {
      context.save();
      context.lineTo(width, tall);
      context.lineTo(0, tall);
      context.closePath();
      const gradient = context.createLinearGradient(0, 0, 0, tall);
      gradient.addColorStop(0, `${colour}55`);
      gradient.addColorStop(1, `${colour}00`);
      context.fillStyle = gradient;
      context.fill();
      context.restore();
    }

    context.strokeStyle = colour;
    context.lineWidth = 1.6 * dpr;
    context.lineJoin = "round";
    context.stroke();

    // The live head: a dot at the newest sample, so a stalled stream is visibly stalled.
    const last = frames.at(-1);
    if (last) {
      context.fillStyle = colour;
      context.beginPath();
      context.arc(width - 1.5 * dpr, y(valueRef.current(last)), 2.2 * dpr, 0, Math.PI * 2);
      context.fill();
    }
  }, Boolean(frames));

  return (
    <div ref={wrapRef} className={cn("w-full", className)} style={{ height }}>
      <canvas ref={canvasRef} className="h-full w-full" />
    </div>
  );
}
