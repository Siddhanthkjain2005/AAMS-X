"""Associative context memory.

The memory stores *contexts*, never frequencies.  A prototype answers "have I been
in a situation shaped like this before, and what worked?" — which is the only form
of recall that can transfer between two different receivers covering two different
bands, and the reason the recurring-environment experiment is winnable at all.

Retrieval is the modern-Hopfield / attention update: with unit-normalised
prototypes ``M`` and query ``z``, the retrieved pattern is
``softmax(beta * M z)^T M``.  A single step of this update is exactly
scaled-dot-product attention over the stored patterns, and for large ``beta`` it
converges on the nearest stored prototype, so one pass is enough.

Each prototype carries an *action preference* over regions — an EMA of the
per-region hit rate observed while that context was active.  That vector is what
MAG-NTS uses as a prior when a context is recognised, and it is why recovery after
a return to a known environment is faster than rediscovery.

Capacity is bounded and eviction is explicit: lowest utility x recency loses, and
freshly created prototypes are protected so a novel context is never evicted
before it has had a chance to prove itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

RECOGNITION_THRESHOLD = 0.90
"""Cosine similarity at which a context counts as *recognised* for the UI."""


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=-1, keepdims=True)
    return matrix / np.maximum(norms, 1e-9)


class RunningStandardiser:
    """Online per-dimension mean/variance (Welford), used to whiten context vectors.

    Whitening is not cosmetic here, it is what makes the memory work at all.  Raw
    context vectors are all-positive and dominated by dimensions that barely move
    across an episode, so their cosine similarities sit above 0.99 everywhere and
    every environment "matches" every other.  Measured on the recurring-environment
    scenario, whitening separates the three phases into distinct prototypes where
    the raw vectors collapsed two different stations into one.
    """

    def __init__(self, dim: int, *, warmup: int = 24) -> None:
        self.dim = int(dim)
        self.warmup = int(warmup)
        self.reset()

    def reset(self) -> None:
        self.count = 0
        self._mean = np.zeros(self.dim, dtype=np.float64)
        self._m2 = np.zeros(self.dim, dtype=np.float64)

    def observe(self, vector: np.ndarray) -> None:
        self.count += 1
        delta = np.asarray(vector, dtype=np.float64) - self._mean
        self._mean += delta / self.count
        self._m2 += delta * (np.asarray(vector, dtype=np.float64) - self._mean)

    #: Dimensions quieter than this fraction of the median spread are not amplified.
    SCALE_FLOOR_FRACTION = 0.25

    @property
    def scale(self) -> np.ndarray:
        """Per-dimension spread, floored so silent dimensions are not amplified.

        Plain whitening would divide a dimension that never moves by its own tiny
        noise and turn it into the loudest term in the similarity. The floor keeps
        whitening useful for informative dimensions while leaving flat ones flat.
        """
        if self.count < 2:
            return np.ones(self.dim, dtype=np.float64)
        spread = np.sqrt(np.maximum(self._m2 / (self.count - 1), 1e-12))
        floor = self.SCALE_FLOOR_FRACTION * float(np.median(spread))
        return np.maximum(spread, max(floor, 1e-4))

    def transform(self, vector: np.ndarray) -> np.ndarray:
        """Whiten a context vector; a no-op until enough samples have been seen."""
        array = np.asarray(vector, dtype=np.float64)
        if self.count < self.warmup:
            return array - array.mean()
        return (array - self._mean) / self.scale


@dataclass(slots=True)
class Prototype:
    """One remembered context."""

    prototype_id: int
    vector: np.ndarray  # (D,) context prototype
    preference: np.ndarray  # (R,) region preference learned in this context
    utility: float
    visits: int
    created_step: int
    last_step: int
    label: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.prototype_id,
            "label": self.label,
            "utility": round(float(self.utility), 5),
            "visits": int(self.visits),
            "created_step": int(self.created_step),
            "last_step": int(self.last_step),
            "preference": [round(float(v), 5) for v in self.preference],
        }


@dataclass(frozen=True, slots=True)
class MemoryReadout:
    """What a single read returned."""

    similarity: float
    prototype_id: int | None
    prior: np.ndarray | None
    age: int
    utility: float
    visits: int
    label: str
    recognised: bool
    top_ids: tuple[int, ...] = field(default_factory=tuple)
    top_weights: tuple[float, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, object]:
        return {
            "similarity": round(float(self.similarity), 5),
            "prototype_id": self.prototype_id,
            "age": int(self.age),
            "utility": round(float(self.utility), 5),
            "visits": int(self.visits),
            "label": self.label,
            "recognised": bool(self.recognised),
            "top_ids": list(self.top_ids),
            "top_weights": [round(float(w), 5) for w in self.top_weights],
        }


EMPTY_READOUT = MemoryReadout(
    similarity=0.0,
    prototype_id=None,
    prior=None,
    age=0,
    utility=0.0,
    visits=0,
    label="novel",
    recognised=False,
)


class AssociativeMemory:
    """Bounded modern-Hopfield memory over context prototypes."""

    def __init__(
        self,
        n_regions: int,
        context_dim: int,
        *,
        capacity: int = 24,
        beta: float = 12.0,
        write_threshold: float = 0.88,
        top_k: int = 3,
        utility_decay: float = 0.85,
        vector_decay: float = 0.9,
        preference_decay: float = 0.8,
        protect_steps: int = 60,
        recency_tau: float = 400.0,
    ) -> None:
        self.n_regions = int(n_regions)
        self.context_dim = int(context_dim)
        self.capacity = int(capacity)
        self.beta = float(beta)
        self.write_threshold = float(write_threshold)
        self.top_k = int(top_k)
        self.utility_decay = float(utility_decay)
        self.vector_decay = float(vector_decay)
        self.preference_decay = float(preference_decay)
        self.protect_steps = int(protect_steps)
        self.recency_tau = float(recency_tau)
        self.standardiser = RunningStandardiser(self.context_dim)
        self.reset()

    def reset(self) -> None:
        self.standardiser.reset()
        self._prototypes: list[Prototype] = []
        self._next_id = 0
        self.writes = 0
        self.creations = 0
        self.evictions = 0
        self.recognitions = 0

    def __len__(self) -> int:
        return len(self._prototypes)

    @property
    def prototypes(self) -> tuple[Prototype, ...]:
        return tuple(self._prototypes)

    def _matrix(self) -> np.ndarray:
        return np.stack([p.vector for p in self._prototypes])

    # ---- read ----------------------------------------------------------------

    def read(self, context: np.ndarray) -> MemoryReadout:
        """Retrieve the blended preference of the contexts most like ``context``."""
        if not self._prototypes:
            return EMPTY_READOUT
        query = _normalise(self.standardiser.transform(context))
        keys = _normalise(self._matrix().astype(np.float64))
        similarity = keys @ query

        k = min(self.top_k, similarity.size)
        top = np.argsort(-similarity)[:k]
        logits = self.beta * similarity[top]
        weights = np.exp(logits - logits.max())
        weights /= weights.sum()

        prior = np.zeros(self.n_regions, dtype=np.float64)
        for weight, index in zip(weights, top, strict=True):
            prior += weight * self._prototypes[index].preference
        best = self._prototypes[int(top[0])]
        best_similarity = float(similarity[top[0]])
        recognised = best_similarity >= RECOGNITION_THRESHOLD and best.visits >= 2
        if recognised:
            self.recognitions += 1
        return MemoryReadout(
            similarity=best_similarity,
            prototype_id=best.prototype_id,
            prior=prior,
            age=0,
            utility=best.utility,
            visits=best.visits,
            label=best.label,
            recognised=recognised,
            top_ids=tuple(int(self._prototypes[i].prototype_id) for i in top),
            top_weights=tuple(float(w) for w in weights),
        )

    # ---- write ---------------------------------------------------------------

    def write(
        self,
        context: np.ndarray,
        region_profile: np.ndarray,
        reward: float,
        step: int,
        *,
        label: str = "",
    ) -> Prototype:
        """Store or refine the prototype for the current context."""
        self.writes += 1
        self.standardiser.observe(context)
        vector = self.standardiser.transform(context)
        profile = np.asarray(region_profile, dtype=np.float64)
        if profile.shape != (self.n_regions,):
            raise ValueError(f"region profile must be ({self.n_regions},), got {profile.shape}")

        if self._prototypes:
            keys = _normalise(self._matrix().astype(np.float64))
            similarity = keys @ _normalise(vector)
            best = int(np.argmax(similarity))
            if float(similarity[best]) >= self.write_threshold:
                return self._refine(self._prototypes[best], vector, profile, reward, step)
        return self._create(vector, profile, reward, step, label)

    def _refine(
        self,
        prototype: Prototype,
        vector: np.ndarray,
        profile: np.ndarray,
        reward: float,
        step: int,
    ) -> Prototype:
        prototype.vector = self.vector_decay * prototype.vector + (1 - self.vector_decay) * vector
        prototype.preference = (
            self.preference_decay * prototype.preference + (1 - self.preference_decay) * profile
        )
        prototype.utility = self.utility_decay * prototype.utility + (
            1 - self.utility_decay
        ) * float(reward)
        prototype.visits += 1
        prototype.last_step = int(step)
        return prototype

    def _create(
        self, vector: np.ndarray, profile: np.ndarray, reward: float, step: int, label: str
    ) -> Prototype:
        if len(self._prototypes) >= self.capacity:
            self._evict(step)
        prototype = Prototype(
            prototype_id=self._next_id,
            vector=vector.copy(),
            preference=profile.copy(),
            utility=float(reward),
            visits=1,
            created_step=int(step),
            last_step=int(step),
            label=label or "novel",
        )
        self._next_id += 1
        self.creations += 1
        self._prototypes.append(prototype)
        return prototype

    def _evict(self, step: int) -> None:
        candidates = [
            prototype
            for prototype in self._prototypes
            if step - prototype.created_step > self.protect_steps
        ]
        if not candidates:
            candidates = list(self._prototypes)
        scores = [
            prototype.utility * np.exp(-(step - prototype.last_step) / self.recency_tau)
            for prototype in candidates
        ]
        victim = candidates[int(np.argmin(scores))]
        self._prototypes.remove(victim)
        self.evictions += 1

    def snapshot(self) -> dict[str, object]:
        return {
            "size": len(self._prototypes),
            "capacity": self.capacity,
            "writes": self.writes,
            "creations": self.creations,
            "evictions": self.evictions,
            "recognitions": self.recognitions,
            "standardiser_samples": self.standardiser.count,
            "prototypes": [prototype.to_dict() for prototype in self._prototypes],
        }
