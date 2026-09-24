import numpy as np
import pytest

from backend.metrics import MetricAccumulator
from backend.tests.conftest import decision, observation


def test_metrics_against_hand_calculated_confusion_matrix(world_factory):
    truth = np.zeros((3, 8), dtype=bool)
    truth[0, [1, 6]] = True
    truth[1, 1] = True
    truth[2, 6] = True
    metrics = MetricAccumulator(world_factory(truth), 100)
    values = [observation(0, 0, [True, True]), observation(1, 0, [False, False]), observation(2, 6, [True, False], cost=0.2)]
    for i, obs in enumerate(values):
        metrics.update(obs, decision(obs.window), changed=i == 2)
    m = metrics.snapshot()
    assert (m["true_positives"], m["false_positives"], m["true_negatives"], m["false_negatives_observed"]) == (2, 1, 2, 1)
    assert m["pd"] == pytest.approx(2 / 3, abs=1e-6)
    assert m["pfa"] == pytest.approx(1 / 3, abs=1e-6)
    assert m["recall"] == m["avg_interception_rate"] == m["prediction_accuracy"] == 0.5
    assert m["interception_ratio"] == pytest.approx(2 / 3, abs=1e-6)
    assert m["avg_intercept_time_ms"] == 0
    assert m["missed_active_cells"] == 2
    assert m["reward_cost"] == pytest.approx((2 - 1 - 0.02) / 3.2, abs=1e-6)
    assert m["retune_count"] == 1
    assert m["avg_intercept_time_error_ms"] is None


def test_prospective_period_errors_not_scored_before_actual_onset(world_factory):
    truth = np.zeros((8, 8), dtype=bool)
    truth[5, 1] = True
    metrics = MetricAccumulator(world_factory(truth), 100)
    for step in range(6):
        obs = observation(step, 0, [False, step == 5])
        forecasts = [{"band": 1, "confidence": 0.8, "next_slot": 6.5}] if step == 0 else []
        metrics.update(obs, decision(obs.window, forecasts=forecasts), False)
        if step < 5:
            assert metrics.snapshot()["avg_intercept_time_error_ms"] is None
    assert metrics.snapshot()["avg_intercept_time_error_ms"] == 150
    assert metrics.snapshot()["resolved_predictions"] == 1


def test_measured_rf_metrics_have_no_fabricated_truth(world_factory):
    world = world_factory(None, [[-90] * 8])
    metrics = MetricAccumulator(world, 100)
    obs = observation(0, 0, [True, False])
    result = metrics.update(obs, decision(obs.window), False)
    for key in ["pd", "pfa", "recall", "interception_ratio", "reward_cost", "average_reward", "prediction_accuracy", "avg_intercept_time_ms", "avg_intercept_time_error_ms"]:
        assert result["metrics"][key] is None
    assert result["metrics"]["observed_energy_events"] == 1
    assert result["metrics"]["coverage"] == 0.25
    assert result["reward"] is None


def test_zero_denominators_and_missing_channels(world_factory):
    metrics = MetricAccumulator(world_factory([[False] * 8]), 100)
    obs = observation(0, 0, [False, False], valid=[True, False])
    metrics.update(obs, decision(obs.window), False)
    m = metrics.snapshot()
    assert m["pd"] is None and m["recall"] is None
    assert m["pfa"] == 0
    assert m["observed_cells"] == 1 and m["missing_channel_fraction"] == 0.5
