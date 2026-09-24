"""Thompson sampling, stationary and non-stationary.

Both keep a Beta posterior per *region* — not per window — because that is the
level at which evidence arrives: one dwell on a four-region window updates four
posteriors, and every overlapping window benefits.  The window score is the sum of
its regions' sampled rates, so the policy is still doing Thompson sampling over
actions, just with an action space that shares structure properly.

``NonStationaryTS`` adds the two standard non-stationary corrections, and nothing
else: geometric discounting of accumulated counts, and an optional hard discount
when a change point fires.  Keeping it minimal is deliberate — it is the ablation
baseline that isolates exactly what memory, information gain and periodicity add
on top.
"""

from __future__ import annotations

import numpy as np

from aamsx.contracts.observation import ActionProposal, DecisionContext, Feedback
from aamsx.schedulers.base import BaseScheduler, SchedulerSetup, register

PRIOR_ALPHA = 1.0
PRIOR_BETA = 1.0


class _RegionBetaPolicy(BaseScheduler):
    """Shared Beta-Bernoulli bookkeeping over regions."""

    stochastic = True

    def __init__(self, discount: float = 1.0, change_discount: float = 1.0) -> None:
        super().__init__()
        self.discount = float(discount)
        self.change_discount = float(change_discount)

    def reset(self, setup: SchedulerSetup) -> None:
        super().reset(setup)
        n = setup.n_regions
        self.alpha = np.full(n, PRIOR_ALPHA)
        self.beta = np.full(n, PRIOR_BETA)
        self._changes_seen = 0

    def sample_rates(self) -> np.ndarray:
        return self.rng.beta(self.alpha, self.beta)

    @property
    def posterior_mean(self) -> np.ndarray:
        return self.alpha / (self.alpha + self.beta)

    @property
    def effective_samples(self) -> np.ndarray:
        return self.alpha + self.beta - (PRIOR_ALPHA + PRIOR_BETA)

    def update(self, feedback: Feedback) -> None:
        if self.discount < 1.0:
            # Geometric forgetting keeps the posterior tracking a moving target;
            # counts decay toward the prior instead of accumulating forever.
            self.alpha = PRIOR_ALPHA + (self.alpha - PRIOR_ALPHA) * self.discount
            self.beta = PRIOR_BETA + (self.beta - PRIOR_BETA) * self.discount
        observation = feedback.observation
        if observation.available:
            detected = observation.detected.astype(np.float64)
            self.alpha[observation.regions] += detected
            self.beta[observation.regions] += 1.0 - detected
        self.step += 1

    def on_change(self) -> None:
        if self.change_discount < 1.0:
            self.alpha = PRIOR_ALPHA + (self.alpha - PRIOR_ALPHA) * self.change_discount
            self.beta = PRIOR_BETA + (self.beta - PRIOR_BETA) * self.change_discount
            self._changes_seen += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "name": self.name,
            "step": self.step,
            "mean_rate": round(float(self.posterior_mean.mean()), 5),
            "max_rate": round(float(self.posterior_mean.max()), 5),
            "effective_samples": round(float(self.effective_samples.mean()), 3),
            "changes_seen": self._changes_seen,
        }


@register
class ThompsonSamplingScheduler(_RegionBetaPolicy):
    """Stationary Beta-Bernoulli Thompson sampling."""

    name = "thompson"
    display_name = "Thompson Sampling"
    family = "bandit"
    description = (
        "Beta-Bernoulli Thompson sampling over regions. Explores in proportion to "
        "posterior uncertainty, but assumes the environment never changes — evidence "
        "from an hour ago counts as much as evidence from a moment ago."
    )

    def __init__(self) -> None:
        super().__init__(discount=1.0, change_discount=1.0)

    def select(self, context: DecisionContext) -> ActionProposal:
        rates = self.sample_rates()
        window = self.config.window_size
        values = self.window_sum(rates, window) / window
        anchor = int(np.argmax(values))
        chosen = slice(anchor, anchor + window)
        return self.proposal(
            anchor,
            value=float(values[anchor]),
            factors={
                "sampled_rate": float(rates[chosen].mean()),
                "posterior_mean": float(self.posterior_mean[chosen].mean()),
                "evidence": float(self.effective_samples[chosen].mean()),
            },
            per_region_value=rates,
            notes=("posterior sample, stationary prior",),
        )


@register
class NonStationaryTSScheduler(_RegionBetaPolicy):
    """Discounted Thompson sampling with change-triggered forgetting."""

    name = "nts"
    display_name = "Non-Stationary TS"
    family = "bandit"
    description = (
        "Thompson sampling with geometric discounting of past evidence plus an extra "
        "discount when the change detector fires. Tracks a moving environment, but has "
        "no memory of environments it has already seen — it can only forget, never recall."
    )

    def __init__(self, discount: float = 0.995, change_discount: float = 0.4) -> None:
        super().__init__(discount=discount, change_discount=change_discount)

    def select(self, context: DecisionContext) -> ActionProposal:
        if context.change_flag:
            self.on_change()
        rates = self.sample_rates()
        window = self.config.window_size
        values = self.window_sum(rates, window) / window
        anchor = int(np.argmax(values))
        chosen = slice(anchor, anchor + window)
        notes: tuple[str, ...] = ("discounted posterior sample",)
        if context.change_flag:
            notes = (*notes, "change detected: stale evidence discounted")
        return self.proposal(
            anchor,
            value=float(values[anchor]),
            factors={
                "sampled_rate": float(rates[chosen].mean()),
                "posterior_mean": float(self.posterior_mean[chosen].mean()),
                "evidence": float(self.effective_samples[chosen].mean()),
                "change_score": float(context.change_score),
            },
            per_region_value=rates,
            notes=notes,
        )
