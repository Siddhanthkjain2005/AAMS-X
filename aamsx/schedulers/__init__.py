"""Scheduler registry.

Importing this package registers every built-in policy.  The optional deep-RL
policy is imported defensively: if PyTorch is absent (the default install), the
module simply does not register and the rest of the platform is unaffected.
"""

from __future__ import annotations

from aamsx.logging import get_logger
from aamsx.schedulers.base import (
    AblationFlags,
    BaseScheduler,
    Scheduler,
    SchedulerSetup,
    available,
    create,
    describe_all,
    register,
)
from aamsx.schedulers.baselines import (
    RandomScanScheduler,
    RoundRobinScheduler,
    UCBScheduler,
)
from aamsx.schedulers.mag_nts import MagNtsScheduler, MagWeights
from aamsx.schedulers.thompson import (
    NonStationaryTSScheduler,
    ThompsonSamplingScheduler,
)

log = get_logger(__name__)

#: Display order used by the Algorithm Arena, weakest baseline first.
ARENA_ORDER: tuple[str, ...] = (
    "round-robin",
    "random",
    "ucb",
    "thompson",
    "nts",
    "mag-nts",
)

try:  # pragma: no cover - exercised only when the neural extra is installed
    from aamsx.schedulers.dqn import DQNScheduler  # noqa: F401

    _DEEP_RL_AVAILABLE = True
except ImportError as exc:  # torch missing is the normal, supported case
    _DEEP_RL_AVAILABLE = False
    log.debug("schedulers.deep_rl_unavailable", extra={"reason": str(exc)})


def deep_rl_available() -> bool:
    """Whether the optional PyTorch policy registered successfully."""
    return _DEEP_RL_AVAILABLE


__all__ = [
    "ARENA_ORDER",
    "AblationFlags",
    "BaseScheduler",
    "MagNtsScheduler",
    "MagWeights",
    "NonStationaryTSScheduler",
    "RandomScanScheduler",
    "RoundRobinScheduler",
    "Scheduler",
    "SchedulerSetup",
    "ThompsonSamplingScheduler",
    "UCBScheduler",
    "available",
    "create",
    "deep_rl_available",
    "describe_all",
    "register",
]
