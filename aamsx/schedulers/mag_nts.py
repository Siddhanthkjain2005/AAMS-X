"""MAG-NTS — Memory-Augmented, Information-Guided Non-Stationary Thompson Sampling.

The primary scheduler.  Its action value is an explicit weighted sum of eight named
terms, each normalised to roughly [0, 1] so the weights mean something and the
decision inspector can show a decomposition a person can check:

    value(a) =  w_D * detection        sampled activity rate, discounted posterior
              + w_I * information      expected entropy reduction, in bits
              + w_M * memory           retrieved preference x context similarity
              + w_P * periodicity      phase-conditional recurrence lift
              + w_U * uncertainty      posterior + epistemic, gated by change state
              + w_R * recency          staleness of the region
              - w_C * cost             sensing and retuning cost
              - w_S * switching        distance moved across the band

Three couplings make it non-stationary rather than merely weighted.

**Change gating.**  When the change detector fires, accumulated evidence is
discounted and the uncertainty weight is temporarily boosted, so exploration rises
exactly when the world stopped being what the policy learned.

**Memory gating.**  The memory term is scaled by retrieval similarity, so a
recognised context pulls hard and an unfamiliar one contributes nothing.  This is
what lets the policy skip rediscovery when an environment returns.

**Budget pressure.**  As remaining budget falls behind remaining horizon, the
exploratory terms (information, uncertainty, recency) are attenuated and detection
dominates: with two observations left, curiosity is a luxury.

No term is allowed to dominate unconditionally, which is checked by
``tests/test_mag_nts.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from operator import add

import numpy as np

from aamsx.contracts.observation import FACTOR_ORDER, ActionProposal, DecisionContext, Feedback
from aamsx.schedulers.base import BaseScheduler, SchedulerSetup, register

LOG2 = float(np.log(2.0))


@dataclass(frozen=True, slots=True)
class MagWeights:
    """Action-value weights.

    The defaults are not hand-picked.  ``scripts/tune_mag_nts.py`` runs a random
    search over 44 candidate weightings across the four **training-split** scenario
    families, three seeds each, and selects by a rule fixed before the search:
    highest win rate against the non-stationary Thompson baseline, ties broken by
    mean advantage.  These weights won 12 of 12 training episodes with a mean
    advantage of +28.6 reward.  The complete search, including the candidates that
    scored higher on raw advantage but lost somewhere, is recorded in
    ``data/index/mag_nts_tuning.json``.

    Validation and unseen scenarios were never consulted during tuning, which is
    what keeps the generalisation result in EXPERIMENTS.md meaningful.

    They stay exposed in the Experiment Lab because no weighting is universally
    correct, and sensitivity analysis is part of the deliverable.
    """

    detection: float = 0.94
    information: float = 0.07
    memory: float = 0.57
    periodicity: float = 0.27
    uncertainty: float = 0.23
    recency: float = 0.17
    cost: float = 0.29
    switching: float = 0.10

    def to_dict(self) -> dict[str, float]:
        return {
            "detection": self.detection,
            "information": self.information,
            "memory": self.memory,
            "periodicity": self.periodicity,
            "uncertainty": self.uncertainty,
            "recency": self.recency,
            "cost": self.cost,
            "switching": self.switching,
        }


@register
class MagNtsScheduler(BaseScheduler):
    """The full memory-augmented, information-guided non-stationary policy."""

    name = "mag-nts"
    display_name = "MAG-NTS"
    family = "adaptive"
    stochastic = True
    uses_memory = True
    uses_information_gain = True
    description = (
        "Memory-Augmented, Information-Guided Non-Stationary Thompson Sampling. "
        "Combines a discounted posterior over activity with expected information gain, "
        "retrieved context memory, measured recurrence, uncertainty-aware exploration "
        "and budget pressure — and reports the contribution of every term."
    )

    PRIOR_ALPHA = 1.0
    PRIOR_BETA = 1.0

    def __init__(
        self,
        weights: MagWeights | None = None,
        *,
        discount: float = 0.995,
        change_discount: float = 0.4,
        change_boost: float = 0.8,
    ) -> None:
        super().__init__()
        self.weights = weights or MagWeights()
        self.discount = float(discount)
        self.change_discount = float(change_discount)
        self.change_boost = float(change_boost)

    def reset(self, setup: SchedulerSetup) -> None:
        super().reset(setup)
        n = setup.n_regions
        self.alpha = np.full(n, self.PRIOR_ALPHA)
        self.beta = np.full(n, self.PRIOR_BETA)
        self.changes_seen = 0
        self.memory_pulls = 0
        self._last_factors: dict[str, float] = {}

    @property
    def posterior_mean(self) -> np.ndarray:
        return self.alpha / (self.alpha + self.beta)

    # ---- decision ------------------------------------------------------------

    def select(self, context: DecisionContext) -> ActionProposal:
        setup = self.config
        window = setup.window_size
        flags = setup.flags
        notes: list[str] = []

        if context.change_flag and flags.change_detection:
            self._discount_on_change()
            self.changes_seen += 1
            notes.append("change detected: evidence discounted, exploration raised")

        sampled = self.rng.beta(self.alpha, self.beta)

        budget_pressure = self._budget_pressure(context)
        explore_gain = 1.0 - budget_pressure
        if flags.change_detection and flags.uncertainty_exploration:
            explore_gain += self.change_boost * float(np.clip(context.change_score, 0.0, 1.0))

        terms = self._terms(context, sampled, window, explore_gain, budget_pressure, notes)
        # reduce rather than sum(): the eight terms are always present, and folding them
        # keeps the result an array instead of "array or the int 0" for a reader (or a
        # type checker) who cannot see that the mapping is never empty.
        total = reduce(add, terms.values())
        anchor = int(np.argmax(total))
        per_region = self._per_region_value(total, setup.n_regions, window)

        factors = self._factors(context, sampled, anchor, window, terms, per_region)
        self._last_factors = factors
        if flags.memory and context.memory_similarity > 0.9:
            self.memory_pulls += 1
            notes.append(
                f"context recognised (similarity {context.memory_similarity:.2f}) — "
                "retrieved prior applied"
            )
        if budget_pressure > 0.5:
            notes.append(f"budget pressure {budget_pressure:.2f}: exploration attenuated")

        return self.proposal(
            anchor,
            value=float(total[anchor]),
            factors=factors,
            per_region_value=per_region,
            notes=tuple(notes),
            exploration_rate=float(np.clip(explore_gain, 0.0, 2.0)),
        )

    def _budget_pressure(self, context: DecisionContext) -> float:
        """How far behind the budget is, relative to the steps still to come."""
        remaining_steps = max(1, context.horizon - context.step)
        unit_cost = max(self.config.receiver.cost_per_observation, 1e-9)
        affordable = context.budget_remaining / unit_cost
        return float(np.clip(1.0 - affordable / remaining_steps, 0.0, 1.0))

    def _terms(
        self,
        context: DecisionContext,
        sampled: np.ndarray,
        window: int,
        explore_gain: float,
        budget_pressure: float,
        notes: list[str],
    ) -> dict[str, np.ndarray]:
        flags = self.config.flags
        weights = self.weights
        per_anchor = lambda values: self.window_sum(values, window) / window  # noqa: E731

        detection = weights.detection * per_anchor(sampled)

        if flags.information_gain:
            information = (
                weights.information
                * explore_gain
                * per_anchor(np.clip(context.information_gain / LOG2, 0.0, 1.0))
            )
        else:
            information = np.zeros_like(detection)

        if flags.memory and context.memory_prior is not None and context.memory_similarity > 0.0:
            prior = np.asarray(context.memory_prior, dtype=np.float64)
            span = float(prior.max() - prior.min())
            scaled = (prior - prior.min()) / span if span > 1e-9 else np.zeros_like(prior)
            memory = weights.memory * context.memory_similarity * per_anchor(scaled)
        else:
            memory = np.zeros_like(detection)

        periodicity = (
            weights.periodicity * per_anchor(context.periodicity_score)
            if flags.periodicity
            else np.zeros_like(detection)
        )
        uncertainty = (
            weights.uncertainty * explore_gain * per_anchor(context.uncertainty)
            if flags.uncertainty_exploration
            else np.zeros_like(detection)
        )
        recency = weights.recency * (1.0 - budget_pressure) * per_anchor(context.staleness)

        cost = np.asarray(context.sensing_cost, dtype=np.float64)
        anchors = detection.size
        cost_anchor = cost[:anchors] if cost.size >= anchors else np.zeros(anchors)
        peak = float(cost_anchor.max()) if cost_anchor.size else 0.0
        cost_term = -weights.cost * (cost_anchor / peak if peak > 0 else cost_anchor)

        switching = -weights.switching * self.switch_penalty(context)[:anchors]

        if not flags.temporal_encoder:
            notes.append("temporal encoder disabled: no regime features in play")

        return {
            "detection": detection,
            "information": information,
            "memory": memory,
            "periodicity": periodicity,
            "uncertainty": uncertainty,
            "recency": recency,
            "cost": cost_term,
            "switching": switching,
        }

    def _per_region_value(
        self, anchor_values: np.ndarray, n_regions: int, window: int
    ) -> np.ndarray:
        """Credit each region with the best window containing it, for the belief map."""
        out = np.full(n_regions, -np.inf)
        for offset in range(window):
            indices = np.arange(anchor_values.size) + offset
            np.maximum.at(out, indices, anchor_values)
        return np.where(np.isfinite(out), out, float(anchor_values.min()))

    def _factors(
        self,
        context: DecisionContext,
        sampled: np.ndarray,
        anchor: int,
        window: int,
        terms: dict[str, np.ndarray],
        per_region: np.ndarray,
    ) -> dict[str, float]:
        """The Decision Inspector payload: raw evidence plus weighted contributions."""
        chosen = slice(anchor, anchor + window)
        raw = {
            "predicted_activity": float(context.belief[chosen].mean()),
            "posterior_confidence": float(1.0 - context.uncertainty[chosen].mean()),
            "information_gain": float(context.information_gain[chosen].mean() / LOG2),
            "memory_similarity": float(context.memory_similarity),
            "periodicity_score": float(context.periodicity_score[chosen].mean()),
            "staleness": float(context.staleness[chosen].mean()),
            "uncertainty": float(context.uncertainty[chosen].mean()),
            "sensing_cost": float(context.sensing_cost[anchor]),
            "switching_penalty": float(self.switch_penalty(context)[anchor]),
        }
        contributions = {
            f"contribution.{key}": float(value[anchor]) for key, value in terms.items()
        }
        return {
            **{name: round(raw[name], 6) for name in FACTOR_ORDER},
            **{key: round(value, 6) for key, value in contributions.items()},
            "sampled_rate": round(float(sampled[chosen].mean()), 6),
            "steps_since_observed": float(context.steps_since_seen[anchor]),
            "steps_since_change": float(context.steps_since_change),
            "budget_pressure": round(self._budget_pressure(context), 6),
            "final_action_value": round(float(per_region[anchor]), 6),
        }

    # ---- learning ------------------------------------------------------------

    def _discount_on_change(self) -> None:
        self.alpha = self.PRIOR_ALPHA + (self.alpha - self.PRIOR_ALPHA) * self.change_discount
        self.beta = self.PRIOR_BETA + (self.beta - self.PRIOR_BETA) * self.change_discount

    def update(self, feedback: Feedback) -> None:
        self.alpha = self.PRIOR_ALPHA + (self.alpha - self.PRIOR_ALPHA) * self.discount
        self.beta = self.PRIOR_BETA + (self.beta - self.PRIOR_BETA) * self.discount
        observation = feedback.observation
        if observation.available:
            detected = observation.detected.astype(np.float64)
            self.alpha[observation.regions] += detected
            self.beta[observation.regions] += 1.0 - detected
        self.step += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "name": self.name,
            "step": self.step,
            "weights": self.weights.to_dict(),
            "discount": self.discount,
            "changes_seen": self.changes_seen,
            "memory_pulls": self.memory_pulls,
            "mean_rate": round(float(self.posterior_mean.mean()), 5),
            "max_rate": round(float(self.posterior_mean.max()), 5),
            "last_factors": self._last_factors,
        }
