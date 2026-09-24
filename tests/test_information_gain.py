"""Information gain: exactness, monotonicity and the window projection."""

from __future__ import annotations

import numpy as np
import pytest

from aamsx.belief.filter import binary_entropy
from aamsx.information_gain.entropy import (
    maximum_possible_gain,
    region_information_gain,
    spread_to_regions,
    window_information_gain,
)


def _brute_force(b: float, s: float, f: float) -> float:
    """The definition, written out, as an independent check on the vectorised form."""
    p_detect = s * b + f * (1.0 - b)
    post_detect = s * b / p_detect
    post_miss = (1.0 - s) * b / (1.0 - p_detect)
    expected = p_detect * float(binary_entropy(post_detect)) + (1.0 - p_detect) * float(
        binary_entropy(post_miss)
    )
    return float(binary_entropy(b)) - expected


@pytest.mark.parametrize("belief", [0.02, 0.1, 0.3, 0.5, 0.7, 0.95])
def test_matches_the_closed_form_definition(belief):
    got = region_information_gain(np.array([belief]), sensitivity=0.9, false_alarm=0.1)[0]
    assert got == pytest.approx(_brute_force(belief, 0.9, 0.1), abs=1e-12)


def test_gain_is_never_negative_and_never_exceeds_prior_entropy():
    beliefs = np.linspace(1e-6, 1 - 1e-6, 501)
    gain = region_information_gain(beliefs, sensitivity=0.9, false_alarm=0.1)
    assert np.all(gain >= 0.0)
    assert np.all(gain <= binary_entropy(beliefs) + 1e-12)


def test_gain_peaks_near_maximum_uncertainty():
    beliefs = np.linspace(0.01, 0.99, 199)
    gain = region_information_gain(beliefs, sensitivity=0.9, false_alarm=0.1)
    assert 0.35 < beliefs[int(np.argmax(gain))] < 0.65


def test_certain_regions_teach_nothing():
    gain = region_information_gain(np.array([1e-9, 1.0 - 1e-9]), sensitivity=0.95, false_alarm=0.05)
    assert np.all(gain < 1e-6)


def test_a_perfect_sensor_resolves_the_whole_bit():
    """With s=1 and f=0 one observation removes all entropy, so IG == H(b)."""
    beliefs = np.array([0.2, 0.5, 0.8])
    gain = region_information_gain(beliefs, sensitivity=1.0 - 1e-9, false_alarm=1e-9)
    assert np.allclose(gain, binary_entropy(beliefs), atol=1e-6)


def test_a_useless_sensor_teaches_nothing():
    """When s == f the measurement is independent of the state."""
    beliefs = np.array([0.2, 0.5, 0.8])
    gain = region_information_gain(beliefs, sensitivity=0.5, false_alarm=0.5)
    assert np.all(gain < 1e-9)


def test_a_noisier_sensor_learns_less():
    beliefs = np.full(5, 0.5)
    sharp = region_information_gain(beliefs, sensitivity=0.98, false_alarm=0.02)
    blunt = region_information_gain(beliefs, sensitivity=0.70, false_alarm=0.30)
    assert np.all(sharp > blunt)


def test_window_gain_is_the_sum_over_its_regions():
    gains = np.array([0.1, 0.4, 0.2, 0.05, 0.3, 0.25])
    windows = window_information_gain(gains, 3)
    assert windows.size == 4
    for anchor in range(4):
        assert windows[anchor] == pytest.approx(gains[anchor : anchor + 3].sum())


def test_window_size_one_is_the_identity():
    gains = np.array([0.3, 0.1, 0.2])
    assert np.allclose(window_information_gain(gains, 1), gains)


def test_window_larger_than_the_band_is_rejected():
    with pytest.raises(ValueError, match="exceeds"):
        window_information_gain(np.zeros(3), 5)


def test_spread_credits_each_region_with_its_best_window():
    windows = np.array([1.0, 5.0, 2.0])  # 5 regions, window 3
    spread = spread_to_regions(windows, 5, 3)
    assert spread.size == 5
    assert spread[0] == 1.0  # only window 0 covers region 0
    assert spread[2] == 5.0  # covered by windows 0, 1, 2 -> best is 5
    assert spread[4] == 2.0  # only window 2 covers region 4
    assert np.all(spread <= windows.max())


def test_maximum_possible_gain_is_one_bit_per_region():
    assert maximum_possible_gain(48) == pytest.approx(48 * np.log(2.0))
