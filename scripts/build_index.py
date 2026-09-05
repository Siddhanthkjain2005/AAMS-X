#!/usr/bin/env python3
"""Characterise every window in the offline cache and write the scenario index.

    python scripts/build_index.py
    python scripts/build_index.py --regions 48 --window-steps 1200

The index is what turns the cache into a searchable scenario library: after this
runs, ``aamsx.environment.scenarios`` can answer "give me the most periodic real
window available" with a SQL query instead of a hand-written constant.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aamsx.datasets.windows import (
    DEFAULT_TIME_BINS,
    DEFAULT_WINDOW_STEPS,
    build_index,
    index_path,
    query,
)
from aamsx.logging import configure_logging


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regions", type=int, default=48)
    parser.add_argument(
        "--window-steps",
        type=int,
        nargs="+",
        default=list(DEFAULT_WINDOW_STEPS),
        help="window lengths to profile, in environment steps",
    )
    parser.add_argument(
        "--time-bins",
        type=int,
        nargs="+",
        default=list(DEFAULT_TIME_BINS),
        help="native samples per environment step",
    )
    args = parser.parse_args()
    configure_logging()

    started = time.perf_counter()
    rows = build_index(
        n_regions=args.regions,
        window_steps=tuple(args.window_steps),
        time_bins=tuple(args.time_bins),
        progress=True,
    )
    elapsed = time.perf_counter() - started
    print(f"\nindexed {rows} windows in {elapsed:.1f}s -> {index_path()}")

    summary = query(
        """
        SELECT archetype, count(*) AS windows, round(avg(occupancy), 4) AS occupancy,
               round(avg(persistence), 3) AS persistence,
               round(max(period_strength), 3) AS best_period
        FROM windows GROUP BY archetype ORDER BY windows DESC
        """
    )
    print("\narchetypes discovered in the cache")
    print(f"  {'archetype':<20}{'windows':>9}{'occupancy':>11}{'persist':>9}{'max T str':>11}")
    for row in summary:
        print(
            f"  {row['archetype']:<20}{row['windows']:>9}{row['occupancy']:>11}"
            f"{row['persistence']:>9}{row['best_period']:>11}"
        )

    periodic = query(
        """
        SELECT station, time_bin, start_step, period_steps, round(period_strength, 3) AS strength,
               round(occupancy, 3) AS occupancy
        FROM windows WHERE period_steps > 0 ORDER BY period_strength DESC LIMIT 8
        """
    )
    print("\nstrongest measured periodicity")
    for row in periodic:
        print(
            f"  {row['station']:<22} bin={row['time_bin']:>3}  T={row['period_steps']:>4} steps  "
            f"strength={row['strength']:<6} occ={row['occupancy']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
