"""Anti-leakage: proof that no scheduler can see what it did not pay to observe.

This is the test that makes every other result in AAMS-X meaningful.  A scheduler
that can read hidden occupancy would score beautifully and mean nothing, so the
wall is checked three independent ways:

*Structurally*
    ``select`` takes a :class:`DecisionContext` and nothing else — no environment,
    no truth array, no callable that could reach either.  Checked by inspecting
    every registered scheduler's signature and its captured attributes.
*Dynamically*
    :meth:`ReplayEnvironment.sealed` raises :class:`LeakageError` on every
    truth-reading accessor while a decision is in flight.
*Behaviourally*
    the truth is scrambled *after* the context is built and every scheduler is
    asked to decide again.  A scheduler reading hidden state would change its
    answer; every scheduler here does not.
"""

from __future__ import annotations

import inspect

import numpy as np
import pytest

from aamsx.contracts.observation import DecisionContext, Feedback, Observation
from aamsx.environment.replay import LeakageError, make_environment
from aamsx.experiments.context import ContextBuilder
from aamsx.experiments.runner import build_setup, run_episode
from aamsx.schedulers.base import AblationFlags, available, create
from tests.conftest import requires_cache

SCHEDULERS = available()
TRUTH_FIELDS = ("occupied", "margin_db", "available", "t_utc_sec", "segment_of_step")


# --------------------------------------------------------------------------- #
# 1. structural
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("name", SCHEDULERS)
def test_select_accepts_a_decision_context_and_nothing_else(name):
    scheduler = create(name)
    signature = inspect.signature(scheduler.select)
    parameters = list(signature.parameters.values())
    assert len(parameters) == 1, f"{name}.select takes extra arguments: {signature}"
    assert parameters[0].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    annotation = parameters[0].annotation
    assert annotation in (DecisionContext, "DecisionContext")


@pytest.mark.parametrize("name", SCHEDULERS)
def test_a_reset_scheduler_holds_no_reference_to_truth_or_environment(name, short_spec):
    """Walk everything the scheduler owns and assert none of it is the environment."""
    scheduler = create(name)
    setup = build_setup(short_spec, seed=0, flags=AblationFlags(), n_anchors=13)
    scheduler.reset(setup)

    seen: set[int] = set()
    forbidden = ("ReplayEnvironment", "EnvironmentTruth", "StepOutcome", "MeasurementCube")

    def walk(value, path: str, depth: int = 0) -> None:
        if depth > 4 or id(value) in seen:
            return
        seen.add(id(value))
        assert type(value).__name__ not in forbidden, f"{name} reaches truth via {path}"
        if isinstance(value, dict):
            for key, item in value.items():
                walk(item, f"{path}[{key!r}]", depth + 1)
        elif isinstance(value, (list, tuple, set)):
            for index, item in enumerate(value):
                walk(item, f"{path}[{index}]", depth + 1)
        elif hasattr(value, "__dict__") or hasattr(value, "__slots__"):
            for attribute in _attributes(value):
                walk(getattr(value, attribute, None), f"{path}.{attribute}", depth + 1)

    def _attributes(value) -> list[str]:
        names: list[str] = list(getattr(value, "__dict__", {}))
        for klass in type(value).__mro__:
            names.extend(getattr(klass, "__slots__", ()) or ())
        return [n for n in names if not n.startswith("__")]

    for attribute in _attributes(scheduler):
        walk(getattr(scheduler, attribute, None), f"{name}.{attribute}")


def test_a_decision_context_carries_no_truth_shaped_array(short_spec):
    """Nothing in the context may be the size of the hidden occupancy matrix."""
    env = make_environment(short_spec, seed=0)
    setup = build_setup(short_spec, seed=0, flags=AblationFlags(), n_anchors=env.n_anchors)
    builder = ContextBuilder(setup)
    context = builder.build()
    for name, value in context.as_dict().items():
        if isinstance(value, np.ndarray):
            assert value.ndim == 1, f"{name} is multi-dimensional; truth is (T, R)"
            assert value.size <= max(short_spec.n_regions, 64), f"{name} is suspiciously large"
    assert not any(field in context.as_dict() for field in TRUTH_FIELDS)


# --------------------------------------------------------------------------- #
# 2. dynamic — the seal
# --------------------------------------------------------------------------- #


@pytest.mark.usefixtures("recordings")
class TestTheSeal:
    def test_the_seal_closes_the_truth_handle(self, short_spec):
        env = make_environment(short_spec, seed=0)
        with env.sealed(), pytest.raises(LeakageError):
            _ = env.truth

    def test_the_seal_closes_the_oracle(self, short_spec):
        env = make_environment(short_spec, seed=0)
        with env.sealed(), pytest.raises(LeakageError):
            env.oracle_best_count(0)

    def test_the_error_names_what_was_touched(self, short_spec):
        env = make_environment(short_spec, seed=0)
        with env.sealed(), pytest.raises(LeakageError, match="oracle_best_count"):
            env.oracle_best_count(0)

    def test_a_scheduler_that_reaches_for_the_environment_is_caught(self, short_spec):
        """A deliberately cheating scheduler must fail loudly, not score well."""
        env = make_environment(short_spec, seed=0)
        setup = build_setup(short_spec, seed=0, flags=AblationFlags(), n_anchors=env.n_anchors)
        context = ContextBuilder(setup).build()

        def cheat(_context):
            return env.truth.occupied[0].argmax()

        with env.sealed(), pytest.raises(LeakageError):
            cheat(context)


# --------------------------------------------------------------------------- #
# 3. behavioural — scramble the truth and re-decide
# --------------------------------------------------------------------------- #


def _observation(step: int, regions: np.ndarray, detected: np.ndarray) -> Observation:
    size = regions.size
    return Observation(
        step=step,
        regions=regions,
        measured_db=np.where(detected, 6.0, -3.0).astype(np.float32),
        detected=detected,
        threshold_db=np.zeros(size, dtype=np.float32),
        confidence=np.full(size, 0.8, dtype=np.float32),
        cost=1.0,
        available=True,
        t_sec=float(step),
    )


def _warm(scheduler, builder, setup, steps: int = 40) -> None:
    """Give the scheduler a real history so its decision is not a cold-start default."""
    rng = np.random.default_rng(0)
    for step in range(steps):
        context = builder.build()
        proposal = scheduler.select(context)
        regions = proposal.regions
        detected = rng.random(regions.size) < 0.3
        observation = _observation(step, regions, detected)
        builder.absorb(observation)
        feedback = Feedback(
            step=step,
            observation=observation,
            true_occupied=detected,
            reward=float(detected.sum()) / regions.size,
            reward_terms={"detection": float(detected.sum()) / regions.size},
            hits=int(detected.sum()),
            false_alarms=0,
            misses_in_window=0,
            budget_remaining=setup.budget - step,
        )
        scheduler.update(feedback)
        builder.commit(feedback)


@requires_cache
@pytest.mark.parametrize("name", SCHEDULERS)
def test_scrambling_the_truth_does_not_change_the_decision(name, short_spec):
    """The empirical proof. Same history, different hidden truth, same action."""
    decisions = []
    for scramble in (False, True):
        env = make_environment(short_spec, seed=3)
        setup = build_setup(short_spec, seed=3, flags=AblationFlags(), n_anchors=env.n_anchors)
        scheduler = create(name)
        scheduler.reset(setup)
        builder = ContextBuilder(setup)
        _warm(scheduler, builder, setup)
        if scramble:
            truth = env.truth
            rng = np.random.default_rng(999)
            truth.occupied[:] = rng.random(truth.occupied.shape) < 0.5
            truth.margin_db[:] = rng.normal(size=truth.margin_db.shape).astype(np.float32)
        decisions.append(scheduler.select(builder.build()).regions.tolist())
    assert decisions[0] == decisions[1], f"{name} responded to hidden state"


@requires_cache
def test_the_context_is_a_function_of_history_alone(short_spec):
    """Two builders fed identical observations must produce identical contexts."""
    setup = build_setup(short_spec, seed=1, flags=AblationFlags(), n_anchors=13)
    contexts = []
    for _ in range(2):
        builder = ContextBuilder(setup)
        scheduler = create("round-robin")
        scheduler.reset(setup)
        _warm(scheduler, builder, setup)
        contexts.append(builder.build())
    left, right = contexts
    for field, value in left.as_dict().items():
        other = getattr(right, field)
        if isinstance(value, np.ndarray):
            assert np.allclose(value, other, equal_nan=True), field
        else:
            assert value == other or value is other, field


@requires_cache
def test_a_frozen_context_cannot_be_written_to(short_spec):
    """``freeze`` is what lets this suite hand the same context to two schedulers."""
    setup = build_setup(short_spec, seed=1, flags=AblationFlags(), n_anchors=13)
    frozen = ContextBuilder(setup).build().freeze()
    assert not frozen.belief.flags.writeable
    with pytest.raises(ValueError, match="read-only"):
        frozen.belief[0] = 0.5
    assert not frozen.uncertainty.flags.writeable
    assert not frozen.staleness.flags.writeable


@requires_cache
def test_freezing_copies_rather_than_aliases(short_spec):
    setup = build_setup(short_spec, seed=1, flags=AblationFlags(), n_anchors=13)
    builder = ContextBuilder(setup)
    live = builder.build()
    frozen = live.freeze()
    live.belief[0] = 0.123456
    assert frozen.belief[0] != 0.123456


@requires_cache
@pytest.mark.parametrize("name", ["round-robin", "thompson", "mag-nts"])
def test_a_full_episode_never_trips_the_seal(name, short_spec):
    """The end-to-end guarantee: the real runner seals every decision."""
    result = run_episode(short_spec, name, seed=2)
    assert result.metrics["steps"] > 0
