/** Start a run.
 *
 * Everything the scheduler will be given is on this panel, including the eight MAG-NTS
 * weights — the brief calls for them exposed rather than buried in a config file, and an
 * ablated policy has to be visibly ablated before anyone reads its numbers. Presets the
 * current cache cannot build are listed and disabled rather than hidden, so a missing
 * recording looks like a missing recording.
 */

import { AnimatePresence, motion } from "framer-motion";
import { ChevronRight, RotateCcw, Zap } from "lucide-react";
import { useEffect, useState } from "react";

import { useSchedulers, useScenarios, useStartEpisode } from "@/api/queries";
import { FACTOR_TERMS, type MagWeights } from "@/api/types";
import { Badge, Button, Field, NumberInput, Select, Slider, Toggle } from "@/components/ui";
import { cn } from "@/lib/cn";
import { policyLabel } from "@/lib/format";
import { FACTOR_COLORS } from "@/lib/palette";
import { disabledComponents, isFullPolicy, useSession } from "@/state/session";

const ABLATION_HINTS: { key: keyof MagWeights | string; label: string; hint: string }[] = [
  { key: "memory", label: "Associative memory", hint: "Hopfield recall over contexts" },
  { key: "information_gain", label: "Information gain", hint: "H(b) − E[H(b′)|a]" },
  { key: "change_detection", label: "Change detection", hint: "Page-Hinkley + EWMA" },
  { key: "periodicity", label: "Periodicity", hint: "mined real cycles" },
  { key: "temporal_encoder", label: "Temporal encoder", hint: "context features" },
  { key: "uncertainty_exploration", label: "Uncertainty exploration", hint: "entropy bonus" },
];

export function LaunchPanel({ compact = false }: { compact?: boolean }) {
  const scenarios = useScenarios();
  const schedulers = useSchedulers();
  const start = useStartEpisode();
  const launch = useSession((state) => state.launch);
  const patchLaunch = useSession((state) => state.patchLaunch);
  const patchAblation = useSession((state) => state.patchAblation);
  const patchMagWeights = useSession((state) => state.patchMagWeights);
  const resetWeights = useSession((state) => state.resetWeights);
  const setExperimentId = useSession((state) => state.setExperimentId);
  const [showAdvanced, setShowAdvanced] = useState(false);

  const presets = scenarios.data?.presets ?? [];
  const unavailable = new Set(scenarios.data?.unavailable ?? []);

  // Default to the first buildable preset rather than leaving the field empty: an empty
  // scenario id would post a request the server has to reject.
  useEffect(() => {
    if (launch.scenarioId || !presets.length) return;
    const first = presets.find((preset) => !unavailable.has(preset.scenario_id));
    if (first) patchLaunch({ scenarioId: first.scenario_id });
  }, [launch.scenarioId, presets, unavailable, patchLaunch]);

  const scenario = presets.find((preset) => preset.scenario_id === launch.scenarioId);
  const ablated = !isFullPolicy(launch.ablation);
  const isMag = launch.scheduler === "mag-nts";
  const missing = disabledComponents(launch.ablation);

  const launchRun = () => {
    if (!launch.scenarioId) return;
    start.mutate(
      {
        scenario_id: launch.scenarioId,
        scheduler: launch.scheduler,
        seed: launch.seed,
        pace_hz: launch.paceHz,
        frame_stride: launch.frameStride,
        ablation: launch.ablation,
        mag_weights: isMag ? launch.magWeights : null,
      },
      { onSuccess: (started) => setExperimentId(started.experiment_id) },
    );
  };

  return (
    <div className="flex flex-col gap-3">
      <div className={cn("grid gap-3", compact ? "grid-cols-2" : "grid-cols-1")}>
        <Field
          label="Scenario"
          hint={
            scenario
              ? `${scenario.family} · ${scenario.horizon} steps · ${scenario.n_regions} regions · budget ${scenario.effective_budget}`
              : "presets are mined from the cached recordings"
          }
          className={compact ? "col-span-2" : undefined}
        >
          <Select
            value={launch.scenarioId}
            onChange={(scenarioId) => patchLaunch({ scenarioId })}
            options={presets.map((preset) => ({
              value: preset.scenario_id,
              label: `${preset.name}${unavailable.has(preset.scenario_id) ? " — not in cache" : ""}`,
              disabled: unavailable.has(preset.scenario_id),
            }))}
            disabled={!presets.length}
          />
        </Field>

        <Field label="Scheduler" hint={isMag ? "the proposed policy" : "baseline"}>
          <Select
            value={String(launch.scheduler)}
            onChange={(scheduler) => patchLaunch({ scheduler })}
            options={(schedulers.data?.schedulers ?? []).map((entry) => ({
              value: entry.name,
              label: policyLabel(entry.name),
            }))}
          />
        </Field>

        <Field label="Seed" hint="same seed, same run">
          <NumberInput
            value={launch.seed}
            onChange={(seed) => patchLaunch({ seed })}
            min={0}
            max={9999}
          />
        </Field>

        {!compact && (
          <>
            <Field label="Pace" hint="frames per second, 0 = as fast as it runs">
              <NumberInput
                value={launch.paceHz}
                onChange={(paceHz) => patchLaunch({ paceHz })}
                min={0}
                max={2000}
              />
            </Field>
            <Field label="Frame stride" hint="send every nth frame on long horizons">
              <NumberInput
                value={launch.frameStride}
                onChange={(frameStride) => patchLaunch({ frameStride })}
                min={1}
                max={100}
              />
            </Field>
          </>
        )}
      </div>

      {scenario && (
        <div className="flex flex-wrap items-center gap-1.5">
          <Badge tone={scenario.split === "unseen" ? "mag" : scenario.split === "validation" ? "signal" : "neutral"}>
            {scenario.split}
          </Badge>
          {scenario.change_points.length > 0 && (
            <Badge tone="warn">{scenario.change_points.length} change points</Badge>
          )}
          <Badge>
            {scenario.segments.length} segment{scenario.segments.length === 1 ? "" : "s"}
          </Badge>
          {scenario.tags.slice(0, 3).map((tag) => (
            <Badge key={tag}>{tag}</Badge>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2">
        <Button
          variant="primary"
          size={compact ? "md" : "lg"}
          icon={<Zap className="size-4" />}
          disabled={!launch.scenarioId || start.isPending}
          onClick={launchRun}
          className="flex-1"
        >
          {start.isPending ? "Starting…" : "Run episode"}
        </Button>
        <Button
          size={compact ? "md" : "lg"}
          onClick={() => setShowAdvanced((prior) => !prior)}
          icon={
            <ChevronRight
              className={cn("size-4 transition-transform", showAdvanced && "rotate-90")}
            />
          }
        >
          Policy
        </Button>
      </div>

      {ablated && (
        <p className="rounded-md border border-warn/30 bg-warn/[0.07] px-2.5 py-2 text-[11px] leading-relaxed text-warn">
          Ablated policy: {missing.join(", ")} disabled. Results from this run are not
          comparable with the published MAG-NTS numbers.
        </p>
      )}

      {start.isError && (
        <p className="mono rounded-md border border-bad/30 bg-bad/[0.07] px-2.5 py-2 text-[11px] leading-relaxed text-bad">
          {start.error instanceof Error ? start.error.message : "could not start the run"}
        </p>
      )}

      <AnimatePresence initial={false}>
        {showAdvanced && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="overflow-hidden"
          >
            <div className="flex flex-col gap-3 border-t border-line pt-3">
              <div>
                <p className="eyebrow mb-1.5">Components</p>
                <div className="grid grid-cols-2 gap-1.5">
                  {ABLATION_HINTS.map((entry) => (
                    <Toggle
                      key={entry.key}
                      label={entry.label}
                      hint={entry.hint}
                      checked={Boolean(launch.ablation[entry.key as keyof typeof launch.ablation])}
                      onChange={(checked) => patchAblation({ [entry.key]: checked })}
                    />
                  ))}
                </div>
              </div>

              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <p className="eyebrow">MAG-NTS weights</p>
                  <Button
                    size="sm"
                    variant="subtle"
                    icon={<RotateCcw className="size-3" />}
                    onClick={resetWeights}
                  >
                    Tuned defaults
                  </Button>
                </div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                  {FACTOR_TERMS.map((term) => (
                    <Slider
                      key={term}
                      label={term}
                      value={launch.magWeights[term]}
                      onChange={(value) => patchMagWeights({ [term]: value })}
                      min={0}
                      max={1.5}
                      colour={FACTOR_COLORS[term]}
                      disabled={!isMag}
                    />
                  ))}
                </div>
                {!isMag && (
                  <p className="mt-1.5 text-[10px] text-faint">
                    Weights apply to MAG-NTS only; {policyLabel(String(launch.scheduler))} ignores
                    them.
                  </p>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
