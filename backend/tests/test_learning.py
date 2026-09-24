import numpy as np

from backend.contracts import BandObservation, DecisionContext, PublicReceiver
from backend.scheduler import Policy
from backend.scheduler.belief import Belief
from backend.scheduler.change import ChangeDetector
from backend.scheduler.memory import AssociativeMemory
from backend.scheduler.periodicity import PeriodicityEstimator


def test_belief_hits_misses_missing_and_age():
    belief = Belief(8)
    assert np.allclose(belief.mean, 0.5)
    assert np.allclose(belief.uncertainty, 1)
    assert np.allclose(belief.information_gain, np.log(2) - 0.5)
    for t in range(12):
        belief.update(t, BandObservation(2, -80, True, 1, -96))
        belief.update(t, BandObservation(4, -96, False, 1, -96))
        belief.update(t, BandObservation(5, None, False, 0, -96, False))
    assert belief.mean[2] > 0.9 and belief.mean[4] < 0.1
    assert belief.mean[5] == 0.5 and belief.counts[5] == 0
    old_uncertainty = belief.uncertainty[2]
    belief.advance(200)
    assert old_uncertainty < belief.uncertainty[2] <= 1
    assert 0.5 < belief.mean[2] < 0.9


def test_low_confidence_hit_is_weaker_evidence():
    belief = Belief(8)
    belief.update(0, BandObservation(0, -94, True, 0.01, -96))
    belief.update(0, BandObservation(1, -80, True, 0.99, -96))
    assert belief.mean[0] < belief.mean[1]


def test_periodicity_requires_four_episodes_and_fits_recurrence():
    estimator = PeriodicityEstimator(1)
    for t in range(40):
        estimator.update(0, t, t % 18 == 0)
    assert estimator.predictions(39) == []
    for t in range(40, 120):
        estimator.update(0, t, t % 18 == 0)
    estimate = estimator.predictions(119)[0]
    assert estimate["period_slots"] == 18
    assert estimate["evidence_count"] == 7
    assert estimate["confidence"] >= 0.6
    assert abs(estimate["next_slot"] - 126) < 0.01
    assert estimator.predictions(400)[0]["confidence"] < estimate["confidence"]


def test_adjacent_hits_not_counted_as_periodic_episodes():
    estimator = PeriodicityEstimator(1)
    for t in range(20):
        estimator.update(0, t, True)
    assert len(estimator.events[0]) == 1
    assert estimator.predictions(20) == []


def test_cusum_shift_detection_and_no_unobserved_updates():
    detector = ChangeDetector(2)
    for t in range(15):
        assert detector.update(0, 0, 0.05, t) is None
    events = [detector.update(0, 1, 0.05, t) for t in range(15, 25)]
    assert any(event and event["direction"] == "activity increased" for event in events)
    assert detector.counts[1] == 0
    assert detector.priority(25)[0] > detector.priority(25)[1]


def test_associative_memory_needs_supported_past_outcomes():
    memory = AssociativeMemory(8)
    for t in range(4):
        memory.update(2, True, t)
    assert not memory.recall_all(4)[1]
    for t in range(4, 20):
        memory.update(2, True, t)
    scores, matches = memory.recall_all(20)
    assert scores[2] > 0 and matches[0]["previous_step"] < 20
    assert matches[0]["support"] >= 3


def test_fixed_sweep_covers_tail_and_is_open_loop():
    policy = Policy("fixed", PublicReceiver(10, 4, 100, 8, 0.3), 42)
    starts = [policy.select_action(DecisionContext(t, None)).action.start for t in range(6)]
    assert starts == [0, 4, 6, 0, 4, 6]
    policy.belief.alpha[:] = 999
    assert policy.select_action(DecisionContext(6, 6)).action.start == 0


def test_all_baselines_and_ablations_obey_geometry():
    for algorithm in ["magnts", "fixed", "random", "ucb", "thompson", "no_memory", "no_information", "no_change"]:
        policy = Policy(algorithm, PublicReceiver(16, 3, 100, 8, 0.3), 42)
        decision = policy.select_action(DecisionContext(0, None))
        assert decision.action.width == 3
        assert 0 <= decision.action.start <= 13
        if algorithm == "no_memory":
            assert decision.components["memory"] == 0
        if algorithm == "no_information":
            assert decision.components["information"] == 0
        if algorithm == "no_change":
            assert decision.components["change"] == 0
