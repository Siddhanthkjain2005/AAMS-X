"""Optional recurrent context encoder (PyTorch).

Off by default, and honestly labelled.  The default encoder in
:mod:`aamsx.features.engineered` is hand-written: every dimension has a name, a
bound and a reason, which is what lets the Decision Inspector explain a choice.
This module keeps all of that and changes exactly one thing — how the *memory
key* is built.

What it does
------------
:class:`NeuralEncoder` calls the engineered encoder first, so the 18 named
temporal features the scheduler scores against and the inspector displays are
byte-for-byte the same.  It then pushes the engineered context vector through a
single :class:`torch.nn.GRUCell` and returns the recurrent hidden state as the
context vector, so associative memory keys on a summary of the recent
*trajectory* rather than only the current step.  The output keeps
``engineered.CONTEXT_DIM`` dimensions and the same ``[0, 1]`` range, so memory,
retrieval thresholds and the ablation flags need no changes.

What it does **not** do
-----------------------
There is no training loop, no label to fit and no shipped checkpoint.  With
random weights this is a **reservoir**: a fixed, seeded, nonlinear recurrent
projection.  That is a real transform with a real literature behind it, but it is
*not* a learned representation, and enabling it is not evidence of anything.
No benchmark number in ``docs/EXPERIMENTS.md`` was produced with this flag on.
If you supply a checkpoint, the provenance of that checkpoint is yours.

Determinism
-----------
Weights come from a seeded generator and the module runs under
:func:`torch.no_grad` in ``eval`` mode on CPU, so a given ``(seed, n_regions)``
gives bit-identical vectors on every run — the reproducibility registry stays
meaningful.

Checkpoints are untrusted input and are therefore loaded with
``weights_only=True``: a ``.pt`` file is a pickle, and an unrestricted
``torch.load`` executes it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import torch  # ImportError here is the supported "extra not installed" path
from torch import nn

from aamsx.features import engineered
from aamsx.logging import get_logger

log = get_logger(__name__)

DEFAULT_SEED = 20260825
"""Fixed so an enabled encoder is still reproducible without a checkpoint."""


class ContextGRU(nn.Module):
    """One GRU step over the engineered context vector.

    Deliberately one layer wide enough to mix bands but small enough to stay in
    the microsecond budget the scheduler has per step (see the latency table in
    ``docs/EXPERIMENTS.md``: the whole decision path is ~0.1 ms).
    """

    def __init__(self, dim: int, *, seed: int = DEFAULT_SEED) -> None:
        super().__init__()
        self.cell = nn.GRUCell(dim, dim)
        generator = torch.Generator().manual_seed(seed)
        with torch.no_grad():
            for parameter in self.cell.parameters():
                if parameter.dim() > 1:
                    # Orthogonal-ish scaling keeps the recurrence from saturating
                    # in the first few steps of an episode.
                    bound = (1.0 / max(dim, 1)) ** 0.5
                    parameter.uniform_(-bound, bound, generator=generator)
                else:
                    parameter.zero_()
        self.eval()

    @torch.no_grad()
    def forward(self, vector: torch.Tensor, hidden: torch.Tensor) -> torch.Tensor:
        return self.cell(vector, hidden)


class NeuralEncoder:
    """Drop-in replacement for :func:`aamsx.features.engineered.encode`.

    Callable with the same keyword arguments and returning the same
    ``(temporal_features, context_vector)`` pair, so
    :func:`aamsx.experiments.context._resolve_encoder` can swap it in without
    the scheduler knowing.
    """

    def __init__(
        self,
        n_regions: int,
        *,
        seed: int = DEFAULT_SEED,
        checkpoint: str | Path | None = None,
    ) -> None:
        self.n_regions = int(n_regions)
        self.dim = engineered.CONTEXT_DIM
        self.model = ContextGRU(self.dim, seed=seed)
        self.trained = False
        if checkpoint is not None:
            self.load(checkpoint)
        self._hidden = torch.zeros(1, self.dim)
        self.steps = 0

    # -- lifecycle ---------------------------------------------------------- #

    def reset(self) -> None:
        """Clear the recurrent state. Called at the start of every episode."""
        self._hidden = torch.zeros(1, self.dim)
        self.steps = 0

    def load(self, checkpoint: str | Path) -> None:
        """Load weights from a ``.pt`` file, treating the file as untrusted."""
        path = Path(checkpoint)
        if not path.is_file():
            raise FileNotFoundError(f"no encoder checkpoint at {path}")
        state = torch.load(path, map_location="cpu", weights_only=True)
        if not isinstance(state, dict):
            raise ValueError(f"{path} does not hold a state dict")
        self.model.load_state_dict(state)
        self.model.eval()
        self.trained = True
        log.info("neural.checkpoint_loaded", extra={"path": str(path)})

    # -- encoding ----------------------------------------------------------- #

    def __call__(self, **kwargs: object) -> tuple[np.ndarray, np.ndarray]:
        features, context = engineered.encode(**kwargs)  # type: ignore[arg-type]
        tensor = torch.from_numpy(np.ascontiguousarray(context, dtype=np.float32)).unsqueeze(0)
        self._hidden = self.model(tensor, self._hidden)
        self.steps += 1
        # GRU hidden state is in [-1, 1]; map to [0, 1] so it lives on the same
        # scale as the engineered vector and no single dimension dominates the
        # cosine similarity memory retrieval uses.
        encoded = (0.5 * (self._hidden.squeeze(0) + 1.0)).numpy().astype(np.float32)
        return features, encoded

    def describe(self) -> dict[str, object]:
        """Metadata for the provenance panel: an honest label, not a claim."""
        return {
            "encoder": "gru-context",
            "kind": "model-inferred",
            "dim": self.dim,
            "trained": self.trained,
            "steps": self.steps,
            "note": (
                "Recurrent context key. Untrained weights are a seeded random "
                "reservoir, not a learned representation."
            ),
        }


def available() -> bool:
    """True when the torch extra is importable (it is, if this module imported)."""
    return True
