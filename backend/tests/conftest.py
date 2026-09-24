import numpy as np
import pytest

from backend.contracts import Action, BandObservation, Observation
from backend.environment import World
from backend.scheduler.policies import Decision


@pytest.fixture
def world_factory():
    def make(truth, energy=None):
        truth = np.array(truth, dtype=bool) if truth is not None else None
        if energy is None:
            energy = -96 + truth.astype(float) * 14
        energy = np.array(energy, dtype=np.float32)
        h, n = energy.shape
        return World(energy, truth, np.full((h, n), 0.1), np.full((h, n), 0.99), np.arange(n) * 10.0, np.arange(h) * 100.0, {"category": "CONTROLLED_SIMULATION", "ground_truth": truth is not None})
    return make


def observation(step, start, hits, cost=0.0, valid=None):
    return Observation(step, step * 100.0, Action(start, len(hits)), tuple(BandObservation(start + i, -80.0 if hit else -96.0, hit, 0.99, -96.0, valid[i] if valid else True) for i, hit in enumerate(hits)), 99.0, cost)


def decision(action, bands=8, forecasts=None):
    return Decision(action, 0.0, [], {}, [], False, [0.2] * bands, [1.0] * bands, forecasts or [], [])
