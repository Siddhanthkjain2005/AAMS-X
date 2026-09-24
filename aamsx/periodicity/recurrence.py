"""Periodicity and recurrence estimation from a scheduler's own observations.

Estimating per-region periodicity directly is not possible here, and pretending
otherwise would be the easiest place in this codebase to fake a result: a region
is observed on maybe one step in twelve, so a per-region autocorrelation would be
computed from a handful of coincidental sample pairs.

AAMS-X splits the problem instead.

* The **period** is estimated from the total detection count per step.  That
  signal exists at every step, because the receiver always dwells somewhere, so
  its autocorrelation is computed from dense, genuinely observed data.
* The **per-region recurrence score** is then a phase model.  Once a period ``T``
  is known, each region's observation history is bucketed by phase and AAMS-X
  measures the hit rate in each bucket.  A region whose detections concentrate at
  one phase scores highly when that phase comes round again, and every cycle
  contributes to the same buckets — so the estimate is stable at the sampling
  rates a real scheduler achieves.

A region with no phase preference scores zero, which is the honest answer.
"""

from __future__ import annotations

import numpy as np

from aamsx.environment.characterize import dominant_period


class PeriodicityEngine:
    """Global period estimation plus per-region phase preference."""

    def __init__(
        self,
        n_regions: int,
        *,
        history: int = 720,
        min_history: int = 96,
        refresh_every: int = 24,
        max_phase_bins: int = 12,
        min_bucket_observations: int = 3,
        confirmations: int = 2,
    ) -> None:
        self.n_regions = int(n_regions)
        self.history = int(history)
        self.min_history = int(min_history)
        self.refresh_every = int(refresh_every)
        self.max_phase_bins = int(max_phase_bins)
        self.min_bucket_observations = int(min_bucket_observations)
        self.confirmations = int(confirmations)
        self.reset()

    def reset(self) -> None:
        self._activity: list[float] = []
        self.period = 0
        self.strength = 0.0
        self.n_bins = 0
        self._hits = np.zeros((self.n_regions, self.max_phase_bins), dtype=np.float64)
        self._looks = np.zeros((self.n_regions, self.max_phase_bins), dtype=np.float64)
        self._observations = np.zeros(self.n_regions, dtype=np.float64)
        self._detections = np.zeros(self.n_regions, dtype=np.float64)
        self._step = 0
        self._candidate = 0
        self._candidate_hits = 0

    # ---- ingestion -----------------------------------------------------------

    def observe(
        self, step: int, detections: int, regions: np.ndarray, detected: np.ndarray
    ) -> None:
        """Record one step: the global detection count and this window's outcome."""
        self._step = int(step)
        self._activity.append(float(detections))
        if len(self._activity) > self.history:
            del self._activity[0]

        self._observations[regions] += 1.0
        self._detections[regions] += detected.astype(np.float64)
        if self.period > 0 and self.n_bins > 0:
            bucket = self._phase_bin(step)
            self._looks[regions, bucket] += 1.0
            self._hits[regions, bucket] += detected.astype(np.float64)

        if step % self.refresh_every == 0:
            self.refresh()

    def refresh(self) -> None:
        """Re-estimate the dominant period from the dense activity trace.

        A new period is only adopted after it has been measured on
        ``confirmations`` consecutive refreshes.  Without that guard the estimate
        flickers between neighbouring lags on real data and the UI ends up
        announcing a different "discovered period" every few seconds — which would
        be noise presented as insight.
        """
        if len(self._activity) < self.min_history:
            return
        signal = np.asarray(self._activity, dtype=np.float64)
        period, strength = dominant_period(signal, min_lag=4, max_lag=len(signal) // 3)
        if period == self.period:
            self.strength = strength
            self._candidate, self._candidate_hits = 0, 0
            return
        if period == self._candidate:
            self._candidate_hits += 1
        else:
            self._candidate, self._candidate_hits = int(period), 1
        if self._candidate_hits < self.confirmations:
            return
        self.period = int(period)
        self.strength = float(strength)
        self.n_bins = min(self.max_phase_bins, self.period) if self.period > 0 else 0
        # The phase alignment just changed, so previously bucketed evidence no
        # longer refers to the same phases and has to be discarded.
        self._hits[:] = 0.0
        self._looks[:] = 0.0

    def _phase_bin(self, step: int) -> int:
        if self.period <= 0 or self.n_bins <= 0:
            return 0
        phase = (step % self.period) / self.period
        return int(min(self.n_bins - 1, phase * self.n_bins))

    # ---- readout -------------------------------------------------------------

    @property
    def base_rate(self) -> np.ndarray:
        return self._detections / np.maximum(self._observations, 1.0)

    def region_scores(self, step: int) -> np.ndarray:
        """Per-region recurrence prediction for ``step``, in [0, 1].

        The score is the phase-conditional hit rate minus the region's overall hit
        rate, rectified and scaled by the confidence in the period itself.  A
        bucket with too little evidence contributes nothing.
        """
        if self.period <= 0 or self.n_bins <= 0 or self.strength <= 0.0:
            return np.zeros(self.n_regions, dtype=np.float64)
        bucket = self._phase_bin(step)
        looks = self._looks[:, bucket]
        enough = looks >= self.min_bucket_observations
        if not np.any(enough):
            return np.zeros(self.n_regions, dtype=np.float64)
        phase_rate = np.where(enough, self._hits[:, bucket] / np.maximum(looks, 1.0), 0.0)
        lift = np.clip(phase_rate - self.base_rate, 0.0, 1.0)
        return np.where(enough, lift * self.strength, 0.0)

    def region_periods(self) -> np.ndarray:
        """The period attributed to each region: the global one where evidence exists."""
        if self.period <= 0:
            return np.zeros(self.n_regions, dtype=np.int32)
        supported = self._looks.sum(axis=1) >= self.min_bucket_observations
        return np.where(supported, self.period, 0).astype(np.int32)

    def snapshot(self) -> dict[str, object]:
        return {
            "period_steps": int(self.period),
            "strength": round(float(self.strength), 5),
            "phase_bins": int(self.n_bins),
            "phase": int(self._phase_bin(self._step)),
            "history": len(self._activity),
            "region_scores": [round(float(v), 5) for v in self.region_scores(self._step)],
        }
