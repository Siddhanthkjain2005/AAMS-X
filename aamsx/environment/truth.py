"""Hidden environment state, assembled from spliced real recordings.

Nothing in this module is generated.  A scenario names real cached windows; this
module loads them, projects each onto the shared region action space, and
concatenates them into one hidden truth matrix.  The concatenation boundary is
the change point: the timing is known exactly because *we* chose where to cut,
while the activity either side is entirely measured.

Everything here is hidden state.  It is reachable only through
:class:`aamsx.environment.replay.ReplayEnvironment`, which enforces that a
scheduler can see nothing but the cells it paid to observe.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aamsx.config import Settings, get_settings
from aamsx.contracts.scenario import ScenarioSpec, SegmentSpec
from aamsx.contracts.spectrum import Provenance
from aamsx.datasets.store import get_recording, load_raw
from aamsx.environment.characterize import WindowStats, characterise
from aamsx.environment.grid import RegionGrid, bin_time, build_grid, region_margin_db
from aamsx.logging import get_logger

log = get_logger(__name__)


class ScenarioUnsatisfiable(ValueError):
    """Raised when a scenario asks for data the cache cannot provide."""


@dataclass(frozen=True, slots=True)
class SegmentTruth:
    """One spliced-in real window, already projected onto the region grid."""

    spec: SegmentSpec
    station: str
    grid: RegionGrid
    margin_db: np.ndarray  # (T_s, R) float32, dB above the per-channel threshold
    available: np.ndarray  # (T_s,) bool
    t_utc_sec: np.ndarray  # (T_s,) float64, absolute UTC seconds
    provenance: Provenance
    stats: WindowStats

    @property
    def n_steps(self) -> int:
        return int(self.margin_db.shape[0])

    def to_dict(self) -> dict[str, object]:
        return {
            **self.spec.to_dict(),
            "station": self.station,
            "grid": self.grid.to_dict(),
            "stats": self.stats.to_dict(),
            "provenance": self.provenance.to_dict(),
            "availability": round(float(self.available.mean()), 5),
        }


@dataclass(frozen=True, slots=True)
class EnvironmentTruth:
    """The complete hidden state of one episode."""

    margin_db: np.ndarray  # (T, R) float32
    occupied: np.ndarray  # (T, R) bool
    available: np.ndarray  # (T,) bool
    segment_of_step: np.ndarray  # (T,) int32
    t_utc_sec: np.ndarray  # (T,) float64
    segments: tuple[SegmentTruth, ...]

    @property
    def horizon(self) -> int:
        return int(self.margin_db.shape[0])

    @property
    def n_regions(self) -> int:
        return int(self.margin_db.shape[1])

    def grid_at(self, step: int) -> RegionGrid:
        """The frequency mapping in force at ``step`` — it changes at a splice."""
        return self.segments[int(self.segment_of_step[min(step, self.horizon - 1)])].grid

    def oracle_window_counts(self, window_size: int) -> np.ndarray:
        """``(T, R)`` count of truly occupied regions per window anchor.

        Evaluation only.  This is the clairvoyant benchmark used to compute
        regret; it is never exposed to a scheduler.
        """
        occupied = self.occupied.astype(np.int16)
        cumulative = np.cumsum(occupied, axis=1)
        padded = np.concatenate([np.zeros((self.horizon, 1), np.int16), cumulative], axis=1)
        anchors = self.n_regions - window_size + 1
        counts = padded[:, window_size : window_size + anchors] - padded[:, :anchors]
        return counts.astype(np.int16)


def _segment_truth(
    segment: SegmentSpec,
    *,
    n_regions: int,
    time_bin: int,
    freq_range_mhz: tuple[float, float] | None,
    settings: Settings,
) -> SegmentTruth:
    record = get_recording(segment.recording_id, settings=settings)
    needed = segment.n_steps * time_bin
    if segment.start_step + needed > record.n_times:
        raise ScenarioUnsatisfiable(
            f"{segment.recording_id} has {record.n_times} samples; segment needs "
            f"{needed} starting at {segment.start_step} "
            f"({segment.n_steps} steps x time_bin {time_bin})"
        )
    raw = load_raw(
        segment.recording_id, start_step=segment.start_step, n_steps=needed, settings=settings
    )
    cube = raw.to_cube()
    try:
        grid = build_grid(cube.freq_mhz, n_regions, freq_range_mhz=freq_range_mhz)
    except ValueError as exc:
        raise ScenarioUnsatisfiable(
            f"{segment.recording_id} covers {cube.freq_mhz.min():.1f}-"
            f"{cube.freq_mhz.max():.1f} MHz and cannot supply {n_regions} regions"
            f"{f' inside {freq_range_mhz} MHz' if freq_range_mhz else ''}: {exc}"
        ) from exc

    margin = bin_time(region_margin_db(cube.power_db, cube.threshold_vector(), grid), time_bin)
    absolute = raw.epoch_utc.timestamp() + cube.t_sec
    binned_time = absolute[: margin.shape[0] * time_bin : time_bin]
    # A step is unavailable when the archive time axis jumps: the receiver
    # published nothing for that interval and AAMS-X refuses to invent it.
    expected = float(record.cadence_sec) * time_bin
    deltas = np.diff(binned_time, prepend=binned_time[0] - expected)
    available = deltas < expected * 1.5
    stats = characterise(margin > 0.0, margin)
    return SegmentTruth(
        spec=segment,
        station=record.station,
        grid=grid,
        margin_db=np.ascontiguousarray(margin, dtype=np.float32),
        available=available,
        t_utc_sec=binned_time,
        provenance=raw.provenance,
        stats=stats,
    )


def build_truth(spec: ScenarioSpec, *, settings: Settings | None = None) -> EnvironmentTruth:
    """Load and splice every segment of a scenario into one hidden truth block."""
    settings = settings or get_settings()
    if not spec.segments:
        raise ScenarioUnsatisfiable(f"scenario {spec.scenario_id!r} declares no segments")

    segments = tuple(
        _segment_truth(
            segment,
            n_regions=spec.n_regions,
            time_bin=spec.time_bin,
            freq_range_mhz=spec.freq_range_mhz,
            settings=settings,
        )
        for segment in spec.segments
    )
    margin = np.concatenate([segment.margin_db for segment in segments], axis=0)
    available = np.concatenate([segment.available for segment in segments])
    t_utc = np.concatenate([segment.t_utc_sec for segment in segments])
    owner = np.concatenate(
        [np.full(segment.n_steps, index, np.int32) for index, segment in enumerate(segments)]
    )
    log.info(
        "truth.built",
        extra={
            "scenario": spec.scenario_id,
            "horizon": int(margin.shape[0]),
            "regions": spec.n_regions,
            "occupancy": round(float((margin > 0).mean()), 4),
            "segments": len(segments),
        },
    )
    return EnvironmentTruth(
        margin_db=margin,
        occupied=margin > 0.0,
        available=available,
        segment_of_step=owner,
        t_utc_sec=t_utc,
        segments=segments,
    )
