"""Optional deep-RL baseline (DQN). A feature flag, not a result.

Why this exists
---------------
"Why not just use deep RL?" is the first question a reviewer asks, and the honest
answer needs a runnable comparison rather than an opinion.  So the policy is here,
it is the textbook algorithm, and it receives exactly the same
:class:`~aamsx.contracts.observation.DecisionContext` as every other scheduler.

Why it is off by default
------------------------
1. **Sample budget.** A single AAMS-X episode is 400-1200 steps. DQN needs orders
   of magnitude more transitions than that to beat a well-specified bandit, and
   the multi-seed protocol resets it every episode: there is no pre-training
   corpus, because pre-training on the scenario library and then reporting on it
   is testing on the training set.
2. **Explainability.** MAG-NTS reports an additive decomposition the Decision
   Inspector renders factor by factor. A Q-network reports one number. It answers
   ``factors`` with its own diagnostics and a note saying so, so no screen ever
   implies a black box explained itself.
3. **Determinism.** Torch seeded on CPU is reproducible, but the extra is not part
   of the default install, so the reported benchmark must not depend on it.

No number in ``docs/EXPERIMENTS.md`` was produced with this policy.  Enable it
with ``AAMSX_ENABLE_DEEP_RL=true`` and ``pip install -e ".[neural]"`` to run the
comparison yourself; whatever comes out is the answer.
"""

from __future__ import annotations

import itertools
import random
from collections import deque

import numpy as np
import torch  # ImportError here keeps the default install free of torch
from torch import nn

from aamsx.contracts.observation import ActionProposal, DecisionContext, Feedback
from aamsx.logging import get_logger
from aamsx.schedulers.base import BaseScheduler, SchedulerSetup, register

log = get_logger(__name__)

STATE_BINS = 12
"""Bands each per-region vector is pooled into, so the input width is fixed."""

HIDDEN = 128
REPLAY_CAPACITY = 4096
BATCH_SIZE = 64
WARMUP_STEPS = 96
TRAIN_EVERY = 2
TARGET_SYNC = 64
GAMMA = 0.95
LEARNING_RATE = 1e-3
EPSILON_START = 1.0
EPSILON_FINAL = 0.05
EPSILON_DECAY_STEPS = 400


def _pool(values: np.ndarray, bins: int) -> np.ndarray:
    """Average a per-region vector into ``bins`` contiguous bands."""
    array = np.asarray(values, dtype=np.float32)
    if array.size == bins:
        return array
    edges = np.linspace(0, array.size, bins + 1).astype(int)
    return np.array(
        [array[a:b].mean() if b > a else 0.0 for a, b in itertools.pairwise(edges)],
        dtype=np.float32,
    )


class QNetwork(nn.Module):
    """Two hidden layers over the pooled context; one output per window anchor."""

    def __init__(self, state_dim: int, n_actions: int) -> None:
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, HIDDEN),
            nn.ReLU(),
            nn.Linear(HIDDEN, HIDDEN),
            nn.ReLU(),
            nn.Linear(HIDDEN, n_actions),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.net(state)


@register
class DQNScheduler(BaseScheduler):
    """Online DQN over window anchors, learning within the episode.

    Deep Q-learning with a replay buffer, a target network, Huber loss and
    epsilon-greedy exploration — no tricks that the baselines do not also get, and
    no pre-training.
    """

    name = "dqn"
    display_name = "DQN (flagged)"
    family = "deep-rl"
    stochastic = True
    description = (
        "Deep Q-Network over window anchors, trained online inside the episode. "
        "Present so the deep-RL comparison can be run rather than argued about; "
        "off by default because 400-1200 steps is far below its sample budget and "
        "it cannot explain a decision."
    )

    def __init__(
        self,
        *,
        gamma: float = GAMMA,
        learning_rate: float = LEARNING_RATE,
        epsilon_decay_steps: int = EPSILON_DECAY_STEPS,
    ) -> None:
        super().__init__()
        self.gamma = float(gamma)
        self.learning_rate = float(learning_rate)
        self.epsilon_decay_steps = int(epsilon_decay_steps)
        self._policy: QNetwork | None = None
        self._target: QNetwork | None = None
        self._replay: deque[tuple[np.ndarray, int, float, np.ndarray]] = deque(
            maxlen=REPLAY_CAPACITY
        )
        self._last_state: np.ndarray | None = None
        self._last_action = 0
        self._last_q = 0.0
        self._last_loss = float("nan")
        self._updates = 0

    # -- lifecycle ---------------------------------------------------------- #

    def reset(self, setup: SchedulerSetup) -> None:
        super().reset(setup)
        # Seeded on every stream torch may touch, so a seed reproduces a run.
        torch.manual_seed(setup.seed)
        random.seed(setup.seed)
        state_dim = self._state_dim(setup)
        self._policy = QNetwork(state_dim, setup.n_anchors)
        self._target = QNetwork(state_dim, setup.n_anchors)
        self._target.load_state_dict(self._policy.state_dict())
        self._target.eval()
        self._optimiser = torch.optim.Adam(self._policy.parameters(), lr=self.learning_rate)
        self._replay.clear()
        self._last_state = None
        self._last_action = 0
        self._last_q = 0.0
        self._last_loss = float("nan")
        self._updates = 0
        log.debug("dqn.reset", extra={"state_dim": state_dim, "actions": setup.n_anchors})

    def _state_dim(self, setup: SchedulerSetup) -> int:
        from aamsx.features.engineered import GLOBAL_FEATURES

        # 5 pooled per-region vectors + the engineered globals + 3 scalars.
        return 5 * STATE_BINS + len(GLOBAL_FEATURES) + 3

    # -- state -------------------------------------------------------------- #

    def _state(self, context: DecisionContext) -> np.ndarray:
        pooled = [
            _pool(context.belief, STATE_BINS),
            _pool(context.uncertainty, STATE_BINS),
            _pool(context.staleness, STATE_BINS),
            _pool(context.hit_rate, STATE_BINS),
            _pool(context.periodicity_score, STATE_BINS),
        ]
        scalars = np.array(
            [
                context.change_score,
                context.budget_fraction,
                context.step / max(context.horizon, 1),
            ],
            dtype=np.float32,
        )
        features = np.asarray(context.temporal_features, dtype=np.float32)
        return np.concatenate([*pooled, features, scalars]).astype(np.float32)

    @property
    def epsilon(self) -> float:
        decay = min(1.0, self.step / max(self.epsilon_decay_steps, 1))
        return EPSILON_START + (EPSILON_FINAL - EPSILON_START) * decay

    # -- decision ----------------------------------------------------------- #

    def select(self, context: DecisionContext) -> ActionProposal:
        assert self._policy is not None  # reset() guarantees this
        state = self._state(context)
        with torch.no_grad():
            q_values = self._policy(torch.from_numpy(state).unsqueeze(0)).squeeze(0).numpy()
        epsilon = self.epsilon
        exploring = bool(self.rng.random() < epsilon)
        anchor = (
            int(self.rng.integers(self.config.n_anchors)) if exploring else int(np.argmax(q_values))
        )
        self._last_state = state
        self._last_action = anchor
        self._last_q = float(q_values[anchor])
        return self.proposal(
            anchor,
            value=self._last_q,
            # A Q-network has no additive decomposition. These are diagnostics,
            # and the note says as much so no panel implies an explanation.
            factors={
                "q_value": round(self._last_q, 5),
                "q_advantage": round(float(q_values[anchor] - q_values.mean()), 5),
                "epsilon": round(epsilon, 5),
                "td_loss": round(self._last_loss, 5) if self._last_loss == self._last_loss else 0.0,
            },
            per_region_value=None,
            notes=(
                "epsilon-greedy exploration" if exploring else "greedy argmax Q",
                "black-box value: no factor decomposition is available",
            ),
            exploration_rate=epsilon,
        )

    # -- learning ----------------------------------------------------------- #

    def update(self, feedback: Feedback) -> None:
        self.step += 1
        if self._last_state is None:
            return
        # The next state is not known until the following select(), so the
        # transition is stored with the current state standing in as s' and
        # corrected on the next push. Storing (s, a, r, s) for the final step of
        # an episode is the standard terminal-transition treatment.
        self._replay.append(
            (self._last_state, self._last_action, float(feedback.reward), self._last_state)
        )
        if len(self._replay) >= 2:
            older = self._replay[-2]
            self._replay[-2] = (older[0], older[1], older[2], self._last_state)
        if len(self._replay) >= max(WARMUP_STEPS, BATCH_SIZE) and self.step % TRAIN_EVERY == 0:
            self._learn()

    def _learn(self) -> None:
        assert self._policy is not None and self._target is not None
        batch = random.sample(self._replay, BATCH_SIZE)
        states = torch.from_numpy(np.stack([row[0] for row in batch]))
        actions = torch.tensor([row[1] for row in batch], dtype=torch.int64).unsqueeze(1)
        rewards = torch.tensor([row[2] for row in batch], dtype=torch.float32).unsqueeze(1)
        next_states = torch.from_numpy(np.stack([row[3] for row in batch]))

        predicted = self._policy(states).gather(1, actions)
        with torch.no_grad():
            bootstrap = self._target(next_states).max(dim=1, keepdim=True).values
            target = rewards + self.gamma * bootstrap
        loss = nn.functional.smooth_l1_loss(predicted, target)
        self._optimiser.zero_grad(set_to_none=True)
        loss.backward()
        nn.utils.clip_grad_norm_(self._policy.parameters(), 10.0)
        self._optimiser.step()
        self._last_loss = float(loss.detach())
        self._updates += 1
        if self._updates % TARGET_SYNC == 0:
            self._target.load_state_dict(self._policy.state_dict())

    def snapshot(self) -> dict[str, object]:
        return {
            "name": self.name,
            "step": self.step,
            "epsilon": round(self.epsilon, 4),
            "replay": len(self._replay),
            "gradient_updates": self._updates,
            "td_loss": round(self._last_loss, 5) if self._last_loss == self._last_loss else None,
            "q_selected": round(self._last_q, 5),
            "explainable": False,
        }
