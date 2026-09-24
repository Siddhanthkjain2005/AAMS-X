"""Multi-seed, paired evaluations with sample variance and Student-t mean intervals."""

import csv
import io
import json
import uuid
from datetime import datetime, timezone

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator
from scipy.stats import t as student_t

from backend.contracts import Algorithm, ExperimentConfig, ReceiverConfig
from backend.datasets.environment import build_world

from .engine import Experiment
from .registry import Registry

DEFAULT_ABLATIONS = ["magnts", "no_memory", "no_information", "no_change", "thompson", "fixed"]
BENCHMARK_METRICS = ["recall", "pd", "pfa", "avg_intercept_time_ms", "prediction_accuracy", "reward_cost", "interception_ratio", "avg_intercept_time_error_ms", "coverage_fairness"]


class BenchmarkConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenarios: list[str] = Field(default_factory=lambda: ["sudden", "periodic", "agile"], min_length=1, max_length=10)
    seed: int = Field(42, ge=0, le=2**32 - 20)
    runs: int = Field(3, ge=1, le=6)
    horizon: int = Field(240, ge=24, le=1000)
    receiver: ReceiverConfig = Field(default_factory=ReceiverConfig)
    algorithms: list[Algorithm] = Field(default_factory=lambda: list(DEFAULT_ABLATIONS), min_length=1, max_length=8)
    dataset_id: str = "simulation"

    @model_validator(mode="after")
    def bounded(self):
        if len(self.scenarios) * self.runs > 30:
            raise ValueError("Local benchmark limit: 30 paired worlds per job")
        if len(set(self.scenarios)) != len(self.scenarios) or len(set(self.algorithms)) != len(self.algorithms):
            raise ValueError("Scenarios and algorithms must be unique")
        return self


def statistics(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "mean": None, "median": None, "variance": None, "ci95": None, "values": []}
    mean = float(np.mean(values))
    variance = float(np.var(values, ddof=1)) if len(values) > 1 else None
    margin = float(student_t.ppf(0.975, len(values) - 1) * np.sqrt(variance / len(values))) if variance is not None else None
    return {"n": len(values), "mean": mean, "median": float(np.median(values)), "variance": variance, "ci95": [mean - margin, mean + margin] if margin is not None else None, "values": values}


class Benchmark:
    def __init__(self, config: BenchmarkConfig, registry: Registry):
        self.id = f"BENCH-{uuid.uuid4().hex[:10].upper()}"
        self.config = config
        self.registry = registry
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.state = "running"
        self.error = None
        self.results: list[dict] = []
        self.completed = 0
        self.total = len(config.scenarios) * config.runs

    def run_one(self, scenario: str, seed: int):
        requested = ExperimentConfig(scenario=scenario, seed=seed, horizon=self.config.horizon, receiver=self.config.receiver, algorithms=self.config.algorithms, dataset_id=self.config.dataset_id)
        effective, world = build_world(requested)
        run = Experiment(effective, world).run()
        self.registry.save(run.record())
        self.results.append({"experiment_id": run.id, "scenario": scenario, "seed": seed, "environment_hash": run.environment_hash, "metrics": run.summary()["metrics"]})
        self.completed += 1

    def snapshot(self) -> dict:
        aggregates = []
        for scenario in self.config.scenarios:
            selected = [r for r in self.results if r["scenario"] == scenario]
            for algorithm in self.config.algorithms:
                metrics, paired = {}, {}
                for key in BENCHMARK_METRICS:
                    values = [r["metrics"][algorithm][key] for r in selected if r["metrics"][algorithm][key] is not None]
                    metrics[key] = statistics(values)
                    deltas = [r["metrics"][algorithm][key] - r["metrics"]["fixed"][key] for r in selected if "fixed" in r["metrics"] and r["metrics"][algorithm][key] is not None and r["metrics"]["fixed"][key] is not None]
                    paired[key] = statistics(deltas)
                aggregates.append({"scenario": scenario, "algorithm": algorithm, "metrics": metrics, "paired_delta_vs_fixed": paired})
        return {"id": self.id, "created_at": self.created_at, "state": self.state, "error": self.error, "completed": self.completed, "total": self.total, "config": self.config.model_dump(), "results": list(self.results), "aggregates": aggregates, "methodology": "Paired seeds, immutable shared world/noise per run, independent policy states. 95% Student-t confidence interval for the mean across seeds; n=1 has no interval. No selection of winning seeds. Timing averages are conditional on intercepted episodes."}

    def persist(self):
        path = self.registry.directory / f"{self.id}.json"
        path.write_text(json.dumps(self.snapshot(), allow_nan=False))


def benchmark_csv(record: dict) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["benchmark_id", "experiment_id", "scenario", "seed", "algorithm", *BENCHMARK_METRICS])
    writer.writeheader()
    for run in record["results"]:
        for algorithm, metrics in run["metrics"].items():
            writer.writerow({"benchmark_id": record["id"], "experiment_id": run["experiment_id"], "scenario": run["scenario"], "seed": run["seed"], "algorithm": algorithm, **{key: metrics[key] for key in BENCHMARK_METRICS}})
    return output.getvalue()
