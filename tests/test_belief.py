"""Belief filter: does the posterior behave like a posterior?"""

from __future__ import annotations

import numpy as np

from aamsx.belief.filter import BeliefConfig, BeliefFilter, binary_entropy
from aamsx.contracts.observation import Observation


def _observation(step: int, regions: np.ndarray, measured_db: np.ndarray) -> Observation:
    measured = np.asarray(measured_db, dtype=np.float32)
    return Observation(
        step=step,
        regions=np.asarray(regions, dtype=np.int32),
        measured_db=measured,
        detected=measured > 0.0,
        threshold_db=np.zeros(measured.size, dtype=np.float32),
        confidence=np.clip(np.abs(measured) / 6.0, 0.0, 1.0).astype(np.float32),
        cost=1.0,
        available=True,
        t_sec=float(step),
    )


def test_binary_entropy_is_maximal_at_one_half():
    assert binary_entropy(0.5) == np.log(2.0)
    assert binary_entropy(0.5) > binary_entropy(0.1)
    assert binary_entropy(0.5) > binary_entropy(0.9)
    assert binary_entropy(0.0) < 1e-6
    assert binary_entropy(1.0) < 1e-6


def test_prior_is_uniform_before_any_evidence():
    f = BeliefFilter(12, BeliefConfig(prior_activity=0.2))
    assert np.allclose(f.belief, 0.2)
    assert np.allclose(f.observation_counts, 0)
    assert np.allclose(f.staleness, 0.0)


def test_strong_positive_measurement_raises_belief_weak_one_barely_moves():
    f = BeliefFilter(8, BeliefConfig(prior_activity=0.15, noise_db=1.0))
    before = f.belief[2]
    f.update(_observation(0, [2], [9.0]))
    decisive = f.belief[2]

    g = BeliefFilter(8, BeliefConfig(prior_activity=0.15, noise_db=1.0))
    g.update(_observation(0, [2], [0.15]))
    marginal = g.belief[2]

    assert decisive > 0.95
    assert before < marginal < decisive
    # Confidence has to be earned by the measurement, not by the detection flag.
    assert marginal - before < 0.5 * (decisive - before)


def test_negative_measurement_lowers_belief():
    f = BeliefFilter(8, BeliefConfig(prior_activity=0.5, noise_db=1.0))
    f.update(_observation(0, [3], [-9.0]))
    assert f.belief[3] < 0.05


def test_observing_reduces_entropy_and_resets_staleness():
    f = BeliefFilter(24, BeliefConfig(prior_activity=0.5))
    before = f.entropy()
    for step in range(6):
        f.predict()
        f.update(_observation(step, [0, 1, 2, 3], [8.0, 8.0, -8.0, -8.0]))
    assert f.entropy() < before
    assert np.all(f.steps_since_seen[[0, 1, 2, 3]] == 0)
    assert np.all(f.steps_since_seen[8:] == 6)


def test_unobserved_regions_decay_toward_their_stationary_rate():
    f = BeliefFilter(6, BeliefConfig(prior_activity=0.5))
    # Teach region 0 that it is usually active, then stop looking at it.
    for step in range(40):
        f.predict()
        f.update(_observation(step, [0], [7.0]))
    high = f.belief[0]
    stationary = f.stationary[0]
    for _ in range(500):
        f.predict()
    assert abs(f.belief[0] - stationary) < abs(high - stationary)
    assert abs(f.belief[0] - stationary) < 0.02


def test_staleness_and_epistemic_uncertainty_grow_without_observation():
    f = BeliefFilter(10)
    f.update(_observation(0, [4], [5.0]))
    assert f.epistemic[4] == 0.0
    for _ in range(50):
        f.predict()
    assert f.staleness[4] > 0.9
    assert f.epistemic[4] > 0.0
    assert 0.0 <= f.uncertainty[4] <= 1.0


def test_uncertainty_splits_into_aleatoric_and_epistemic():
    f = BeliefFilter(10, BeliefConfig(prior_activity=0.5))
    for _ in range(20):
        f.predict()
    assert np.all(f.aleatoric >= 0.0) and np.all(f.aleatoric <= 1.0)
    assert np.all(f.epistemic_normalised >= 0.0)
    assert np.all(f.uncertainty <= 1.0)
    assert np.all(f.uncertainty >= f.aleatoric - 1e-9)


def test_transition_rates_are_learned_from_consecutive_posteriors():
    """A region that alternates on/off must learn high switching rates."""
    flip = BeliefFilter(4, BeliefConfig(prior_activity=0.5))
    for step in range(60):
        flip.predict()
        flip.update(_observation(step, [0], [8.0 if step % 2 == 0 else -8.0]))

    steady = BeliefFilter(4, BeliefConfig(prior_activity=0.5))
    for step in range(60):
        steady.predict()
        steady.update(_observation(step, [0], [8.0]))

    assert flip.p_off[0] > steady.p_off[0]
    assert flip.p_on[0] > 0.1


def test_unavailable_observation_is_a_no_op():
    f = BeliefFilter(5)
    obs = _observation(0, [1], [9.0])
    blank = Observation(
        step=0,
        regions=obs.regions,
        measured_db=obs.measured_db,
        detected=obs.detected,
        threshold_db=obs.threshold_db,
        confidence=obs.confidence,
        cost=0.0,
        available=False,
        t_sec=0.0,
    )
    before = f.belief.copy()
    surprise = f.update(blank)
    assert np.allclose(f.belief, before)
    assert np.allclose(surprise, 0.0)
    assert f.observation_counts.sum() == 0


def test_change_reaction_discounts_evidence_and_reinflates_uncertainty():
    f = BeliefFilter(6, BeliefConfig(prior_activity=0.5))
    for step in range(40):
        f.predict()
        f.update(_observation(step, [0, 1], [7.0, -7.0]))
    counts_before = f.on_alpha[0] + f.on_beta[0]
    f.on_change_detected()
    assert f.on_alpha[0] + f.on_beta[0] < counts_before
    assert np.all(~np.isfinite(f.last_state))


def test_surprise_is_larger_when_the_prior_was_wrong():
    f = BeliefFilter(4, BeliefConfig(prior_activity=0.05, noise_db=1.0))
    surprising = f.update(_observation(0, [0], [9.0]))
    g = BeliefFilter(4, BeliefConfig(prior_activity=0.95, noise_db=1.0))
    expected = g.update(_observation(0, [0], [9.0]))
    assert surprising[0] > expected[0]


def test_snapshot_is_json_safe():
    f = BeliefFilter(8)
    f.predict()
    f.update(_observation(0, [0, 1], [3.0, -3.0]))
    snap = f.snapshot()
    for key in ("belief", "uncertainty", "aleatoric", "epistemic"):
        assert len(snap[key]) == 8
        assert all(isinstance(v, float) for v in snap[key])
