"""The replay environment: real data in, partial observations out, budget enforced.

Every assertion here is about the *wall* between measured truth and what a
scheduler is allowed to see, plus the bookkeeping that makes an episode
reproducible.
"""

from __future__ import annotations

import numpy as np
import pytest

from aamsx.contracts.observation import Observation
from aamsx.contracts.scenario import ReceiverSpec
from aamsx.environment.replay import LeakageError, make_environment
from tests.conftest import requires_cache

pytestmark = requires_cache


def _episode(env, anchors) -> list:
    return [env.step(int(anchor)) for anchor in anchors]


def _sweep(env, steps: int) -> list:
    return _episode(env, [index % env.n_anchors for index in range(steps)])


def _dwell(env, steps: int) -> list:
    """Stay on one anchor, so every step costs exactly ``cost_per_observation``.

    Needed wherever a test has to reach the horizon: under the default budget of
    ``horizon x cost_per_observation`` there is no allowance for retuning, so a
    sweeping policy runs out of budget first (see
    ``test_the_default_budget_leaves_no_slack_for_retuning``).
    """
    return _episode(env, [0] * steps)


# --------------------------------------------------------------------------- #
# geometry and observation shape
# --------------------------------------------------------------------------- #


def test_environment_geometry_matches_the_scenario(short_spec):
    env = make_environment(short_spec, seed=1)
    assert env.n_regions == short_spec.n_regions
    assert env.window_size == short_spec.receiver.window_size
    assert env.n_anchors == short_spec.n_regions - short_spec.receiver.window_size + 1
    assert env.horizon <= short_spec.horizon


def test_an_observation_exposes_only_the_window_it_paid_for(short_spec):
    env = make_environment(short_spec, seed=1)
    outcome = env.step(3)
    observation = outcome.observation
    assert isinstance(observation, Observation)
    assert observation.window_size == env.window_size
    assert observation.regions.tolist() == [3, 4, 5, 6]
    for array in (observation.measured_db, observation.detected, observation.confidence):
        assert array.shape == (env.window_size,)
    assert outcome.true_occupied.shape == (env.window_size,)


def test_anchors_are_clamped_into_the_band(short_spec):
    env = make_environment(short_spec, seed=1)
    high = env.step(10_000).observation.regions
    assert high[-1] == short_spec.n_regions - 1
    env.reset()
    low = env.step(-10_000).observation.regions
    assert low[0] == 0


def test_confidence_is_a_unit_interval_and_hits_are_consistent(short_spec):
    env = make_environment(short_spec, seed=3)
    for outcome in _sweep(env, 60):
        observation = outcome.observation
        assert np.all((observation.confidence >= 0.0) & (observation.confidence <= 1.0))
        assert outcome.hits + outcome.false_alarms == int(observation.detected.sum())
        assert outcome.hits + outcome.missed_in_window == int(outcome.true_occupied.sum())
        assert outcome.occupied_total >= int(outcome.true_occupied.sum())


def test_the_oracle_is_at_least_as_good_as_any_actual_window(short_spec):
    env = make_environment(short_spec, seed=5)
    for outcome in _sweep(env, 80):
        assert outcome.oracle_best_count >= int(outcome.true_occupied.sum())
        assert outcome.oracle_best_count <= env.window_size


# --------------------------------------------------------------------------- #
# the observability wall
# --------------------------------------------------------------------------- #


def test_sealing_closes_every_truth_accessor(short_spec):
    env = make_environment(short_spec, seed=1)
    assert env.truth is not None  # readable by the evaluation layer
    with env.sealed():
        with pytest.raises(LeakageError, match="sealed"):
            _ = env.truth
        with pytest.raises(LeakageError, match="sealed"):
            env.oracle_best_count(0)
    assert env.truth is not None  # and reopened afterwards


def test_sealing_nests_without_reopening_early(short_spec):
    env = make_environment(short_spec, seed=1)
    with env.sealed():
        with env.sealed():
            pass
        with pytest.raises(LeakageError):
            _ = env.truth


def test_stepping_still_works_while_sealed(short_spec):
    """The seal hides truth from *readers*; the environment itself must still run."""
    env = make_environment(short_spec, seed=1)
    with env.sealed():
        outcome = env.step(0)
    assert outcome.observation.window_size == env.window_size


# --------------------------------------------------------------------------- #
# budget
# --------------------------------------------------------------------------- #


def test_default_budget_is_one_observation_per_step(short_spec):
    env = make_environment(short_spec, seed=1)
    assert env.budget == pytest.approx(
        short_spec.horizon * short_spec.receiver.cost_per_observation
    )


def test_spending_never_exceeds_the_declared_budget(short_spec):
    """The hard constraint: sum of costs <= B, enforced by the environment."""
    spec = short_spec.__class__(
        **{
            **{field: getattr(short_spec, field) for field in short_spec.__slots__},
            "budget": 25.0,
        }
    )
    env = make_environment(spec, seed=2)
    assert env.budget == pytest.approx(25.0)
    steps = 0
    while not env.done:
        env.step(steps % env.n_anchors)
        steps += 1
        assert env.budget_remaining >= 0.0
    assert env.budget_spent >= 25.0 - env.spec.receiver.cost_per_observation * 2
    assert steps < spec.horizon, "a tight budget must end the episode before the horizon"
    with pytest.raises(RuntimeError, match="finished"):
        env.step(0)


def test_retuning_costs_more_than_dwelling(short_spec):
    env = make_environment(short_spec, seed=1)
    env.step(0)
    before = env.budget_spent
    env.step(0)  # stay put
    stay = env.budget_spent - before
    env.reset()
    env.step(0)
    before = env.budget_spent
    env.step(env.n_anchors - 1)  # jump the whole band
    jump = env.budget_spent - before
    assert jump > stay
    assert stay == pytest.approx(short_spec.receiver.cost_per_observation)


def test_the_default_budget_leaves_no_slack_for_retuning(short_spec):
    """A measured consequence of the default, not a bug: switching is paid for.

    ``effective_budget`` defaults to ``horizon x cost_per_observation``, which buys
    exactly one dwell per step and nothing else.  Any policy that retunes therefore
    ends its episode before the nominal horizon, and the fraction it loses is the
    switching cost it chose to incur.  Scenarios that need the full horizon under a
    moving receiver set ``budget`` explicitly.
    """
    env = make_environment(short_spec, seed=1)
    steps = 0
    while not env.done:
        env.step(steps % env.n_anchors)
        steps += 1
    assert env.step_index < env.horizon
    assert env.budget_spent <= env.budget + short_spec.receiver.cost_per_observation


def test_a_switch_cost_of_zero_makes_every_step_cost_the_same(short_spec):
    spec = short_spec.__class__(
        **{
            **{field: getattr(short_spec, field) for field in short_spec.__slots__},
            "receiver": ReceiverSpec(window_size=4, switch_cost=0.0),
        }
    )
    env = make_environment(spec, seed=1)
    costs = {round(outcome.observation.cost, 6) for outcome in _sweep(env, 30)}
    assert costs == {1.0}


# --------------------------------------------------------------------------- #
# determinism and reset
# --------------------------------------------------------------------------- #


def test_the_same_seed_measures_the_same_noise(short_spec):
    anchors = [(index * 3) % 13 for index in range(60)]
    first = [
        o.observation.measured_db.copy()
        for o in _episode(make_environment(short_spec, seed=7), anchors)
    ]
    second = [
        o.observation.measured_db.copy()
        for o in _episode(make_environment(short_spec, seed=7), anchors)
    ]
    for left, right in zip(first, second, strict=True):
        assert np.array_equal(left, right)


def test_a_different_seed_measures_different_noise(short_spec):
    anchors = [(index * 3) % 13 for index in range(60)]
    first = np.concatenate(
        [o.observation.measured_db for o in _episode(make_environment(short_spec, seed=7), anchors)]
    )
    second = np.concatenate(
        [o.observation.measured_db for o in _episode(make_environment(short_spec, seed=8), anchors)]
    )
    assert not np.array_equal(first, second)


def test_the_underlying_truth_does_not_depend_on_the_seed(short_spec):
    """Noise is seeded; the measurements themselves are archival and fixed."""
    anchors = [(index * 3) % 13 for index in range(60)]
    first = np.concatenate(
        [o.true_margin_db for o in _episode(make_environment(short_spec, seed=7), anchors)]
    )
    second = np.concatenate(
        [o.true_margin_db for o in _episode(make_environment(short_spec, seed=99), anchors)]
    )
    assert np.array_equal(first, second)


def test_reset_rewinds_the_episode_exactly(short_spec):
    env = make_environment(short_spec, seed=11)
    first = [o.observation.measured_db.copy() for o in _sweep(env, 40)]
    env.reset()
    assert env.step_index == 0
    assert env.budget_spent == 0.0
    assert env.previous_anchor is None
    second = [o.observation.measured_db.copy() for o in _sweep(env, 40)]
    for left, right in zip(first, second, strict=True):
        assert np.array_equal(left, right)


def test_an_episode_runs_to_its_horizon_and_then_stops(short_spec):
    env = make_environment(short_spec, seed=1)
    horizon = env.horizon
    _dwell(env, horizon)
    assert env.done
    with pytest.raises(RuntimeError, match="finished"):
        env.step(0)


# --------------------------------------------------------------------------- #
# spliced scenarios
# --------------------------------------------------------------------------- #


def test_a_spliced_scenario_reports_its_segment_boundary(two_phase_spec):
    """The change point is known exactly because it is where one recording ends."""
    env = make_environment(two_phase_spec, seed=1)
    outcomes = _dwell(env, env.horizon)
    changed = [index for index, outcome in enumerate(outcomes) if outcome.changed_segment]
    assert changed == list(two_phase_spec.change_points)
    assert {outcome.segment_index for outcome in outcomes} == {0, 1}


def test_segments_come_from_genuinely_different_recordings(two_phase_spec):
    ids = {segment.recording_id for segment in two_phase_spec.segments}
    assert len(ids) == len(two_phase_spec.segments) >= 2


def test_a_mismatched_region_count_is_rejected(short_spec):
    from aamsx.environment.replay import ReplayEnvironment
    from aamsx.environment.truth import build_truth

    truth = build_truth(short_spec)
    wrong = short_spec.__class__(
        **{
            **{field: getattr(short_spec, field) for field in short_spec.__slots__},
            "n_regions": short_spec.n_regions + 1,
        }
    )
    with pytest.raises(ValueError, match="regions"):
        ReplayEnvironment(wrong, truth, seed=0)
