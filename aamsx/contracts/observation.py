"""Observation, decision and feedback contracts.

These types are the only channel between the environment and a scheduler.
A scheduler receives a :class:`DecisionContext` — assembled purely from its own
past observations — and answers with an :class:`ActionProposal`.  It never
receives an environment handle, so hidden state cannot leak by construction;
:mod:`tests.test_no_leakage` proves it empirically as well.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

import numpy as np

# Names of the factors every explainable scheduler reports, in display order.
FACTOR_ORDER: tuple[str, ...] = (
    "predicted_activity",
    "posterior_confidence",
    "information_gain",
    "memory_similarity",
    "periodicity_score",
    "staleness",
    "uncertainty",
    "sensing_cost",
    "switching_penalty",
)


@dataclass(frozen=True, slots=True)
class Observation:
    """What the receiver actually measured at one step, for one window."""

    step: int
    regions: np.ndarray  # (W,) int32 region indices actually observed
    measured_db: np.ndarray  # (W,) float32 excess power incl. receiver noise
    detected: np.ndarray  # (W,) bool  measured above the region threshold
    threshold_db: np.ndarray  # (W,) float32 per-region decision threshold
    confidence: np.ndarray  # (W,) float32 distance from the boundary, in [0, 1]
    cost: float
    available: bool  # False when the archive had no data for this step
    t_sec: float

    @property
    def window_size(self) -> int:
        return int(self.regions.size)


@dataclass(frozen=True, slots=True)
class Feedback:
    """Ground-truth-scored outcome of one observation, used for learning and metrics.

    ``true_occupied`` is available because the *environment* scores the action
    after it was chosen.  Schedulers receive this object in :meth:`update`, which
    is the standard bandit feedback loop: you learn what you observed, never what
    you did not.
    """

    step: int
    observation: Observation
    true_occupied: np.ndarray  # (W,) bool, only for the observed regions
    reward: float
    reward_terms: dict[str, float]
    hits: int
    false_alarms: int
    misses_in_window: int
    budget_remaining: float


@dataclass(frozen=True, slots=True)
class ActionProposal:
    """A scheduler's decision plus the evidence behind it."""

    regions: np.ndarray  # (W,) int32 contiguous window the scheduler wants
    action_value: float
    factors: dict[str, float]  # decomposition for the selected window
    per_region_value: np.ndarray | None = None  # (R,) score of every candidate
    notes: tuple[str, ...] = field(default_factory=tuple)
    exploration_rate: float = 0.0

    @property
    def anchor(self) -> int:
        return int(self.regions[0])


@dataclass(slots=True)
class DecisionContext:
    """Everything a scheduler is allowed to know at decision time.

    Every array is derived from the scheduler's own observation history. Nothing
    in this structure is a function of unobserved environment state.
    """

    step: int
    n_regions: int
    window_size: int
    belief: np.ndarray  # (R,) P(region active now)
    uncertainty: np.ndarray  # (R,) posterior + epistemic uncertainty in [0, 1]
    staleness: np.ndarray  # (R,) normalised time since last observed
    steps_since_seen: np.ndarray  # (R,) int32
    observation_counts: np.ndarray  # (R,) int32
    hit_rate: np.ndarray  # (R,) empirical detections / observations
    information_gain: np.ndarray  # (R,) expected entropy reduction from observing region
    periodicity_score: np.ndarray  # (R,) recurrence prediction in [0, 1]
    periodicity_period: np.ndarray  # (R,) estimated period in steps, 0 = none
    sensing_cost: np.ndarray  # (n_anchors,) cost of anchoring the window here
    change_score: float
    change_flag: bool
    steps_since_change: int
    budget_remaining: float
    budget_fraction: float
    horizon: int
    temporal_features: np.ndarray  # (F,) global engineered features
    memory_similarity: float = 0.0
    memory_prior: np.ndarray | None = None  # (R,) retrieved action preference
    memory_context_id: int | None = None
    recent_rewards: np.ndarray | None = None
    previous_regions: np.ndarray | None = None

    def as_dict(self) -> dict[str, Any]:
        """Field-name to value mapping.

        Written against :func:`dataclasses.fields` rather than ``__dict__`` because
        this class is ``slots=True`` and therefore has no instance dictionary.
        """
        return {entry.name: getattr(self, entry.name) for entry in fields(self)}

    def freeze(self) -> DecisionContext:
        """Return a deep, read-only copy — used by the anti-leakage test."""
        copied: dict[str, Any] = {
            key: (value.copy() if isinstance(value, np.ndarray) else value)
            for key, value in self.as_dict().items()
        }
        clone = DecisionContext(**copied)
        for value in clone.as_dict().values():
            if isinstance(value, np.ndarray):
                value.flags.writeable = False
        return clone
