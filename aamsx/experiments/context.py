"""The shared decision-context builder.

One instance owns every perception component — belief filter, observation buffer,
change detector, periodicity engine, associative memory, state encoder — and turns
them into the single :class:`~aamsx.contracts.observation.DecisionContext` handed to
whichever policy is running.

Two things follow from centralising it.  First, every scheduler in a comparison
sees *identical* inputs, so a win in the Algorithm Arena is about the policy and
not about a privately better state estimator.  Second, the ablation switches live
in exactly one place: turning memory off zeroes the memory field here, so
"MAG-NTS without memory" is provably the same program with one input removed.
"""

from __future__ import annotations

import numpy as np

from aamsx.belief.filter import BeliefConfig, BeliefFilter
from aamsx.change_detection.detectors import CompositeChangeDetector
from aamsx.contracts.observation import DecisionContext, Feedback, Observation
from aamsx.features import engineered
from aamsx.features.buffer import TemporalBuffer
from aamsx.information_gain.entropy import region_information_gain
from aamsx.memory.hopfield import EMPTY_READOUT, AssociativeMemory, MemoryReadout
from aamsx.periodicity.recurrence import PeriodicityEngine
from aamsx.receiver.model import ReceiverModel
from aamsx.schedulers.base import AblationFlags, SchedulerSetup


class ContextBuilder:
    """Perception pipeline: observations in, one decision context out."""

    def __init__(self, setup: SchedulerSetup, *, memory_capacity: int = 24) -> None:
        self.setup = setup
        self.flags: AblationFlags = setup.flags
        self.receiver = ReceiverModel(setup.receiver, setup.n_regions)
        self.belief = BeliefFilter(
            setup.n_regions, BeliefConfig(noise_db=max(setup.receiver.noise_db, 0.25))
        )
        self.buffer = TemporalBuffer(setup.n_regions)
        self.change = CompositeChangeDetector()
        self.periodicity = PeriodicityEngine(setup.n_regions)
        self.memory = AssociativeMemory(
            setup.n_regions, engineered.CONTEXT_DIM, capacity=memory_capacity
        )
        self.encoder = _resolve_encoder(setup)
        self.reset()

    def reset(self) -> None:
        self.belief.reset()
        self.buffer.reset()
        self.change.reset()
        self.periodicity.reset()
        self.memory.reset()
        self.step = 0
        self.budget_remaining = float(self.setup.budget)
        self.last_context: DecisionContext | None = None
        self.last_readout: MemoryReadout = EMPTY_READOUT
        self.last_features = np.zeros(len(engineered.GLOBAL_FEATURES), dtype=np.float32)
        self.last_context_vector = np.zeros(engineered.CONTEXT_DIM, dtype=np.float32)
        self.last_surprise = 0.0
        self.change_events: list[int] = []
        self.memory_events: list[dict[str, object]] = []

    # ---- build ---------------------------------------------------------------

    def build(self) -> DecisionContext:
        """Assemble the context for the current step."""
        setup = self.setup
        self.belief.predict()

        sensitivity, false_alarm = self.belief.sensitivity_specificity()
        if self.flags.information_gain:
            gain = region_information_gain(
                self.belief.belief, sensitivity=sensitivity, false_alarm=false_alarm
            )
        else:
            gain = np.zeros(setup.n_regions)

        state = self.change.state
        change_score = state.score if self.flags.change_detection else 0.0
        change_flag = bool(state.flag) if self.flags.change_detection else False
        steps_since_change = state.steps_since_change if self.flags.change_detection else 10_000

        if self.flags.periodicity:
            periodicity_score = self.periodicity.region_scores(self.step)
            periodicity_period = self.periodicity.region_periods()
            period_strength = self.periodicity.strength
        else:
            periodicity_score = np.zeros(setup.n_regions)
            periodicity_period = np.zeros(setup.n_regions, dtype=np.int32)
            period_strength = 0.0

        budget_fraction = self.budget_remaining / max(setup.budget, 1e-9)
        progress = self.step / max(setup.horizon, 1)
        features, context_vector = self.encoder(
            belief=self.belief,
            buffer=self.buffer,
            change_score=change_score,
            steps_since_change=steps_since_change,
            period_strength=period_strength,
            budget_fraction=budget_fraction,
            progress=progress,
        )
        if not self.flags.temporal_encoder:
            features = np.zeros_like(features)
        self.last_features = features
        self.last_context_vector = context_vector

        readout = self.memory.read(context_vector) if self.flags.memory else EMPTY_READOUT
        self.last_readout = readout
        if readout.recognised:
            self.memory_events.append(
                {
                    "step": self.step,
                    "prototype_id": readout.prototype_id,
                    "similarity": round(readout.similarity, 4),
                    "label": readout.label,
                    "utility": round(readout.utility, 4),
                }
            )

        previous = self.buffer.previous_anchor
        context = DecisionContext(
            step=self.step,
            n_regions=setup.n_regions,
            window_size=setup.window_size,
            belief=self.belief.belief.copy(),
            uncertainty=self.belief.uncertainty,
            staleness=self.belief.staleness,
            steps_since_seen=self.belief.steps_since_seen.copy(),
            observation_counts=self.buffer.visit_counts.copy(),
            hit_rate=self.buffer.region_hit_rate(),
            information_gain=gain,
            periodicity_score=periodicity_score,
            periodicity_period=periodicity_period,
            sensing_cost=self.receiver.cost_per_anchor(previous),
            change_score=float(change_score),
            change_flag=change_flag,
            steps_since_change=int(steps_since_change),
            budget_remaining=float(self.budget_remaining),
            budget_fraction=float(budget_fraction),
            horizon=int(setup.horizon),
            temporal_features=features,
            memory_similarity=float(readout.similarity),
            memory_prior=readout.prior,
            memory_context_id=readout.prototype_id,
            recent_rewards=self.buffer.recent_rewards(32),
            previous_regions=(
                np.arange(previous, previous + setup.window_size, dtype=np.int32)
                if previous is not None
                else None
            ),
        )
        self.last_context = context
        return context

    # ---- learn ---------------------------------------------------------------

    def absorb(self, observation: Observation) -> tuple[float, float, float]:
        """Fold the measurement into the belief only.

        Returns ``(mean_surprise, entropy_before, entropy_after)``. This runs before
        the reward is computed because the *realised* information reward is the
        entropy the belief actually lost, which is only knowable after the update.
        """
        entropy_before = self.belief.entropy()
        surprise = self.belief.update(observation)
        entropy_after = self.belief.entropy()
        self.last_surprise = float(surprise.mean()) if surprise.size else 0.0
        return self.last_surprise, entropy_before, entropy_after

    def commit(self, feedback: Feedback) -> None:
        """Fold the scored outcome into every remaining perception component."""
        observation: Observation = feedback.observation
        mean_surprise = self.last_surprise
        self.buffer.push(observation, feedback.reward)
        self.periodicity.observe(
            self.step,
            int(observation.detected.sum()),
            observation.regions,
            observation.detected,
        )
        state = self.change.update(
            self.step,
            surprise=mean_surprise,
            divergence=self.buffer.profile_divergence(),
            detection_rate=observation.detected.mean() if observation.available else 0.0,
        )
        if state.flag:
            self.change_events.append(self.step)
            if self.flags.change_detection:
                self.belief.on_change_detected()

        if self.flags.memory:
            self.memory.write(
                self.last_context_vector,
                self.buffer.region_hit_rate(),
                feedback.reward,
                self.step,
                label=self._label_context(),
            )

        self.budget_remaining = max(0.0, self.budget_remaining - observation.cost)
        self.step += 1

    def _label_context(self) -> str:
        """Human-readable name for the current regime, from named features only."""
        named = engineered.describe(self.last_features)
        if named.get("change_score", 0.0) > 0.5 or named.get("steps_since_change", 1.0) < 0.2:
            return "post-change"
        if named.get("period_strength", 0.0) > 0.5:
            return "periodic"
        if named.get("mean_uncertainty", 0.0) > 0.6:
            return "high-uncertainty"
        if named.get("recent_hit_rate", 0.0) > 0.5:
            return "dense-activity"
        if named.get("recent_hit_rate", 0.0) < 0.08:
            return "sparse-activity"
        if named.get("belief_concentration", 0.0) > 0.5:
            return "concentrated"
        return "mixed"

    def snapshot(self) -> dict[str, object]:
        return {
            "step": self.step,
            "belief": self.belief.snapshot(),
            "change": self.change.snapshot(),
            "periodicity": self.periodicity.snapshot(),
            "memory": self.memory.snapshot(),
            "features": engineered.describe(self.last_features),
            "readout": self.last_readout.to_dict(),
            "surprise": round(self.last_surprise, 5),
            "budget_remaining": round(self.budget_remaining, 4),
        }


def _resolve_encoder(setup: SchedulerSetup):
    """Pick the neural encoder when it is both requested and importable."""
    if setup.flags.neural_encoder:
        try:
            from aamsx.features.neural import NeuralEncoder

            return NeuralEncoder(setup.n_regions)
        except ImportError:
            from aamsx.logging import get_logger

            get_logger(__name__).warning(
                "context.neural_encoder_unavailable",
                extra={"fallback": "engineered features"},
            )
    return engineered.encode
