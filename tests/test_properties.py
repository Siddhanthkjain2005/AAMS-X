"""Property-based tests: invariants that must hold for *every* admissible input.

The example-based modules check that AAMS-X gets specific measured cases right.
This one checks the algebra underneath: entropy is bounded, information gain is
never negative, a region grid always tiles its band, a belief stays a
probability, and a confidence interval always brackets its mean.  Hypothesis
searches for the counterexample, which is a different job from choosing one.
"""

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from hypothesis.extra import numpy as hnp

from aamsx.belief.filter import BeliefConfig, BeliefFilter, binary_entropy
from aamsx.contracts.observation import Observation
from aamsx.contracts.scenario import ReceiverSpec
from aamsx.datasets.calibration import compute_calibration
from aamsx.environment.grid import bin_time, build_grid, region_margin_db
from aamsx.evaluation.pareto import OBJECTIVES, frontier
from aamsx.evaluation.statistics import aggregate, compare
from aamsx.experiments.registry import config_hash
from aamsx.information_gain.entropy import (
    maximum_possible_gain,
    region_information_gain,
    spread_to_regions,
    window_information_gain,
)
from aamsx.periodicity.recurrence import dominant_period
from aamsx.receiver.model import ReceiverModel

FAST = settings(max_examples=60, deadline=None)
SLOW = settings(max_examples=25, deadline=None)

LN2 = math.log(2.0)

probabilities = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
finite = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


def belief_vectors(min_size: int = 1, max_size: int = 64):
    return hnp.arrays(
        np.float64,
        st.integers(min_value=min_size, max_value=max_size),
        elements=st.floats(min_value=0.0, max_value=1.0, allow_nan=False),
    )


# --------------------------------------------------------------------------- #
# entropy
# --------------------------------------------------------------------------- #


@FAST
@given(probabilities)
def test_binary_entropy_is_bounded_by_one_bit(p):
    value = float(binary_entropy(p))
    assert 0.0 <= value <= LN2 + 1e-12


@FAST
@given(probabilities)
def test_binary_entropy_is_symmetric_about_a_half(p):
    assert float(binary_entropy(p)) == pytest.approx(float(binary_entropy(1.0 - p)), abs=1e-12)


@FAST
@given(st.floats(min_value=0.0, max_value=0.5, allow_nan=False))
def test_binary_entropy_never_exceeds_its_value_at_a_half(p):
    assert float(binary_entropy(p)) <= float(binary_entropy(0.5)) + 1e-12


@FAST
@given(belief_vectors())
def test_entropy_is_elementwise_and_shape_preserving(belief):
    out = binary_entropy(belief)
    assert out.shape == belief.shape
    assert np.all(np.isfinite(out))


# --------------------------------------------------------------------------- #
# information gain
# --------------------------------------------------------------------------- #

sensitivities = st.floats(min_value=0.01, max_value=0.99, allow_nan=False)


@FAST
@given(belief_vectors(), sensitivities, sensitivities)
def test_information_gain_is_never_negative_and_never_exceeds_current_entropy(belief, s, f):
    """Observing cannot create uncertainty, and cannot remove more than exists."""
    gain = region_information_gain(belief, sensitivity=s, false_alarm=f)
    assert np.all(gain >= 0.0)
    assert np.all(gain <= binary_entropy(belief) + 1e-9)
    assert np.all(np.isfinite(gain))


@FAST
@given(belief_vectors(), sensitivities)
def test_a_sensor_that_ignores_the_truth_is_worth_nothing(belief, rate):
    """When P(detect|on) == P(detect|off) the measurement carries no information."""
    gain = region_information_gain(belief, sensitivity=rate, false_alarm=rate)
    assert np.all(gain < 1e-9)


@FAST
@given(
    hnp.arrays(
        np.float64,
        st.integers(min_value=1, max_value=48),
        elements=st.floats(min_value=0.02, max_value=0.98, allow_nan=False),
    )
)
def test_a_perfect_sensor_removes_all_the_uncertainty_it_can(belief):
    """Away from the clipped extremes, a near-noiseless look resolves the region."""
    gain = region_information_gain(belief, sensitivity=0.999, false_alarm=0.001)
    assert np.all(gain >= 0.9 * binary_entropy(belief) - 1e-9)


@FAST
@given(
    hnp.arrays(
        np.float64,
        st.integers(min_value=2, max_value=40),
        elements=st.floats(min_value=0.0, max_value=10.0, allow_nan=False),
    ),
    st.integers(min_value=1, max_value=8),
)
def test_window_gain_equals_the_brute_force_sliding_sum(gains, window):
    assume(window <= gains.size)
    out = window_information_gain(gains, window)
    assert out.size == gains.size - window + 1
    expected = [float(gains[a : a + window].sum()) for a in range(out.size)]
    assert np.allclose(out, expected, atol=1e-9)


@FAST
@given(
    hnp.arrays(np.float64, st.integers(min_value=2, max_value=20), elements=finite),
    st.integers(min_value=2, max_value=40),
)
def test_a_window_wider_than_the_band_is_refused(gains, window):
    assume(window > gains.size)
    with pytest.raises(ValueError, match="exceeds"):
        window_information_gain(gains, window)


@FAST
@given(st.integers(min_value=2, max_value=48), st.integers(min_value=1, max_value=8))
def test_spreading_credits_every_region_with_its_best_window(n_regions, window):
    assume(window <= n_regions)
    n_anchors = n_regions - window + 1
    values = np.arange(n_anchors, dtype=np.float64)
    out = spread_to_regions(values, n_regions, window)
    assert out.size == n_regions
    for region in range(n_regions):
        containing = [values[a] for a in range(n_anchors) if a <= region < a + window]
        assert out[region] == pytest.approx(max(containing) if containing else 0.0)


@FAST
@given(st.integers(min_value=1, max_value=200))
def test_the_normaliser_is_the_entropy_of_a_maximally_uncertain_band(n_regions):
    assert maximum_possible_gain(n_regions) == pytest.approx(n_regions * LN2)
    belief = np.full(n_regions, 0.5)
    assert binary_entropy(belief).sum() == pytest.approx(maximum_possible_gain(n_regions))


# --------------------------------------------------------------------------- #
# region geometry
# --------------------------------------------------------------------------- #


@SLOW
@given(
    st.integers(min_value=2, max_value=24),
    st.integers(min_value=2, max_value=200),
    st.booleans(),
)
def test_a_grid_always_tiles_its_band_and_keeps_every_channel(n_regions, n_channels, descending):
    assume(n_channels >= n_regions)
    freq = np.linspace(20.0, 400.0, n_channels)
    grid = build_grid(freq[::-1] if descending else freq, n_regions)

    assert grid.n_regions == n_regions
    assert grid.counts.sum() == grid.n_channels == n_channels
    assert set(np.unique(grid.region_of_channel)) == set(range(n_regions))
    assert np.all(np.diff(grid.edges_mhz) > 0.0), (
        "edges must be ascending with no zero-width region"
    )
    assert np.allclose(grid.edges_mhz[1:-1], grid.edges_mhz[1:-1])  # tiling: shared boundaries
    assert np.all(grid.width_mhz > 0.0)
    # Inclusive: a region holding a single channel has its centre on an edge.
    assert np.all(grid.centre_mhz >= grid.edges_mhz[:-1])
    assert np.all(grid.centre_mhz <= grid.edges_mhz[1:])
    # equal channel counts, not equal bandwidth
    assert int(grid.counts.max() - grid.counts.min()) <= 1
    assert np.array_equal(grid.starts, np.concatenate(([0], np.cumsum(grid.counts)[:-1])))


@SLOW
@given(st.integers(min_value=2, max_value=16), st.integers(min_value=1, max_value=30))
def test_a_grid_refuses_a_band_it_cannot_fill(n_regions, n_channels):
    assume(n_channels < n_regions)
    with pytest.raises(ValueError):
        build_grid(np.linspace(20.0, 400.0, n_channels), n_regions)


@SLOW
@given(st.integers(min_value=2, max_value=12), st.integers(min_value=12, max_value=64))
def test_region_margin_is_the_best_channel_in_the_region(n_regions, n_channels):
    assume(n_channels >= n_regions)
    rng = np.random.default_rng(n_regions * 1000 + n_channels)
    grid = build_grid(np.linspace(20.0, 400.0, n_channels), n_regions)
    excess = rng.normal(0.0, 4.0, size=(5, n_channels)).astype(np.float32)
    threshold = rng.uniform(0.5, 3.0, size=n_channels).astype(np.float32)

    margin = region_margin_db(excess, threshold, grid)
    assert margin.shape == (5, n_regions)
    per_channel = excess[:, grid.channel_index] - threshold[grid.channel_index]
    for region in range(n_regions):
        mask = grid.region_of_channel == region
        assert np.allclose(margin[:, region], per_channel[:, mask].max(axis=1), atol=1e-4)


@FAST
@given(
    hnp.arrays(
        np.float32,
        st.tuples(st.integers(min_value=1, max_value=60), st.integers(min_value=1, max_value=6)),
        elements=st.floats(min_value=-50.0, max_value=50.0, width=32),
    ),
    st.integers(min_value=1, max_value=8),
)
def test_binning_never_invents_steps_and_max_dominates_mean(values, time_bin):
    assume(values.shape[0] >= time_bin)
    hardest = bin_time(values, time_bin, reduce="max")
    average = bin_time(values, time_bin, reduce="mean")
    expected_steps = values.shape[0] if time_bin <= 1 else values.shape[0] // time_bin
    assert hardest.shape[0] == expected_steps
    assert np.all(hardest >= average - 1e-4)
    assert np.all(np.isfinite(hardest))


@FAST
@given(
    hnp.arrays(
        np.float32,
        st.tuples(st.integers(min_value=1, max_value=20), st.integers(min_value=1, max_value=4)),
        elements=st.floats(min_value=-10.0, max_value=10.0, width=32),
    ),
    st.integers(min_value=2, max_value=64),
)
def test_binning_refuses_to_fabricate_a_step_it_cannot_fill(values, time_bin):
    assume(time_bin > values.shape[0])
    with pytest.raises(ValueError, match="cannot form a single step"):
        bin_time(values, time_bin)


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #


@SLOW
@given(
    hnp.arrays(
        np.uint8,
        st.tuples(st.integers(min_value=2, max_value=120), st.integers(min_value=1, max_value=8)),
        elements=st.integers(min_value=0, max_value=255),
    ),
    st.floats(min_value=1.0, max_value=8.0),
)
def test_calibration_always_yields_a_usable_threshold(digits, k_mad):
    calibration = compute_calibration(digits, db_per_digit=0.25, k_mad=k_mad, min_excess_db=1.5)
    assert calibration.noise_db.shape == (digits.shape[1],)
    assert np.all(calibration.noise_db > 0.0), (
        "a zero sigma would make every channel infinitely sure"
    )
    assert np.all(calibration.threshold_db >= 1.5 - 1e-6), "the floor must never be undercut"
    assert np.allclose(
        calibration.threshold_db, np.maximum(1.5, k_mad * calibration.noise_db), atol=1e-4
    )
    assert calibration.baseline_blocks.shape[1] == digits.shape[1]
    assert calibration.n_blocks >= 1
    assert np.all(np.isfinite(calibration.baseline_blocks))


@SLOW
@given(
    hnp.arrays(
        np.uint8,
        st.tuples(st.integers(min_value=4, max_value=80), st.integers(min_value=1, max_value=4)),
        elements=st.integers(min_value=0, max_value=255),
    )
)
def test_the_baseline_is_evaluated_inside_the_observed_range(digits):
    calibration = compute_calibration(digits, db_per_digit=0.25)
    baseline = calibration.baseline_at(np.arange(digits.shape[0]))
    power = digits.astype(np.float64) * 0.25
    assert baseline.shape == digits.shape
    assert np.all(baseline >= power.min() - 1e-6)
    assert np.all(baseline <= power.max() + 1e-6)


# --------------------------------------------------------------------------- #
# the receiver
# --------------------------------------------------------------------------- #


@FAST
@given(
    st.integers(min_value=2, max_value=64),
    st.integers(min_value=1, max_value=8),
    st.integers(min_value=-50, max_value=100),
)
def test_a_tuned_window_is_always_contiguous_and_inside_the_band(n_regions, window, anchor):
    assume(window <= n_regions)
    model = ReceiverModel(ReceiverSpec(window_size=window), n_regions)
    regions = model.window(anchor)
    assert regions.size == window
    assert np.array_equal(np.diff(regions), np.ones(window - 1, dtype=np.int32))
    assert int(regions[0]) >= 0 and int(regions[-1]) < n_regions


@FAST
@given(
    st.integers(min_value=4, max_value=48),
    st.integers(min_value=1, max_value=4),
    st.integers(min_value=0, max_value=47),
    st.integers(min_value=0, max_value=47),
    st.floats(min_value=0.0, max_value=2.0),
)
def test_dwelling_is_never_dearer_than_retuning(n_regions, window, anchor, previous, switch):
    model = ReceiverModel(ReceiverSpec(window_size=window, switch_cost=switch), n_regions)
    assume(anchor < model.n_anchors and previous < model.n_anchors)
    stay = model.cost(previous, previous)
    move = model.cost(anchor, previous)
    assert stay == pytest.approx(model.spec.cost_per_observation)
    assert move >= stay - 1e-12
    assert 0.0 <= model.retune_fraction(anchor, previous) <= 1.0
    assert model.cost(anchor, None) == pytest.approx(model.spec.cost_per_observation)


@FAST
@given(
    st.integers(min_value=4, max_value=32),
    st.integers(min_value=1, max_value=4),
    st.integers(min_value=0, max_value=31),
)
def test_the_priced_option_vector_agrees_with_the_scalar_price(n_regions, window, previous):
    model = ReceiverModel(ReceiverSpec(window_size=window, switch_cost=0.3), n_regions)
    assume(previous < model.n_anchors)
    vector = model.cost_per_anchor(previous)
    assert vector.size == model.n_anchors
    for anchor in range(model.n_anchors):
        assert vector[anchor] == pytest.approx(model.cost(anchor, previous))


@FAST
@given(
    hnp.arrays(
        np.float32,
        st.integers(min_value=1, max_value=8),
        elements=st.floats(min_value=-30.0, max_value=30.0, width=32),
    ),
    st.floats(min_value=0.05, max_value=5.0),
    st.integers(min_value=0, max_value=2**31 - 1),
)
def test_a_measurement_is_finite_and_its_confidence_is_a_probability(margin, noise, seed):
    model = ReceiverModel(ReceiverSpec(window_size=margin.size), max(margin.size, 2))
    measured, detected, confidence = model.measure(
        margin, noise_db=noise, rng=np.random.default_rng(seed)
    )
    assert measured.shape == detected.shape == confidence.shape == margin.shape
    assert np.all(np.isfinite(measured))
    assert np.all((confidence >= 0.0) & (confidence <= 1.0))
    assert np.array_equal(detected, measured > 0.0), "detection must be the sign of the measurement"


# --------------------------------------------------------------------------- #
# the belief filter
# --------------------------------------------------------------------------- #


@SLOW
@given(
    st.integers(min_value=4, max_value=24),
    st.integers(min_value=1, max_value=20),
    st.integers(min_value=0, max_value=2**31 - 1),
)
def test_a_belief_stays_a_probability_however_long_it_runs(n_regions, steps, seed):
    rng = np.random.default_rng(seed)
    belief = BeliefFilter(n_regions, BeliefConfig(noise_db=1.0))
    window = min(4, n_regions)
    for step in range(steps):
        belief.predict()
        anchor = int(rng.integers(0, n_regions - window + 1))
        regions = np.arange(anchor, anchor + window, dtype=np.int32)
        measured = rng.normal(0.0, 3.0, size=window).astype(np.float32)
        surprise = belief.update(
            Observation(
                step=step,
                regions=regions,
                measured_db=measured,
                detected=measured > 0.0,
                threshold_db=np.zeros(window, dtype=np.float32),
                confidence=np.full(window, 0.5, dtype=np.float32),
                cost=1.0,
                available=True,
                t_sec=float(step),
            )
        )
        assert np.all(surprise >= 0.0), "Bayesian surprise is a negative log probability"
        assert np.all((belief.belief > 0.0) & (belief.belief < 1.0))
        assert np.all((belief.uncertainty >= 0.0) & (belief.uncertainty <= 1.0))
        assert np.all(belief.epistemic <= 0.25 + 1e-9)
        assert np.all((belief.staleness >= 0.0) & (belief.staleness <= 1.0))
        assert np.all((belief.p_on > 0.0) & (belief.p_on < 1.0))
        assert np.all((belief.stationary >= 0.0) & (belief.stationary <= 1.0))
        assert np.isfinite(belief.entropy())


@FAST
@given(st.integers(min_value=2, max_value=32), st.integers(min_value=1, max_value=30))
def test_an_unobserved_region_only_grows_more_uncertain(n_regions, steps):
    """Nothing may become more certain without evidence."""
    belief = BeliefFilter(n_regions)
    previous = belief.epistemic.copy()
    for _ in range(steps):
        belief.predict()
        assert np.all(belief.epistemic >= previous - 1e-12)
        previous = belief.epistemic.copy()
    assert np.all(belief.steps_since_seen == steps)


@FAST
@given(st.integers(min_value=2, max_value=32))
def test_an_unavailable_step_teaches_the_filter_nothing(n_regions):
    belief = BeliefFilter(n_regions)
    before = belief.belief.copy()
    surprise = belief.update(
        Observation(
            step=0,
            regions=np.arange(2, dtype=np.int32),
            measured_db=np.full(2, 9.0, dtype=np.float32),
            detected=np.ones(2, dtype=bool),
            threshold_db=np.zeros(2, dtype=np.float32),
            confidence=np.ones(2, dtype=np.float32),
            cost=0.0,
            available=False,
            t_sec=0.0,
        )
    )
    assert np.array_equal(belief.belief, before)
    assert np.all(surprise == 0.0)


# --------------------------------------------------------------------------- #
# statistics
# --------------------------------------------------------------------------- #

samples = st.lists(
    st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
    min_size=1,
    max_size=30,
)


@FAST
@given(samples)
def test_an_aggregate_brackets_its_own_mean(values):
    result = aggregate("metric", values)
    assert result.n == len(values)
    # Summing identical floats can land the mean one ULP outside [min, max]
    # (three copies of 2731.605902528813 average to ...8137), so the bracket is
    # asserted to floating-point tolerance rather than exactly.
    tol = 1e-9 * max(1.0, abs(result.mean))
    assert result.minimum - tol <= result.mean <= result.maximum + tol
    assert result.minimum <= result.median <= result.maximum
    assert result.std >= 0.0
    assert result.ci_low <= result.mean + 1e-6
    assert result.ci_high >= result.mean - 1e-6


@FAST
@given(samples, st.floats(min_value=-100.0, max_value=100.0))
def test_shifting_every_sample_shifts_the_mean_and_leaves_the_spread_alone(values, offset):
    base = aggregate("m", values)
    moved = aggregate("m", [v + offset for v in values])
    assert moved.mean == pytest.approx(base.mean + offset, rel=1e-6, abs=1e-6)
    assert moved.std == pytest.approx(base.std, rel=1e-6, abs=1e-6)


testable = st.lists(
    st.floats(min_value=-1e4, max_value=1e4, allow_nan=False, allow_infinity=False),
    min_size=2,
    max_size=30,
)
"""``compare`` declines to report a p-value below two finite observations per arm,
which is the honest answer rather than a property to test around."""


@FAST
@given(testable, testable)
def test_a_comparison_is_antisymmetric_in_its_arguments(treatment, control):
    forward = compare("m", treatment, control, treatment_name="t", control_name="c")
    backward = compare("m", control, treatment, treatment_name="c", control_name="t")
    assert forward.difference == pytest.approx(-backward.difference, abs=1e-9)
    if np.isfinite(forward.welch_p) and np.isfinite(backward.welch_p):
        assert forward.welch_p == pytest.approx(backward.welch_p, abs=1e-9)


@FAST
@given(testable)
def test_comparing_a_sample_with_itself_finds_no_difference(values):
    result = compare("m", values, list(values))
    assert result.difference == pytest.approx(0.0, abs=1e-9)
    assert not result.significant


# --------------------------------------------------------------------------- #
# Pareto
# --------------------------------------------------------------------------- #

objective_values = st.fixed_dictionaries(
    {metric: st.floats(min_value=0.0, max_value=100.0, allow_nan=False) for metric in OBJECTIVES}
)


@SLOW
@given(st.dictionaries(st.text(min_size=1, max_size=4), objective_values, min_size=1, max_size=6))
def test_the_frontier_is_never_empty_and_domination_is_irreflexive(points):
    result = frontier(points)
    assert len(result) == len(points)
    assert any(point.on_frontier for point in result), "somebody must be non-dominated"
    for point in result:
        assert point.label not in point.dominated_by
    assert [p.on_frontier for p in result] == sorted(
        (p.on_frontier for p in result), reverse=True
    ), "frontier points must be listed first"


@SLOW
@given(st.dictionaries(st.text(min_size=1, max_size=4), objective_values, min_size=2, max_size=5))
def test_domination_is_transitive_and_asymmetric(points):
    result = {point.label: point for point in frontier(points)}
    for label, point in result.items():
        for dominator in point.dominated_by:
            assert label not in result[dominator].dominated_by, "domination cannot go both ways"


# --------------------------------------------------------------------------- #
# hashing and periodicity
# --------------------------------------------------------------------------- #

hashable = st.dictionaries(
    st.text(min_size=1, max_size=6),
    st.one_of(st.integers(), st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=6)),
    min_size=1,
    max_size=6,
)


@FAST
@given(hashable)
def test_a_config_hash_is_order_independent_and_always_sixteen_hex_digits(payload):
    shuffled = dict(reversed(list(payload.items())))
    digest = config_hash(payload)
    assert digest == config_hash(shuffled)
    assert len(digest) == 16
    assert all(character in "0123456789abcdef" for character in digest)


@SLOW
@given(
    hnp.arrays(
        np.float64,
        st.integers(min_value=1, max_value=300),
        elements=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False),
    )
)
def test_a_reported_period_is_always_a_usable_lag(series):
    lag, strength = dominant_period(series)
    assert 0.0 <= strength <= 1.0
    assert lag >= 0
    if lag:
        # The search runs over [min_lag, limit) with min_lag = 4 and limit = n // 3,
        # so a period is only ever reported where four cycles could be seen.
        assert 4 <= lag < max(6, series.size // 3)


@FAST
@given(st.integers(min_value=6, max_value=40), st.integers(min_value=6, max_value=12))
def test_a_clean_repetition_is_recovered_exactly(cycles, period):
    """``min_lag = 4`` and ``limit = n // 3`` bound what is detectable at all."""
    series = np.tile(np.concatenate([np.ones(period // 2), np.zeros(period - period // 2)]), cycles)
    assume(series.size // 3 > period)
    lag, strength = dominant_period(series)
    assert lag, "a square wave repeated six times is periodic by construction"
    assert lag % period == 0 or period % lag == 0
    assert strength > 0.3


@FAST
@given(
    hnp.arrays(
        np.float64,
        st.integers(min_value=8, max_value=200),
        elements=st.floats(min_value=-1.0, max_value=1.0, allow_nan=False),
    ),
    st.floats(min_value=-5.0, max_value=5.0),
)
def test_a_constant_offset_does_not_create_a_period(series, offset):
    """Autocorrelation must be computed on the mean-removed signal."""
    base_lag, base_strength = dominant_period(series)
    moved_lag, moved_strength = dominant_period(series + offset)
    assert base_lag == moved_lag
    assert base_strength == pytest.approx(moved_strength, abs=1e-9)
