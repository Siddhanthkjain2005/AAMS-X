"""Engineered temporal state encoder.

The default encoder is deliberately hand-written rather than learned.  Every
feature is named, bounded and inspectable, which matters for two reasons: the
decision inspector can explain a choice in terms a person can check, and the
platform has no checkpoint to lose.  The optional GRU encoder in
:mod:`aamsx.features.neural` consumes exactly this vector, so enabling it is an
upgrade rather than a rewrite — and disabling it costs nothing.

Two vectors come out:

``temporal_features``
    ``GLOBAL_FEATURES`` scalars describing the episode's current regime. This is
    what the action-value model conditions on.

``context_vector``
    the same scalars followed by a *spatial* signature — belief, recent hit rate and
    recent signal level, each downsampled to ``PROFILE_BINS`` bands. Associative
    memory keys on this, because recognising "this environment again" requires
    knowing the shape of the band, not only its summary statistics.

    The two observation-derived profiles are deliberately the *decaying* ones from
    :class:`~aamsx.features.buffer.TemporalBuffer`. Episode-cumulative profiles
    would still describe the previous regime long after a shift, which is precisely
    when the memory needs to tell the regimes apart.

    They are also *evidence-shrunk*: a region the receiver has not visited for a
    long time is pulled toward the mean of the regions it has visited, so it adds
    nothing distinctive to the key. Without that, a stale region's leftover value
    is read as a real difference between two environments, and a returning
    environment fails to be recognised simply because the policy happened to be
    looking somewhere else this time.
"""

from __future__ import annotations

import itertools

import numpy as np

from aamsx.belief.filter import BeliefFilter, binary_entropy
from aamsx.features.buffer import TemporalBuffer

GLOBAL_FEATURES: tuple[str, ...] = (
    "mean_belief",
    "max_belief",
    "belief_entropy",
    "belief_concentration",
    "mean_uncertainty",
    "mean_epistemic",
    "mean_staleness",
    "coverage",
    "recent_hit_rate",
    "recent_activity_variance",
    "switch_rate",
    "change_score",
    "steps_since_change",
    "period_strength",
    "budget_fraction",
    "progress",
    "mean_reward",
    "reward_trend",
)

PROFILE_BINS = 16
CONTEXT_DIM = len(GLOBAL_FEATURES) + 3 * PROFILE_BINS

EVIDENCE_TAU = 120.0
"""Steps after which an unobserved region's profile entry is fully discounted."""


def _downsample(values: np.ndarray, bins: int) -> np.ndarray:
    """Average ``values`` into ``bins`` contiguous bands."""
    array = np.asarray(values, dtype=np.float64)
    if array.size == bins:
        return array
    edges = np.linspace(0, array.size, bins + 1).astype(int)
    return np.array(
        [
            array[start:stop].mean() if stop > start else 0.0
            for start, stop in itertools.pairwise(edges)
        ]
    )


def _shrink_to_evidence(
    profile: np.ndarray, steps_since_seen: np.ndarray, *, tau: float = EVIDENCE_TAU
) -> np.ndarray:
    """Pull stale regions toward the mean of the freshly observed ones."""
    values = np.asarray(profile, dtype=np.float64)
    weight = np.exp(-np.asarray(steps_since_seen, dtype=np.float64) / max(tau, 1e-9))
    total = float(weight.sum())
    neutral = float((weight * values).sum() / total) if total > 1e-9 else 0.0
    return weight * values + (1.0 - weight) * neutral


def _gini(values: np.ndarray) -> float:
    array = np.asarray(values, dtype=np.float64)
    total = float(array.sum())
    if array.size == 0 or total <= 0.0:
        return 0.0
    n = array.size
    ordered = np.sort(array)
    index = np.arange(1, n + 1)
    return float((2.0 * (index * ordered).sum()) / (n * total) - (n + 1.0) / n)


def encode(
    *,
    belief: BeliefFilter,
    buffer: TemporalBuffer,
    change_score: float,
    steps_since_change: int,
    period_strength: float,
    budget_fraction: float,
    progress: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute ``(temporal_features, context_vector)``.

    Every component is bounded in roughly [0, 1] so that cosine similarity in
    memory retrieval is not dominated by one loud dimension.
    """
    n_regions = belief.n_regions
    rewards = buffer.recent_rewards(32)
    mean_reward = float(rewards.mean()) if rewards.size else 0.0
    if rewards.size >= 8:
        half = rewards.size // 2
        trend = float(rewards[half:].mean() - rewards[:half].mean())
    else:
        trend = 0.0

    entropy = float(binary_entropy(belief.belief).sum() / (n_regions * np.log(2.0)))
    entries = buffer.recent(1)
    window_size = entries[-1].window_size if entries else 1
    # Detection counts per step live in [0, window_size], so their variance is
    # normalised by window_size^2 before being squashed.
    activity_variance = buffer.recent_variance(32) / float(max(window_size, 1) ** 2)

    features = np.array(
        [
            float(belief.belief.mean()),
            float(belief.belief.max()),
            entropy,
            _gini(belief.belief),
            float(belief.uncertainty.mean()),
            float(belief.epistemic_normalised.mean()),
            float(belief.staleness.mean()),
            buffer.coverage(),
            buffer.recent_hit_rate(32),
            float(np.tanh(activity_variance)),
            buffer.switch_rate(32),
            float(np.clip(change_score, 0.0, 1.0)),
            float(1.0 - np.exp(-steps_since_change / max(n_regions, 1))),
            float(np.clip(period_strength, 0.0, 1.0)),
            float(np.clip(budget_fraction, 0.0, 1.0)),
            float(np.clip(progress, 0.0, 1.0)),
            float(np.tanh(mean_reward)),
            float(np.tanh(trend)),
        ],
        dtype=np.float32,
    )
    stale = belief.steps_since_seen
    context = np.concatenate(
        [
            features,
            _downsample(belief.stationary, PROFILE_BINS).astype(np.float32),
            _downsample(_shrink_to_evidence(buffer.recent_hit_profile, stale), PROFILE_BINS).astype(
                np.float32
            ),
            _downsample(
                _shrink_to_evidence(buffer.recent_level_profile, stale), PROFILE_BINS
            ).astype(np.float32),
        ]
    ).astype(np.float32)
    return features, context


def describe(features: np.ndarray) -> dict[str, float]:
    """Name the feature vector for the UI's inspector panel."""
    return {
        name: round(float(value), 5) for name, value in zip(GLOBAL_FEATURES, features, strict=True)
    }
