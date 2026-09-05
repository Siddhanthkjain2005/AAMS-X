"""Single-episode runner — the closed loop.

One pass of this loop is the whole thesis in miniature::

    observe -> encode -> infer -> remember -> estimate uncertainty
    -> value information -> select next observation -> score -> adapt

The ordering below is load-bearing in two places.

*The seal.*  ``env.sealed()`` wraps only the scheduler's decision, so any attempt
to read hidden state at exactly the moment it would matter raises immediately.

*The belief update precedes the reward.*  Information reward is the entropy the
belief filter genuinely lost, so it cannot be computed until the measurement has
been folded in — a scheduler cannot be paid for information it merely predicted.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from aamsx.config import Settings
from aamsx.contracts.observation import Feedback
from aamsx.contracts.scenario import ScenarioSpec
from aamsx.environment.replay import ReplayEnvironment, make_environment
from aamsx.evaluation.events import EventTracker
from aamsx.evaluation.metrics import MetricAccumulator, recovery_time
from aamsx.evaluation.reward import RewardModel
from aamsx.experiments.context import ContextBuilder
from aamsx.experiments.events import EventLog
from aamsx.logging import get_logger
from aamsx.schedulers import create
from aamsx.schedulers.base import AblationFlags, SchedulerSetup

log = get_logger(__name__)

FrameSink = Callable[[dict], None] | None


@dataclass(slots=True)
class EpisodeResult:
    """Everything one episode produced."""

    scenario_id: str
    scheduler: str
    seed: int
    flags: dict[str, bool]
    metrics: dict[str, float | int]
    curves: dict[str, Sequence[float]]
    timeline: list[dict[str, object]]
    recovery: dict[str, object]
    scheduler_snapshot: dict[str, object]
    context_snapshot: dict[str, object]
    segment_metrics: list[dict[str, object]]
    duration_sec: float
    decision_ms: dict[str, float]
    steps: int
    scenario: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scheduler": self.scheduler,
            "seed": self.seed,
            "flags": self.flags,
            "metrics": self.metrics,
            "curves": self.curves,
            "timeline": self.timeline,
            "recovery": self.recovery,
            "scheduler_snapshot": self.scheduler_snapshot,
            "context_snapshot": self.context_snapshot,
            "segment_metrics": self.segment_metrics,
            "duration_sec": round(self.duration_sec, 4),
            "decision_ms": self.decision_ms,
            "steps": self.steps,
            "scenario": self.scenario,
        }


def build_setup(
    spec: ScenarioSpec, *, seed: int, flags: AblationFlags, n_anchors: int
) -> SchedulerSetup:
    return SchedulerSetup(
        n_regions=spec.n_regions,
        window_size=spec.receiver.window_size,
        n_anchors=n_anchors,
        horizon=spec.horizon,
        budget=spec.effective_budget(),
        receiver=spec.receiver,
        reward=spec.reward,
        seed=seed,
        flags=flags,
    )


def run_episode(
    spec: ScenarioSpec,
    scheduler_name: str,
    *,
    seed: int = 0,
    flags: AblationFlags | None = None,
    environment: ReplayEnvironment | None = None,
    settings: Settings | None = None,
    frame_sink: FrameSink = None,
    frame_stride: int = 1,
    scheduler_kwargs: dict[str, object] | None = None,
) -> EpisodeResult:
    """Run one scheduler through one scenario and score it."""
    started = time.perf_counter()
    env = environment or make_environment(spec, seed=seed, settings=settings)
    env.reset()
    flags = flags or AblationFlags()

    setup = build_setup(spec, seed=seed, flags=flags, n_anchors=env.n_anchors)
    scheduler = create(scheduler_name, **(scheduler_kwargs or {}))
    scheduler.reset(setup)
    builder = ContextBuilder(setup)
    reward_model = RewardModel(spec.reward, spec.receiver.window_size)
    tracker = EventTracker(spec.n_regions)
    metrics = MetricAccumulator(
        n_regions=spec.n_regions,
        window_size=spec.receiver.window_size,
        horizon=spec.horizon,
        budget=spec.effective_budget(),
    )
    timeline = EventLog(horizon=spec.horizon)
    timeline.experiment_started(spec, scheduler_name, seed, flags)

    truth = env.truth  # evaluation-only handle, never passed onward
    decision_times: list[float] = []
    hit_curve: list[float] = []
    detection_by_step: list[int] = []

    for step in range(env.horizon):
        if env.done:
            timeline.budget_exhausted(step, env.budget_spent)
            break

        tracker.begin_step(step, truth.occupied[step])
        context = builder.build()
        previous_anchor = (
            int(context.previous_regions[0]) if context.previous_regions is not None else None
        )

        decision_started = time.perf_counter()
        with env.sealed():
            proposal = scheduler.select(context)
        decision_times.append((time.perf_counter() - decision_started) * 1000.0)

        outcome = env.step(proposal.anchor)
        observation = outcome.observation
        tracker.observe(step, observation.regions, observation.detected)

        _, entropy_before, entropy_after = builder.absorb(observation)
        reward = reward_model.score(
            observation,
            outcome.true_occupied,
            entropy_before=entropy_before,
            entropy_after=entropy_after,
            pending_delay=tracker.pending_delay(step),
            retune_fraction=env.receiver.retune_fraction(proposal.anchor, previous_anchor),
        )
        feedback = Feedback(
            step=step,
            observation=observation,
            true_occupied=outcome.true_occupied,
            reward=reward.total,
            reward_terms=reward.terms,
            hits=reward.hits,
            false_alarms=reward.false_alarms,
            misses_in_window=reward.missed_in_window,
            budget_remaining=env.budget_remaining,
        )
        scheduler.update(feedback)
        builder.commit(feedback)

        metrics.record(
            step=step,
            anchor=proposal.anchor,
            detected=observation.detected,
            true_occupied=outcome.true_occupied,
            reward=reward.total,
            reward_terms=reward.terms,
            cost=observation.cost,
            information_bits=reward.realised_information_bits,
            oracle_best=outcome.oracle_best_count,
            available=observation.available,
        )
        detection_by_step.append(reward.hits)
        hit_curve.append(reward.hits / max(1, spec.receiver.window_size))

        timeline.step(
            step=step,
            proposal=proposal,
            outcome=outcome,
            reward=reward,
            builder=builder,
            budget_remaining=env.budget_remaining,
            budget=spec.effective_budget(),
        )
        if frame_sink is not None and step % max(1, frame_stride) == 0:
            frame_sink(
                _frame(
                    step=step,
                    spec=spec,
                    proposal=proposal,
                    outcome=outcome,
                    reward=reward,
                    builder=builder,
                    metrics=metrics,
                    env=env,
                )
            )

    tracker.finish(env.step_index)
    timeline.experiment_completed(env.step_index, metrics, tracker)

    summary = metrics.summary(tracker)
    recovery = _recovery(spec, np.asarray(hit_curve, dtype=np.float64), truth)
    result = EpisodeResult(
        scenario_id=spec.scenario_id,
        scheduler=scheduler_name,
        seed=seed,
        flags=flags.to_dict(),
        metrics=summary,
        curves={
            "reward": [round(v, 4) for v in metrics.reward_curve],
            "regret": [round(v, 4) for v in metrics.regret_curve],
            "hits": detection_by_step,
            "anchors": metrics.anchors,
        },
        timeline=timeline.entries,
        recovery=recovery,
        scheduler_snapshot=scheduler.snapshot(),
        context_snapshot=builder.snapshot(),
        segment_metrics=_segment_metrics(spec, truth, detection_by_step),
        duration_sec=time.perf_counter() - started,
        decision_ms=_latency(decision_times),
        steps=env.step_index,
        scenario=spec.to_dict(),
    )
    log.info(
        "episode.done",
        extra={
            "scenario": spec.scenario_id,
            "scheduler": scheduler_name,
            "seed": seed,
            "reward": summary["cumulative_reward"],
            "regret": summary["cumulative_regret"],
            "events": f"{summary['events_detected']}/{summary['events_total']}",
            "ms_p50": result.decision_ms["p50"],
        },
    )
    return result


def _latency(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {"p50": 0.0, "p95": 0.0, "p99": 0.0, "max": 0.0, "mean": 0.0}
    array = np.asarray(samples)
    return {
        "p50": round(float(np.percentile(array, 50)), 4),
        "p95": round(float(np.percentile(array, 95)), 4),
        "p99": round(float(np.percentile(array, 99)), 4),
        "max": round(float(array.max()), 4),
        "mean": round(float(array.mean()), 4),
    }


def _recovery(spec: ScenarioSpec, hit_curve: np.ndarray, truth) -> dict[str, object]:
    """Recovery time after every ground-truth phase boundary."""
    entries: list[dict[str, object]] = []
    for change_step in spec.change_points:
        steps = recovery_time(hit_curve, change_step)
        entries.append(
            {
                "change_step": int(change_step),
                "recovered_after": steps,
                "recovered": steps is not None,
            }
        )
    return {"change_points": entries, "n_change_points": len(spec.change_points)}


def _segment_metrics(spec: ScenarioSpec, truth, hits: list[int]) -> list[dict[str, object]]:
    """Per-phase detection summary, so A vs B vs A' can be compared directly."""
    out: list[dict[str, object]] = []
    counts = np.asarray(hits, dtype=np.float64)
    for index, (phase, start, stop) in enumerate(spec.phase_spans):
        stop = min(stop, counts.size)
        if stop <= start:
            continue
        block = counts[start:stop]
        segment = truth.segments[index] if index < len(truth.segments) else None
        out.append(
            {
                "phase": phase or f"segment {index}",
                "start_step": int(start),
                "stop_step": int(stop),
                "mean_hits": round(float(block.mean()), 4),
                "station": segment.station if segment else "",
                "archetype": segment.stats.archetype if segment else "",
                "true_occupancy": round(float(segment.stats.occupancy), 5) if segment else 0.0,
            }
        )
    return out


def _frame(*, step, spec, proposal, outcome, reward, builder, metrics, env) -> dict[str, object]:
    """One streaming frame: everything the live dashboard needs for this step."""
    observation = outcome.observation
    belief = builder.belief
    readout = builder.last_readout
    return {
        "type": "frame",
        "step": step,
        "t_sec": round(observation.t_sec, 3),
        "regions": observation.regions.tolist(),
        "measured_db": [round(float(v), 3) for v in observation.measured_db],
        "detected": observation.detected.tolist(),
        "confidence": [round(float(v), 4) for v in observation.confidence],
        "true_occupied": outcome.true_occupied.tolist(),
        "true_margin_db": [round(float(v), 3) for v in outcome.true_margin_db],
        "band_truth": outcome.occupied_total,
        "oracle_best": outcome.oracle_best_count,
        "available": observation.available,
        "belief": [round(float(v), 4) for v in belief.belief],
        "uncertainty": [round(float(v), 4) for v in belief.uncertainty],
        "staleness": [round(float(v), 4) for v in belief.staleness],
        "action_value": round(proposal.action_value, 5),
        "factors": proposal.factors,
        "notes": list(proposal.notes),
        "per_region_value": (
            [round(float(v), 5) for v in proposal.per_region_value]
            if proposal.per_region_value is not None
            else None
        ),
        "reward": round(reward.total, 5),
        "reward_terms": reward.terms,
        "cumulative_reward": round(metrics.total_reward, 4),
        "cumulative_regret": round(metrics.total_regret, 4),
        "hits": reward.hits,
        "false_alarms": reward.false_alarms,
        "budget_remaining": round(env.budget_remaining, 3),
        "change": builder.change.snapshot(),
        "memory": readout.to_dict(),
        "periodicity": {
            "period_steps": builder.periodicity.period,
            "strength": round(float(builder.periodicity.strength), 4),
        },
        "segment_index": outcome.segment_index,
        "segment_changed": outcome.changed_segment,
        "exploration_rate": round(float(proposal.exploration_rate), 4),
    }
