"""Ground-truth event bookkeeping.

An *event* is one contiguous run of occupancy in one region.  Events are the unit
in which detection performance actually matters: a scheduler that finds a
30-second burst on its 29th second technically detected it, and the honest way to
say that is "detected, with 29 steps of delay".

This tracker consumes the hidden truth and therefore lives strictly in the
evaluation layer.  It never touches a scheduler, and it is only ever advanced
*after* an action has been chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass(slots=True)
class Event:
    region: int
    onset_step: int
    end_step: int | None = None
    detected_step: int | None = None
    observations_while_active: int = 0

    @property
    def detected(self) -> bool:
        return self.detected_step is not None

    @property
    def delay(self) -> int | None:
        if self.detected_step is None:
            return None
        return self.detected_step - self.onset_step

    @property
    def duration(self) -> int | None:
        if self.end_step is None:
            return None
        return self.end_step - self.onset_step

    def to_dict(self) -> dict[str, object]:
        return {
            "region": self.region,
            "onset_step": self.onset_step,
            "end_step": self.end_step,
            "detected_step": self.detected_step,
            "delay": self.delay,
            "duration": self.duration,
            "observations_while_active": self.observations_while_active,
        }


@dataclass(slots=True)
class EventTracker:
    """Follows every ground-truth activity run and whether the scheduler caught it."""

    n_regions: int
    delay_cap: int = 64
    """Steps after which an undetected event stops accruing extra delay penalty."""

    events: list[Event] = field(default_factory=list)
    _open: dict[int, Event] = field(default_factory=dict)

    def reset(self) -> None:
        self.events = []
        self._open = {}

    def begin_step(self, step: int, occupied_now: np.ndarray) -> None:
        """Open events that just started and close those that just ended."""
        active = set(np.flatnonzero(occupied_now).tolist())
        for region in list(self._open):
            if region not in active:
                event = self._open.pop(region)
                event.end_step = step
        for region in active:
            if region not in self._open:
                event = Event(region=int(region), onset_step=int(step))
                self._open[region] = event
                self.events.append(event)

    def observe(self, step: int, regions: np.ndarray, detected: np.ndarray) -> None:
        """Credit any open event that this observation actually caught."""
        for region, hit in zip(regions.tolist(), detected.tolist(), strict=True):
            event = self._open.get(int(region))
            if event is None:
                continue
            event.observations_while_active += 1
            if hit and event.detected_step is None:
                event.detected_step = int(step)

    def finish(self, step: int) -> None:
        for region, event in self._open.items():
            if event.end_step is None:
                event.end_step = int(step)
            del region
        self._open = {}

    # ---- live signals used by the reward and the timeline ---------------------

    def pending_delay(self, step: int) -> float:
        """Mean normalised age of currently active but still undetected events."""
        ages = [
            min(step - event.onset_step, self.delay_cap)
            for event in self._open.values()
            if event.detected_step is None
        ]
        if not ages:
            return 0.0
        return float(np.mean(ages) / self.delay_cap)

    def undetected_now(self) -> int:
        return sum(1 for event in self._open.values() if event.detected_step is None)

    # ---- summaries -----------------------------------------------------------

    SUSTAINED_STEPS = 3
    """Minimum duration for an event to count as *sustained*.

    Nearly half of the ground-truth events in the cache last a single step, which
    a 4-region window scanning 48 regions cannot be expected to catch. Reporting
    only the all-events figure would therefore compress every policy into the same
    small range and hide real differences, so both are reported: the raw figure for
    completeness and the sustained figure for discrimination.
    """

    def summary(self) -> dict[str, float | int]:
        total = len(self.events)
        detected = [event for event in self.events if event.detected]
        delays = [event.delay for event in detected if event.delay is not None]
        durations = [event.duration for event in self.events if event.duration]
        sustained = [
            event for event in self.events if (event.duration or 0) >= self.SUSTAINED_STEPS
        ]
        sustained_hit = [event for event in sustained if event.detected]
        sustained_delays = [e.delay for e in sustained_hit if e.delay is not None]
        # Mean delay over *detected* events only is survivorship-biased: a policy
        # that catches nothing but the three easiest bursts reports a superb delay.
        # Charging every missed event the cap makes the metric monotone in what we
        # actually want — find activity, and find it soon.
        capped = [
            self.delay_cap if event.delay is None else min(event.delay, self.delay_cap)
            for event in sustained
        ]
        return {
            "time_to_detect_capped": float(np.mean(capped)) if capped else float("nan"),
            "delay_cap": self.delay_cap,
            "events_sustained": len(sustained),
            "events_sustained_detected": len(sustained_hit),
            "sustained_detection_probability": (
                len(sustained_hit) / len(sustained) if sustained else 0.0
            ),
            "sustained_detection_delay": (
                float(np.mean(sustained_delays)) if sustained_delays else float("nan")
            ),
            "events_total": total,
            "events_detected": len(detected),
            "event_detection_probability": (len(detected) / total) if total else 0.0,
            "mean_detection_delay": float(np.mean(delays)) if delays else float("nan"),
            "median_detection_delay": float(np.median(delays)) if delays else float("nan"),
            "p90_detection_delay": float(np.percentile(delays, 90)) if delays else float("nan"),
            "mean_event_duration": float(np.mean(durations)) if durations else 0.0,
            "events_missed": total - len(detected),
        }
