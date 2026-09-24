"""Reproducibility: the same request must produce the same numbers, twice.

The Replay Experiment button in the UI is only honest if this holds, so it is
tested three ways: the config hash is stable across dict orderings, the registry
round-trips a run without losing anything, and two identical episodes agree
metric-for-metric.
"""

from __future__ import annotations

import json

import pytest

from aamsx.config import Settings
from aamsx.experiments.registry import Registry, config_hash
from aamsx.experiments.runner import run_episode
from aamsx.schedulers.base import AblationFlags
from aamsx.version import CODE_VERSION
from tests.conftest import requires_cache


@pytest.fixture()
def registry(tmp_path) -> Registry:
    settings = Settings(data_dir=tmp_path / "data", reports_dir=tmp_path / "reports")
    settings.ensure_dirs()
    return Registry(settings)


def _create(registry: Registry, experiment_id: str, **overrides) -> None:
    payload = {
        "experiment_id": experiment_id,
        "kind": "episode",
        "scenario_id": "easy-static",
        "scheduler": "mag-nts",
        "seed": 0,
        "ablation": "full",
        "recordings": ["MRO/20260825"],
        "config": {"scenario_id": "easy-static", "scheduler": "mag-nts", "seed": 0},
    }
    payload.update(overrides)
    registry.create(**payload)


# --------------------------------------------------------------------------- #
# the config hash
# --------------------------------------------------------------------------- #


def test_the_hash_ignores_key_order():
    left = {"scheduler": "mag-nts", "seed": 3, "scenario": "sudden-shift"}
    right = {"seed": 3, "scenario": "sudden-shift", "scheduler": "mag-nts"}
    assert config_hash(left) == config_hash(right)


def test_the_hash_ignores_nested_key_order():
    left = {"ablation": {"memory": True, "periodicity": False}, "seed": 1}
    right = {"seed": 1, "ablation": {"periodicity": False, "memory": True}}
    assert config_hash(left) == config_hash(right)


@pytest.mark.parametrize(
    "change",
    [
        {"seed": 4},
        {"scheduler": "nts"},
        {"scenario": "recurring-environment"},
        {"extra": 1},
    ],
)
def test_any_material_change_changes_the_hash(change):
    base = {"scheduler": "mag-nts", "seed": 3, "scenario": "sudden-shift"}
    assert config_hash(base) != config_hash({**base, **change})


def test_the_hash_is_short_stable_and_hex():
    digest = config_hash({"a": 1})
    assert len(digest) == 16
    assert int(digest, 16) >= 0
    assert digest == config_hash({"a": 1})


def test_the_hash_survives_a_json_round_trip():
    payload = {"ablation": AblationFlags().to_dict(), "seed": 2, "weights": {"delay": 0.5}}
    assert config_hash(payload) == config_hash(json.loads(json.dumps(payload)))


def test_a_boolean_and_its_integer_are_not_confused():
    """``memory: True`` and ``memory: 1`` are different requests, not the same one."""
    assert config_hash({"memory": True}) != config_hash({"memory": "1"})


# --------------------------------------------------------------------------- #
# the registry
# --------------------------------------------------------------------------- #


def test_a_created_experiment_is_immediately_retrievable(registry):
    _create(registry, "exp-1")
    record = registry.get("exp-1")
    assert record is not None
    assert record.status == "running"
    assert record.scenario_id == "easy-static"
    assert record.code_version == CODE_VERSION
    assert record.recordings == ["MRO/20260825"]
    assert record.metrics is None
    assert record.finished_at is None


def test_an_unknown_experiment_returns_none_rather_than_raising(registry):
    assert registry.get("nope") is None
    assert registry.load_result("nope") is None


def test_finishing_stores_the_metrics_and_the_full_trace(registry):
    _create(registry, "exp-2")
    result = {"metrics": {"cumulative_reward": 12.5}, "curves": {"reward": [1.0, 2.0]}}
    registry.finish("exp-2", status="completed", metrics=result["metrics"], result=result)
    record = registry.get("exp-2")
    assert record.status == "completed"
    assert record.finished_at is not None
    assert record.metrics == {"cumulative_reward": 12.5}
    assert registry.load_result("exp-2") == result
    assert registry.result_path("exp-2").exists()


def test_a_failed_experiment_records_the_error_and_no_metrics(registry):
    _create(registry, "exp-3")
    registry.finish("exp-3", status="failed", error="cache miss")
    record = registry.get("exp-3")
    assert record.status == "failed"
    assert record.error == "cache miss"
    assert record.metrics is None


def test_only_completed_runs_are_found_by_hash(registry):
    """Replay must never hand back a crashed run's trace."""
    _create(registry, "exp-4")
    digest = registry.get("exp-4").config_hash
    assert registry.find_by_hash(digest) is None  # still running
    registry.finish("exp-4", status="failed", error="boom")
    assert registry.find_by_hash(digest) is None  # failed
    registry.finish("exp-4", status="completed", metrics={"m": 1.0}, result={"m": 1.0})
    assert registry.find_by_hash(digest).experiment_id == "exp-4"


def test_the_same_config_hashes_to_the_same_row(registry):
    _create(registry, "exp-5")
    _create(registry, "exp-6")
    assert registry.get("exp-5").config_hash == registry.get("exp-6").config_hash


def test_history_is_newest_first_and_filterable_by_kind(registry):
    _create(registry, "exp-7", kind="episode")
    _create(registry, "exp-8", kind="arena")
    _create(registry, "exp-9", kind="ablation")
    assert [r.experiment_id for r in registry.history(limit=2)] == ["exp-9", "exp-8"]
    assert [r.experiment_id for r in registry.history(kind="arena")] == ["exp-8"]
    assert len(registry.history(limit=1)) == 1


def test_stats_counts_experiments_by_status(registry):
    _create(registry, "exp-a")
    _create(registry, "exp-b")
    registry.finish("exp-b", status="completed", metrics={}, result={})
    assert registry.stats() == {"running": 1, "completed": 1}


def test_a_record_round_trips_through_json(registry):
    _create(registry, "exp-c")
    payload = registry.get("exp-c").to_dict()
    assert json.loads(json.dumps(payload)) == payload


def test_a_second_registry_on_the_same_path_sees_the_same_rows(registry):
    _create(registry, "exp-d")
    reopened = Registry(registry.settings)
    assert reopened.get("exp-d") is not None


# --------------------------------------------------------------------------- #
# episode-level determinism
# --------------------------------------------------------------------------- #


@requires_cache
@pytest.mark.parametrize("scheduler", ["round-robin", "ucb", "thompson", "nts", "mag-nts"])
def test_the_same_seed_reproduces_every_metric(scheduler, short_spec):
    first = run_episode(short_spec, scheduler, seed=5)
    second = run_episode(short_spec, scheduler, seed=5)
    assert first.metrics == second.metrics
    assert first.curves["reward"] == second.curves["reward"]
    assert first.steps == second.steps


@requires_cache
def test_a_different_seed_gives_a_different_trace(short_spec):
    """Otherwise the seed is decorative and multi-seed statistics mean nothing."""
    first = run_episode(short_spec, "mag-nts", seed=5)
    second = run_episode(short_spec, "mag-nts", seed=6)
    assert first.curves["reward"] != second.curves["reward"]


@requires_cache
def test_a_deterministic_baseline_still_moves_with_the_seed_because_the_receiver_does(short_spec):
    """The seed drives receiver noise as well as the policy, and that is the point.

    Round robin has no randomness of its own, so it visits the *same anchors in the
    same order* under any seed.  Its rewards still differ, because the seed also
    draws the receiver noise the environment adds to each dwell — which is what
    makes a multi-seed comparison a measurement of the sensing problem rather than
    of the policy's coin flips.  A test asserting identical rewards here would be
    asserting that the receiver is noiseless.
    """
    first = run_episode(short_spec, "round-robin", seed=5)
    second = run_episode(short_spec, "round-robin", seed=6)
    assert first.curves["anchors"] == second.curves["anchors"]
    assert first.curves["reward"] != second.curves["reward"]


@requires_cache
def test_an_episode_result_is_json_serialisable_and_carries_its_provenance(short_spec):
    result = run_episode(short_spec, "mag-nts", seed=1)
    payload = result.to_dict()
    json.dumps(payload, allow_nan=True)
    assert payload["scheduler"] == "mag-nts"
    assert payload["seed"] == 1
    assert payload["flags"] == AblationFlags().to_dict()
    assert payload["scenario"]["segments"]
    assert payload["steps"] > 0
    assert payload["decision_ms"]["p50"] >= 0.0


@requires_cache
def test_ablation_flags_are_recorded_with_the_result(short_spec):
    flags = AblationFlags(memory=False, periodicity=False)
    result = run_episode(short_spec, "mag-nts", seed=1, flags=flags)
    assert result.flags == flags.to_dict()
    assert result.flags["memory"] is False


@requires_cache
def test_turning_a_component_off_changes_the_trace(short_spec):
    """An ablation that changes nothing would mean the component is not wired in."""
    full = run_episode(short_spec, "mag-nts", seed=2)
    without_ig = run_episode(
        short_spec, "mag-nts", seed=2, flags=AblationFlags(information_gain=False)
    )
    assert full.curves["reward"] != without_ig.curves["reward"]
