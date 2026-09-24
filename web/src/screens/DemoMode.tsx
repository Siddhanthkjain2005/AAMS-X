/** Full-screen presentation mode.
 *
 * This view is a lens over the same websocket, frame ring and stored result used by the
 * research console. It never creates demo-only samples: before a run exists it offers the
 * real launcher, while memory prototypes stay absent until the episode writes its final
 * snapshot. Arrow keys move between three evidence views; F toggles the browser's native
 * full-screen mode and Escape always provides a route back to the console.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  BrainCircuit,
  ChevronLeft,
  ChevronRight,
  Crosshair,
  Expand,
  Home,
  Info,
  Keyboard,
  Layers3,
  Minimize2,
  Play,
  Radio,
  ShieldCheck,
  Sparkles,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { Link, useNavigate } from "react-router-dom";

import { useExperiment, useScenario } from "@/api/queries";
import { isEpisodeResult, type Frame, type MemorySnapshot } from "@/api/types";
import { LaunchPanel } from "@/components/run/LaunchPanel";
import { FactorBars, contributionTotal } from "@/components/viz/FactorBars";
import { MemoryConstellation } from "@/components/viz/MemoryConstellation";
import { RampLegend } from "@/components/viz/RampLegend";
import { RegionBars } from "@/components/viz/RegionBars";
import { Sparkline } from "@/components/viz/Sparkline";
import { Surface3D } from "@/components/viz/Surface3D";
import { Waterfall } from "@/components/viz/Waterfall";
import {
  Badge,
  Button,
  EmptyState,
  LiveDot,
  Panel,
  ProgressBar,
  Stat,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { int, num, pct, policyLabel, regionLabel, signed } from "@/lib/format";
import {
  BELIEF_LUT,
  MEMORY_LUT,
  PALETTE,
  SPECTRUM_LUT,
  UNCERTAINTY_LUT,
} from "@/lib/palette";
import { useLive } from "@/state/LiveProvider";
import { useSession } from "@/state/session";

type SceneId = "signal" | "decision" | "memory";

const SCENES: {
  id: SceneId;
  label: string;
  kicker: string;
  icon: typeof Radio;
}[] = [
  { id: "signal", label: "Sense", kicker: "measured spectrum", icon: Radio },
  {
    id: "decision",
    label: "Decide",
    kicker: "eight visible terms",
    icon: Crosshair,
  },
  {
    id: "memory",
    label: "Remember",
    kicker: "context retrieval",
    icon: BrainCircuit,
  },
];

export default function DemoMode() {
  const navigate = useNavigate();
  const { state, frames } = useLive();
  const experimentId = useSession((session) => session.experimentId);
  const stored = useExperiment(experimentId, { staleTime: 10_000 });
  const scenarioId = state.session?.scenario_id ?? null;
  const scenario = useScenario(scenarioId);
  const frame = state.latest;

  const [scene, setScene] = useState<SceneId>("signal");
  const [help, setHelp] = useState(false);
  const [fullscreen, setFullscreen] = useState(
    Boolean(document.fullscreenElement),
  );

  const result = useMemo(() => {
    if (isEpisodeResult(state.result)) return state.result;
    const archived = stored.data?.result ?? null;
    return isEpisodeResult(archived) ? archived : null;
  }, [state.result, stored.data?.result]);
  const memory: MemorySnapshot | null = result?.context_snapshot.memory ?? null;
  const nRegions = scenario.data?.n_regions ?? frame?.belief.length ?? 32;
  const centres = scenario.data?.segments_measured?.[0]?.grid?.centre_mhz;
  const sceneIndex = SCENES.findIndex((entry) => entry.id === scene);

  const changeScene = useCallback((delta: number) => {
    setScene((current) => {
      const index = SCENES.findIndex((entry) => entry.id === current);
      return SCENES[(index + delta + SCENES.length) % SCENES.length].id;
    });
  }, []);

  const toggleFullscreen = useCallback(async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await document.documentElement.requestFullscreen();
    } catch {
      // Browsers can deny full-screen outside a user gesture; the button remains usable.
    }
  }, []);

  useEffect(() => {
    const sync = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (target?.matches("input, textarea, select, button")) return;
      if (event.key === "ArrowRight" || event.key === "PageDown")
        changeScene(1);
      else if (event.key === "ArrowLeft" || event.key === "PageUp")
        changeScene(-1);
      else if (event.key === "1" || event.key === "2" || event.key === "3") {
        setScene(SCENES[Number(event.key) - 1].id);
      } else if (event.key.toLowerCase() === "h" || event.key === "?")
        setHelp((open) => !open);
      else if (event.key.toLowerCase() === "f") void toggleFullscreen();
      else if (event.key === "Escape") {
        if (help) setHelp(false);
        else if (!document.fullscreenElement) navigate("/");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [changeScene, help, navigate, toggleFullscreen]);

  return (
    <div className="relative flex h-screen min-h-[680px] flex-col overflow-hidden bg-void/35 p-3 text-ink sm:p-4">
      <PresentationHeader
        state={state.status}
        experimentId={experimentId}
        label={state.session?.label ?? stored.data?.scheduler ?? null}
        scenario={scenario.data?.name ?? state.session?.scenario_id ?? null}
        progress={frame?.progress ?? state.session?.progress ?? 0}
        scene={scene}
        fullscreen={fullscreen}
        onScene={setScene}
        onHelp={() => setHelp(true)}
        onFullscreen={() => void toggleFullscreen()}
      />

      {experimentId && frame ? (
        <>
          <KpiRail frame={frame} status={state.status} />
          <main className="min-h-0 flex-1 py-3">
            <AnimatePresence mode="wait" initial={false} custom={sceneIndex}>
              <motion.div
                key={scene}
                custom={sceneIndex}
                variants={SCENE_MOTION}
                initial="enter"
                animate="centre"
                exit="exit"
                transition={{ duration: 0.42, ease: [0.22, 1, 0.36, 1] }}
                className="h-full"
              >
                {scene === "signal" ? (
                  <SignalScene
                    frame={frame}
                    frames={frames}
                    nRegions={nRegions}
                    centres={centres}
                  />
                ) : scene === "decision" ? (
                  <DecisionScene
                    frame={frame}
                    frames={frames}
                    nRegions={nRegions}
                    centres={centres}
                  />
                ) : (
                  <MemoryScene frame={frame} frames={frames} memory={memory} />
                )}
              </motion.div>
            </AnimatePresence>
          </main>
          <PresentationFooter
            sceneIndex={sceneIndex}
            frame={frame}
            event={state.timeline[0]?.message ?? null}
            onPrevious={() => changeScene(-1)}
            onNext={() => changeScene(1)}
          />
        </>
      ) : (
        <DemoEmpty connecting={Boolean(experimentId)} label={state.error} />
      )}

      <AnimatePresence>
        {help && <HelpOverlay onClose={() => setHelp(false)} />}
      </AnimatePresence>
    </div>
  );
}

const SCENE_MOTION = {
  enter: { opacity: 0, x: 36, scale: 0.985 },
  centre: { opacity: 1, x: 0, scale: 1 },
  exit: { opacity: 0, x: -24, scale: 0.99 },
};

function PresentationHeader({
  state,
  experimentId,
  label,
  scenario,
  progress,
  scene,
  fullscreen,
  onScene,
  onHelp,
  onFullscreen,
}: {
  state: string;
  experimentId: string | null;
  label: string | null;
  scenario: string | null;
  progress: number;
  scene: SceneId;
  fullscreen: boolean;
  onScene: (scene: SceneId) => void;
  onHelp: () => void;
  onFullscreen: () => void;
}) {
  const tone =
    state === "streaming"
      ? "accent"
      : state === "complete"
        ? "good"
        : state === "failed"
          ? "bad"
          : "neutral";
  return (
    <header className="panel lit relative z-20 flex shrink-0 items-center gap-4 overflow-hidden px-4 py-3">
      <div className="absolute inset-x-0 bottom-0">
        <ProgressBar value={progress} showSweep={state === "streaming"} />
      </div>
      <Link to="/" className="group flex shrink-0 items-center gap-3">
        <span className="relative grid size-10 place-items-center rounded-lg border border-accent/40 bg-accent/10 text-accent">
          <Activity className="size-5" />
          <span className="absolute inset-0 animate-pulse-ring rounded-lg" />
        </span>
        <span>
          <span className="block text-[17px] font-bold tracking-[0.18em] text-ink">
            AAMS-X
          </span>
          <span className="eyebrow block text-[9px]">
            adaptive sensing laboratory
          </span>
        </span>
      </Link>

      <div className="hidden h-9 w-px bg-line lg:block" />
      <div className="hidden min-w-0 flex-1 lg:block">
        <p className="truncate text-xs font-semibold text-ink-dim">
          {scenario ?? "No scenario loaded"}
        </p>
        <p className="mono mt-0.5 truncate text-[9px] text-faint">
          {label ? policyLabel(label) : "waiting for an execution"}
          {experimentId ? ` · ${experimentId}` : " · measured recordings only"}
        </p>
      </div>

      <nav className="ml-auto flex items-center rounded-lg border border-line bg-void/60 p-1">
        {SCENES.map((entry, index) => {
          const Icon = entry.icon;
          const active = entry.id === scene;
          return (
            <button
              key={entry.id}
              type="button"
              onClick={() => onScene(entry.id)}
              className={cn(
                "relative flex min-w-[88px] items-center gap-2 rounded-md px-3 py-2 text-left transition-colors",
                active
                  ? "text-accent"
                  : "text-muted hover:bg-panel-2 hover:text-ink-dim",
              )}
            >
              {active && (
                <motion.span
                  layoutId="demo-tab"
                  className="absolute inset-0 rounded-md border border-accent/30 bg-accent/10"
                />
              )}
              <Icon className="relative size-3.5 shrink-0" />
              <span className="relative hidden xl:block">
                <span className="block text-[11px] font-semibold">
                  {index + 1}. {entry.label}
                </span>
                <span className="block text-[8px] text-faint">
                  {entry.kicker}
                </span>
              </span>
            </button>
          );
        })}
      </nav>

      <Badge tone={tone} className="hidden shrink-0 md:inline-flex">
        <LiveDot active={state === "streaming"} tone={tone} />
        {state}
      </Badge>
      <button
        type="button"
        onClick={onHelp}
        className="rounded-md border border-line p-2 text-muted transition-colors hover:bg-panel-2 hover:text-ink"
        aria-label="Demo keyboard help"
      >
        <Keyboard className="size-4" />
      </button>
      <button
        type="button"
        onClick={onFullscreen}
        className="rounded-md border border-line p-2 text-muted transition-colors hover:bg-panel-2 hover:text-ink"
        aria-label={fullscreen ? "Exit full screen" : "Enter full screen"}
      >
        {fullscreen ? (
          <Minimize2 className="size-4" />
        ) : (
          <Expand className="size-4" />
        )}
      </button>
      <Link
        to="/"
        className="rounded-md border border-line p-2 text-muted transition-colors hover:bg-panel-2 hover:text-ink"
        aria-label="Return to Command Center"
      >
        <X className="size-4" />
      </Link>
    </header>
  );
}

function KpiRail({ frame, status }: { frame: Frame; status: string }) {
  const flags = frame.hits + frame.false_alarms;
  return (
    <Panel flush className="mt-3 shrink-0">
      <div className="grid grid-cols-4 gap-x-5 gap-y-3 px-4 py-3 md:grid-cols-8">
        <Stat
          label="Step"
          value={int(frame.step)}
          hint={`${pct(frame.progress, 0)} complete`}
          tone="ink"
        />
        <Stat
          label="Window"
          value={`${frame.regions[0]}–${frame.regions.at(-1)}`}
          hint={`${frame.regions.length} regions observed`}
          tone="signal"
        />
        <Stat
          label="Hits now"
          value={int(frame.hits)}
          hint={`of ${int(frame.oracle_best)} oracle ceiling`}
          tone="good"
        />
        <Stat
          label="False alarms"
          value={int(frame.false_alarms)}
          hint={`${int(flags)} flags raised`}
          tone={frame.false_alarms > frame.hits ? "bad" : "ink"}
        />
        <Stat
          label="Reward"
          value={num(frame.cumulative_reward, 1)}
          hint="cumulative objective"
          tone="accent"
        />
        <Stat
          label="Regret"
          value={num(frame.cumulative_regret, 1)}
          hint="against sealed oracle"
          tone="warn"
        />
        <Stat
          label="Budget left"
          value={num(frame.budget_remaining, 0)}
          hint="Σ cost ≤ B"
          tone={frame.budget_remaining <= 0 ? "bad" : "signal"}
        />
        <Stat
          label="Stream"
          value={status === "streaming" ? "LIVE" : status.toUpperCase()}
          hint={`archive ${archiveClock(frame.t_sec)} UTC`}
          tone={status === "streaming" ? "good" : "ink"}
        />
      </div>
    </Panel>
  );
}

function SignalScene({
  frame,
  frames,
  nRegions,
  centres,
}: LiveSceneProps & { nRegions: number; centres?: number[] }) {
  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-[minmax(0,1.28fr)_minmax(360px,0.72fr)]">
      <Panel
        flush
        title="Measured spectrum as terrain"
        subtitle="height = margin above threshold · inferred plateaus remain visibly lower"
        actions={
          <Badge tone={frame.available ? "accent" : "warn"}>
            {frame.available ? "archive sample" : "archive gap"}
          </Badge>
        }
      >
        <Surface3D frames={frames} nRegions={nRegions} depth={88} />
      </Panel>
      <div className="flex min-h-0 flex-col gap-3">
        <Panel
          flush
          title="Live spectrum intelligence"
          subtitle="frequency ↑ · time → · measured cells bright, belief dim"
          actions={
            <RampLegend
              lut={SPECTRUM_LUT}
              min={0}
              max={14}
              unit="dB"
              label="margin"
              className="w-32"
            />
          }
          className="min-h-[260px] flex-1"
        >
          <Waterfall
            frames={frames}
            nRegions={nRegions}
            centreMhz={centres}
            columnWidth={2}
          />
        </Panel>
        <Panel
          flush
          title="Posterior band state"
          subtitle="outlined columns are the receiver window this step"
          actions={
            <RampLegend
              lut={BELIEF_LUT}
              min={0}
              max={1}
              label="belief"
              className="w-24"
            />
          }
          className="shrink-0"
        >
          <div className="px-2 pb-2">
            <RegionBars
              frames={frames}
              frame={frame}
              select={(entry) => entry.belief}
              lut={BELIEF_LUT}
              height={92}
            />
            <div className="mono flex justify-between px-1 text-[9px] text-faint">
              <span>{regionLabel(0, centres?.[0])}</span>
              <span>
                {int(frame.band_truth)} occupied regions · truth sealed until
                scoring
              </span>
              <span>{regionLabel(nRegions - 1, centres?.[nRegions - 1])}</span>
            </div>
          </div>
        </Panel>
      </div>
    </div>
  );
}

function DecisionScene({
  frame,
  frames,
  nRegions,
  centres,
}: LiveSceneProps & { nRegions: number; centres?: number[] }) {
  const sum = contributionTotal(frame.factors);
  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-[minmax(0,1.15fr)_minmax(380px,0.85fr)]">
      <div className="flex min-h-0 flex-col gap-3">
        <Panel
          title="Why this window"
          subtitle="the exact additive terms behind the action — penalties extend left of zero"
          actions={
            <Badge
              tone={Math.abs(sum - frame.action_value) < 0.002 ? "good" : "bad"}
            >
              Σ {signed(sum, 3)} · V {num(frame.action_value, 3)}
            </Badge>
          }
          className="min-h-[360px] flex-1"
        >
          <FactorBars factors={frame.factors} />
          <div className="mt-4 grid grid-cols-3 gap-3 border-t border-line pt-4">
            <DecisionDatum
              label="Chosen window"
              value={`${frame.regions[0]}–${frame.regions.at(-1)}`}
              hint={`${frame.regions.length} of ${nRegions} regions`}
              tone="signal"
            />
            <DecisionDatum
              label="Exploration rate"
              value={pct(frame.exploration_rate)}
              hint={
                frame.change.exploration_boost > 0
                  ? `change boost ${num(frame.change.exploration_boost, 2)}`
                  : "posterior-driven"
              }
              tone="warn"
            />
            <DecisionDatum
              label="Periodicity"
              value={
                frame.periodicity.period_steps > 0
                  ? `${int(frame.periodicity.period_steps)} steps`
                  : "not found"
              }
              hint={`strength ${num(frame.periodicity.strength, 2)}`}
              tone="mag"
            />
          </div>
        </Panel>
        <Panel
          flush
          title="Belief · uncertainty · staleness"
          subtitle="three different quantities, three fixed colour ramps"
          className="shrink-0"
        >
          <div className="space-y-1.5 px-2 py-1.5">
            <LabeledRegions
              label="belief"
              frames={frames}
              frame={frame}
              select={(entry) => entry.belief}
              lut={BELIEF_LUT}
            />
            <LabeledRegions
              label="uncertainty"
              frames={frames}
              frame={frame}
              select={(entry) => entry.uncertainty}
              lut={UNCERTAINTY_LUT}
            />
            <LabeledRegions
              label="staleness"
              frames={frames}
              frame={frame}
              select={(entry) => entry.staleness}
              lut={MEMORY_LUT}
              scale={(value) => Math.min(1, value / 120)}
            />
          </div>
        </Panel>
      </div>
      <div className="grid min-h-0 grid-rows-[auto_1fr] gap-3">
        <Panel
          title="Change response"
          subtitle="Page–Hinkley + EWMA, conservative by design"
        >
          <div className="grid grid-cols-2 gap-4">
            <Stat
              label="Change score"
              value={num(frame.change.score, 3)}
              hint={`statistic ${num(frame.change.statistic, 2)}`}
              tone={frame.change.flag ? "bad" : "ink"}
            />
            <Stat
              label="Detector"
              value={frame.change.flag ? "FIRED" : "quiet"}
              hint={`${frame.change.change_steps.length} changes recorded`}
              tone={frame.change.flag ? "bad" : "good"}
            />
            <Stat
              label="Since change"
              value={int(frame.change.steps_since_change)}
              hint="steps"
              tone="ink"
            />
            <Stat
              label="Exploration boost"
              value={num(frame.change.exploration_boost, 2)}
              hint="added only after a detected shift"
              tone="warn"
            />
          </div>
        </Panel>
        <div className="grid min-h-0 grid-rows-3 gap-3">
          <DemoTrend
            label="Cumulative reward"
            value={num(frame.cumulative_reward, 1)}
            colour={PALETTE.accent}
            frames={frames}
            select={(entry) => entry.cumulative_reward}
          />
          <DemoTrend
            label="Regret vs sealed oracle"
            value={num(frame.cumulative_regret, 1)}
            colour={PALETTE.warn}
            frames={frames}
            select={(entry) => entry.cumulative_regret}
          />
          <DemoTrend
            label="Change score"
            value={num(frame.change.score, 2)}
            colour={PALETTE.bad}
            frames={frames}
            select={(entry) => entry.change.score}
          />
        </div>
      </div>
      <span className="pointer-events-none absolute bottom-16 left-7 hidden text-[9px] text-faint 2xl:block">
        {centres
          ? `${num(centres[frame.regions[0]], 1)}–${num(centres[frame.regions.at(-1) ?? 0], 1)} MHz`
          : "region-indexed band"}
      </span>
    </div>
  );
}

function MemoryScene({
  frame,
  frames,
  memory,
}: LiveSceneProps & { memory: MemorySnapshot | null }) {
  const prototypes = memory?.prototypes ?? [];
  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(380px,0.8fr)]">
      <Panel
        flush
        title="Associative memory constellation"
        subtitle={
          memory
            ? `${memory.size} stored contexts · bounded capacity ${memory.capacity}`
            : "the prototype store is written into the result when the episode ends"
        }
        actions={
          <Badge tone={frame.memory.recognised ? "mag" : "neutral"}>
            {frame.memory.recognised
              ? `recalled #${frame.memory.prototype_id}`
              : "no context recognised"}
          </Badge>
        }
      >
        {prototypes.length > 0 ? (
          <MemoryConstellation
            prototypes={prototypes}
            readout={frame.memory}
            step={frame.step}
          />
        ) : (
          <EmptyState
            icon={<BrainCircuit className="size-7 text-mag" />}
            title="The live read is real; the stored prototype table is not available yet"
            detail="Similarity and top-k retrieval weights stream every step. Prototype vectors are captured once in the completed result, so this constellation appears when the episode finishes instead of borrowing a store from a different run."
          />
        )}
      </Panel>
      <div className="flex min-h-0 flex-col gap-3">
        <Panel
          title="This step's Hopfield read"
          subtitle="softmax weights over the contexts returned by the server"
        >
          <div className="grid grid-cols-3 gap-4 border-b border-line pb-4">
            <Stat
              label="Similarity"
              value={num(frame.memory.similarity, 3)}
              hint={
                frame.memory.recognised
                  ? "above recognition gate"
                  : "below recognition gate"
              }
              tone={frame.memory.recognised ? "mag" : "ink"}
            />
            <Stat
              label="Match"
              value={
                frame.memory.prototype_id === null
                  ? "—"
                  : `#${frame.memory.prototype_id}`
              }
              hint={frame.memory.label || "unlabelled context"}
              tone="accent"
            />
            <Stat
              label="Context age"
              value={int(frame.memory.age)}
              hint={`${int(frame.memory.visits)} visits · utility ${num(frame.memory.utility, 2)}`}
              tone="ink"
            />
          </div>
          {frame.memory.top_ids.length > 0 ? (
            <div className="mt-4 space-y-2">
              {frame.memory.top_ids.map((id, index) => {
                const weight = frame.memory.top_weights[index] ?? 0;
                return (
                  <div
                    key={id}
                    className="grid grid-cols-[52px_1fr_56px] items-center gap-2"
                  >
                    <span className="mono text-[11px] text-ink-dim">#{id}</span>
                    <span className="h-2 overflow-hidden rounded-full bg-void">
                      <motion.span
                        className="block h-full rounded-full bg-mag"
                        animate={{ width: `${Math.max(1, weight * 100)}%` }}
                        transition={{
                          type: "spring",
                          stiffness: 220,
                          damping: 26,
                        }}
                      />
                    </span>
                    <span className="mono text-right text-[11px] text-mag">
                      {num(weight, 3)}
                    </span>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="mt-4 text-[11px] leading-relaxed text-faint">
              No top-k read was returned at this step. The memory term therefore
              contributes nothing.
            </p>
          )}
        </Panel>

        {memory && (
          <Panel
            title="Bounded store"
            subtitle="contexts, not sealed occupancy truth"
          >
            <div className="grid grid-cols-3 gap-4">
              <Stat
                label="Held"
                value={`${int(memory.size)} / ${int(memory.capacity)}`}
                hint="bounded capacity"
                tone="signal"
              />
              <Stat
                label="Writes"
                value={int(memory.writes)}
                hint={`${int(memory.creations)} creations`}
                tone="accent"
              />
              <Stat
                label="Evictions"
                value={int(memory.evictions)}
                hint="lowest utility first"
                tone={memory.evictions > 0 ? "warn" : "ink"}
              />
            </div>
          </Panel>
        )}

        <div className="grid min-h-0 flex-1 grid-rows-2 gap-3">
          <DemoTrend
            label="Recall similarity"
            value={num(frame.memory.similarity, 3)}
            colour={PALETTE.mag}
            frames={frames}
            select={(entry) => entry.memory.similarity}
            domain={[0, 1]}
          />
          <DemoTrend
            label="Memory contribution"
            value={signed(frame.factors["contribution.memory"] ?? 0, 3)}
            colour={PALETTE.accent}
            frames={frames}
            select={(entry) => entry.factors["contribution.memory"] ?? 0}
          />
        </div>
      </div>
    </div>
  );
}

type LiveSceneProps = {
  frame: Frame;
  frames: ReturnType<typeof useLive>["frames"];
};

function LabeledRegions({
  label,
  frames,
  frame,
  select,
  lut,
  scale,
}: {
  label: string;
  frames: LiveSceneProps["frames"];
  frame: Frame;
  select: (frame: Frame) => number[];
  lut: Uint8ClampedArray;
  scale?: (value: number) => number;
}) {
  return (
    <div className="grid grid-cols-[86px_1fr] items-center gap-2">
      <span className="eyebrow text-[9px]">{label}</span>
      <RegionBars
        frames={frames}
        frame={frame}
        select={select}
        lut={lut}
        scale={scale}
        height={38}
      />
    </div>
  );
}

function DecisionDatum({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint: string;
  tone: "signal" | "warn" | "mag";
}) {
  const colour = { signal: "text-signal", warn: "text-warn", mag: "text-mag" }[
    tone
  ];
  return (
    <div>
      <p className="eyebrow">{label}</p>
      <p className={cn("mono mt-1 text-lg font-semibold", colour)}>{value}</p>
      <p className="mt-0.5 text-[10px] text-faint">{hint}</p>
    </div>
  );
}

function DemoTrend({
  label,
  value,
  colour,
  frames,
  select,
  domain,
}: {
  label: string;
  value: string;
  colour: string;
  frames: LiveSceneProps["frames"];
  select: (frame: Frame) => number;
  domain?: [number, number];
}) {
  return (
    <Panel flush className="min-h-0">
      <div className="flex items-center justify-between px-3.5 pt-2.5">
        <span className="eyebrow">{label}</span>
        <span className="mono text-sm font-semibold" style={{ color: colour }}>
          {value}
        </span>
      </div>
      <Sparkline
        frames={frames}
        value={select}
        colour={colour}
        domain={domain}
        height={60}
        zeroLine
      />
    </Panel>
  );
}

function PresentationFooter({
  sceneIndex,
  frame,
  event,
  onPrevious,
  onNext,
}: {
  sceneIndex: number;
  frame: Frame;
  event: string | null;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <footer className="panel lit flex h-12 shrink-0 items-center gap-3 px-3">
      <button
        type="button"
        onClick={onPrevious}
        className="grid size-8 place-items-center rounded-md border border-line text-muted transition-colors hover:bg-panel-2 hover:text-ink"
        aria-label="Previous demo view"
      >
        <ChevronLeft className="size-4" />
      </button>
      <div className="flex gap-1.5">
        {SCENES.map((entry, index) => (
          <span
            key={entry.id}
            className={cn(
              "h-1.5 rounded-full transition-all",
              index === sceneIndex ? "w-8 bg-accent" : "w-1.5 bg-line-bright",
            )}
          />
        ))}
      </div>
      <div className="h-5 w-px bg-line" />
      <div className="min-w-0 flex-1">
        <p className="mono truncate text-[10px] text-ink-dim">
          {event ??
            frame.notes[0] ??
            `window ${frame.regions[0]}–${frame.regions.at(-1)} selected at step ${frame.step}`}
        </p>
      </div>
      <p className="hidden items-center gap-1.5 text-[9px] text-faint lg:flex">
        <ShieldCheck className="size-3 text-good" />
        evaluation truth is sealed from the scheduler and shown only after each
        action
      </p>
      <button
        type="button"
        onClick={onNext}
        className="grid size-8 place-items-center rounded-md border border-line text-muted transition-colors hover:bg-panel-2 hover:text-ink"
        aria-label="Next demo view"
      >
        <ChevronRight className="size-4" />
      </button>
    </footer>
  );
}

function DemoEmpty({
  connecting,
  label,
}: {
  connecting: boolean;
  label: string | null;
}) {
  return (
    <main className="grid min-h-0 flex-1 place-items-center py-6">
      <div className="grid w-full max-w-5xl gap-4 lg:grid-cols-[1.05fr_0.95fr]">
        <motion.section
          initial={{ opacity: 0, x: -24 }}
          animate={{ opacity: 1, x: 0 }}
          className="panel lit relative overflow-hidden p-8"
        >
          <div className="absolute -right-20 -top-20 size-72 rounded-full bg-accent/10 blur-3xl" />
          <div className="relative">
            <Badge tone="accent">
              <Sparkles className="size-3" /> SIH presentation view
            </Badge>
            <h1 className="mt-6 max-w-xl text-4xl font-semibold leading-tight tracking-tight text-ink">
              Sense less. Learn the context. Catch more of what matters.
            </h1>
            <p className="mt-4 max-w-xl text-sm leading-relaxed text-muted">
              AAMS-X schedules narrow real-spectrum observations with an
              interpretable memory-augmented policy. Every demo instrument waits
              for an executed frame; there is no synthetic fallback behind this
              screen.
            </p>
            <div className="mt-7 grid grid-cols-3 gap-4 border-t border-line pt-5">
              <HeroFact
                icon={<Radio className="size-4 text-accent" />}
                label="Observe"
                detail="public cached recordings"
              />
              <HeroFact
                icon={<Crosshair className="size-4 text-signal" />}
                label="Decide"
                detail="eight exposed terms"
              />
              <HeroFact
                icon={<BrainCircuit className="size-4 text-mag" />}
                label="Remember"
                detail="bounded context memory"
              />
            </div>
            {connecting && (
              <p className="mt-5 rounded-md border border-warn/30 bg-warn/[0.06] px-3 py-2 text-[11px] text-warn">
                {label ??
                  "The run is selected; waiting for its first streamed frame."}
              </p>
            )}
          </div>
        </motion.section>
        <motion.section
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.08 }}
          className="panel lit p-5"
        >
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="eyebrow">Start the evidence</p>
              <p className="mt-1 text-xs text-faint">
                real cached recordings only
              </p>
            </div>
            <Play className="size-5 text-accent" />
          </div>
          <LaunchPanel compact />
          <p className="mt-4 border-t border-line pt-3 text-[10px] leading-relaxed text-faint">
            The launch uses the same scenario, scheduler, seed, ablation flags
            and tuned weights as the full console. Demo Mode changes
            presentation only.
          </p>
        </motion.section>
      </div>
    </main>
  );
}

function HeroFact({
  icon,
  label,
  detail,
}: {
  icon: ReactNode;
  label: string;
  detail: string;
}) {
  return (
    <div>
      <p className="flex items-center gap-2 text-xs font-semibold text-ink-dim">
        {icon}
        {label}
      </p>
      <p className="mt-1 text-[10px] text-faint">{detail}</p>
    </div>
  );
}

/** A frame carries an absolute archive timestamp, not elapsed experiment seconds. */
function archiveClock(epochSeconds: number): string {
  if (!Number.isFinite(epochSeconds)) return "—";
  return new Date(epochSeconds * 1000).toLocaleTimeString("en-GB", {
    hour12: false,
    timeZone: "UTC",
  });
}

function HelpOverlay({ onClose }: { onClose: () => void }) {
  const shortcuts = [
    ["← / →", "previous or next evidence view"],
    ["1 · 2 · 3", "Sense, Decide or Remember directly"],
    ["F", "toggle browser full screen"],
    ["H / ?", "show or hide this guide"],
    ["Esc", "close guide, exit full screen, then return home"],
  ];
  return (
    <motion.div
      className="absolute inset-0 z-50 grid place-items-center bg-void/80 p-6 backdrop-blur-md"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.section
        className="panel lit w-full max-w-lg p-5"
        initial={{ y: 20, scale: 0.97 }}
        animate={{ y: 0, scale: 1 }}
        exit={{ y: 12, scale: 0.98 }}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div>
            <p className="eyebrow">Presentation controls</p>
            <p className="mt-1 text-xs text-faint">
              keyboard-first for a projector or judge walkthrough
            </p>
          </div>
          <Button size="sm" icon={<X className="size-3.5" />} onClick={onClose}>
            Close
          </Button>
        </div>
        <div className="mt-5 space-y-2">
          {shortcuts.map(([key, detail]) => (
            <div
              key={key}
              className="flex items-center justify-between rounded-md border border-line bg-void/45 px-3 py-2.5"
            >
              <kbd className="rounded border border-line-bright bg-panel-2 px-2 py-1 text-[11px] text-accent">
                {key}
              </kbd>
              <span className="text-[11px] text-ink-dim">{detail}</span>
            </div>
          ))}
        </div>
        <div className="mt-4 flex items-start gap-2.5 rounded-md border border-good/25 bg-good/[0.05] px-3 py-2.5 text-[10.5px] leading-relaxed text-muted">
          <Info className="mt-0.5 size-3.5 shrink-0 text-good" />
          Scene changes do not pause, replay or transform the experiment. Every
          view reads the same live frame ring; only the camera and explanatory
          layout change.
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <Link
            to="/"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-[11px] font-semibold text-ink-dim hover:bg-panel-2"
          >
            <Home className="size-3.5" /> Command Center
          </Link>
          <Link
            to="/registry"
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line px-3 text-[11px] font-semibold text-ink-dim hover:bg-panel-2"
          >
            <Layers3 className="size-3.5" /> Registry
          </Link>
        </div>
      </motion.section>
    </motion.div>
  );
}
