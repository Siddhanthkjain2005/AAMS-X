"""The data layer: FITS in, regions out, with every preprocessing step visible.

Two things are being defended here.  First, that the numbers a scheduler sees are
traceable back to receiver digits by an arithmetic path a reader can check.
Second, that AAMS-X fails loudly when the cache cannot serve a request instead of
substituting anything invented.
"""

from __future__ import annotations

import numpy as np
import pytest

from aamsx.datasets.calibration import DEFAULT_BLOCK_SIZE, compute_calibration
from aamsx.datasets.fits import BLOCK, CARD, FitsFormatError, read_callisto
from aamsx.datasets.store import CacheMiss, get_recording, list_recordings, load_cube, load_raw
from aamsx.environment.grid import bin_time, build_grid, region_margin_db
from tests.conftest import requires_cache

DB_PER_DIGIT = 25.4 / 255.0


# --------------------------------------------------------------------------- #
# the region grid
# --------------------------------------------------------------------------- #


def test_regions_have_equal_channel_counts_not_equal_bandwidth():
    """The e-CALLISTO frequency axis is not linear; equal widths would starve bins."""
    freq = np.concatenate([np.linspace(20, 40, 60), np.linspace(40.5, 400, 140)])
    grid = build_grid(freq, 8)
    assert grid.counts.sum() == grid.n_channels == 200
    assert grid.counts.max() - grid.counts.min() <= 1
    assert not np.allclose(grid.width_mhz, grid.width_mhz[0])


def test_edges_tile_the_axis_without_gaps_or_overlaps():
    grid = build_grid(np.linspace(45, 870, 200), 12)
    assert np.all(np.diff(grid.edges_mhz) > 0)
    assert np.allclose(grid.width_mhz, np.diff(grid.edges_mhz))
    assert grid.centre_mhz[0] < grid.centre_mhz[-1]


def test_a_descending_frequency_axis_is_sorted_into_ascending_regions():
    """CALLISTO publishes descending frequency, and region 0 must be the low band."""
    ascending = build_grid(np.linspace(45, 870, 200), 10)
    descending = build_grid(np.linspace(870, 45, 200), 10)
    assert np.allclose(ascending.centre_mhz, descending.centre_mhz)
    assert descending.centre_mhz[0] < descending.centre_mhz[-1]


def test_padding_channels_pinned_to_the_band_edge_are_dropped():
    """A documented preprocessing step, not a silent one."""
    freq = np.concatenate([np.full(8, 45.0), np.linspace(45, 870, 200)])
    kept = build_grid(freq, 10)
    padded = build_grid(freq, 10, drop_duplicate_freqs=False)
    assert kept.n_channels == 200
    assert padded.n_channels == 208
    assert kept.width_mhz[0] > 0.0


def test_a_frequency_range_selects_a_sub_band():
    freq = np.linspace(45, 870, 400)
    grid = build_grid(freq, 8, freq_range_mhz=(100.0, 200.0))
    assert grid.edges_mhz[0] >= 100.0
    assert grid.edges_mhz[-1] <= 200.0
    assert grid.n_channels < 400


def test_impossible_geometry_raises_instead_of_degrading():
    with pytest.raises(ValueError, match="at least 2"):
        build_grid(np.linspace(45, 870, 100), 1)
    with pytest.raises(ValueError, match="cannot fill"):
        build_grid(np.linspace(45, 870, 100), 40, freq_range_mhz=(45.0, 50.0))
    with pytest.raises(ValueError, match="distinct frequencies"):
        build_grid(np.full(50, 100.0), 8)


def test_region_labels_are_stable_and_readable():
    grid = build_grid(np.linspace(45, 870, 200), 4)
    label = grid.region_label(1)
    assert label.startswith("R01")
    assert "MHz" in label


def test_grid_dict_is_round_trippable():
    grid = build_grid(np.linspace(45, 870, 200), 6)
    payload = grid.to_dict()
    assert len(payload["edges_mhz"]) == 7
    assert len(payload["centre_mhz"]) == len(payload["counts"]) == 6
    assert sum(payload["counts"]) == payload["n_channels"]


# --------------------------------------------------------------------------- #
# margin: the quantity everything else works in
# --------------------------------------------------------------------------- #


def test_region_margin_is_the_best_channel_in_the_region():
    grid = build_grid(np.linspace(45, 870, 8), 4)  # two channels per region
    excess = np.array([[1.0, 5.0, 0.0, 0.0, 2.0, 2.0, -3.0, -1.0]], dtype=np.float32)
    threshold = np.full(8, 1.5, dtype=np.float32)
    margin = region_margin_db(excess, threshold, grid)
    assert margin.shape == (1, 4)
    assert margin[0, 0] == pytest.approx(3.5)  # max(1, 5) - 1.5
    assert margin[0, 1] == pytest.approx(-1.5)
    assert margin[0, 2] == pytest.approx(0.5)
    assert margin[0, 3] == pytest.approx(-2.5)


def test_occupancy_is_exactly_a_positive_margin():
    grid = build_grid(np.linspace(45, 870, 8), 4)
    excess = np.array([[1.6, 0.0, 1.4, 0.0, 1.5, 0.0, 9.0, 0.0]], dtype=np.float32)
    margin = region_margin_db(excess, np.full(8, 1.5, dtype=np.float32), grid)
    assert (margin > 0).tolist() == [[True, False, False, True]]


def test_channels_with_different_thresholds_are_not_pooled_on_a_common_one():
    """Pooling raw power would smuggle in a threshold nobody measured."""
    grid = build_grid(np.linspace(45, 870, 4), 2)
    excess = np.array([[3.0, 3.0, 3.0, 3.0]], dtype=np.float32)
    thresholds = np.array([1.0, 9.0, 9.0, 9.0], dtype=np.float32)
    margin = region_margin_db(excess, thresholds, grid)
    assert margin[0, 0] > 0  # its quiet channel supports a detection
    assert margin[0, 1] < 0  # equally loud, but both channels are noisy


# --------------------------------------------------------------------------- #
# time binning
# --------------------------------------------------------------------------- #


def test_time_binning_keeps_the_loudest_sample_by_default():
    values = np.arange(12, dtype=np.float32).reshape(6, 2)
    assert bin_time(values, 3, reduce="max").tolist() == [[4.0, 5.0], [10.0, 11.0]]


def test_time_binning_supports_mean_and_any():
    values = np.arange(8, dtype=np.float32).reshape(4, 2)
    assert bin_time(values, 2, reduce="mean").tolist() == [[1.0, 2.0], [5.0, 6.0]]
    flags = np.array([[True, False], [False, False], [False, False], [False, False]])
    assert bin_time(flags, 2, reduce="any").tolist() == [[True, False], [False, False]]


def test_time_binning_by_one_is_the_identity():
    values = np.arange(6, dtype=np.float32).reshape(3, 2)
    assert bin_time(values, 1) is values


def test_a_partial_trailing_bin_is_dropped_not_padded():
    values = np.arange(7, dtype=np.float32).reshape(7, 1)
    assert bin_time(values, 3).shape == (2, 1)


def test_time_binning_refuses_an_impossible_request():
    with pytest.raises(ValueError, match="cannot form a single step"):
        bin_time(np.zeros((2, 3), dtype=np.float32), 8)
    with pytest.raises(ValueError, match="unknown reduction"):
        bin_time(np.zeros((8, 3), dtype=np.float32), 2, reduce="median")


# --------------------------------------------------------------------------- #
# calibration
# --------------------------------------------------------------------------- #


def _digits(rng, n_times=6000, n_channels=16, level=100) -> np.ndarray:
    return np.clip(rng.normal(level, 2.0, size=(n_times, n_channels)), 0, 255).astype(np.uint8)


def test_the_baseline_tracks_a_drifting_receiver(rng):
    """A fixed baseline would read a warming front end as hours of activity."""
    n_times, n_channels = 3 * DEFAULT_BLOCK_SIZE, 8
    drift = np.linspace(80, 160, n_times)[:, None]
    digits = np.clip(drift + rng.normal(0, 1.0, size=(n_times, n_channels)), 0, 255).astype(
        np.uint8
    )
    calibration = compute_calibration(digits, db_per_digit=DB_PER_DIGIT)
    assert calibration.n_blocks == 3
    assert calibration.baseline_blocks[0].mean() < calibration.baseline_blocks[-1].mean()
    excess = calibration.excess(digits)
    raw_drift = float((digits[-1].mean() - digits[0].mean()) * DB_PER_DIGIT)
    residual = abs(float(excess[: n_times // 3].mean()) - float(excess[-n_times // 3 :].mean()))
    # Block-quantile tracking cannot follow drift *within* a block, so a residual
    # remains; what matters is that it is a small fraction of the raw excursion.
    assert raw_drift > 7.0
    assert residual < 0.15 * raw_drift


def test_the_noise_scale_comes_from_first_differences(rng):
    """Robust to activity: a burst raises the level, not the sample-to-sample jitter."""
    quiet = _digits(rng, n_channels=4, level=100)
    calibration = compute_calibration(quiet, db_per_digit=DB_PER_DIGIT)
    expected = 2.0 * DB_PER_DIGIT
    assert calibration.noise_db.mean() == pytest.approx(expected, rel=0.25)

    loud = quiet.copy()
    loud[1000:1400] = 200  # a long, flat burst
    with_burst = compute_calibration(loud, db_per_digit=DB_PER_DIGIT)
    assert with_burst.noise_db.mean() == pytest.approx(calibration.noise_db.mean(), rel=0.3)


def test_the_threshold_is_the_larger_of_a_floor_and_k_sigma(rng):
    noisy = np.clip(rng.normal(100, 30.0, size=(4000, 4)), 0, 255).astype(np.uint8)
    calibration = compute_calibration(
        noisy, db_per_digit=DB_PER_DIGIT, k_mad=5.0, min_excess_db=1.5
    )
    assert np.all(calibration.threshold_db >= 1.5)
    assert np.allclose(
        calibration.threshold_db,
        np.maximum(1.5, 5.0 * calibration.noise_db),
        atol=1e-5,
    )


def test_a_quiet_channel_gets_the_floor_not_a_zero_threshold():
    flat = np.full((4000, 3), 100, dtype=np.uint8)
    calibration = compute_calibration(flat, db_per_digit=DB_PER_DIGIT, min_excess_db=1.5)
    assert np.all(calibration.threshold_db == pytest.approx(1.5))
    assert np.all(calibration.noise_db > 0.0)  # never zero, or excess/noise explodes


def test_a_real_burst_clears_the_threshold_and_quiet_data_does_not(rng):
    digits = _digits(rng, n_times=4000, n_channels=4, level=100)
    calibration = compute_calibration(digits, db_per_digit=DB_PER_DIGIT)
    quiet_excess = calibration.excess(digits)
    assert float((quiet_excess > calibration.threshold_db).mean()) < 0.05

    loud = digits.copy()
    loud[2000:2050] = 200
    burst_excess = calibration.excess(loud)[2000:2050]
    assert np.all(burst_excess > calibration.threshold_db)


def test_baseline_interpolation_is_clamped_at_both_ends(rng):
    digits = _digits(rng, n_times=3 * DEFAULT_BLOCK_SIZE, n_channels=4)
    calibration = compute_calibration(digits, db_per_digit=DB_PER_DIGIT)
    values = calibration.baseline_at(np.array([-500, 0, 10**7]))
    assert np.allclose(values[0], values[1], atol=1e-3)
    assert np.allclose(values[-1], calibration.baseline_blocks[-1], atol=1e-3)


def test_a_single_block_recording_still_calibrates(rng):
    digits = _digits(rng, n_times=500, n_channels=4)
    calibration = compute_calibration(digits, db_per_digit=DB_PER_DIGIT)
    assert calibration.n_blocks == 1
    assert calibration.excess(digits).shape == digits.shape


def test_calibration_rejects_a_non_matrix():
    with pytest.raises(ValueError, match=r"\(T, C\)"):
        compute_calibration(np.zeros(10, dtype=np.uint8), db_per_digit=DB_PER_DIGIT)


def test_calibration_dict_records_the_knobs_that_produced_it():
    payload = compute_calibration(
        np.full((100, 3), 90, dtype=np.uint8), db_per_digit=DB_PER_DIGIT
    ).to_dict()
    for key in ("block_size", "db_per_digit", "percentile", "k_mad", "min_excess_db"):
        assert key in payload


# --------------------------------------------------------------------------- #
# the FITS reader
# --------------------------------------------------------------------------- #


def test_the_fits_reader_rejects_content_that_is_not_fits():
    """Archive downloads are untrusted input and are validated before use."""
    with pytest.raises(FitsFormatError):
        read_callisto(b"<html>404 Not Found</html>" + b" " * BLOCK)
    with pytest.raises(FitsFormatError):
        read_callisto(b"")


def test_the_fits_reader_rejects_a_truncated_file():
    header = b"SIMPLE  =                    T" + b" " * (CARD - 30)
    with pytest.raises(FitsFormatError):
        read_callisto(header + b" " * 100)


# --------------------------------------------------------------------------- #
# the offline cache
# --------------------------------------------------------------------------- #


@requires_cache
def test_the_cache_lists_real_recordings_with_provenance(recordings):
    for record in recordings:
        assert record.n_times > 0
        assert record.n_channels > 0
        assert record.freq_min_mhz < record.freq_max_mhz
        assert 0.0 <= record.occupancy <= 1.0
        assert record.cadence_sec > 0.0
        provenance = record.provenance
        assert provenance["adapter"] == "e-callisto"
        assert provenance["is_synthetic"] is False, "the cache must never hold invented data"
        assert provenance["source_url"].startswith("http")
        assert provenance["retrieved_at"]
        assert provenance["license"]
        assert provenance["reference"]
        assert provenance["checksum"]
        # Every transformation between digits and labels is listed, in order.
        steps = " | ".join(provenance["preprocessing"])
        assert "baseline" in steps and "noise scale" in steps and "occupancy label" in steps
        assert "reference label, not absolute truth" in steps
        payload = record.to_dict()
        assert payload["recording_id"] == f"{record.station}/{record.day}"


@requires_cache
def test_a_slice_loads_exactly_the_steps_requested(recording_id):
    raw = load_raw(recording_id, start_step=100, n_steps=64)
    assert raw.digits.shape[0] == 64
    assert raw.t_sec.size == 64
    assert raw.available.size == 64
    assert raw.digits.dtype == np.uint8


@requires_cache
def test_the_same_slice_loads_identically_every_time(recording_id):
    first = load_raw(recording_id, start_step=200, n_steps=48)
    second = load_raw(recording_id, start_step=200, n_steps=48)
    assert np.array_equal(first.digits, second.digits)
    assert np.array_equal(first.t_sec, second.t_sec)


@requires_cache
def test_overlapping_slices_agree_where_they_overlap(recording_id):
    wide = load_raw(recording_id, start_step=100, n_steps=200)
    narrow = load_raw(recording_id, start_step=150, n_steps=50)
    assert np.array_equal(wide.digits[50:100], narrow.digits)


@requires_cache
def test_a_slice_past_the_end_is_truncated_not_padded(recording_id):
    record = get_recording(recording_id)
    raw = load_raw(recording_id, start_step=record.n_times - 10, n_steps=1000)
    assert raw.digits.shape[0] == 10


@requires_cache
def test_an_impossible_window_raises_cache_miss(recording_id):
    record = get_recording(recording_id)
    with pytest.raises(CacheMiss, match="outside recording"):
        load_raw(recording_id, start_step=record.n_times + 5, n_steps=10)
    with pytest.raises(CacheMiss, match="outside recording"):
        load_raw(recording_id, start_step=-1, n_steps=10)


@requires_cache
def test_a_missing_recording_names_what_is_available():
    """No synthetic fallback exists, so the error has to be actionable."""
    with pytest.raises(CacheMiss) as info:
        get_recording("NOWHERE/19700101")
    message = str(info.value)
    assert "not cached" in message
    assert any(record.station in message for record in list_recordings())


@requires_cache
def test_a_loaded_cube_is_internally_consistent(recording_id):
    cube = load_cube(recording_id, start_step=0, n_steps=128)
    summary = cube.summary()
    assert 0.0 <= summary["occupancy"] <= 1.0
    occupancy = cube.occupancy()
    assert occupancy.shape[0] == 128
    assert occupancy.dtype == bool
    assert float(occupancy.mean()) == pytest.approx(summary["occupancy"], abs=0.05)
