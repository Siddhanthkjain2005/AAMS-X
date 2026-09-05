#!/usr/bin/env python3
"""Sweep the reward weights and report how the ranking moves.

    python scripts/sensitivity.py                                  # sweep delay
    python scripts/sensitivity.py --weight information --seeds 4
    python scripts/sensitivity.py --weight delay --values 0.1,0.3,0.5,0.8 --json out.json

The headline table in ``docs/EXPERIMENTS.md`` ranks policies by one scalar reward,
and that scalar is a *choice*.  This script measures how much of the result is the
choice rather than the policy: it re-runs the protocol with one weight varied and
reports the ranking at each value, plus the detection metrics that do not depend on
the weighting at all.

Every episode is genuinely re-executed at each weight, because the reward is fed
back to the scheduler — re-scoring stored trajectories with new weights would
describe policies that never existed.  That is why this is a script you run
deliberately rather than part of the default benchmark.

Read the output as a caveat, not as a tuning knob: picking the weight that makes
MAG-NTS win would be exactly the mistake this script exists to expose.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aamsx.config import get_settings
from aamsx.contracts.scenario import ScenarioSpec
from aamsx.environment.scenarios import preset
from aamsx.experiments.batch import BatchJob, default_workers, run_batch
from aamsx.logging import configure_logging
from aamsx.schedulers.base import AblationFlags

DEFAULT_SCENARIOS = ("easy-static", "sudden-shift")
DEFAULT_SCHEDULERS = ("round-robin", "thompson", "nts", "mag-nts")
DEFAULT_VALUES = {
    "detection": (0.5, 1.0, 1.5),
    "information": (0.0, 0.35, 0.7, 1.2),
    "delay": (0.0, 0.1, 0.3, 0.5, 0.8, 1.2),
    "false_alarm": (0.0, 0.25, 0.5, 1.0),
    "switching": (0.0, 0.05, 0.2, 0.5),
}
#: Reported alongside reward because they are *not* functions of the weighting:
#: if the winner changes while these stay flat, the weighting is doing the work.
INVARIANTS = (
    ("sustained_detection_probability", "P(sust)", 4),
    ("sustained_detection_delay", "delay", 2),
    ("false_alarm_rate", "FA", 4),
    ("detections_per_cost", "det/cost", 3),
    ("band_coverage", "coverage", 3),
)


def reweight(spec: ScenarioSpec, weight: str, value: float) -> ScenarioSpec:
    """Copy a scenario with one reward weight changed and nothing else touched."""
    reward = dataclasses.replace(spec.reward, **{weight: float(value)})
    return dataclasses.replace(spec, reward=reward)


def rank(aggregates: dict[str, dict[str, dict[str, object]]]) -> list[tuple[str, float]]:
    """Order variants by mean cumulative reward, best first."""
    scored = [
        (variant, float(metrics["cumulative_reward"]["mean"]))
        for variant, metrics in aggregates.items()
        if "cumulative_reward" in metrics
    ]
    return sorted(scored, key=lambda row: -row[1])


def sweep_scenario(
    scenario_id: str,
    weight: str,
    values: tuple[float, ...],
    *,
    schedulers: tuple[str, ...],
    seeds: int,
    workers: int,
) -> dict[str, object]:
    """Re-run every policy at every weight value on one scenario."""
    base = preset(scenario_id)
    baseline_value = getattr(base.reward, weight)
    rule = "=" * 96
    print(
        f"\n{rule}\n{scenario_id}   sweeping reward.{weight}   "
        f"(protocol value {baseline_value})\n{rule}"
    )

    header = f"{weight:>9s}  " + "".join(f"{name:>14s}" for name in schedulers)
    header += "   winner            " + "".join(f"{label:>10s}" for _, label, _ in INVARIANTS)
    print(header)

    rows: list[dict[str, object]] = []
    for value in values:
        spec = reweight(base, weight, value)
        jobs = [
            BatchJob(spec=spec, scheduler=name, seed=seed, flags=AblationFlags())
            for name in schedulers
            for seed in range(seeds)
        ]
        result = run_batch(jobs, workers=workers, baseline=schedulers[0])
        ordered = rank(result.aggregates)
        winner = ordered[0][0] if ordered else "-"
        best = result.aggregates.get(winner, {})

        line = f"{value:9.3f}  "
        means = {variant: score for variant, score in ordered}
        for name in schedulers:
            line += f"{means.get(name, float('nan')):14.2f}"
        marker = " *" if winner != schedulers[-1] else "  "
        line += f"   {winner:<16s}{marker}"
        for key, _, digits in INVARIANTS:
            entry = best.get(key, {})
            mean = float(entry.get("mean", float("nan"))) if entry else float("nan")
            line += f"{mean:10.{digits}f}"
        print(line, flush=True)

        rows.append(
            {
                "value": value,
                "winner": winner,
                "ranking": ordered,
                "aggregates": {
                    variant: {
                        key: result.aggregates[variant][key]
                        for key in ("cumulative_reward", *[k for k, _, _ in INVARIANTS])
                        if key in result.aggregates[variant]
                    }
                    for variant in result.aggregates
                },
            }
        )
    return {
        "scenario_id": scenario_id,
        "weight": weight,
        "protocol_value": baseline_value,
        "schedulers": list(schedulers),
        "seeds": seeds,
        "rows": rows,
    }


def summarise(sweeps: list[dict[str, object]], weight: str) -> None:
    """State plainly whether the ranking survived the sweep."""
    print(f"\n{'=' * 96}\nwhat the sweep shows\n{'=' * 96}")
    for sweep in sweeps:
        winners = {row["value"]: row["winner"] for row in sweep["rows"]}  # type: ignore[index]
        distinct = sorted(set(winners.values()))
        flips = [f"{value:g}->{name}" for value, name in winners.items()]
        verdict = (
            f"one winner across the whole sweep ({distinct[0]})"
            if len(distinct) == 1
            else f"the winner changes with reward.{weight}: {', '.join(flips)}"
        )
        print(f"  {sweep['scenario_id']:24s} {verdict}")
    print(
        "\nA ranking that flips inside the plausible range of a weight is a property of "
        "the objective, not of the policies.\naamsx/evaluation/pareto.py reports the "
        "frontier instead, which needs no weighting at all."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--weight", default="delay", choices=sorted(DEFAULT_VALUES))
    parser.add_argument("--values", default=None, help="comma-separated override, e.g. 0.1,0.5,1.0")
    parser.add_argument("--scenario", action="append", default=None, help="repeatable preset id")
    parser.add_argument("--schedulers", default=",".join(DEFAULT_SCHEDULERS))
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--json", type=Path, default=None, help="write the measured sweep here")
    args = parser.parse_args()
    configure_logging()

    values = (
        tuple(float(token) for token in args.values.split(","))
        if args.values
        else DEFAULT_VALUES[args.weight]
    )
    scenarios = tuple(args.scenario or DEFAULT_SCENARIOS)
    schedulers = tuple(name.strip() for name in args.schedulers.split(",") if name.strip())
    workers = args.workers or default_workers()

    started = time.perf_counter()
    total = len(scenarios) * len(values) * len(schedulers) * args.seeds
    print(
        f"reward-weight sensitivity: {total} episodes "
        f"({len(scenarios)} scenarios x {len(values)} values x {len(schedulers)} policies "
        f"x {args.seeds} seeds) on {workers} workers"
    )

    sweeps = [
        sweep_scenario(
            scenario_id,
            args.weight,
            values,
            schedulers=schedulers,
            seeds=args.seeds,
            workers=workers,
        )
        for scenario_id in scenarios
    ]
    summarise(sweeps, args.weight)
    elapsed = time.perf_counter() - started
    print(f"\n{total} episodes in {elapsed:.1f}s")

    payload = {
        "kind": "measured",
        "weight": args.weight,
        "values": list(values),
        "seeds": args.seeds,
        "sweeps": sweeps,
        "elapsed_sec": round(elapsed, 2),
    }
    destination = args.json or (get_settings().reports_dir / f"sensitivity_{args.weight}.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, default=str))
    print(f"wrote {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
