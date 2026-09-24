import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PROCESSED = ROOT / "data" / "processed"
TSRD_URL = "https://huggingface.co/datasets/alan-turing-institute/turing-synthetic-radar-dataset"
CALLISTO_URL = "https://www.e-callisto.org/"
MEASURED_NOTICE = "Real measured RF replay — e-CALLISTO public spectrum observations. Used for ingestion and robustness demonstration, not labelled EW emitter ground truth."
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,79}")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def safe_path(dataset_id: str, suffix: str, directory: Path = PROCESSED) -> Path:
    if not IDENTIFIER.fullmatch(dataset_id):
        raise ValueError("Invalid dataset ID")
    return directory / f"{dataset_id}{suffix}"


def write_artifact(intensity, time_ms, frequency_mhz, manifest: dict, truth=None, samples: pd.DataFrame | None = None, directory: Path = PROCESSED):
    intensity = np.asarray(intensity, dtype=np.float32)
    time_ms = np.asarray(time_ms, dtype=np.float64)
    frequency_mhz = np.asarray(frequency_mhz, dtype=np.float64)
    if intensity.shape != (len(time_ms), len(frequency_mhz)) or intensity.size > 4_000_000:
        raise ValueError("Artifact shape invalid or exceeds the 4 million cell ingestion limit")
    if min(len(time_ms), len(frequency_mhz)) < 2 or not np.isfinite(time_ms).all() or not np.isfinite(frequency_mhz).all():
        raise ValueError("Artifact coordinates must be finite and nontrivial")
    if np.any(np.diff(time_ms) <= 0) or np.any(np.diff(frequency_mhz) <= 0):
        raise ValueError("Artifact coordinates must be strictly increasing")
    if truth is not None and np.asarray(truth).shape != intensity.shape:
        raise ValueError("Truth dimensions do not match artifact")
    directory.mkdir(parents=True, exist_ok=True)
    dataset_id = manifest["id"]
    path = safe_path(dataset_id, ".npz", directory)
    arrays = {"intensity": intensity, "time_ms": time_ms, "frequency_mhz": frequency_mhz}
    if truth is not None:
        arrays["truth"] = np.asarray(truth, dtype=bool)
    np.savez_compressed(path, **arrays)
    result = {
        **manifest, "status": "available", "ingested_at": datetime.now(timezone.utc).isoformat(),
        "artifact": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else path.name,
        "artifact_sha256": sha256(path), "artifact_bytes": path.stat().st_size,
        "shape": list(intensity.shape), "sample_count": int(intensity.size),
        "valid_sample_count": int(np.isfinite(intensity).sum()), "missing_sample_count": int((~np.isfinite(intensity)).sum()),
        "frequency_range_mhz": [float(frequency_mhz.min()), float(frequency_mhz.max())],
        "time_range_ms": [float(time_ms.min()), float(time_ms.max())],
        "ground_truth": truth is not None, "preprocessing_version": "aams-x/0.1.0",
    }
    if samples is not None:
        parquet = safe_path(dataset_id, ".parquet", directory)
        samples.to_parquet(parquet, index=False)
        result.update({"parquet": str(parquet.relative_to(ROOT)) if parquet.is_relative_to(ROOT) else parquet.name, "parquet_sha256": sha256(parquet), "source_sample_count": len(samples), "sample_columns": list(samples.columns)})
    safe_path(dataset_id, ".json", directory).write_text(json.dumps(result, indent=2, allow_nan=False))
    return result


def read_manifest(dataset_id: str, directory: Path = PROCESSED) -> dict:
    path = safe_path(dataset_id, ".json", directory)
    if not path.exists():
        raise KeyError("Dataset artifact is not installed")
    return json.loads(path.read_text())


def load_artifact(dataset_id: str, directory: Path = PROCESSED) -> tuple[dict, dict]:
    manifest = read_manifest(dataset_id, directory)
    path = safe_path(dataset_id, ".npz", directory)
    if sha256(path) != manifest["artifact_sha256"]:
        raise ValueError("Dataset artifact checksum mismatch")
    with np.load(path, allow_pickle=False) as artifact:
        arrays = {key: artifact[key] for key in artifact.files}
    return arrays, manifest


def catalog(directory: Path = PROCESSED) -> list[dict]:
    installed = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                item = read_manifest(path.stem, directory)
                artifact = safe_path(item["id"], ".npz", directory)
                if not artifact.exists():
                    item["status"] = "missing_artifact"
                elif sha256(artifact) != item["artifact_sha256"]:
                    item["status"] = "checksum_mismatch"
                installed.append(item)
            except (ValueError, KeyError, OSError):
                continue
    result = [{"id": "simulation", "name": "AAMS-X Controlled RF Environment", "organization": "AAMS-X", "category": "CONTROLLED_SIMULATION", "status": "available", "original_format": "Seeded NumPy world", "ground_truth": True, "source_url": None, "note": "Generated per experiment; configuration, seed, energy, detector realization, and truth hash are recorded.", "lineage": ["Seed + scenario", "Activity timeline", "Receiver energy / noise", "Immutable world", "Observation-only policy", "Trace + evaluation"]}]
    if not any(d["category"] == "OFFICIAL_SYNTHETIC_RADAR" for d in installed):
        result.append({"id": "tsrd", "name": "Turing Synthetic Radar Dataset", "organization": "The Alan Turing Institute", "category": "OFFICIAL_SYNTHETIC_RADAR", "status": "access_required", "original_format": "HDF5 Pulse Descriptor Words", "ground_truth": None, "source_url": TSRD_URL, "license": "Apache-2.0 (per publisher dataset card)", "note": "Publisher requires access approval on Hugging Face. No official pulses are installed. Accept the publisher's terms, then download an authorized stare-mode HDF5 and run the importer. The simulator is never substituted under this badge.", "install_command": ".venv/bin/python -m backend.datasets.ingest turing data/raw/config_0.h5 --receiver-mode stare", "lineage": ["Authorized HDF5", "Schema / units validation", "Chunked PDW parsing", "Time × frequency occupancy", "Parquet + NPZ + SHA-256"]})
    if not any(d["category"] == "REAL_MEASURED_RF" for d in installed):
        result.append({"id": "ecallisto", "name": "e-CALLISTO Public Spectrum", "organization": "e-CALLISTO / FHNW public archive", "category": "REAL_MEASURED_RF", "status": "not_downloaded", "original_format": "FITS", "ground_truth": False, "source_url": CALLISTO_URL, "note": MEASURED_NOTICE, "install_command": ".venv/bin/python -m backend.datasets.fetch callisto", "lineage": ["Public FITS", "Station + axes", "Missing channels retained", "Parquet + NPZ + SHA-256"]})
    return result + installed


def preview(dataset_id: str, directory: Path = PROCESSED) -> dict:
    arrays, manifest = load_artifact(dataset_id, directory)
    energy = arrays["intensity"]
    ti = np.unique(np.linspace(0, energy.shape[0] - 1, min(180, energy.shape[0])).astype(int))
    fi = np.unique(np.linspace(0, energy.shape[1] - 1, min(96, energy.shape[1])).astype(int))
    sampled = energy[np.ix_(ti, fi)]
    finite = energy[np.isfinite(energy)]
    samples = []
    parquet = safe_path(dataset_id, ".parquet", directory)
    if parquet.exists():
        if sha256(parquet) != manifest["parquet_sha256"]:
            raise ValueError("Dataset sample checksum mismatch")
        import pyarrow.parquet as pq
        batch = next(pq.ParquetFile(parquet).iter_batches(batch_size=12), None)
        if batch is not None:
            samples = json.loads(batch.to_pandas().to_json(orient="records"))
    return {"metadata": manifest, "time_ms": arrays["time_ms"][ti].tolist(), "frequency_mhz": arrays["frequency_mhz"][fi].tolist(), "intensity": [[float(v) if np.isfinite(v) else None for v in row] for row in sampled], "display_range": np.percentile(finite, [3, 97]).tolist() if len(finite) else [0, 1], "samples": samples, "downsampling": "Uniform index preview only; evaluation uses aggregated source cells."}
