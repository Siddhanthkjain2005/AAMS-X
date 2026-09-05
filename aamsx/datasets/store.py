"""Offline Parquet/DuckDB cache for real spectrum recordings.

Layout::

    data/cached/<STATION>/<YYYYMMDD>/power.parquet     raw receiver digits, one row per timestep
                                    channels.parquet  frequency axis + quiet-time baseline
                                    manifest.json     provenance, checksums, geometry

Raw ``uint8`` digits are stored rather than calibrated floats: they are the
receiver's native precision, they compress far better, and keeping them means
the baseline percentile and occupancy threshold stay *reproducible knobs*
rather than choices baked irreversibly into the cache.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from aamsx.config import Settings, get_settings
from aamsx.contracts.spectrum import MeasurementCube, Provenance, RawRecording
from aamsx.datasets.calibration import Calibration, compute_calibration
from aamsx.logging import get_logger

log = get_logger(__name__)

ROW_GROUP_SIZE = 3600  # one 15-minute CALLISTO observation at 0.25 s cadence
SCHEMA_VERSION = 2


class CacheMiss(FileNotFoundError):
    """Raised when the offline cache cannot serve a requested window."""


@dataclass(frozen=True, slots=True)
class CachedRecording:
    """Metadata for one cached station-day, read from ``manifest.json``."""

    station: str
    day: str
    path: Path
    n_times: int
    n_channels: int
    cadence_sec: float
    epoch_utc: datetime
    freq_min_mhz: float
    freq_max_mhz: float
    occupancy: float
    live_channels: int
    dead_channels: int
    provenance: dict[str, Any]
    calibration: dict[str, Any]

    @property
    def duration_sec(self) -> float:
        return self.n_times * self.cadence_sec

    @property
    def recording_id(self) -> str:
        return f"{self.station}/{self.day}"

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_id": self.recording_id,
            "station": self.station,
            "day": self.day,
            "n_times": self.n_times,
            "n_channels": self.n_channels,
            "cadence_sec": self.cadence_sec,
            "epoch_utc": self.epoch_utc.isoformat(),
            "duration_sec": round(self.duration_sec, 1),
            "freq_min_mhz": self.freq_min_mhz,
            "freq_max_mhz": self.freq_max_mhz,
            "occupancy": self.occupancy,
            "live_channels": self.live_channels,
            "dead_channels": self.dead_channels,
            "provenance": self.provenance,
            "calibration": self.calibration,
        }


def recording_dir(settings: Settings, station: str, day: str) -> Path:
    return settings.cache_dir / station / day


def write_recording(raw: RawRecording, station: str, *, settings: Settings | None = None) -> Path:
    """Persist raw digits + axes + provenance into the offline cache."""
    settings = settings or get_settings()
    day = raw.epoch_utc.strftime("%Y%m%d")
    target = recording_dir(settings, station, day)
    target.mkdir(parents=True, exist_ok=True)
    n_times, n_channels = raw.digits.shape

    flat = pa.array(np.ascontiguousarray(raw.digits).reshape(-1), type=pa.uint8())
    pq.write_table(
        pa.table(
            {
                "t_sec": pa.array(raw.t_sec, type=pa.float64()),
                "available": pa.array(raw.available, type=pa.bool_()),
                "digits": pa.FixedSizeListArray.from_arrays(flat, n_channels),
            }
        ),
        target / "power.parquet",
        compression="zstd",
        compression_level=9,
        row_group_size=ROW_GROUP_SIZE,
        use_dictionary=False,
    )

    calibration = raw.calibration
    if calibration is None:
        calibration = compute_calibration(
            raw.digits,
            db_per_digit=settings.db_per_digit,
            percentile=settings.baseline_percentile,
            k_mad=settings.occupancy_k_mad,
            min_excess_db=settings.occupancy_threshold_db,
        )
    cube = raw.to_cube()
    per_channel = cube.occupancy().mean(axis=0).astype(np.float32)
    spread = raw.digits.max(axis=0).astype(np.int16) - raw.digits.min(axis=0).astype(np.int16)
    dead = spread <= 1
    pq.write_table(
        pa.table(
            {
                "channel_index": pa.array(np.arange(n_channels), type=pa.int32()),
                "freq_mhz": pa.array(raw.freq_mhz, type=pa.float64()),
                "noise_db": pa.array(calibration.noise_db, type=pa.float32()),
                "threshold_db": pa.array(calibration.threshold_db, type=pa.float32()),
                "occupancy": pa.array(per_channel, type=pa.float32()),
                "dead": pa.array(dead, type=pa.bool_()),
            }
        ),
        target / "channels.parquet",
        compression="zstd",
    )
    flat_baseline = pa.array(
        np.ascontiguousarray(calibration.baseline_blocks).reshape(-1), type=pa.float32()
    )
    pq.write_table(
        pa.table(
            {
                "block_index": pa.array(np.arange(calibration.n_blocks), type=pa.int32()),
                "baseline_db": pa.FixedSizeListArray.from_arrays(flat_baseline, n_channels),
            }
        ),
        target / "baseline.parquet",
        compression="zstd",
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "station": station,
        "day": day,
        "n_times": n_times,
        "n_channels": n_channels,
        "cadence_sec": raw.provenance.time_resolution_sec,
        "epoch_utc": raw.epoch_utc.isoformat(),
        "db_per_digit": settings.db_per_digit,
        "occupancy_threshold_db": settings.occupancy_threshold_db,
        "occupancy_k_mad": settings.occupancy_k_mad,
        "baseline_percentile": settings.baseline_percentile,
        "calibration": calibration.to_dict(),
        "freq_min_mhz": float(raw.freq_mhz.min()),
        "freq_max_mhz": float(raw.freq_mhz.max()),
        "occupancy": float(per_channel.mean()),
        "live_channels": int(((per_channel > 0.02) & (per_channel < 0.98)).sum()),
        "dead_channels": int(dead.sum()),
        "provenance": raw.provenance.to_dict(),
    }
    (target / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    size_mb = sum(f.stat().st_size for f in target.iterdir()) / 1e6
    log.info(
        "cache.written",
        extra={"recording": f"{station}/{day}", "steps": n_times, "mb": round(size_mb, 2)},
    )
    return target


# --------------------------------------------------------------------------- #
# reading
# --------------------------------------------------------------------------- #


def _read_manifest(path: Path) -> dict:
    try:
        return json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CacheMiss(f"unreadable cache manifest at {path}: {exc}") from exc


def _as_cached(path: Path, manifest: dict) -> CachedRecording:
    return CachedRecording(
        station=str(manifest["station"]),
        day=str(manifest["day"]),
        path=path,
        n_times=int(manifest["n_times"]),
        n_channels=int(manifest["n_channels"]),
        cadence_sec=float(manifest["cadence_sec"]),
        epoch_utc=datetime.fromisoformat(str(manifest["epoch_utc"])),
        freq_min_mhz=float(manifest["freq_min_mhz"]),
        freq_max_mhz=float(manifest["freq_max_mhz"]),
        occupancy=float(manifest["occupancy"]),
        live_channels=int(manifest["live_channels"]),
        dead_channels=int(manifest.get("dead_channels", 0)),
        provenance=dict(manifest["provenance"]),
        calibration=dict(manifest["calibration"]),
    )


def list_recordings(*, settings: Settings | None = None) -> list[CachedRecording]:
    """Every recording present in the offline cache, newest first."""
    settings = settings or get_settings()
    found: list[CachedRecording] = []
    if not settings.cache_dir.exists():
        return found
    for manifest_path in sorted(settings.cache_dir.glob("*/*/manifest.json")):
        path = manifest_path.parent
        try:
            found.append(_as_cached(path, _read_manifest(path)))
        except (CacheMiss, KeyError, ValueError) as exc:
            log.warning("cache.bad_recording", extra={"path": str(path), "error": str(exc)})
    found.sort(key=lambda r: (r.day, r.station), reverse=True)
    return found


def get_recording(recording_id: str, *, settings: Settings | None = None) -> CachedRecording:
    settings = settings or get_settings()
    station, _, day = recording_id.partition("/")
    path = recording_dir(settings, station, day)
    if not (path / "manifest.json").exists():
        available = ", ".join(r.recording_id for r in list_recordings(settings=settings)) or "none"
        raise CacheMiss(f"recording {recording_id!r} is not cached; available: {available}")
    return _as_cached(path, _read_manifest(path))


def load_raw(
    recording_id: str,
    *,
    start_step: int = 0,
    n_steps: int | None = None,
    settings: Settings | None = None,
) -> RawRecording:
    """Load a contiguous slice from the cache, touching only the needed row groups."""
    settings = settings or get_settings()
    record = get_recording(recording_id, settings=settings)
    stop_step = record.n_times if n_steps is None else min(record.n_times, start_step + n_steps)
    if start_step < 0 or start_step >= record.n_times or stop_step <= start_step:
        raise CacheMiss(
            f"window [{start_step}, {stop_step}) is outside recording "
            f"{recording_id} which has {record.n_times} steps"
        )

    handle = pq.ParquetFile(record.path / "power.parquet")
    offsets: list[int] = []
    cursor = 0
    for index in range(handle.num_row_groups):
        rows = handle.metadata.row_group(index).num_rows
        offsets.append(cursor)
        cursor += rows
    wanted = [
        index
        for index, offset in enumerate(offsets)
        if offset < stop_step and offset + handle.metadata.row_group(index).num_rows > start_step
    ]
    table = handle.read_row_groups(wanted, columns=["t_sec", "available", "digits"])
    local_start = start_step - offsets[wanted[0]]
    local_stop = local_start + (stop_step - start_step)

    digits = (
        table.column("digits")
        .combine_chunks()
        .flatten()
        .to_numpy(zero_copy_only=False)
        .reshape(-1, record.n_channels)[local_start:local_stop]
    )
    t_sec = table.column("t_sec").to_numpy(zero_copy_only=False)[local_start:local_stop]
    available = table.column("available").to_numpy(zero_copy_only=False)[local_start:local_stop]

    channels = pq.read_table(record.path / "channels.parquet")
    freq_mhz = np.asarray(channels.column("freq_mhz").to_numpy(zero_copy_only=False), np.float64)
    calibration = _load_calibration(record, channels)

    return RawRecording(
        digits=np.ascontiguousarray(digits, dtype=np.uint8),
        freq_mhz=freq_mhz,
        t_sec=np.asarray(t_sec, dtype=np.float64),
        epoch_utc=record.epoch_utc,
        available=np.asarray(available, dtype=bool),
        provenance=Provenance(**_provenance_kwargs(record.provenance)),
        calibration=calibration,
        start_step=start_step,
    )


def _load_calibration(record: CachedRecording, channels: pa.Table) -> Calibration:
    manifest_cal = dict(record.calibration)
    table = pq.read_table(record.path / "baseline.parquet")
    blocks = (
        table.column("baseline_db")
        .combine_chunks()
        .flatten()
        .to_numpy(zero_copy_only=False)
        .reshape(-1, record.n_channels)
        .astype(np.float32)
    )
    return Calibration(
        block_size=int(manifest_cal["block_size"]),
        baseline_blocks=blocks,
        noise_db=channels.column("noise_db").to_numpy(zero_copy_only=False).astype(np.float32),
        threshold_db=channels.column("threshold_db")
        .to_numpy(zero_copy_only=False)
        .astype(np.float32),
        db_per_digit=float(manifest_cal["db_per_digit"]),
        percentile=float(manifest_cal["percentile"]),
        k_mad=float(manifest_cal["k_mad"]),
        min_excess_db=float(manifest_cal["min_excess_db"]),
        n_times=record.n_times,
    )


def _provenance_kwargs(payload: dict) -> dict:
    data = dict(payload)
    for key in ("retrieved_at", "observed_from", "observed_to"):
        data[key] = datetime.fromisoformat(str(data[key]))
    data["preprocessing"] = tuple(data.get("preprocessing", ()))
    data["gaps"] = tuple(tuple(gap) for gap in data.get("gaps", ()))
    return data


def load_cube(
    recording_id: str,
    *,
    start_step: int = 0,
    n_steps: int | None = None,
    settings: Settings | None = None,
) -> MeasurementCube:
    """Load and calibrate a cache slice into a :class:`MeasurementCube`."""
    settings = settings or get_settings()
    raw = load_raw(recording_id, start_step=start_step, n_steps=n_steps, settings=settings)
    return raw.to_cube()
