export type Category = 'CONTROLLED_SIMULATION' | 'OFFICIAL_SYNTHETIC_RADAR' | 'REAL_MEASURED_RF'
export type Algorithm = 'magnts' | 'fixed' | 'random' | 'thompson' | 'ucb' | 'no_memory' | 'no_information' | 'no_change'
export type RunState = 'running' | 'paused' | 'completed' | 'cancelled' | 'failed'
export type Page = 'command' | 'duel' | 'cube' | 'knowledge' | 'periodic' | 'benchmark' | 'explorer' | 'provenance' | 'architecture' | 'methodology' | 'library'

export interface ReceiverConfig {
  bands: number; window_width: number; frequency_min_mhz: number; frequency_max_mhz: number
  slot_ms: number; min_dwell_ms: number; retune_ms: number; scan_latency_ms: number
  noise_floor_db: number; noise_std_db: number; threshold_db: number; snr_db: number
  false_alarm_probability: number; miss_probability: number; switching_cost: number
}
export interface ExperimentConfig {
  seed: number; scenario: string; horizon: number; receiver: ReceiverConfig
  algorithms: Algorithm[]; dataset_id: string; emitters?: EmitterSpec[] | null
}
export interface EmitterSpec {
  kind: 'continuous' | 'periodic' | 'burst' | 'hopping' | 'agile' | 'random' | 'changing'
  band: number; width?: number; start?: number; stop?: number | null; period?: number; duration?: number; duty?: number; snr_offset?: number
}
export interface Scenario { id: string; name: string; description: string; tag: string }
export interface Dataset {
  id: string; name: string; category: Category; status?: string; organization?: string
  ground_truth: boolean | null; original_format?: string; source_url?: string | null; note: string
  artifact?: string; artifact_sha256?: string; source_sha256?: string; source_file?: string
  ingested_at?: string; time_start_utc?: string; sample_count?: number; source_sample_count?: number
  pulse_count?: number; station?: string; frequency_range_mhz?: number[]; time_range_ms?: number[]
  shape?: number[]; energy_unit?: string; raw_energy_unit?: string; lineage?: string[]
  preprocessing?: Record<string, unknown>; install_command?: string; license?: string
  calibration_slots?: number; evaluation_time_offset_ms?: number
}
export type Metrics = Record<string, number | boolean | null>
export interface Candidate {
  start: number; end: number; score: number; probability: number; uncertainty: number
  selected: boolean; components: Record<string, number>
}
export interface PeriodicCandidate {
  band: number; period_slots: number; phase: number; confidence: number; observed_events: number[]
  next_slot: number; evidence_count: number; interval_mae_slots: number; status: string; fit_step: number
}
export interface MemoryMatch {
  band: number; similarity: number; previous_step: number; previous_outcome: string
  expected_hit: number; pattern: number[]; support: number; contribution: number
}
export interface Decision {
  action: { start: number; width: number }; score: number; candidates: Candidate[]
  components: Record<string, number>; reasons: string[]; exploration: boolean
  pre_probability: number[]; pre_uncertainty: number[]; periodic_candidates: PeriodicCandidate[]
  memory_matches: MemoryMatch[]
}
export interface BandObservation {
  band: number; energy: number | null; detected: boolean; confidence: number; noise_estimate: number; valid: boolean
}
export interface ChangeEvent { band: number; step: number; score: number; direction: string }
export interface Belief {
  probability: number[]; uncertainty: number[]; information_gain: number[]; observations: number[]
  last_visit: number[]; age: number[]; change_scores: number[]; change_events: ChangeEvent[]
  periodicity: PeriodicCandidate[]; memory_size: number
}
export interface PredictionEvent { band: number; issued_slot: number; predicted_slot: number; actual_slot: number; error_ms: number; confidence: number }
export interface PolicyFrame {
  algorithm: Algorithm; selected_window: { start: number; width: number; end: number }
  previous_window: number | null; retune_cost: number; hit_count: number; reward: number | null
  observations: { step: number; timestamp_ms: number; values: BandObservation[]; effective_dwell_ms: number; retune_cost: number }
  decision: Decision; belief: Belief; metrics: Metrics
  evaluation?: { true_hits: number[]; false_alarms: number[]; missed_bands: number[]; new_interceptions: { band: number; onset: number; delay_ms: number }[]; prediction_events: PredictionEvent[] }
}
export interface Frame {
  step: number; timestamp_ms: number; policies: Partial<Record<Algorithm, PolicyFrame>>
  evaluation?: { label: string; active_bands: number[] | null; energy: (number | null)[] }
}
export interface Run {
  id: string; created_at: string; state: RunState; error?: string | null; step: number
  config: ExperimentConfig; dataset: Dataset; environment_hash: string; receiver_hash: string
  frequencies_mhz: number[]; metrics: Partial<Record<Algorithm, Metrics>>; engine_version: string
  policy_input: string; trace_hash?: string; recording_label?: string
}
export interface DatasetPreview {
  metadata: Dataset; time_ms: number[]; frequency_mhz: number[]; intensity: (number | null)[][]
  display_range: number[]; samples: Record<string, string | number | null>[]; downsampling: string
}
export interface MetricDefinition { key: string; name: string; formula: string; unit: string; truth: boolean; note: string }
export interface SummaryStatistics { n: number; mean: number | null; median: number | null; variance: number | null; ci95: number[] | null; values: number[] }
export interface BenchmarkConfig { scenarios: string[]; seed: number; runs: number; horizon: number; receiver: ReceiverConfig; algorithms: Algorithm[]; dataset_id: string }
export interface BenchmarkResult {
  id: string; created_at: string; state: string; error: string | null; completed: number; total: number
  config: BenchmarkConfig; methodology: string
  results: { experiment_id: string; scenario: string; seed: number; environment_hash: string; metrics: Partial<Record<Algorithm, Metrics>> }[]
  aggregates: { scenario: string; algorithm: Algorithm; metrics: Record<string, SummaryStatistics>; paired_delta_vs_fixed: Record<string, SummaryStatistics> }[]
}
