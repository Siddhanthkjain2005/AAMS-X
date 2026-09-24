"""Scenario routes: presets mined from the index, plus custom scenario validation."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aamsx.api.deps import build_scenario
from aamsx.api.schemas import ScenarioRequest
from aamsx.environment.scenarios import (
    FAMILY_PREDICATES,
    PRESET_ORDER,
    list_presets,
    preset,
    sample_scenario,
)
from aamsx.environment.truth import ScenarioUnsatisfiable, build_truth

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("")
def scenarios() -> dict[str, object]:
    """Every preset the current cache can satisfy, plus the randomised families."""
    built = list_presets()
    available = {spec.scenario_id for spec in built}
    return {
        "presets": [spec.to_dict() for spec in built],
        "unavailable": [name for name in PRESET_ORDER if name not in available],
        "families": [
            {"family": family, "predicate": predicate}
            for family, predicate in FAMILY_PREDICATES.items()
        ],
        "note": (
            "Presets are queries against measured window statistics, not constants. "
            "Every scenario points at a real recording and a real time range."
        ),
    }


@router.get("/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict[str, object]:
    """One preset, with the measured statistics of each spliced segment."""
    try:
        spec = preset(scenario_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    try:
        truth = build_truth(spec)
    except (ScenarioUnsatisfiable, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        **spec.to_dict(),
        "segments_measured": [segment.to_dict() for segment in truth.segments],
        "truth_occupancy": round(float(truth.occupied.mean()), 5),
        "availability": round(float(truth.available.mean()), 5),
    }


@router.post("/sample")
def sample(family: str, seed: int = 0, unseen: bool = False) -> dict[str, object]:
    """Draw a randomised real environment from a family — one per seed."""
    if family not in FAMILY_PREDICATES:
        raise HTTPException(
            status_code=404,
            detail=f"unknown family {family!r}; available: {', '.join(FAMILY_PREDICATES)}",
        )
    try:
        spec = sample_scenario(
            family, seed=seed, roles=("unseen",) if unseen else ("train", "validation")
        )
    except (LookupError, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return spec.to_dict()


@router.post("/validate")
def validate(request: ScenarioRequest) -> dict[str, object]:
    """Check a custom scenario against the cache and report its measured behaviour."""
    spec = build_scenario(request)
    try:
        truth = build_truth(spec)
    except (ScenarioUnsatisfiable, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        **spec.to_dict(),
        "segments_measured": [segment.to_dict() for segment in truth.segments],
        "truth_occupancy": round(float(truth.occupied.mean()), 5),
        "valid": True,
    }
