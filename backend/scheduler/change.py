"""Two-sided observation-time CUSUM. Unobserved cells are never treated as misses."""

import numpy as np


class ChangeDetector:
    def __init__(self, bands: int, threshold: float = 2.5, slack: float = 0.12):
        self.positive = np.zeros(bands)
        self.negative = np.zeros(bands)
        self.counts = np.zeros(bands, dtype=int)
        self.last_change = np.full(bands, -1000)
        self.threshold = threshold
        self.slack = slack

    def update(self, band: int, value: float, expected: float, step: int) -> dict | None:
        residual = value - expected
        self.positive[band] = max(0, self.positive[band] + residual - self.slack)
        self.negative[band] = max(0, self.negative[band] - residual - self.slack)
        self.counts[band] += 1
        score = max(self.positive[band], self.negative[band])
        if self.counts[band] >= 5 and score > self.threshold and step - self.last_change[band] > 8:
            direction = "activity increased" if self.positive[band] > self.negative[band] else "activity decreased"
            self.positive[band] = self.negative[band] = 0
            self.last_change[band] = step
            return {"band": band, "step": step, "score": round(float(score), 4), "direction": direction}
        return None

    def priority(self, step: int):
        return np.exp(-np.maximum(0, step - self.last_change) / 14)

    def scores(self):
        return np.maximum(self.positive, self.negative) / self.threshold
