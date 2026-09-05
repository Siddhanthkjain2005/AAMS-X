"""Information-gain estimation — what makes AAMS-X an active-sensing system.

A reward-maximising bandit observes where it expects signal.  An active-sensing
scheduler also observes where it expects to *learn*, and those are not the same
place: a region sitting at ``b = 0.5`` promises little detection but resolves a
full bit of uncertainty, while a region at ``b = 0.97`` promises a detection and
teaches almost nothing.

For belief ``b`` the expected posterior entropy after one observation is exact
under the binary observation model, because there are only two outcomes:

    P(detect)   = s*b + f*(1-b)
    b | detect  = s*b / P(detect)
    b | miss    = (1-s)*b / (1 - P(detect))
    IG(region)  = H(b) - [ P(detect) H(b|detect) + P(miss) H(b|miss) ]

``s`` (sensitivity) and ``f`` (false-alarm rate) come from the receiver noise and
the *measured* typical margin either side of the decision threshold — see
:meth:`aamsx.belief.filter.BeliefFilter.sensitivity_specificity` — so the
estimate tracks the recording instead of being hand-tuned.

Regions are treated as independent, so a window's gain is the sum of its regions'
gains.  The entropy of the regions the receiver does *not* visit changes too, but
identically for every candidate action, so it cancels in the comparison.
"""

from __future__ import annotations

import numpy as np

from aamsx.belief.filter import EPSILON, binary_entropy


def region_information_gain(
    belief: np.ndarray, *, sensitivity: float, false_alarm: float
) -> np.ndarray:
    """Expected entropy reduction, in nats, from observing each region once."""
    b = np.clip(np.asarray(belief, dtype=np.float64), EPSILON, 1.0 - EPSILON)
    s = float(np.clip(sensitivity, EPSILON, 1.0 - EPSILON))
    f = float(np.clip(false_alarm, EPSILON, 1.0 - EPSILON))

    p_detect = np.clip(s * b + f * (1.0 - b), EPSILON, 1.0 - EPSILON)
    posterior_detect = np.clip(s * b / p_detect, EPSILON, 1.0 - EPSILON)
    posterior_miss = np.clip((1.0 - s) * b / (1.0 - p_detect), EPSILON, 1.0 - EPSILON)

    expected = p_detect * binary_entropy(posterior_detect) + (1.0 - p_detect) * binary_entropy(
        posterior_miss
    )
    return np.maximum(binary_entropy(b) - expected, 0.0)


def window_information_gain(region_gain: np.ndarray, window_size: int) -> np.ndarray:
    """Sum region gains over every contiguous window, returning ``(n_anchors,)``."""
    gains = np.asarray(region_gain, dtype=np.float64)
    if window_size <= 1:
        return gains.copy()
    cumulative = np.concatenate(([0.0], np.cumsum(gains)))
    anchors = gains.size - window_size + 1
    if anchors <= 0:
        raise ValueError(f"window_size {window_size} exceeds {gains.size} regions")
    return cumulative[window_size : window_size + anchors] - cumulative[:anchors]


def spread_to_regions(window_values: np.ndarray, n_regions: int, window_size: int) -> np.ndarray:
    """Project per-anchor values back onto regions for display.

    Each region is credited with the best window that contains it, which is the
    quantity a user is actually asking about when they hover a region: "how much
    would looking here be worth?"
    """
    values = np.asarray(window_values, dtype=np.float64)
    out = np.full(n_regions, -np.inf, dtype=np.float64)
    for offset in range(window_size):
        indices = np.arange(values.size) + offset
        np.maximum.at(out, indices, values)
    return np.where(np.isfinite(out), out, 0.0)


def maximum_possible_gain(n_regions: int) -> float:
    """Entropy of a maximally uncertain band, used to normalise gains for display."""
    return float(n_regions * np.log(2.0))
