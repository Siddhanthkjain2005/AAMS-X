/** Console state that outlives a screen.
 *
 * Deliberately small. Anything the server can answer for lives in TanStack Query, and
 * anything arriving at 60 Hz lives in the frame ring — this store holds only the choices
 * a person made: which run we are watching, where the scrub cursor is, and how the next
 * launch is configured. Those choices must survive navigating between the twelve screens,
 * which is the one thing neither of the other two layers can do.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

import type { AblationFlags, MagWeights, SchedulerName } from "@/api/types";

/** The tuned defaults from data/index/mag_nts_tuning.json — TRAIN only, never validation. */
export const DEFAULT_MAG_WEIGHTS: MagWeights = {
  detection: 0.94,
  information: 0.07,
  memory: 0.57,
  periodicity: 0.27,
  uncertainty: 0.23,
  recency: 0.17,
  cost: 0.29,
  switching: 0.1,
};

export const FULL_ABLATION: AblationFlags = {
  memory: true,
  information_gain: true,
  change_detection: true,
  periodicity: true,
  temporal_encoder: true,
  uncertainty_exploration: true,
  neural_encoder: false,
};

export interface LaunchConfig {
  scenarioId: string;
  scheduler: SchedulerName | string;
  seed: number;
  paceHz: number;
  frameStride: number;
  ablation: AblationFlags;
  magWeights: MagWeights;
}

interface SessionState {
  /** The run every explain-screen reads from. Set by a launch, a replay or a click. */
  experimentId: string | null;
  /** null = follow the live edge; a number = frozen at that frame index for inspection. */
  cursor: number | null;
  launch: LaunchConfig;
  /** Arena / ablation batch the evaluate-screens are showing. */
  batchId: string | null;
  reportSelection: string[];

  setExperimentId: (id: string | null) => void;
  setCursor: (cursor: number | null) => void;
  setBatchId: (id: string | null) => void;
  patchLaunch: (patch: Partial<LaunchConfig>) => void;
  patchAblation: (patch: Partial<AblationFlags>) => void;
  patchMagWeights: (patch: Partial<MagWeights>) => void;
  resetWeights: () => void;
  toggleReportSelection: (id: string) => void;
  clearReportSelection: () => void;
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      experimentId: null,
      cursor: null,
      batchId: null,
      reportSelection: [],
      launch: {
        scenarioId: "",
        scheduler: "mag-nts",
        seed: 0,
        paceHz: 30,
        frameStride: 1,
        ablation: { ...FULL_ABLATION },
        magWeights: { ...DEFAULT_MAG_WEIGHTS },
      },

      setExperimentId: (experimentId) => set({ experimentId, cursor: null }),
      setCursor: (cursor) => set({ cursor }),
      setBatchId: (batchId) => set({ batchId }),
      patchLaunch: (patch) => set((state) => ({ launch: { ...state.launch, ...patch } })),
      patchAblation: (patch) =>
        set((state) => ({
          launch: { ...state.launch, ablation: { ...state.launch.ablation, ...patch } },
        })),
      patchMagWeights: (patch) =>
        set((state) => ({
          launch: { ...state.launch, magWeights: { ...state.launch.magWeights, ...patch } },
        })),
      resetWeights: () =>
        set((state) => ({
          launch: {
            ...state.launch,
            magWeights: { ...DEFAULT_MAG_WEIGHTS },
            ablation: { ...FULL_ABLATION },
          },
        })),
      toggleReportSelection: (id) =>
        set((state) => ({
          reportSelection: state.reportSelection.includes(id)
            ? state.reportSelection.filter((entry) => entry !== id)
            : [...state.reportSelection, id].slice(-24),
        })),
      clearReportSelection: () => set({ reportSelection: [] }),
    }),
    {
      name: "aamsx.session",
      version: 1,
      // Only the launch configuration is worth remembering across reloads. Persisting an
      // experiment id would resurrect a dead session id on the next page load and the
      // socket would 404 for a run the server no longer holds.
      partialize: (state) => ({ launch: state.launch }),
    },
  ),
);

/** Do the flags describe the complete policy? Drives the "ablated" warning badge. */
export function isFullPolicy(flags: AblationFlags): boolean {
  return (
    flags.memory &&
    flags.information_gain &&
    flags.change_detection &&
    flags.periodicity &&
    flags.temporal_encoder &&
    flags.uncertainty_exploration
  );
}

export function disabledComponents(flags: AblationFlags): string[] {
  const labels: [keyof AblationFlags, string][] = [
    ["memory", "memory"],
    ["information_gain", "information gain"],
    ["change_detection", "change detection"],
    ["periodicity", "periodicity"],
    ["temporal_encoder", "temporal encoder"],
    ["uncertainty_exploration", "uncertainty exploration"],
  ];
  return labels.filter(([key]) => !flags[key]).map(([, label]) => label);
}
