"""Discounted Beta-Bernoulli beliefs and exact one-step mutual information."""

import numpy as np
from scipy.special import digamma

from backend.contracts import BandObservation


class Belief:
    def __init__(self, bands: int, discount: float = 0.989):
        self.alpha = np.ones(bands)
        self.beta = np.ones(bands)
        self.counts = np.zeros(bands, dtype=int)
        self.last_visit = np.full(bands, -1, dtype=int)
        self.last_hit = np.full(bands, -1, dtype=int)
        self.miss_streak = np.zeros(bands)
        self.discount = discount
        self.last_step = 0

    def advance(self, step: int):
        decay = self.discount ** max(0, step - self.last_step)
        self.alpha = 1 + (self.alpha - 1) * decay
        self.beta = 1 + (self.beta - 1) * decay
        self.last_step = step

    @property
    def mean(self):
        return self.alpha / (self.alpha + self.beta)

    @property
    def uncertainty(self):
        total = self.alpha + self.beta
        variance = self.alpha * self.beta / (total * total * (total + 1))
        return np.sqrt(12 * variance).clip(0, 1)

    @property
    def information_gain(self):
        total = self.alpha + self.beta
        p = self.mean
        entropy = -(p * np.log(p) + (1 - p) * np.log(1 - p))
        expected_entropy = digamma(total + 1) - p * digamma(self.alpha + 1) - (1 - p) * digamma(self.beta + 1)
        return np.maximum(0, entropy - expected_entropy)

    def soften(self, band: int):
        self.alpha[band] = 1 + (self.alpha[band] - 1) * 0.2
        self.beta[band] = 1 + (self.beta[band] - 1) * 0.2

    def update(self, step: int, value: BandObservation, weighted: bool = True):
        if not value.valid:
            return
        b = value.band
        weight = 0.5 + 0.5 * value.confidence if weighted else 1.0
        self.alpha[b] += weight * value.detected
        self.beta[b] += weight * (not value.detected)
        self.counts[b] += 1
        self.last_visit[b] = step
        self.miss_streak[b] = 0 if value.detected else min(10, self.miss_streak[b] + 1)
        if value.detected:
            self.last_hit[b] = step

    def snapshot(self, step: int):
        return {
            "probability": self.mean.round(5).tolist(),
            "uncertainty": self.uncertainty.round(5).tolist(),
            "information_gain": self.information_gain.round(6).tolist(),
            "observations": self.counts.tolist(),
            "last_visit": self.last_visit.tolist(),
            "age": np.where(self.last_visit >= 0, step - self.last_visit, step + 1).tolist(),
        }
