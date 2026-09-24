"""Every policy is a function of public geometry, its RNG, and prior observations.

The module deliberately cannot import environments, evaluators, or datasets.
The same API is used by baselines and all component ablations.
"""

from dataclasses import dataclass

import numpy as np

from backend.contracts import Action, DecisionContext, Observation, PublicReceiver

from .belief import Belief
from .change import ChangeDetector
from .memory import AssociativeMemory
from .periodicity import PeriodicityEstimator

ALGORITHM_NAMES = {
    "magnts": "MAG-NTS", "fixed": "Fixed Sweep", "random": "Random", "thompson": "Vanilla Thompson",
    "ucb": "UCB", "no_memory": "MAG-NTS · no Memory", "no_information": "MAG-NTS · no Information Gain", "no_change": "MAG-NTS · no Change Detection",
}

COMPONENT_LABELS = {
    "opportunity": "Learned activity + Thompson sample",
    "information": "Expected information gain",
    "uncertainty": "Uncertainty exploration",
    "memory": "Similar observation pattern recalled",
    "periodicity": "Recurring activity opportunity",
    "recency": "Time since last observation",
    "change": "Recent distribution shift",
    "exploration": "Directed exploration",
    "retune": "Retuning cost",
    "wasted": "Repeated empty observations",
}


@dataclass(frozen=True)
class Decision:
    action: Action
    score: float
    candidates: list[dict]
    components: dict
    reasons: list[str]
    exploration: bool
    pre_probability: list[float]
    pre_uncertainty: list[float]
    periodic_candidates: list[dict]
    memory_matches: list[dict]


class Policy:
    def __init__(self, algorithm: str, receiver: PublicReceiver, seed: int):
        if algorithm not in ALGORITHM_NAMES:
            raise ValueError(f"Unknown policy: {algorithm}")
        self.algorithm = algorithm
        self.receiver = receiver
        self.rng = np.random.default_rng(seed)
        self.adaptive = algorithm in {"magnts", "no_memory", "no_information", "no_change"}
        self.belief = Belief(receiver.bands, discount=0.989 if self.adaptive else 1.0)
        self.change = ChangeDetector(receiver.bands)
        self.memory = AssociativeMemory(receiver.bands)
        self.periodicity = PeriodicityEstimator(receiver.bands)
        self.changes: list[dict] = []
        self.starts = np.arange(receiver.bands - receiver.width + 1)
        self.sweep = sorted(set([*range(0, receiver.bands - receiver.width + 1, receiver.width), receiver.bands - receiver.width]))

    def _window_mean(self, values: np.ndarray) -> np.ndarray:
        return np.convolve(values, np.ones(self.receiver.width) / self.receiver.width, mode="valid")

    def select_action(self, context: DecisionContext) -> Decision:
        b, r, t = self.belief, self.receiver, context.step
        b.advance(t)
        mean, uncertainty = b.mean, b.uncertainty
        sample = self.rng.beta(b.alpha, b.beta)
        memory, matches = self.memory.recall_all(t) if self.adaptive and self.algorithm != "no_memory" else (np.zeros(r.bands), [])
        periodic = self.periodicity.opportunity(t, r.bands) if self.adaptive else np.zeros(r.bands)
        age = np.minimum(1, (t - b.last_visit) / max(12, r.bands * 1.5))
        explore = bool(self.adaptive and self.rng.random() < 0.12)
        parts = {
            "opportunity": self._window_mean(0.8 * mean + 0.4 * sample),
            "information": 0.65 * self._window_mean(b.information_gain / 0.193147) if self.algorithm != "no_information" else np.zeros(len(self.starts)),
            "uncertainty": 0.16 * self._window_mean(uncertainty),
            "memory": 0.28 * self._window_mean(memory),
            "periodicity": 0.75 * self._window_mean(periodic),
            "recency": 0.22 * self._window_mean(age),
            "change": 0.3 * self._window_mean(self.change.priority(t)) if self.algorithm != "no_change" else np.zeros(len(self.starts)),
            "exploration": 0.65 * self._window_mean(age * uncertainty) if explore else np.zeros(len(self.starts)),
            "retune": -0.24 * np.array([r.retune_cost(context.previous_start, int(s)) for s in self.starts]),
            "wasted": -0.14 * self._window_mean(np.minimum(1, b.miss_streak / 5) * (1 - mean)),
        }
        scores = sum(parts.values())
        if self.algorithm == "fixed":
            selected = self.sweep[t % len(self.sweep)]
        elif self.algorithm == "random":
            selected = int(self.rng.choice(self.starts))
            explore = True
        elif self.algorithm == "thompson":
            scores = self._window_mean(sample)
            selected = int(np.argmax(scores))
        elif self.algorithm == "ucb":
            scores = self._window_mean(mean + np.sqrt(2 * np.log(t + 2) / (b.counts + 1)))
            selected = int(np.argmax(scores))
        else:
            selected = int(np.argmax(scores))
        if not self.adaptive:
            parts = {"opportunity": scores if self.algorithm in {"ucb", "thompson"} else np.zeros_like(scores)}
            scores = parts["opportunity"]
        ranking = list(np.argsort(-scores)[:5])
        if selected not in ranking:
            ranking = [selected, *ranking[:4]]
        candidates = [{"start": int(s), "end": int(s + r.width - 1), "score": round(float(scores[s]), 5), "probability": round(float(self._window_mean(mean)[s]), 4), "uncertainty": round(float(self._window_mean(uncertainty)[s]), 4), "selected": bool(s == selected), "components": {key: round(float(values[s]), 5) for key, values in parts.items()}} for s in ranking]
        components = {key: round(float(values[selected]), 5) for key, values in parts.items()}
        reasons = [COMPONENT_LABELS[key] for key in sorted(components, key=components.get, reverse=True)[:3] if components[key] > 0.02]
        if self.algorithm == "fixed":
            reasons = ["Predetermined sequential sweep", "Same dwell and bandwidth as AAMS-X"]
        elif self.algorithm == "random":
            reasons = ["Uniform random contiguous window"]
        return Decision(Action(selected, r.width), round(float(scores[selected]), 5), candidates, components, reasons, explore, mean.round(6).tolist(), uncertainty.round(6).tolist(), self.periodicity.predictions(t) if self.adaptive else [], matches)

    def update(self, observation: Observation):
        self.changes = []
        for value in observation.values:
            if not value.valid:
                continue
            if self.adaptive and self.algorithm != "no_change":
                event = self.change.update(value.band, float(value.detected), float(self.belief.mean[value.band]), observation.step)
                if event:
                    self.changes.append(event)
                    self.belief.soften(value.band)
            self.belief.update(observation.step, value, weighted=self.adaptive)
            if self.adaptive:
                self.periodicity.update(value.band, observation.step, value.detected and value.confidence >= 0.55)
                if self.algorithm != "no_memory":
                    self.memory.update(value.band, value.detected, observation.step)

    def snapshot(self, step: int) -> dict:
        return {**self.belief.snapshot(step), "change_scores": self.change.scores().round(4).tolist(), "change_events": list(self.changes), "periodicity": self.periodicity.predictions(step) if self.adaptive else [], "memory_size": len(self.memory.episodes)}
