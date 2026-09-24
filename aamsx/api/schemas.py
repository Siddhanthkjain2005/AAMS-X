"""Pydantic request/response models for the HTTP API.

These are deliberately separate from the internal dataclasses in
:mod:`aamsx.contracts`: the wire format is allowed to evolve for the UI's
convenience without dragging the scientific core along, and validation errors are
caught at the edge with a message a user can act on.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SchedulerName = str


class AblationRequest(BaseModel):
    """Which intelligence components to enable."""

    memory: bool = True
    information_gain: bool = True
    change_detection: bool = True
    periodicity: bool = True
    temporal_encoder: bool = True
    uncertainty_exploration: bool = True
    neural_encoder: bool = False


class ReceiverRequest(BaseModel):
    window_size: int = Field(default=4, ge=1, le=64)
    noise_db: float = Field(default=0.4, ge=0.0, le=20.0)
    cost_per_observation: float = Field(default=1.0, gt=0.0, le=100.0)
    switch_cost: float = Field(default=0.15, ge=0.0, le=10.0)
    settling_penalty_db: float = Field(default=0.0, ge=0.0, le=10.0)


class RewardRequest(BaseModel):
    detection: float = Field(default=1.0, ge=0.0, le=10.0)
    information: float = Field(default=0.35, ge=0.0, le=10.0)
    delay: float = Field(default=0.50, ge=0.0, le=10.0)
    false_alarm: float = Field(default=0.50, ge=0.0, le=10.0)
    switching: float = Field(default=0.05, ge=0.0, le=10.0)


class MagWeightsRequest(BaseModel):
    detection: float = Field(default=0.94, ge=0.0, le=5.0)
    information: float = Field(default=0.07, ge=0.0, le=5.0)
    memory: float = Field(default=0.57, ge=0.0, le=5.0)
    periodicity: float = Field(default=0.27, ge=0.0, le=5.0)
    uncertainty: float = Field(default=0.23, ge=0.0, le=5.0)
    recency: float = Field(default=0.17, ge=0.0, le=5.0)
    cost: float = Field(default=0.29, ge=0.0, le=5.0)
    switching: float = Field(default=0.10, ge=0.0, le=5.0)


class SegmentRequest(BaseModel):
    recording_id: str
    start_step: int = Field(ge=0)
    n_steps: int = Field(gt=0, le=20000)
    label: str = ""
    phase: str = ""


class ScenarioRequest(BaseModel):
    """A custom scenario assembled in the Experiment Lab."""

    scenario_id: str = "custom"
    name: str = "Custom Scenario"
    description: str = ""
    family: str = "intermittent"
    segments: list[SegmentRequest] = Field(min_length=1, max_length=8)
    n_regions: int = Field(default=48, ge=8, le=256)
    time_bin: int = Field(default=4, ge=1, le=600)
    freq_range_mhz: tuple[float, float] | None = None
    receiver: ReceiverRequest = Field(default_factory=ReceiverRequest)
    reward: RewardRequest = Field(default_factory=RewardRequest)
    budget: float | None = Field(default=None, gt=0.0)
    split: Literal["train", "validation", "unseen"] = "train"

    @field_validator("segments")
    @classmethod
    def _window_fits(cls, value: list[SegmentRequest]) -> list[SegmentRequest]:
        if sum(segment.n_steps for segment in value) > 20000:
            raise ValueError("total horizon must not exceed 20000 environment steps")
        return value


class EpisodeRequest(BaseModel):
    """Start one streamed episode."""

    scenario_id: str | None = None
    scenario: ScenarioRequest | None = None
    scheduler: SchedulerName = "mag-nts"
    seed: int = Field(default=0, ge=0, le=2**31 - 1)
    ablation: AblationRequest = Field(default_factory=AblationRequest)
    mag_weights: MagWeightsRequest | None = None
    pace_hz: float = Field(default=30.0, ge=0.0, le=2000.0)
    frame_stride: int = Field(default=1, ge=1, le=100)


class BatchRequest(BaseModel):
    """Start an Algorithm Arena or Ablation Lab batch."""

    scenario_id: str | None = None
    scenario: ScenarioRequest | None = None
    schedulers: list[SchedulerName] | None = None
    seeds: int = Field(default=5, ge=1, le=40)
    workers: int | None = Field(default=None, ge=1, le=64)


class ReportRequest(BaseModel):
    experiment_ids: list[str] = Field(min_length=1, max_length=24)
    title: str = "AAMS-X Experiment Report"
    notes: str = ""


class WindowQuery(BaseModel):
    """Search the measured window index."""

    where: str = "TRUE"
    order_by: str = "occupancy DESC"
    limit: int = Field(default=25, ge=1, le=500)

    @field_validator("where", "order_by")
    @classmethod
    def _no_statements(cls, value: str) -> str:
        lowered = value.lower()
        banned = (";", "--", "/*", "attach", "copy", "install", "pragma", "create", "drop")
        if any(token in lowered for token in banned):
            raise ValueError("only simple SQL predicates are accepted here")
        return value


class StatusResponse(BaseModel):
    version: str
    scheduler_version: str
    data_mode: str
    network_allowed: bool
    recordings: int
    windows_indexed: int
    presets: int
    schedulers: list[dict[str, Any]]
    neural_available: bool
    deep_rl_available: bool
    experiments: dict[str, int]
    cache_mb: float
    warnings: list[str]
