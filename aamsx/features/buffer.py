"""Rolling observation buffer — the scheduler's entire memory of the episode.

Everything a scheduler is allowed to condition on is derived from this buffer,
which only ever receives observations the receiver actually paid for.  Keeping it
in one place is what makes the no-leakage guarantee checkable rather than
aspirational: if a quantity is not derivable from this buffer, it cannot reach a
decision.

The buffer is bounded, so memory use is constant in the episode length.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from aamsx.contracts.observation import Observation


@dataclass(frozen=True, slots=True)
class BufferEntry:
    step: int
    anchor: int
    detections: int
    window_size: int
    mean_measured_db: float
    max_measured_db: float
    mean_confidence: float
    reward: float
    cost: float
    available: bool


class TemporalBuffer:
    """Bounded history of observations, actions and rewards."""

    #: Smoothing for the *recent* per-region profiles (about a 60-look memory).
    PROFILE_ALPHA = 0.10
    #: Smoothing for the slow reference profile (about a 600-look memory).
    SLOW_PROFILE_ALPHA = 0.015

    def __init__(self, n_regions: int, *, capacity: int = 256) -> None:
        self.n_regions = int(n_regions)
        self.capacity = int(capacity)
        self.reset()

    def reset(self) -> None:
        self._entries: deque[BufferEntry] = deque(maxlen=self.capacity)
        self.total_observations = 0
        self.total_detections = 0
        self.total_cost = 0.0
        self.total_reward = 0.0
        self.previous_anchor: int | None = None
        self.visit_counts = np.zeros(self.n_regions, dtype=np.int32)
        self.detection_counts = np.zeros(self.n_regions, dtype=np.int32)
        self.last_measured_db = np.zeros(self.n_regions, dtype=np.float32)
        # Recent, decaying profiles. The cumulative counts above describe the whole
        # episode, which is exactly wrong for recognising *the environment I am in
        # now*: after a shift they still carry the old regime. These decay.
        self.recent_hit_profile = np.zeros(self.n_regions, dtype=np.float64)
        self.recent_level_profile = np.zeros(self.n_regions, dtype=np.float64)
        # A slower copy of the hit profile. The distance between the two is the
        # sharpest single indicator of a distribution shift available to a
        # scheduler: when the environment changes, *which* regions pay off changes
        # well before the total detection count does.
        self.slow_hit_profile = np.zeros(self.n_regions, dtype=np.float64)

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> tuple[BufferEntry, ...]:
        return tuple(self._entries)

    def push(self, observation: Observation, reward: float) -> None:
        detections = int(observation.detected.sum())
        measured = observation.measured_db.astype(np.float64)
        self._entries.append(
            BufferEntry(
                step=observation.step,
                anchor=int(observation.regions[0]),
                detections=detections,
                window_size=observation.window_size,
                mean_measured_db=float(measured.mean()) if measured.size else 0.0,
                max_measured_db=float(measured.max()) if measured.size else 0.0,
                mean_confidence=float(observation.confidence.mean())
                if observation.confidence.size
                else 0.0,
                reward=float(reward),
                cost=float(observation.cost),
                available=bool(observation.available),
            )
        )
        self.previous_anchor = int(observation.regions[0])
        self.total_cost += float(observation.cost)
        self.total_reward += float(reward)
        if observation.available:
            self.total_observations += observation.window_size
            self.total_detections += detections
            self.visit_counts[observation.regions] += 1
            self.detection_counts[observation.regions] += observation.detected.astype(np.int32)
            self.last_measured_db[observation.regions] = observation.measured_db
            alpha = self.PROFILE_ALPHA
            regions = observation.regions
            self.recent_hit_profile[regions] += alpha * (
                observation.detected.astype(np.float64) - self.recent_hit_profile[regions]
            )
            level = np.tanh(observation.measured_db.astype(np.float64) / 6.0)
            self.recent_level_profile[regions] += alpha * (
                level - self.recent_level_profile[regions]
            )
            self.slow_hit_profile[regions] += self.SLOW_PROFILE_ALPHA * (
                observation.detected.astype(np.float64) - self.slow_hit_profile[regions]
            )

    # ---- summaries used by the encoder ---------------------------------------

    def recent(self, window: int) -> tuple[BufferEntry, ...]:
        if window <= 0 or not self._entries:
            return ()
        return tuple(self._entries)[-window:]

    def recent_rewards(self, window: int = 32) -> np.ndarray:
        return np.array([entry.reward for entry in self.recent(window)], dtype=np.float32)

    def recent_hit_rate(self, window: int = 32) -> float:
        entries = [entry for entry in self.recent(window) if entry.available]
        if not entries:
            return 0.0
        looks = sum(entry.window_size for entry in entries)
        return float(sum(entry.detections for entry in entries) / max(looks, 1))

    def recent_activity(self, window: int = 32) -> np.ndarray:
        """Detections per step over the recent window — the periodicity input."""
        return np.array([entry.detections for entry in self.recent(window)], dtype=np.float64)

    def recent_variance(self, window: int = 32) -> float:
        activity = self.recent_activity(window)
        return float(activity.var()) if activity.size > 1 else 0.0

    def profile_divergence(self) -> float:
        """Mean absolute distance between the fast and slow per-region hit profiles."""
        return float(np.abs(self.recent_hit_profile - self.slow_hit_profile).mean())

    def region_hit_rate(self) -> np.ndarray:
        return self.detection_counts / np.maximum(self.visit_counts, 1)

    def coverage(self) -> float:
        """Fraction of the band visited at least once."""
        return float((self.visit_counts > 0).mean())

    def switch_rate(self, window: int = 32) -> float:
        entries = self.recent(window)
        if len(entries) < 2:
            return 0.0
        anchors = np.array([entry.anchor for entry in entries], dtype=np.float64)
        scale = max(1.0, float(self.n_regions - 1))
        return float(np.abs(np.diff(anchors)).mean() / scale)
