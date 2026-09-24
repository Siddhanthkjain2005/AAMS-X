"""Episode metric accumulation.

Metrics are accumulated online so an episode can stream to the UI and be scored at
the same time, and so a 20 000-step run costs constant memory.

Two families of accuracy metric are reported and they answer different questions.
*Cell-level* rates (detection rate, false-alarm rate) describe the receiver inside
the windows it was pointed at.  *Event-level* rates (event detection probability,
detection delay) describe the scheduler: whether it pointed the receiver at the
right place while something was happening.  A policy can have an excellent cell
detection rate and a terrible event detection probability, and that gap is exactly
what this platform exists to measure.

Regret is pseudo-regret against a clairvoyant window oracle: at each step the
oracle picks the window containing the most genuinely occupied regions, and regret
accrues the difference between that count and the hits actually achieved.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from aamsx.evaluation.events import EventTracker


@dataclass(slots=True)
class MetricAccumulator:
    """Online accumulation of every episode metric."""

    n_regions: int
    window_size: int
    horizon: int
    budget: float

    steps: int = 0
    unavailable_steps: int = 0
    cells_observed: int = 0
    true_positives: int = 0
    false_positives: int = 0
    true_negatives: int = 0
    false_negatives: int = 0
    total_reward: float = 0.0
    total_cost: float = 0.0
    total_information_bits: float = 0.0
    total_regret: float = 0.0
    oracle_total: int = 0
    hits_total: int = 0
    reward_terms: dict[str, float] = field(default_factory=dict)
    reward_curve: list[float] = field(default_factory=list)
    regret_curve: list[float] = field(default_factory=list)
    anchors: list[int] = field(default_factory=list)

    def record(
        self,
        *,
        step: int,
        anchor: int,
        detected: np.ndarray,
        true_occupied: np.ndarray,
        reward: float,
        reward_terms: dict[str, float],
        cost: float,
        information_bits: float,
        oracle_best: int,
        available: bool,
    ) -> None:
        self.steps += 1
        self.anchors.append(int(anchor))
        if not available:
            self.unavailable_steps += 1
        else:
            self.cells_observed += int(detected.size)
            self.true_positives += int((detected & true_occupied).sum())
            self.false_positives += int((detected & ~true_occupied).sum())
            self.false_negatives += int((~detected & true_occupied).sum())
            self.true_negatives += int((~detected & ~true_occupied).sum())

        hits = int((detected & true_occupied).sum())
        self.hits_total += hits
        self.oracle_total += int(oracle_best)
        self.total_regret += max(0, int(oracle_best) - hits)
        self.total_reward += float(reward)
        self.total_cost += float(cost)
        self.total_information_bits += float(information_bits)
        for key, value in reward_terms.items():
            self.reward_terms[key] = self.reward_terms.get(key, 0.0) + float(value)
        self.reward_curve.append(float(self.total_reward))
        self.regret_curve.append(float(self.total_regret))

    # ---- derived --------------------------------------------------------------

    @property
    def detection_rate(self) -> float:
        """Cell-level recall inside observed windows."""
        denominator = self.true_positives + self.false_negatives
        return self.true_positives / denominator if denominator else float("nan")

    @property
    def false_alarm_rate(self) -> float:
        denominator = self.false_positives + self.true_negatives
        return self.false_positives / denominator if denominator else float("nan")

    @property
    def precision(self) -> float:
        denominator = self.true_positives + self.false_positives
        return self.true_positives / denominator if denominator else float("nan")

    @property
    def detections_per_observation(self) -> float:
        return self.hits_total / self.steps if self.steps else 0.0

    @property
    def detections_per_cost(self) -> float:
        return self.hits_total / self.total_cost if self.total_cost > 0 else 0.0

    @property
    def information_per_observation(self) -> float:
        return self.total_information_bits / self.steps if self.steps else 0.0

    @property
    def oracle_ratio(self) -> float:
        """Achieved detections as a fraction of the clairvoyant maximum."""
        return self.hits_total / self.oracle_total if self.oracle_total else float("nan")

    @property
    def coverage(self) -> float:
        visited = len({anchor for anchor in self.anchors})
        anchors = max(1, self.n_regions - self.window_size + 1)
        return visited / anchors

    def summary(self, tracker: EventTracker) -> dict[str, float | int]:
        events = tracker.summary()
        return {
            "steps": self.steps,
            "unavailable_steps": self.unavailable_steps,
            "detection_rate": _clean(self.detection_rate),
            "false_alarm_rate": _clean(self.false_alarm_rate),
            "precision": _clean(self.precision),
            "event_detection_probability": _clean(events["event_detection_probability"]),
            "sustained_detection_probability": _clean(events["sustained_detection_probability"]),
            "sustained_detection_delay": _clean(events["sustained_detection_delay"]),
            "time_to_detect_capped": _clean(events["time_to_detect_capped"]),
            "events_sustained": int(events["events_sustained"]),
            "events_sustained_detected": int(events["events_sustained_detected"]),
            "mean_detection_delay": _clean(events["mean_detection_delay"]),
            "median_detection_delay": _clean(events["median_detection_delay"]),
            "p90_detection_delay": _clean(events["p90_detection_delay"]),
            "events_total": int(events["events_total"]),
            "events_detected": int(events["events_detected"]),
            "events_missed": int(events["events_missed"]),
            "cumulative_reward": _clean(self.total_reward),
            "mean_reward": _clean(self.total_reward / self.steps if self.steps else 0.0),
            "cumulative_regret": _clean(self.total_regret),
            "regret_per_step": _clean(self.total_regret / self.steps if self.steps else 0.0),
            "oracle_ratio": _clean(self.oracle_ratio),
            "detections": self.hits_total,
            "detections_per_observation": _clean(self.detections_per_observation),
            "detections_per_cost": _clean(self.detections_per_cost),
            "information_bits": _clean(self.total_information_bits),
            "information_per_observation": _clean(self.information_per_observation),
            "sensing_cost": _clean(self.total_cost),
            "budget": _clean(self.budget),
            "budget_used_fraction": _clean(
                self.total_cost / self.budget if self.budget > 0 else 0.0
            ),
            "band_coverage": _clean(self.coverage),
            **{f"reward.{key}": _clean(value) for key, value in self.reward_terms.items()},
        }


def _clean(value: float | int) -> float | int:
    """Replace NaN/inf with None-safe values for JSON transport."""
    if isinstance(value, int):
        return value
    number = float(value)
    if not np.isfinite(number):
        return float("nan")
    return round(number, 6)


def recovery_time(
    curve: np.ndarray, change_step: int, *, window: int = 40, tolerance: float = 0.9
) -> int | None:
    """Steps after ``change_step`` until a rolling performance level recovers.

    The pre-change reference is the mean of ``curve`` over the ``window`` steps
    before the change; recovery is the first step at which the trailing mean
    reaches ``tolerance`` of that reference and stays defined.  ``None`` means the
    policy had not recovered by the end of the episode, which is itself a result
    and is reported as such rather than silently coerced to the horizon.
    """
    values = np.asarray(curve, dtype=np.float64)
    if change_step <= window or change_step >= values.size:
        return None
    reference = float(values[max(0, change_step - window) : change_step].mean())
    if reference <= 0.0:
        return None
    target = tolerance * reference
    for step in range(change_step + 1, values.size):
        start = max(change_step, step - window + 1)
        if float(values[start : step + 1].mean()) >= target:
            return step - change_step
    return None
