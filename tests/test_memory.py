"""Associative memory: retrieval, capacity, eviction and the standardiser."""

from __future__ import annotations

import numpy as np
import pytest

from aamsx.memory.hopfield import (
    RECOGNITION_THRESHOLD,
    AssociativeMemory,
    RunningStandardiser,
)
from aamsx.memory.projection import project

DIM = 12
REGIONS = 16


def _context(rng, base: np.ndarray, jitter: float = 0.0) -> np.ndarray:
    return base + jitter * rng.standard_normal(base.size)


def test_empty_memory_returns_the_null_readout():
    memory = AssociativeMemory(REGIONS, DIM)
    readout = memory.read(np.zeros(DIM))
    assert len(memory) == 0
    assert readout.prototype_id is None
    assert readout.prior is None
    assert readout.similarity == 0.0
    assert not readout.recognised
    assert readout.label == "novel"


def test_a_written_context_is_retrieved_with_its_preference(rng):
    memory = AssociativeMemory(REGIONS, DIM, write_threshold=0.9)
    context = rng.standard_normal(DIM)
    profile = np.zeros(REGIONS)
    profile[3:7] = 1.0
    # Two writes: the standardiser needs more than one sample to have a scale.
    for step in range(6):
        memory.write(context, profile, reward=1.0, step=step)
    readout = memory.read(context)
    assert readout.prototype_id is not None
    assert readout.similarity > 0.95
    assert int(np.argmax(readout.prior)) in range(3, 7)


def test_dissimilar_contexts_create_separate_prototypes(rng):
    memory = AssociativeMemory(REGIONS, DIM, write_threshold=0.9)
    left = np.concatenate([np.ones(DIM // 2), -np.ones(DIM // 2)])
    right = -left
    for step in range(20):
        memory.write(left, np.eye(REGIONS)[2], reward=1.0, step=step)
        memory.write(right, np.eye(REGIONS)[11], reward=1.0, step=step)
    assert len(memory) >= 2
    assert int(np.argmax(memory.read(left).prior)) != int(np.argmax(memory.read(right).prior))


def test_a_recurring_pair_of_contexts_refines_rather_than_duplicating(rng):
    """Two alternating regimes must converge on two prototypes, not eighty.

    The contexts have to genuinely differ for whitening to have an axis to work
    with; a memory fed one unchanging vector sees only noise once the mean is
    removed, which is why AAMS-X keys memory on engineered features that move.
    """
    memory = AssociativeMemory(REGIONS, DIM, write_threshold=0.7)
    left = np.concatenate([np.ones(DIM // 2), np.zeros(DIM - DIM // 2)]) * 4.0
    right = np.concatenate([np.zeros(DIM // 2), np.ones(DIM - DIM // 2)]) * 4.0
    for step in range(80):
        base, region = (left, 4) if step % 2 == 0 else (right, 12)
        memory.write(_context(rng, base, 0.05), np.eye(REGIONS)[region], reward=1.0, step=step)
    assert len(memory) == 2
    assert min(p.visits for p in memory.prototypes) > 20
    assert memory.creations == 2
    assert int(np.argmax(memory.read(left).prior)) == 4
    assert int(np.argmax(memory.read(right).prior)) == 12


def test_capacity_is_never_exceeded(rng):
    memory = AssociativeMemory(REGIONS, DIM, capacity=5, write_threshold=0.999, protect_steps=0)
    for step in range(60):
        memory.write(
            rng.standard_normal(DIM),
            rng.random(REGIONS),
            reward=float(step % 3),
            step=step * 10,
        )
    assert len(memory) <= 5
    assert memory.evictions > 0
    assert memory.snapshot()["size"] == len(memory)


def test_eviction_removes_the_least_useful_prototype():
    memory = AssociativeMemory(
        REGIONS, DIM, capacity=2, write_threshold=0.999, protect_steps=0, recency_tau=1e9
    )
    basis = np.eye(DIM)
    memory.write(basis[0] * 5, np.eye(REGIONS)[0], reward=10.0, step=0)
    memory.write(basis[1] * 5, np.eye(REGIONS)[1], reward=-10.0, step=1)
    useful_id = memory.prototypes[0].prototype_id
    useless_id = memory.prototypes[1].prototype_id
    memory.write(basis[2] * 5, np.eye(REGIONS)[2], reward=0.0, step=2)
    surviving = {p.prototype_id for p in memory.prototypes}
    assert useless_id not in surviving
    assert useful_id in surviving


def test_recent_prototypes_are_protected_from_eviction():
    memory = AssociativeMemory(REGIONS, DIM, capacity=2, write_threshold=0.999, protect_steps=100)
    basis = np.eye(DIM)
    for index in range(3):
        memory.write(basis[index] * 5, np.eye(REGIONS)[index], reward=1.0, step=index)
    # Everything is inside the protection window, so eviction still had to pick one.
    assert len(memory) == 2
    assert memory.evictions == 1


def test_recognition_requires_both_similarity_and_a_repeat_visit(rng):
    memory = AssociativeMemory(REGIONS, DIM, write_threshold=0.5)
    base = rng.standard_normal(DIM)
    memory.write(base, np.eye(REGIONS)[1], reward=1.0, step=0)
    assert not memory.read(base).recognised, "one visit is not recognition"
    for step in range(1, 12):
        memory.write(_context(rng, base, 0.005), np.eye(REGIONS)[1], reward=1.0, step=step)
    readout = memory.read(base)
    assert readout.visits >= 2
    assert readout.similarity >= RECOGNITION_THRESHOLD
    assert readout.recognised


def test_retrieval_blends_the_top_k_prototypes(rng):
    memory = AssociativeMemory(REGIONS, DIM, top_k=3, write_threshold=0.999)
    basis = np.eye(DIM) * 4.0
    for index in range(5):
        memory.write(basis[index], np.eye(REGIONS)[index], reward=1.0, step=index)
    readout = memory.read(basis[0])
    assert len(readout.top_ids) == 3
    assert sum(readout.top_weights) == pytest.approx(1.0, abs=1e-9)
    assert readout.top_ids[0] == memory.prototypes[0].prototype_id


def test_profile_shape_is_validated():
    memory = AssociativeMemory(REGIONS, DIM)
    with pytest.raises(ValueError, match="region profile"):
        memory.write(np.zeros(DIM), np.zeros(REGIONS + 1), reward=0.0, step=0)


def test_standardiser_whitens_and_floors_the_scale(rng):
    standardiser = RunningStandardiser(4, warmup=3)
    for _ in range(200):
        standardiser.observe(rng.normal(loc=[0.0, 10.0, -5.0, 0.0], scale=[1.0, 4.0, 0.1, 0.0]))
    transformed = standardiser.transform(np.array([0.0, 10.0, -5.0, 0.0]))
    assert np.all(np.abs(transformed) < 1.0), "the mean must map near zero"
    assert np.all(np.isfinite(standardiser.scale))
    assert np.all(standardiser.scale > 0.0), "a constant feature must not divide by zero"


def test_standardiser_only_centres_before_warmup():
    """Until there are enough samples to estimate a scale, transform just centres."""
    standardiser = RunningStandardiser(3, warmup=10)
    standardiser.observe(np.array([5.0, 5.0, 5.0]))
    out = standardiser.transform(np.array([1.0, 2.0, 3.0]))
    assert np.allclose(out, [-1.0, 0.0, 1.0])
    assert out.sum() == pytest.approx(0.0)


def test_projection_is_two_dimensional_and_labelled(rng):
    memory = AssociativeMemory(REGIONS, DIM, write_threshold=0.999)
    basis = np.eye(DIM) * 3.0
    for index in range(6):
        memory.write(basis[index], rng.random(REGIONS), reward=float(index), step=index)
    payload = project(memory, query=basis[0]).to_dict()
    # The live context is projected alongside the prototypes, tagged id -1.
    assert len(payload["points"]) == len(memory) + 1
    assert payload["method"] == "PCA (SVD)"
    assert 0.0 <= payload["explained_variance"] <= 1.0
    for point in payload["points"]:
        assert np.isfinite([point["x"], point["y"]]).all()
        assert "id" in point and "label" in point
    assert payload["points"][-1]["id"] == -1

    without_query = project(memory).to_dict()
    assert len(without_query["points"]) == len(memory)


def test_projection_of_an_empty_memory_is_empty():
    payload = project(AssociativeMemory(REGIONS, DIM)).to_dict()
    assert payload["points"] == []


def test_reset_clears_everything(rng):
    memory = AssociativeMemory(REGIONS, DIM)
    for step in range(10):
        memory.write(rng.standard_normal(DIM), rng.random(REGIONS), reward=1.0, step=step)
    memory.reset()
    assert len(memory) == 0
    assert memory.writes == 0
    assert memory.creations == 0
    assert memory.read(np.zeros(DIM)).prototype_id is None
