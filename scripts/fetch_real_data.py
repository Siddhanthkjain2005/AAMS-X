#!/usr/bin/env python3
"""Populate the offline cache with real e-CALLISTO recordings.

    python scripts/fetch_real_data.py                    # whole catalogue, 12 h each
    python scripts/fetch_real_data.py --hours 4          # quicker
    python scripts/fetch_real_data.py --station MRO/60    # one recording
    python scripts/fetch_real_data.py --date 2026-08-25  # pin an archive day

Recordings already present are skipped unless ``--force`` is passed, so the
script is safe to re-run after a dropped connection.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aamsx.config import get_settings
from aamsx.datasets.callisto import AdapterUnavailable, fetch_raw
from aamsx.datasets.stations import STATIONS, get_station
from aamsx.datasets.store import recording_dir, write_recording
from aamsx.logging import configure_logging, get_logger

log = get_logger("fetch")

DEFAULT_DATE = "2026-08-25"
DEFAULT_START_HOUR = 6


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=DEFAULT_DATE, help="archive day, YYYY-MM-DD (UTC)")
    parser.add_argument("--start-hour", type=int, default=DEFAULT_START_HOUR)
    parser.add_argument("--hours", type=float, default=12.0)
    parser.add_argument("--station", action="append", help="NAME/FOCUS; repeatable")
    parser.add_argument("--force", action="store_true", help="re-fetch cached recordings")
    args = parser.parse_args()

    configure_logging()
    settings = get_settings()
    day = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=UTC)
    start = day + timedelta(hours=args.start_hour)
    end = start + timedelta(hours=args.hours)

    targets = [get_station(key) for key in args.station] if args.station else list(STATIONS)
    print(
        f"AAMS-X ingestion  {len(targets)} recording(s)  "
        f"{start:%Y-%m-%d %H:%M} -> {end:%H:%M} UTC\n"
    )

    ok, failed = 0, 0
    for index, station in enumerate(targets, start=1):
        label = f"[{index}/{len(targets)}] {station.key:<26}"
        target = recording_dir(settings, station.name, f"{start:%Y%m%d}")
        if (target / "manifest.json").exists() and not args.force:
            print(f"{label} cached, skipping")
            ok += 1
            continue
        try:
            raw = fetch_raw(station, start, end, settings=settings)
            path = write_recording(raw, station.name, settings=settings)
            size_mb = sum(f.stat().st_size for f in path.iterdir()) / 1e6
            cube = raw.to_cube(
                db_per_digit=settings.db_per_digit,
                occupancy_threshold_db=settings.occupancy_threshold_db,
                baseline_percentile=settings.baseline_percentile,
                k_mad=settings.occupancy_k_mad,
            )
            summary = cube.summary()
            print(
                f"{label} {raw.n_times:6d} steps x {raw.n_channels:3d} ch  "
                f"occ={summary['occupancy']:.4f} live={summary['live_channels']:3d}  "
                f"{size_mb:6.1f} MB  gaps={len(raw.provenance.gaps)}"
            )
            ok += 1
        except (AdapterUnavailable, ValueError, OSError) as exc:
            failed += 1
            print(f"{label} FAILED: {exc}")
            log.warning("fetch.failed", extra={"station": station.key, "error": str(exc)})
        except Exception:  # pragma: no cover - unexpected, keep going
            failed += 1
            print(f"{label} UNEXPECTED ERROR")
            traceback.print_exc(limit=3)

    total_mb = sum(f.stat().st_size for f in settings.cache_dir.rglob("*") if f.is_file()) / 1e6
    print(f"\ndone: {ok} cached, {failed} failed, cache size {total_mb:.1f} MB")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
