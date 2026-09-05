/** The single place this app talks to the backend.
 *
 * Two rules hold everywhere below.
 *
 * *One origin.*  Both `vite.config.ts` (dev) and `nginx.conf` (prod) proxy `/api` to the
 * FastAPI service, so the base is a path and never a host. Nothing here reads a URL from
 * the environment, which means no API host can leak into the bundle.
 *
 * *Errors carry the server's words.*  FastAPI answers a 422 or 503 with a `detail` that a
 * user can act on ("the offline cache is empty", "scenario unsatisfiable"). Throwing a
 * bare "Request failed" would discard exactly the sentence worth showing, so `ApiError`
 * keeps `detail` and the UI renders it.
 */

import type {
  ActiveResponse,
  AnalyticsResponse,
  BatchRequest,
  DatasetsResponse,
  EpisodeRequest,
  ExperimentDetail,
  FramesResponse,
  HistoryResponse,
  Recording,
  ReportCreated,
  ReportRequest,
  ReportsResponse,
  ScenarioDetail,
  ScenarioRequest,
  ScenarioSpec,
  ScenariosResponse,
  SchedulersResponse,
  SpectrogramResponse,
  StartResponse,
  StatusResponse,
  WindowsResponse,
} from "./types";

/** Where the API lives, as a *path*.
 *
 * The Dockerfile bakes VITE_API_BASE at build time, but a host is refused on purpose: a
 * host here would put an API origin into the shipped bundle and break the single-origin
 * guarantee nginx.conf provides (no CORS preflight, and the WebSocket upgrade survives).
 * So an absolute URL falls back to the default rather than being honoured.
 */
function resolveApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE?.trim();
  if (!configured) return "/api";
  if (!configured.startsWith("/")) {
    console.warn(`VITE_API_BASE must be a path, not a host — ignoring "${configured}"`);
    return "/api";
  }
  return configured.replace(/\/+$/, "") || "/api";
}

export const API_BASE = resolveApiBase();

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly url: string,
  ) {
    super(detail || `HTTP ${status}`);
    this.name = "ApiError";
  }

  /** 503 means the cache or index is missing — recoverable by running a script. */
  get isDataMissing(): boolean {
    return this.status === 503;
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

function url(path: string, query?: Query): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined) search.set(key, String(value));
  }
  const suffix = search.toString();
  return `${API_BASE}${path}${suffix ? `?${suffix}` : ""}`;
}

async function request<T>(path: string, init?: RequestInit & { query?: Query }): Promise<T> {
  const { query, ...rest } = init ?? {};
  const target = url(path, query);
  let response: Response;
  try {
    response = await fetch(target, {
      ...rest,
      headers: {
        Accept: "application/json",
        ...(rest.body ? { "Content-Type": "application/json" } : {}),
        ...rest.headers,
      },
    });
  } catch (cause) {
    // A dead API is the single most likely failure in a demo; name it plainly instead of
    // surfacing the browser's "Failed to fetch".
    throw new ApiError(0, "cannot reach the AAMS-X API — is `make api` running?", target);
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") detail = body.detail;
      else if (body.detail) detail = JSON.stringify(body.detail);
    } catch {
      /* a non-JSON error body is still an error; keep the status line */
    }
    throw new ApiError(response.status, detail, target);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const post = <T>(path: string, body?: unknown, query?: Query) =>
  request<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    query,
  });

// ---- system ----------------------------------------------------------------

export const getStatus = () => request<StatusResponse>("/status");
export const getSchedulers = () => request<SchedulersResponse>("/schedulers");

// ---- scenarios -------------------------------------------------------------

export const getScenarios = () => request<ScenariosResponse>("/scenarios");
export const getScenario = (scenarioId: string) =>
  request<ScenarioDetail>(`/scenarios/${encodeURIComponent(scenarioId)}`);
export const sampleScenario = (family: string, seed = 0, unseen = false) =>
  post<ScenarioSpec>("/scenarios/sample", undefined, { family, seed, unseen });
export const validateScenario = (scenario: ScenarioRequest) =>
  post<ScenarioDetail>("/scenarios/validate", scenario);

// ---- datasets --------------------------------------------------------------

export const getDatasets = () => request<DatasetsResponse>("/datasets");
export const getRecording = (recordingId: string) =>
  request<Recording>(`/datasets/${recordingId}`);
export const getSpectrogram = (
  recordingId: string,
  query: {
    start_step?: number;
    n_steps?: number;
    n_regions?: number;
    time_bin?: number;
    freq_min_mhz?: number;
    freq_max_mhz?: number;
  } = {},
) => request<SpectrogramResponse>(`/datasets/${recordingId}/spectrogram`, { query });
export const getAnalytics = (
  recordingId: string,
  query: { start_step?: number; n_steps?: number; n_regions?: number; time_bin?: number } = {},
) => request<AnalyticsResponse>(`/datasets/${recordingId}/analytics`, { query });
export const queryWindows = (
  query: { where?: string; order_by?: string; limit?: number } = {},
) => request<WindowsResponse>("/datasets/index/windows", { query });

// ---- experiments -----------------------------------------------------------

export const startEpisode = (body: EpisodeRequest) => post<StartResponse>("/experiments", body);
export const startArena = (body: BatchRequest) => post<StartResponse>("/experiments/arena", body);
export const startAblation = (body: BatchRequest) =>
  post<StartResponse>("/experiments/ablation", body);
export const getActive = () => request<ActiveResponse>("/experiments/active");
export const getHistory = (query: { limit?: number; kind?: string } = {}) =>
  request<HistoryResponse>("/experiments/history", { query });
export const getExperiment = (experimentId: string) =>
  request<ExperimentDetail>(`/experiments/${experimentId}`);
export const getFrames = (experimentId: string, query: { start?: number; limit?: number } = {}) =>
  request<FramesResponse>(`/experiments/${experimentId}/frames`, { query });
export const cancelExperiment = (experimentId: string) =>
  post<{ experiment_id: string; status: string }>(`/experiments/${experimentId}/cancel`);
export const replayExperiment = (experimentId: string, paceHz = 30) =>
  post<StartResponse>(`/experiments/${experimentId}/replay`, undefined, { pace_hz: paceHz });

// ---- reports ---------------------------------------------------------------

export const createReport = (body: ReportRequest) => post<ReportCreated>("/reports", body);
export const getReports = () => request<ReportsResponse>("/reports");
export const reportUrl = (name: string) => `${API_BASE}/reports/${encodeURIComponent(name)}`;

/** Absolute ws:// or wss:// URL for one experiment's stream, matching the page's scheme. */
export function streamUrl(experimentId: string): string {
  const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${window.location.host}${API_BASE}/experiments/${experimentId}/stream`;
}
