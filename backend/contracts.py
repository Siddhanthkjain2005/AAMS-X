"""The complete policy-facing surface. No environment, dataset, or evaluator imports.

Policies receive PublicReceiver, DecisionContext, and immutable Observation values.
The experiment runner owns everything else, including random detector realizations.
"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

SourceCategory = Literal["OFFICIAL_SYNTHETIC_RADAR", "CONTROLLED_SIMULATION", "REAL_MEASURED_RF"]
Algorithm = Literal[
    "magnts", "fixed", "random", "thompson", "ucb", "no_memory", "no_information", "no_change"
]


class ReceiverConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)
    bands: int = Field(48, ge=8, le=128)
    window_width: int = Field(4, ge=1, le=32)
    frequency_min_mhz: float = Field(2000, ge=0)
    frequency_max_mhz: float = Field(6000, gt=0)
    slot_ms: float = Field(100, ge=1, le=60000)
    min_dwell_ms: float = Field(10, ge=0.1, le=1000)
    retune_ms: float = Field(8, ge=0, le=1000)
    scan_latency_ms: float = Field(1, ge=0, le=100)
    noise_floor_db: float = Field(-96, ge=-180, le=100)
    noise_std_db: float = Field(1.4, ge=0.05, le=12)
    threshold_db: float = Field(5, ge=0.1, le=30)
    snr_db: float = Field(12, ge=-5, le=40)
    false_alarm_probability: float = Field(0.003, ge=0, le=0.5)
    miss_probability: float = Field(0.03, ge=0, le=0.9)
    switching_cost: float = Field(0.3, ge=0, le=5)

    @model_validator(mode="after")
    def valid_geometry(self):
        if self.window_width > self.bands:
            raise ValueError("Instantaneous bandwidth cannot exceed the monitored spectrum")
        if self.frequency_max_mhz <= self.frequency_min_mhz:
            raise ValueError("Frequency bounds must be increasing")
        if self.slot_ms - self.retune_ms - self.scan_latency_ms < self.min_dwell_ms:
            raise ValueError("The time slot must fit minimum dwell, retuning, and scan latency")
        return self


class EmitterSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: Literal["continuous", "periodic", "burst", "hopping", "agile", "random", "changing"]
    band: int = Field(8, ge=0, le=127)
    width: int = Field(1, ge=1, le=8)
    start: int = Field(0, ge=0)
    stop: int | None = Field(None, ge=1)
    period: int = Field(20, ge=4, le=300)
    duration: int = Field(5, ge=1, le=100)
    duty: float = Field(0.5, ge=0, le=1)
    snr_offset: float = Field(0, ge=-20, le=20)


class ExperimentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed: int = Field(42, ge=0, le=2**32 - 1)
    scenario: str = "sudden"
    horizon: int = Field(360, ge=24, le=2000)
    receiver: ReceiverConfig = Field(default_factory=ReceiverConfig)
    algorithms: list[Algorithm] = Field(default_factory=lambda: ["fixed", "magnts"], min_length=1, max_length=8)
    dataset_id: str = "simulation"
    emitters: list[EmitterSpec] | None = Field(None, max_length=24)

    @model_validator(mode="after")
    def unique_algorithms(self):
        if len(set(self.algorithms)) != len(self.algorithms):
            raise ValueError("Algorithms must be unique")
        if self.emitters and any(e.band + e.width > self.receiver.bands for e in self.emitters):
            raise ValueError("Custom emitter frequency region is outside the monitored spectrum")
        return self


@dataclass(frozen=True, slots=True)
class PublicReceiver:
    bands: int
    width: int
    slot_ms: float
    retune_ms: float
    switching_cost: float

    @classmethod
    def from_config(cls, config: ReceiverConfig):
        return cls(config.bands, config.window_width, config.slot_ms, config.retune_ms, config.switching_cost)

    def retune_cost(self, previous: int | None, start: int) -> float:
        if previous is None or previous == start:
            return 0.0
        return self.retune_ms / self.slot_ms + self.switching_cost * abs(start - previous) / max(
            1, self.bands - self.width
        )


@dataclass(frozen=True, slots=True)
class Action:
    start: int
    width: int

    @property
    def bands(self) -> tuple[int, ...]:
        return tuple(range(self.start, self.start + self.width))


@dataclass(frozen=True, slots=True)
class BandObservation:
    band: int
    energy: float | None
    detected: bool
    confidence: float
    noise_estimate: float
    valid: bool = True


@dataclass(frozen=True, slots=True)
class Observation:
    step: int
    timestamp_ms: float
    window: Action
    values: tuple[BandObservation, ...]
    effective_dwell_ms: float
    retune_cost: float

    def __post_init__(self):
        if tuple(v.band for v in self.values) != self.window.bands:
            raise ValueError("An observation must contain exactly its selected contiguous window")


@dataclass(frozen=True, slots=True)
class DecisionContext:
    step: int
    previous_start: int | None
