"""Run real local episodes and persist genuine frames for the deck's figures.

Nothing here invents a decision: the factor decomposition, belief array, memory
readout and notes are exactly what the live product streams to the browser.
"""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = Path(__file__).resolve().parent / "assets"

from aamsx.cli import _spec
from aamsx.experiments.runner import run_episode


def capture(scenario: str, scheduler: str, seed: int = 0):
    frames: list[dict] = []
    spec = _spec(scenario)
    result = run_episode(spec, scheduler, seed=seed, frame_sink=frames.append, frame_stride=1)
    print(f"{scenario}/{scheduler}: {len(frames)} frames, reward={result.metrics['cumulative_reward']:.2f}")
    keep = ["step", "band_truth", "belief", "uncertainty", "staleness", "true_occupied", "detected",
            "regions", "action_value", "factors", "notes", "reward", "reward_terms",
            "cumulative_reward", "change", "memory", "periodicity", "exploration_rate",
            "budget_remaining", "confidence", "measured_db", "true_margin_db", "per_region_value"]
    slim = [{k: f[k] for k in keep if k in f} for f in frames]
    belief = np.array([f["belief"] for f in frames], dtype=np.float32)
    unc = np.array([f["uncertainty"] for f in frames], dtype=np.float32)
    stale = np.array([f["staleness"] for f in frames], dtype=np.float32)
    n_reg = belief.shape[1]
    # `true_occupied` in a frame covers only the observed window, by design: the
    # scheduler is never handed the whole truth array. Record it sparsely.
    looked = np.zeros((len(frames), n_reg), dtype=np.int8)
    hit = np.zeros((len(frames), n_reg), dtype=np.int8)
    for i, f in enumerate(frames):
        for j, r in enumerate(f["regions"]):
            looked[i, r] = 1
            if j < len(f["true_occupied"]) and f["true_occupied"][j]:
                hit[i, r] = 1
    band_truth = np.array([f.get("band_truth", 0) for f in frames], dtype=np.int16)
    tag = f"{scenario}__{scheduler}__s{seed}"
    np.savez_compressed(OUT / f"ep_{tag}.npz", belief=belief, staleness=stale,
                        uncertainty=unc, looked=looked, hit=hit, band_truth=band_truth,
                        reward=np.array([f["cumulative_reward"] for f in frames], dtype=np.float32))
    (OUT / f"ep_{tag}.json").write_text(json.dumps({
        "scenario": scenario, "scheduler": scheduler, "seed": seed,
        "metrics": {k: (float(v) if isinstance(v, (int, float)) else v)
                    for k, v in result.metrics.items() if not isinstance(v, (list, dict))},
        "n_regions": int(spec.n_regions), "horizon": int(spec.horizon),
        "frames": slim[::20], "sample_frames": [slim[i] for i in (60, 240, 600, 900) if i < len(slim)],
    }, indent=1))
    return result


if __name__ == "__main__":
    capture("high-noise", "mag-nts", 0)
    capture("recurring-environment", "mag-nts", 0)
    capture("high-noise", "round-robin", 0)
