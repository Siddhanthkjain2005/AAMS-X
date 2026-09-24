"""2-D projection of context prototypes for the memory visualiser.

PCA is used rather than t-SNE or UMAP for three reasons that matter here: it is
deterministic (the same memory always lands in the same place, so the picture is
stable while an episode streams), it is linear (distances on screen mean something
about distances in context space), and it costs nothing on 24 vectors.

With fewer than three prototypes PCA is undefined, so the projection falls back to
the two most informative raw dimensions, and says so.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from aamsx.memory.hopfield import AssociativeMemory


@dataclass(frozen=True, slots=True)
class Projection:
    points: np.ndarray  # (K, 2)
    ids: tuple[int, ...]
    labels: tuple[str, ...]
    utilities: tuple[float, ...]
    visits: tuple[int, ...]
    explained_variance: float
    method: str

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "explained_variance": round(float(self.explained_variance), 4),
            "points": [
                {
                    "id": int(identifier),
                    "x": round(float(point[0]), 5),
                    "y": round(float(point[1]), 5),
                    "label": label,
                    "utility": round(float(utility), 5),
                    "visits": int(visit),
                }
                for identifier, point, label, utility, visit in zip(
                    self.ids, self.points, self.labels, self.utilities, self.visits, strict=True
                )
            ],
        }


def project(memory: AssociativeMemory, *, query: np.ndarray | None = None) -> Projection:
    """Project stored prototypes (and optionally the live context) into 2-D."""
    prototypes = memory.prototypes
    if not prototypes:
        return Projection(np.zeros((0, 2)), (), (), (), (), 0.0, "empty")

    matrix = np.stack([prototype.vector for prototype in prototypes]).astype(np.float64)
    stack = matrix if query is None else np.vstack([matrix, np.asarray(query, dtype=np.float64)])
    centred = stack - stack.mean(axis=0, keepdims=True)

    if stack.shape[0] < 3:
        spread = centred.var(axis=0)
        axes = np.argsort(-spread)[:2]
        points = centred[:, axes]
        explained = float(spread[axes].sum() / max(spread.sum(), 1e-12))
        method = "top-variance axes"
    else:
        # Economy SVD: for K <= 25 vectors this is microseconds and avoids a
        # scikit-learn import on the streaming path.
        _, singular, components = np.linalg.svd(centred, full_matrices=False)
        points = centred @ components[:2].T
        total = float((singular**2).sum())
        explained = float((singular[:2] ** 2).sum() / total) if total > 0 else 0.0
        method = "PCA (SVD)"

    ids = tuple(prototype.prototype_id for prototype in prototypes)
    if query is not None:
        ids = (*ids, -1)
        labels = (*(p.label for p in prototypes), "current context")
        utilities = (*(p.utility for p in prototypes), 0.0)
        visits = (*(p.visits for p in prototypes), 0)
    else:
        labels = tuple(prototype.label for prototype in prototypes)
        utilities = tuple(prototype.utility for prototype in prototypes)
        visits = tuple(prototype.visits for prototype in prototypes)

    return Projection(
        points=points.astype(np.float32),
        ids=ids,
        labels=labels,
        utilities=utilities,
        visits=visits,
        explained_variance=explained,
        method=method,
    )
