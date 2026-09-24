#!/usr/bin/env python3
"""Measure e-CALLISTO stations so the catalogue is chosen, not guessed.

    python scripts/survey_stations.py                       # survey the curated set
    python scripts/survey_stations.py --discover            # every station the archive lists
    python scripts/survey_stations.py --hours 1.0 --json out.json

For each *(station, focus-code)* pair this downloads a short real window and
measures, under the same labelling policy the rest of AAMS-X uses:

* the achieved frequency span and channel count,
* the occupied-cell fraction,
* the **live channel** count — channels that are neither permanently silent nor
  permanently saturated, which is what decides whether the recording poses a
  scheduling problem at all,
* the region-to-region spread of occupancy, because a band where every region
  behaves identically cannot separate one policy from another,
* the archetype the characteriser assigns.

This is the script that produced the numbers in ``aamsx/datasets/stations.py``
and the recording table in ``docs/DATA.md``.  It is read-only with respect to the
cache: it never writes a recording, so re-running it cannot change an experiment.
Every value printed is measured from a download made during the run; a station
that fails to download is reported as failed and is not estimated.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aamsx.config import get_settings
from aamsx.datasets.callisto import AdapterUnavailable, fetch_raw, list_day
from aamsx.datasets.stations import STATIONS, Station
from aamsx.environment.characterize import characterise
from aamsx.environment.grid import bin_time, build_grid, region_margin_db
from aamsx.logging import configure_logging, get_logger

log = get_logger("survey")

#: A channel that is occupied essentially never, or essentially always, carries no
#: schedulable information: its state is knowable without ever looking at it.
DEAD_LOW = 0.002
DEAD_HIGH = 0.98

DEFAULT_DAY = "2026-08-25"
DEFAULT_START_HOUR = 6
FILE_RE = re.compile(r"^(?P<station>.+)_(?P<date>\d{8})_(?P<time>\d{6})_(?P<focus>\d{2})\.fit\.gz$")
HREF_RE = re.compile(r'href="([A-Za-z0-9_.\-]+\.fit\.gz)"')


@dataclass(slots=True)
class SurveyRow:
    """One measured (station, focus) pair."""

    station: str
    focus: str
    ok: bool
    detail: str = ""
    n_channels: int = 0
    freq_min_mhz: float = 0.0
    freq_max_mhz: float = 0.0
    cadence_sec: float = 0.0
    n_steps: int = 0
    hours: float = 0.0
    occupancy: float = 0.0
    live_channels: int = 0
    live_fraction: float = 0.0
    region_occupancy_spread: float = 0.0
    burstiness: float = 0.0
    archetype: str = ""
    files_found: int = 0

    def row(self) -> str:
        if not self.ok:
            return f"{self.station:22s} {self.focus:>4s}  FAILED  {self.detail[:52]}"
        return (
            f"{self.station:22s} {self.focus:>4s}  "
            f"{self.freq_min_mhz:7.1f}-{self.freq_max_mhz:7.1f} MHz  "
            f"{self.n_channels:4d}ch  {self.live_channels:4d} live "
            f"({self.live_fraction:5.1%})  occ {self.occupancy:6.3%}  "
            f"spread {self.region_occupancy_spread:6.4f}  {self.archetype}"
        )


def discover_focus_codes(day: datetime, *, limit: int | None = None) -> list[tuple[str, str]]:
    """List every (station, focus) pair the archive published on ``day``."""
    settings = get_settings()
    if not settings.allow_network:
        raise AdapterUnavailable("network access disabled (AAMSX_ALLOW_NETWORK=0)")
    url = f"{settings.callisto_archive}/{day:%Y/%m/%d}/"
    response = httpx.get(url, timeout=settings.http_timeout_sec, follow_redirects=True)
    response.raise_for_status()
    pairs: dict[tuple[str, str], int] = {}
    for filename in dict.fromkeys(HREF_RE.findall(response.text)):
        match = FILE_RE.match(filename)
        if match is None:
            continue
        key = (match.group("station"), match.group("focus"))
        pairs[key] = pairs.get(key, 0) + 1
    # Busiest sweeps first: a pair with two files that day cannot fill a scenario.
    ordered = sorted(pairs, key=lambda key: (-pairs[key], key))
    return ordered[:limit] if limit else ordered


def _probe_station(name: str, focus: str) -> Station:
    """A catalogue entry if we have one, otherwise a bare stub to fetch with.

    ``fetch_raw`` reads the focus code off the catalogue entry, which is exactly
    right in production and useless for a discovery survey of sweeps that are not
    in the catalogue yet. Every field below that the survey measures is a
    placeholder; the printed numbers all come from the download.
    """
    for station in STATIONS:
        if station.name == name and station.focus == focus:
            return station
    return Station(
        name=name,
        focus=focus,
        label=f"{name} (focus {focus}, unsurveyed)",
        country="?",
        continent="?",
        band="?",
        freq_min_mhz=0.0,
        freq_max_mhz=0.0,
        n_channels=0,
        cadence_sec=0.25,
        role="train",
        archetype="unmeasured",
        measured_occupancy=0.0,
        live_channels=0,
        files_per_day=0,
        notes="constructed by scripts/survey_stations.py --discover",
    )


def survey_pair(
    station: str,
    focus: str,
    start: datetime,
    hours: float,
    *,
    n_regions: int,
    time_bin: int,
) -> SurveyRow:
    """Download a real window for one sweep and measure it."""
    end = start + timedelta(hours=hours)
    row = SurveyRow(station=station, focus=focus, ok=False)
    try:
        row.files_found = len(list_day(station, start.date(), focus=focus))
        raw = fetch_raw(_probe_station(station, focus), start, end)
    except (AdapterUnavailable, ValueError, KeyError) as exc:
        row.detail = f"{type(exc).__name__}: {exc}"
        return row

    cube = raw.to_cube()
    per_channel = (cube.power_db > cube.threshold_vector()).mean(axis=0)
    live = np.count_nonzero((per_channel > DEAD_LOW) & (per_channel < DEAD_HIGH))

    grid = build_grid(cube.freq_mhz, n_regions)
    margin = bin_time(region_margin_db(cube.power_db, cube.threshold_vector(), grid), time_bin)
    occupied = margin > 0.0
    stats = characterise(occupied, margin)
    per_region = occupied.mean(axis=0)

    row.ok = True
    row.n_channels = cube.n_channels
    row.freq_min_mhz = float(cube.freq_mhz.min())
    row.freq_max_mhz = float(cube.freq_mhz.max())
    row.cadence_sec = float(np.median(np.diff(raw.t_sec))) if raw.t_sec.size > 1 else 0.0
    row.n_steps = int(cube.power_db.shape[0])
    row.hours = round(row.n_steps * row.cadence_sec / 3600.0, 3)
    row.occupancy = float(occupied.mean())
    row.live_channels = int(live)
    row.live_fraction = float(live / max(cube.n_channels, 1))
    row.region_occupancy_spread = float(per_region.std())
    row.burstiness = float(stats.burstiness)
    row.archetype = str(stats.archetype)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--day", default=DEFAULT_DAY, help="UTC archive day, YYYY-MM-DD")
    parser.add_argument("--start-hour", type=int, default=DEFAULT_START_HOUR)
    parser.add_argument("--hours", type=float, default=0.5, help="window length to measure")
    parser.add_argument("--n-regions", type=int, default=48)
    parser.add_argument("--time-bin", type=int, default=4)
    parser.add_argument(
        "--discover",
        action="store_true",
        help="survey every (station, focus) pair in the archive index instead of the curated set",
    )
    parser.add_argument("--limit", type=int, default=None, help="cap on discovered pairs")
    parser.add_argument(
        "--station",
        action="append",
        default=None,
        help="restrict the survey to this station name (repeatable)",
    )
    parser.add_argument("--json", type=Path, default=None, help="write the measured rows here")
    args = parser.parse_args()
    configure_logging()

    day = datetime.fromisoformat(args.day).replace(
        hour=args.start_hour, minute=0, second=0, microsecond=0, tzinfo=UTC
    )
    if args.discover:
        pairs = discover_focus_codes(day, limit=args.limit)
        print(f"archive lists {len(pairs)} (station, focus) pairs on {day:%Y-%m-%d}")
    else:
        pairs = [(station.name, station.focus) for station in STATIONS]
    if args.station:
        wanted = set(args.station)
        pairs = [pair for pair in pairs if pair[0] in wanted]
        if not pairs:
            parser.error(f"no surveyed sweep matches {sorted(wanted)}")

    print(
        f"\nmeasuring {args.hours:.2f} h from {day.isoformat()} "
        f"at {args.n_regions} regions / time_bin {args.time_bin}\n"
    )
    rows: list[SurveyRow] = []
    for station, focus in pairs:
        row = survey_pair(
            station, focus, day, args.hours, n_regions=args.n_regions, time_bin=args.time_bin
        )
        rows.append(row)
        print(row.row(), flush=True)

    good = [row for row in rows if row.ok]
    print(f"\n{len(good)}/{len(rows)} sweeps measured")
    if good:
        ranked = sorted(good, key=lambda r: (-r.live_channels, -r.region_occupancy_spread))
        print("\nbest scheduling problems (live channels, then region spread):")
        for row in ranked[:10]:
            print(
                f"  {row.station:22s} {row.focus:>4s}  {row.live_channels:4d} live  "
                f"spread {row.region_occupancy_spread:.4f}  occ {row.occupancy:.3%}  "
                f"{row.archetype}"
            )
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps([asdict(row) for row in rows], indent=2))
        print(f"\nwrote {args.json}")
    return 0 if good else 1


if __name__ == "__main__":
    raise SystemExit(main())
