"""The replay environment: real measurements behind a partial-observability wall.

The environment owns :class:`~aamsx.environment.truth.EnvironmentTruth` and hands
out nothing but :class:`~aamsx.contracts.observation.Observation` objects for the
window a scheduler chose to pay for.

Leakage is prevented three ways, and all three are tested:

1. **Structurally** — a scheduler is never passed the environment, only a
   :class:`~aamsx.contracts.observation.DecisionContext` built from its own
   observation history.
2. **Dynamically** — :meth:`ReplayEnvironment.sealed` closes every truth-reading
   accessor for the duration of a decision, so a scheduler that somehow held a
   reference still cannot read hidden state.
3. **Behaviourally** — ``tests/test_no_leakage.py`` scrambles the truth after a
   context has been built and asserts every scheduler picks the same action.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import numpy as np

from aamsx.contracts.observation import Observation
from aamsx.contracts.scenario import ScenarioSpec
from aamsx.environment.truth import EnvironmentTruth, build_truth
from aamsx.receiver.model import ReceiverModel


class LeakageError(RuntimeError):
    """Raised when hidden environment state is touched while sealed for a decision."""


@dataclass(frozen=True, slots=True)
class StepOutcome:
    """Everything one environment step produced.

    ``observation`` is public and goes to the scheduler.  Every other field is
    truth-derived and goes only to the evaluation layer.
    """

    observation: Observation
    true_occupied: np.ndarray  # (W,) bool, for the observed regions
    true_margin_db: np.ndarray  # (W,) float32
    occupied_total: int  # occupied regions across the whole band this step
    oracle_best_count: int  # best achievable in-window detections this step
    window_size: int
    segment_index: int
    changed_segment: bool

    @property
    def hits(self) -> int:
        return int((self.observation.detected & self.true_occupied).sum())

    @property
    def false_alarms(self) -> int:
        return int((self.observation.detected & ~self.true_occupied).sum())

    @property
    def missed_in_window(self) -> int:
        return int((~self.observation.detected & self.true_occupied).sum())

    @property
    def missed_outside_window(self) -> int:
        return int(self.occupied_total - self.true_occupied.sum())


class ReplayEnvironment:
    """A partially observable episode driven entirely by cached real measurements."""

    def __init__(self, spec: ScenarioSpec, truth: EnvironmentTruth, *, seed: int = 0) -> None:
        if truth.n_regions != spec.n_regions:
            raise ValueError(
                f"truth has {truth.n_regions} regions but scenario declares {spec.n_regions}"
            )
        self.spec = spec
        self.seed = int(seed)
        self.receiver = ReceiverModel(spec.receiver, truth.n_regions)
        self._truth = truth
        self._oracle_counts = truth.oracle_window_counts(spec.receiver.window_size)
        self._sealed = False
        self.rng = np.random.default_rng(seed)
        self.step_index = 0
        self.previous_anchor: int | None = None
        self.budget_spent = 0.0

    # ---- public geometry (never hidden state) --------------------------------

    @property
    def n_regions(self) -> int:
        return self._truth.n_regions

    @property
    def horizon(self) -> int:
        return min(self._truth.horizon, self.spec.horizon)

    @property
    def window_size(self) -> int:
        return self.spec.receiver.window_size

    @property
    def n_anchors(self) -> int:
        return self.receiver.n_anchors

    @property
    def budget(self) -> float:
        return self.spec.effective_budget()

    @property
    def budget_remaining(self) -> float:
        return max(0.0, self.budget - self.budget_spent)

    @property
    def done(self) -> bool:
        return self.step_index >= self.horizon or self.budget_remaining <= 0.0

    def reset(self) -> None:
        self.rng = np.random.default_rng(self.seed)
        self.step_index = 0
        self.previous_anchor = None
        self.budget_spent = 0.0

    # ---- the observability wall ---------------------------------------------

    @contextmanager
    def sealed(self) -> Iterator[None]:
        """Close every truth accessor while a scheduler is deciding."""
        previous = self._sealed
        self._sealed = True
        try:
            yield
        finally:
            self._sealed = previous

    def _require_unsealed(self, what: str) -> None:
        if self._sealed:
            raise LeakageError(
                f"hidden environment state ({what}) was accessed while the "
                "environment was sealed for a scheduling decision"
            )

    @property
    def truth(self) -> EnvironmentTruth:
        """Evaluation-only handle on hidden state."""
        self._require_unsealed("truth")
        return self._truth

    def oracle_best_count(self, step: int) -> int:
        self._require_unsealed("oracle_best_count")
        return int(self._oracle_counts[step].max())

    # ---- stepping ------------------------------------------------------------

    def step(self, anchor: int) -> StepOutcome:
        """Tune to ``anchor``, dwell for one step, and return what was measured."""
        if self.done:
            raise RuntimeError("episode is finished; call reset() before stepping again")
        step = self.step_index
        regions = self.receiver.window(anchor)
        resolved_anchor = int(regions[0])

        moved = self.receiver.retune_fraction(resolved_anchor, self.previous_anchor)
        noise = self.receiver.effective_noise_db(moved)
        cost = self.receiver.cost(resolved_anchor, self.previous_anchor)

        true_margin = self._truth.margin_db[step, regions]
        true_occupied = self._truth.occupied[step, regions]
        available = bool(self._truth.available[step])

        if available:
            measured, detected, confidence = self.receiver.measure(
                true_margin, noise_db=noise, rng=self.rng
            )
        else:
            # The archive published nothing for this interval. AAMS-X reports the
            # dropout instead of interpolating over it, and charges nothing.
            measured = np.zeros(regions.size, dtype=np.float32)
            detected = np.zeros(regions.size, dtype=bool)
            confidence = np.zeros(regions.size, dtype=np.float32)
            cost = 0.0

        observation = Observation(
            step=step,
            regions=regions,
            measured_db=measured,
            detected=detected,
            threshold_db=np.zeros(regions.size, dtype=np.float32),
            confidence=confidence,
            cost=cost,
            available=available,
            t_sec=float(self._truth.t_utc_sec[step]),
        )
        segment = int(self._truth.segment_of_step[step])
        changed = step > 0 and segment != int(self._truth.segment_of_step[step - 1])

        outcome = StepOutcome(
            observation=observation,
            true_occupied=true_occupied.copy(),
            true_margin_db=true_margin.astype(np.float32),
            occupied_total=int(self._truth.occupied[step].sum()),
            oracle_best_count=int(self._oracle_counts[step].max()),
            window_size=self.window_size,
            segment_index=segment,
            changed_segment=changed,
        )
        self.previous_anchor = resolved_anchor
        self.budget_spent += cost
        self.step_index += 1
        return outcome


def make_environment(spec: ScenarioSpec, *, seed: int = 0, settings=None) -> ReplayEnvironment:
    """Load a scenario's real windows and wrap them in an environment."""
    truth = build_truth(spec, settings=settings)
    return ReplayEnvironment(spec, truth, seed=seed)
