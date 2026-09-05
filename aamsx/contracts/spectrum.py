"""Canonical internal representation of spectrum measurements.

Every data adapter — e-CALLISTO, SigMF, ElectroSense — normalises into a
:class:`MeasurementCube`.  Downstream code (environment, analytics, UI) never
learns which adapter produced a cube; it only sees calibrated arrays plus the
:class:`Provenance` record that says where they came from.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal, Self

import numpy as np

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    from aamsx.datasets.calibration import Calibration

DataKind = Literal["measured", "model-inferred", "derived-label"]
Adapter = Literal["e-callisto", "sigmf", "electrosense", "user-import"]


@dataclass(frozen=True, slots=True)
class Provenance:
    """Auditable description of where a cube came from and what was done to it."""

    adapter: Adapter
    source_id: str
    source_url: str
    retrieved_at: datetime
    observed_from: datetime
    observed_to: datetime
    n_source_files: int
    n_samples: int
    freq_resolution_khz: float | None
    time_resolution_sec: float
    preprocessing: tuple[str, ...]
    license: str
    reference: str
    checksum: str
    is_synthetic: bool = False
    notes: str = ""
    gaps: tuple[tuple[str, str], ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "source_id": self.source_id,
            "source_url": self.source_url,
            "retrieved_at": self.retrieved_at.isoformat(),
            "observed_from": self.observed_from.isoformat(),
            "observed_to": self.observed_to.isoformat(),
            "n_source_files": self.n_source_files,
            "n_samples": self.n_samples,
            "freq_resolution_khz": self.freq_resolution_khz,
            "time_resolution_sec": self.time_resolution_sec,
            "preprocessing": list(self.preprocessing),
            "license": self.license,
            "reference": self.reference,
            "checksum": self.checksum,
            "is_synthetic": self.is_synthetic,
            "notes": self.notes,
            "gaps": [list(gap) for gap in self.gaps],
        }


def checksum_array(*arrays: np.ndarray) -> str:
    """Stable content hash used for provenance and experiment reproducibility."""
    digest = hashlib.sha256()
    for array in arrays:
        contiguous = np.ascontiguousarray(array)
        digest.update(str(contiguous.dtype).encode())
        digest.update(str(contiguous.shape).encode())
        digest.update(contiguous.tobytes())
    return digest.hexdigest()[:32]


@dataclass(slots=True)
class MeasurementCube:
    """A time x frequency block of calibrated spectrum measurements.

    ``power_db`` is *excess* power over each channel's own quiet-time baseline,
    which is what makes recordings from different receivers comparable at all.
    ``available`` marks timesteps that exist in the source archive; real archives
    have gaps and AAMS-X refuses to interpolate over them silently.
    """

    power_db: np.ndarray  # (T, C) float32, dB above per-channel baseline
    freq_mhz: np.ndarray  # (C,) float64
    t_sec: np.ndarray  # (T,) float64, seconds since epoch_utc
    epoch_utc: datetime
    available: np.ndarray  # (T,) bool
    provenance: Provenance
    occupancy_threshold_db: np.ndarray | float = 3.0
    """Per-channel occupancy decision threshold (a scalar is broadcast).

    A single global dB threshold would be wrong: e-CALLISTO receivers differ in
    gain and noise figure by more than 30 dB, so the same absolute excess means
    'loud carrier' at one station and 'thermal noise' at another.  AAMS-X
    therefore thresholds each channel against its own measured fluctuation —
    see :meth:`RawRecording.to_cube`.
    """

    def __post_init__(self) -> None:
        n_times, n_channels = self.power_db.shape
        if self.freq_mhz.shape != (n_channels,):
            raise ValueError(f"freq axis {self.freq_mhz.shape} != {n_channels} channels")
        if self.t_sec.shape != (n_times,):
            raise ValueError(f"time axis {self.t_sec.shape} != {n_times} steps")
        if self.available.shape != (n_times,):
            raise ValueError(f"availability mask {self.available.shape} != {n_times} steps")

    @property
    def n_times(self) -> int:
        return int(self.power_db.shape[0])

    @property
    def n_channels(self) -> int:
        return int(self.power_db.shape[1])

    @property
    def duration_sec(self) -> float:
        return float(self.t_sec[-1] - self.t_sec[0]) if self.n_times > 1 else 0.0

    def timestamps(self) -> list[datetime]:
        from datetime import timedelta

        return [self.epoch_utc + timedelta(seconds=float(s)) for s in self.t_sec]

    # ---- derived views (computed on demand, never stored) -------------------

    def occupancy(self) -> np.ndarray:
        """Reference occupancy labels: excess power above the per-channel threshold."""
        return self.power_db > self.occupancy_threshold_db

    def threshold_vector(self) -> np.ndarray:
        """The decision threshold as an explicit ``(C,)`` array."""
        return np.broadcast_to(
            np.asarray(self.occupancy_threshold_db, dtype=np.float32), (self.n_channels,)
        ).copy()

    def activity(self, *, scale_db: float = 12.0) -> np.ndarray:
        """Soft activity score in [0, 1] — a monotone squash of excess power."""
        return np.clip(self.power_db / scale_db, 0.0, 1.0).astype(np.float32)

    def label_confidence(self, *, margin_db: float = 2.0) -> np.ndarray:
        """How far each cell sits from the decision boundary, mapped to [0, 1]."""
        distance = np.abs(self.power_db - self.occupancy_threshold_db)
        return np.clip(distance / margin_db, 0.0, 1.0).astype(np.float32)

    def slice_time(self, start: int, stop: int) -> Self:
        return type(self)(
            power_db=self.power_db[start:stop],
            freq_mhz=self.freq_mhz,
            t_sec=self.t_sec[start:stop],
            epoch_utc=self.epoch_utc,
            available=self.available[start:stop],
            provenance=self.provenance,
            occupancy_threshold_db=self.occupancy_threshold_db,
        )

    def summary(self) -> dict[str, object]:
        occupancy = self.occupancy()
        per_channel = occupancy.mean(axis=0)
        return {
            "n_times": self.n_times,
            "n_channels": self.n_channels,
            "duration_sec": round(self.duration_sec, 2),
            "freq_min_mhz": round(float(self.freq_mhz.min()), 4),
            "freq_max_mhz": round(float(self.freq_mhz.max()), 4),
            "occupancy": round(float(occupancy.mean()), 5),
            "live_channels": int(((per_channel > 0.02) & (per_channel < 0.98)).sum()),
            "availability": round(float(self.available.mean()), 5),
            "p99_excess_db": round(float(np.percentile(self.power_db, 99)), 3),
            "kind": "measured",
        }


UTC_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


@dataclass(slots=True)
class RawRecording:
    """Uncalibrated receiver output, exactly as the archive published it.

    This is what the offline cache stores.  Keeping the raw ``uint8`` digits
    means the calibration policy (baseline quantile, dB-per-digit, occupancy
    threshold) stays a reproducible parameter instead of being frozen into the
    cache — re-running an old experiment with a new threshold is a config
    change, not a re-download.
    """

    digits: np.ndarray  # (T, C) uint8, native receiver scale
    freq_mhz: np.ndarray  # (C,) float64
    t_sec: np.ndarray  # (T,) float64, seconds since epoch_utc
    epoch_utc: datetime
    available: np.ndarray  # (T,) bool
    provenance: Provenance
    calibration: Calibration | None = None
    start_step: int = 0
    """Offset of this slice inside the full recording, needed to index the
    drift-tracking baseline correctly."""

    @property
    def n_times(self) -> int:
        return int(self.digits.shape[0])

    @property
    def n_channels(self) -> int:
        return int(self.digits.shape[1])

    def to_cube(
        self,
        *,
        db_per_digit: float = 0.25,
        occupancy_threshold_db: float = 1.5,
        baseline_percentile: float = 10.0,
        k_mad: float = 5.0,
    ) -> MeasurementCube:
        """Calibrate into excess power with per-channel occupancy thresholds.

        A stored :class:`~aamsx.datasets.calibration.Calibration` always wins:
        the keyword arguments only matter for a recording that has never been
        calibrated (a fresh download, or an imported SigMF file).
        """
        from aamsx.datasets.calibration import compute_calibration

        calibration = self.calibration
        if calibration is None:
            calibration = compute_calibration(
                self.digits,
                db_per_digit=db_per_digit,
                percentile=baseline_percentile,
                k_mad=k_mad,
                min_excess_db=occupancy_threshold_db,
            )
        return MeasurementCube(
            power_db=calibration.excess(self.digits, start_step=self.start_step),
            freq_mhz=self.freq_mhz,
            t_sec=self.t_sec,
            epoch_utc=self.epoch_utc,
            available=self.available,
            provenance=self.provenance,
            occupancy_threshold_db=calibration.threshold_db,
        )

    def slice_time(self, start: int, stop: int) -> Self:
        return type(self)(
            digits=self.digits[start:stop],
            freq_mhz=self.freq_mhz,
            t_sec=self.t_sec[start:stop],
            epoch_utc=self.epoch_utc,
            available=self.available[start:stop],
            provenance=self.provenance,
            calibration=self.calibration,
            start_step=self.start_step + start,
        )
