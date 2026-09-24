"""Dataset routes: the offline cache, provenance, and real-data analytics.

The spectrogram and analytics endpoints back the Real Spectrum Replay screen.
Everything they return is measured; every response carries the provenance record
and a ``kind`` field so the UI can label a panel *measured*, *derived-label* or
*model-inferred* rather than letting the reader assume.
"""

from __future__ import annotations

import contextlib

import numpy as np
from fastapi import APIRouter, HTTPException, Query

from aamsx.datasets.electrosense import status as _electrosense_status
from aamsx.datasets.stations import STATIONS, get_station
from aamsx.datasets.store import CacheMiss, get_recording, list_recordings, load_raw
from aamsx.datasets.windows import query as query_index
from aamsx.environment.characterize import characterise, dominant_period
from aamsx.environment.grid import bin_time, build_grid, region_margin_db

router = APIRouter(prefix="/datasets", tags=["datasets"])

MAX_SPECTROGRAM_COLUMNS = 1200


def _adapter_status() -> dict[str, object]:
    """The ElectroSense adapter's own report, trimmed to the catalogue's shape."""
    report = _electrosense_status()
    return {
        "name": "electrosense",
        "status": report["status"],
        "detail": report["detail"],
        "verified": report["verified"],
        "credentials_configured": report["credentials_configured"],
    }


@router.get("")
def datasets() -> dict[str, object]:
    """Every cached recording plus the station catalogue it came from."""
    recordings = list_recordings()
    catalogue = {station.name: station for station in STATIONS}
    payload = []
    for record in recordings:
        station = catalogue.get(record.station)
        payload.append(
            {
                **record.to_dict(),
                "station_meta": station.to_dict() if station else None,
                "role": station.role if station else "unknown",
                "kind": "measured",
            }
        )
    return {
        "data_mode": "REAL PUBLIC SPECTRUM REPLAY",
        "adapters": [
            {
                "name": "e-callisto",
                "status": "active",
                "detail": "Public FITS archive, no credentials required.",
            },
            {
                "name": "sigmf",
                "status": "import-only",
                "detail": "Upload a .sigmf-meta/.sigmf-data pair to ingest your own recording.",
            },
            # Asked, not assumed: the ElectroSense adapter reports its own state.
            # DNS-only by default so listing datasets never waits on a dead host.
            _adapter_status(),
        ],
        "recordings": payload,
        "catalogue": [station.to_dict() for station in STATIONS],
    }


# Declared before the ``/{station}/{day}`` routes on purpose: FastAPI matches in
# declaration order, so a parametrised path registered first would swallow
# ``/index/windows`` and answer it as a missing recording.
@router.get("/index/windows")
def windows(
    where: str = Query(default="TRUE"),
    order_by: str = Query(default="occupancy DESC"),
    limit: int = Query(default=25, ge=1, le=500),
) -> dict[str, object]:
    """Search the measured window index — the scenario library, as data."""
    banned = (";", "--", "/*", "attach", "copy", "install", "pragma", "create", "drop")
    for clause in (where, order_by):
        if any(token in clause.lower() for token in banned):
            raise HTTPException(status_code=422, detail="only simple SQL predicates are accepted")
    sql = (
        f"SELECT * EXCLUDE (profile) FROM windows WHERE {where} "
        f"ORDER BY {order_by}, recording_id, time_bin, start_step LIMIT {limit}"
    )
    try:
        rows = query_index(sql)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid query: {exc}") from exc
    return {"count": len(rows), "windows": rows}


@router.get("/{station}/{day}")
def dataset_detail(station: str, day: str) -> dict[str, object]:
    """Provenance panel content for one recording."""
    try:
        record = get_recording(f"{station}/{day}")
    except CacheMiss as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    meta = None
    with contextlib.suppress(KeyError):  # a cached recording from an unlisted station
        meta = get_station(station).to_dict()
    return {**record.to_dict(), "station_meta": meta, "kind": "measured"}


@router.get("/{station}/{day}/spectrogram")
def spectrogram(
    station: str,
    day: str,
    start_step: int = Query(default=0, ge=0),
    n_steps: int = Query(default=2400, ge=8, le=40000),
    n_regions: int = Query(default=64, ge=8, le=256),
    time_bin: int = Query(default=4, ge=1, le=600),
    freq_min_mhz: float | None = None,
    freq_max_mhz: float | None = None,
) -> dict[str, object]:
    """A real waterfall: region x time margin above each channel's own threshold."""
    recording_id = f"{station}/{day}"
    try:
        record = get_recording(recording_id)
        raw = load_raw(recording_id, start_step=start_step, n_steps=n_steps)
    except CacheMiss as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cube = raw.to_cube()
    freq_range = (
        (freq_min_mhz, freq_max_mhz)
        if freq_min_mhz is not None and freq_max_mhz is not None
        else None
    )
    try:
        grid = build_grid(cube.freq_mhz, n_regions, freq_range_mhz=freq_range)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    margin = bin_time(region_margin_db(cube.power_db, cube.threshold_vector(), grid), time_bin)
    if margin.shape[0] > MAX_SPECTROGRAM_COLUMNS:
        stride = int(np.ceil(margin.shape[0] / MAX_SPECTROGRAM_COLUMNS))
        margin = bin_time(margin, stride)
        time_bin *= stride
    occupied = margin > 0.0
    return {
        "recording_id": recording_id,
        "kind": "measured",
        "label_kind": "derived-label",
        "start_step": start_step,
        "time_bin": time_bin,
        "cadence_sec": record.cadence_sec * time_bin,
        "epoch_utc": record.epoch_utc.isoformat(),
        "n_steps": int(margin.shape[0]),
        "n_regions": int(margin.shape[1]),
        "grid": grid.to_dict(),
        # Margin in dB above each region's own decision threshold: 0 is the boundary.
        "margin_db": [[round(float(v), 2) for v in row] for row in margin],
        "occupancy": round(float(occupied.mean()), 5),
        "per_region_occupancy": [round(float(v), 5) for v in occupied.mean(axis=0)],
        "provenance": cube.provenance.to_dict(),
    }


@router.get("/{station}/{day}/analytics")
def analytics(
    station: str,
    day: str,
    start_step: int = Query(default=0, ge=0),
    n_steps: int = Query(default=9600, ge=64, le=80000),
    n_regions: int = Query(default=48, ge=8, le=256),
    time_bin: int = Query(default=4, ge=1, le=600),
) -> dict[str, object]:
    """Non-invasive analytics on real measurements.

    Activity segmentation, temporal statistics, recurrence estimation and an
    offline change-point scan — all computed from the recording itself, with no
    scheduler and no claim of interception performance.
    """
    recording_id = f"{station}/{day}"
    try:
        raw = load_raw(recording_id, start_step=start_step, n_steps=n_steps)
    except CacheMiss as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cube = raw.to_cube()
    grid = build_grid(cube.freq_mhz, n_regions)
    margin = bin_time(region_margin_db(cube.power_db, cube.threshold_vector(), grid), time_bin)
    occupied = margin > 0.0
    stats = characterise(occupied, margin)

    total = occupied.sum(axis=1).astype(np.float64)
    period, strength = dominant_period(total)
    # Offline change scan: distance between adjacent halves of a sliding window on
    # the per-region occupancy profile. Retrospective and therefore honest about
    # being an analysis, not a detector a scheduler could have used online.
    span = max(16, min(240, occupied.shape[0] // 8))
    scan_steps: list[int] = []
    scan_scores: list[float] = []
    for centre in range(span, occupied.shape[0] - span, max(1, span // 4)):
        before = occupied[centre - span : centre].mean(axis=0)
        after = occupied[centre : centre + span].mean(axis=0)
        scan_steps.append(int(centre))
        scan_scores.append(round(float(np.abs(before - after).mean()), 5))
    threshold = float(np.percentile(scan_scores, 95)) if scan_scores else 0.0
    change_points = [
        step for step, score in zip(scan_steps, scan_scores, strict=True) if score >= threshold
    ]

    return {
        "recording_id": recording_id,
        "kind": "measured",
        "derived": "derived-label",
        "time_bin": time_bin,
        "n_steps": int(occupied.shape[0]),
        "stats": stats.to_dict(),
        "activity_per_step": [int(v) for v in total],
        "periodicity": {
            "period_steps": int(period),
            "period_sec": round(period * time_bin * 0.25, 2),
            "strength": round(float(strength), 4),
            "method": "prominence-gated autocorrelation, Bartlett significance bound",
        },
        "change_scan": {
            "steps": scan_steps,
            "scores": scan_scores,
            "threshold": round(threshold, 5),
            "change_points": change_points,
            "method": f"profile L1 distance across a +/-{span}-step sliding split",
        },
        "grid": grid.to_dict(),
        "provenance": cube.provenance.to_dict(),
    }
