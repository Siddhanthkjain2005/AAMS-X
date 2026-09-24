"""Experiment lifecycle: start, stream, cancel, replay, history."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect

from aamsx.api.deps import resolve_scenario, scheduler_kwargs, to_flags, to_weights
from aamsx.api.schemas import BatchRequest, EpisodeRequest
from aamsx.environment.truth import ScenarioUnsatisfiable
from aamsx.experiments.batch import ablation_jobs, arena_jobs, default_workers
from aamsx.experiments.engine import get_engine
from aamsx.logging import get_logger
from aamsx.schedulers import ARENA_ORDER, available
from aamsx.schedulers.base import AblationFlags

log = get_logger(__name__)

router = APIRouter(prefix="/experiments", tags=["experiments"])


@router.post("", status_code=202)
def start_episode(request: EpisodeRequest) -> dict[str, object]:
    """Launch one streamed episode and return immediately with its id."""
    if request.scheduler not in available():
        raise HTTPException(
            status_code=404,
            detail=f"unknown scheduler {request.scheduler!r}; available: {', '.join(available())}",
        )
    spec = resolve_scenario(request.scenario_id, request.scenario)
    engine = get_engine()
    try:
        session = engine.start_episode(
            spec,
            request.scheduler,
            seed=request.seed,
            flags=to_flags(request.ablation),
            pace_hz=request.pace_hz,
            frame_stride=request.frame_stride,
            scheduler_kwargs=scheduler_kwargs(request.scheduler, to_weights(request.mag_weights)),
        )
    except (ScenarioUnsatisfiable, FileNotFoundError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"experiment_id": session.experiment_id, **session.summary()}


@router.post("/arena", status_code=202)
def start_arena(request: BatchRequest) -> dict[str, object]:
    """Race every policy through identical seeds of the same real scenario."""
    spec = resolve_scenario(request.scenario_id, request.scenario)
    names = request.schedulers or list(ARENA_ORDER)
    unknown = [name for name in names if name not in available()]
    if unknown:
        raise HTTPException(status_code=404, detail=f"unknown scheduler(s): {', '.join(unknown)}")
    jobs = arena_jobs(spec, names, range(request.seeds))
    session = get_engine().start_batch(
        spec,
        kind="arena",
        jobs=jobs,
        baseline="nts" if "nts" in names else names[0],
        workers=request.workers or default_workers(),
    )
    return {"experiment_id": session.experiment_id, **session.summary(), "n_jobs": len(jobs)}


@router.post("/ablation", status_code=202)
def start_ablation(request: BatchRequest) -> dict[str, object]:
    """Run the ablation ladder: MAG-NTS with one component removed at a time."""
    spec = resolve_scenario(request.scenario_id, request.scenario)
    jobs = ablation_jobs(spec, range(request.seeds))
    session = get_engine().start_batch(
        spec,
        kind="ablation",
        jobs=jobs,
        baseline="NTS",
        workers=request.workers or default_workers(),
    )
    return {"experiment_id": session.experiment_id, **session.summary(), "n_jobs": len(jobs)}


@router.get("/active")
def active() -> dict[str, object]:
    return {"active": get_engine().active()}


@router.get("/history")
def history(
    limit: int = Query(default=50, ge=1, le=500), kind: str | None = None
) -> dict[str, object]:
    records = get_engine().registry.history(limit=limit, kind=kind)
    return {"count": len(records), "experiments": [record.to_dict() for record in records]}


@router.get("/{experiment_id}")
def detail(experiment_id: str) -> dict[str, object]:
    """Live session state if it is running, otherwise the stored result."""
    engine = get_engine()
    session = engine.get(experiment_id)
    if session is not None:
        return {**session.summary(), "result": session.result}
    record = engine.registry.get(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no experiment {experiment_id!r}")
    return {**record.to_dict(), "result": engine.registry.load_result(experiment_id)}


@router.get("/{experiment_id}/frames")
def frames(
    experiment_id: str,
    start: int = Query(default=0, ge=0),
    limit: int = Query(default=600, ge=1, le=4000),
) -> dict[str, object]:
    """Retained frames, for a client that wants to scrub without a socket."""
    session = get_engine().get(experiment_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"no live session {experiment_id!r}")
    window = session.frames[start : start + limit]
    return {"start": start, "count": len(window), "total": len(session.frames), "frames": window}


@router.post("/{experiment_id}/cancel")
def cancel(experiment_id: str) -> dict[str, object]:
    if not get_engine().cancel(experiment_id):
        raise HTTPException(
            status_code=409, detail=f"experiment {experiment_id!r} is not cancellable"
        )
    return {"experiment_id": experiment_id, "status": "cancelling"}


@router.post("/{experiment_id}/replay", status_code=202)
def replay(experiment_id: str, pace_hz: float = 30.0) -> dict[str, object]:
    """Re-execute a stored experiment from its recorded configuration.

    This genuinely re-runs the episode from the stored seed and flags; it does not
    replay a cached picture. Identical inputs give identical outputs, which is the
    point of storing the configuration hash.
    """
    engine = get_engine()
    record = engine.registry.get(experiment_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"no experiment {experiment_id!r}")
    config = record.config
    if config.get("kind") != "episode":
        raise HTTPException(
            status_code=422,
            detail=f"experiment {experiment_id!r} is a {config.get('kind')} batch; "
            "replay currently covers single episodes",
        )
    from aamsx.contracts.scenario import ScenarioSpec

    # Rebuild the exact stored problem, not a freshly built preset: the window
    # index can move underneath a scenario_id, and replay must not silently
    # substitute a different set of recordings.
    spec = ScenarioSpec.from_dict(config["scenario"])
    session = engine.start_episode(
        spec,
        config["scheduler"],
        seed=config["seed"],
        flags=AblationFlags(**config["flags"]),
        pace_hz=pace_hz,
    )
    return {
        "experiment_id": session.experiment_id,
        "replay_of": experiment_id,
        "config_hash": record.config_hash,
        **session.summary(),
    }


@router.websocket("/{experiment_id}/stream")
async def stream(websocket: WebSocket, experiment_id: str) -> None:
    """Stream session history then live frames until the run finishes."""
    await websocket.accept()
    engine = get_engine()
    try:
        async for message in engine.subscribe(experiment_id):
            await websocket.send_json(message)
    except KeyError:
        await websocket.send_json({"type": "error", "error": f"no live session {experiment_id!r}"})
    except WebSocketDisconnect:
        log.debug("ws.disconnected", extra={"id": experiment_id})
        return
    finally:
        # The peer may already be gone; closing a closed socket is not an error here.
        with contextlib.suppress(RuntimeError):
            await websocket.close()
