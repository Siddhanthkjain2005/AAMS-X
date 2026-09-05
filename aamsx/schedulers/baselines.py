"""Deterministic and memory-free baselines.

These exist to be beaten honestly.  Each one is the textbook algorithm, given the
same context, the same environment, the same seed and the same budget as MAG-NTS —
no artificial handicaps.  Round-robin in particular is a genuinely strong baseline
on a persistent environment, and it should win there.
"""

from __future__ import annotations

import numpy as np

from aamsx.contracts.observation import ActionProposal, DecisionContext, Feedback
from aamsx.schedulers.base import BaseScheduler, SchedulerSetup, register


@register
class RoundRobinScheduler(BaseScheduler):
    """Sweep the band in non-overlapping windows, forever."""

    name = "round-robin"
    display_name = "Round Robin"
    family = "deterministic"
    description = (
        "Sweeps the band in fixed non-overlapping steps. Perfectly fair coverage and "
        "zero adaptation: the control case for 'does knowing anything actually help?'"
    )

    def reset(self, setup: SchedulerSetup) -> None:
        super().reset(setup)
        self._cursor = 0

    def select(self, context: DecisionContext) -> ActionProposal:
        stride = max(1, self.config.window_size)
        anchor = int(self._cursor % self.config.n_anchors)
        self._cursor = (self._cursor + stride) % max(1, self.config.n_anchors)
        return self.proposal(
            anchor,
            value=0.0,
            factors={"sweep_position": anchor / max(1, self.config.n_anchors - 1)},
            notes=("fixed sweep, no adaptation",),
        )

    def update(self, feedback: Feedback) -> None:
        self.step += 1


@register
class RandomScanScheduler(BaseScheduler):
    """Uniformly random retuning."""

    name = "random"
    display_name = "Random Scan"
    family = "deterministic"
    stochastic = True
    description = (
        "Picks a uniformly random window every step. Unbiased coverage in expectation, "
        "and the reference point for how much structure the other policies exploit."
    )

    def select(self, context: DecisionContext) -> ActionProposal:
        anchor = int(self.rng.integers(self.config.n_anchors))
        return self.proposal(
            anchor,
            value=0.0,
            factors={"uniform_probability": 1.0 / max(1, self.config.n_anchors)},
            notes=("uniform random",),
            exploration_rate=1.0,
        )

    def update(self, feedback: Feedback) -> None:
        self.step += 1


@register
class UCBScheduler(BaseScheduler):
    """UCB1 over window anchors, with observations shared through regions.

    Textbook UCB1 treats each window as an independent arm, which wastes most of
    what an observation teaches: windows overlap, so looking at anchor 7 also says
    something about anchors 5, 6, 8 and 9.  This implementation keeps per-*region*
    statistics and sums them across a window, which is the same algorithm applied
    at the level where the information actually arrives.
    """

    name = "ucb"
    display_name = "UCB1"
    family = "bandit"
    description = (
        "Upper Confidence Bound with per-region statistics. Deterministic optimism: "
        "regions are ranked by empirical hit rate plus a confidence bonus that shrinks "
        "with every visit."
    )

    def __init__(self, exploration: float = 1.4) -> None:
        super().__init__()
        self.exploration = float(exploration)

    def reset(self, setup: SchedulerSetup) -> None:
        super().reset(setup)
        n = setup.n_regions
        self._successes = np.zeros(n)
        self._visits = np.zeros(n)
        self._total = 0

    def select(self, context: DecisionContext) -> ActionProposal:
        visits = np.maximum(self._visits, 1e-9)
        mean = self._successes / visits
        total = max(self._total, 1)
        bonus = self.exploration * np.sqrt(np.log(total + 1.0) / visits)
        # Never-visited regions get an infinite bonus, so UCB1 sweeps once first.
        bonus = np.where(self._visits > 0, bonus, 1e6)
        score = mean + bonus

        window = self.config.window_size
        values = self.window_sum(score, window) / window
        anchor = int(np.argmax(values))
        chosen = slice(anchor, anchor + window)
        return self.proposal(
            anchor,
            value=float(values[anchor]),
            factors={
                "empirical_hit_rate": float(mean[chosen].mean()),
                "confidence_bonus": float(np.clip(bonus[chosen], 0.0, 10.0).mean()),
                "visits": float(self._visits[chosen].mean()),
            },
            per_region_value=np.clip(score, 0.0, 10.0),
            notes=("deterministic optimism",),
        )

    def update(self, feedback: Feedback) -> None:
        observation = feedback.observation
        if observation.available:
            self._visits[observation.regions] += 1.0
            self._successes[observation.regions] += observation.detected.astype(np.float64)
            self._total += 1
        self.step += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "name": self.name,
            "step": self.step,
            "visited_regions": int((self._visits > 0).sum()),
            "mean_hit_rate": round(
                float((self._successes / np.maximum(self._visits, 1.0)).mean()), 5
            ),
        }
