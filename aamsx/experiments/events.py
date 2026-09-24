"""Timeline events.

The event log is what turns a run into a story a person can follow: not every
step, only the moments that mean something.  Each entry carries a severity so the
UI can filter, and every one is derived from real state — there is no cosmetic
event in this module.

The log is bounded.  A long episode produces a lot of detections, so per-step
event families are rate-limited while the rare, important ones (change detected,
context recognised, periodicity discovered) are always kept.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from aamsx.contracts.observation import ActionProposal
from aamsx.contracts.scenario import ScenarioSpec
from aamsx.schedulers.base import AblationFlags

Severity = Literal["info", "success", "warning", "critical", "insight"]

EventKind = Literal[
    "experiment_started",
    "detection",
    "burst_detected",
    "miss",
    "high_uncertainty",
    "change_detected",
    "memory_recalled",
    "periodicity_discovered",
    "exploration_increased",
    "budget_threshold",
    "budget_exhausted",
    "phase_changed",
    "archive_gap",
    "experiment_completed",
]

MAX_ENTRIES = 400


@dataclass(slots=True)
class EventLog:
    """Bounded, prioritised timeline of meaningful episode events."""

    horizon: int
    entries: list[dict[str, object]] = field(default_factory=list)
    _seen_period: int = 0
    _budget_marks: set[int] = field(default_factory=set)
    _last_detection_step: int = -999
    _last_uncertainty_step: int = -999
    _recognised_prototypes: set[int] = field(default_factory=set)

    #: Kinds that are never dropped when the log is full.
    PRIORITY: frozenset[str] = frozenset(
        {
            "experiment_started",
            "experiment_completed",
            "change_detected",
            "memory_recalled",
            "periodicity_discovered",
            "phase_changed",
            "budget_exhausted",
            "archive_gap",
        }
    )

    def add(
        self,
        kind: EventKind,
        step: int,
        message: str,
        *,
        severity: Severity = "info",
        data: dict[str, object] | None = None,
    ) -> None:
        if len(self.entries) >= MAX_ENTRIES:
            self._make_room()
        self.entries.append(
            {
                "kind": kind,
                "step": int(step),
                "message": message,
                "severity": severity,
                "data": data or {},
            }
        )

    def _make_room(self) -> None:
        for index, entry in enumerate(self.entries):
            if entry["kind"] not in self.PRIORITY:
                del self.entries[index]
                return
        del self.entries[0]

    # ---- lifecycle -----------------------------------------------------------

    def experiment_started(
        self, spec: ScenarioSpec, scheduler: str, seed: int, flags: AblationFlags
    ) -> None:
        stations = sorted({segment.recording_id.split("/")[0] for segment in spec.segments})
        self.add(
            "experiment_started",
            0,
            f"{scheduler} on '{spec.name}' — {spec.horizon} steps, "
            f"{spec.n_regions} regions, real data from {', '.join(stations)}",
            severity="info",
            data={
                "scheduler": scheduler,
                "seed": seed,
                "ablation": flags.label,
                "stations": stations,
                "budget": spec.effective_budget(),
            },
        )

    def experiment_completed(self, steps: int, metrics, tracker) -> None:
        events = tracker.summary()
        self.add(
            "experiment_completed",
            steps,
            f"Completed {steps} steps — {events['events_detected']}/{events['events_total']} "
            f"events detected, cumulative reward {metrics.total_reward:.1f}, "
            f"regret {metrics.total_regret:.0f}",
            severity="success",
            data={
                "reward": round(metrics.total_reward, 3),
                "regret": round(metrics.total_regret, 3),
                "events_detected": int(events["events_detected"]),
                "events_total": int(events["events_total"]),
            },
        )

    def budget_exhausted(self, step: int, spent: float) -> None:
        self.add(
            "budget_exhausted",
            step,
            f"Sensing budget exhausted after {step} steps ({spent:.1f} cost units)",
            severity="warning",
            data={"spent": round(spent, 3)},
        )

    # ---- per-step derivation -------------------------------------------------

    def step(
        self,
        *,
        step: int,
        proposal: ActionProposal,
        outcome,
        reward,
        builder,
        budget_remaining: float,
        budget: float,
    ) -> None:
        """Derive whichever events this step actually earned."""
        if outcome.changed_segment:
            self.add(
                "phase_changed",
                step,
                f"Ground truth phase boundary: the environment is now a different "
                f"real recording (segment {outcome.segment_index})",
                severity="critical",
                data={"segment_index": outcome.segment_index},
            )

        if not outcome.observation.available:
            self.add(
                "archive_gap",
                step,
                "The archive published no data for this interval — reported, not interpolated",
                severity="warning",
            )

        change = builder.change.state
        if change.flag:
            self.add(
                "change_detected",
                step,
                f"ENVIRONMENT SHIFT DETECTED — surprise statistic {change.score:.2f}; "
                "stale evidence discounted and exploration raised",
                severity="critical",
                data={
                    "score": round(change.score, 4),
                    "page_hinkley": round(change.page_hinkley, 4),
                    "ewma": round(change.ewma, 4),
                },
            )
            self.add(
                "exploration_increased",
                step,
                f"Exploration boost {change.exploration_boost:.2f} applied after the shift",
                severity="info",
            )

        readout = builder.last_readout
        if (
            readout.recognised
            and readout.prototype_id is not None
            and readout.prototype_id not in self._recognised_prototypes
        ):
            self._recognised_prototypes.add(int(readout.prototype_id))
            self.add(
                "memory_recalled",
                step,
                f"ASSOCIATIVE MEMORY MATCH — context #{readout.prototype_id} "
                f"('{readout.label}') recognised at similarity {readout.similarity:.2f} "
                f"after {readout.visits} prior visits; its region preference is now a prior",
                severity="insight",
                data=readout.to_dict(),
            )

        period = builder.periodicity.period
        if period > 0 and period != self._seen_period and builder.periodicity.strength > 0.4:
            self._seen_period = int(period)
            self.add(
                "periodicity_discovered",
                step,
                f"Recurrence detected: activity repeats every {period} steps "
                f"(autocorrelation {builder.periodicity.strength:.2f})",
                severity="insight",
                data={
                    "period_steps": int(period),
                    "strength": round(float(builder.periodicity.strength), 4),
                },
            )

        if reward.hits > 0 and step - self._last_detection_step >= 12:
            self._last_detection_step = step
            anchor = proposal.anchor
            self.add(
                "detection" if reward.hits < proposal.regions.size else "burst_detected",
                step,
                f"{reward.hits}/{proposal.regions.size} regions confirmed active at anchor "
                f"R{anchor:02d}"
                + (f" (+{reward.false_alarms} false alarm)" if reward.false_alarms else ""),
                severity="success",
                data={"anchor": anchor, "hits": reward.hits, "false_alarms": reward.false_alarms},
            )

        undetected = outcome.missed_outside_window
        if undetected >= max(3, proposal.regions.size) and step % 40 == 0:
            self.add(
                "miss",
                step,
                f"{undetected} regions were active outside the observed window this step",
                severity="warning",
                data={"undetected": undetected},
            )

        uncertainty = float(builder.belief.uncertainty.mean())
        if uncertainty > 0.75 and step - self._last_uncertainty_step >= 60:
            self._last_uncertainty_step = step
            self.add(
                "high_uncertainty",
                step,
                f"Mean posterior uncertainty at {uncertainty:.2f} — belief is stale "
                "across much of the band",
                severity="warning",
                data={"uncertainty": round(uncertainty, 4)},
            )

        if budget > 0:
            used = 1.0 - budget_remaining / budget
            for mark in (50, 75, 90):
                if used >= mark / 100.0 and mark not in self._budget_marks:
                    self._budget_marks.add(mark)
                    self.add(
                        "budget_threshold",
                        step,
                        f"{mark}% of the sensing budget consumed "
                        f"({budget_remaining:.1f} units remaining)",
                        severity="info" if mark < 90 else "warning",
                        data={"used_fraction": round(used, 4)},
                    )
