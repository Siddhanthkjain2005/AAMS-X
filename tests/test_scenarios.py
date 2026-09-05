"""Scenario presets, family sampling and the measured window index.

Two things are being defended here.  The first is that every scenario is built
from a window the index actually measured, so the numbers quoted in a scenario
description are properties of the block that gets replayed rather than of a
longer recording it was cut from.  The second is the generalisation split: the
held-out receivers must appear in exactly one preset, because everything else is
tuned against what it sees.
"""

from __future__ import annotations

import json
from typing import get_args

import numpy as np
import pytest

from aamsx.contracts.scenario import ScenarioFamily, ScenarioSpec
from aamsx.datasets.stations import STATIONS, stations_for_role
from aamsx.datasets.windows import INDEX_NAME, WindowRef, index_path, query
from aamsx.environment.scenarios import (
    FAMILY_PREDICATES,
    MULTI_SEGMENT_FAMILIES,
    PRESET_ORDER,
    TUNING_ROLES,
    find_pair,
    find_windows,
    list_presets,
    preset,
    profile_similarity,
    sample_scenario,
)
from tests.conftest import requires_index

pytestmark = requires_index

ALL_FAMILIES: tuple[str, ...] = get_args(ScenarioFamily)
UNSEEN_STATIONS = {station.name for station in stations_for_role("unseen")}
TUNING_STATIONS = {station.name for station in STATIONS if station.role in TUNING_ROLES}


def _built() -> list[ScenarioSpec]:
    return list_presets()


def _stations(spec: ScenarioSpec) -> set[str]:
    return {segment.recording_id.split("/")[0] for segment in spec.segments}


def _try(scenario_id: str) -> ScenarioSpec:
    try:
        return preset(scenario_id)
    except (LookupError, FileNotFoundError) as exc:
        pytest.skip(f"cache cannot satisfy {scenario_id}: {exc}")


# --------------------------------------------------------------------------- #
# the window index
# --------------------------------------------------------------------------- #


def test_the_index_lives_where_the_settings_say():
    assert index_path().name == INDEX_NAME
    assert index_path().exists()


def test_the_index_holds_characterised_windows():
    rows = query("SELECT * FROM windows LIMIT 5")
    assert rows
    for row in rows:
        assert row["n_steps"] > 0
        assert row["time_bin"] > 0
        assert 0.0 <= row["occupancy"] <= 1.0
        assert len(row["profile"]) == row["n_regions"]


def test_every_indexed_length_is_one_of_the_three_scenario_shapes():
    """1200 for a single phase, 600 for a splice, 400 for an A->B->A' recurrence."""
    lengths = {row["n_steps"] for row in query("SELECT DISTINCT n_steps FROM windows")}
    assert lengths <= {400, 600, 1200}


def test_a_window_ref_reports_its_real_duration():
    ref = find_windows(limit=1)[0]
    assert ref.duration_sec == pytest.approx(ref.n_steps * ref.time_bin * 0.25)


def test_a_window_ref_flattens_its_statistics_for_the_api():
    ref = find_windows(limit=1)[0]
    payload = ref.to_dict()
    assert payload["recording_id"] == ref.recording_id
    assert payload["occupancy"] == ref.stats["occupancy"]
    assert "profile" not in payload, "the profile is a 48-vector, not a summary field"
    json.dumps(payload)


def test_find_windows_orders_by_the_requested_column():
    refs = find_windows(order_by="occupancy DESC", limit=8)
    occupancies = [float(ref.stats["occupancy"]) for ref in refs]
    assert occupancies == sorted(occupancies, reverse=True)


def test_find_windows_respects_the_generalisation_split():
    for role_set, allowed in ((TUNING_ROLES, TUNING_STATIONS), (("unseen",), UNSEEN_STATIONS)):
        refs = find_windows(limit=64, roles=role_set)
        if not refs:
            continue
        assert {ref.station for ref in refs} <= allowed


def test_a_missing_index_is_reported_rather_than_silently_empty(tmp_path):
    from aamsx.config import Settings

    with pytest.raises(FileNotFoundError, match="window index missing"):
        query("SELECT 1", settings=Settings(data_dir=tmp_path))


# --------------------------------------------------------------------------- #
# profile similarity
# --------------------------------------------------------------------------- #


def _ref(profile: tuple[float, ...]) -> WindowRef:
    return WindowRef(
        recording_id="X/20260825",
        station="X",
        start_step=0,
        time_bin=4,
        n_steps=400,
        n_regions=len(profile),
        stats={"occupancy": float(np.mean(profile) if profile else 0.0)},
        profile=profile,
    )


def test_a_window_is_perfectly_similar_to_itself():
    ref = _ref((0.1, 0.9, 0.2, 0.7))
    assert profile_similarity(ref, ref) == pytest.approx(1.0)


def test_an_inverted_profile_is_perfectly_dissimilar():
    left = _ref((0.1, 0.9, 0.2, 0.7))
    right = _ref(tuple(1.0 - value for value in left.profile))
    assert profile_similarity(left, right) == pytest.approx(-1.0)


def test_similarity_ignores_the_overall_level():
    """Two windows can differ in occupancy and still pose the same problem."""
    left = _ref((0.1, 0.5, 0.2))
    right = _ref((0.2, 1.0, 0.4))
    assert profile_similarity(left, right) > 0.99


def test_a_flat_profile_has_no_shape_to_correlate():
    assert profile_similarity(_ref((0.3, 0.3, 0.3)), _ref((0.1, 0.9, 0.5))) == 0.0


@pytest.mark.parametrize(
    ("left", "right"),
    [((), (0.1, 0.2)), ((0.1, 0.2), ()), ((0.1, 0.2), (0.1, 0.2, 0.3))],
)
def test_similarity_declines_rather_than_guessing_on_mismatched_profiles(left, right):
    assert profile_similarity(_ref(left), _ref(right)) == 0.0


# --------------------------------------------------------------------------- #
# pair selection
# --------------------------------------------------------------------------- #


def test_a_dissimilar_pair_is_less_alike_than_a_similar_one():
    kwargs = {"where": "occupancy BETWEEN 0.02 AND 0.4", "n_steps": 600, "time_bin": 4}
    try:
        far = find_pair(mode="dissimilar", **kwargs)
        near = find_pair(mode="similar", **kwargs)
    except LookupError as exc:
        pytest.skip(str(exc))
    assert profile_similarity(*far) < profile_similarity(*near)


def test_a_cross_station_pair_uses_two_different_receivers():
    try:
        left, right = find_pair(
            where="occupancy BETWEEN 0.02 AND 0.4", n_steps=600, time_bin=4, same_station=False
        )
    except LookupError as exc:
        pytest.skip(str(exc))
    assert left.station != right.station


def test_a_same_station_pair_is_separated_by_a_real_time_gap():
    """Overlapping windows are the same environment, not a recurrence of one."""
    n_steps, time_bin, gap_spans = 400, 4, 4.0
    try:
        left, right = find_pair(
            where="occupancy BETWEEN 0.02 AND 0.4",
            n_steps=n_steps,
            time_bin=time_bin,
            mode="similar",
            same_station=True,
            min_gap_spans=gap_spans,
        )
    except LookupError as exc:
        pytest.skip(str(exc))
    assert left.station == right.station
    assert abs(left.start_step - right.start_step) >= gap_spans * n_steps * time_bin


def test_an_unsatisfiable_pair_request_says_so():
    with pytest.raises(LookupError, match="fewer than two indexed windows"):
        find_pair(where="occupancy > 5.0", n_steps=600, time_bin=4)


# --------------------------------------------------------------------------- #
# presets
# --------------------------------------------------------------------------- #


def test_the_cache_satisfies_every_declared_preset():
    assert [spec.scenario_id for spec in _built()] == list(PRESET_ORDER)


def test_an_unknown_preset_names_the_ones_that_exist():
    with pytest.raises(KeyError, match="easy-static"):
        preset("does-not-exist")


def test_presets_are_cached_per_process():
    assert preset("easy-static") is preset("easy-static")


@pytest.mark.parametrize("scenario_id", PRESET_ORDER)
def test_a_preset_is_internally_consistent(scenario_id):
    spec = _try(scenario_id)
    assert spec.horizon == sum(segment.n_steps for segment in spec.segments)
    assert spec.horizon > 0
    assert len(spec.change_points) == len(spec.segments) - 1
    assert list(spec.change_points) == sorted(spec.change_points)
    assert all(0 < point < spec.horizon for point in spec.change_points)
    assert spec.phase_spans[-1][2] == spec.horizon
    assert spec.description.strip()
    json.dumps(spec.to_dict(), allow_nan=False)


@pytest.mark.parametrize("scenario_id", PRESET_ORDER)
def test_every_segment_names_a_window_the_index_measured(scenario_id):
    spec = _try(scenario_id)
    for segment in spec.segments:
        rows = query(
            "SELECT 1 FROM windows "
            f"WHERE recording_id = '{segment.recording_id}' "
            f"AND start_step = {segment.start_step} AND time_bin = {spec.time_bin}"
        )
        assert rows, f"{segment.recording_id} @ {segment.start_step} is not in the index"


def test_only_the_held_out_preset_touches_the_held_out_receivers():
    """The leakage guard behind the 'Unseen Generalization' claim."""
    for spec in _built():
        used = _stations(spec)
        if spec.scenario_id == "unseen-generalization":
            assert used <= UNSEEN_STATIONS, "the held-out test must use only held-out stations"
            assert spec.split == "unseen"
        else:
            assert not (used & UNSEEN_STATIONS), f"{spec.scenario_id} leaks a held-out station"
            assert spec.split in TUNING_ROLES


def test_the_shift_preset_splices_two_genuinely_different_receivers():
    spec = _try("sudden-shift")
    assert len(spec.segments) == 2
    assert len(_stations(spec)) == 2
    assert spec.family == "distribution-shift"
    assert spec.change_points == (spec.segments[0].n_steps,)


def test_the_recurrence_preset_returns_to_the_first_environment_later_in_time():
    spec = _try("recurring-environment")
    assert [segment.phase for segment in spec.segments] == ["A", "B", "A-prime"]
    first, middle, last = spec.segments
    assert first.recording_id == last.recording_id, "A' must be the same receiver as A"
    assert first.start_step != last.start_step, "A' must be a different stretch of time"
    assert middle.recording_id != first.recording_id
    assert spec.family == "recurring-context"


def test_the_budget_preset_actually_constrains_sensing():
    spec = _try("extreme-budget")
    assert spec.budget is not None
    assert spec.effective_budget() < spec.horizon * spec.receiver.cost_per_observation
    assert spec.family == "budget-constrained"


def test_the_noise_preset_raises_receiver_noise_above_the_calibrated_default():
    from aamsx.contracts.scenario import ReceiverSpec

    spec = _try("high-noise")
    assert spec.receiver.noise_db > ReceiverSpec().noise_db
    assert spec.family == "noisy"


def test_the_periodic_preset_selects_a_window_with_a_measured_period():
    spec = _try("periodic-challenge")
    assert spec.family == "periodic"
    row = query(
        "SELECT period_steps, period_strength FROM windows "
        f"WHERE recording_id = '{spec.segments[0].recording_id}' "
        f"AND start_step = {spec.segments[0].start_step} "
        f"AND n_steps = {spec.segments[0].n_steps} AND time_bin = {spec.time_bin}"
    )[0]
    assert row["period_steps"] > 0
    assert row["period_strength"] > 0.4


def test_preset_scenario_ids_are_unique():
    ids = [spec.scenario_id for spec in _built()]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------- #
# randomised families
# --------------------------------------------------------------------------- #


def test_every_declared_family_has_a_measured_predicate():
    assert set(FAMILY_PREDICATES) == set(ALL_FAMILIES)
    assert set(ALL_FAMILIES) >= MULTI_SEGMENT_FAMILIES


def test_an_unknown_family_is_rejected():
    with pytest.raises(KeyError):
        sample_scenario("not-a-family", seed=0)  # type: ignore[arg-type]


@pytest.mark.parametrize("family", ALL_FAMILIES)
def test_a_sampled_scenario_is_well_formed(family):
    try:
        spec = sample_scenario(family, seed=3, segment_steps=120)
    except LookupError as exc:
        pytest.skip(str(exc))
    assert spec.family == family
    assert spec.horizon > 0
    assert spec.segments
    expected_segments = (
        3 if family == "recurring-context" else (2 if family in MULTI_SEGMENT_FAMILIES else 1)
    )
    assert len(spec.segments) == expected_segments
    json.dumps(spec.to_dict(), allow_nan=False)


def test_the_same_seed_samples_the_same_environment():
    first = sample_scenario("distribution-shift", seed=11, segment_steps=120)
    second = sample_scenario("distribution-shift", seed=11, segment_steps=120)
    assert first.to_dict() == second.to_dict()


def test_different_seeds_sample_different_environments():
    """Otherwise a multi-seed run re-measures one episode instead of averaging over many."""
    drawn = {
        tuple(
            (segment.recording_id, segment.start_step)
            for segment in sample_scenario(
                "distribution-shift", seed=seed, segment_steps=120
            ).segments
        )
        for seed in range(8)
    }
    assert len(drawn) > 1


def test_a_multi_segment_family_splices_two_different_receivers():
    spec = sample_scenario("distribution-shift", seed=7, segment_steps=120)
    stations = [segment.recording_id.split("/")[0] for segment in spec.segments]
    assert stations[0] != stations[1]
    assert spec.change_points == (spec.segments[0].n_steps,)


def test_the_budget_family_leaves_only_a_third_of_the_horizon():
    spec = sample_scenario("budget-constrained", seed=2, segment_steps=120)
    assert spec.budget == pytest.approx(0.35 * spec.horizon)


def test_the_unseen_family_is_forced_onto_the_held_out_receivers():
    """Passing tuning roles must not be able to contaminate the held-out family."""
    spec = sample_scenario("unseen-combination", seed=1, roles=TUNING_ROLES, segment_steps=120)
    assert spec.split == "unseen"
    assert {segment.recording_id.split("/")[0] for segment in spec.segments} <= UNSEEN_STATIONS


def test_a_sampled_scenario_honours_the_requested_segment_length():
    spec = sample_scenario("persistent", seed=4, segment_steps=90)
    assert spec.segments[0].n_steps <= 90
