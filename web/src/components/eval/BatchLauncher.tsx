/** Start (or re-open) a multi-seed batch: the arena and the ablation ladder both need it.
 *
 * The two differ in exactly one place — the arena picks which policies race, the ladder
 * always races MAG-NTS against itself with one component removed — so the control set is
 * shared and the scheduler picker is conditional. Seeds are a count, not a list, because
 * the server derives `seed = 0..n-1` for every arm: identical seeds across arms is the
 * whole point of the comparison and letting the browser choose them would break it.
 */

import { Play, Square } from "lucide-react";
import { useState } from "react";

import {
  useCancelExperiment,
  useHistory,
  useSchedulers,
  useScenarios,
  useStartAblation,
  useStartArena,
} from "@/api/queries";
import type { BatchRequest } from "@/api/types";
import {
  Badge,
  Button,
  Field,
  NumberInput,
  ProgressBar,
  Select,
} from "@/components/ui";
import { cn } from "@/lib/cn";
import { int, isoClock, policyLabel } from "@/lib/format";
import { policyColor } from "@/lib/palette";
import { useSession } from "@/state/session";
import type { BatchView } from "./useBatchResult";

/** Seeds per arm. Two is not a statistic; the significance tests need a handful. */
const SEED_CHOICES = [3, 5, 8, 12, 20];

export function BatchLauncher({
  kind,
  view,
}: {
  kind: "arena" | "ablation";
  view: BatchView;
}) {
  const scenarios = useScenarios();
  const schedulers = useSchedulers();
  const arena = useStartArena();
  const ablation = useStartAblation();
  const cancel = useCancelExperiment();
  const history = useHistory({ kind, limit: 12 });
  const batchId = useSession((state) => state.batchId);
  const setBatchId = useSession((state) => state.setBatchId);

  const presets = scenarios.data?.presets ?? [];
  const unavailable = new Set(scenarios.data?.unavailable ?? []);
  const buildable = presets.filter(
    (preset) => !unavailable.has(preset.scenario_id),
  );

  const [scenarioId, setScenarioId] = useState("");
  const [seeds, setSeeds] = useState(5);
  const [picked, setPicked] = useState<string[] | null>(null);

  const order = schedulers.data?.arena_order ?? [];
  const chosen = picked ?? order;
  const scenario =
    presets.find((preset) => preset.scenario_id === scenarioId) ?? buildable[0];
  const start = kind === "arena" ? arena : ablation;
  const pending = start.isPending;

  const launch = () => {
    const target = scenarioId || buildable[0]?.scenario_id;
    if (!target) return;
    const body: BatchRequest = { scenario_id: target, seeds };
    if (kind === "arena") body.schedulers = chosen;
    start.mutate(body, {
      onSuccess: (response) => setBatchId(response.experiment_id),
    });
  };

  const jobs = seeds * (kind === "arena" ? chosen.length : 7);

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="Scenario"
          className="col-span-2"
          hint={
            scenario
              ? `${scenario.split} split · ${int(scenario.horizon)} steps · ${scenario.family}`
              : "no preset the current cache can build"
          }
        >
          <Select
            value={scenario?.scenario_id ?? ""}
            onChange={setScenarioId}
            disabled={!buildable.length}
            options={presets.map((preset) => ({
              value: preset.scenario_id,
              label: `${preset.name}${unavailable.has(preset.scenario_id) ? " · not cached" : ""}`,
              disabled: unavailable.has(preset.scenario_id),
            }))}
          />
        </Field>
        <Field
          label="Seeds per arm"
          hint="the same seeds are given to every arm"
        >
          <Select
            value={String(seeds)}
            onChange={(value) => setSeeds(Number(value))}
            options={SEED_CHOICES.map((count) => ({
              value: String(count),
              label: `${count} seeds`,
            }))}
          />
        </Field>
        <Field
          label="Episodes"
          hint={`${kind === "arena" ? chosen.length : 7} arms × ${seeds}`}
        >
          <NumberInput value={jobs} onChange={() => undefined} disabled />
        </Field>
      </div>

      {kind === "arena" && (
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">Policies in the race</span>
          <div className="flex flex-wrap gap-1.5">
            {order.map((name) => {
              const on = chosen.includes(name);
              return (
                <button
                  key={name}
                  type="button"
                  onClick={() =>
                    setPicked(
                      on
                        ? chosen.filter((entry) => entry !== name)
                        : order.filter(
                            (entry) => chosen.includes(entry) || entry === name,
                          ),
                    )
                  }
                  className={cn(
                    "mono rounded-md border px-2 py-1 text-[10.5px] transition-colors",
                    on
                      ? "text-ink"
                      : "border-line bg-void text-faint hover:border-line-bright",
                  )}
                  style={
                    on
                      ? {
                          borderColor: policyColor(name),
                          background: `${policyColor(name)}1a`,
                        }
                      : undefined
                  }
                >
                  {policyLabel(name)}
                </button>
              );
            })}
          </div>
          <p className="text-[10px] leading-snug text-faint">
            MAG-NTS is the proposal; the rest are the baselines it has to beat
            on the same recordings, the same seeds and the same budget.
          </p>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          icon={<Play className="size-3.5" />}
          onClick={launch}
          disabled={
            pending ||
            view.running ||
            !buildable.length ||
            (kind === "arena" && !chosen.length)
          }
          className="flex-1"
        >
          {pending
            ? "Queuing…"
            : view.running
              ? "Running…"
              : `Run ${jobs} episodes`}
        </Button>
        {view.running && batchId && (
          <Button
            icon={<Square className="size-3.5" />}
            onClick={() => cancel.mutate(batchId)}
            disabled={cancel.isPending}
          >
            Stop
          </Button>
        )}
      </div>

      {start.error && (
        <p className="text-[11px] leading-snug text-bad">
          {start.error instanceof Error
            ? start.error.message
            : "the launch was refused"}
        </p>
      )}

      {view.running && (
        <div className="flex flex-col gap-1.5">
          <div className="mono flex justify-between text-[10px] text-faint">
            <span>
              {view.progress
                ? `${view.progress.done} / ${view.progress.total} episodes`
                : "queued"}
            </span>
            <span>{view.status}</span>
          </div>
          <ProgressBar
            value={
              view.progress && view.progress.total
                ? view.progress.done / view.progress.total
                : 0
            }
            showSweep
          />
          <p className="text-[10px] leading-snug text-faint">
            Every episode replays cached recordings end to end, so a
            twenty-episode batch takes as long as twenty episodes. Nothing is
            extrapolated from a shorter run.
          </p>
        </div>
      )}

      <div className="flex flex-col gap-1.5 border-t border-line pt-2.5">
        <span className="eyebrow">Earlier batches</span>
        {(history.data?.experiments ?? []).length === 0 ? (
          <p className="text-[10px] text-faint">
            none yet — a finished batch stays readable here for the rest of the
            cache's life
          </p>
        ) : (
          <div className="flex max-h-40 flex-col gap-1 overflow-y-auto">
            {(history.data?.experiments ?? []).map((record) => (
              <button
                key={record.experiment_id}
                type="button"
                onClick={() => setBatchId(record.experiment_id)}
                className={cn(
                  "mono flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-left text-[10px] transition-colors",
                  record.experiment_id === batchId
                    ? "border-accent/45 bg-accent/8 text-ink"
                    : "border-line bg-void text-muted hover:border-line-bright",
                )}
              >
                <span className="truncate">{record.scenario_id}</span>
                <span className="flex shrink-0 items-center gap-1.5 text-faint">
                  {isoClock(record.created_at)}
                  {record.status !== "completed" && (
                    <Badge tone="warn">{record.status}</Badge>
                  )}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
