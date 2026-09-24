"""Batch evaluation: many seeds, many policies, many ablations.

Episodes are embarrassingly parallel, so the batch runner spreads them across
processes.  Within a single episode everything is already vectorised over regions,
which is where the real speed comes from — a 1200-step, 48-region episode runs in
about a second, so a 6-policy x 8-seed comparison finishes in well under a minute
on a laptop.

Progress is reported through a callback rather than printed, so the same code path
serves the CLI scripts and the WebSocket stream to the dashboard.
"""

from __future__ import annotations

import concurrent.futures as futures
import os
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from aamsx.contracts.scenario import ScenarioSpec
from aamsx.evaluation.statistics import (
    HEADLINE_METRICS,
    Comparison,
    compare,
    summarise_runs,
)
from aamsx.experiments.runner import EpisodeResult, run_episode
from aamsx.logging import get_logger
from aamsx.schedulers.base import AblationFlags

log = get_logger(__name__)

ProgressSink = Callable[[dict], None] | None

#: One serialised episode, or one serialised summary.  Deliberately ``Any`` rather
#: than ``object``: these are JSON-shaped payloads whose leaf types differ per key,
#: and every reader coerces the field it wants (``float(run["metrics"][m])``).
Payload = dict[str, Any]

#: Axes the Pareto frontier is drawn over: two benefits, two costs.
PARETO_METRICS: tuple[str, ...] = (
    "sustained_detection_probability",
    "time_to_detect_capped",
    "false_alarm_rate",
    "sensing_cost",
)


@dataclass(frozen=True, slots=True)
class BatchJob:
    """One episode to run."""

    spec: ScenarioSpec
    scheduler: str
    seed: int
    flags: AblationFlags
    variant: str = ""

    @property
    def key(self) -> str:
        return self.variant or (
            self.scheduler
            if self.flags.label == "full"
            else f"{self.scheduler}[{self.flags.label}]"
        )


@dataclass(slots=True)
class BatchResult:
    """Aggregated outcome of a batch, grouped by variant key."""

    scenario: Payload
    variants: list[str]
    runs: dict[str, list[Payload]] = field(default_factory=dict)
    aggregates: dict[str, dict[str, Payload]] = field(default_factory=dict)
    comparisons: list[Payload] = field(default_factory=list)
    recoveries: dict[str, list[Payload]] = field(default_factory=dict)
    latency: dict[str, dict[str, float]] = field(default_factory=dict)

    def to_dict(self) -> Payload:
        return {
            "scenario": self.scenario,
            "variants": self.variants,
            "aggregates": self.aggregates,
            "comparisons": self.comparisons,
            "recoveries": self.recoveries,
            "latency": self.latency,
            "n_runs": {key: len(value) for key, value in self.runs.items()},
        }


def _worker(job: BatchJob) -> tuple[str, Payload]:
    result: EpisodeResult = run_episode(job.spec, job.scheduler, seed=job.seed, flags=job.flags)
    return job.key, {
        "seed": job.seed,
        "scheduler": job.scheduler,
        "ablation": job.flags.label,
        "metrics": result.metrics,
        "recovery": result.recovery,
        "decision_ms": result.decision_ms,
        "segment_metrics": result.segment_metrics,
    }


def default_workers() -> int:
    return max(1, (os.cpu_count() or 2) - 1)


def run_batch(
    jobs: Iterable[BatchJob],
    *,
    workers: int | None = None,
    progress: ProgressSink = None,
    baseline: str | None = None,
    metrics: tuple[str, ...] = HEADLINE_METRICS,
) -> BatchResult:
    """Run every job, then aggregate by variant and compare against ``baseline``."""
    jobs = list(jobs)
    if not jobs:
        raise ValueError("run_batch received no jobs")
    spec = jobs[0].spec
    order: list[str] = []
    for job in jobs:
        if job.key not in order:
            order.append(job.key)

    result = BatchResult(scenario=spec.to_dict(), variants=order)
    result.runs = {key: [] for key in order}
    workers = workers or default_workers()

    completed = 0
    if workers <= 1:
        outcomes: Iterable[tuple[str, Payload]] = (_worker(job) for job in jobs)
        for key, payload in outcomes:
            result.runs[key].append(payload)
            completed += 1
            if progress:
                progress({"type": "batch_progress", "done": completed, "total": len(jobs)})
    else:
        with futures.ProcessPoolExecutor(max_workers=workers) as pool:
            for key, payload in pool.map(_worker, jobs, chunksize=1):
                result.runs[key].append(payload)
                completed += 1
                if progress:
                    progress({"type": "batch_progress", "done": completed, "total": len(jobs)})

    for key, runs in result.runs.items():
        metric_dicts = [run["metrics"] for run in runs]
        result.aggregates[key] = summarise_runs(metric_dicts, metrics=metrics)
        result.recoveries[key] = [run["recovery"] for run in runs]
        result.latency[key] = _latency_summary(runs)

    if baseline and baseline in result.runs:
        result.comparisons = _comparisons(result, baseline, metrics)
    log.info(
        "batch.done",
        extra={"scenario": spec.scenario_id, "jobs": len(jobs), "variants": len(order)},
    )
    return result


def _latency_summary(runs: list[Payload]) -> dict[str, float]:
    if not runs:
        return {}
    keys = ("p50", "p95", "p99", "max", "mean")
    return {
        key: round(sum(float(run["decision_ms"][key]) for run in runs) / len(runs), 4)
        for key in keys
    }


def _comparisons(result: BatchResult, baseline: str, metrics: tuple[str, ...]) -> list[Payload]:
    control_runs = [run["metrics"] for run in result.runs[baseline]]
    out: list[Payload] = []
    for key, runs in result.runs.items():
        if key == baseline:
            continue
        treatment_runs = [run["metrics"] for run in runs]
        for metric in metrics:
            comparison: Comparison = compare(
                metric,
                [float(m[metric]) for m in treatment_runs if metric in m],
                [float(m[metric]) for m in control_runs if metric in m],
                treatment_name=key,
                control_name=baseline,
            )
            out.append(comparison.to_dict())
    return out


# --------------------------------------------------------------------------- #
# job builders
# --------------------------------------------------------------------------- #


def arena_jobs(
    spec: ScenarioSpec, schedulers: Iterable[str], seeds: Iterable[int]
) -> list[BatchJob]:
    """Identical scenario and seeds for every policy — the Algorithm Arena."""
    flags = AblationFlags()
    return [
        BatchJob(spec=spec, scheduler=name, seed=seed, flags=flags)
        for name in schedulers
        for seed in seeds
    ]


#: The ablation ladder, from the memory-free baseline up to the full policy.
ABLATION_LADDER: tuple[tuple[str, AblationFlags], ...] = (
    (
        "NTS",
        AblationFlags(
            memory=False,
            information_gain=False,
            change_detection=False,
            periodicity=False,
            temporal_encoder=False,
            uncertainty_exploration=False,
        ),
    ),
    (
        "NTS+Memory",
        AblationFlags(
            memory=True,
            information_gain=False,
            change_detection=False,
            periodicity=False,
            temporal_encoder=True,
            uncertainty_exploration=False,
        ),
    ),
    (
        "NTS+IG",
        AblationFlags(
            memory=False,
            information_gain=True,
            change_detection=False,
            periodicity=False,
            temporal_encoder=False,
            uncertainty_exploration=True,
        ),
    ),
    (
        "NTS+ChangeDetection",
        AblationFlags(
            memory=False,
            information_gain=False,
            change_detection=True,
            periodicity=False,
            temporal_encoder=False,
            uncertainty_exploration=False,
        ),
    ),
    (
        "NTS+Periodicity",
        AblationFlags(
            memory=False,
            information_gain=False,
            change_detection=False,
            periodicity=True,
            temporal_encoder=False,
            uncertainty_exploration=False,
        ),
    ),
    (
        "NTS+Memory+IG",
        AblationFlags(
            memory=True,
            information_gain=True,
            change_detection=False,
            periodicity=False,
            temporal_encoder=True,
            uncertainty_exploration=True,
        ),
    ),
    ("Full MAG-NTS", AblationFlags()),
)


def ablation_jobs(
    spec: ScenarioSpec, seeds: Iterable[int], *, scheduler: str = "mag-nts"
) -> list[BatchJob]:
    """The same policy with one component removed at a time."""
    seeds = list(seeds)
    return [
        BatchJob(spec=spec, scheduler=scheduler, seed=seed, flags=flags, variant=label)
        for label, flags in ABLATION_LADDER
        for seed in seeds
    ]


def pareto_points(result: BatchResult) -> dict[str, dict[str, float]]:
    """Mean cost/benefit coordinates per variant, for the Pareto frontier."""
    return {
        variant: {
            metric: result.aggregates[variant][metric]["mean"]
            for metric in PARETO_METRICS
            if metric in result.aggregates[variant]
        }
        for variant in result.variants
    }


def run_recorded_batch(
    jobs: list[BatchJob],
    *,
    kind: str,
    baseline: str | None,
    workers: int | None = None,
    progress: ProgressSink = None,
    settings=None,
    source: str = "cli",
) -> tuple[str, Payload]:
    """Run a batch, store it in the reproducibility registry, return (id, payload).

    Both the CLI and ``scripts/run_benchmark.py`` go through here, so a run started
    from either place is replayable and reportable afterwards.  The row is written
    *before* the episodes execute and updated when they finish, which means a crash
    leaves a ``running`` row behind rather than silently losing the attempt.
    """
    from aamsx.evaluation.pareto import describe, frontier
    from aamsx.experiments.registry import Registry

    if not jobs:
        raise ValueError("run_recorded_batch received no jobs")
    spec = jobs[0].spec
    registry = Registry(settings)
    experiment_id = f"{kind}-{uuid.uuid4().hex[:12]}"
    variants = sorted({job.key for job in jobs})
    registry.create(
        experiment_id=experiment_id,
        kind=kind,
        scenario_id=spec.scenario_id,
        scheduler=",".join(variants),
        seed=-1,
        ablation="batch",
        recordings=[segment.recording_id for segment in spec.segments],
        config={
            "kind": kind,
            "scenario": spec.to_dict(),
            "variants": variants,
            "seeds": sorted({job.seed for job in jobs}),
            "baseline": baseline,
            "source": source,
        },
    )
    try:
        result = run_batch(jobs, workers=workers, progress=progress, baseline=baseline)
    except KeyboardInterrupt:
        registry.finish(experiment_id, status="cancelled", error="interrupted")
        raise
    except Exception as exc:
        registry.finish(experiment_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        raise
    payload = {**result.to_dict(), "pareto": describe(frontier(pareto_points(result)))}
    registry.finish(experiment_id, status="completed", result=payload)
    return experiment_id, payload
