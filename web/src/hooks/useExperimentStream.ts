/** React binding for `ExperimentStream`.
 *
 * Returns two different things on purpose. `state` is throttled and safe to render: it
 * changes about ten times a second. `frames` is the live ring buffer and is *not* React
 * state — canvas components read it inside their own animation loop, so the waterfall
 * runs at the display's refresh rate while the numbers above it update at a rate a
 * person can actually read.
 */

import { useEffect, useRef, useState } from "react";

import { ExperimentStream, type FrameRing, type StreamState } from "@/api/stream";

export interface LiveStream {
  state: StreamState;
  frames: FrameRing | null;
  stream: ExperimentStream | null;
}

export function useExperimentStream(experimentId: string | null): LiveStream {
  const [stream, setStream] = useState<ExperimentStream | null>(null);
  const [state, setState] = useState<StreamState>(() => IDLE);

  useEffect(() => {
    if (!experimentId) {
      setStream(null);
      setState(IDLE);
      return;
    }
    const next = new ExperimentStream(experimentId);
    const unsubscribe = next.subscribe(setState);
    next.open();
    setStream(next);
    return () => {
      unsubscribe();
      next.close();
      setStream(null);
    };
  }, [experimentId]);

  return { state, frames: stream?.frames ?? null, stream };
}

const IDLE: StreamState = {
  status: "closed",
  session: null,
  latest: null,
  frameCount: 0,
  timeline: [],
  result: null,
  error: null,
  batch: null,
};

/**
 * Run `callback` on every animation frame while `active`. Used by every canvas in the
 * app: one rAF loop per visual, started and stopped with the component, and the callback
 * gets the frame delta so motion is time-based rather than tick-based.
 */
export function useAnimationFrame(
  callback: (deltaMs: number, elapsedMs: number) => void,
  active = true,
): void {
  const stored = useRef(callback);
  stored.current = callback;

  useEffect(() => {
    if (!active) return;
    let raf = 0;
    let previous = performance.now();
    const started = previous;
    const tick = (now: number) => {
      stored.current(now - previous, now - started);
      previous = now;
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [active]);
}
