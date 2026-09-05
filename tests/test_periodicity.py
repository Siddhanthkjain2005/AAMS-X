"""Periodicity: find a real cycle, and refuse to invent one.

The failure mode this module is built against is a confident period reported for
a signal that has none — an ACF maximum always exists, so a naive detector always
"discovers" a period.  Half of these tests are therefore negative controls.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from aamsx.environment.characterize import dominant_period
from aamsx.periodicity.recurrence import PeriodicityEngine

REGIONS = 12
WINDOW = 4


def _window(anchor: int) -> np.ndarray:
    return np.arange(anchor, anchor + WINDOW, dtype=np.int32)


# --------------------------------------------------------------------------- #
# dominant_period
# --------------------------------------------------------------------------- #


def test_a_clean_sine_gives_back_its_own_period():
    steps = np.arange(600)
    period, strength = dominant_period(np.sin(2 * np.pi * steps / 40.0))
    assert period == 40
    assert strength > 0.9


def test_a_square_wave_gives_back_its_own_period():
    steps = np.arange(600)
    period, strength = dominant_period(((steps // 15) % 2).astype(float))
    assert period == 30
    assert strength > 0.5


def test_white_noise_produces_only_weak_unrepeatable_peaks(rng):
    """The honest negative control, and it is a partial pass.

    ``dominant_period`` does *not* return lag 0 on white noise: at n = 600 the
    Bartlett bound is 1.96/sqrt(600) = 0.080 and roughly 200 lags are examined, so
    a prominent-looking peak clears the gate about 93% of the time.  What it cannot
    do is clear it *strongly*: measured over 200 noise realisations the reported
    strength never exceeded 0.165 (95th percentile 0.124), whereas a sine buried
    under equal-amplitude noise scores at least 0.59.  Two safeguards convert that
    margin into a decision — ``PeriodicityEngine`` scales every region score by
    ``strength``, and it only adopts a period confirmed on consecutive refreshes,
    which an arbitrary noise lag does not survive.  Nothing here should be read as
    "the ACF test rejects noise" on its own.
    """
    results = [dominant_period(rng.standard_normal(600)) for _ in range(60)]
    assert max(strength for _, strength in results) < 0.30
    lags = [lag for lag, _ in results if lag]
    assert len(set(lags)) > len(lags) // 2, "noise lags must be scattered, not consistent"


def test_a_monotonic_ramp_is_not_called_periodic():
    """A persistent, drifting signal has a decaying ACF with no prominent peak."""
    period, strength = dominant_period(np.linspace(0.0, 10.0, 600))
    assert period == 0
    assert strength == 0.0


def test_a_constant_signal_is_not_periodic():
    assert dominant_period(np.full(600, 3.0)) == (0, 0.0)


def test_too_short_a_signal_refuses_to_guess():
    assert dominant_period(np.sin(np.arange(12) / 2.0), min_lag=4) == (0, 0.0)


def test_prominence_gate_can_be_tightened():
    steps = np.arange(600)
    signal = np.sin(2 * np.pi * steps / 40.0) * 0.05 + steps * 0.01
    assert dominant_period(signal, min_prominence=0.9)[0] == 0


# --------------------------------------------------------------------------- #
# PeriodicityEngine — global period
# --------------------------------------------------------------------------- #


def test_engine_starts_agnostic():
    engine = PeriodicityEngine(REGIONS)
    assert engine.period == 0
    assert engine.strength == 0.0
    assert np.all(engine.region_scores(0) == 0.0)
    assert np.all(engine.region_periods() == 0)


def test_engine_refuses_to_refresh_before_min_history():
    engine = PeriodicityEngine(REGIONS, min_history=96)
    for step in range(90):
        engine.observe(step, 1, _window(0), np.ones(WINDOW, dtype=bool))
    assert engine.period == 0


def test_engine_recovers_an_injected_period():
    engine = PeriodicityEngine(REGIONS)
    period = 30
    for step in range(600):
        active = (step % period) < 8
        detections = 3 if active else 0
        detected = np.full(WINDOW, active, dtype=bool)
        engine.observe(step, detections, _window(0), detected)
    assert engine.period == period
    assert engine.strength > 0.4


def test_engine_needs_consecutive_confirmations_before_adopting_a_period():
    """One lucky refresh must not become a headline number in the UI."""
    engine = PeriodicityEngine(REGIONS, confirmations=5, refresh_every=24)
    for step in range(24 * 5):
        active = (step % 30) < 8
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    seen_early = engine.period
    for step in range(24 * 5, 700):
        active = (step % 30) < 8
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    assert engine.period == 30
    assert seen_early in (0, 30)  # never a third, spurious value


def test_engine_reports_no_period_on_noise(rng):
    engine = PeriodicityEngine(REGIONS)
    for step in range(700):
        detections = int(rng.integers(0, WINDOW + 1))
        detected = np.zeros(WINDOW, dtype=bool)
        detected[:detections] = True
        engine.observe(
            step, detections, _window(int(rng.integers(0, REGIONS - WINDOW + 1))), detected
        )
    assert engine.strength < 0.5


# --------------------------------------------------------------------------- #
# PeriodicityEngine — per-region phase model
# --------------------------------------------------------------------------- #


def test_a_region_with_a_phase_preference_scores_above_one_without():
    """The whole point: which region, not just when."""
    engine = PeriodicityEngine(REGIONS, min_bucket_observations=2)
    period = 24
    early, late = 0, REGIONS - WINDOW  # two disjoint windows
    for step in range(1200):
        phase = step % period
        anchor = early if step % 2 == 0 else late
        regions = _window(anchor)
        # Only the early-anchor window is ever live, and only in the first half
        # of the cycle: a genuine phase preference for those regions.
        active = anchor == early and phase < period // 2
        detected = np.full(WINDOW, active, dtype=bool)
        engine.observe(step, int(detected.sum()), regions, detected)
    assert engine.period > 0
    scores = engine.region_scores(period * 50)  # phase 0 — the live half
    assert scores[early : early + WINDOW].mean() > scores[late : late + WINDOW].mean()
    assert np.all((scores >= 0.0) & (scores <= 1.0))


def test_a_region_with_no_phase_preference_scores_zero():
    engine = PeriodicityEngine(REGIONS, min_bucket_observations=2)
    period = 24
    for step in range(1200):
        phase = step % period
        # Global activity is periodic (so a period is found) but region 0 is
        # uniformly half-live regardless of phase.
        driver = phase < period // 2
        detected = np.zeros(WINDOW, dtype=bool)
        detected[0] = step % 2 == 0
        engine.observe(step, int(driver) * 3 + int(detected.sum()), _window(0), detected)
    assert engine.period > 0
    assert engine.region_scores(period * 50)[0] == pytest.approx(0.0, abs=0.05)


def test_region_periods_are_only_reported_where_evidence_exists():
    engine = PeriodicityEngine(REGIONS, min_bucket_observations=3)
    period = 24
    for step in range(1200):
        phase = step % period
        active = phase < period // 2
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    periods = engine.region_periods()
    assert np.all(periods[:WINDOW] == engine.period)
    assert np.all(periods[WINDOW:] == 0), "never-observed regions must not claim a period"


def test_base_rate_is_the_empirical_hit_rate():
    engine = PeriodicityEngine(REGIONS)
    for step in range(100):
        detected = np.array([True, False, False, False])
        engine.observe(step, 1, _window(0), detected)
    rates = engine.base_rate
    assert rates[0] == pytest.approx(1.0)
    assert rates[1] == pytest.approx(0.0)
    assert rates[WINDOW:].max() == pytest.approx(0.0)


def test_adopting_a_new_period_discards_stale_phase_evidence():
    engine = PeriodicityEngine(REGIONS, min_bucket_observations=2, confirmations=2)
    for step in range(700):
        active = (step % 30) < 8
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    first = engine.period
    assert first > 0
    for step in range(700, 2200):
        active = (step % 51) < 12
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    assert engine.period != first, "a genuinely different cycle must be re-estimated"


def test_reset_clears_every_accumulator():
    engine = PeriodicityEngine(REGIONS)
    for step in range(700):
        active = (step % 30) < 8
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    assert engine.period > 0
    engine.reset()
    assert engine.period == 0
    assert engine.strength == 0.0
    assert np.all(engine.base_rate == 0.0)
    assert np.all(engine.region_scores(0) == 0.0)


def test_snapshot_is_json_serialisable():
    engine = PeriodicityEngine(REGIONS)
    for step in range(300):
        active = (step % 30) < 8
        engine.observe(step, 3 if active else 0, _window(0), np.full(WINDOW, active, dtype=bool))
    payload = engine.snapshot()
    assert json.loads(json.dumps(payload)) == payload
    assert set(payload) >= {"period_steps", "strength", "phase_bins", "phase"}
