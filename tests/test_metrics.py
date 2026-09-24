"""Metrics, events and reward: the invariants a judge is entitled to assume.

These are pure-function tests with hand-built inputs, so every expected number is
derived by hand in the assertion rather than recorded from a previous run.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from aamsx.contracts.observation import Observation
from aamsx.contracts.scenario import RewardWeights
from aamsx.evaluation.events import EventTracker
from aamsx.evaluation.metrics import MetricAccumulator, recovery_time
from aamsx.evaluation.reward import LOG2, RewardModel

REGIONS = 8
WINDOW = 4


def _observation(
    step: int = 0, *, detected: list[bool], cost: float = 1.0, available: bool = True
) -> Observation:
    size = len(detected)
    return Observation(
        step=step,
        regions=np.arange(size, dtype=np.int32),
        measured_db=np.zeros(size, dtype=np.float32),
        detected=np.array(detected, dtype=bool),
        threshold_db=np.zeros(size, dtype=np.float32),
        confidence=np.full(size, 0.9, dtype=np.float32),
        cost=cost,
        available=available,
        t_sec=float(step),
    )


def _accumulator(**kwargs) -> MetricAccumulator:
    return MetricAccumulator(
        n_regions=REGIONS, window_size=WINDOW, horizon=100, budget=100.0, **kwargs
    )


def _record(acc: MetricAccumulator, *, step, anchor, detected, truth, oracle=2, **kwargs):
    acc.record(
        step=step,
        anchor=anchor,
        detected=np.array(detected, dtype=bool),
        true_occupied=np.array(truth, dtype=bool),
        reward=kwargs.pop("reward", 1.0),
        reward_terms=kwargs.pop("reward_terms", {"detection": 1.0}),
        cost=kwargs.pop("cost", 1.0),
        information_bits=kwargs.pop("information_bits", 0.5),
        oracle_best=oracle,
        available=kwargs.pop("available", True),
    )


# --------------------------------------------------------------------------- #
# confusion-matrix bookkeeping
# --------------------------------------------------------------------------- #


def test_a_perfect_step_is_all_true_positives():
    acc = _accumulator()
    _record(acc, step=0, anchor=0, detected=[1, 1, 1, 1], truth=[1, 1, 1, 1], oracle=4)
    assert (acc.true_positives, acc.false_positives, acc.false_negatives) == (4, 0, 0)
    assert acc.detection_rate == 1.0
    assert acc.precision == 1.0
    assert acc.total_regret == 0.0


def test_the_four_confusion_cells_are_counted_independently():
    acc = _accumulator()
    _record(acc, step=0, anchor=0, detected=[1, 1, 0, 0], truth=[1, 0, 1, 0])
    assert acc.true_positives == 1
    assert acc.false_positives == 1
    assert acc.false_negatives == 1
    assert acc.true_negatives == 1
    assert acc.detection_rate == pytest.approx(0.5)
    assert acc.false_alarm_rate == pytest.approx(0.5)
    assert acc.precision == pytest.approx(0.5)


def test_rates_are_nan_rather_than_zero_when_undefined():
    """Reporting 0.0 for "no positives existed" would be a fabricated result."""
    acc = _accumulator()
    _record(acc, step=0, anchor=0, detected=[0, 0, 0, 0], truth=[0, 0, 0, 0], oracle=0)
    assert np.isnan(acc.detection_rate)
    assert np.isnan(acc.precision)
    assert acc.false_alarm_rate == 0.0


def test_an_unavailable_step_is_counted_but_never_scored_as_a_cell():
    """An archive dropout must not be laundered into a perfect specificity."""
    acc = _accumulator()
    _record(acc, step=0, anchor=0, detected=[0, 0, 0, 0], truth=[1, 1, 0, 0], available=False)
    assert acc.steps == 1
    assert acc.unavailable_steps == 1
    assert acc.cells_observed == 0
    assert (acc.true_positives, acc.false_negatives, acc.true_negatives) == (0, 0, 0)


# --------------------------------------------------------------------------- #
# regret and the oracle
# --------------------------------------------------------------------------- #


def test_regret_is_the_shortfall_against_the_clairvoyant_window():
    acc = _accumulator()
    _record(acc, step=0, anchor=0, detected=[1, 0, 0, 0], truth=[1, 1, 1, 1], oracle=4)
    assert acc.total_regret == 3.0
    assert acc.oracle_ratio == pytest.approx(0.25)


def test_regret_never_goes_negative():
    """Beating the oracle is impossible; a noisy hit must not create credit."""
    acc = _accumulator()
    _record(acc, step=0, anchor=0, detected=[1, 1, 1, 1], truth=[1, 1, 1, 1], oracle=1)
    assert acc.total_regret == 0.0


def test_curves_are_monotone_and_one_point_per_step():
    acc = _accumulator()
    for step in range(20):
        _record(acc, step=step, anchor=step % 5, detected=[1, 0, 0, 0], truth=[1, 1, 0, 0])
    assert len(acc.reward_curve) == len(acc.regret_curve) == 20
    assert np.all(np.diff(acc.reward_curve) >= 0)  # every reward here is positive
    assert np.all(np.diff(acc.regret_curve) >= 0)  # regret can only accumulate


# --------------------------------------------------------------------------- #
# efficiency and coverage
# --------------------------------------------------------------------------- #


def test_efficiency_metrics_divide_by_what_they_claim_to():
    acc = _accumulator()
    for step in range(4):
        _record(acc, step=step, anchor=0, detected=[1, 1, 0, 0], truth=[1, 1, 0, 0], cost=2.0)
    assert acc.hits_total == 8
    assert acc.detections_per_observation == pytest.approx(2.0)
    assert acc.detections_per_cost == pytest.approx(1.0)
    assert acc.information_per_observation == pytest.approx(0.5)


def test_coverage_is_the_fraction_of_anchors_visited():
    acc = _accumulator()
    anchors = REGIONS - WINDOW + 1
    for step in range(anchors):
        _record(acc, step=step, anchor=step, detected=[0] * 4, truth=[0] * 4, oracle=0)
    assert acc.coverage == pytest.approx(1.0)

    camper = _accumulator()
    for step in range(anchors):
        _record(camper, step=step, anchor=0, detected=[0] * 4, truth=[0] * 4, oracle=0)
    assert camper.coverage == pytest.approx(1.0 / anchors)


def test_reward_terms_accumulate_per_key():
    acc = _accumulator()
    for step in range(3):
        _record(
            acc,
            step=step,
            anchor=0,
            detected=[1, 0, 0, 0],
            truth=[1, 0, 0, 0],
            reward_terms={"detection": 0.25, "switching": -0.1},
        )
    assert acc.reward_terms["detection"] == pytest.approx(0.75)
    assert acc.reward_terms["switching"] == pytest.approx(-0.3)


def test_summary_is_json_safe_and_carries_the_headline_keys():
    acc = _accumulator()
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(10):
        tracker.begin_step(step, np.array([1, 1, 0, 0, 0, 0, 0, 0], dtype=bool))
        tracker.observe(step, np.arange(4, dtype=np.int32), np.array([1, 0, 0, 0], dtype=bool))
        _record(acc, step=step, anchor=0, detected=[1, 0, 0, 0], truth=[1, 1, 0, 0])
    tracker.finish(10)
    summary = acc.summary(tracker)
    for key in (
        "detection_rate",
        "sustained_detection_probability",
        "cumulative_reward",
        "cumulative_regret",
        "oracle_ratio",
        "band_coverage",
        "budget_used_fraction",
        "reward.detection",
    ):
        assert key in summary
    # NaN is not JSON, but it must survive the round trip rather than be faked.
    json.dumps(summary, allow_nan=True)


# --------------------------------------------------------------------------- #
# event tracking
# --------------------------------------------------------------------------- #


def _band(*regions: int) -> np.ndarray:
    occupied = np.zeros(REGIONS, dtype=bool)
    for region in regions:
        occupied[region] = True
    return occupied


def test_one_contiguous_run_is_one_event():
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(5):
        tracker.begin_step(step, _band(2))
    tracker.begin_step(5, _band())
    tracker.finish(6)
    assert len(tracker.events) == 1
    assert tracker.events[0].onset_step == 0
    assert tracker.events[0].duration == 5


def test_activity_that_stops_and_restarts_is_two_events():
    tracker = EventTracker(n_regions=REGIONS)
    for step, occupied in enumerate([_band(2), _band(2), _band(), _band(2)]):
        tracker.begin_step(step, occupied)
    tracker.finish(4)
    assert len(tracker.events) == 2


def test_delay_is_measured_from_onset_not_from_the_first_look():
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(6):
        tracker.begin_step(step, _band(0))
        if step == 4:
            tracker.observe(step, np.array([0], dtype=np.int32), np.array([True]))
    tracker.finish(6)
    event = tracker.events[0]
    assert event.detected is True
    assert event.delay == 4


def test_a_later_detection_does_not_overwrite_the_first():
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(6):
        tracker.begin_step(step, _band(0))
        if step in (2, 5):
            tracker.observe(step, np.array([0], dtype=np.int32), np.array([True]))
    tracker.finish(6)
    assert tracker.events[0].delay == 2


def test_an_undetected_event_reports_no_delay_rather_than_a_large_one():
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(4):
        tracker.begin_step(step, _band(3))
    tracker.finish(4)
    event = tracker.events[0]
    assert event.detected is False
    assert event.delay is None
    assert tracker.summary()["events_missed"] == 1


def test_single_step_events_are_excluded_from_the_sustained_figures():
    """Why both figures are reported: blips are not a scheduling failure."""
    tracker = EventTracker(n_regions=REGIONS)
    blips = [_band(1), _band(), _band(2), _band()]
    for step, occupied in enumerate(blips):
        tracker.begin_step(step, occupied)
    for step in range(4, 4 + EventTracker.SUSTAINED_STEPS + 1):
        tracker.begin_step(step, _band(5))
    tracker.finish(4 + EventTracker.SUSTAINED_STEPS + 1)
    summary = tracker.summary()
    assert summary["events_total"] == 3
    assert summary["events_sustained"] == 1


def test_time_to_detect_charges_the_cap_for_a_missed_event():
    """Otherwise the metric rewards catching only the three easiest bursts."""
    tracker = EventTracker(n_regions=REGIONS, delay_cap=16)
    for step in range(8):
        tracker.begin_step(step, _band(0, 4))
        if step == 2:
            tracker.observe(step, np.array([0], dtype=np.int32), np.array([True]))
    tracker.finish(8)
    summary = tracker.summary()
    assert summary["events_sustained"] == 2
    assert summary["events_sustained_detected"] == 1
    assert summary["sustained_detection_probability"] == pytest.approx(0.5)
    # (2 detected + 16 capped) / 2
    assert summary["time_to_detect_capped"] == pytest.approx(9.0)
    # Survivorship-biased delay, reported alongside for comparison.
    assert summary["sustained_detection_delay"] == pytest.approx(2.0)


def test_pending_delay_is_normalised_by_the_cap():
    tracker = EventTracker(n_regions=REGIONS, delay_cap=10)
    assert tracker.pending_delay(0) == 0.0
    for step in range(6):
        tracker.begin_step(step, _band(0))
    assert tracker.undetected_now() == 1
    assert tracker.pending_delay(5) == pytest.approx(0.5)


def test_a_detected_event_stops_contributing_to_pending_delay():
    tracker = EventTracker(n_regions=REGIONS, delay_cap=10)
    for step in range(6):
        tracker.begin_step(step, _band(0))
        if step == 1:
            tracker.observe(step, np.array([0], dtype=np.int32), np.array([True]))
    assert tracker.undetected_now() == 0
    assert tracker.pending_delay(5) == 0.0


def test_pending_delay_is_capped():
    tracker = EventTracker(n_regions=REGIONS, delay_cap=4)
    for step in range(50):
        tracker.begin_step(step, _band(0))
    assert tracker.pending_delay(49) == pytest.approx(1.0)


def test_tracker_reset_clears_open_and_closed_events():
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(4):
        tracker.begin_step(step, _band(0))
    tracker.reset()
    assert tracker.events == []
    assert tracker.summary()["events_total"] == 0


def test_event_dicts_are_json_serialisable():
    tracker = EventTracker(n_regions=REGIONS)
    for step in range(4):
        tracker.begin_step(step, _band(0))
    tracker.finish(4)
    payload = [event.to_dict() for event in tracker.events]
    assert json.loads(json.dumps(payload)) == payload


# --------------------------------------------------------------------------- #
# the reward model
# --------------------------------------------------------------------------- #


def _model(**overrides) -> RewardModel:
    return RewardModel(RewardWeights(**overrides), WINDOW)


def _score(model: RewardModel, detected, truth, **kwargs):
    return model.score(
        _observation(
            detected=detected, **{k: kwargs.pop(k) for k in ("available",) if k in kwargs}
        ),
        np.array(truth, dtype=bool),
        entropy_before=kwargs.pop("entropy_before", 0.0),
        entropy_after=kwargs.pop("entropy_after", 0.0),
        pending_delay=kwargs.pop("pending_delay", 0.0),
        retune_fraction=kwargs.pop("retune_fraction", 0.0),
    )


def test_every_term_is_normalised_by_the_window():
    model = _model()
    full = _score(model, [1, 1, 1, 1], [1, 1, 1, 1])
    assert full.terms["detection"] == pytest.approx(1.0)
    half = _score(model, [1, 1, 0, 0], [1, 1, 0, 0])
    assert half.terms["detection"] == pytest.approx(0.5)


def test_information_is_realised_not_predicted():
    """One nat of entropy actually lost, expressed in bits per region."""
    model = _model(information=1.0)
    reward = _score(model, [0, 0, 0, 0], [0, 0, 0, 0], entropy_before=LOG2, entropy_after=0.0)
    assert reward.realised_information_bits == pytest.approx(1.0)
    assert reward.terms["information"] == pytest.approx(0.25)


def test_entropy_that_went_up_earns_nothing_rather_than_a_penalty():
    model = _model(information=1.0)
    reward = _score(model, [0] * 4, [0] * 4, entropy_before=0.0, entropy_after=LOG2)
    assert reward.realised_information_bits == 0.0
    assert reward.terms["information"] == 0.0


def test_the_penalty_terms_are_negative_and_weighted():
    model = _model(delay=0.5, false_alarm=0.5, switching=0.05)
    reward = _score(model, [1, 1, 0, 0], [0, 0, 0, 0], pending_delay=1.0, retune_fraction=1.0)
    assert reward.false_alarms == 2
    assert reward.terms["false_alarm"] == pytest.approx(-0.25)
    assert reward.terms["delay"] == pytest.approx(-0.5)
    assert reward.terms["switching"] == pytest.approx(-0.05)


def test_the_total_is_exactly_the_sum_of_the_reported_terms():
    model = _model()
    reward = _score(
        model,
        [1, 1, 1, 0],
        [1, 1, 0, 0],
        entropy_before=2 * LOG2,
        entropy_after=0.0,
        pending_delay=0.3,
        retune_fraction=0.8,
    )
    assert reward.total == pytest.approx(sum(reward.terms.values()), abs=1e-6)
    assert reward.hits == 2
    assert reward.false_alarms == 1
    assert reward.missed_in_window == 0


def test_a_dropout_earns_and_charges_nothing_but_still_pays_for_delay():
    model = _model(delay=0.5)
    reward = _score(
        model,
        [1, 1, 1, 1],
        [1, 1, 1, 1],
        available=False,
        entropy_before=4 * LOG2,
        entropy_after=0.0,
        pending_delay=1.0,
        retune_fraction=1.0,
    )
    assert reward.terms["detection"] == 0.0
    assert reward.terms["information"] == 0.0
    assert reward.terms["switching"] == 0.0
    assert reward.terms["delay"] == pytest.approx(-0.5)


def test_zero_weights_produce_a_zero_reward():
    model = RewardModel(
        RewardWeights(detection=0, information=0, delay=0, false_alarm=0, switching=0), WINDOW
    )
    reward = _score(model, [1, 0, 1, 0], [1, 1, 0, 0], pending_delay=1.0, retune_fraction=1.0)
    assert reward.total == 0.0


# --------------------------------------------------------------------------- #
# recovery time
# --------------------------------------------------------------------------- #


def test_recovery_time_finds_the_step_performance_returns():
    before = np.full(100, 1.0)
    after = np.concatenate([np.zeros(30), np.full(70, 1.0)])
    assert recovery_time(np.concatenate([before, after]), 100, window=20) == pytest.approx(
        48, abs=8
    )


def test_a_policy_that_never_recovers_reports_none_not_the_horizon():
    curve = np.concatenate([np.full(100, 1.0), np.zeros(100)])
    assert recovery_time(curve, 100, window=20) is None


def test_recovery_time_declines_to_answer_without_a_reference_window():
    curve = np.full(100, 1.0)
    assert recovery_time(curve, 5, window=20) is None
    assert recovery_time(curve, 500, window=20) is None
    assert recovery_time(np.zeros(100), 50, window=20) is None
