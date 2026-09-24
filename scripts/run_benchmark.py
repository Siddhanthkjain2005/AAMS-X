#!/usr/bin/env python3
"""Run the AAMS-X evaluation protocol and print the headline table.

    python scripts/run_benchmark.py                       # every preset, 5 seeds
    python scripts/run_benchmark.py --seeds 8 --scenario sudden-shift
    python scripts/run_benchmark.py --ablation             # ablation ladder instead
    python scripts/run_benchmark.py --baseline thompson    # change the control arm

Every number printed here comes from executed episodes. Nothing is cached from a
previous run and nothing is illustrative.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aamsx.config import get_settings
from aamsx.environment.scenarios import PRESET_ORDER, preset
from aamsx.experiments.batch import (
    ABLATION_LADDER,
    ablation_jobs,
    arena_jobs,
    default_workers,
    run_recorded_batch,
)
from aamsx.logging import configure_logging
from aamsx.schedulers import ARENA_ORDER

BASELINE = "nts"
ABLATION_BASELINE = "NTS"
TABLE_METRICS = (
    ("cumulative_reward", "reward", 1),
    ("cumulative_regret", "regret", 0),
    ("sustained_detection_probability", "P(sust)", 3),
    ("sustained_detection_delay", "delay", 2),
    ("false_alarm_rate", "FA", 3),
    ("detections_per_cost", "det/cost", 3),
    ("information_per_observation", "bits/obs", 3),
    ("oracle_ratio", "vs oracle", 3),
)


def _print_table_from(payload: dict, baseline: str) -> None:
    """Print the aggregate table from a stored batch payload.

    ``±`` is the half-width of the Student-t 95% confidence interval on the mean,
    not the standard deviation; the stored JSON carries both.
    """
    header = f"  {'variant':<22}"
    for _, label, _digits in TABLE_METRICS:
        header += f"{label:>18}"
    print(header)
    aggregates = payload["aggregates"]
    for variant in payload["variants"]:
        row = f"  {variant:<22}"
        for metric, _label, digits in TABLE_METRICS:
            entry = aggregates[variant][metric]
            mean, low, high = entry["mean"], entry["ci_low"], entry["ci_high"]
            if mean != mean:  # NaN
                row += f"{'n/a':>18}"
            else:
                half = (high - low) / 2 if high == high else 0.0
                row += f"{mean:>11.{digits}f}±{half:<6.{digits}f}"
        print(row)
    pareto = payload.get("pareto", {})
    if pareto.get("vacuous"):
        print(f"\n  Pareto frontier not computed: missing {', '.join(pareto['axes_missing'])}")
    elif pareto.get("frontier"):
        print(f"\n  Pareto frontier: {', '.join(pareto['frontier'])}")
    if not payload["comparisons"]:
        return
    print(f"\n  significance vs {baseline} (Welch t-test, 95%):")
    for row in payload["comparisons"]:
        if row["metric"] != "cumulative_reward":
            continue
        mark = "significant" if row["significant"] else "not significant"
        print(
            f"    {row['treatment']:<22} Δreward {row['difference']:+9.2f} "
            f"({row['relative']:+.1%})  p={row['welch_p']:.4f}  d={row['cohens_d']:+.2f}  {mark}"
        )


def _default_name(ablation: bool, baseline: str) -> str:
    """Output filename, suffixed by the control arm unless it is the default one.

    A run with a non-default control answers a different question from the shipped
    table, so it must not land on top of it: ``--baseline thompson`` writes
    ``benchmark_thompson.json`` and leaves ``benchmark.json`` alone.
    """
    stem = "ablation" if ablation else "benchmark"
    default = ABLATION_BASELINE if ablation else BASELINE
    if baseline == default:
        return f"{stem}.json"
    slug = re.sub(r"[^a-z0-9]+", "-", baseline.lower()).strip("-")
    return f"{stem}_{slug}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("--scenario", action="append", help="preset id; repeatable")
    parser.add_argument("--ablation", action="store_true", help="run the ablation ladder")
    parser.add_argument(
        "--baseline",
        default=None,
        help=(
            "control arm for the significance tests "
            f"(default {BASELINE!r}, or {ABLATION_BASELINE!r} with --ablation)"
        ),
    )
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--out", type=Path, default=None, help="write the full JSON here")
    args = parser.parse_args()
    configure_logging("ERROR")

    # Variant keys do not depend on the scenario, so an unknown control is caught
    # before any episode runs rather than silently producing zero comparisons.
    baseline = args.baseline or (ABLATION_BASELINE if args.ablation else BASELINE)
    known = {label for label, _flags in ABLATION_LADDER} if args.ablation else set(ARENA_ORDER)
    if baseline not in known:
        parser.error(f"unknown --baseline {baseline!r}; available: {', '.join(sorted(known))}")

    scenario_ids = args.scenario or list(PRESET_ORDER)
    seeds = list(range(args.seeds))
    workers = args.workers or default_workers()
    payload: dict[str, object] = {
        "seeds": seeds,
        "mode": "ablation" if args.ablation else "arena",
        "baseline": baseline,
    }

    started = time.perf_counter()
    for scenario_id in scenario_ids:
        try:
            spec = preset(scenario_id)
        except (LookupError, FileNotFoundError) as exc:
            print(f"\n{scenario_id}: unavailable — {exc}")
            continue
        jobs = ablation_jobs(spec, seeds) if args.ablation else arena_jobs(spec, ARENA_ORDER, seeds)
        print(f"\n{'=' * 118}\n{spec.name}  ({scenario_id})")
        print(f"  {spec.description}")
        stations = sorted({s.recording_id for s in spec.segments})
        print(
            f"  horizon={spec.horizon} regions={spec.n_regions} window={spec.receiver.window_size} "
            f"noise={spec.receiver.noise_db}dB budget={spec.effective_budget():.0f} "
            f"split={spec.split} | {', '.join(stations)}"
        )
        print(f"  {len(jobs)} episodes on {workers} workers\n")
        # Recorded, not just printed: the registry row is what makes this run
        # replayable and what `aamsx report` renders afterwards.
        experiment_id, scenario_payload = run_recorded_batch(
            jobs,
            kind="ablation" if args.ablation else "arena",
            baseline=baseline,
            workers=workers,
            source="run_benchmark.py",
        )
        _print_table_from(scenario_payload, baseline)
        print(f"  recorded as {experiment_id}")
        payload[scenario_id] = {**scenario_payload, "experiment_id": experiment_id}

    elapsed = time.perf_counter() - started
    print(f"\n{'=' * 118}\ncompleted in {elapsed:.1f}s")

    target = args.out or (get_settings().reports_dir / _default_name(args.ablation, baseline))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"full results -> {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
