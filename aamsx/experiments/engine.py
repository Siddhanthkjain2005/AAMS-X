"""Async experiment engine: run episodes in the background and stream them out.

The scheduler loop is CPU-bound and synchronous, so it runs in a worker thread and
publishes frames back into the event loop.  Frames are both fanned out to live
WebSocket subscribers and retained in the session, which is what lets a client
attach late, scrub backwards, or replay without re-running anything.

A run can be *paced*.  A 1200-step episode finishes in about a second, which is too
fast to watch, so the sink throttles itself to a target frame rate.  Pacing changes
only when frames are emitted, never what is computed: a paced run and an unpaced run
of the same seed produce byte-identical results.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import time
import traceback
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from aamsx.config import Settings, get_settings
from aamsx.contracts.scenario import ScenarioSpec
from aamsx.experiments.registry import Registry
from aamsx.experiments.runner import EpisodeResult, run_episode
from aamsx.logging import get_logger
from aamsx.schedulers.base import AblationFlags

log = get_logger(__name__)

MAX_RETAINED_FRAMES = 4000


@dataclass
class Session:
    """One running or finished experiment."""

    experiment_id: str
    kind: str
    scenario_id: str
    label: str
    status: str = "queued"
    frames: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: float = 0.0
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    cancelled: bool = False
    subscribers: list[asyncio.Queue] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "kind": self.kind,
            "scenario_id": self.scenario_id,
            "label": self.label,
            "status": self.status,
            "progress": round(self.progress, 4),
            "n_frames": len(self.frames),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_sec": round((self.finished_at or time.time()) - self.started_at, 3),
        }


class ExperimentEngine:
    """Owns every live session and the thread pool that drives them."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.registry = Registry(self.settings)
        self.sessions: dict[str, Session] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the serving event loop so a worker thread can launch runs.

        The launch endpoints are deliberately ``def`` and not ``async def``: they
        resolve a scenario, which reads Parquet from disk, and that must not block
        the event loop.  FastAPI therefore runs them in a worker thread, which has
        no running loop of its own, so the driving coroutine has to be handed back
        to the serving loop explicitly.
        """
        self._loop = loop

    def _spawn(self, coro) -> asyncio.Task:
        """Schedule a driver coroutine, whether or not this thread owns the loop."""
        try:
            return asyncio.get_running_loop().create_task(coro)
        except RuntimeError:
            pass
        loop = self._loop
        if loop is None or loop.is_closed():
            coro.close()
            raise RuntimeError(
                "the experiment engine is not bound to a running event loop; "
                "call bind_loop() during application startup"
            )
        handle: concurrent.futures.Future = concurrent.futures.Future()
        loop.call_soon_threadsafe(lambda: handle.set_result(loop.create_task(coro)))
        return handle.result(timeout=10.0)

    # ---- lifecycle -----------------------------------------------------------

    def _new_session(self, kind: str, scenario_id: str, label: str) -> Session:
        experiment_id = f"{kind[:3]}-{uuid.uuid4().hex[:10]}"
        session = Session(
            experiment_id=experiment_id, kind=kind, scenario_id=scenario_id, label=label
        )
        self.sessions[experiment_id] = session
        self._evict_old()
        return session

    def _evict_old(self, *, keep: int = 24) -> None:
        finished = [s for s in self.sessions.values() if s.status in {"completed", "failed"}]
        if len(finished) <= keep:
            return
        finished.sort(key=lambda s: s.finished_at or 0.0)
        for session in finished[: len(finished) - keep]:
            self.sessions.pop(session.experiment_id, None)

    def get(self, experiment_id: str) -> Session | None:
        return self.sessions.get(experiment_id)

    def cancel(self, experiment_id: str) -> bool:
        session = self.sessions.get(experiment_id)
        if session is None or session.status not in {"queued", "running"}:
            return False
        session.cancelled = True
        task = self._tasks.get(experiment_id)
        if task is not None:
            task.cancel()
        return True

    def active(self) -> list[dict[str, Any]]:
        return [
            session.summary()
            for session in self.sessions.values()
            if session.status in {"queued", "running"}
        ]

    # ---- publishing ----------------------------------------------------------

    def _publish(self, session: Session, message: dict[str, Any]) -> None:
        if message.get("type") == "frame":
            session.frames.append(message)
            if len(session.frames) > MAX_RETAINED_FRAMES:
                del session.frames[0]
        for queue in list(session.subscribers):
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # A slow client must never stall the experiment; it will resync from
                # the retained frames when it reconnects.
                log.debug("engine.subscriber_lagging", extra={"id": session.experiment_id})

    async def subscribe(self, experiment_id: str) -> AsyncIterator[dict[str, Any]]:
        """Yield the retained history, then live messages until the run ends."""
        session = self.sessions.get(experiment_id)
        if session is None:
            raise KeyError(experiment_id)
        queue: asyncio.Queue = asyncio.Queue(maxsize=512)
        session.subscribers.append(queue)
        try:
            yield {"type": "session", **session.summary()}
            for frame in list(session.frames):
                yield frame
            for event in list(session.events):
                yield event
            if session.status in {"completed", "failed"}:
                yield {"type": "complete", **session.summary(), "result": session.result}
                return
            while True:
                message = await queue.get()
                yield message
                if message.get("type") in {"complete", "error"}:
                    return
        finally:
            with contextlib.suppress(ValueError):
                session.subscribers.remove(queue)

    # ---- episode -------------------------------------------------------------

    def start_episode(
        self,
        spec: ScenarioSpec,
        scheduler: str,
        *,
        seed: int = 0,
        flags: AblationFlags | None = None,
        pace_hz: float = 30.0,
        frame_stride: int = 1,
        scheduler_kwargs: dict[str, Any] | None = None,
    ) -> Session:
        """Launch one paced, streamed episode."""
        flags = flags or AblationFlags()
        session = self._new_session("episode", spec.scenario_id, f"{scheduler} · {spec.name}")
        config = {
            "kind": "episode",
            "scenario": spec.to_dict(),
            "scheduler": scheduler,
            "seed": seed,
            "flags": flags.to_dict(),
            "scheduler_kwargs": scheduler_kwargs or {},
        }
        self.registry.create(
            experiment_id=session.experiment_id,
            kind="episode",
            scenario_id=spec.scenario_id,
            scheduler=scheduler,
            seed=seed,
            ablation=flags.label,
            recordings=[segment.recording_id for segment in spec.segments],
            config=config,
        )
        task = self._spawn(
            self._drive_episode(
                session,
                spec,
                scheduler,
                seed=seed,
                flags=flags,
                pace_hz=pace_hz,
                frame_stride=frame_stride,
                scheduler_kwargs=scheduler_kwargs,
            )
        )
        self._tasks[session.experiment_id] = task
        return session

    async def _drive_episode(
        self,
        session: Session,
        spec: ScenarioSpec,
        scheduler: str,
        *,
        seed: int,
        flags: AblationFlags,
        pace_hz: float,
        frame_stride: int,
        scheduler_kwargs: dict[str, Any] | None,
    ) -> None:
        loop = asyncio.get_running_loop()
        session.status = "running"
        self._publish(session, {"type": "status", **session.summary()})
        horizon = max(1, spec.horizon)
        interval = 1.0 / pace_hz if pace_hz > 0 else 0.0

        def sink(frame: dict[str, Any]) -> None:
            if session.cancelled:
                raise _Cancelled
            frame["progress"] = round(frame["step"] / horizon, 5)
            loop.call_soon_threadsafe(self._on_frame, session, frame)
            if interval:
                time.sleep(interval)

        try:
            result: EpisodeResult = await asyncio.to_thread(
                run_episode,
                spec,
                scheduler,
                seed=seed,
                flags=flags,
                settings=self.settings,
                frame_sink=sink,
                frame_stride=frame_stride,
                scheduler_kwargs=scheduler_kwargs,
            )
        except (_Cancelled, asyncio.CancelledError):
            session.status = "failed"
            session.error = "cancelled by user"
            session.finished_at = time.time()
            self.registry.finish(session.experiment_id, status="cancelled", error=session.error)
            self._publish(session, {"type": "error", **session.summary()})
            return
        except Exception as exc:
            session.status = "failed"
            session.error = f"{type(exc).__name__}: {exc}"
            session.finished_at = time.time()
            log.warning(
                "engine.episode_failed",
                extra={"id": session.experiment_id, "error": session.error},
            )
            self.registry.finish(
                session.experiment_id, status="failed", error=traceback.format_exc(limit=4)
            )
            self._publish(session, {"type": "error", **session.summary()})
            return

        payload = result.to_dict()
        session.result = payload
        session.events = [{"type": "timeline", **entry} for entry in payload["timeline"]]
        session.status = "completed"
        session.progress = 1.0
        session.finished_at = time.time()
        self.registry.finish(
            session.experiment_id,
            status="completed",
            metrics=result.metrics,
            result=payload,
        )
        for event in session.events:
            self._publish(session, event)
        self._publish(session, {"type": "complete", **session.summary(), "result": payload})

    def _on_frame(self, session: Session, frame: dict[str, Any]) -> None:
        session.progress = float(frame.get("progress", session.progress))
        self._publish(session, frame)

    # ---- batch (arena / ablation) --------------------------------------------

    def start_batch(
        self,
        spec: ScenarioSpec,
        *,
        kind: str,
        jobs,
        baseline: str | None,
        workers: int | None = None,
    ) -> Session:
        """Launch a multi-episode batch and stream its progress."""
        label = f"{kind} · {spec.name} ({len(jobs)} episodes)"
        session = self._new_session(kind, spec.scenario_id, label)
        config: dict[str, Any] = {
            "kind": kind,
            "scenario": spec.to_dict(),
            "variants": sorted({job.key for job in jobs}),
            "seeds": sorted({job.seed for job in jobs}),
            "baseline": baseline,
        }
        self.registry.create(
            experiment_id=session.experiment_id,
            kind=kind,
            scenario_id=spec.scenario_id,
            scheduler=",".join(config["variants"]),
            seed=-1,
            ablation="batch",
            recordings=[segment.recording_id for segment in spec.segments],
            config=config,
        )
        task = self._spawn(self._drive_batch(session, jobs, baseline=baseline, workers=workers))
        self._tasks[session.experiment_id] = task
        return session

    async def _drive_batch(self, session: Session, jobs, *, baseline, workers) -> None:
        from aamsx.experiments.batch import run_batch

        loop = asyncio.get_running_loop()
        session.status = "running"
        self._publish(session, {"type": "status", **session.summary()})

        def progress(message: dict[str, Any]) -> None:
            if session.cancelled:
                raise _Cancelled
            loop.call_soon_threadsafe(self._on_progress, session, message)

        try:
            result = await asyncio.to_thread(
                run_batch, jobs, workers=workers, progress=progress, baseline=baseline
            )
        except (_Cancelled, asyncio.CancelledError):
            session.status = "failed"
            session.error = "cancelled by user"
            session.finished_at = time.time()
            self.registry.finish(session.experiment_id, status="cancelled", error=session.error)
            self._publish(session, {"type": "error", **session.summary()})
            return
        except Exception as exc:
            session.status = "failed"
            session.error = f"{type(exc).__name__}: {exc}"
            session.finished_at = time.time()
            log.warning("engine.batch_failed", extra={"id": session.experiment_id})
            self.registry.finish(
                session.experiment_id, status="failed", error=traceback.format_exc(limit=4)
            )
            self._publish(session, {"type": "error", **session.summary()})
            return

        from aamsx.evaluation.pareto import describe, frontier
        from aamsx.experiments.batch import pareto_points

        payload = {**result.to_dict(), "pareto": describe(frontier(pareto_points(result)))}
        session.result = payload
        session.status = "completed"
        session.progress = 1.0
        session.finished_at = time.time()
        self.registry.finish(session.experiment_id, status="completed", result=payload)
        self._publish(session, {"type": "complete", **session.summary(), "result": payload})

    def _on_progress(self, session: Session, message: dict[str, Any]) -> None:
        total = max(1, int(message.get("total", 1)))
        session.progress = min(1.0, int(message.get("done", 0)) / total)
        self._publish(session, {**message, "progress": round(session.progress, 4)})


class _Cancelled(RuntimeError):
    """Raised inside the worker thread to unwind a cancelled run."""


_ENGINE: ExperimentEngine | None = None


def get_engine() -> ExperimentEngine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = ExperimentEngine()
    return _ENGINE
