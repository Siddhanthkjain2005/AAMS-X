"""Shared helpers for the route modules: scenario resolution and error mapping."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from aamsx.api.schemas import (
    AblationRequest,
    MagWeightsRequest,
    ScenarioRequest,
)
from aamsx.contracts.scenario import (
    ReceiverSpec,
    RewardWeights,
    ScenarioSpec,
    SegmentSpec,
)
from aamsx.datasets.store import CacheMiss, get_recording
from aamsx.environment.scenarios import preset
from aamsx.schedulers.base import AblationFlags
from aamsx.schedulers.mag_nts import MagWeights


def to_flags(request: AblationRequest) -> AblationFlags:
    return AblationFlags(**request.model_dump())


def to_weights(request: MagWeightsRequest | None) -> MagWeights | None:
    return MagWeights(**request.model_dump()) if request is not None else None


def build_scenario(request: ScenarioRequest) -> ScenarioSpec:
    """Validate a custom scenario against the cache before it reaches the engine."""
    for segment in request.segments:
        try:
            record = get_recording(segment.recording_id)
        except CacheMiss as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        needed = segment.start_step + segment.n_steps * request.time_bin
        if needed > record.n_times:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{segment.recording_id} holds {record.n_times} samples; this segment "
                    f"needs {needed} (start {segment.start_step} + {segment.n_steps} steps "
                    f"x time_bin {request.time_bin}). Shorten the segment, lower the time "
                    f"bin, or start earlier."
                ),
            )
        if request.n_regions > record.n_channels:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"{segment.recording_id} has {record.n_channels} channels and cannot be "
                    f"split into {request.n_regions} regions."
                ),
            )
    if request.receiver.window_size > request.n_regions:
        raise HTTPException(
            status_code=422,
            detail=(
                f"receiver window ({request.receiver.window_size}) cannot exceed the number "
                f"of regions ({request.n_regions})"
            ),
        )
    return ScenarioSpec(
        scenario_id=request.scenario_id,
        name=request.name,
        description=request.description or "Custom scenario assembled in the Experiment Lab.",
        family=request.family,  # type: ignore[arg-type]
        segments=tuple(
            SegmentSpec(
                recording_id=segment.recording_id,
                start_step=segment.start_step,
                n_steps=segment.n_steps,
                label=segment.label,
                phase=segment.phase,
            )
            for segment in request.segments
        ),
        n_regions=request.n_regions,
        time_bin=request.time_bin,
        freq_range_mhz=request.freq_range_mhz,
        receiver=ReceiverSpec(**request.receiver.model_dump()),
        reward=RewardWeights(**request.reward.model_dump()),
        budget=request.budget,
        split=request.split,
        tags=("custom",),
    )


def resolve_scenario(scenario_id: str | None, scenario: ScenarioRequest | None) -> ScenarioSpec:
    """Either a named preset or a fully specified custom scenario."""
    if scenario is not None:
        return build_scenario(scenario)
    if not scenario_id:
        raise HTTPException(
            status_code=422, detail="provide either scenario_id or an inline scenario"
        )
    try:
        return preset(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"preset '{scenario_id}' cannot be built from the current cache: {exc}. "
                "Run scripts/fetch_real_data.py and scripts/build_index.py."
            ),
        ) from exc


def scheduler_kwargs(scheduler: str, weights: MagWeights | None) -> dict[str, Any]:
    if scheduler == "mag-nts" and weights is not None:
        return {"weights": weights}
    return {}
