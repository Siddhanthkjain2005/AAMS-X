"""Empirical characterisation of a real observation window.

AAMS-X cannot *specify* activity probability, persistence or periodicity the way
a synthetic generator would — the data is measured, so those properties have to
be **discovered**.  This module measures them, which is what lets the scenario
library be mined from the archive ("find me a window that behaves periodically")
instead of hand-asserted.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np


@dataclass(frozen=True, slots=True)
class WindowStats:
    """Measured behaviour of one region x time occupancy block."""

    n_steps: int
    n_regions: int
    occupancy: float
    per_region_occupancy: np.ndarray = field(repr=False)
    persistence: float
    """P(occupied at t+1 | occupied at t), pooled over active regions."""

    onset_rate: float
    """P(occupied at t+1 | free at t) — how often new activity appears."""

    burstiness: float
    """Coefficient of variation of on-run lengths; 0 = perfectly regular."""

    intermittent_regions: int
    """Regions occupied between 2% and 50% of the time — the interesting ones."""

    persistent_regions: int
    quiet_regions: int
    period_steps: int
    """Dominant autocorrelation lag of total activity, 0 when none is significant."""

    period_strength: float
    concentration: float
    """Gini coefficient of per-region occupancy: how unevenly activity is spread."""

    profile_drift: float
    """L1 distance between the occupancy profiles of the first and second half."""

    mean_margin_db: float
    p95_margin_db: float
    archetype: str

    def to_dict(self) -> dict[str, object]:
        return {
            "n_steps": self.n_steps,
            "n_regions": self.n_regions,
            "occupancy": round(self.occupancy, 5),
            "persistence": round(self.persistence, 4),
            "onset_rate": round(self.onset_rate, 5),
            "burstiness": round(self.burstiness, 4),
            "intermittent_regions": self.intermittent_regions,
            "persistent_regions": self.persistent_regions,
            "quiet_regions": self.quiet_regions,
            "period_steps": self.period_steps,
            "period_strength": round(self.period_strength, 4),
            "concentration": round(self.concentration, 4),
            "profile_drift": round(self.profile_drift, 5),
            "mean_margin_db": round(self.mean_margin_db, 3),
            "p95_margin_db": round(self.p95_margin_db, 3),
            "archetype": self.archetype,
            "per_region_occupancy": [round(float(v), 5) for v in self.per_region_occupancy],
        }


def _gini(values: np.ndarray) -> float:
    if values.size == 0 or float(values.sum()) <= 0.0:
        return 0.0
    ordered = np.sort(values.astype(np.float64))
    n = ordered.size
    index = np.arange(1, n + 1)
    return float((2.0 * (index * ordered).sum()) / (n * ordered.sum()) - (n + 1.0) / n)


def _run_lengths(series: np.ndarray) -> np.ndarray:
    """Lengths of contiguous ``True`` runs in a 1-D boolean array."""
    padded = np.concatenate(([False], series, [False]))
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return edges[1::2] - edges[::2]


def dominant_period(
    signal: np.ndarray,
    *,
    min_lag: int = 4,
    max_lag: int | None = None,
    min_prominence: float = 0.12,
) -> tuple[int, float]:
    """Strongest *prominent* autocorrelation peak of a 1-D signal.

    Taking the global ACF maximum would be wrong, and wrongly convincing: a
    merely persistent series has an ACF that decays monotonically, so the
    largest value always sits at the smallest lag examined and every recording
    would be declared "periodic with period 3".  A real period instead appears
    as a *local* maximum that rises above the preceding trough.

    A candidate lag is therefore accepted only when it is a local maximum, rises
    ``min_prominence`` above the lowest ACF value between ``min_lag`` and itself,
    and exceeds the Bartlett white-noise bound ``1.96 / sqrt(n)``.
    """
    series = np.asarray(signal, dtype=np.float64)
    n = series.size
    if n < 4 * min_lag:
        return 0, 0.0
    centred = series - series.mean()
    variance = float((centred**2).sum())
    if variance <= 1e-12:
        return 0, 0.0
    limit = max_lag if max_lag is not None else max(min_lag + 2, n // 3)
    limit = min(limit, n - 2)
    if limit <= min_lag + 1:
        return 0, 0.0
    acf = np.correlate(centred, centred, mode="full")[n - 1 :][: limit + 1] / variance

    significance = 1.96 / np.sqrt(n)
    best_lag, best_strength = 0, 0.0
    for lag in range(min_lag, limit):
        if not (acf[lag] > acf[lag - 1] and acf[lag] >= acf[lag + 1]):
            continue
        trough = float(acf[min_lag - 1 : lag].min())
        prominence = float(acf[lag]) - trough
        if prominence < min_prominence or acf[lag] < significance:
            continue
        if float(acf[lag]) > best_strength:
            best_lag, best_strength = lag, float(acf[lag])
    return best_lag, best_strength


def characterise(occupied: np.ndarray, margin_db: np.ndarray) -> WindowStats:
    """Measure the behaviour of a real occupancy block."""
    if occupied.ndim != 2:
        raise ValueError(f"expected a (T, R) occupancy matrix, got {occupied.shape}")
    n_steps, n_regions = occupied.shape
    per_region = occupied.mean(axis=0)

    current, following = occupied[:-1], occupied[1:]
    on_total = int(current.sum())
    off_total = int(current.size - on_total)
    persistence = float((current & following).sum() / on_total) if on_total else 0.0
    onset_rate = float((~current & following).sum() / off_total) if off_total else 0.0

    runs = np.concatenate(
        [_run_lengths(occupied[:, region]) for region in range(n_regions)] or [np.zeros(0)]
    )
    burstiness = float(runs.std() / runs.mean()) if runs.size > 1 and runs.mean() > 0 else 0.0

    period, strength = dominant_period(occupied.sum(axis=1).astype(np.float64))
    half = n_steps // 2
    drift = (
        float(np.abs(occupied[:half].mean(axis=0) - occupied[half:].mean(axis=0)).mean())
        if half > 0
        else 0.0
    )

    stats = WindowStats(
        n_steps=n_steps,
        n_regions=n_regions,
        occupancy=float(occupied.mean()),
        per_region_occupancy=per_region.astype(np.float32),
        persistence=persistence,
        onset_rate=onset_rate,
        burstiness=burstiness,
        intermittent_regions=int(((per_region >= 0.02) & (per_region <= 0.5)).sum()),
        persistent_regions=int((per_region > 0.5).sum()),
        quiet_regions=int((per_region < 0.02).sum()),
        period_steps=period,
        period_strength=strength,
        concentration=_gini(per_region),
        profile_drift=drift,
        mean_margin_db=float(margin_db.mean()),
        p95_margin_db=float(np.percentile(margin_db, 95)),
        archetype="",
    )
    return replace(stats, archetype=classify(stats))


def classify(stats: WindowStats) -> str:
    """Assign a human-readable archetype from the measured statistics."""
    if stats.occupancy < 0.02:
        return "quiet"
    if stats.period_strength > 0.55 and stats.period_steps > 0:
        return "periodic"
    if stats.persistent_regions >= max(2, stats.n_regions // 8) and stats.persistence > 0.9:
        return "persistent"
    if stats.persistence < 0.55:
        return "rapidly-changing"
    if stats.burstiness > 1.6:
        return "bursting"
    if stats.intermittent_regions >= stats.n_regions // 3:
        return "intermittent"
    return "mixed"
