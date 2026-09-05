/** Wire types for the AAMS-X API.
 *
 * These mirror `aamsx/api/schemas.py` (requests) and the payloads built by
 * `aamsx/experiments/runner.py::_frame`, `EpisodeResult.to_dict` and
 * `BatchResult.to_dict` (responses). They are hand-written rather than generated so the
 * comments explaining *what a field means* live next to the field; where a name here
 * differs from the Python one it is a bug, not a translation.
 */

// ---- shared ----------------------------------------------------------------

/** Which data split a scenario draws from. Enforced server-side; see docs/DATA.md. */
export type Split = "train" | "validation" | "unseen";

export type SchedulerName =
  | "round-robin"
  | "random"
  | "ucb"
  | "thompson"
  | "nts"
  | "mag-nts"
  | "dqn"
  | "sac";

/** One aggregate over seeds. `ci_low`/`ci_high` are Student-t at 95%, not normal. */
export interface Aggregate {
  metric: string;
  n: number;
  mean: number;
  std: number;
  sem: number;
  ci_low: number;
  ci_high: number;
  median: number;
  minimum: number;
  maximum: number;
  values?: number[];
}

/**
 * One significance test. `significant` is the conjunction of both tests at alpha = 0.05
 * — never Welch alone. See docs/EXPERIMENTS.md section 1.
 */
export interface Comparison {
  metric: string;
  treatment: string;
  control: string;
  n_treatment: number;
  n_control: number;
  difference: number;
  relative: number;
  welch_t: number;
  welch_p: number;
  mannwhitney_u: number;
  mannwhitney_p: number;
  cohens_d: number;
  significant: boolean;
}

// ---- provenance and real data ----------------------------------------------

/**
 * Where a number came from. Attached to every dataset response so a panel can be
 * labelled honestly instead of letting the reader assume. `derived-label` means the
 * occupancy mask AAMS-X computed from the measurement, not something the archive shipped.
 */
export type DataKind = "measured" | "derived-label" | "model-inferred";

/** `aamsx/contracts/spectrum.py::Provenance.to_dict`. `is_synthetic` is always false. */
export interface Provenance {
  adapter: string;
  source_id: string;
  source_url: string;
  retrieved_at: string;
  observed_from: string;
  observed_to: string;
  n_source_files: number;
  n_samples: number;
  freq_resolution_khz: number;
  time_resolution_sec: number;
  preprocessing: string[];
  license: string;
  reference: string;
  checksum: string;
  is_synthetic: boolean;
  notes: string;
  /** Archive gaps as `[start_step, stop_step]` — real recordings are not continuous. */
  gaps: number[][];
}

/** The frequency partition. `centre_mhz[r]` labels region `r` throughout the UI. */
export interface RegionGrid {
  n_regions: number;
  n_channels: number;
  edges_mhz: number[];
  centre_mhz: number[];
  width_mhz: number[];
  counts: number[];
}

/** `aamsx/environment/characterize.py::Characterisation.to_dict`. */
export interface Characterisation {
  n_steps: number;
  n_regions: number;
  occupancy: number;
  persistence: number;
  onset_rate: number;
  burstiness: number;
  intermittent_regions: number;
  persistent_regions: number;
  quiet_regions: number;
  period_steps: number;
  period_strength: number;
  concentration: number;
  profile_drift: number;
  mean_margin_db: number;
  p95_margin_db: number;
  archetype: string;
  per_region_occupancy: number[];
}

export interface Recording {
  recording_id: string;
  station: string;
  day: string;
  n_times: number;
  n_channels: number;
  cadence_sec: number;
  epoch_utc: string;
  duration_sec: number;
  freq_min_mhz: number;
  freq_max_mhz: number;
  occupancy: number;
  live_channels: number;
  dead_channels: number;
  provenance: Provenance;
  calibration: Record<string, unknown>;
  station_meta: StationMeta | null;
  role?: string;
  kind?: DataKind;
}

export interface StationMeta {
  name: string;
  country: string;
  role: string;
  freq_min_mhz: number;
  freq_max_mhz: number;
  cadence_sec: number;
  notes?: string;
  [key: string]: unknown;
}

export interface AdapterStatus {
  name: string;
  status: string;
  detail: string;
  verified?: boolean;
  credentials_configured?: boolean;
}

export interface DatasetsResponse {
  data_mode: string;
  adapters: AdapterStatus[];
  recordings: Recording[];
  catalogue: StationMeta[];
}

/** `GET /api/datasets/{station}/{day}/spectrogram` — the Real Spectrum Replay waterfall. */
export interface SpectrogramResponse {
  recording_id: string;
  kind: DataKind;
  label_kind: DataKind;
  start_step: number;
  time_bin: number;
  cadence_sec: number;
  epoch_utc: string;
  n_steps: number;
  n_regions: number;
  grid: RegionGrid;
  /** dB above each region's own decision threshold; 0 is the boundary, not silence. */
  margin_db: number[][];
  occupancy: number;
  per_region_occupancy: number[];
  provenance: Provenance;
}

/** `GET /api/datasets/{station}/{day}/analytics` — retrospective, no scheduler involved. */
export interface AnalyticsResponse {
  recording_id: string;
  kind: DataKind;
  derived: DataKind;
  time_bin: number;
  n_steps: number;
  stats: Characterisation;
  activity_per_step: number[];
  periodicity: {
    period_steps: number;
    period_sec: number;
    strength: number;
    method: string;
  };
  change_scan: {
    steps: number[];
    scores: number[];
    threshold: number;
    change_points: number[];
    method: string;
  };
  grid: RegionGrid;
  provenance: Provenance;
}

/** One row of the measured window index — the scenario library as data. */
export interface WindowRow {
  recording_id: string;
  station: string;
  start_step: number;
  n_steps: number;
  time_bin: number;
  n_regions: number;
  occupancy: number;
  archetype: string;
  role: string;
  [key: string]: unknown;
}

export interface WindowsResponse {
  count: number;
  windows: WindowRow[];
}

// ---- scenarios --------------------------------------------------------------

export interface ReceiverSpec {
  window_size: number;
  noise_db: number;
  cost_per_observation: number;
  switch_cost: number;
  settling_penalty_db: number;
}

/** The interpretable reward weights. Every one of these is editable in the Lab. */
export interface RewardWeights {
  detection: number;
  information: number;
  delay: number;
  false_alarm: number;
  switching: number;
}

/** MAG-NTS decision weights. Tuned on TRAIN only; see data/index/mag_nts_tuning.json. */
export interface MagWeights {
  detection: number;
  information: number;
  memory: number;
  periodicity: number;
  uncertainty: number;
  recency: number;
  cost: number;
  switching: number;
}

/** One contiguous slice of one cached recording. Splicing these is how shift is made. */
export interface SegmentSpec {
  recording_id: string;
  start_step: number;
  n_steps: number;
  label: string;
  /** Free-form phase tag — `A`, `B`, `A-prime` for the recurrence scenarios. */
  phase: string;
}

/** `aamsx/contracts/scenario.py::ScenarioSpec.to_dict`. Derived keys are recomputed. */
export interface ScenarioSpec {
  scenario_id: string;
  name: string;
  description: string;
  family: string;
  segments: SegmentSpec[];
  n_regions: number;
  time_bin: number;
  freq_range_mhz: [number, number] | null;
  receiver: ReceiverSpec;
  reward: RewardWeights;
  budget: number | null;
  effective_budget: number;
  horizon: number;
  /** Step indices where a spliced boundary lands — the ground truth for TTD-after-change. */
  change_points: number[];
  phase_spans: number[][];
  split: Split;
  tags: string[];
}

/** A segment as *measured*, returned by scenario detail and validate. */
export interface MeasuredSegment extends SegmentSpec {
  station: string;
  grid: RegionGrid;
  stats: Characterisation;
  provenance: Provenance;
  availability: number;
}

export interface ScenarioDetail extends ScenarioSpec {
  segments_measured: MeasuredSegment[];
  truth_occupancy: number;
  availability?: number;
  valid?: boolean;
}

export interface ScenariosResponse {
  presets: ScenarioSpec[];
  /** Presets the current cache cannot satisfy — shown greyed out, never faked. */
  unavailable: string[];
  families: { family: string; predicate: string }[];
  note: string;
}

// ---- schedulers -------------------------------------------------------------

export interface SchedulerInfo {
  name: string;
  display_name: string;
  description: string;
  stochastic: boolean;
  uses_memory: boolean;
  uses_information_gain: boolean;
  family: string;
}

export interface SchedulersResponse {
  arena_order: string[];
  schedulers: SchedulerInfo[];
  deep_rl_available: boolean;
}

export interface StatusResponse {
  version: string;
  scheduler_version: string;
  data_mode: string;
  network_allowed: boolean;
  recordings: number;
  windows_indexed: number;
  presets: number;
  schedulers: SchedulerInfo[];
  neural_available: boolean;
  deep_rl_available: boolean;
  experiments: Record<string, number>;
  cache_mb: number;
  /** Rendered verbatim in the header. An empty cache says so rather than inventing data. */
  warnings: string[];
}

// ---- requests ---------------------------------------------------------------

/** Which parts of the intelligence stack are switched on. The Ablation Lab drives this. */
export interface AblationFlags {
  memory: boolean;
  information_gain: boolean;
  change_detection: boolean;
  periodicity: boolean;
  temporal_encoder: boolean;
  uncertainty_exploration: boolean;
  neural_encoder: boolean;
}

export interface ScenarioRequest {
  scenario_id?: string;
  name?: string;
  description?: string;
  family?: string;
  segments: SegmentSpec[];
  n_regions?: number;
  time_bin?: number;
  freq_range_mhz?: [number, number] | null;
  receiver?: Partial<ReceiverSpec>;
  reward?: Partial<RewardWeights>;
  budget?: number | null;
  split?: Split;
}

export interface EpisodeRequest {
  scenario_id?: string;
  scenario?: ScenarioRequest;
  scheduler: SchedulerName | string;
  seed?: number;
  ablation?: Partial<AblationFlags>;
  mag_weights?: Partial<MagWeights> | null;
  /** Frames per second the server paces the stream at. 0 = as fast as it runs. */
  pace_hz?: number;
  frame_stride?: number;
}

export interface BatchRequest {
  scenario_id?: string;
  scenario?: ScenarioRequest;
  schedulers?: string[];
  seeds?: number;
  workers?: number | null;
}

export interface ReportRequest {
  experiment_ids: string[];
  title?: string;
  notes?: string;
}

// ---- the live frame ---------------------------------------------------------

/** Modern-Hopfield read result for one step. `recognised` gates the memory term. */
export interface MemoryReadout {
  similarity: number;
  prototype_id: number | null;
  age: number;
  utility: number;
  visits: number;
  label: string;
  recognised: boolean;
  top_ids: number[];
  top_weights: number[];
}

/** One stored context prototype. `preference` is the retrieved prior over regions. */
export interface MemoryPrototype {
  id: number;
  label: string;
  utility: number;
  visits: number;
  created_step: number;
  last_step: number;
  preference: number[];
}

export interface MemorySnapshot {
  size: number;
  capacity: number;
  writes: number;
  creations: number;
  evictions: number;
  recognitions: number;
  standardiser_samples: number;
  prototypes: MemoryPrototype[];
}

/** Page-Hinkley + EWMA change state. `flag` is what the scheduler actually saw. */
export interface ChangeSnapshot {
  score: number;
  flag: boolean;
  steps_since_change: number;
  change_steps: number[];
  statistic: number;
  page_hinkley: number;
  ewma: number;
  exploration_boost: number;
}

export interface BeliefSnapshot {
  belief: number[];
  uncertainty: number[];
  aleatoric: number[];
  epistemic: number[];
  staleness: number[];
  steps_since_seen: number[];
  hit_rate: number[];
  observations: number[];
}

export interface PeriodicitySnapshot {
  period_steps: number;
  strength: number;
  phase_bins: number;
  phase: number;
  history: number;
  region_scores: number[];
}

/** The eight weighted terms, keyed `contribution.<term>` inside `DecisionFactors`. */
export const FACTOR_TERMS = [
  "detection",
  "information",
  "memory",
  "periodicity",
  "uncertainty",
  "recency",
  "cost",
  "switching",
] as const;

export type FactorTerm = (typeof FACTOR_TERMS)[number];

/**
 * The Decision Inspector payload: raw evidence for the chosen window, then the same
 * eight terms after weighting. `final_action_value` is their sum at the anchor, so the
 * inspector can show that the explanation adds up to the decision rather than
 * gesturing at it.
 */
export interface DecisionFactors {
  predicted_activity: number;
  posterior_confidence: number;
  information_gain: number;
  memory_similarity: number;
  periodicity_score: number;
  staleness: number;
  uncertainty: number;
  sensing_cost: number;
  switching_penalty: number;
  sampled_rate: number;
  steps_since_observed: number;
  steps_since_change: number;
  budget_pressure: number;
  final_action_value: number;
  /** `contribution.detection`, `contribution.memory`, … one per FACTOR_TERMS entry. */
  [key: string]: number;
}

/** The additive reward terms, exposed so the score is never a black box. */
export interface RewardTerms {
  detection: number;
  information: number;
  delay: number;
  false_alarm: number;
  switching: number;
  [key: string]: number;
}

/**
 * One streamed step — `aamsx/experiments/runner.py::_frame` plus the `progress` the
 * engine stamps on. `true_occupied` / `true_margin_db` / `band_truth` / `oracle_best`
 * are evaluation-only: they arrive here for the ground-truth overlay and were sealed
 * away from the scheduler when it chose (`env.sealed()`).
 */
export interface Frame {
  type: "frame";
  step: number;
  t_sec: number;
  /** The regions the receiver actually landed on this step (the window). */
  regions: number[];
  measured_db: number[];
  detected: boolean[];
  confidence: number[];
  true_occupied: boolean[];
  true_margin_db: number[];
  band_truth: number;
  /** Best achievable detections this step — the denominator of `oracle_ratio`. */
  oracle_best: number;
  /** False during an archive gap: the receiver measured nothing real. */
  available: boolean;
  belief: number[];
  uncertainty: number[];
  staleness: number[];
  action_value: number;
  factors: DecisionFactors;
  /** Human-readable reasons the policy logged for this decision. */
  notes: string[];
  per_region_value: number[] | null;
  reward: number;
  reward_terms: RewardTerms;
  cumulative_reward: number;
  cumulative_regret: number;
  hits: number;
  false_alarms: number;
  budget_remaining: number;
  change: ChangeSnapshot;
  memory: MemoryReadout;
  periodicity: { period_steps: number; strength: number };
  segment_index: number;
  segment_changed: boolean;
  exploration_rate: number;
  progress: number;
}

// ---- results ----------------------------------------------------------------

/**
 * `MetricAccumulator.summary`. The named fields are the ones the UI ranks on; the
 * index signature carries the `reward.<term>` breakdown that comes with them.
 */
export interface EpisodeMetrics {
  steps: number;
  unavailable_steps: number;
  detection_rate: number;
  false_alarm_rate: number;
  precision: number;
  event_detection_probability: number;
  sustained_detection_probability: number;
  sustained_detection_delay: number;
  time_to_detect_capped: number;
  events_sustained: number;
  events_sustained_detected: number;
  mean_detection_delay: number;
  median_detection_delay: number;
  p90_detection_delay: number;
  events_total: number;
  events_detected: number;
  events_missed: number;
  cumulative_reward: number;
  mean_reward: number;
  cumulative_regret: number;
  regret_per_step: number;
  oracle_ratio: number;
  detections: number;
  detections_per_observation: number;
  detections_per_cost: number;
  information_bits: number;
  information_per_observation: number;
  sensing_cost: number;
  budget: number;
  budget_used_fraction: number;
  band_coverage: number;
  [key: string]: number;
}

/** In-process wall-clock per decision. Not reproducible across runs; see docs/LIMITATIONS.md. */
export interface Latency {
  p50: number;
  p95: number;
  p99: number;
  max: number;
  mean: number;
}

export type Severity = "info" | "success" | "warning" | "critical" | "insight";

export type EventKind =
  | "experiment_started"
  | "detection"
  | "burst_detected"
  | "miss"
  | "high_uncertainty"
  | "change_detected"
  | "memory_recalled"
  | "periodicity_discovered"
  | "exploration_increased"
  | "budget_threshold"
  | "budget_exhausted"
  | "phase_changed"
  | "archive_gap"
  | "experiment_completed";

export interface TimelineEvent {
  kind: EventKind;
  step: number;
  message: string;
  severity: Severity;
  data: Record<string, unknown>;
}

export interface RecoveryEntry {
  change_step: number;
  recovered_after: number | null;
  recovered: boolean;
}

export interface Recovery {
  change_points: RecoveryEntry[];
  n_change_points: number;
}

/** Per-phase detection, so A vs B vs A-prime is directly comparable. */
export interface SegmentMetric {
  phase: string;
  start_step: number;
  stop_step: number;
  mean_hits: number;
  station: string;
  archetype: string;
  true_occupancy: number;
}

export interface EpisodeResult {
  scenario_id: string;
  scheduler: string;
  seed: number;
  flags: AblationFlags;
  metrics: EpisodeMetrics;
  curves: {
    reward: number[];
    regret: number[];
    hits: number[];
    /** Anchor chosen at each step — the scan pattern, drawn as a raster. */
    anchors: number[];
  };
  timeline: TimelineEvent[];
  recovery: Recovery;
  scheduler_snapshot: Record<string, unknown>;
  context_snapshot: {
    step: number;
    belief: BeliefSnapshot;
    change: ChangeSnapshot;
    periodicity: PeriodicitySnapshot;
    memory: MemorySnapshot;
    features: Record<string, number>;
    readout: MemoryReadout;
    surprise: number;
    budget_remaining: number;
  };
  segment_metrics: SegmentMetric[];
  duration_sec: number;
  decision_ms: Latency;
  steps: number;
  scenario: ScenarioSpec;
}

/**
 * `BatchResult.to_dict`. `variants` is the ordered list of arm keys — a scheduler name
 * for an arena, `mag-nts[label]` for an ablation rung — and every other map is keyed by
 * it. Note what is *not* here: per-arm raw samples against a different control. A
 * head-to-head with another baseline is a re-run, not a re-read, which is why
 * `scripts/run_benchmark.py --baseline` writes its own file.
 */
export interface BatchResult {
  scenario: ScenarioSpec;
  variants: string[];
  /** `aggregates[variant][metric]` — the 13 headline metrics, aggregated over seeds. */
  aggregates: Record<string, Record<string, Aggregate>>;
  comparisons: Comparison[];
  /** One entry per seed, each holding that episode's per-change-point recovery. */
  recoveries: Record<string, Recovery[]>;
  latency: Record<string, Latency>;
  n_runs: Record<string, number>;
  /** Attached by the engine, not by `run_batch` — absent in the CLI's JSON artefacts. */
  pareto?: ParetoFrontier;
}

/** One policy's position in objective space. */
export interface ParetoPoint {
  label: string;
  values: Partial<Record<ParetoObjective, number>>;
  on_frontier: boolean;
  dominated_by: string[];
}

export type ParetoObjective =
  | "sustained_detection_probability"
  | "time_to_detect_capped"
  | "false_alarm_rate"
  | "sensing_cost";

/**
 * `aamsx/evaluation/pareto.py::describe`. `vacuous` is the honest flag: when every
 * point is missing the same axis, nothing can dominate anything and a full frontier
 * means "the comparison could not be made", not "every policy is optimal".
 */
export interface ParetoFrontier {
  axes_missing: string[];
  vacuous: boolean;
  objectives: {
    metric: ParetoObjective;
    label: string;
    direction: "maximise" | "minimise";
  }[];
  points: ParetoPoint[];
  frontier: string[];
}

/** The metrics a batch aggregates and compares, in report order. */
export const HEADLINE_METRICS = [
  "cumulative_reward",
  "cumulative_regret",
  "sustained_detection_probability",
  "event_detection_probability",
  "sustained_detection_delay",
  "time_to_detect_capped",
  "detection_rate",
  "false_alarm_rate",
  "detections_per_cost",
  "information_per_observation",
  "oracle_ratio",
  "band_coverage",
  "sensing_cost",
] as const;

export type HeadlineMetric = (typeof HEADLINE_METRICS)[number];

export type ExperimentResult = EpisodeResult | BatchResult;

export function isBatchResult(
  result: ExperimentResult | null,
): result is BatchResult {
  return result !== null && "comparisons" in result;
}

export function isEpisodeResult(
  result: ExperimentResult | null,
): result is EpisodeResult {
  return result !== null && "curves" in result;
}

// ---- sessions and the websocket --------------------------------------------

export type SessionStatus =
  "queued" | "running" | "completed" | "failed" | "cancelled" | "cancelling";

/** `Session.summary()`. Spread into every non-frame websocket message. */
export interface SessionSummary {
  experiment_id: string;
  kind: string;
  scenario_id: string;
  label: string;
  status: SessionStatus | string;
  progress: number;
  n_frames: number;
  error: string | null;
  started_at: number;
  finished_at: number | null;
  duration_sec: number;
}

export interface StartResponse extends SessionSummary {
  experiment_id: string;
  /** Batches only: how many episodes the arena or ladder will run. */
  n_jobs?: number;
  /** Replays only: the experiment this one re-executes, plus its config hash. */
  replay_of?: string;
  config_hash?: string;
}

/**
 * `GET /experiments/{id}` returns one of two shapes, and they disagree about time.
 *
 * A run still held in memory answers with the live session summary, whose `started_at` /
 * `finished_at` are `time.time()` floats. Once the session is evicted the registry row
 * answers instead, and its `created_at` / `finished_at` are ISO strings. So `finished_at`
 * is genuinely a union here and callers must narrow it — see `isoOrEpochSeconds`.
 */
export interface ExperimentDetail extends Omit<
  Partial<SessionSummary>,
  "finished_at"
> {
  experiment_id: string;
  result: ExperimentResult | null;
  config_hash?: string;
  scheduler?: string;
  seed?: number;
  ablation?: string;
  /** Registry rows only, and always an ISO string when present. */
  created_at?: string;
  finished_at?: number | string | null;
  code_version?: string;
  scheduler_version?: string;
  recordings?: string[];
  config?: Record<string, unknown>;
  metrics?: Record<string, number>;
}

/** A registry row. `config_hash` is what makes the Replay button honest. */
export interface RegistryRecord {
  experiment_id: string;
  config_hash: string;
  kind: string;
  scenario_id: string;
  scheduler: string;
  seed: number;
  ablation: string;
  status: string;
  /** ISO-8601, tz-aware UTC — the registry stores these as TEXT, not epoch seconds. */
  created_at: string;
  finished_at: string | null;
  code_version: string;
  scheduler_version: string;
  recordings: string[];
  config: Record<string, unknown>;
  metrics: Record<string, number>;
  error: string | null;
}

export interface HistoryResponse {
  count: number;
  experiments: RegistryRecord[];
}

export interface ActiveResponse {
  active: SessionSummary[];
}

export interface FramesResponse {
  start: number;
  count: number;
  total: number;
  frames: Frame[];
}

/** Batch progress, emitted by `run_batch`'s progress sink through the same socket. */
export interface BatchProgress {
  type: "batch_progress";
  done: number;
  total: number;
}

export type StreamMessage =
  | Frame
  | ({ type: "session" } & SessionSummary)
  | ({ type: "status" } & SessionSummary)
  | ({ type: "timeline" } & TimelineEvent)
  | ({ type: "complete" } & SessionSummary & { result: ExperimentResult })
  | ({ type: "error" } & Partial<SessionSummary> & { error: string })
  | BatchProgress;

export function isFrame(message: StreamMessage): message is Frame {
  return message.type === "frame";
}

// ---- reports ----------------------------------------------------------------

export interface ReportSummary {
  name: string;
  url: string;
  size_bytes: number;
  modified: number;
}

export interface ReportsResponse {
  reports: ReportSummary[];
}

export interface ReportCreated {
  name: string;
  path: string;
  url: string;
  size_bytes: number;
  experiment_ids: string[];
}
