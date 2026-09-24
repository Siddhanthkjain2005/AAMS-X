"""Evaluation-only metrics. This module is not importable by scheduler modules.

Denominators, units, censoring, and aliases are deliberately explicit. Detector
Pd is conditional on observation; global recall includes unobserved activity.
"""

import numpy as np

from backend.contracts import Observation
from backend.environment.spectrum import World
from backend.scheduler.policies import Decision

METRIC_DEFINITIONS = [
    {"key": "pd", "name": "Probability of Detection", "formula": "TP / (TP + FN_observed)", "unit": "fraction", "truth": True, "note": "Detector performance conditional on valid observed active cells; it is not full-spectrum interception."},
    {"key": "pfa", "name": "Probability of False Alarm", "formula": "FP / (FP + TN)", "unit": "fraction", "truth": True, "note": "Conditional on valid observed inactive cells."},
    {"key": "recall", "name": "Sensitivity / Recall", "formula": "TP / all active band-time cells", "unit": "fraction", "truth": True, "note": "Unobserved active cells count as missed. Also called global interception share in the live duel."},
    {"key": "avg_interception_rate", "name": "Average Interception Rate", "formula": "mean_t(TP_t / active_t), over slots with active_t > 0", "unit": "fraction", "truth": True, "note": "Unweighted mean of per-slot interception share; recall is the activity-weighted version."},
    {"key": "average_reward", "name": "Average Reward", "formula": "Σ(TP − FP − 0.1 × retune_cost) / steps", "unit": "reward / step", "truth": True, "note": "Evaluation reward only. The scheduler learns from observed detections, never this truth-derived reward."},
    {"key": "reward_cost", "name": "Reward / Cost", "formula": "Σreward / Σ(1 + retune_cost)", "unit": "reward / cost unit", "truth": True, "note": "One sensing-cost unit per slot. Retune cost = delay / slot + switching_weight × normalized frequency distance."},
    {"key": "prediction_accuracy", "name": "Percentage of Correct Predictions", "formula": "correct pre-observation occupancy classifications / valid observed cells", "unit": "fraction", "truth": True, "note": "Threshold = 0.5; scores are captured before the observation. Class imbalance can inflate accuracy."},
    {"key": "avg_intercept_time_ms", "name": "Average Intercept Time", "formula": "mean(first detected slot − episode onset) × slot_ms", "unit": "ms", "truth": True, "note": "Among intercepted band-activity episodes only. Report the episode censoring fraction alongside this metric."},
    {"key": "avg_intercept_time_error_ms", "name": "Average Intercept Time Error", "formula": "mean(|predicted next onset − actual next onset|) × slot_ms", "unit": "ms", "truth": True, "note": "Prospective recurrence forecasts with confidence ≥ 0.6; first forecast per band/onset, scored only when the actual onset has occurred. N/A without resolved forecasts."},
    {"key": "interception_ratio", "name": "Interception Ratio", "formula": "intercepted band-activity episodes / episodes begun", "unit": "fraction", "truth": True, "note": "An episode is a contiguous active interval in one logical frequency band, not an identified emitter."},
    {"key": "miss_rate", "name": "Global Miss Rate", "formula": "1 − recall", "unit": "fraction", "truth": True, "note": "Includes out-of-window activity."},
    {"key": "scan_efficiency", "name": "Scan Efficiency", "formula": "observed active cells / valid observed cells", "unit": "fraction", "truth": True, "note": "How effectively the sensing budget is allocated to activity."},
    {"key": "active_scan_fraction", "name": "Scans Spent on Active Bands", "formula": "slots observing ≥ 1 active cell / slots", "unit": "fraction", "truth": True, "note": "Activity comes from evaluation labels, not detection output."},
    {"key": "time_to_first_detection_ms", "name": "Time to First Source-Overlap Detection", "formula": "mean(first detection overlapping source − first source activity)", "unit": "ms", "truth": True, "note": "Controlled source tracks only; conditional on detection. This does not claim emitter identification. Undetected source count is also reported."},
    {"key": "coverage_fairness", "name": "Coverage Fairness", "formula": "(Σvisits)² / (bands × Σvisits²)", "unit": "fraction", "truth": False, "note": "Jain index of valid observation counts. Higher fairness is not always higher interception."},
    {"key": "exploration_fraction", "name": "Directed Exploration", "formula": "explicit exploration decisions / steps", "unit": "fraction", "truth": False, "note": "Counts the exploration branch; ordinary Thompson sampling can explore outside this branch too."},
    {"key": "coverage", "name": "Band Coverage", "formula": "bands with ≥ 1 valid observation / bands", "unit": "fraction", "truth": False, "note": "Available for measured RF recordings without labels."},
    {"key": "retune_count", "name": "Retune Count", "formula": "Σ1(window_t ≠ window_(t−1))", "unit": "retunes", "truth": False, "note": "Initial tuning is not counted as a retune."},
    {"key": "retune_cost", "name": "Accumulated Retune Cost", "formula": "Σ(delay / slot + weight × |Δband| / candidate_span)", "unit": "cost units", "truth": False, "note": "Dimensionless accounting cost, not watts or hardware power."},
]


def ratio(a: float, b: float) -> float | None:
    return round(float(a / b), 6) if b else None


class MetricAccumulator:
    def __init__(self, world: World, slot_ms: float):
        self.world = world
        self.slot_ms = slot_ms
        self.bands = world.energy.shape[1]
        self.counts = {k: 0 for k in ("tp", "fp", "tn", "fn", "active", "observed", "correct", "steps", "hits", "exploration", "retunes", "active_scans", "episodes", "intercepted", "missing")}
        self.visits = np.zeros(self.bands, dtype=int)
        self.episode_start = np.full(self.bands, -1, dtype=int)
        self.episode_caught = np.zeros(self.bands, dtype=bool)
        self.previous_truth = np.zeros(self.bands, dtype=bool)
        self.delays: list[float] = []
        self.slot_interception: list[float] = []
        self.forecasts: dict[tuple[int, int], dict] = {}
        self.prediction_results: list[dict] = []
        self.onsets = [np.flatnonzero(world.truth[:, b] & ~np.r_[False, world.truth[:-1, b]]) if world.truth is not None else np.array([]) for b in range(self.bands)]
        self.source_cells = {track["id"]: {t: set(range(b, b + w)) for t, b, w in track["cells"]} for track in world.tracks}
        self.source_first = {key: min(cells) for key, cells in self.source_cells.items() if cells}
        self.source_delays: dict[str, float] = {}
        self.reward = self.cost = self.retune_cost = self.confidence_sum = 0.0

    def update(self, observation: Observation, decision: Decision, changed: bool) -> dict:
        t, c = observation.step, self.counts
        c["steps"] += 1
        c["hits"] += sum(v.detected for v in observation.values)
        c["exploration"] += decision.exploration
        c["retunes"] += changed
        c["missing"] += sum(not v.valid for v in observation.values)
        self.retune_cost += observation.retune_cost
        self.cost += 1 + observation.retune_cost
        for value in observation.values:
            if value.valid:
                self.visits[value.band] += 1
                c["observed"] += 1
                self.confidence_sum += value.confidence
        evaluation = {"true_hits": [], "false_alarms": [], "missed_bands": [], "new_interceptions": [], "prediction_events": []}
        if self.world.truth is None:
            return {"evaluation": evaluation, "reward": None, "metrics": self.snapshot()}
        truth = self.world.truth[t]
        starts = truth & ~self.previous_truth
        self.episode_start[starts] = t
        self.episode_caught[starts] = False
        c["episodes"] += int(starts.sum())
        self.previous_truth = truth
        tp = fp = observed_active = 0
        for value in observation.values:
            if not value.valid:
                continue
            active = bool(truth[value.band])
            c["correct"] += (decision.pre_probability[value.band] >= 0.5) == active
            observed_active += active
            if value.detected and active:
                tp += 1
                evaluation["true_hits"].append(value.band)
                if not self.episode_caught[value.band]:
                    self.episode_caught[value.band] = True
                    c["intercepted"] += 1
                    delay = float((t - self.episode_start[value.band]) * self.slot_ms)
                    self.delays.append(delay)
                    evaluation["new_interceptions"].append({"band": value.band, "onset": int(self.episode_start[value.band]), "delay_ms": delay})
            elif value.detected:
                fp += 1
                evaluation["false_alarms"].append(value.band)
            else:
                c["fn" if active else "tn"] += 1
        c["tp"] += tp
        c["fp"] += fp
        c["active"] += int(truth.sum())
        c["active_scans"] += observed_active > 0
        evaluation["missed_bands"] = [int(b) for b in np.flatnonzero(truth) if b not in evaluation["true_hits"]]
        if truth.sum():
            self.slot_interception.append(tp / float(truth.sum()))
        reward = tp - fp - 0.1 * observation.retune_cost
        self.reward += reward
        for track_id, cells in self.source_cells.items():
            if track_id not in self.source_delays and t in cells and cells[t].intersection(evaluation["true_hits"]):
                self.source_delays[track_id] = (t - self.source_first[track_id]) * self.slot_ms
        # Resolve only forecasts issued before this onset, never use future truth in live metrics.
        for band in np.flatnonzero(starts):
            key = (int(band), t)
            if key in self.forecasts:
                result = {**self.forecasts.pop(key), "actual_slot": t}
                result["error_ms"] = abs(result["predicted_slot"] - t) * self.slot_ms
                self.prediction_results.append(result)
                evaluation["prediction_events"].append(result)
        for prediction in decision.periodic_candidates:
            if prediction["confidence"] < 0.6:
                continue
            band = prediction["band"]
            future = self.onsets[band][self.onsets[band] > t]
            if len(future):
                key = (band, int(future[0]))
                self.forecasts.setdefault(key, {"band": band, "issued_slot": t, "predicted_slot": prediction["next_slot"], "confidence": prediction["confidence"]})
        return {"evaluation": evaluation, "reward": round(reward, 6), "metrics": self.snapshot()}

    def snapshot(self) -> dict:
        c = self.counts
        labelled = self.world.truth is not None
        s = {
            "steps": c["steps"], "observed_cells": c["observed"], "observed_energy_events": c["hits"],
            "true_positives": c["tp"] if labelled else None,
            "false_positives": c["fp"] if labelled else None,
            "false_negatives_observed": c["fn"] if labelled else None,
            "true_negatives": c["tn"] if labelled else None,
            "total_active_cells": c["active"] if labelled else None,
            "missed_active_cells": c["active"] - c["tp"] if labelled else None,
            "pd": ratio(c["tp"], c["tp"] + c["fn"]) if labelled else None,
            "pfa": ratio(c["fp"], c["fp"] + c["tn"]) if labelled else None,
            "recall": ratio(c["tp"], c["active"]) if labelled else None,
            "avg_interception_rate": float(np.mean(self.slot_interception)) if self.slot_interception else None,
            "average_reward": ratio(self.reward, c["steps"]) if labelled else None,
            "reward_cost": ratio(self.reward, self.cost) if labelled else None,
            "prediction_accuracy": ratio(c["correct"], c["observed"]) if labelled else None,
            "avg_intercept_time_ms": float(np.mean(self.delays)) if self.delays else None,
            "avg_intercept_time_error_ms": float(np.mean([p["error_ms"] for p in self.prediction_results])) if self.prediction_results else None,
            "interception_ratio": ratio(c["intercepted"], c["episodes"]) if labelled else None,
            "intercepted_episodes": c["intercepted"] if labelled else None,
            "total_episodes": c["episodes"] if labelled else None,
            "episode_censoring_fraction": ratio(c["episodes"] - c["intercepted"], c["episodes"]) if labelled else None,
            "scan_efficiency": ratio(c["tp"] + c["fn"], c["observed"]) if labelled else None,
            "active_scan_fraction": ratio(c["active_scans"], c["steps"]) if labelled else None,
            "retune_count": c["retunes"], "retune_cost": round(self.retune_cost, 6), "total_cost": round(self.cost, 6),
            "time_to_first_detection_ms": float(np.mean(list(self.source_delays.values()))) if self.source_delays else None,
            "undetected_sources": sum(first <= c["steps"] - 1 and key not in self.source_delays for key, first in self.source_first.items()) if self.source_first else None,
            "coverage_fairness": ratio(float(self.visits.sum()) ** 2, self.bands * float((self.visits**2).sum())),
            "coverage": float(np.count_nonzero(self.visits) / self.bands),
            "exploration_fraction": ratio(c["exploration"], c["steps"]),
            "mean_observation_confidence": ratio(self.confidence_sum, c["observed"]),
            "missing_channel_fraction": ratio(c["missing"], c["observed"] + c["missing"]),
            "resolved_predictions": len(self.prediction_results), "pending_predictions": len(self.forecasts),
            "ground_truth_available": labelled,
        }
        s["miss_rate"] = 1 - s["recall"] if s["recall"] is not None else None
        return s
