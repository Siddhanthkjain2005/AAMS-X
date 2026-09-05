#!/usr/bin/env python3
"""Tune MAG-NTS action-value weights — on the training split only.

    python scripts/tune_mag_nts.py --trials 48 --seeds 3

The protocol is deliberately narrow so the generalisation claim survives:

* candidate weights are scored **only** on scenarios whose segments come from
  ``train`` stations,
* the objective is the platform's own declared utility (cumulative reward under
  the default reward weights) — the reward function is never tuned to flatter the
  policy,
* the winner is then reported on validation and unseen scenarios by
  ``scripts/run_benchmark.py``, which this script never touches.

Results are written to ``data/index/mag_nts_tuning.json`` so the chosen weights
are auditable rather than folklore.
"""

from __future__ import annotations

import argparse
import concurrent.futures as futures
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from aamsx.config import get_settings
from aamsx.environment.scenarios import sample_scenario
from aamsx.experiments.runner import run_episode
from aamsx.logging import configure_logging
from aamsx.schedulers.mag_nts import MagWeights

TRAIN_FAMILIES = ("persistent", "bursting", "intermittent", "distribution-shift")
BASELINE = "nts"


def _score(args: tuple[dict, str, int]) -> tuple[float, float]:
    weights, family, seed = args
    spec = sample_scenario(family, seed=seed, roles=("train",))
    mag = run_episode(
        spec, "mag-nts", seed=seed, scheduler_kwargs={"weights": MagWeights(**weights)}
    )
    base = run_episode(spec, BASELINE, seed=seed)
    return (
        float(mag.metrics["cumulative_reward"]),
        float(base.metrics["cumulative_reward"]),
    )


def sample_weights(rng: np.random.Generator) -> dict[str, float]:
    return {
        "detection": float(rng.uniform(0.8, 1.6)),
        "information": float(rng.uniform(0.02, 0.35)),
        "memory": float(rng.uniform(0.1, 0.8)),
        "periodicity": float(rng.uniform(0.02, 0.35)),
        "uncertainty": float(rng.uniform(0.0, 0.25)),
        "recency": float(rng.uniform(0.0, 0.2)),
        "cost": float(rng.uniform(0.05, 0.35)),
        "switching": float(rng.uniform(0.0, 0.2)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=48)
    parser.add_argument("--seeds", type=int, default=3)
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()
    configure_logging("ERROR")
    settings = get_settings()

    rng = np.random.default_rng(20260827)
    candidates = [asdict(MagWeights())] + [sample_weights(rng) for _ in range(args.trials)]
    jobs = [
        (weights, family, seed)
        for weights in candidates
        for family in TRAIN_FAMILIES
        for seed in range(args.seeds)
    ]
    workers = args.workers or max(1, (settings.batch_workers or 0) or 6)
    print(
        f"tuning MAG-NTS: {len(candidates)} candidates x {len(TRAIN_FAMILIES)} train families "
        f"x {args.seeds} seeds = {len(jobs)} episode pairs on {workers} workers"
    )

    started = time.perf_counter()
    per_candidate: list[list[tuple[float, float]]] = [[] for _ in candidates]
    chunk = len(TRAIN_FAMILIES) * args.seeds
    with futures.ProcessPoolExecutor(max_workers=workers) as pool:
        for index, outcome in enumerate(pool.map(_score, jobs, chunksize=2)):
            per_candidate[index // chunk].append(outcome)

    rows = []
    for weights, results in zip(candidates, per_candidate, strict=True):
        mag = np.array([r[0] for r in results])
        base = np.array([r[1] for r in results])
        rows.append(
            {
                "weights": weights,
                "mag_reward": float(mag.mean()),
                "baseline_reward": float(base.mean()),
                "advantage": float((mag - base).mean()),
                "win_rate": float((mag > base).mean()),
            }
        )
    # Selection rule, fixed in advance: highest win rate against the baseline,
    # ties broken by mean advantage. Robustness first — a candidate that wins by a
    # lot on one family and loses on another is worse than one that always wins.
    rows.sort(key=lambda row: (row["win_rate"], row["advantage"]), reverse=True)

    print(f"\ndone in {time.perf_counter() - started:.1f}s. Top 8 by win rate over {BASELINE}:")
    print(f"  {'adv':>8}{'win':>6}{'mag':>9}{'base':>9}   weights")
    for row in rows[:8]:
        pretty = " ".join(f"{k[:3]}={v:.2f}" for k, v in row["weights"].items())
        print(
            f"  {row['advantage']:>8.1f}{row['win_rate']:>6.2f}{row['mag_reward']:>9.1f}"
            f"{row['baseline_reward']:>9.1f}   {pretty}"
        )

    target = settings.index_dir / "mag_nts_tuning.json"
    target.write_text(
        json.dumps(
            {
                "protocol": {
                    "families": list(TRAIN_FAMILIES),
                    "roles": ["train"],
                    "seeds": args.seeds,
                    "objective": "cumulative reward vs " + BASELINE,
                    "selection_rule": "max win_rate, ties broken by mean advantage",
                    "baseline": BASELINE,
                },
                "best": rows[0],
                "all": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {target}")
    print("\nbest weights:")
    print("  MagWeights(" + ", ".join(f"{k}={v:.3f}" for k, v in rows[0]["weights"].items()) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
