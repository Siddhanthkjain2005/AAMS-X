"""Scenario contracts — how a real recording becomes a scheduling problem.

AAMS-X contains no synthetic environment.  A scenario is an ordered list of
*segments*, each naming a real cached recording and a real time window inside
it.  Splicing segments is how the platform produces distribution shift and
recurring context without inventing data: the change point is the boundary
between two genuinely different measured environments, so its timing is known
exactly while the activity itself stays real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ScenarioFamily = Literal[
    "persistent",
    "periodic",
    "intermittent",
    "bursting",
    "rapidly-changing",
    "noisy",
    "distribution-shift",
    "recurring-context",
    "unseen-combination",
    "budget-constrained",
]

SplitRole = Literal["train", "validation", "unseen"]


@dataclass(frozen=True, slots=True)
class ReceiverSpec:
    """The sensing constraint: how much of the band the receiver can look at."""

    window_size: int = 4
    """Contiguous regions observable in a single step."""

    noise_db: float = 0.4
    """Std-dev of receiver noise added to each dwell measurement, in dB.

    Calibrated against the real margin distribution in the cache rather than
    picked for convenience: at 0.4 dB the receiver achieves a 0.90 cell detection
    rate at a 0.094 false-alarm rate (Youden's J = 0.81), which leaves the
    scheduling problem — not the front end — as the thing being measured. The
    High Noise scenario raises it deliberately.
    """

    cost_per_observation: float = 1.0
    switch_cost: float = 0.15
    """Cost of retuning, proportional to the normalised distance moved."""

    settling_penalty_db: float = 0.0
    """Optional sensitivity loss on the step immediately after a large retune."""

    def to_dict(self) -> dict[str, object]:
        return {
            "window_size": self.window_size,
            "noise_db": self.noise_db,
            "cost_per_observation": self.cost_per_observation,
            "switch_cost": self.switch_cost,
            "settling_penalty_db": self.settling_penalty_db,
        }


@dataclass(frozen=True, slots=True)
class RewardWeights:
    """Interpretable multi-objective utility weights (all exposed in the UI).

    ``delay`` deserves a note, because its value decides which policy wins.  With a
    token delay weight the objective collapses into "maximise raw detections", and
    the winning strategy is to camp on the few busiest regions and ignore the rest
    of the band — measured, not asserted: at ``delay=0.10`` plain discounted
    Thompson sampling beats every richer policy on this reward while detecting 30%
    fewer distinct events.  That is a defect in the objective, not a virtue of the
    policy.  AAMS-X exists to find activity across a band it cannot fully observe,
    so leaving live activity unwatched has to cost something comparable to finding
    it.  ``delay=0.50`` makes those two terms commensurate.

    No weighting is claimed to be universally right.  ``scripts/sensitivity.py``
    sweeps this weight and reports how the ranking changes, and
    :mod:`aamsx.evaluation.pareto` refuses the scalarisation entirely.
    """

    detection: float = 1.0
    information: float = 0.35
    delay: float = 0.50
    false_alarm: float = 0.50
    switching: float = 0.05

    def to_dict(self) -> dict[str, float]:
        return {
            "detection": self.detection,
            "information": self.information,
            "delay": self.delay,
            "false_alarm": self.false_alarm,
            "switching": self.switching,
        }


@dataclass(frozen=True, slots=True)
class SegmentSpec:
    """One contiguous slice of one real cached recording."""

    recording_id: str
    """``STATION/YYYYMMDD`` as written by the ingestion cache."""

    start_step: int
    """Offset in the recording's native cadence (0.25 s for e-CALLISTO)."""

    n_steps: int
    """Length in *environment* steps, after time binning."""

    label: str = ""
    phase: str = ""
    """Free-form phase tag, e.g. ``A``, ``B``, ``A-prime``."""

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_id": self.recording_id,
            "start_step": self.start_step,
            "n_steps": self.n_steps,
            "label": self.label,
            "phase": self.phase,
        }


@dataclass(frozen=True, slots=True)
class ScenarioSpec:
    """A complete, reproducible scheduling problem built from real measurements."""

    scenario_id: str
    name: str
    description: str
    family: ScenarioFamily
    segments: tuple[SegmentSpec, ...]
    n_regions: int = 48
    time_bin: int = 4
    """Native samples aggregated per environment step (4 x 0.25 s = 1 s)."""

    freq_range_mhz: tuple[float, float] | None = None
    receiver: ReceiverSpec = field(default_factory=ReceiverSpec)
    reward: RewardWeights = field(default_factory=RewardWeights)
    budget: float | None = None
    """Total sensing budget. ``None`` means one observation per step."""

    split: SplitRole = "train"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def horizon(self) -> int:
        return sum(segment.n_steps for segment in self.segments)

    @property
    def change_points(self) -> tuple[int, ...]:
        """Environment steps at which the underlying recording changes."""
        boundaries: list[int] = []
        cursor = 0
        for segment in self.segments[:-1]:
            cursor += segment.n_steps
            boundaries.append(cursor)
        return tuple(boundaries)

    @property
    def phase_spans(self) -> tuple[tuple[str, int, int], ...]:
        spans: list[tuple[str, int, int]] = []
        cursor = 0
        for segment in self.segments:
            spans.append((segment.phase or segment.label, cursor, cursor + segment.n_steps))
            cursor += segment.n_steps
        return tuple(spans)

    def effective_budget(self) -> float:
        if self.budget is not None:
            return float(self.budget)
        return float(self.horizon) * self.receiver.cost_per_observation

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ScenarioSpec:
        """Rebuild a spec from :meth:`to_dict`.

        Used to replay a stored experiment: the registry keeps the serialised
        scenario, and replay has to reconstruct exactly that problem rather than a
        freshly built preset, which could have drifted with the window index.
        The derived keys (``horizon``, ``change_points``, ``effective_budget`` …)
        are ignored on the way back in because they are recomputed from the
        segments, so a tampered file cannot inject an inconsistent horizon.
        """
        segments = tuple(
            SegmentSpec(
                recording_id=str(segment["recording_id"]),
                start_step=int(segment["start_step"]),
                n_steps=int(segment["n_steps"]),
                label=str(segment.get("label", "")),
                phase=str(segment.get("phase", "")),
            )
            for segment in payload["segments"]
        )
        freq_range = payload.get("freq_range_mhz")
        return cls(
            scenario_id=str(payload["scenario_id"]),
            name=str(payload["name"]),
            description=str(payload.get("description", "")),
            family=payload.get("family", "static"),
            segments=segments,
            n_regions=int(payload.get("n_regions", 48)),
            time_bin=int(payload.get("time_bin", 4)),
            freq_range_mhz=(float(freq_range[0]), float(freq_range[1])) if freq_range else None,
            receiver=ReceiverSpec(**payload.get("receiver", {})),
            reward=RewardWeights(**payload.get("reward", {})),
            budget=payload.get("budget"),
            split=payload.get("split", "train"),
            tags=tuple(payload.get("tags", ())),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "description": self.description,
            "family": self.family,
            "segments": [segment.to_dict() for segment in self.segments],
            "n_regions": self.n_regions,
            "time_bin": self.time_bin,
            "freq_range_mhz": list(self.freq_range_mhz) if self.freq_range_mhz else None,
            "receiver": self.receiver.to_dict(),
            "reward": self.reward.to_dict(),
            "budget": self.budget,
            "effective_budget": self.effective_budget(),
            "horizon": self.horizon,
            "change_points": list(self.change_points),
            "phase_spans": [list(span) for span in self.phase_spans],
            "split": self.split,
            "tags": list(self.tags),
        }
