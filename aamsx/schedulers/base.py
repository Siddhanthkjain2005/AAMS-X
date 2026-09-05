"""Scheduler interface, ablation flags and registry.

Every scheduler receives the same :class:`~aamsx.contracts.observation.DecisionContext`,
built once per step by :mod:`aamsx.experiments.context` from the scheduler's own
observation history.  That single shared builder is what makes the comparison in
the Algorithm Arena fair — no policy gets a privately better view of the world —
and it is where the ablation switches live, so "MAG-NTS without memory" really is
MAG-NTS with the memory input zeroed rather than a different program.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

import numpy as np

from aamsx.contracts.observation import ActionProposal, DecisionContext, Feedback
from aamsx.contracts.scenario import ReceiverSpec, RewardWeights


@dataclass(frozen=True, slots=True)
class AblationFlags:
    """Which intelligence components are active.

    Turning one off removes its *input*, not its code path, so an ablation cannot
    accidentally change anything else about the policy.
    """

    memory: bool = True
    information_gain: bool = True
    change_detection: bool = True
    periodicity: bool = True
    temporal_encoder: bool = True
    uncertainty_exploration: bool = True
    neural_encoder: bool = False

    @property
    def label(self) -> str:
        if all(
            (
                self.memory,
                self.information_gain,
                self.change_detection,
                self.periodicity,
                self.temporal_encoder,
                self.uncertainty_exploration,
            )
        ):
            return "full"
        active = [
            name
            for name, on in (
                ("Mem", self.memory),
                ("IG", self.information_gain),
                ("CD", self.change_detection),
                ("Per", self.periodicity),
                ("Enc", self.temporal_encoder),
                ("Unc", self.uncertainty_exploration),
            )
            if on
        ]
        return "+".join(active) if active else "none"

    def to_dict(self) -> dict[str, bool]:
        return {
            "memory": self.memory,
            "information_gain": self.information_gain,
            "change_detection": self.change_detection,
            "periodicity": self.periodicity,
            "temporal_encoder": self.temporal_encoder,
            "uncertainty_exploration": self.uncertainty_exploration,
            "neural_encoder": self.neural_encoder,
        }


@dataclass(frozen=True, slots=True)
class SchedulerSetup:
    """Everything a scheduler learns about the problem before it starts."""

    n_regions: int
    window_size: int
    n_anchors: int
    horizon: int
    budget: float
    receiver: ReceiverSpec
    reward: RewardWeights
    seed: int = 0
    flags: AblationFlags = field(default_factory=AblationFlags)


@runtime_checkable
class Scheduler(Protocol):
    """The complete scheduler contract."""

    name: str
    display_name: str
    description: str

    def reset(self, setup: SchedulerSetup) -> None: ...

    def select(self, context: DecisionContext) -> ActionProposal: ...

    def update(self, feedback: Feedback) -> None: ...

    def snapshot(self) -> dict[str, object]: ...


class BaseScheduler:
    """Shared bookkeeping: setup, RNG, step counter and a default snapshot."""

    name = "base"
    display_name = "Base"
    description = ""
    #: Marks policies whose action value is a stochastic draw, so the UI can say so.
    stochastic = False

    def __init__(self) -> None:
        self.setup: SchedulerSetup | None = None
        self.rng = np.random.default_rng(0)
        self.step = 0

    def reset(self, setup: SchedulerSetup) -> None:
        self.setup = setup
        self.rng = np.random.default_rng(setup.seed)
        self.step = 0

    @property
    def config(self) -> SchedulerSetup:
        if self.setup is None:
            raise RuntimeError(f"{type(self).__name__}.reset() must be called before use")
        return self.setup

    def update(self, feedback: Feedback) -> None:  # pragma: no cover - overridden
        self.step += 1

    def snapshot(self) -> dict[str, object]:
        return {"name": self.name, "step": self.step}

    # ---- helpers shared by the window-scoring policies ------------------------

    def window_sum(self, per_region: np.ndarray, window_size: int) -> np.ndarray:
        """Sum a per-region quantity over every contiguous window."""
        values = np.asarray(per_region, dtype=np.float64)
        if window_size <= 1:
            return values.copy()
        cumulative = np.concatenate(([0.0], np.cumsum(values)))
        anchors = values.size - window_size + 1
        return cumulative[window_size : window_size + anchors] - cumulative[:anchors]

    def switch_penalty(self, context: DecisionContext) -> np.ndarray:
        """Normalised retune distance for every candidate anchor."""
        n_anchors = self.config.n_anchors
        if context.previous_regions is None or n_anchors <= 1:
            return np.zeros(n_anchors)
        previous = float(context.previous_regions[0])
        return np.abs(np.arange(n_anchors, dtype=np.float64) - previous) / (n_anchors - 1)

    def proposal(
        self,
        anchor: int,
        *,
        value: float,
        factors: dict[str, float],
        per_region_value: np.ndarray | None = None,
        notes: tuple[str, ...] = (),
        exploration_rate: float = 0.0,
    ) -> ActionProposal:
        window = self.config.window_size
        regions = np.arange(anchor, anchor + window, dtype=np.int32)
        return ActionProposal(
            regions=regions,
            action_value=float(value),
            factors=factors,
            per_region_value=per_region_value,
            notes=notes,
            exploration_rate=float(exploration_rate),
        )


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

_REGISTRY: dict[str, type[BaseScheduler]] = {}


def register[SchedulerClass: type[BaseScheduler]](cls: SchedulerClass) -> SchedulerClass:
    """Class decorator that publishes a scheduler under its ``name``."""
    key = getattr(cls, "name", None)
    if not key:
        raise ValueError(f"{cls.__name__} must define a non-empty name")
    if key in _REGISTRY and _REGISTRY[key] is not cls:
        raise ValueError(f"scheduler name {key!r} is already registered")
    _REGISTRY[key] = cls
    return cls


def available() -> tuple[str, ...]:
    return tuple(_REGISTRY)


def describe_all() -> list[dict[str, object]]:
    return [
        {
            "name": cls.name,
            "display_name": cls.display_name,
            "description": cls.description,
            "stochastic": bool(getattr(cls, "stochastic", False)),
            "uses_memory": getattr(cls, "uses_memory", False),
            "uses_information_gain": getattr(cls, "uses_information_gain", False),
            "family": getattr(cls, "family", "baseline"),
        }
        for cls in _REGISTRY.values()
    ]


def create(name: str, **kwargs: object) -> Scheduler:
    try:
        cls = _REGISTRY[name]
    except KeyError as exc:
        raise KeyError(
            f"unknown scheduler {name!r}; registered: {', '.join(sorted(_REGISTRY))}"
        ) from exc
    return cls(**kwargs)  # type: ignore[return-value]
