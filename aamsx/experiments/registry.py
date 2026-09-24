"""Experiment registry — reproducibility bookkeeping.

Every run is recorded in SQLite with its seed, configuration hash, scheduler
version and dataset identifiers, and its full result JSON is written alongside.
That is what makes the "Replay Experiment" button honest: replaying reads the
stored configuration and re-executes it, rather than re-displaying a cached
picture.

The configuration hash is a SHA-256 over a canonical JSON encoding of the
scenario, scheduler, seed and ablation flags, so an identical request can reuse a
previous result and a changed one cannot.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aamsx.config import Settings, get_settings
from aamsx.logging import get_logger
from aamsx.version import CODE_VERSION, SCHEDULER_VERSION

log = get_logger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS experiments (
    experiment_id   TEXT PRIMARY KEY,
    config_hash     TEXT NOT NULL,
    kind            TEXT NOT NULL,
    scenario_id     TEXT NOT NULL,
    scheduler       TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    ablation        TEXT NOT NULL,
    status          TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    finished_at     TEXT,
    code_version    TEXT NOT NULL,
    scheduler_version TEXT NOT NULL,
    recordings      TEXT NOT NULL,
    config_json     TEXT NOT NULL,
    metrics_json    TEXT,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS experiments_hash ON experiments(config_hash);
CREATE INDEX IF NOT EXISTS experiments_created ON experiments(created_at DESC);
"""


def config_hash(payload: dict[str, Any]) -> str:
    """Stable hash of an experiment request."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class ExperimentRecord:
    experiment_id: str
    config_hash: str
    kind: str
    scenario_id: str
    scheduler: str
    seed: int
    ablation: str
    status: str
    created_at: str
    finished_at: str | None
    code_version: str
    scheduler_version: str
    recordings: list[str]
    config: dict[str, Any]
    metrics: dict[str, Any] | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "config_hash": self.config_hash,
            "kind": self.kind,
            "scenario_id": self.scenario_id,
            "scheduler": self.scheduler,
            "seed": self.seed,
            "ablation": self.ablation,
            "status": self.status,
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "code_version": self.code_version,
            "scheduler_version": self.scheduler_version,
            "recordings": self.recordings,
            "config": self.config,
            "metrics": self.metrics,
            "error": self.error,
        }


class Registry:
    """Thin SQLite-backed store; one row per experiment, one JSON file per result."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.path = self.settings.registry_path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15.0)
        connection.row_factory = sqlite3.Row
        return connection

    def result_path(self, experiment_id: str) -> Path:
        return self.settings.traces_dir / f"{experiment_id}.json"

    # ---- writes --------------------------------------------------------------

    def create(
        self,
        *,
        experiment_id: str,
        kind: str,
        scenario_id: str,
        scheduler: str,
        seed: int,
        ablation: str,
        recordings: list[str],
        config: dict[str, Any],
    ) -> ExperimentRecord:
        record = ExperimentRecord(
            experiment_id=experiment_id,
            config_hash=config_hash(config),
            kind=kind,
            scenario_id=scenario_id,
            scheduler=scheduler,
            seed=seed,
            ablation=ablation,
            status="running",
            created_at=datetime.now(UTC).isoformat(),
            finished_at=None,
            code_version=CODE_VERSION,
            scheduler_version=SCHEDULER_VERSION,
            recordings=recordings,
            config=config,
            metrics=None,
            error=None,
        )
        with closing(self._connect()) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    record.experiment_id,
                    record.config_hash,
                    record.kind,
                    record.scenario_id,
                    record.scheduler,
                    record.seed,
                    record.ablation,
                    record.status,
                    record.created_at,
                    record.finished_at,
                    record.code_version,
                    record.scheduler_version,
                    json.dumps(record.recordings),
                    json.dumps(record.config, default=str),
                    None,
                    None,
                ),
            )
            connection.commit()
        return record

    def finish(
        self,
        experiment_id: str,
        *,
        status: str,
        metrics: dict[str, Any] | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if result is not None:
            self.result_path(experiment_id).write_text(
                json.dumps(result, default=str), encoding="utf-8"
            )
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE experiments SET status=?, finished_at=?, metrics_json=?, error=? "
                "WHERE experiment_id=?",
                (
                    status,
                    datetime.now(UTC).isoformat(),
                    json.dumps(metrics, default=str) if metrics else None,
                    error,
                    experiment_id,
                ),
            )
            connection.commit()

    # ---- reads ---------------------------------------------------------------

    def _row_to_record(self, row: sqlite3.Row) -> ExperimentRecord:
        return ExperimentRecord(
            experiment_id=row["experiment_id"],
            config_hash=row["config_hash"],
            kind=row["kind"],
            scenario_id=row["scenario_id"],
            scheduler=row["scheduler"],
            seed=row["seed"],
            ablation=row["ablation"],
            status=row["status"],
            created_at=row["created_at"],
            finished_at=row["finished_at"],
            code_version=row["code_version"],
            scheduler_version=row["scheduler_version"],
            recordings=json.loads(row["recordings"]),
            config=json.loads(row["config_json"]),
            metrics=json.loads(row["metrics_json"]) if row["metrics_json"] else None,
            error=row["error"],
        )

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE experiment_id=?", (experiment_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def find_by_hash(self, digest: str) -> ExperimentRecord | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM experiments WHERE config_hash=? AND status='completed' "
                "ORDER BY created_at DESC LIMIT 1",
                (digest,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def history(self, *, limit: int = 50, kind: str | None = None) -> list[ExperimentRecord]:
        sql = "SELECT * FROM experiments"
        params: tuple[object, ...] = ()
        if kind:
            sql += " WHERE kind=?"
            params = (kind,)
        sql += " ORDER BY created_at DESC LIMIT ?"
        with closing(self._connect()) as connection:
            rows = connection.execute(sql, (*params, limit)).fetchall()
        return [self._row_to_record(row) for row in rows]

    def load_result(self, experiment_id: str) -> dict[str, Any] | None:
        path = self.result_path(experiment_id)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:  # pragma: no cover - corrupt trace
            log.warning("registry.bad_trace", extra={"id": experiment_id, "error": str(exc)})
            return None

    def stats(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT status, count(*) AS n FROM experiments GROUP BY status"
            ).fetchall()
        return {row["status"]: row["n"] for row in rows}
