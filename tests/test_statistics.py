"""Multi-seed statistics and Pareto analysis.

The claim these tests defend is that AAMS-X never reports a single-episode number
as a result, and never calls a difference significant that a standard test does
not support.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from scipy import stats

from aamsx.evaluation.pareto import OBJECTIVES, describe, frontier
from aamsx.evaluation.statistics import (
    HEADLINE_METRICS,
    aggregate,
    compare,
    summarise_runs,
)

# --------------------------------------------------------------------------- #
# aggregate
# --------------------------------------------------------------------------- #


def test_aggregate_matches_hand_computed_moments():
    values = [1.0, 2.0, 3.0, 4.0]
    result = aggregate("reward", values)
    assert result.n == 4
    assert result.mean == pytest.approx(2.5)
    assert result.std == pytest.approx(np.std(values, ddof=1))
    assert result.sem == pytest.approx(np.std(values, ddof=1) / 2.0)
    assert result.median == pytest.approx(2.5)
    assert (result.minimum, result.maximum) == (1.0, 4.0)


def test_the_interval_uses_the_student_t_critical_value():
    """At five seeds the normal approximation is not good enough to publish."""
    values = [0.5, 0.6, 0.55, 0.7, 0.45]
    result = aggregate("sdp", values)
    half = stats.t.ppf(0.975, 4) * result.sem
    assert result.ci_high - result.mean == pytest.approx(half)
    normal_half = 1.96 * result.sem
    assert half > normal_half * 1.25  # ~30% wider, as the docstring claims


def test_the_interval_brackets_the_mean_and_widens_with_spread():
    tight = aggregate("m", [1.0, 1.01, 0.99, 1.0, 1.0])
    loose = aggregate("m", [0.0, 2.0, 1.0, -1.0, 3.0])
    assert tight.ci_low <= tight.mean <= tight.ci_high
    assert (loose.ci_high - loose.ci_low) > (tight.ci_high - tight.ci_low)


def test_a_single_seed_reports_a_zero_width_interval_not_a_fake_one():
    result = aggregate("m", [0.42])
    assert result.n == 1
    assert result.std == 0.0
    assert result.ci_low == result.ci_high == pytest.approx(0.42)


def test_no_seeds_reports_nan_rather_than_zero():
    result = aggregate("m", [])
    assert result.n == 0
    assert np.isnan(result.mean)
    assert result.values == ()


def test_non_finite_values_are_dropped_not_propagated():
    """A NaN delay from an episode that caught nothing must not poison the mean."""
    result = aggregate("delay", [1.0, float("nan"), 3.0, float("inf")])
    assert result.n == 2
    assert result.mean == pytest.approx(2.0)


def test_aggregate_dict_can_omit_the_raw_values():
    result = aggregate("m", [1.0, 2.0, 3.0])
    assert "values" in result.to_dict()
    assert "values" not in result.to_dict(include_values=False)
    assert json.loads(json.dumps(result.to_dict())) == result.to_dict()


# --------------------------------------------------------------------------- #
# compare
# --------------------------------------------------------------------------- #


def test_a_clear_separation_is_significant_under_both_tests():
    treatment = [10.0, 10.2, 9.8, 10.1, 10.3]
    control = [5.0, 5.1, 4.9, 5.2, 5.0]
    result = compare("reward", treatment, control, treatment_name="mag-nts", control_name="random")
    assert result.difference == pytest.approx(np.mean(treatment) - np.mean(control))
    assert result.relative == pytest.approx(1.0, abs=0.02)
    assert result.welch_p < 0.001
    assert result.mannwhitney_p < 0.05
    assert result.cohens_d > 3.0
    assert result.significant is True


def test_overlapping_samples_are_not_declared_significant(rng):
    same = rng.normal(loc=1.0, scale=1.0, size=8)
    other = rng.normal(loc=1.0, scale=1.0, size=8)
    result = compare("reward", same, other)
    assert result.welch_p > 0.05
    assert result.significant is False


def test_identical_samples_do_not_crash_the_rank_test():
    values = [1.0] * 6
    result = compare("m", values, values)
    assert result.difference == 0.0
    assert result.significant is False
    # scipy returns a statistic but a NaN p-value for two identical samples;
    # what matters is that nothing raises and nothing is called significant.
    assert not (np.isfinite(result.mannwhitney_p) and result.mannwhitney_p < 0.05)


def test_too_few_seeds_refuses_to_produce_a_p_value():
    """One seed per arm is not a comparison, and must not look like one."""
    result = compare("m", [1.0], [2.0])
    assert np.isnan(result.welch_p)
    assert result.significant is False
    assert (result.n_treatment, result.n_control) == (1, 1)


def test_the_sign_of_the_difference_follows_the_argument_order():
    up = compare("m", [2.0, 2.1, 2.2], [1.0, 1.1, 1.2])
    down = compare("m", [1.0, 1.1, 1.2], [2.0, 2.1, 2.2])
    assert up.difference > 0 > down.difference
    assert up.welch_t > 0 > down.welch_t
    assert up.welch_p == pytest.approx(down.welch_p)


def test_relative_change_is_undefined_against_a_zero_baseline():
    result = compare("m", [1.0, 1.1, 0.9], [0.0, 0.0, 0.0])
    assert np.isnan(result.relative)
    assert np.isfinite(result.difference)


def test_the_rank_test_survives_a_skewed_metric_that_defeats_the_t_test():
    """Why both are reported: delay distributions are not normal."""
    treatment = [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 200.0]
    control = [3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0]
    result = compare("delay", treatment, control)
    assert result.welch_p > 0.05, "one outlier swamps the mean"
    assert result.mannwhitney_p < 0.05, "the ranks still separate cleanly"
    assert result.significant is False, "the rank test alone is not enough either"


def test_welch_alone_does_not_declare_a_difference_significant():
    """The measured `extreme-budget` case: this is why the rule is a conjunction.

    Both lists are the six per-seed cumulative rewards stored in
    `reports/out/benchmark.json`. The means separate (Welch *p* = 0.021) while the ranks
    overlap (Mann-Whitney *p* = 0.065), so the arena table marks that row not
    significant — and would be wrong to mark it a win.
    """
    treatment = [111.852, 108.192, 98.288, 110.581, 90.006, 105.921]
    control = [86.800, 92.653, 93.934, 93.306, 98.546, 92.170]
    result = compare("cumulative_reward", treatment, control, treatment_name="mag-nts")
    assert result.difference > 0
    assert result.welch_p < 0.05
    assert result.mannwhitney_p > 0.05
    assert result.significant is False


def test_comparison_dict_is_json_serialisable():
    result = compare("m", [1.0, 2.0, 3.0], [4.0, 5.0, 6.0])
    payload = result.to_dict()
    assert json.loads(json.dumps(payload)) == payload
    assert payload["significant"] in (True, False)


# --------------------------------------------------------------------------- #
# summarise_runs
# --------------------------------------------------------------------------- #


def test_summarise_runs_covers_every_headline_metric():
    runs = [{metric: float(index + 1) for metric in HEADLINE_METRICS} for index in range(4)]
    summary = summarise_runs(runs)
    assert set(summary) == set(HEADLINE_METRICS)
    assert summary["cumulative_reward"]["n"] == 4
    assert summary["cumulative_reward"]["mean"] == pytest.approx(2.5)


def test_summarise_runs_tolerates_a_metric_missing_from_some_runs():
    runs = [{"cumulative_reward": 1.0}, {"cumulative_reward": 3.0}, {}]
    summary = summarise_runs(runs, metrics=("cumulative_reward", "band_coverage"))
    assert summary["cumulative_reward"]["n"] == 2
    assert summary["band_coverage"]["n"] == 0


# --------------------------------------------------------------------------- #
# Pareto
# --------------------------------------------------------------------------- #


def _point(sdp: float, ttd: float, far: float, cost: float) -> dict[str, float]:
    return {
        "sustained_detection_probability": sdp,
        "time_to_detect_capped": ttd,
        "false_alarm_rate": far,
        "sensing_cost": cost,
    }


def test_objective_directions_are_declared_explicitly():
    assert OBJECTIVES["sustained_detection_probability"] == +1
    assert set(OBJECTIVES.values()) <= {+1, -1}


def test_a_strictly_better_policy_dominates_a_strictly_worse_one():
    points = frontier({"good": _point(0.8, 10, 0.05, 100), "bad": _point(0.4, 20, 0.2, 200)})
    by_label = {point.label: point for point in points}
    assert by_label["good"].on_frontier
    assert by_label["bad"].dominated_by == ("good",)


def test_a_trade_off_leaves_both_policies_on_the_frontier():
    """The whole reason the frontier exists instead of a single ranking."""
    points = frontier(
        {
            "thorough": _point(0.9, 8, 0.30, 400),
            "frugal": _point(0.5, 25, 0.02, 90),
        }
    )
    assert all(point.on_frontier for point in points)
    assert describe(points)["frontier"] == ["frugal", "thorough"]


def test_identical_points_do_not_dominate_each_other():
    points = frontier({"a": _point(0.5, 10, 0.1, 100), "b": _point(0.5, 10, 0.1, 100)})
    assert all(point.on_frontier for point in points)


def test_being_better_on_one_axis_is_not_enough_to_dominate():
    points = frontier({"a": _point(0.9, 10, 0.1, 100), "b": _point(0.5, 10, 0.1, 100)})
    by_label = {point.label: point for point in points}
    assert by_label["a"].on_frontier
    assert by_label["b"].dominated_by == ("a",)  # equal elsewhere, worse on one


def test_a_non_finite_axis_disables_domination_rather_than_guessing():
    points = frontier({"a": _point(0.9, 10, 0.1, 100), "b": _point(0.1, float("nan"), 0.9, 900)})
    assert all(point.on_frontier for point in points)


def test_a_missing_axis_disables_domination():
    incomplete = {"sustained_detection_probability": 0.1}
    points = frontier({"a": _point(0.9, 10, 0.1, 100), "b": incomplete})
    assert all(point.on_frontier for point in points)


def test_frontier_points_are_listed_before_dominated_ones():
    points = frontier(
        {
            "zzz_best": _point(0.9, 5, 0.01, 50),
            "aaa_worst": _point(0.1, 50, 0.5, 500),
            "mmm_mid": _point(0.5, 20, 0.2, 200),
        }
    )
    assert points[0].label == "zzz_best"
    assert [point.on_frontier for point in points] == [True, False, False]


def test_describe_is_json_serialisable_and_labels_every_axis():
    points = frontier({"a": _point(0.9, 10, 0.1, 100), "b": _point(0.5, 20, 0.2, 200)})
    payload = describe(points)
    assert json.loads(json.dumps(payload)) == payload
    assert len(payload["objectives"]) == len(OBJECTIVES)
    for axis in payload["objectives"]:
        assert axis["direction"] in ("maximise", "minimise")
        assert axis["label"] != axis["metric"]


def test_a_frontier_that_could_not_be_computed_says_so():
    """The regression this exists for.

    ``sensing_cost`` was once missing from :data:`HEADLINE_METRICS`, so no
    aggregate carried it, ``_dominates`` always returned False and *every* policy
    was reported Pareto-optimal.  That reads as "all policies are equally good"
    but means "no comparison was made", so the payload must label it.
    """
    without_cost = {
        "sustained_detection_probability": 0.8,
        "time_to_detect_capped": 10.0,
        "false_alarm_rate": 0.05,
    }
    worse = {**without_cost, "sustained_detection_probability": 0.2}
    payload = describe(frontier({"a": without_cost, "b": worse}))
    assert payload["axes_missing"] == ["sensing_cost"]
    assert payload["vacuous"] is True
    assert sorted(payload["frontier"]) == ["a", "b"]


def test_a_complete_frontier_is_never_labelled_vacuous():
    payload = describe(frontier({"a": _point(0.9, 10, 0.1, 100), "b": _point(0.5, 20, 0.2, 200)}))
    assert payload["axes_missing"] == []
    assert payload["vacuous"] is False


def test_one_point_alone_is_not_a_vacuous_comparison():
    """A single policy is trivially on its own frontier; that is not a failure."""
    payload = describe(frontier({"only": {"sustained_detection_probability": 0.5}}))
    assert payload["vacuous"] is False


def test_every_pareto_axis_is_a_metric_the_aggregator_actually_produces():
    """The guard that would have caught the vacuous-frontier bug at the source."""
    from aamsx.evaluation.pareto import OBJECTIVES as AXES
    from aamsx.experiments.batch import PARETO_METRICS

    assert set(PARETO_METRICS) == set(AXES)
    missing = sorted(set(AXES) - set(HEADLINE_METRICS))
    assert not missing, f"aggregates will never carry {missing}, so the frontier is vacuous"
