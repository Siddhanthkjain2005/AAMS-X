"""The window index: a scenario library mined from real measurements.

A synthetic platform would let you *ask* for a periodic environment.  AAMS-X has
only real recordings, so instead it measures every candidate window in the cache
and lets you *search* for one.  ``build_index`` walks each cached recording at
several time scales, characterises every window with
:func:`aamsx.environment.characterize.characterise`, and writes the result to a
Parquet table that DuckDB can query.

That inversion is the point: scenario presets in the UI are queries against
measured statistics, so every "Periodic Challenge" or "Sudden Shift" scenario
points at a real time range in a real recording, and the numbers describing it
were measured rather than declared.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from aamsx.config import Settings, get_settings
from aamsx.datasets.store import CachedRecording, list_recordings, load_raw
from aamsx.environment.characterize import characterise
from aamsx.environment.grid import bin_time, build_grid, region_margin_db
from aamsx.logging import get_logger

log = get_logger(__name__)

INDEX_NAME = "windows.parquet"
DEFAULT_TIME_BINS: tuple[int, ...] = (4, 20, 60)
"""Environment cadences to profile: 1 s, 5 s and 15 s per step at 0.25 s native."""

DEFAULT_WINDOW_STEPS: tuple[int, ...] = (400, 600, 1200)
"""Window lengths profiled, in environment steps.

Three lengths matter because every scenario is built to the same 1200-step horizon:
a single-phase experiment uses one 1200-step window, a two-phase splice uses two
600-step windows, and an A->B->A' recurrence uses three 400-step ones. Indexing each
length separately means the statistics quoted in a scenario description describe
exactly the block that will be replayed, not a longer window it was cut from.
"""

CHUNK_SAMPLES = 40_000


@dataclass(frozen=True, slots=True)
class WindowRef:
    """One indexed, characterised window — a ready-made scenario segment."""

    recording_id: str
    station: str
    start_step: int
    time_bin: int
    n_steps: int
    n_regions: int
    stats: dict[str, Any]
    profile: tuple[float, ...] = ()
    """Per-region occupancy — the shape of the environment, used to pick genuinely
    dissimilar pairs for a distribution shift and similar ones for a recurrence."""

    @property
    def duration_sec(self) -> float:
        return self.n_steps * self.time_bin * 0.25

    def to_dict(self) -> dict[str, object]:
        return {
            "recording_id": self.recording_id,
            "station": self.station,
            "start_step": self.start_step,
            "time_bin": self.time_bin,
            "n_steps": self.n_steps,
            "n_regions": self.n_regions,
            "duration_sec": round(self.duration_sec, 1),
            **self.stats,
        }


def region_margin_series(
    record: CachedRecording,
    n_regions: int,
    *,
    settings: Settings | None = None,
    freq_range_mhz: tuple[float, float] | None = None,
) -> np.ndarray:
    """Full-length ``(T_native, R)`` margin matrix, computed in bounded chunks."""
    settings = settings or get_settings()
    grid = None
    blocks: list[np.ndarray] = []
    for offset in range(0, record.n_times, CHUNK_SAMPLES):
        count = min(CHUNK_SAMPLES, record.n_times - offset)
        raw = load_raw(record.recording_id, start_step=offset, n_steps=count, settings=settings)
        cube = raw.to_cube()
        if grid is None:
            grid = build_grid(cube.freq_mhz, n_regions, freq_range_mhz=freq_range_mhz)
        blocks.append(region_margin_db(cube.power_db, cube.threshold_vector(), grid))
        del cube, raw
    return np.concatenate(blocks, axis=0)


def build_index(
    *,
    n_regions: int = 48,
    window_steps: tuple[int, ...] = DEFAULT_WINDOW_STEPS,
    time_bins: tuple[int, ...] = DEFAULT_TIME_BINS,
    settings: Settings | None = None,
    progress: bool = False,
) -> int:
    """Characterise every window in the cache and write the Parquet index."""
    settings = settings or get_settings()
    records = list_recordings(settings=settings)
    if not records:
        raise FileNotFoundError("the offline cache is empty; run scripts/fetch_real_data.py first")

    rows: list[dict[str, object]] = []
    for record in records:
        margin = region_margin_series(record, n_regions, settings=settings)
        for time_bin in time_bins:
            binned = bin_time(margin, time_bin)
            for span in window_steps:
                if binned.shape[0] < span:
                    continue
                stride = max(1, span // 2)
                for start in range(0, binned.shape[0] - span + 1, stride):
                    block = binned[start : start + span]
                    stats = characterise(block > 0.0, block)
                    payload = stats.to_dict()
                    profile = payload.pop("per_region_occupancy")
                    rows.append(
                        {
                            "recording_id": record.recording_id,
                            "station": record.station,
                            "start_step": start * time_bin,
                            "time_bin": time_bin,
                            "n_steps": span,
                            "n_regions": n_regions,
                            "duration_sec": round(span * time_bin * record.cadence_sec, 1),
                            "profile": profile,
                            **payload,
                        }
                    )
        if progress:
            log.info("index.recording", extra={"recording": record.recording_id, "rows": len(rows)})
        del margin

    table = pa.Table.from_pylist(rows)
    settings.index_dir.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, settings.index_dir / INDEX_NAME, compression="zstd")
    log.info("index.written", extra={"rows": len(rows), "path": str(settings.index_dir)})
    return len(rows)


def index_path(settings: Settings | None = None):
    settings = settings or get_settings()
    return settings.index_dir / INDEX_NAME


def query(sql: str, *, settings: Settings | None = None) -> list[dict[str, object]]:
    """Run a DuckDB query against the window index.

    ``windows`` is bound to the Parquet file; the caller writes ordinary SQL.
    """
    settings = settings or get_settings()
    path = index_path(settings)
    if not path.exists():
        raise FileNotFoundError(f"window index missing at {path}; run scripts/build_index.py")
    connection = duckdb.connect(database=":memory:")
    try:
        connection.execute(f"CREATE VIEW windows AS SELECT * FROM read_parquet('{path}')")
        cursor = connection.execute(sql)
        columns = [description[0] for description in cursor.description]
        return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]
    finally:
        connection.close()
