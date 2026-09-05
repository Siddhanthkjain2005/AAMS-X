"""Pareto analysis over the four objectives AAMS-X actually trades off.

Reward collapses detection, information, delay, false alarms and switching into
one number using weights nobody can justify universally.  The Pareto frontier
refuses that collapse: it reports which policies are not beaten on *every* axis
at once, so a reader who cares more about response time than about false alarms
can pick for themselves.

Axes and their directions are declared explicitly in :data:`OBJECTIVES`; a policy
dominates another when it is at least as good on all four and strictly better on
one.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

#: ``metric -> +1 if larger is better, -1 if smaller is better``.
OBJECTIVES: dict[str, int] = {
    "sustained_detection_probability": +1,
    "time_to_detect_capped": -1,
    "false_alarm_rate": -1,
    "sensing_cost": -1,
}

AXIS_LABELS: dict[str, str] = {
    "sustained_detection_probability": "Detection performance",
    "time_to_detect_capped": "Time to detect (missed = cap)",
    "false_alarm_rate": "False-alarm rate",
    "sensing_cost": "Sensing cost",
}


@dataclass(frozen=True, slots=True)
class ParetoPoint:
    label: str
    values: dict[str, float]
    dominated_by: tuple[str, ...]

    @property
    def on_frontier(self) -> bool:
        return not self.dominated_by

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "values": {key: round(float(value), 6) for key, value in self.values.items()},
            "on_frontier": self.on_frontier,
            "dominated_by": list(self.dominated_by),
        }


def _dominates(a: dict[str, float], b: dict[str, float], objectives: dict[str, int]) -> bool:
    better_anywhere = False
    for metric, direction in objectives.items():
        left, right = a.get(metric), b.get(metric)
        if left is None or right is None or not (np.isfinite(left) and np.isfinite(right)):
            return False
        if direction * (left - right) < -1e-12:
            return False
        if direction * (left - right) > 1e-12:
            better_anywhere = True
    return better_anywhere


def frontier(
    points: dict[str, dict[str, float]], *, objectives: dict[str, int] | None = None
) -> list[ParetoPoint]:
    """Classify each labelled point as on or off the Pareto frontier."""
    axes = objectives or OBJECTIVES
    result: list[ParetoPoint] = []
    for label, values in points.items():
        dominators = tuple(
            other
            for other, other_values in points.items()
            if other != label and _dominates(other_values, values, axes)
        )
        result.append(ParetoPoint(label=label, values=dict(values), dominated_by=dominators))
    result.sort(key=lambda point: (not point.on_frontier, point.label))
    return result


def describe(points: list[ParetoPoint]) -> dict[str, object]:
    """Serialise a frontier, including whether it is actually informative.

    A point missing an axis can neither dominate nor be dominated (see
    :func:`_dominates`), so if *every* point is missing the same axis the result is
    a frontier containing everything — which looks like "all policies are optimal"
    but means "the comparison could not be made".  ``axes_missing`` and
    ``vacuous`` say so out loud rather than letting a caller read the empty result
    as a finding.
    """
    missing = sorted(
        {metric for point in points for metric in OBJECTIVES if metric not in point.values}
    )
    vacuous = bool(missing) and len(points) > 1 and all(point.on_frontier for point in points)
    return {
        "axes_missing": missing,
        "vacuous": vacuous,
        "objectives": [
            {
                "metric": metric,
                "label": AXIS_LABELS.get(metric, metric),
                "direction": "maximise" if direction > 0 else "minimise",
            }
            for metric, direction in OBJECTIVES.items()
        ],
        "points": [point.to_dict() for point in points],
        "frontier": [point.label for point in points if point.on_frontier],
    }
