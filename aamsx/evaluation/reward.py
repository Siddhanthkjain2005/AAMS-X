"""The multi-objective reward.

    R_t = w_D * detection + w_I * information - w_T * delay - w_F * false_alarm
          - w_S * switching

Every term is normalised to roughly [0, 1] before weighting, so the weights are
comparable and a judge can reason about them:

``detection``
    hits in the observed window, divided by window size.
``information``
    entropy the belief filter *actually* lost on this update, in bits per region.
    Realised, not predicted — a scheduler cannot earn information reward by
    forecasting a large gain that failed to arrive.
``delay``
    mean normalised age of activity that is live right now and still undetected.
    This is the term that punishes leaving a region unwatched.
``false_alarm``
    detections in the window that ground truth does not support.
``switching``
    fraction of the band crossed by this retune.

AAMS-X does not claim these weights are correct.  They are exposed in the
Experiment Lab precisely so their influence can be measured, and
``evaluation/pareto.py`` maps the trade-off surface rather than asserting a point
on it.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aamsx.contracts.observation import Observation
from aamsx.contracts.scenario import RewardWeights

LOG2 = float(np.log(2.0))


@dataclass(frozen=True, slots=True)
class StepReward:
    total: float
    terms: dict[str, float]
    hits: int
    false_alarms: int
    missed_in_window: int
    realised_information_bits: float


class RewardModel:
    """Turns one scored observation into a reward plus its decomposition."""

    def __init__(self, weights: RewardWeights, window_size: int) -> None:
        self.weights = weights
        self.window_size = max(1, int(window_size))

    def score(
        self,
        observation: Observation,
        true_occupied: np.ndarray,
        *,
        entropy_before: float,
        entropy_after: float,
        pending_delay: float,
        retune_fraction: float,
    ) -> StepReward:
        detected = observation.detected
        hits = int((detected & true_occupied).sum())
        false_alarms = int((detected & ~true_occupied).sum())
        missed = int((~detected & true_occupied).sum())

        information_bits = max(0.0, (entropy_before - entropy_after) / LOG2)
        weights = self.weights
        terms = {
            "detection": weights.detection * (hits / self.window_size),
            "information": weights.information * (information_bits / self.window_size),
            "delay": -weights.delay * float(pending_delay),
            "false_alarm": -weights.false_alarm * (false_alarms / self.window_size),
            "switching": -weights.switching * float(retune_fraction),
        }
        if not observation.available:
            # No data was published for this interval: nothing earned, nothing
            # charged, and the delay term still applies because activity that is
            # going unwatched is going unwatched regardless of why.
            terms["detection"] = 0.0
            terms["information"] = 0.0
            terms["false_alarm"] = 0.0
            terms["switching"] = 0.0
        return StepReward(
            total=float(sum(terms.values())),
            terms={key: round(float(value), 6) for key, value in terms.items()},
            hits=hits,
            false_alarms=false_alarms,
            missed_in_window=missed,
            realised_information_bits=float(information_bits),
        )
