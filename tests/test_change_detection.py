"""Change detection: does it fire when the environment really changes, and stay quiet otherwise?

Both halves matter equally.  A detector that fires often looks impressive on a
recall plot and destroys the policy that trusts it, because every false alarm
throws away a correctly learned posterior.  These tests pin the operating point
that ``aamsx.change_detection.detectors`` documents.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from aamsx.change_detection.detectors import (
    SIGNAL_WEIGHTS,
    ChangeState,
    CompositeChangeDetector,
    EwmaDetector,
    OnlineStandardiser,
    PageHinkley,
)

STATIONARY_STEPS = 400
"""Comfortably past every warmup in the module, so a quiet run is really quiet."""


def _run(
    detector: CompositeChangeDetector,
    *,
    steps: int,
    surprise: float = 0.5,
    divergence: float = 0.2,
    detection_rate: float = 0.4,
    rng: np.random.Generator,
    start: int = 0,
    jitter: float = 0.02,
) -> list[ChangeState]:
    """Feed ``steps`` steps of one regime, with a little noise on every symptom."""
    states: list[ChangeState] = []
    for offset in range(steps):
        state = detector.update(
            start + offset,
            surprise=surprise + jitter * rng.standard_normal(),
            divergence=divergence + jitter * rng.standard_normal(),
            detection_rate=detection_rate + jitter * rng.standard_normal(),
        )
        # ``update`` mutates and returns the same object, so record a copy.
        states.append(
            ChangeState(
                score=state.score,
                flag=state.flag,
                steps_since_change=state.steps_since_change,
                change_steps=list(state.change_steps),
                page_hinkley=state.page_hinkley,
                ewma=state.ewma,
                statistic=state.statistic,
                exploration_boost=state.exploration_boost,
            )
        )
    return states


# --------------------------------------------------------------------------- #
# the standardiser
# --------------------------------------------------------------------------- #


def test_standardiser_is_silent_until_warmup():
    standardiser = OnlineStandardiser(warmup=40)
    outputs = [
        standardiser.update(float(value)) for value in np.random.default_rng(0).normal(size=39)
    ]
    assert outputs == [0.0] * 39
    assert standardiser.samples == 39


def test_standardiser_reports_deviations_in_units_of_sigma(rng):
    standardiser = OnlineStandardiser(warmup=40)
    for value in rng.normal(loc=3.0, scale=1.0, size=600):
        standardiser.update(float(value))
    assert standardiser.mean == pytest.approx(3.0, abs=0.4)
    ordinary = standardiser.update(3.2)
    extreme = standardiser.update(12.0)
    assert abs(ordinary) < 2.0
    assert extreme > 5.0


def test_standardiser_reset_forgets_the_regime(rng):
    standardiser = OnlineStandardiser()
    for value in rng.normal(size=200):
        standardiser.update(float(value))
    standardiser.reset()
    assert (standardiser.mean, standardiser.variance, standardiser.samples) == (0.0, 1.0, 0)


# --------------------------------------------------------------------------- #
# Page-Hinkley
# --------------------------------------------------------------------------- #


def test_page_hinkley_ignores_zero_mean_noise(rng):
    detector = PageHinkley()
    fired = [detector.update(float(value))[0] for value in rng.standard_normal(2000)]
    assert not any(fired), "noise around zero must never accumulate past the threshold"


def test_page_hinkley_catches_a_persistent_upward_shift(rng):
    detector = PageHinkley()
    for _ in range(200):
        detector.update(float(rng.standard_normal()))
    latency = None
    for offset in range(200):
        flag, score = detector.update(6.0 + float(rng.standard_normal()))
        assert score >= 0.0
        if flag:
            latency = offset + 1
            break
    assert latency is not None, "a sustained +6 sigma shift must be detected"
    assert latency <= 20, f"latency {latency} is too slow to be useful to a scheduler"


def test_page_hinkley_tolerates_drift_below_delta():
    detector = PageHinkley(delta=2.0)
    fired = [detector.update(1.9)[0] for _ in range(5000)]
    assert not any(fired), "drift under delta is deliberately absorbed, not alarmed on"


def test_page_hinkley_reset_clears_the_accumulator():
    detector = PageHinkley()
    for _ in range(20):
        detector.update(5.0)
    detector.reset()
    assert (detector.cumulative, detector.minimum, detector.samples) == (0.0, 0.0, 0)


# --------------------------------------------------------------------------- #
# EWMA backstop
# --------------------------------------------------------------------------- #


def test_ewma_is_silent_during_warmup():
    detector = EwmaDetector(warmup=40)
    fired = [detector.update(50.0)[0] for _ in range(39)]
    assert not any(fired)


def test_ewma_needs_a_streak_not_a_single_spike():
    detector = EwmaDetector(warmup=5, alpha=1.0, k=4.0, consecutive=3)
    for _ in range(5):
        detector.update(0.0)
    assert detector.update(100.0)[0] is False  # one step above k is not enough
    assert detector.update(100.0)[0] is False
    assert detector.update(100.0)[0] is True  # three consecutive, now it fires


def test_ewma_score_is_bounded_to_one():
    detector = EwmaDetector()
    scores = [detector.update(1e6)[1] for _ in range(100)]
    assert max(scores) <= 1.0


# --------------------------------------------------------------------------- #
# the composite detector
# --------------------------------------------------------------------------- #


def test_stationary_symptoms_do_not_raise_an_alarm(rng):
    """The false-alarm control: nothing changes, so nothing may fire."""
    detector = CompositeChangeDetector()
    states = _run(detector, steps=STATIONARY_STEPS, rng=rng)
    assert not any(state.flag for state in states)
    assert detector.state.change_steps == []
    # ``steps_since_change`` starts at a sentinel 10_000 meaning "never changed".
    assert detector.state.steps_since_change == ChangeState().steps_since_change + STATIONARY_STEPS


def test_a_spatial_shift_in_the_hit_profile_is_detected(rng):
    """Profile divergence is the sharpest symptom of a real splice."""
    detector = CompositeChangeDetector()
    _run(detector, steps=STATIONARY_STEPS, rng=rng)
    after = _run(
        detector,
        steps=120,
        divergence=1.6,
        surprise=1.4,
        rng=rng,
        start=STATIONARY_STEPS,
    )
    flags = [index for index, state in enumerate(after) if state.flag]
    assert flags, "a large sustained divergence jump must be detected"
    assert flags[0] <= 40, f"detected {flags[0]} steps after the change; too slow"
    assert detector.state.change_steps[0] >= STATIONARY_STEPS


def test_a_drop_in_detections_raises_the_statistic_without_firing_on_its_own(rng):
    """Detection rate enters negatively, so a sparser regime pushes the statistic up.

    It deliberately does *not* fire alone at this magnitude.  Measured here: hits
    collapsing from 0.6 to 0.0 lifts the combined statistic to about +6.8 sigma for
    one step, which then decays as the online mean chases the new level, and
    Page-Hinkley's ``delta = 2.0`` absorbs the remainder.  That conservatism is the
    reason the false-alarm rate in the calibration sweep was 1 in 28 episodes; a
    real splice moves the spatial profile too, which is what actually trips it.
    """
    assert SIGNAL_WEIGHTS["detections"] < 0
    detector = CompositeChangeDetector()
    quiet = _run(detector, steps=STATIONARY_STEPS, detection_rate=0.6, rng=rng)
    after = _run(
        detector, steps=40, detection_rate=0.0, rng=rng, start=STATIONARY_STEPS, jitter=0.005
    )
    assert after[0].statistic > 4.0
    settled = max(state.score for state in quiet[-100:])
    assert max(state.score for state in after) > 2 * settled
    assert not any(state.flag for state in after)


def test_a_sparser_regime_that_also_moves_the_profile_does_fire(rng):
    """The combination the detector is actually calibrated for."""
    detector = CompositeChangeDetector()
    _run(detector, steps=STATIONARY_STEPS, detection_rate=0.6, rng=rng)
    after = _run(
        detector,
        steps=150,
        detection_rate=0.05,
        divergence=1.4,
        surprise=1.3,
        rng=rng,
        start=STATIONARY_STEPS,
    )
    assert any(state.flag for state in after)


def test_the_refractory_window_suppresses_a_second_alarm(rng):
    detector = CompositeChangeDetector(refractory=90)
    _run(detector, steps=STATIONARY_STEPS, rng=rng)
    _run(detector, steps=60, divergence=1.6, surprise=1.4, rng=rng, start=STATIONARY_STEPS)
    first = list(detector.state.change_steps)
    assert len(first) == 1
    # A second, equally violent shift inside the refractory window is absorbed.
    _run(detector, steps=20, divergence=3.0, surprise=3.0, rng=rng, start=STATIONARY_STEPS + 60)
    assert detector.state.change_steps == first


def test_an_alarm_boosts_exploration_and_then_lets_it_decay(rng):
    detector = CompositeChangeDetector(boost_gain=1.0, boost_decay=0.9)
    _run(detector, steps=STATIONARY_STEPS, rng=rng)
    after = _run(detector, steps=80, divergence=1.6, surprise=1.4, rng=rng, start=STATIONARY_STEPS)
    alarm = next(index for index, state in enumerate(after) if state.flag)
    assert after[alarm].exploration_boost == pytest.approx(1.0)
    assert after[alarm].steps_since_change == 0
    later = after[alarm + 10]
    assert later.exploration_boost < after[alarm].exploration_boost
    assert later.steps_since_change == 10


def test_score_is_a_continuous_signal_in_the_unit_interval(rng):
    detector = CompositeChangeDetector()
    states = _run(detector, steps=STATIONARY_STEPS, rng=rng)
    states += _run(
        detector, steps=120, divergence=1.6, surprise=1.4, rng=rng, start=STATIONARY_STEPS
    )
    scores = np.array([state.score for state in states])
    assert np.all((scores >= 0.0) & (scores <= 1.0))
    assert scores[STATIONARY_STEPS:].max() > scores[:STATIONARY_STEPS].max()


def test_reset_returns_the_detector_to_its_initial_state(rng):
    detector = CompositeChangeDetector()
    _run(detector, steps=STATIONARY_STEPS, rng=rng)
    _run(detector, steps=80, divergence=1.6, surprise=1.4, rng=rng, start=STATIONARY_STEPS)
    detector.reset()
    assert detector.state.change_steps == []
    assert detector.state.flag is False
    assert detector.state.exploration_boost == 0.0
    assert detector.page_hinkley.samples == 0


def test_snapshot_is_json_serialisable(rng):
    detector = CompositeChangeDetector()
    _run(detector, steps=60, rng=rng)
    payload = detector.snapshot()
    assert json.loads(json.dumps(payload)) == payload
    assert set(payload) >= {"score", "flag", "steps_since_change"}
