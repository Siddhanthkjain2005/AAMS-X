import csv
import io
import json

import pytest

from backend.contracts import ExperimentConfig
from backend.experiments import Experiment, Registry
from backend.experiments.benchmark import Benchmark, BenchmarkConfig, statistics
from backend.experiments.engine import canonical_json, view_frame
from backend.experiments.registry import export_csv


def test_fair_duel_and_exact_seed_replay(tmp_path):
    config = ExperimentConfig(horizon=48)
    a, b = Experiment(config).run(), Experiment(config).run()
    assert a.environment_hash == b.environment_hash
    assert a.frames == b.frames
    assert all(env._world is a.world for env in a.environments.values())
    assert a.policies["fixed"].belief is not a.policies["magnts"].belief
    registry = Registry(tmp_path)
    registry.save(a.record())
    loaded = registry.load(a.id)
    assert loaded["frames"] == a.frames
    assert json.loads(canonical_json(loaded))["trace_hash"] == a.record()["trace_hash"]
    assert len(list(csv.DictReader(io.StringIO(export_csv(loaded))))) == config.horizon * 2
    assert len(registry.list()) == 1


def test_replay_checksum_detects_corruption(tmp_path):
    registry = Registry(tmp_path)
    run = Experiment(ExperimentConfig(horizon=24)).run()
    registry.save(run.record())
    path = tmp_path / f"{run.id}.json.gz"
    path.write_bytes(path.read_bytes() + b"corruption")
    with pytest.raises(ValueError, match="checksum"):
        registry.load(run.id)
    with pytest.raises(ValueError, match="ID"):
        registry.load("../../secret")


def test_judge_truth_is_opt_in_and_pre_observation_predictions_stored():
    run = Experiment(ExperimentConfig(horizon=24))
    frame = run.step()
    ordinary = view_frame(frame)
    assert "evaluation" not in ordinary
    assert "evaluation" not in ordinary["policies"]["magnts"]
    assert "evaluation" in view_frame(frame, judge=True)
    assert set(frame["policies"]["magnts"]["decision"]["pre_probability"]) == {0.5}
    assert ordinary["policies"]["magnts"]["belief"]["probability"] != [0.5] * 48


def test_benchmark_aggregation_is_paired_and_computed(tmp_path):
    config = BenchmarkConfig(scenarios=["sudden"], runs=2, horizon=24, algorithms=["magnts", "fixed"])
    job = Benchmark(config, Registry(tmp_path))
    job.run_one("sudden", 42)
    job.run_one("sudden", 43)
    results = job.snapshot()
    full = next(a for a in results["aggregates"] if a["algorithm"] == "magnts")
    expected = [r["metrics"]["magnts"]["recall"] - r["metrics"]["fixed"]["recall"] for r in results["results"]]
    assert full["paired_delta_vs_fixed"]["recall"]["values"] == expected
    assert full["metrics"]["recall"]["n"] == 2
    assert full["metrics"]["recall"]["ci95"] is not None
    assert statistics([])["mean"] is None
    assert statistics([0.5])["ci95"] is None
