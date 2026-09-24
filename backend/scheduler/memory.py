"""Bounded, observation-derived episodic context → next-observation memory."""

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Episode:
    band: int
    step: int
    pattern: tuple[int, ...]
    outcome: int


class AssociativeMemory:
    def __init__(self, bands: int, capacity: int = 512):
        self.bands = bands
        self.history = [deque(maxlen=6) for _ in range(bands)]
        self.episodes: deque[Episode] = deque(maxlen=capacity)

    def update(self, band: int, hit: bool, step: int):
        history = self.history[band]
        if len(history) >= 4:
            self.episodes.append(Episode(band, step, tuple(history)[-4:], int(hit)))
        history.append(int(hit))

    def recall_all(self, step: int) -> tuple[np.ndarray, list[dict]]:
        evidence = np.zeros(self.bands)
        matches = []
        episodes = list(self.episodes)[-160:]
        if not episodes:
            return evidence, matches
        patterns = np.array([e.pattern for e in episodes])
        locations = np.array([e.band for e in episodes])
        times = np.array([e.step for e in episodes])
        outcomes = np.array([e.outcome for e in episodes])
        for band in range(self.bands):
            if len(self.history[band]) < 4:
                continue
            pattern = np.array(tuple(self.history[band])[-4:])
            similarity = np.mean(patterns == pattern, axis=1)
            weights = similarity**4 * np.exp(-abs(locations - band) / max(1, self.bands / 3)) * np.exp(-(step - times) / 240)
            weights[similarity < 0.75] = 0
            if np.count_nonzero(weights) < 3 or weights.sum() < 1:
                continue
            outcome = float(np.dot(weights, outcomes) / weights.sum())
            best = int(np.argmax(weights))
            # Retrieval is soft evidence, bounded independently of memory size.
            evidence[band] = max(0, outcome - 0.45) * float(similarity[best])
            if evidence[band] > 0.05:
                matches.append({"band": band, "similarity": round(float(similarity[best]), 3), "previous_step": episodes[best].step, "previous_outcome": "HIT" if episodes[best].outcome else "MISS", "expected_hit": round(outcome, 4), "pattern": pattern.tolist(), "support": int(np.count_nonzero(weights)), "contribution": round(float(evidence[band]) * 0.28, 4)})
        return evidence, sorted(matches, key=lambda m: m["contribution"], reverse=True)[:8]
