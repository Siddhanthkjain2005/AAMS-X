/** Experiment Lab — pick a preset, or build a scenario out of measured windows.
 *
 * Three things this screen refuses to do, each of which would be easier.
 *
 * It does not write its own preset descriptions. Every preset's text is generated
 * server-side from the window it selected ("persistence 0.90, 4 regions occupied more
 * than half the time"), so the description is a measurement. Paraphrasing it here would
 * turn a measured claim into a marketing one.
 *
 * It does not offer a free-text SQL box for the window index. The endpoint has its own
 * denylist, but composing predicates from a fixed vocabulary means the browser cannot
 * send a clause nobody designed — the filters below expand to a handful of known columns
 * and nothing else.
 *
 * It does not print the numbers from the four signature experiments. Those live in
 * docs/EXPERIMENTS.md because they came out of executed runs; a screen that showed them
 * before you ran anything would be showing you someone else's results as if they were
 * yours. Each card says what its experiment measures and which metric decides it.
 */

import { AnimatePresence, motion } from "framer-motion";
import {
  Check,
  CircleSlash,
  FlaskConical,
  Plus,
  Rows3,
  Shuffle,
  Trash2,
  Wand2,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  useDatasets,
  useScenario,
  useScenarios,
  useStartEpisode,
  useValidateScenario,
  useWindows,
} from "@/api/queries";
import type { ScenarioRequest, ScenarioSpec, Split, WindowRow } from "@/api/types";
import { LaunchPanel } from "@/components/run/LaunchPanel";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  NumberInput,
  Panel,
  Select,
  Slider,
  Stat,
  Tabs,
  Toggle,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { duration, int, num, pct } from "@/lib/format";
import { PALETTE } from "@/lib/palette";
import { useSession } from "@/state/session";

type Tab = "presets" | "custom" | "signature";

/** Split tones, used identically everywhere a split is named. */
const SPLIT_TONE: Record<Split, "neutral" | "signal" | "mag"> = {
  train: "neutral",
  validation: "signal",
  unseen: "mag",
};

const SPLIT_MEANING: Record<Split, string> = {
  train: "tuning was allowed to see this",
  validation: "used to choose between candidates, never to fit weights",
  unseen: "held out from everything — the only honest generalisation test",
};

export default function ExperimentLab() {
  const scenarios = useScenarios();
  const [tab, setTab] = useState<Tab>("presets");
  const launchScenarioId = useSession((session) => session.launch.scenarioId);
  const patchLaunch = useSession((session) => session.patchLaunch);

  const presets = scenarios.data?.presets ?? [];
  const unavailable = new Set(scenarios.data?.unavailable ?? []);
  const detail = useScenario(tab === "presets" ? launchScenarioId || null : null);

  const bySplit = useMemo(() => {
    const counts: Record<string, number> = { train: 0, validation: 0, unseen: 0 };
    for (const preset of presets) counts[preset.split] = (counts[preset.split] ?? 0) + 1;
    return counts;
  }, [presets]);

  if (scenarios.isLoading) {
    return (
      <div className="p-4">
        <Panel className="min-h-96">
          <LoadingState label="Reading the preset library" />
        </Panel>
      </div>
    );
  }
  if (scenarios.isError) {
    return (
      <div className="p-4">
        <Panel className="min-h-96">
          <ErrorState error={scenarios.error} onRetry={() => void scenarios.refetch()} />
        </Panel>
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-3 p-4">
      <Panel flush className="shrink-0">
        <div className="grid grid-cols-2 gap-x-6 gap-y-4 p-4 md:grid-cols-3 xl:grid-cols-6">
          <Stat label="Presets built" value={int(presets.length)} hint="mined from the cache" tone="accent" />
          <Stat
            label="Unbuildable"
            value={int(unavailable.size)}
            hint={unavailable.size ? "listed and disabled, never faked" : "the cache satisfies every preset"}
            tone={unavailable.size ? "warn" : "good"}
          />
          <Stat label="Train" value={int(bySplit.train ?? 0)} hint={SPLIT_MEANING.train} tone="ink" />
          <Stat
            label="Validation"
            value={int(bySplit.validation ?? 0)}
            hint={SPLIT_MEANING.validation}
            tone="signal"
          />
          <Stat label="Unseen" value={int(bySplit.unseen ?? 0)} hint={SPLIT_MEANING.unseen} tone="mag" />
          <Stat
            label="Families"
            value={int(scenarios.data?.families.length ?? 0)}
            hint="each defined by a measured predicate"
            tone="ink"
          />
        </div>
      </Panel>

      <div className="flex shrink-0 items-center justify-between gap-3">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: "presets", label: "Presets", count: presets.length },
            { value: "custom", label: "Custom scenario" },
            { value: "signature", label: "Signature experiments", count: 4 },
          ]}
        />
        {scenarios.data?.note && (
          <p className="mono hidden truncate text-[10px] text-faint xl:block">
            {scenarios.data.note}
          </p>
        )}
      </div>

      {tab === "presets" && (
        <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[1fr_380px]">
          <div className="grid min-h-0 auto-rows-min grid-cols-1 gap-3 md:grid-cols-2">
            {presets.map((preset) => (
              <PresetCard
                key={preset.scenario_id}
                preset={preset}
                selected={preset.scenario_id === launchScenarioId}
                blocked={unavailable.has(preset.scenario_id)}
                onSelect={() => patchLaunch({ scenarioId: preset.scenario_id })}
              />
            ))}
            {presets.length === 0 && (
              <Panel className="md:col-span-2 min-h-64">
                <EmptyState
                  title="No preset could be built from this cache"
                  detail="Every preset is a query against the measured window index. With no recordings ingested there is nothing to query, and this screen will not invent a scenario to fill the space."
                  icon={<CircleSlash className="size-5 text-warn" />}
                />
              </Panel>
            )}
          </div>

          <div className="flex min-h-0 flex-col gap-3">
            <Panel title="Launch" subtitle="the policy, its weights, and the seed">
              <LaunchPanel />
            </Panel>
            <Panel
              title="What gets replayed"
              subtitle={detail.data ? `${detail.data.segments_measured.length} measured segment(s)` : "select a preset"}
              className="min-h-0 flex-1"
            >
              {detail.isLoading ? (
                <LoadingState label="Measuring the scenario" />
              ) : detail.isError ? (
                <ErrorState error={detail.error} />
              ) : detail.data ? (
                <ScenarioDetailBody scenario={detail.data} />
              ) : (
                <p className="text-[11px] leading-relaxed text-faint">
                  Pick a preset to see the recordings behind it, their provenance and the
                  splice points that make recovery measurable.
                </p>
              )}
            </Panel>
          </div>
        </div>
      )}

      {tab === "custom" && <CustomScenario />}
      {tab === "signature" && (
        <SignatureExperiments presets={presets} unavailable={unavailable} />
      )}
    </div>
  );
}

function PresetCard({
  preset,
  selected,
  blocked,
  onSelect,
}: {
  preset: ScenarioSpec;
  selected: boolean;
  blocked: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={blocked ? undefined : onSelect}
      disabled={blocked}
      className={cn(
        "panel lit flex flex-col gap-2.5 p-3.5 text-left transition-colors",
        selected ? "border-accent/60 bg-accent/[0.04]" : "hover:border-line-bright",
        blocked && "cursor-not-allowed opacity-45",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="truncate text-[13px] font-semibold text-ink">{preset.name}</h3>
          <p className="mono mt-0.5 truncate text-[10px] text-faint">{preset.scenario_id}</p>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {selected && <Badge tone="accent"><Check className="size-2.5" />loaded</Badge>}
          <Badge tone={SPLIT_TONE[preset.split]}>{preset.split}</Badge>
        </div>
      </div>

      <p className="line-clamp-4 text-[11px] leading-relaxed text-muted">{preset.description}</p>

      <div className="mono grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-faint">
        <span>family · {preset.family}</span>
        <span>{int(preset.horizon)} steps</span>
        <span>{int(preset.n_regions)} regions · window {int(preset.receiver.window_size)}</span>
        <span>bin {num(preset.time_bin, 0)} s</span>
        <span>
          budget{" "}
          {preset.budget === null ? (
            <span className="text-muted">unconstrained</span>
          ) : (
            <span className="text-warn">{num(preset.effective_budget, 0)}</span>
          )}
        </span>
        <span>
          {preset.change_points.length > 0 ? (
            <span className="text-warn">{preset.change_points.length} splice(s)</span>
          ) : (
            "no splice"
          )}
        </span>
      </div>

      <div className="flex flex-wrap gap-1">
        {blocked && <Badge tone="warn">not in cache</Badge>}
        {preset.segments.map((segment) => (
          <Badge key={`${segment.recording_id}-${segment.start_step}`} tone="neutral">
            {segment.phase || segment.label || segment.recording_id}
          </Badge>
        ))}
      </div>
    </button>
  );
}

/** The measured side of a preset: which recordings, how complete, and where it splices. */
function ScenarioDetailBody({ scenario }: { scenario: ReturnType<typeof useScenario>["data"] }) {
  if (!scenario) return null;
  const availability = scenario.availability ?? 1;
  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-x-4 gap-y-2">
        <Stat label="Truth occupancy" value={pct(scenario.truth_occupancy)} hint="sealed, scoring only" tone="mag" />
        <Stat
          label="Archive coverage"
          value={pct(availability)}
          hint={availability < 1 ? "the rest are real gaps" : "no gaps in this block"}
          tone={availability < 0.95 ? "warn" : "good"}
        />
        <Stat label="Horizon" value={`${int(scenario.horizon)} steps`} hint={duration(scenario.horizon * scenario.time_bin * 0.25)} tone="ink" />
        <Stat
          label="Budget"
          value={scenario.budget === null ? "∞" : num(scenario.effective_budget, 0)}
          hint={scenario.budget === null ? "every step affordable" : "Σ c(a_t) ≤ B"}
          tone={scenario.budget === null ? "ink" : "warn"}
        />
      </div>

      <div className="flex flex-col gap-2 border-t border-line pt-2.5">
        <span className="eyebrow">Segments as measured</span>
        {scenario.segments_measured.map((segment, index) => (
          <div key={`${segment.recording_id}-${index}`} className="rounded-md border border-line bg-void/60 p-2.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className="mono truncate text-[11px] text-ink-dim">
                {segment.phase && <span className="text-accent">{segment.phase} · </span>}
                {segment.station}
              </span>
              <span className="mono shrink-0 text-[10px] text-faint">
                +{int(segment.start_step)} → {int(segment.start_step + segment.n_steps)}
              </span>
            </div>
            <div className="mono mt-1 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9.5px] text-faint">
              <span>archetype · {segment.stats.archetype}</span>
              <span>occupancy · {pct(segment.stats.occupancy)}</span>
              <span>persistence · {num(segment.stats.persistence, 2)}</span>
              <span>burstiness · {num(segment.stats.burstiness, 2)}</span>
              <span>
                period ·{" "}
                {segment.stats.period_steps > 0
                  ? `${int(segment.stats.period_steps)} steps (r ${num(segment.stats.period_strength, 2)})`
                  : "none mined"}
              </span>
              <span>available · {pct(segment.availability)}</span>
            </div>
            <p className="mono mt-1.5 truncate text-[9px] text-faint">
              {segment.provenance.adapter} · {segment.provenance.license} ·{" "}
              {segment.provenance.checksum.slice(0, 10)}
            </p>
          </div>
        ))}
      </div>

      {scenario.change_points.length > 0 && (
        <div className="flex flex-col gap-1 border-t border-line pt-2.5">
          <span className="eyebrow">Splice points</span>
          <p className="mono text-[10px] text-warn">
            step {scenario.change_points.map((step) => int(step)).join(" · ")}
          </p>
          <p className="text-[10px] leading-relaxed text-faint">
            The only fabricated thing in the scenario is the boundary itself — both sides are
            real recordings. Knowing exactly where it lands is what makes time-to-recovery a
            measurement rather than an impression.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-1 border-t border-line pt-2.5">
        <span className="eyebrow">Reward weights in force</span>
        <div className="mono grid grid-cols-2 gap-x-3 text-[10px] text-muted">
          {Object.entries(scenario.reward).map(([term, weight]) => (
            <span key={term} className="flex justify-between gap-2">
              <span className="text-faint">{term}</span>
              <span>{num(weight, 2)}</span>
            </span>
          ))}
        </div>
        <p className="text-[10px] leading-relaxed text-faint">
          These shape the score, not the policy. They were never tuned — tuning the objective
          to flatter the scheduler would make every later comparison meaningless.
        </p>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------------------
 * Custom scenarios, composed from the measured window index.
 *
 * The index is the scenario library: `build_index` walked every cached recording at
 * three cadences and three window lengths and characterised each block, so asking for
 * "a strongly periodic 600-step window" is a query, not a request for something to be
 * generated. Everything below composes a `WHERE` clause out of the columns that table
 * actually has — which is why `role` is absent from the vocabulary: the split lives on
 * the station catalogue, not on the index, so a split filter expands to the station
 * names the catalogue assigns that role.
 * ------------------------------------------------------------------------- */

const ARCHETYPES = [
  "periodic",
  "persistent",
  "intermittent",
  "bursting",
  "rapidly-changing",
  "quiet",
  "mixed",
] as const;

/** The three window lengths the index holds, and what each is for. */
const SPANS = [
  { value: "1200", label: "1200 — one phase, full horizon" },
  { value: "600", label: "600 — half, for an A→B splice" },
  { value: "400", label: "400 — third, for an A→B→A′ recurrence" },
];

/** Cadences the index profiled. 0.25 s native, so these are 1 s / 5 s / 15 s per step. */
const TIME_BINS = [
  { value: "4", label: "4 bins · 1 s per step" },
  { value: "20", label: "20 bins · 5 s per step" },
  { value: "60", label: "60 bins · 15 s per step" },
];

const ORDERINGS: { value: string; label: string; sql: string }[] = [
  { value: "busy", label: "Busiest band", sql: "occupancy DESC" },
  { value: "persistent", label: "Most persistent", sql: "persistence DESC" },
  { value: "cycle", label: "Strongest cycle", sql: "period_strength DESC" },
  { value: "bursty", label: "Burstiest", sql: "burstiness DESC" },
  { value: "loud", label: "Strongest margin", sql: "p95_margin_db DESC" },
  { value: "drift", label: "Most non-stationary", sql: "profile_drift DESC" },
];

const PHASE_NAMES = ["A", "B", "A-prime", "C", "D", "E"];

interface Filters {
  archetype: string;
  split: string;
  span: string;
  timeBin: string;
  minOccupancy: number;
  minPersistence: number;
  minCycle: number;
  order: string;
}

const DEFAULT_FILTERS: Filters = {
  archetype: "any",
  split: "any",
  span: "600",
  timeBin: "4",
  minOccupancy: 0,
  minPersistence: 0,
  minCycle: 0,
  order: "busy",
};

/** Station identifiers are catalogue-supplied; refuse anything that is not an identifier. */
const SAFE_NAME = /^[A-Za-z0-9_-]+$/;

/**
 * Compose the predicate. Every literal that reaches this string is either a number this
 * function formatted itself or a token matched against a list defined above, so there is
 * no path from a keystroke to SQL.
 */
function buildWhere(filters: Filters, stationsForSplit: string[]): string {
  const clauses: string[] = [
    `time_bin = ${Math.round(Number(filters.timeBin) || 4)}`,
    `n_steps = ${Math.round(Number(filters.span) || 600)}`,
  ];
  if (ARCHETYPES.includes(filters.archetype as (typeof ARCHETYPES)[number])) {
    clauses.push(`archetype = '${filters.archetype}'`);
  }
  if (filters.minOccupancy > 0) clauses.push(`occupancy >= ${filters.minOccupancy.toFixed(4)}`);
  if (filters.minPersistence > 0) {
    clauses.push(`persistence >= ${filters.minPersistence.toFixed(4)}`);
  }
  if (filters.minCycle > 0) {
    clauses.push(`period_strength >= ${filters.minCycle.toFixed(4)}`, "period_steps > 0");
  }
  if (filters.split !== "any") {
    const names = stationsForSplit.filter((name) => SAFE_NAME.test(name));
    // An empty IN () is a syntax error, and a split with no cached station should return
    // nothing rather than silently widening to every station.
    clauses.push(names.length ? `station IN (${names.map((n) => `'${n}'`).join(", ")})` : "FALSE");
  }
  return clauses.join(" AND ");
}

function CustomScenario() {
  const datasets = useDatasets();
  const validate = useValidateScenario();
  const start = useStartEpisode();
  const launch = useSession((session) => session.launch);
  const setExperimentId = useSession((session) => session.setExperimentId);

  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [picked, setPicked] = useState<WindowRow[]>([]);
  const [windowSize, setWindowSize] = useState(4);
  const [budget, setBudget] = useState(600);
  const [capped, setCapped] = useState(false);
  const [split, setSplit] = useState<Split>("train");
  const [validated, setValidated] = useState<string | null>(null);

  const catalogue = datasets.data?.catalogue ?? [];
  const patch = (next: Partial<Filters>) => setFilters((prior) => ({ ...prior, ...next }));

  const stationsForSplit = useMemo(
    () =>
      catalogue
        .filter((station) => String(station.role) === filters.split)
        .map((station) => String(station.name)),
    [catalogue, filters.split],
  );

  const where = useMemo(() => buildWhere(filters, stationsForSplit), [filters, stationsForSplit]);
  const orderBy = ORDERINGS.find((entry) => entry.value === filters.order)?.sql ?? "occupancy DESC";
  const windows = useWindows(
    { where, order_by: orderBy, limit: 40 },
    filters.split === "any" || catalogue.length > 0,
  );

  // Geometry is not a control: the server takes `n_regions` and `time_bin` from the first
  // window, because those are properties of how the block was measured. Inventing a
  // different binning here would describe a scenario the replay would not produce.
  const geometry = picked[0];
  const nRegions = geometry ? Number(geometry.n_regions) : 32;
  const timeBin = geometry ? Number(geometry.time_bin) : 4;
  const horizon = picked.reduce((total, row) => total + Number(row.n_steps), 0);
  const mismatched = picked.filter(
    (row) => Number(row.time_bin) !== timeBin || Number(row.n_regions) !== nRegions,
  );

  const request: ScenarioRequest = useMemo(
    () => ({
      name: picked.length > 1 ? `Spliced ${picked.length}-phase composition` : "Single-phase window",
      description: describeComposition(picked),
      family: familyFor(picked),
      segments: picked.map((row, index) => ({
        recording_id: String(row.recording_id),
        start_step: Number(row.start_step),
        n_steps: Number(row.n_steps),
        label: `${row.station} +${((Number(row.start_step) * 0.25) / 60).toFixed(0)} min`,
        phase: PHASE_NAMES[index] ?? `P${index}`,
      })),
      n_regions: nRegions,
      time_bin: timeBin,
      receiver: { window_size: windowSize },
      budget: capped ? budget : null,
      split,
    }),
    [picked, nRegions, timeBin, windowSize, capped, budget, split],
  );

  const key = JSON.stringify(request);
  const accepted = validated === key && validate.isSuccess;
  const blocked = picked.length === 0 || mismatched.length > 0;

  const runIt = () => {
    if (!accepted) return;
    start.mutate(
      {
        scenario: request,
        scheduler: launch.scheduler,
        seed: launch.seed,
        pace_hz: launch.paceHz,
        frame_stride: launch.frameStride,
        ablation: launch.ablation,
        mag_weights: launch.scheduler === "mag-nts" ? launch.magWeights : null,
      },
      { onSuccess: (started) => setExperimentId(started.experiment_id) },
    );
  };

  return (
    <div className="grid min-h-0 flex-1 grid-cols-1 gap-3 xl:grid-cols-[250px_1fr_330px]">
      <Panel title="Search the index" subtitle="fixed vocabulary, no free-text SQL">
        <div className="flex flex-col gap-3">
          <Field label="Window length" hint="all three fit the same 1200-step horizon">
            <Select value={filters.span} onChange={(span) => patch({ span })} options={SPANS} />
          </Field>
          <Field label="Cadence" hint="how much wall-clock one decision covers">
            <Select
              value={filters.timeBin}
              onChange={(timeBin) => patch({ timeBin })}
              options={TIME_BINS}
            />
          </Field>
          <Field label="Archetype" hint="assigned by measurement, not by hand">
            <Select
              value={filters.archetype}
              onChange={(archetype) => patch({ archetype })}
              options={[
                { value: "any", label: "any archetype" },
                ...ARCHETYPES.map((name) => ({ value: name, label: name })),
              ]}
            />
          </Field>
          <Field label="Split" hint={SPLIT_MEANING[filters.split as Split] ?? "every station"}>
            <Select
              value={filters.split}
              onChange={(next) => patch({ split: next })}
              options={[
                { value: "any", label: "any station" },
                { value: "train", label: "train stations" },
                { value: "validation", label: "validation stations" },
                { value: "unseen", label: "unseen stations" },
              ]}
            />
          </Field>
          <div className="flex flex-col gap-2 border-t border-line pt-2.5">
            <Slider
              label="Min occupancy"
              value={filters.minOccupancy}
              onChange={(minOccupancy) => patch({ minOccupancy })}
              max={0.8}
              colour={PALETTE.accent}
            />
            <Slider
              label="Min persistence"
              value={filters.minPersistence}
              onChange={(minPersistence) => patch({ minPersistence })}
              colour={PALETTE.signal}
            />
            <Slider
              label="Min cycle strength"
              value={filters.minCycle}
              onChange={(minCycle) => patch({ minCycle })}
              colour={PALETTE.mag}
            />
          </div>
          <Field label="Order by" hint="the index is sorted server-side">
            <Select
              value={filters.order}
              onChange={(order) => patch({ order })}
              options={ORDERINGS.map(({ value, label }) => ({ value, label }))}
            />
          </Field>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="subtle"
              icon={<Shuffle className="size-3" />}
              onClick={() => setFilters(DEFAULT_FILTERS)}
            >
              Reset
            </Button>
            <span className="mono text-[9px] text-faint">{windows.data?.count ?? 0} matched</span>
          </div>
          <p className="mono rounded border border-line bg-void/60 p-2 text-[9px] leading-relaxed break-words text-faint">
            WHERE {where}
          </p>
        </div>
      </Panel>

      <Panel
        flush
        title="Measured windows"
        subtitle="every row is a real time range in a real recording"
        className="min-h-0"
        bodyClassName="min-h-0 overflow-auto"
      >
        {windows.isLoading ? (
          <LoadingState label="querying the window index" />
        ) : windows.error ? (
          <ErrorState error={windows.error} onRetry={() => void windows.refetch()} />
        ) : (windows.data?.windows.length ?? 0) === 0 ? (
          <EmptyState
            title="No window matches"
            detail="Loosen a threshold. The index only holds what the cache actually contains, so a narrow query can legitimately return nothing."
            icon={<CircleSlash className="size-5 text-faint" />}
          />
        ) : (
          <table className="w-full border-collapse text-[11px]">
            <thead className="sticky top-0 z-1 bg-panel">
              <tr className="border-b border-line-bright">
                <th className="eyebrow py-2 pl-3 text-left">Recording</th>
                <th className="eyebrow py-2 text-left">Archetype</th>
                <th className="eyebrow py-2 text-right">Start</th>
                <th className="eyebrow py-2 text-right">Occ.</th>
                <th className="eyebrow py-2 text-right">Persist.</th>
                <th className="eyebrow py-2 text-right">Cycle</th>
                <th className="eyebrow py-2 text-right">p95 dB</th>
                <th className="w-8" />
              </tr>
            </thead>
            <tbody>
              {(windows.data?.windows ?? []).map((row) => (
                <WindowRowView
                  key={`${row.recording_id}-${row.time_bin}-${row.start_step}`}
                  row={row}
                  onAdd={() => {
                    setPicked((prior) => [...prior, row]);
                    setValidated(null);
                  }}
                />
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <div className="flex min-h-0 flex-col gap-3 overflow-auto">
        <Panel
          title="Composition"
          subtitle={picked.length ? `${picked.length} phase(s) · ${int(horizon)} steps` : "empty"}
          actions={
            picked.length > 0 ? (
              <Button
                size="sm"
                variant="subtle"
                icon={<Trash2 className="size-3" />}
                onClick={() => {
                  setPicked([]);
                  setValidated(null);
                }}
              >
                Clear
              </Button>
            ) : null
          }
        >
          {picked.length === 0 ? (
            <p className="text-[11px] leading-relaxed text-faint">
              <Rows3 className="mr-1 inline size-3" />
              Add windows from the middle column. One window is a single-phase environment;
              two spliced windows are a distribution shift; three, with the first and third
              from the same station, are a recurrence — which is the only way this project
              produces non-stationarity, since it has no simulator to ask for it.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              <AnimatePresence initial={false}>
                {picked.map((row, index) => (
                  <motion.div
                    key={`${row.recording_id}-${row.start_step}-${index}`}
                    layout
                    initial={{ opacity: 0, y: -6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, height: 0 }}
                    className="flex items-start gap-2 rounded-md border border-line bg-void/60 p-2"
                  >
                    <Badge tone={index === 0 ? "accent" : "signal"}>
                      {PHASE_NAMES[index] ?? `P${index}`}
                    </Badge>
                    <div className="min-w-0 flex-1">
                      <p className="mono truncate text-[10.5px] text-ink-dim">{row.recording_id}</p>
                      <p className="mono text-[9px] text-faint">
                        {row.archetype} · +{int(Number(row.start_step))} · {int(Number(row.n_steps))}{" "}
                        steps · occ {pct(Number(row.occupancy))}
                      </p>
                    </div>
                    <button
                      type="button"
                      title="remove this phase"
                      onClick={() => {
                        setPicked((prior) => prior.filter((_, at) => at !== index));
                        setValidated(null);
                      }}
                      className="mt-0.5 text-faint transition-colors hover:text-bad"
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </motion.div>
                ))}
              </AnimatePresence>

              {mismatched.length > 0 && (
                <p className="mono rounded border border-bad/40 bg-bad/8 p-2 text-[9.5px] leading-relaxed text-bad">
                  {mismatched.length} window(s) were measured at a different cadence or region
                  count than the first. Splicing across binnings would change what a step means
                  mid-episode, so remove them before running.
                </p>
              )}

              <div className="mono grid grid-cols-2 gap-x-3 gap-y-0.5 border-t border-line pt-2 text-[9.5px] text-faint">
                <span>regions · {int(nRegions)} (from phase A)</span>
                <span>bin · {int(timeBin)} ({num(timeBin * 0.25, 2)} s/step)</span>
                <span>horizon · {int(horizon)} steps</span>
                <span>wall clock · {duration(horizon * timeBin * 0.25)}</span>
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Receiver and budget" subtitle="the constraint the scheduler works under">
          <div className="flex flex-col gap-3">
            <Field label="Window size" hint={`${windowSize} of ${int(nRegions)} regions per step`}>
              <NumberInput value={windowSize} min={1} max={Math.max(1, nRegions)} onChange={(next) => { setWindowSize(next); setValidated(null); }} />
            </Field>
            <Toggle
              label="Cap the sensing budget"
              checked={capped}
              onChange={(next) => {
                setCapped(next);
                setValidated(null);
              }}
              hint="Σ c(a_t) ≤ B — off means every step is affordable"
            />
            {capped && (
              <Field label="Budget B" hint="in cost units, not steps">
                <NumberInput
                  value={budget}
                  min={1}
                  step={10}
                  onChange={(next) => {
                    setBudget(next);
                    setValidated(null);
                  }}
                />
              </Field>
            )}
            <Field label="Split label" hint={SPLIT_MEANING[split]}>
              <Select
                value={split}
                onChange={(next) => {
                  setSplit(next);
                  setValidated(null);
                }}
                options={[
                  { value: "train" as Split, label: "train" },
                  { value: "validation" as Split, label: "validation" },
                  { value: "unseen" as Split, label: "unseen" },
                ]}
              />
            </Field>
            <p className="text-[9.5px] leading-relaxed text-faint">
              The label is bookkeeping, not enforcement — it records which pool you drew from
              so a later report cannot quietly present a train-station result as generalisation.
              Picking "unseen" while filtering train stations mislabels your own experiment.
            </p>
          </div>
        </Panel>

        <Panel title="Validate, then run" subtitle="the server decides whether it is buildable">
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                variant="subtle"
                icon={<Wand2 className="size-3" />}
                disabled={blocked || validate.isPending}
                onClick={() =>
                  validate.mutate(request, { onSuccess: () => setValidated(key) })
                }
              >
                {validate.isPending ? "Validating…" : "Validate"}
              </Button>
              <Button
                size="sm"
                variant="primary"
                icon={<Zap className="size-3" />}
                disabled={!accepted || start.isPending}
                onClick={runIt}
              >
                {start.isPending ? "Starting…" : "Run episode"}
              </Button>
            </div>

            {!accepted && !validate.error && (
              <p className="text-[10px] leading-relaxed text-faint">
                Run is disabled until the server has accepted this exact composition. It checks
                that every segment is in the cache and long enough; a composition that only the
                browser approved of could fail halfway through an episode.
              </p>
            )}

            {validate.error && <ErrorState error={validate.error} />}

            {accepted && validate.data && (
              <div className="flex flex-col gap-2">
                <p className="mono flex items-center gap-1.5 text-[10px] text-good">
                  <Check className="size-3" />
                  buildable · {validate.data.scenario_id}
                </p>
                <ScenarioDetailBody scenario={validate.data} />
              </div>
            )}
          </div>
        </Panel>
      </div>
    </div>
  );
}

/** One index row. The numbers are the measurement; nothing here is derived in the browser. */
function WindowRowView({ row, onAdd }: { row: WindowRow; onAdd: () => void }) {
  const period = Number(row.period_steps ?? 0);
  const strength = Number(row.period_strength ?? 0);
  return (
    <tr className="border-b border-line/60 last:border-0 hover:bg-panel-2/40">
      <td className="py-1.5 pl-3">
        <span className="mono block truncate text-[10.5px] text-ink-dim">{row.recording_id}</span>
        <span className="mono block text-[9px] text-faint">
          {int(Number(row.n_steps))} steps · bin {int(Number(row.time_bin))}
        </span>
      </td>
      <td className="py-1.5">
        <Badge tone="neutral">{String(row.archetype)}</Badge>
      </td>
      <td className="mono py-1.5 text-right text-[10px] tabular-nums text-muted">
        +{int(Number(row.start_step))}
      </td>
      <td className="mono py-1.5 text-right text-[10px] tabular-nums text-ink-dim">
        {pct(Number(row.occupancy))}
      </td>
      <td className="mono py-1.5 text-right text-[10px] tabular-nums text-muted">
        {num(Number(row.persistence ?? 0), 2)}
      </td>
      <td className="mono py-1.5 text-right text-[10px] tabular-nums text-muted">
        {period > 0 ? `${int(period)} · ${num(strength, 2)}` : "—"}
      </td>
      <td className="mono py-1.5 text-right text-[10px] tabular-nums text-muted">
        {num(Number(row.p95_margin_db ?? 0), 1)}
      </td>
      <td className="pr-2 text-right">
        <button
          type="button"
          title="append as the next phase"
          onClick={onAdd}
          className="text-faint transition-colors hover:text-accent"
        >
          <Plus className="size-3.5" />
        </button>
      </td>
    </tr>
  );
}

/** A description assembled from the measured stats, so it stays a measurement. */
function describeComposition(picked: WindowRow[]): string {
  if (picked.length === 0) return "empty composition";
  return picked
    .map((row, index) => {
      const phase = PHASE_NAMES[index] ?? `P${index}`;
      return (
        `${phase}: ${row.station} ${row.archetype}, occupancy ` +
        `${(Number(row.occupancy) * 100).toFixed(1)}%, persistence ` +
        `${Number(row.persistence ?? 0).toFixed(2)}`
      );
    })
    .join(" → ");
}

/**
 * The family a composition belongs to, decided by its shape rather than by a dropdown.
 * Three phases whose first and last come from the same recording is a recurrence; two
 * unlike phases are a shift; a single phase inherits its own measured archetype when that
 * archetype is also a scenario family, and falls back to `persistent` when it is not.
 */
function familyFor(picked: WindowRow[]): string {
  if (picked.length >= 3) {
    return picked[0].recording_id === picked[picked.length - 1].recording_id
      ? "recurring-context"
      : "distribution-shift";
  }
  if (picked.length === 2) return "distribution-shift";
  const archetype = String(picked[0]?.archetype ?? "");
  const families = ["persistent", "periodic", "intermittent", "bursting", "rapidly-changing"];
  return families.includes(archetype) ? archetype : "persistent";
}

/* ---------------------------------------------------------------------------
 * The four signature experiments.
 *
 * Each card states the question, the preset the question is asked of, and the single
 * metric that answers it. No card shows a result. The measured numbers exist — they are
 * in docs/EXPERIMENTS.md, produced by executed runs — but printing them here would put
 * someone else's outcome on a screen you have not run anything on yet, and a judge
 * cannot tell those apart. Where a finding has a caveat, the caveat travels with it.
 * ------------------------------------------------------------------------- */

interface Signature {
  id: string;
  title: string;
  question: string;
  needs: string[];
  decides: string;
  reads: string;
  how: string;
  route: string;
  routeLabel: string;
  caveat?: string;
}

const SIGNATURES: Signature[] = [
  {
    id: "recovery",
    title: "Recurrence recovery",
    question: "Does a returning environment get recognised, or relearned from scratch?",
    needs: ["recurring-environment"],
    decides: "Steps to recover after each change point",
    reads:
      "The scenario is A → B → A′: two splices, the second returning to the station the run started on. Recovery after the first change is the cost of meeting a novel environment; recovery after the second is the cost of meeting a familiar one. The gap between those two numbers is the whole experiment.",
    how: "Run the preset with MAG-NTS, then read the recovery table on the Timeline screen.",
    route: "/timeline",
    routeLabel: "Timeline",
    caveat:
      "The memory key is built from what the scheduler chose to observe, so it is confounded by the policy's own behaviour: phase A′ does not reliably retrieve phase A's prototype. Faster re-adaptation is measurable; attributing it to associative retrieval is not yet earned.",
  },
  {
    id: "shift",
    title: "Distribution shift",
    question: "When the band changes underneath a learned belief, what buys the recovery?",
    needs: ["sudden-shift"],
    decides: "Sustained detection probability, rung by rung",
    reads:
      "Two receivers with anti-correlated occupancy profiles are spliced mid-episode, so almost nothing learned before the splice applies after it. Running the ablation ladder here separates the components that recover coverage from the ones that merely look active.",
    how: "Run the ablation ladder on this preset — seven rungs, additive.",
    route: "/ablation",
    routeLabel: "Ablation Lab",
    caveat:
      "A policy with no beliefs has none to lose: round-robin recovers almost instantly here. That is not a win for round-robin, it is the price of learning anything at all, and the comparison table shows it plainly.",
  },
  {
    id: "efficiency",
    title: "Information efficiency",
    question: "How many bits does one observation buy, and does that survive a budget?",
    needs: ["easy-static", "extreme-budget"],
    decides: "Bits per observation, then reward under a cap",
    reads:
      "On a static band, efficiency is a fair fight and a systematic sweep is a strong contender. Under `extreme-budget`, where only a third of the steps are affordable, the same question becomes which policy spends a scarce observation best — a different problem with a different answer.",
    how: "Run the arena on both presets and compare bits per observation, then reward.",
    route: "/arena",
    routeLabel: "Algorithm Arena",
  },
  {
    id: "unseen",
    title: "Unseen generalisation",
    question: "Does the advantage hold on stations that tuning never saw?",
    needs: ["unseen-generalization"],
    decides: "Reward and SDP against NTS, with significance",
    reads:
      "Both stations in this preset are held out of tuning entirely — the weights were fitted on TRAIN and chosen on VALIDATION, and neither pool contains these receivers. It is the only test on this screen whose result cannot have leaked.",
    how: "Run the arena, then read the significance matrix. Both tests must reject.",
    route: "/analytics",
    routeLabel: "Analytics",
    caveat:
      "This is the experiment where MAG-NTS is known to lose on reward, significantly, against plain NTS. It stays in the suite for exactly that reason: an evaluation that only contains the scenarios a method wins is not an evaluation.",
  },
];

function SignatureExperiments({
  presets,
  unavailable,
}: {
  presets: ScenarioSpec[];
  unavailable: Set<string>;
}) {
  const patchLaunch = useSession((session) => session.patchLaunch);
  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {SIGNATURES.map((signature, index) => {
        const missing = signature.needs.filter((id) => unavailable.has(id));
        const known = signature.needs.filter((id) =>
          presets.some((preset) => preset.scenario_id === id),
        );
        return (
          <motion.div
            key={signature.id}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.06, duration: 0.28 }}
            className="panel lit flex flex-col gap-2.5 p-4"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <span className="eyebrow flex items-center gap-1.5">
                  <FlaskConical className="size-3 text-accent" />
                  experiment {index + 1}
                </span>
                <h3 className="mt-1 text-[13.5px] font-semibold text-ink">{signature.title}</h3>
              </div>
              {missing.length > 0 && <Badge tone="warn">{missing.length} preset missing</Badge>}
            </div>

            <p className="text-[11.5px] leading-relaxed text-ink-dim">{signature.question}</p>

            <div className="rounded-md border border-accent/25 bg-accent/[0.05] px-2.5 py-2">
              <span className="eyebrow text-accent">decided by</span>
              <p className="mono mt-0.5 text-[10.5px] text-ink-dim">{signature.decides}</p>
            </div>

            <p className="text-[10.5px] leading-relaxed text-muted">{signature.reads}</p>

            {signature.caveat && (
              <p className="border-l-2 border-warn/50 pl-2 text-[10px] leading-relaxed text-faint">
                {signature.caveat}
              </p>
            )}

            <div className="mt-auto flex flex-wrap items-center gap-1.5 border-t border-line pt-2.5">
              {known.map((id) => (
                <Button
                  key={id}
                  size="sm"
                  variant="subtle"
                  disabled={unavailable.has(id)}
                  onClick={() => patchLaunch({ scenarioId: id })}
                >
                  load {id}
                </Button>
              ))}
              <Link to={signature.route} className="ml-auto">
                <Button size="sm" variant="ghost">
                  {signature.routeLabel} →
                </Button>
              </Link>
            </div>
            <p className="mono text-[9px] leading-relaxed text-faint">{signature.how}</p>
          </motion.div>
        );
      })}
    </div>
  );
}
