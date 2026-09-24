"""Probabilistic belief over unobserved regions.

Each region is a two-state Markov chain — active or free — whose transition
rates are estimated online from that region's own observation history.  The
filter runs the standard predict/update cycle, but only ever updates the regions
the receiver actually paid to observe; everything else is *predicted forward*,
which is what makes belief decay toward the region's stationary rate when it has
not been visited for a while.

The measurement update uses the measured margin rather than the binary detection
flag.  Under a flat prior on the true margin, the probability that a measurement
``m`` came from an occupied cell is ``Phi(m / sigma)``, so the likelihood ratio
is ``Phi / (1 - Phi)`` and a marginal +0.3 dB reading moves belief far less than
a decisive +9 dB one.  Confidence is therefore earned by the measurement, not
asserted.

Uncertainty is reported as a variance decomposition:

* *aleatoric* — ``b (1 - b)``, the irreducible Bernoulli variance of the state;
* *epistemic* — variance contributed by the Beta posteriors over the transition
  rates, accumulated over every step since the region was last observed.

Splitting them is what lets the UI distinguish "probably active, and we know it"
from "probably active, but we are guessing".
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import norm

from aamsx.contracts.observation import Observation

EPSILON = 1e-9


def binary_entropy(probability: np.ndarray | float) -> np.ndarray:
    """Shannon entropy of a Bernoulli variable, in nats."""
    p = np.clip(np.asarray(probability, dtype=np.float64), EPSILON, 1.0 - EPSILON)
    return -(p * np.log(p) + (1.0 - p) * np.log1p(-p))


@dataclass(slots=True)
class BeliefConfig:
    prior_activity: float = 0.15
    """Initial belief before any observation, and the prior mean for p_on."""

    prior_strength: float = 2.0
    """Pseudo-counts behind the transition-rate priors (weak on purpose)."""

    noise_db: float = 1.0
    """Receiver noise assumed by the measurement likelihood."""

    discount: float = 0.997
    """Per-step discount on transition counts, so stale evidence fades."""

    change_discount: float = 0.5
    """Extra one-off discount applied when a change point fires."""

    min_rate: float = 1e-3
    max_rate: float = 0.9


class BeliefFilter:
    """Per-region two-state filter with online transition-rate estimation."""

    def __init__(self, n_regions: int, config: BeliefConfig | None = None) -> None:
        self.n_regions = int(n_regions)
        self.config = config or BeliefConfig()
        self.reset()

    # ---- lifecycle -----------------------------------------------------------

    def reset(self) -> None:
        cfg = self.config
        n = self.n_regions
        self.belief = np.full(n, cfg.prior_activity, dtype=np.float64)
        # Beta(alpha, beta) counts for the two transition rates.
        self.on_alpha = np.full(n, cfg.prior_strength * cfg.prior_activity)
        self.on_beta = np.full(n, cfg.prior_strength * (1.0 - cfg.prior_activity))
        self.off_alpha = np.full(n, cfg.prior_strength * (1.0 - cfg.prior_activity))
        self.off_beta = np.full(n, cfg.prior_strength * cfg.prior_activity)
        self.epistemic = np.zeros(n, dtype=np.float64)
        self.steps_since_seen = np.zeros(n, dtype=np.int32)
        self.observation_counts = np.zeros(n, dtype=np.int32)
        self.detection_counts = np.zeros(n, dtype=np.int32)
        self.last_state = np.full(n, np.nan)  # last posterior for the observed region
        self.step = 0
        # Running estimates of the typical margin either side of the boundary,
        # used to price information gain. Seeded with sane receiver-scale values.
        self._margin_positive = 4.0
        self._margin_negative = -4.0
        self._margin_weight = 1.0

    # ---- derived quantities --------------------------------------------------

    @property
    def p_on(self) -> np.ndarray:
        rate = self.on_alpha / np.maximum(self.on_alpha + self.on_beta, EPSILON)
        return np.clip(rate, self.config.min_rate, self.config.max_rate)

    @property
    def p_off(self) -> np.ndarray:
        rate = self.off_alpha / np.maximum(self.off_alpha + self.off_beta, EPSILON)
        return np.clip(rate, self.config.min_rate, self.config.max_rate)

    @property
    def stationary(self) -> np.ndarray:
        """Long-run activity rate each region's estimated chain converges to."""
        on, off = self.p_on, self.p_off
        return on / np.maximum(on + off, EPSILON)

    @property
    def hit_rate(self) -> np.ndarray:
        return self.detection_counts / np.maximum(self.observation_counts, 1)

    @property
    def staleness(self) -> np.ndarray:
        """Time since last observed, squashed into [0, 1) with a 1-region-visit scale."""
        scale = max(1.0, float(self.n_regions))
        return 1.0 - np.exp(-self.steps_since_seen / scale)

    @property
    def uncertainty(self) -> np.ndarray:
        """Total normalised predictive variance in [0, 1]."""
        aleatoric = self.belief * (1.0 - self.belief)
        return np.clip(4.0 * (aleatoric + self.epistemic), 0.0, 1.0)

    @property
    def aleatoric(self) -> np.ndarray:
        return np.clip(4.0 * self.belief * (1.0 - self.belief), 0.0, 1.0)

    @property
    def epistemic_normalised(self) -> np.ndarray:
        return np.clip(4.0 * self.epistemic, 0.0, 1.0)

    def entropy(self) -> float:
        """Total belief entropy over the whole band, in nats."""
        return float(binary_entropy(self.belief).sum())

    def sensitivity_specificity(self) -> tuple[float, float]:
        """Detection probability for an occupied cell, and false-alarm probability.

        Both are derived from the receiver noise and the *measured* typical margin
        either side of the threshold, so they track the recording rather than
        being tuned by hand.
        """
        sigma = max(self.config.noise_db, 1e-6)
        sensitivity = float(norm.cdf(self._margin_positive / sigma))
        false_alarm = float(norm.cdf(self._margin_negative / sigma))
        return (
            float(np.clip(sensitivity, 0.5 + 1e-6, 1.0 - 1e-6)),
            float(np.clip(false_alarm, 1e-6, 0.5 - 1e-6)),
        )

    # ---- the filter ----------------------------------------------------------

    def predict(self) -> None:
        """Advance every region one step through its own estimated Markov chain."""
        on, off = self.p_on, self.p_off
        previous = self.belief
        self.belief = np.clip(previous * (1.0 - off) + (1.0 - previous) * on, EPSILON, 1 - EPSILON)

        # Propagate transition-rate uncertainty. The predicted belief is linear in
        # p_on and p_off, so first-order variance propagation is exact for the mean
        # and a good approximation for the variance.
        on_total = np.maximum(self.on_alpha + self.on_beta, EPSILON)
        off_total = np.maximum(self.off_alpha + self.off_beta, EPSILON)
        var_on = (self.on_alpha * self.on_beta) / (on_total**2 * (on_total + 1.0))
        var_off = (self.off_alpha * self.off_beta) / (off_total**2 * (off_total + 1.0))
        self.epistemic += (1.0 - previous) ** 2 * var_on + previous**2 * var_off
        self.epistemic = np.minimum(self.epistemic, 0.25)

        self.steps_since_seen += 1
        self.on_alpha *= self.config.discount
        self.on_beta *= self.config.discount
        self.off_alpha *= self.config.discount
        self.off_beta *= self.config.discount
        self.step += 1

    def update(self, observation: Observation) -> np.ndarray:
        """Fold one window of measurements in. Returns the surprise per region, in nats."""
        if not observation.available:
            return np.zeros(observation.window_size, dtype=np.float64)
        regions = observation.regions
        sigma = max(self.config.noise_db, 1e-6)
        probability_occupied = np.clip(
            norm.cdf(observation.measured_db.astype(np.float64) / sigma), EPSILON, 1.0 - EPSILON
        )

        prior = self.belief[regions]
        # Bayes in odds form: posterior_odds = prior_odds * likelihood_ratio.
        likelihood_ratio = probability_occupied / (1.0 - probability_occupied)
        prior_odds = prior / (1.0 - prior)
        posterior = (prior_odds * likelihood_ratio) / (1.0 + prior_odds * likelihood_ratio)
        posterior = np.clip(posterior, EPSILON, 1.0 - EPSILON)

        # Bayesian surprise: how badly the prior predicted what arrived.
        evidence = prior * probability_occupied + (1.0 - prior) * (1.0 - probability_occupied)
        surprise = -np.log(np.clip(evidence, EPSILON, 1.0))

        self._learn_transitions(regions, posterior)
        self.belief[regions] = posterior
        self.epistemic[regions] = 0.0
        self.steps_since_seen[regions] = 0
        self.observation_counts[regions] += 1
        self.detection_counts[regions] += observation.detected.astype(np.int32)
        self.last_state[regions] = posterior
        self._track_margins(observation)
        return surprise

    def _learn_transitions(self, regions: np.ndarray, posterior: np.ndarray) -> None:
        """Accumulate soft transition counts using consecutive posteriors.

        Only regions with a previous posterior contribute, and the counts are
        weighted by the (soft) previous state, so a marginal reading contributes
        proportionally little evidence about the transition rates.
        """
        previous = self.last_state[regions]
        known = np.isfinite(previous)
        if not np.any(known):
            return
        was, now = previous[known], posterior[known]
        index = regions[known]
        # From free -> active informs p_on; from active -> free informs p_off.
        np.add.at(self.on_alpha, index, (1.0 - was) * now)
        np.add.at(self.on_beta, index, (1.0 - was) * (1.0 - now))
        np.add.at(self.off_alpha, index, was * (1.0 - now))
        np.add.at(self.off_beta, index, was * now)

    def _track_margins(self, observation: Observation) -> None:
        """Update the running estimate of the typical margin either side of zero."""
        measured = observation.measured_db.astype(np.float64)
        decay = 0.98
        positive = measured[measured > 0.0]
        negative = measured[measured <= 0.0]
        if positive.size:
            self._margin_positive = decay * self._margin_positive + (1 - decay) * float(
                positive.mean()
            )
        if negative.size:
            self._margin_negative = decay * self._margin_negative + (1 - decay) * float(
                negative.mean()
            )
        self._margin_weight = min(1.0, self._margin_weight + 0.01)

    def on_change_detected(self) -> None:
        """React to a change point: discount learned rates and re-inflate uncertainty."""
        factor = self.config.change_discount
        self.on_alpha *= factor
        self.on_beta *= factor
        self.off_alpha *= factor
        self.off_beta *= factor
        self.epistemic = np.minimum(self.epistemic + 0.05, 0.25)
        self.last_state[:] = np.nan

    def snapshot(self) -> dict[str, list[float]]:
        """Compact, JSON-safe view used by the API and the belief map."""
        return {
            "belief": [round(float(v), 5) for v in self.belief],
            "uncertainty": [round(float(v), 5) for v in self.uncertainty],
            "aleatoric": [round(float(v), 5) for v in self.aleatoric],
            "epistemic": [round(float(v), 5) for v in self.epistemic_normalised],
            "staleness": [round(float(v), 5) for v in self.staleness],
            "steps_since_seen": [int(v) for v in self.steps_since_seen],
            "hit_rate": [round(float(v), 5) for v in self.hit_rate],
            "observations": [int(v) for v in self.observation_counts],
        }
