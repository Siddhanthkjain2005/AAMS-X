"""Scheduler contract, posterior updates and discounting."""

from __future__ import annotations

import numpy as np
import pytest

from aamsx.contracts.observation import (
    FACTOR_ORDER,
    DecisionContext,
    Feedback,
    Observation,
)
from aamsx.contracts.scenario import ReceiverSpec, RewardWeights
from aamsx.schedulers import ARENA_ORDER, available, create, describe_all
from aamsx.schedulers.base import AblationFlags, Scheduler, SchedulerSetup

N_REGIONS = 16
WINDOW = 4
N_ANCHORS = N_REGIONS - WINDOW + 1


def make_setup(seed: int = 0, flags: AblationFlags | None = None) -> SchedulerSetup:
    return SchedulerSetup(
        n_regions=N_REGIONS,
        window_size=WINDOW,
        n_anchors=N_ANCHORS,
        horizon=200,
        budget=200.0,
        receiver=ReceiverSpec(window_size=WINDOW),
        reward=RewardWeights(),
        seed=seed,
        flags=flags or AblationFlags(),
    )


def make_context(step: int = 0, *, belief=None, change_flag: bool = False) -> DecisionContext:
    belief = np.full(N_REGIONS, 0.2) if belief is None else np.asarray(belief, dtype=np.float64)
    return DecisionContext(
        step=step,
        n_regions=N_REGIONS,
        window_size=WINDOW,
        belief=belief,
        uncertainty=np.full(N_REGIONS, 0.3),
        staleness=np.full(N_REGIONS, 0.1),
        steps_since_seen=np.zeros(N_REGIONS, dtype=np.int32),
        observation_counts=np.ones(N_REGIONS, dtype=np.int32),
        hit_rate=np.full(N_REGIONS, 0.2),
        information_gain=np.full(N_REGIONS, 0.4),
        periodicity_score=np.zeros(N_REGIONS),
        periodicity_period=np.zeros(N_REGIONS),
        sensing_cost=np.ones(N_ANCHORS),
        change_score=0.0,
        change_flag=change_flag,
        steps_since_change=step,
        budget_remaining=100.0,
        budget_fraction=0.5,
        horizon=200,
        temporal_features=np.zeros(8),
    )


def make_feedback(step: int, regions, detected) -> Feedback:
    regions = np.asarray(regions, dtype=np.int32)
    detected = np.asarray(detected, dtype=bool)
    observation = Observation(
        step=step,
        regions=regions,
        measured_db=np.where(detected, 6.0, -6.0).astype(np.float32),
        detected=detected,
        threshold_db=np.zeros(regions.size, dtype=np.float32),
        confidence=np.full(regions.size, 0.9, dtype=np.float32),
        cost=1.0,
        available=True,
        t_sec=float(step),
    )
    return Feedback(
        step=step,
        observation=observation,
        true_occupied=detected,
        reward=float(detected.sum()),
        reward_terms={},
        hits=int(detected.sum()),
        false_alarms=0,
        misses_in_window=0,
        budget_remaining=100.0,
    )


@pytest.mark.parametrize("name", sorted(available()))
def test_every_registered_scheduler_satisfies_the_protocol(name):
    scheduler = create(name)
    assert isinstance(scheduler, Scheduler)
    scheduler.reset(make_setup())
    proposal = scheduler.select(make_context())
    assert proposal.regions.size == WINDOW
    assert np.all(np.diff(proposal.regions) == 1), "the window must be contiguous"
    assert 0 <= proposal.anchor <= N_REGIONS - WINDOW
    assert np.isfinite(proposal.action_value)
    assert isinstance(proposal.factors, dict)
    scheduler.update(make_feedback(0, proposal.regions, np.ones(WINDOW, bool)))
    assert isinstance(scheduler.snapshot(), dict)


@pytest.mark.parametrize("name", sorted(available()))
def test_schedulers_never_leave_the_band(name):
    scheduler = create(name)
    scheduler.reset(make_setup(seed=7))
    for step in range(120):
        proposal = scheduler.select(make_context(step))
        assert proposal.regions.min() >= 0
        assert proposal.regions.max() < N_REGIONS
        scheduler.update(make_feedback(step, proposal.regions, np.arange(WINDOW) % 2 == 0))


def test_arena_order_is_a_subset_of_the_registry():
    assert set(ARENA_ORDER) <= set(available())
    assert "mag-nts" in available()


def test_catalogue_entries_are_descriptive():
    for entry in describe_all():
        assert entry["display_name"]
        assert len(str(entry["description"])) > 40


def test_round_robin_sweeps_the_band_exactly_once_per_cycle():
    scheduler = create("round-robin")
    scheduler.reset(make_setup())
    anchors = []
    for step in range(N_ANCHORS * 2):
        proposal = scheduler.select(make_context(step))
        anchors.append(proposal.anchor)
        scheduler.update(make_feedback(step, proposal.regions, np.zeros(WINDOW, bool)))
    covered = set()
    for anchor in anchors[: (N_REGIONS + WINDOW - 1) // WINDOW]:
        covered.update(range(anchor, anchor + WINDOW))
    assert covered == set(range(N_REGIONS)), "one cycle must cover the whole band"


def test_thompson_posterior_tracks_the_detection_rate():
    scheduler = create("thompson")
    scheduler.reset(make_setup())
    hot = np.arange(0, WINDOW, dtype=np.int32)
    for step in range(60):
        scheduler.update(make_feedback(step, hot, np.ones(WINDOW, bool)))
    assert np.all(scheduler.posterior_mean[hot] > 0.9)
    cold = np.arange(WINDOW, 2 * WINDOW, dtype=np.int32)
    for step in range(60):
        scheduler.update(make_feedback(step, cold, np.zeros(WINDOW, bool)))
    assert np.all(scheduler.posterior_mean[cold] < 0.1)
    # Untouched regions stay at the uninformative prior mean.
    assert scheduler.posterior_mean[-1] == pytest.approx(0.5)


def test_stationary_thompson_accumulates_evidence_without_bound():
    scheduler = create("thompson")
    scheduler.reset(make_setup())
    regions = np.arange(WINDOW, dtype=np.int32)
    for step in range(200):
        scheduler.update(make_feedback(step, regions, np.ones(WINDOW, bool)))
    assert scheduler.effective_samples[0] == pytest.approx(200.0, rel=1e-9)


def test_discounting_bounds_the_effective_sample_size():
    scheduler = create("nts")
    scheduler.reset(make_setup())
    regions = np.arange(WINDOW, dtype=np.int32)
    for step in range(2000):
        scheduler.update(make_feedback(step, regions, np.ones(WINDOW, bool)))
    # Steady state of a geometric filter with discount d is 1/(1-d).
    limit = 1.0 / (1.0 - scheduler.discount)
    assert scheduler.effective_samples[0] < limit * 1.05
    assert scheduler.effective_samples[0] > limit * 0.5


def test_change_flag_makes_nts_forget():
    scheduler = create("nts")
    scheduler.reset(make_setup())
    regions = np.arange(WINDOW, dtype=np.int32)
    for step in range(300):
        scheduler.update(make_feedback(step, regions, np.ones(WINDOW, bool)))
    before = scheduler.effective_samples[0]
    scheduler.select(make_context(300, change_flag=True))
    after = scheduler.effective_samples[0]
    assert after < before
    assert after == pytest.approx(before * scheduler.change_discount, rel=1e-9)
    assert scheduler.snapshot()["changes_seen"] == 1


def test_stationary_thompson_ignores_the_change_flag():
    scheduler = create("thompson")
    scheduler.reset(make_setup())
    regions = np.arange(WINDOW, dtype=np.int32)
    for step in range(100):
        scheduler.update(make_feedback(step, regions, np.ones(WINDOW, bool)))
    before = scheduler.effective_samples.copy()
    scheduler.select(make_context(100, change_flag=True))
    assert np.allclose(scheduler.effective_samples, before)


def test_mag_nts_reports_every_declared_factor():
    scheduler = create("mag-nts")
    scheduler.reset(make_setup())
    proposal = scheduler.select(make_context())
    missing = [name for name in FACTOR_ORDER if name not in proposal.factors]
    assert not missing, f"MAG-NTS must be explainable: missing factors {missing}"
    assert proposal.per_region_value is not None
    assert proposal.per_region_value.size in {N_REGIONS, N_ANCHORS}


def test_mag_nts_prefers_the_region_its_belief_favours():
    scheduler = create("mag-nts")
    scheduler.reset(make_setup(seed=3))
    belief = np.full(N_REGIONS, 0.02)
    belief[8:12] = 0.97
    anchors = []
    for step in range(40):
        context = make_context(step, belief=belief)
        proposal = scheduler.select(context)
        anchors.append(proposal.anchor)
        scheduler.update(make_feedback(step, proposal.regions, belief[proposal.regions] > 0.5))
    assert np.median(anchors) == pytest.approx(8, abs=2)


def test_identical_seeds_produce_identical_decisions():
    contexts = [make_context(step) for step in range(50)]
    runs = []
    for _ in range(2):
        scheduler = create("mag-nts")
        scheduler.reset(make_setup(seed=11))
        anchors = []
        for step, context in enumerate(contexts):
            proposal = scheduler.select(context)
            anchors.append(proposal.anchor)
            scheduler.update(make_feedback(step, proposal.regions, np.ones(WINDOW, bool)))
        runs.append(anchors)
    assert runs[0] == runs[1]


def test_different_seeds_diverge_for_a_stochastic_policy():
    first, second = [], []
    for target, seed in ((first, 1), (second, 99)):
        scheduler = create("thompson")
        scheduler.reset(make_setup(seed=seed))
        for step in range(60):
            proposal = scheduler.select(make_context(step))
            target.append(proposal.anchor)
            scheduler.update(make_feedback(step, proposal.regions, np.zeros(WINDOW, bool)))
    assert first != second


def test_reset_is_required_before_use():
    scheduler = create("mag-nts")
    with pytest.raises(RuntimeError, match="reset"):
        scheduler.select(make_context())


def test_ablation_label_reflects_the_active_components():
    assert AblationFlags().label == "full"
    assert AblationFlags(memory=False).label == "IG+CD+Per+Enc+Unc"
    off = AblationFlags(
        memory=False,
        information_gain=False,
        change_detection=False,
        periodicity=False,
        temporal_encoder=False,
        uncertainty_exploration=False,
    )
    assert off.label == "none"
