"""The receiver observation model.

This is the only path from hidden state to a scheduler, and the only place where
measurement error is introduced.  It stays deliberately thin: real e-CALLISTO
data already contains the receiver's own noise, and the noise added here models
the *additional* uncertainty of a short dwell on a retuned front end rather than
pretending to re-derive physics the archive already measured.
"""

from __future__ import annotations

import numpy as np
from scipy.special import erf

from aamsx.contracts.scenario import ReceiverSpec


class ReceiverModel:
    """Turns per-region truth margins into noisy, costed observations."""

    def __init__(self, spec: ReceiverSpec, n_regions: int) -> None:
        if spec.window_size < 1 or spec.window_size > n_regions:
            raise ValueError(
                f"window_size {spec.window_size} must be within 1..{n_regions} regions"
            )
        self.spec = spec
        self.n_regions = int(n_regions)

    @property
    def n_anchors(self) -> int:
        """Number of distinct contiguous windows the receiver can tune to."""
        return self.n_regions - self.spec.window_size + 1

    def window(self, anchor: int) -> np.ndarray:
        """The contiguous region indices covered by tuning to ``anchor``."""
        clamped = int(np.clip(anchor, 0, self.n_anchors - 1))
        return np.arange(clamped, clamped + self.spec.window_size, dtype=np.int32)

    def retune_fraction(self, anchor: int, previous_anchor: int | None) -> float:
        """How far across the band this retune moves, normalised to [0, 1]."""
        if previous_anchor is None or self.n_anchors <= 1:
            return 0.0
        return abs(int(anchor) - int(previous_anchor)) / (self.n_anchors - 1)

    def cost(self, anchor: int, previous_anchor: int | None) -> float:
        """Sensing cost: a fixed dwell cost plus a retuning penalty."""
        return float(
            self.spec.cost_per_observation
            + self.spec.switch_cost * self.retune_fraction(anchor, previous_anchor)
        )

    def cost_per_anchor(self, previous_anchor: int | None) -> np.ndarray:
        """``(n_anchors,)`` cost vector, so a scheduler can price every option."""
        anchors = np.arange(self.n_anchors, dtype=np.float64)
        if previous_anchor is None or self.n_anchors <= 1:
            moved = np.zeros_like(anchors)
        else:
            moved = np.abs(anchors - float(previous_anchor)) / (self.n_anchors - 1)
        return self.spec.cost_per_observation + self.spec.switch_cost * moved

    def effective_noise_db(self, retune_fraction: float) -> float:
        """Noise on this dwell, inflated by any settling penalty after a big retune."""
        return float(self.spec.noise_db + self.spec.settling_penalty_db * retune_fraction)

    def measure(
        self, true_margin_db: np.ndarray, *, noise_db: float, rng: np.random.Generator
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Observe a window.

        Returns ``(measured_db, detected, confidence)``.  ``confidence`` is the
        probability that the sign of the measurement is correct under Gaussian
        noise — ``erf(|m| / (sigma * sqrt2))`` — so it is a real statement about
        measurement quality, not a decorative score.
        """
        sigma = max(float(noise_db), 1e-6)
        measured = true_margin_db.astype(np.float32) + rng.normal(
            0.0, sigma, size=true_margin_db.shape
        ).astype(np.float32)
        detected = measured > 0.0
        confidence = erf(np.abs(measured) / (sigma * np.sqrt(2.0))).astype(np.float32)
        return measured, detected, confidence
