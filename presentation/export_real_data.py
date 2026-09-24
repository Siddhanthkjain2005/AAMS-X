"""Export real cached e-CALLISTO arrays to .npz so the figure builder (system python,
no pyarrow) can draw genuine measured spectrum rather than anything invented."""
from __future__ import annotations
import json, sys
from pathlib import Path
import numpy as np
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "assets"
OUT.mkdir(exist_ok=True)

def load(station: str, start: int, n_steps: int, time_bin: int = 4, window: int = 4):
    day = sorted(p.name for p in (ROOT / "data/cached" / station).iterdir() if p.is_dir())[0]
    base = ROOT / "data/cached" / station / day
    man = json.loads((base / "manifest.json").read_text())
    dpd = float(man["db_per_digit"])
    block = int(man["calibration"]["block_size"])

    raw = n_steps * time_bin
    tbl = pq.read_table(base / "power.parquet").slice(start, raw)
    digits = np.stack(tbl.column("digits").to_numpy(zero_copy_only=False)).astype(np.float32)
    power = digits * np.float32(dpd)

    bl = pq.read_table(base / "baseline.parquet")
    baseline_blocks = np.stack(bl.column("baseline_db").to_numpy(zero_copy_only=False)).astype(np.float32)
    idx = np.arange(start, start + power.shape[0], dtype=np.float64)
    nb = baseline_blocks.shape[0]
    if nb == 1:
        baseline = np.broadcast_to(baseline_blocks[0], power.shape).copy()
    else:
        pos = np.clip((idx - 0.5 * block) / block, 0.0, nb - 1)
        lo = np.floor(pos).astype(np.intp); hi = np.minimum(lo + 1, nb - 1)
        w = (pos - lo).astype(np.float32)[:, None]
        baseline = baseline_blocks[lo] * (1 - w) + baseline_blocks[hi] * w
    excess = (power - baseline).astype(np.float32)

    ch = pq.read_table(base / "channels.parquet")
    freq = np.asarray(ch.column("freq_mhz").to_numpy(zero_copy_only=False), dtype=np.float32)
    thr = np.asarray(ch.column("threshold_db").to_numpy(zero_copy_only=False), dtype=np.float32)
    dead = np.asarray(ch.column("dead").to_numpy(zero_copy_only=False), dtype=bool)

    # time binning: mean over time_bin consecutive raw samples (matches the env's coarsening)
    T = excess.shape[0] // time_bin
    binned = excess[: T * time_bin].reshape(T, time_bin, -1).mean(axis=1)
    # region aggregation: max margin over `window` adjacent channels
    live = ~dead
    C = binned.shape[1] // window * window
    regions = binned[:, :C].reshape(T, -1, window).max(axis=2)
    rthr = thr[:C].reshape(-1, window).min(axis=1)
    rfreq = freq[:C].reshape(-1, window).mean(axis=1)
    occupied = regions > rthr[None, :]
    return dict(
        station=station, excess=binned, freq=freq, threshold=thr, dead=dead,
        regions=regions, region_threshold=rthr, region_freq=rfreq, occupied=occupied,
        freq_min=float(man["freq_min_mhz"]), freq_max=float(man["freq_max_mhz"]),
        cadence=float(man["cadence_sec"]), time_bin=time_bin, occupancy=float(man["occupancy"]),
        live_channels=int(man["live_channels"]), n_source_files=int(man["provenance"]["n_source_files"]),
        source_url=man["provenance"]["source_url"], retrieved_at=man["provenance"]["retrieved_at"],
        checksum=man["provenance"]["checksum"], notes=man["provenance"]["notes"],
    )

if __name__ == "__main__":
    for station, start in [("INDIA-GAURI", 20000), ("EGYPT-Alexandria", 30000), ("SWISS-Landschlacht", 30000), ("MRO", 40000)]:
        d = load(station, start, 1200)
        meta = {k: v for k, v in d.items() if not isinstance(v, np.ndarray)}
        np.savez_compressed(OUT / f"{station}.npz", **{k: v for k, v in d.items() if isinstance(v, np.ndarray)})
        (OUT / f"{station}.json").write_text(json.dumps(meta, indent=2))
        occ = float(d["occupied"].mean())
        print(f"{station:22s} excess{d['excess'].shape} regions{d['regions'].shape} region-occupancy={occ:.4f}")
