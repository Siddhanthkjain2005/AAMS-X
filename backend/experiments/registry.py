"""Local SQLite experiment index plus compressed, checksummed immutable traces."""

import csv
import gzip
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

from .engine import canonical_json

ROOT = Path(__file__).resolve().parents[2]
RUN_ID = re.compile(r"AX-[A-F0-9]{12}")


class Registry:
    def __init__(self, directory: Path | None = None):
        self.directory = directory or ROOT / "data" / "experiments"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.database = self.directory / "registry.sqlite3"
        with sqlite3.connect(self.database) as db:
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created_at TEXT, summary TEXT, checksum TEXT)")

    def _path(self, run_id: str):
        if not RUN_ID.fullmatch(run_id):
            raise ValueError("Invalid experiment ID")
        return self.directory / f"{run_id}.json.gz"

    def save(self, record: dict):
        path = self._path(record["id"])
        encoded = gzip.compress(canonical_json(record).encode(), mtime=0)
        checksum = hashlib.sha256(encoded).hexdigest()
        temp = path.with_suffix(".tmp")
        temp.write_bytes(encoded)
        temp.replace(path)
        summary = {k: v for k, v in record.items() if k not in {"frames", "evaluation_tracks"}}
        with sqlite3.connect(self.database) as db:
            db.execute("INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?)", (record["id"], record["created_at"], canonical_json(summary), checksum))

    def load(self, run_id: str) -> dict:
        path = self._path(run_id)
        with sqlite3.connect(self.database) as db:
            row = db.execute("SELECT checksum FROM runs WHERE id = ?", (run_id,)).fetchone()
        if row is None or not path.exists():
            raise KeyError("Experiment not found")
        encoded = path.read_bytes()
        if hashlib.sha256(encoded).hexdigest() != row[0]:
            raise ValueError("Experiment artifact checksum mismatch")
        record = json.loads(gzip.decompress(encoded))
        if hashlib.sha256(canonical_json(record["frames"]).encode()).hexdigest() != record["trace_hash"]:
            raise ValueError("Experiment trace checksum mismatch")
        return record

    def list(self, limit: int = 60) -> list[dict]:
        with sqlite3.connect(self.database) as db:
            rows = db.execute("SELECT summary FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def import_record(self, record: dict):
        if hashlib.sha256(canonical_json(record["frames"]).encode()).hexdigest() != record["trace_hash"]:
            raise ValueError("Replay trace checksum mismatch")
        self.save(record)


def export_csv(record: dict) -> str:
    output = io.StringIO()
    first_metrics = next(iter(record["metrics"].values()))
    fields = ["experiment_id", "seed", "scenario", "source_category", "environment_hash", "step", "algorithm", "window_start", "window_width", *first_metrics.keys()]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for frame in record["frames"]:
        for name, policy in frame["policies"].items():
            writer.writerow({"experiment_id": record["id"], "seed": record["config"]["seed"], "scenario": record["config"]["scenario"], "source_category": record["dataset"]["category"], "environment_hash": record["environment_hash"], "step": frame["step"], "algorithm": name, "window_start": policy["selected_window"]["start"], "window_width": policy["selected_window"]["width"], **policy["metrics"]})
    return output.getvalue()
