/** The live experiment socket.
 *
 * Why this is a plain class and not a hook: frames arrive at up to 60 Hz, and putting
 * each one into React state would re-render the whole console sixty times a second for
 * numbers the eye cannot read that fast. So the socket writes into a ring buffer that
 * the canvas renderers read directly inside their own `requestAnimationFrame` loop, and
 * React is notified on a slower schedule for the parts that are text.
 *
 * The buffer is bounded at the same 4000 frames the server retains
 * (`MAX_RETAINED_FRAMES`), so a long run cannot grow this tab without limit.
 */

import { streamUrl } from "./client";
import type { ExperimentResult, Frame, SessionSummary, StreamMessage, TimelineEvent } from "./types";

export const RING_CAPACITY = 4000;

export interface StreamState {
  status: "connecting" | "streaming" | "complete" | "failed" | "closed";
  session: SessionSummary | null;
  /** Last frame received, or null before the first one arrives. */
  latest: Frame | null;
  frameCount: number;
  timeline: TimelineEvent[];
  result: ExperimentResult | null;
  error: string | null;
  /** Batch runs report `done`/`total` episodes instead of frames. */
  batch: { done: number; total: number } | null;
}

type Listener = (state: StreamState) => void;

/**
 * A fixed-size circular buffer of frames. `at(-1)` is the newest; negative indices walk
 * backwards, which is what every trailing-window chart here wants.
 */
export class FrameRing {
  private readonly buffer: (Frame | undefined)[];
  private cursor = 0;
  private filled = 0;

  constructor(readonly capacity: number = RING_CAPACITY) {
    this.buffer = new Array<Frame | undefined>(capacity);
  }

  push(frame: Frame): void {
    this.buffer[this.cursor] = frame;
    this.cursor = (this.cursor + 1) % this.capacity;
    this.filled = Math.min(this.filled + 1, this.capacity);
  }

  get size(): number {
    return this.filled;
  }

  /** `at(0)` is the oldest retained frame, `at(-1)` the newest. */
  at(index: number): Frame | undefined {
    if (this.filled === 0) return undefined;
    const resolved = index < 0 ? this.filled + index : index;
    if (resolved < 0 || resolved >= this.filled) return undefined;
    const start = this.filled === this.capacity ? this.cursor : 0;
    return this.buffer[(start + resolved) % this.capacity];
  }

  /** The last `count` frames, oldest first. Allocates — call it from render, not per frame. */
  tail(count: number): Frame[] {
    const take = Math.min(count, this.filled);
    const out: Frame[] = new Array(take);
    for (let i = 0; i < take; i += 1) out[i] = this.at(this.filled - take + i) as Frame;
    return out;
  }

  clear(): void {
    this.buffer.fill(undefined);
    this.cursor = 0;
    this.filled = 0;
  }
}

const EMPTY: StreamState = {
  status: "connecting",
  session: null,
  latest: null,
  frameCount: 0,
  timeline: [],
  result: null,
  error: null,
  batch: null,
};

export interface StreamOptions {
  /** How often React is told about new frames, in ms. The canvas is not throttled. */
  notifyIntervalMs?: number;
  /** Retry once after this delay if the socket closes before the run finished. */
  reconnectDelayMs?: number;
}

export class ExperimentStream {
  readonly frames = new FrameRing();
  private socket: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private state: StreamState = EMPTY;
  private pending = false;
  private timer: number | null = null;
  private reconnects = 0;
  private closedByUs = false;

  constructor(
    readonly experimentId: string,
    private readonly options: StreamOptions = {},
  ) {}

  get snapshot(): StreamState {
    return this.state;
  }

  subscribe(listener: Listener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  open(): void {
    this.closedByUs = false;
    const socket = new WebSocket(streamUrl(this.experimentId));
    this.socket = socket;
    socket.onmessage = (event) => this.ingest(event.data as string);
    socket.onerror = () => this.patch({ error: "socket error" });
    socket.onclose = () => {
      if (this.closedByUs) return;
      const unfinished = this.state.status === "connecting" || this.state.status === "streaming";
      if (unfinished && this.reconnects < 1) {
        // One retry only. A dev-server restart or a proxy hiccup deserves a second
        // chance; a genuinely dead session must not turn into a reconnect loop.
        this.reconnects += 1;
        window.setTimeout(() => this.open(), this.options.reconnectDelayMs ?? 700);
        return;
      }
      this.patch({ status: unfinished ? "closed" : this.state.status });
    };
    // Flush to React on a timer rather than per message.
    this.timer = window.setInterval(() => {
      if (this.pending) {
        this.pending = false;
        this.emit();
      }
    }, this.options.notifyIntervalMs ?? 100);
  }

  close(): void {
    this.closedByUs = true;
    if (this.timer !== null) window.clearInterval(this.timer);
    this.timer = null;
    this.socket?.close();
    this.socket = null;
    this.listeners.clear();
  }

  private ingest(raw: string): void {
    let message: StreamMessage;
    try {
      message = JSON.parse(raw) as StreamMessage;
    } catch {
      return; // A malformed frame is dropped; the run continues.
    }
    switch (message.type) {
      case "frame": {
        this.frames.push(message);
        this.state = {
          ...this.state,
          status: "streaming",
          latest: message,
          frameCount: this.frames.size,
        };
        this.pending = true; // coalesced by the timer
        return;
      }
      case "session":
      case "status": {
        const { type: _type, ...session } = message;
        this.patch({
          session: session as SessionSummary,
          status: session.status === "failed" ? "failed" : this.state.status,
        });
        return;
      }
      case "timeline": {
        const { type: _type, ...event } = message;
        // Newest first: the console reads top-down and the tail is what matters.
        this.patch({ timeline: [event as TimelineEvent, ...this.state.timeline].slice(0, 400) });
        return;
      }
      case "batch_progress": {
        this.patch({ batch: { done: message.done, total: message.total } });
        return;
      }
      case "complete": {
        const { type: _type, result, ...session } = message;
        this.patch({
          status: "complete",
          session: session as SessionSummary,
          result: result as ExperimentResult,
        });
        return;
      }
      case "error": {
        const { type: _type, error, ...session } = message;
        this.patch({
          status: "failed",
          error: error ?? "experiment failed",
          session: (session.experiment_id ? session : this.state.session) as SessionSummary,
        });
        return;
      }
    }
  }

  private patch(partial: Partial<StreamState>): void {
    this.state = { ...this.state, ...partial };
    this.emit();
  }

  private emit(): void {
    for (const listener of this.listeners) listener(this.state);
  }
}
