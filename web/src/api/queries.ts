/** TanStack Query bindings.
 *
 * The stale times below are chosen from how fast each thing can actually change: the
 * cached recordings and the mined presets only move when someone runs an ingestion
 * script, so they are effectively static for a session; `/status` carries live experiment
 * counts and is polled; the window index is a query and is keyed by its own arguments.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import * as api from "./client";
import type {
  BatchRequest,
  EpisodeRequest,
  ReportRequest,
  ScenarioRequest,
} from "./types";

/** One namespace so an invalidation cannot miss a key by typo. */
export const keys = {
  status: ["status"] as const,
  schedulers: ["schedulers"] as const,
  scenarios: ["scenarios"] as const,
  scenario: (id: string) => ["scenario", id] as const,
  datasets: ["datasets"] as const,
  recording: (id: string) => ["recording", id] as const,
  spectrogram: (id: string, query: object) => ["spectrogram", id, query] as const,
  analytics: (id: string, query: object) => ["analytics", id, query] as const,
  windows: (query: object) => ["windows", query] as const,
  active: ["experiments", "active"] as const,
  history: (query: object) => ["experiments", "history", query] as const,
  experiment: (id: string) => ["experiments", id] as const,
  reports: ["reports"] as const,
};

const MINUTE = 60_000;

/** Cache-derived data: only an ingestion run changes it, so do not re-fetch on focus. */
const STATIC = { staleTime: 30 * MINUTE, refetchOnWindowFocus: false } as const;

export function useStatus(pollMs = 15_000) {
  return useQuery({
    queryKey: keys.status,
    queryFn: api.getStatus,
    refetchInterval: pollMs,
    staleTime: 5_000,
  });
}

export const useSchedulers = () =>
  useQuery({ queryKey: keys.schedulers, queryFn: api.getSchedulers, ...STATIC });

export const useScenarios = () =>
  useQuery({ queryKey: keys.scenarios, queryFn: api.getScenarios, ...STATIC });

export const useScenario = (id: string | null) =>
  useQuery({
    queryKey: keys.scenario(id ?? ""),
    queryFn: () => api.getScenario(id as string),
    enabled: Boolean(id),
    ...STATIC,
  });

export const useDatasets = () =>
  useQuery({ queryKey: keys.datasets, queryFn: api.getDatasets, ...STATIC });

export const useRecording = (id: string | null) =>
  useQuery({
    queryKey: keys.recording(id ?? ""),
    queryFn: () => api.getRecording(id as string),
    enabled: Boolean(id),
    ...STATIC,
  });

type SpectrogramQuery = Parameters<typeof api.getSpectrogram>[1];

export const useSpectrogram = (id: string | null, query: SpectrogramQuery = {}) =>
  useQuery({
    queryKey: keys.spectrogram(id ?? "", query ?? {}),
    queryFn: () => api.getSpectrogram(id as string, query),
    enabled: Boolean(id),
    ...STATIC,
  });

type AnalyticsQuery = Parameters<typeof api.getAnalytics>[1];

export const useAnalytics = (id: string | null, query: AnalyticsQuery = {}) =>
  useQuery({
    queryKey: keys.analytics(id ?? "", query ?? {}),
    queryFn: () => api.getAnalytics(id as string, query),
    enabled: Boolean(id),
    ...STATIC,
  });

type WindowQuery = Parameters<typeof api.queryWindows>[0];

export const useWindows = (query: WindowQuery = {}, enabled = true) =>
  useQuery({
    queryKey: keys.windows(query ?? {}),
    queryFn: () => api.queryWindows(query),
    enabled,
    ...STATIC,
  });

/** Poll only while something is running; an idle console should be silent on the wire. */
export function useActive(pollMs = 4_000) {
  return useQuery({
    queryKey: keys.active,
    queryFn: api.getActive,
    refetchInterval: (query) => (query.state.data?.active.length ? pollMs : pollMs * 3),
  });
}

export const useHistory = (query: { limit?: number; kind?: string } = {}) =>
  useQuery({ queryKey: keys.history(query), queryFn: () => api.getHistory(query) });

export function useExperiment(
  id: string | null,
  options?: Partial<UseQueryOptions<Awaited<ReturnType<typeof api.getExperiment>>>>,
) {
  return useQuery({
    queryKey: keys.experiment(id ?? ""),
    queryFn: () => api.getExperiment(id as string),
    enabled: Boolean(id),
    ...options,
  });
}

export const useReports = () =>
  useQuery({ queryKey: keys.reports, queryFn: api.getReports, staleTime: MINUTE });

// ---- mutations -------------------------------------------------------------

/** Every launch invalidates the same three things, so they share one helper. */
function useLaunchInvalidation() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: keys.active });
    void client.invalidateQueries({ queryKey: ["experiments", "history"] });
    void client.invalidateQueries({ queryKey: keys.status });
  };
}

export function useStartEpisode() {
  const invalidate = useLaunchInvalidation();
  return useMutation({
    mutationFn: (body: EpisodeRequest) => api.startEpisode(body),
    onSuccess: invalidate,
  });
}

export function useStartArena() {
  const invalidate = useLaunchInvalidation();
  return useMutation({
    mutationFn: (body: BatchRequest) => api.startArena(body),
    onSuccess: invalidate,
  });
}

export function useStartAblation() {
  const invalidate = useLaunchInvalidation();
  return useMutation({
    mutationFn: (body: BatchRequest) => api.startAblation(body),
    onSuccess: invalidate,
  });
}

export function useCancelExperiment() {
  const invalidate = useLaunchInvalidation();
  return useMutation({ mutationFn: api.cancelExperiment, onSuccess: invalidate });
}

/** Replay genuinely re-runs from the stored config; it does not replay a cached picture. */
export function useReplayExperiment() {
  const invalidate = useLaunchInvalidation();
  return useMutation({
    mutationFn: ({ id, paceHz }: { id: string; paceHz?: number }) =>
      api.replayExperiment(id, paceHz),
    onSuccess: invalidate,
  });
}

export function useValidateScenario() {
  return useMutation({ mutationFn: (scenario: ScenarioRequest) => api.validateScenario(scenario) });
}

export function useCreateReport() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ReportRequest) => api.createReport(body),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.reports }),
  });
}
