import ast
import inspect
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import numpy as np
import pytest

import backend.scheduler
from backend.contracts import (
    Action,
    BandObservation,
    DecisionContext,
    ExperimentConfig,
    Observation,
    PublicReceiver,
    ReceiverConfig,
)
from backend.environment import SpectrumEnvironment, World, make_simulation
from backend.receiver import Receiver
from backend.scheduler import Policy


def test_POLICY_TRUTH_LEAK_TEST():
    """An architectural import/attribute guard plus counterfactual noninterference.

    This test intentionally fails if policy modules introduce an environment,
    evaluator, dataset, or truth capability. It is not a malicious-code sandbox.
    """
    root = Path(inspect.getfile(backend.scheduler)).parent
    forbidden = {"truth", "_truth", "_world", "world", "environment", "get_truth_for_evaluation", "evaluators", "load", "loadtxt", "fromfile", "memmap", "read_csv", "read_parquet", "read_text", "read_bytes", "open"}
    allowed_imports = {"numpy", "scipy.special", "math", "collections", "dataclasses", "backend.contracts"}
    forbidden_calls = {"open", "__import__", "eval", "exec", "getattr", "globals", "locals", "vars"}
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("backend"):
                assert node.module == "backend.contracts", f"Policy truth-capability import in {path}: {node.module}"
            if isinstance(node, ast.ImportFrom) and node.level == 0:
                assert node.module in allowed_imports, f"Policy acquired an unreviewed external capability: {node.module}"
            if isinstance(node, ast.Import):
                assert all(alias.name in allowed_imports for alias in node.names), f"Capability import in {path}"
            if isinstance(node, ast.Attribute):
                assert node.attr not in forbidden, f"Policy acquired privileged attribute {node.attr} in {path}"
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden_calls, f"Policy acquired I/O or introspection capability in {path}"
    assert {f.name for f in fields(Observation)} == {"step", "timestamp_ms", "window", "values", "effective_dwell_ms", "retune_cost"}
    assert {f.name for f in fields(BandObservation)} == {"band", "energy", "detected", "confidence", "noise_estimate", "valid"}
    config = ExperimentConfig(horizon=24, receiver=ReceiverConfig(bands=16, window_width=3))
    original = make_simulation(config)
    policies = [Policy("magnts", PublicReceiver.from_config(config.receiver), 91) for _ in range(2)]
    previous = None
    for t in range(12):
        decisions = [p.select_action(DecisionContext(t, previous)) for p in policies]
        assert decisions[0] == decisions[1], "Changing hidden state changed the policy before an observation"
        action = decisions[0].action
        # Change every out-of-window value and truth bit in an otherwise identical world.
        outside = np.ones(16, dtype=bool)
        outside[list(action.bands)] = False
        changed_energy = original.energy.copy()
        changed_truth = original.truth.copy()
        changed_energy[:, outside] += 120
        changed_truth[:, outside] = ~changed_truth[:, outside]
        altered = World(changed_energy, changed_truth, original.detector_uniform.copy(), original.false_alarm_uniform.copy(), original.frequencies.copy(), original.times_ms.copy(), original.metadata)
        for policy, world in zip(policies, [original, altered], strict=True):
            receiver = Receiver(config.receiver)
            receiver.previous = previous
            sl = slice(action.start, action.start + action.width)
            obs = receiver.observe(t, action, world.energy[t, sl], world.detector_uniform[t, sl], world.false_alarm_uniform[t, sl])
            assert tuple(v.band for v in obs.values) == action.bands
            policy.update(obs)
        previous = action.start
        np.testing.assert_array_equal(policies[0].belief.alpha, policies[1].belief.alpha)
        np.testing.assert_array_equal(policies[0].belief.beta, policies[1].belief.beta)


def test_receiver_bandwidth_and_immutable_observations():
    c = ExperimentConfig(horizon=24)
    env = SpectrumEnvironment(make_simulation(c), c.receiver)
    obs = env.step(Action(8, 4))
    assert [v.band for v in obs.values] == [8, 9, 10, 11]
    with pytest.raises(FrozenInstanceError):
        obs.values[0].detected = True
    with pytest.raises(ValueError):
        Observation(0, 0, Action(0, 4), obs.values, 99, 0)
    for invalid in [Action(-1, 4), Action(45, 4), Action(0, 5), Action(0, 0)]:
        with pytest.raises(ValueError):
            env.step(invalid)


def test_world_read_only_and_seed_determinism():
    c = ExperimentConfig(horizon=24)
    a, b = make_simulation(c), make_simulation(c)
    assert a.fingerprint == b.fingerprint
    round_tripped = ExperimentConfig.model_validate_json(c.model_dump_json())
    assert a.fingerprint == make_simulation(round_tripped).fingerprint
    assert make_simulation(c.model_copy(update={"seed": 43})).fingerprint != a.fingerprint
    with pytest.raises(ValueError):
        a.energy[0, 0] = 0


def test_retuning_reduces_dwell_and_increases_cost():
    c = ExperimentConfig(horizon=24)
    env = SpectrumEnvironment(make_simulation(c), c.receiver)
    initial = env.step(Action(0, 4))
    stationary = env.step(Action(0, 4))
    moved = env.step(Action(32, 4))
    assert initial.retune_cost == stationary.retune_cost == 0
    assert moved.retune_cost > 0
    assert moved.effective_dwell_ms == stationary.effective_dwell_ms - c.receiver.retune_ms
    assert moved.effective_dwell_ms >= c.receiver.min_dwell_ms
    with pytest.raises(ValueError):
        ReceiverConfig(slot_ms=12, min_dwell_ms=10, retune_ms=8)


def test_receiver_uses_energy_not_truth(world_factory):
    c = ReceiverConfig(bands=8, window_width=2)
    a = world_factory([[True] * 8], [[-96.0] * 8])
    b = world_factory([[False] * 8], [[-96.0] * 8])
    assert SpectrumEnvironment(a, c).step(Action(0, 2)) == SpectrumEnvironment(b, c).step(Action(0, 2))
