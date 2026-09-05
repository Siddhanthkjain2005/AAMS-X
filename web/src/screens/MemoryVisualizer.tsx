/** Associative Memory Visualizer — what the system remembers, and what it is recalling now.
 *
 * The memory stores *contexts*, not spectra: each prototype is a standardised feature
 * vector for a band state, carrying the region preference that state implied. Retrieval is
 * a modern-Hopfield read — a softmax over similarity to every stored prototype — so the
 * honest picture of a read is a weight distribution, not a single winner, which is why the
 * retrieval panel lists all of `top_ids` rather than only `prototype_id`.
 *
 * The two data sources on this screen have different lifetimes and are labelled as such.
 * `frame.memory` is live: similarity, the recognised flag and the top-k weights arrive
 * every step. The prototype table lives in `result.context_snapshot.memory`, which the
 * runner writes once, when the episode ends — so during a run the ring is empty and says
 * so, rather than showing a memory that is merely the one from a previous run.
 */

import { BrainCircuit, Database, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { useExperiment } from "@/api/queries";
import { isEpisodeResult, type MemoryPrototype, type MemorySnapshot } from "@/api/types";
import { NoRun } from "@/components/run/NoRun";
import { RunPicker } from "@/components/run/RunPicker";
import { MemoryConstellation } from "@/components/viz/MemoryConstellation";
import { RampLegend } from "@/components/viz/RampLegend";
import { Sparkline } from "@/components/viz/Sparkline";
import { Badge, EmptyState, Panel, Stat, Tabs } from "@/components/ui";
import { useAnimationFrame } from "@/hooks/useExperimentStream";
import { useMeasure } from "@/hooks/useMeasure";
import { int, num, pct } from "@/lib/format";
import { MEMORY_LUT, PALETTE, lutOffset } from "@/lib/palette";
import { useActiveFrame, useLive } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

export default function MemoryVisualizer() {
  const { state, frames } = useLive();
  const frame = useActiveFrame();
  const experimentId = useSession((session) => session.experimentId);
  const stored = useExperiment(experimentId, { staleTime: 15_000 });
  const [view, setView] = useState<"constellation" | "matrix">("constellation");
  const [selected, setSelected] = useState<number | null>(null);

  // The snapshot can arrive over the socket (on completion) or from the stored record.
  const liveResult = isEpisodeResult(state.result) ? state.result : null;
  const storedResult = isEpisodeResult(stored.data?.result ?? null)
    ? (stored.data?.result as NonNullable<typeof liveResult>)
    : null;
  const snapshot: MemorySnapshot | null =
    liveResult?.context_snapshot.memory ?? storedResult?.context_snapshot.memory ?? null;
  const prototypes = snapshot?.prototypes ?? [];
  const readout = frame?.memory ?? null;
  const nRegions = prototypes[0]?.preference.length ?? frame?.belief.length ?? 32;

  if (!experimentId) {
    return (
      <div className="p-4">
        <Panel className="min-h-96">
          <NoRun what="memory" />
        </Panel>
      </div>
    );
  }

  const occupancy = snapshot && snapshot.capacity > 0 ? snapshot.size / snapshot.capacity : 0;

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <Panel flush className="shrink-0">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-4 xl:grid-cols-7">
          <Stat
            label="Recall similarity"
            value={readout ? num(readout.similarity, 3) : "—"}
            hint={readout?.recognised ? "above the recognition threshold" : "no context recognised"}
            tone={readout?.recognised ? "mag" : "ink"}
          />
          <Stat
            label="Context matched"
            value={readout?.recognised && readout.prototype_id !== null ? `#${readout.prototype_id}` : "—"}
            hint={readout?.recognised ? readout.label || "unlabelled prototype" : "the memory term is gated off"}
            tone={readout?.recognised ? "accent" : "ink"}
          />
          <Stat
            label="Prototypes held"
            value={snapshot ? `${int(snapshot.size)} / ${int(snapshot.capacity)}` : "—"}
            hint={snapshot ? `${pct(occupancy, 0)} of a bounded store` : "written when the run ends"}
            tone={occupancy > 0.9 ? "warn" : "signal"}
          />
          <Stat
            label="Writes"
            value={snapshot ? int(snapshot.writes) : "—"}
            hint={snapshot ? `${int(snapshot.creations)} new contexts` : undefined}
            tone="ink"
          />
          <Stat
            label="Evictions"
            value={snapshot ? int(snapshot.evictions) : "—"}
            hint="lowest-utility prototype dropped when full"
            tone={snapshot && snapshot.evictions > 0 ? "warn" : "ink"}
          />
          <Stat
            label="Recognitions"
            value={snapshot ? int(snapshot.recognitions) : "—"}
            hint={
              snapshot && frame
                ? `${pct(frame.step > 0 ? snapshot.recognitions / frame.step : 0, 0)} of steps`
                : undefined
            }
            tone="mag"
          />
          <Stat
            label="Age of match"
            value={readout && readout.recognised ? int(readout.age) : "—"}
            hint={readout?.recognised ? `${int(readout.visits)} visits · utility ${num(readout.utility, 2)}` : undefined}
            tone="ink"
          />
        </div>
      </Panel>

      <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_340px]">
        <div className="flex min-h-0 flex-col gap-3">
          <Panel
            flush
            title="Stored contexts"
            subtitle={
              snapshot
                ? `${int(prototypes.length)} prototypes · bounded at ${int(snapshot.capacity)} · recorded when the episode ended`
                : "the prototype store is written once, at the end of the run"
            }
            actions={
              <>
                {view === "matrix" && (
                  <RampLegend lut={MEMORY_LUT} min={0} max={1} label="preference" className="w-28" />
                )}
                <Tabs
                  value={view}
                  onChange={setView}
                  tabs={[
                    { value: "constellation", label: "Constellation" },
                    { value: "matrix", label: "Matrix", count: prototypes.length },
                  ]}
                />
              </>
            }
            className="min-h-80 flex-1"
          >
            {prototypes.length === 0 ? (
              <EmptyState
                title="No prototype store yet"
                detail="Similarity, the recognised flag and the retrieval weights are live in the panels around this one. The prototype table itself is part of the end-of-run context snapshot, so it appears when the episode finishes — a store from an earlier run would not describe this one."
                icon={<Database className="size-5 text-faint" />}
              />
            ) : view === "constellation" ? (
              <MemoryConstellation
                prototypes={prototypes}
                readout={readout}
                step={frame?.step ?? 0}
                selected={selected}
                onSelect={(id) => setSelected((prior) => (prior === id ? null : id))}
              />
            ) : (
              <PreferenceMatrix
                prototypes={prototypes}
                nRegions={nRegions}
                highlight={readout?.prototype_id ?? null}
                selected={selected}
                onSelect={(id) => setSelected((prior) => (prior === id ? null : id))}
              />
            )}
          </Panel>

          <div className="grid shrink-0 grid-cols-1 gap-3 md:grid-cols-2">
            <Panel
              flush
              title="Recall similarity over time"
              subtitle="the read's confidence, step by step"
            >
              <Sparkline
                frames={frames}
                value={(f) => f.memory.similarity}
                colour={PALETTE.mag}
                domain={[0, 1]}
                height={72}
              />
            </Panel>
            <Panel
              flush
              title="Recognition raster"
              subtitle="one column per step · lit where the memory term was live"
            >
              <RecognitionRaster frames={frames} frame={frame ?? null} />
            </Panel>
          </div>
        </div>

        <div className="flex min-h-0 flex-col gap-3">
          <Panel title="Run" subtitle="live or finished">
            <RunPicker />
          </Panel>

          <Panel
            title="This step's retrieval"
            subtitle="softmax over similarity to every stored context"
            className="min-h-0"
          >
            {readout && readout.top_ids.length > 0 ? (
              <div className="flex flex-col gap-1.5">
                {readout.top_ids.map((id, index) => {
                  const weight = readout.top_weights[index] ?? 0;
                  const isTop = id === readout.prototype_id;
                  return (
                    <button
                      key={id}
                      type="button"
                      onClick={() => setSelected((prior) => (prior === id ? null : id))}
                      className="group flex items-center gap-2 text-left"
                    >
                      <span className="mono w-10 shrink-0 text-[10.5px] text-muted">#{id}</span>
                      <span className="relative h-3.5 min-w-0 flex-1 overflow-hidden rounded bg-void">
                        <span
                          className="absolute inset-y-0 left-0 rounded transition-[width] duration-200"
                          style={{
                            width: `${Math.max(1, weight * 100)}%`,
                            background: isTop ? PALETTE.mag : `${PALETTE.mag}66`,
                          }}
                        />
                      </span>
                      <span className="mono w-12 shrink-0 text-right text-[10px] text-ink-dim">
                        {num(weight, 3)}
                      </span>
                    </button>
                  );
                })}
                <p className="mt-1 text-[10px] leading-relaxed text-faint">
                  Weights sum to one across the top-k the server returned. Recall is gated: below
                  the recognition threshold the memory term contributes nothing to the decision,
                  even when a prototype is nominally nearest.
                </p>
              </div>
            ) : (
              <EmptyState
                title="No read to show"
                detail="The retrieval distribution appears with the first frame that queries the memory."
                icon={<Sparkles className="size-5 text-faint" />}
              />
            )}
          </Panel>

          <Panel
            title={selected === null ? "Prototype detail" : `Prototype #${selected}`}
            subtitle={selected === null ? "click a node or a bar" : "region preference this context implies"}
            className="min-h-0 flex-1"
          >
            <PrototypeDetail
              prototype={prototypes.find((entry) => entry.id === selected) ?? null}
              prototypes={prototypes}
              onSelect={setSelected}
              step={frame?.step ?? 0}
            />
          </Panel>
        </div>
      </div>

      {snapshot && (
        <p className="mono shrink-0 px-1 text-[10px] leading-relaxed text-faint">
          <BrainCircuit className="mr-1 inline size-3" />
          {int(snapshot.standardiser_samples)} samples in the feature standardiser ·{" "}
          {int(snapshot.creations)} contexts created, {int(snapshot.evictions)} evicted, store
          bounded at {int(snapshot.capacity)} · the memory holds context features and region
          preferences, never the sealed occupancy truth
        </p>
      )}
    </div>
  );
}

/** Prototypes × regions, as a heat grid. One canvas: the store can hold dozens of rows. */
function PreferenceMatrix({
  prototypes,
  nRegions,
  highlight,
  selected,
  onSelect,
}: {
  prototypes: MemoryPrototype[];
  nRegions: number;
  highlight: number | null;
  selected: number | null;
  onSelect: (id: number) => void;
}) {
  const [wrapRef, size] = useMeasure<HTMLDivElement>();
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || size.width < 8 || !prototypes.length) return;

    canvas.width = nRegions;
    canvas.height = prototypes.length;
    const image = context.createImageData(nRegions, prototypes.length);
    prototypes.forEach((prototype, row) => {
      // Each prototype's preference is normalised against its own maximum: the interesting
      // quantity is *where in the band* this context expects activity, not how confident
      // the vector is overall, and a shared scale would wash out the flatter contexts.
      const peak = Math.max(...prototype.preference, 1e-6);
      for (let region = 0; region < nRegions; region += 1) {
        const t = Math.max(0, Math.min(1, (prototype.preference[region] ?? 0) / peak));
        const offset = lutOffset(t);
        const pixel = (row * nRegions + region) * 4;
        image.data[pixel] = MEMORY_LUT[offset];
        image.data[pixel + 1] = MEMORY_LUT[offset + 1];
        image.data[pixel + 2] = MEMORY_LUT[offset + 2];
        image.data[pixel + 3] = 255;
      }
    });
    context.putImageData(image, 0, 0);
  }, [prototypes, nRegions, size.width]);

  return (
    <div ref={wrapRef} className="flex h-full min-h-0 gap-2 px-1 pb-1">
      <div className="flex w-24 shrink-0 flex-col">
        {prototypes.map((prototype) => (
          <button
            key={prototype.id}
            type="button"
            onClick={() => onSelect(prototype.id)}
            className="mono flex min-h-0 flex-1 items-center gap-1 truncate px-1 text-left text-[9px] transition-colors"
            style={{
              color:
                prototype.id === highlight
                  ? PALETTE.mag
                  : prototype.id === selected
                    ? PALETTE.ink
                    : PALETTE.faint,
            }}
          >
            #{prototype.id} {prototype.label}
          </button>
        ))}
      </div>
      <canvas
        ref={canvasRef}
        className="h-full min-h-0 w-full flex-1 rounded"
        style={{ imageRendering: "pixelated" }}
      />
    </div>
  );
}

/** One column per retained step: lit where the read was recognised, dark where it was not. */
function RecognitionRaster({
  frames,
  frame,
}: {
  frames: ReturnType<typeof useLive>["frames"];
  frame: ReturnType<typeof useActiveFrame>;
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [wrapRef, size] = useMeasure<HTMLDivElement>();

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || size.width < 8) return;
    canvas.width = Math.max(1, Math.round(size.width));
    canvas.height = 72;
  }, [size.width]);

  useAnimationFrame(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context || !frames || frames.size === 0) return;
    const width = canvas.width;
    const height = canvas.height;
    context.clearRect(0, 0, width, height);

    const count = Math.min(width, frames.size);
    const first = frames.size - count;
    const columnWidth = width / count;
    for (let i = 0; i < count; i += 1) {
      const entry = frames.at(first + i);
      if (!entry) continue;
      const similarity = Math.max(0, Math.min(1, entry.memory.similarity));
      const barHeight = Math.max(1, similarity * height);
      const offset = lutOffset(entry.memory.recognised ? 0.35 + 0.65 * similarity : 0.12);
      context.fillStyle = entry.memory.recognised
        ? `rgb(${MEMORY_LUT[offset]} ${MEMORY_LUT[offset + 1]} ${MEMORY_LUT[offset + 2]})`
        : "rgb(32 42 54)";
      context.fillRect(i * columnWidth, height - barHeight, Math.max(1, columnWidth), barHeight);
    }
  }, Boolean(frames));

  return (
    <div ref={wrapRef} className="w-full" style={{ height: 72 }}>
      <canvas ref={canvasRef} className="h-full w-full" />
      <span className="mono sr-only">
        {frame?.memory.recognised ? "recognised" : "not recognised"} at step {frame?.step ?? 0}
      </span>
    </div>
  );
}

function PrototypeDetail({
  prototype,
  prototypes,
  onSelect,
  step,
}: {
  prototype: MemoryPrototype | null;
  prototypes: MemoryPrototype[];
  onSelect: (id: number) => void;
  step: number;
}) {
  if (!prototype) {
    if (!prototypes.length) {
      return (
        <p className="text-[11px] leading-relaxed text-faint">
          Nothing to inspect until the run's context snapshot exists.
        </p>
      );
    }
    return (
      <div className="flex flex-col gap-1">
        {prototypes.slice(0, 14).map((entry) => (
          <button
            key={entry.id}
            type="button"
            onClick={() => onSelect(entry.id)}
            className="mono flex items-center justify-between gap-2 rounded border border-line bg-void px-2 py-1 text-[10px] text-muted transition-colors hover:border-line-bright hover:text-ink"
          >
            <span className="truncate">
              #{entry.id} {entry.label}
            </span>
            <span className="shrink-0 text-faint">
              {int(entry.visits)} visits · u {num(entry.utility, 2)}
            </span>
          </button>
        ))}
        {prototypes.length > 14 && (
          <p className="mono text-[9px] text-faint">
            +{prototypes.length - 14} more in the matrix view
          </p>
        )}
      </div>
    );
  }

  const peak = Math.max(...prototype.preference, 1e-6);
  const lifespan = Math.max(1, prototype.last_step - prototype.created_step);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <Badge tone="mag">{prototype.label || "unlabelled"}</Badge>
        <Badge tone="neutral">utility {num(prototype.utility, 3)}</Badge>
        <Badge tone="neutral">{int(prototype.visits)} visits</Badge>
      </div>

      <div className="flex flex-col gap-1">
        <span className="eyebrow">Region preference</span>
        <div className="flex h-16 items-end gap-px">
          {prototype.preference.map((value, region) => {
            const t = Math.max(0, Math.min(1, value / peak));
            const offset = lutOffset(t);
            return (
              <span
                key={region}
                title={`R${String(region).padStart(2, "0")} · ${num(value, 4)}`}
                className="min-w-0 flex-1 rounded-t"
                style={{
                  height: `${Math.max(2, t * 100)}%`,
                  background: `rgb(${MEMORY_LUT[offset]} ${MEMORY_LUT[offset + 1]} ${MEMORY_LUT[offset + 2]})`,
                }}
              />
            );
          })}
        </div>
        <p className="mono text-[9px] text-faint">
          normalised against this prototype's own peak · this is the prior the memory term
          contributes, not a measurement
        </p>
      </div>

      <div className="mono flex flex-col gap-1 border-t border-line pt-2 text-[10px] text-muted">
        <div className="flex justify-between">
          <span className="text-faint">created</span>
          <span>step {int(prototype.created_step)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-faint">last used</span>
          <span>
            step {int(prototype.last_step)}
            {step > prototype.last_step && (
              <span className="ml-1 text-faint">({int(step - prototype.last_step)} ago)</span>
            )}
          </span>
        </div>
        <div className="flex justify-between">
          <span className="text-faint">visits per step alive</span>
          <span>{num(prototype.visits / lifespan, 3)}</span>
        </div>
      </div>
    </div>
  );
}
