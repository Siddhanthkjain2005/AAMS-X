"""Scenario library — real windows selected by measured behaviour.

Every scenario in AAMS-X is a query, not a constant.  ``scripts/build_index.py``
characterises each window in the offline cache; the presets below then ask that
index for the window that best exhibits the behaviour a scenario needs — "the
strongest measured periodicity", "the lowest-contrast window", "the densest
persistent block".  The scenario therefore carries a real recording, a real time
range and measured statistics that were never asserted by hand.

Randomised *families* work the same way: :func:`sample_scenario` draws a
different real window each seed, which is what makes multi-seed evaluation an
average over environments rather than a re-run of one lucky episode.
"""

from __future__ import annotations

from dataclasses import replace
from functools import cache, lru_cache
from typing import Any

import numpy as np

from aamsx.contracts.scenario import (
    ReceiverSpec,
    RewardWeights,
    ScenarioFamily,
    ScenarioSpec,
    SegmentSpec,
    SplitRole,
)
from aamsx.datasets.stations import get_station
from aamsx.datasets.windows import WindowRef, query
from aamsx.logging import get_logger

log = get_logger(__name__)

DEFAULT_REGIONS = 48
DEFAULT_SEGMENT_STEPS = 1200

_STAT_FIELDS: tuple[str, ...] = (
    "occupancy",
    "persistence",
    "onset_rate",
    "burstiness",
    "intermittent_regions",
    "persistent_regions",
    "quiet_regions",
    "period_steps",
    "period_strength",
    "concentration",
    "profile_drift",
    "mean_margin_db",
    "p95_margin_db",
    "archetype",
)


def _as_ref(row: dict[str, Any]) -> WindowRef:
    stats = {field: row[field] for field in _STAT_FIELDS if field in row}
    return WindowRef(
        recording_id=str(row["recording_id"]),
        station=str(row["station"]),
        start_step=int(row["start_step"]),
        time_bin=int(row["time_bin"]),
        n_steps=int(row["n_steps"]),
        n_regions=int(row["n_regions"]),
        stats=stats,
        profile=tuple(float(v) for v in (row.get("profile") or ())),
    )


def find_windows(
    *,
    where: str = "TRUE",
    order_by: str = "occupancy DESC",
    limit: int = 1,
    roles: tuple[SplitRole, ...] | None = None,
) -> list[WindowRef]:
    """Query the measured window index.

    ``roles`` filters by the catalogue's generalisation split, which is how the
    unseen-test scenarios are kept free of any station used for tuning.
    """
    clauses = [f"({where})"]
    if roles:
        allowed = {
            station.name
            for station in (get_station(key) for key in _catalogue_keys())
            if station.role in roles
        }
        listed = ", ".join(f"'{name}'" for name in sorted(allowed))
        clauses.append(f"station IN ({listed})")
    sql = (
        f"SELECT * FROM windows WHERE {' AND '.join(clauses)} "
        f"ORDER BY {order_by}, recording_id, time_bin, start_step LIMIT {limit}"
    )
    return [_as_ref(row) for row in query(sql)]


@lru_cache(maxsize=1)
def _catalogue_keys() -> tuple[str, ...]:
    from aamsx.datasets.stations import STATIONS

    return tuple(station.key for station in STATIONS)


def _segment(ref: WindowRef, *, phase: str = "", label: str = "") -> SegmentSpec:
    return SegmentSpec(
        recording_id=ref.recording_id,
        start_step=ref.start_step,
        n_steps=ref.n_steps,
        label=label or f"{ref.station} +{ref.start_step * 0.25 / 60:.0f} min",
        phase=phase,
    )


def profile_similarity(left: WindowRef, right: WindowRef) -> float:
    """Pearson correlation between two windows' per-region occupancy profiles.

    This is the number that decides whether a splice is a real distribution shift.
    Two recordings can differ wildly in overall occupancy and still present the
    *same* problem to a scheduler if their busy regions line up; conversely two
    windows at similar occupancy can be completely different problems. Correlating
    the profiles measures the thing that actually matters — whether what the policy
    learned still applies.
    """
    if not left.profile or not right.profile or len(left.profile) != len(right.profile):
        return 0.0
    a = np.asarray(left.profile, dtype=np.float64)
    b = np.asarray(right.profile, dtype=np.float64)
    a, b = a - a.mean(), b - b.mean()
    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(a @ b / denominator) if denominator > 1e-12 else 0.0


def find_pair(
    *,
    where: str,
    n_steps: int,
    time_bin: int,
    mode: str = "dissimilar",
    roles: tuple[SplitRole, ...] | None = None,
    candidates: int = 120,
    same_station: bool = False,
    min_gap_spans: float = 4.0,
) -> tuple[WindowRef, WindowRef]:
    """Pick two indexed windows whose activity profiles are as unlike (or alike) as possible.

    ``min_gap_spans`` only bites for same-station pairs, and it is the guard that
    keeps the recurrence experiment honest: indexed windows are strided at half
    their length, so the most "similar" same-station pair is always two windows
    that overlap in time. Replaying overlapping data is not a recurring
    environment, it is the same environment, so a real gap is required.
    """
    pool = find_windows(
        where=f"({where}) AND n_steps = {n_steps} AND time_bin = {time_bin}",
        order_by="occupancy DESC",
        limit=candidates,
        roles=roles,
    )
    if len(pool) < 2:
        raise LookupError(
            f"fewer than two indexed windows match {where!r} at n_steps={n_steps}, "
            f"time_bin={time_bin}"
        )
    span_native = n_steps * time_bin
    minimum_gap = min_gap_spans * span_native
    best: tuple[float, WindowRef, WindowRef] | None = None
    for index, left in enumerate(pool):
        for right in pool[index + 1 :]:
            if same_station != (left.station == right.station):
                continue
            if same_station and abs(left.start_step - right.start_step) < minimum_gap:
                continue
            score = profile_similarity(left, right)
            signed = -score if mode == "dissimilar" else score
            if best is None or signed > best[0]:
                best = (signed, left, right)
    if best is None:
        raise LookupError(
            f"no {'same' if same_station else 'cross'}-station pair among {len(pool)} candidates"
        )
    return best[1], best[2]


def _require(refs: list[WindowRef], description: str) -> WindowRef:
    if not refs:
        raise LookupError(
            f"the window index contains no window matching {description}; "
            "rebuild it with scripts/build_index.py or ingest more recordings"
        )
    return refs[0]


# --------------------------------------------------------------------------- #
# presets
# --------------------------------------------------------------------------- #

TUNING_ROLES: tuple[SplitRole, ...] = ("train", "validation")
"""Roles a preset may use unless it is explicitly the held-out test.

Keeping every other preset inside the tuning split is what makes the
'Unseen Generalization Test' claim airtight: the held-out receivers appear in
exactly one scenario, and nothing is tuned against them.
"""

PRESET_ORDER: tuple[str, ...] = (
    "easy-static",
    "periodic-challenge",
    "high-noise",
    "sudden-shift",
    "recurring-environment",
    "extreme-budget",
    "unseen-generalization",
)


def _easy_static() -> ScenarioSpec:
    ref = _require(
        find_windows(
            where=(
                "persistence > 0.85 AND occupancy BETWEEN 0.10 AND 0.35 "
                "AND period_steps = 0 AND time_bin = 4 AND n_steps = 1200"
            ),
            order_by="persistent_regions DESC, persistence DESC",
            roles=TUNING_ROLES,
        ),
        "a highly persistent window",
    )
    return ScenarioSpec(
        scenario_id="easy-static",
        name="Easy Static",
        description=(
            f"A single persistent window from {ref.station}: measured persistence "
            f"{ref.stats['persistence']:.2f} with {ref.stats['persistent_regions']} regions "
            "occupied more than half the time. Activity barely moves, so any scheduler that "
            "remembers where it found signal should do well — the control case."
        ),
        family="persistent",
        segments=(_segment(ref, phase="static"),),
        n_regions=ref.n_regions,
        time_bin=ref.time_bin,
        tags=("baseline", "control", ref.station),
    )


def _periodic_challenge() -> ScenarioSpec:
    ref = _require(
        find_windows(
            where="period_steps > 0 AND occupancy < 0.35 AND n_steps = 1200",
            order_by="period_strength DESC",
            roles=TUNING_ROLES,
        ),
        "a window with significant measured periodicity",
    )
    period_sec = int(ref.stats["period_steps"]) * ref.time_bin * 0.25
    return ScenarioSpec(
        scenario_id="periodic-challenge",
        name="Periodic Challenge",
        description=(
            f"The strongest periodicity measured anywhere in the cache: {ref.station} repeats "
            f"every {int(ref.stats['period_steps'])} steps ({period_sec / 60:.0f} min) with "
            f"autocorrelation {ref.stats['period_strength']:.2f}. A scheduler that models "
            "recurrence should anticipate the next onset instead of rediscovering it."
        ),
        family="periodic",
        segments=(_segment(ref, phase="periodic"),),
        n_regions=ref.n_regions,
        time_bin=ref.time_bin,
        tags=("periodicity", "recurrence", ref.station),
    )


def _high_noise() -> ScenarioSpec:
    ref = _require(
        find_windows(
            where=(
                "occupancy > 0.05 AND occupancy < 0.35 AND p95_margin_db < 9.0 "
                "AND time_bin = 4 AND n_steps = 1200"
            ),
            order_by="mean_margin_db ASC",
            roles=TUNING_ROLES,
        ),
        "a low-contrast window",
    )
    return ScenarioSpec(
        scenario_id="high-noise",
        name="High Noise",
        description=(
            f"The lowest-contrast real window available ({ref.station}: mean cell sits "
            f"{ref.stats['mean_margin_db']:.2f} dB from its own decision threshold, 95th "
            f"percentile only {ref.stats['p95_margin_db']:.1f} dB above it) seen through a "
            "receiver at 1.5 dB of dwell noise instead of the usual 0.4. Almost everything "
            "sits near the boundary, so "
            "confident detection and honest uncertainty pull apart."
        ),
        family="noisy",
        segments=(_segment(ref, phase="low-contrast"),),
        n_regions=ref.n_regions,
        time_bin=ref.time_bin,
        receiver=ReceiverSpec(window_size=4, noise_db=1.5, switch_cost=0.15),
        tags=("noise", "uncertainty", ref.station),
    )


def _sudden_shift() -> ScenarioSpec:
    steps = DEFAULT_SEGMENT_STEPS // 2
    before, after = find_pair(
        where="occupancy BETWEEN 0.04 AND 0.35",
        n_steps=steps,
        time_bin=4,
        mode="dissimilar",
        roles=TUNING_ROLES,
    )
    similarity = profile_similarity(before, after)
    return ScenarioSpec(
        scenario_id="sudden-shift",
        name="Sudden Shift",
        description=(
            f"Phase A is {before.station} at {before.stats['occupancy']:.1%} occupancy; at the "
            f"halfway point the environment becomes {after.station} at "
            f"{after.stats['occupancy']:.1%}. The two activity profiles correlate at only "
            f"{similarity:+.2f}, so almost nothing the scheduler learned in phase A still "
            "applies in phase B. Both halves are real recordings from different receivers and "
            "bands; only the splice point is our choice, which is what makes recovery time "
            "measurable."
        ),
        family="distribution-shift",
        segments=(
            replace(_segment(before, phase="A"), label=f"A · {before.station}"),
            replace(_segment(after, phase="B"), label=f"B · {after.station}"),
        ),
        n_regions=before.n_regions,
        time_bin=4,
        tags=("change-detection", "recovery", before.station, after.station),
    )


def _recurring_environment() -> ScenarioSpec:
    steps = DEFAULT_SEGMENT_STEPS // 3
    home, revisit = find_pair(
        where="occupancy BETWEEN 0.04 AND 0.35 AND persistence > 0.6",
        n_steps=steps,
        time_bin=4,
        mode="similar",
        roles=TUNING_ROLES,
        same_station=True,
    )
    if revisit.start_step < home.start_step:
        home, revisit = revisit, home
    intruder_pool = find_windows(
        where=(
            f"station <> '{home.station}' AND occupancy BETWEEN 0.04 AND 0.35 "
            f"AND n_steps = {steps} AND time_bin = 4"
        ),
        order_by="occupancy DESC",
        limit=120,
        roles=TUNING_ROLES,
    )
    if not intruder_pool:
        raise LookupError("no contrasting station available for phase B")
    intruder = min(intruder_pool, key=lambda ref: profile_similarity(home, ref))

    recurrence = profile_similarity(home, revisit)
    contrast = profile_similarity(home, intruder)
    gap_min = (revisit.start_step - home.start_step) * 0.25 / 60
    return ScenarioSpec(
        scenario_id="recurring-environment",
        name="Recurring Environment",
        description=(
            f"A -> B -> A'. Phase A is {home.station}; phase B switches to {intruder.station}, "
            f"whose activity profile correlates with A at only {contrast:+.2f}; phase A' returns "
            f"to {home.station} {gap_min:.0f} minutes later, a window whose profile still "
            f"correlates with A at {recurrence:+.2f} — the same environment, genuinely drifted "
            "rather than replayed. A memory-free policy has to rediscover A from scratch."
        ),
        family="recurring-context",
        segments=(
            replace(_segment(home, phase="A"), label=f"A · {home.station}"),
            replace(_segment(intruder, phase="B"), label=f"B · {intruder.station}"),
            replace(_segment(revisit, phase="A-prime"), label=f"A' · {home.station}"),
        ),
        n_regions=home.n_regions,
        time_bin=4,
        tags=("memory", "recurrence", "recovery", home.station, intruder.station),
    )


def _extreme_budget() -> ScenarioSpec:
    ref = _require(
        find_windows(
            where="occupancy BETWEEN 0.06 AND 0.35 AND time_bin = 4 AND n_steps = 1200",
            order_by="intermittent_regions DESC, occupancy DESC",
            roles=TUNING_ROLES,
        ),
        "a window with many intermittent regions",
    )
    horizon = ref.n_steps
    return ScenarioSpec(
        scenario_id="extreme-budget",
        name="Extreme Budget Constraint",
        description=(
            f"{ref.station} with {ref.stats['intermittent_regions']} intermittently active "
            "regions, but only enough sensing budget for 35% of the steps. Every observation "
            "has to be justified, which is where information value stops being a nicety."
        ),
        family="budget-constrained",
        segments=(_segment(ref, phase="constrained"),),
        n_regions=ref.n_regions,
        time_bin=ref.time_bin,
        budget=round(0.35 * horizon, 2),
        tags=("budget", "efficiency", ref.station),
    )


def _unseen_generalization() -> ScenarioSpec:
    steps = DEFAULT_SEGMENT_STEPS // 2
    first, second = find_pair(
        where="occupancy BETWEEN 0.03 AND 0.35",
        n_steps=steps,
        time_bin=4,
        mode="dissimilar",
        roles=("unseen",),
    )
    similarity = profile_similarity(first, second)
    return ScenarioSpec(
        scenario_id="unseen-generalization",
        name="Unseen Generalization Test",
        description=(
            f"Held-out receivers only: {first.station} then {second.station}, both flagged "
            "'unseen' in the station catalogue and never used to tune anything — different "
            f"bands, different hardware, different continents, profiles correlating at "
            f"{similarity:+.2f}. The honest test of whether a scheduler learned scheduling or "
            "learned one recording."
        ),
        family="unseen-combination",
        segments=(
            replace(_segment(first, phase="unseen-A"), label=f"unseen A · {first.station}"),
            replace(_segment(second, phase="unseen-B"), label=f"unseen B · {second.station}"),
        ),
        n_regions=first.n_regions,
        time_bin=4,
        split="unseen",
        tags=("generalisation", "held-out", first.station, second.station),
    )


_BUILDERS = {
    "easy-static": _easy_static,
    "periodic-challenge": _periodic_challenge,
    "high-noise": _high_noise,
    "sudden-shift": _sudden_shift,
    "recurring-environment": _recurring_environment,
    "extreme-budget": _extreme_budget,
    "unseen-generalization": _unseen_generalization,
}


@cache
def preset(scenario_id: str) -> ScenarioSpec:
    """Build one preset from the measured window index (cached per process)."""
    try:
        builder = _BUILDERS[scenario_id]
    except KeyError as exc:
        raise KeyError(
            f"unknown preset {scenario_id!r}; available: {', '.join(PRESET_ORDER)}"
        ) from exc
    return builder()


def list_presets() -> list[ScenarioSpec]:
    """Every preset that the current cache can actually satisfy."""
    built: list[ScenarioSpec] = []
    for scenario_id in PRESET_ORDER:
        try:
            built.append(preset(scenario_id))
        except (LookupError, FileNotFoundError) as exc:
            log.warning(
                "scenario.preset_unavailable",
                extra={"preset": scenario_id, "reason": str(exc)},
            )
    return built


# --------------------------------------------------------------------------- #
# randomised families
# --------------------------------------------------------------------------- #

#: SQL predicate that defines each family in terms of *measured* behaviour.
FAMILY_PREDICATES: dict[ScenarioFamily, str] = {
    "persistent": "persistence > 0.82 AND persistent_regions >= 3 AND occupancy < 0.4",
    "periodic": "period_steps > 0 AND period_strength > 0.40",
    "intermittent": "intermittent_regions >= n_regions / 3 AND occupancy < 0.4",
    "bursting": "burstiness > 2.0 AND occupancy BETWEEN 0.04 AND 0.4",
    "rapidly-changing": "persistence < 0.60 AND occupancy BETWEEN 0.02 AND 0.4",
    "noisy": "p95_margin_db < 9.0 AND occupancy BETWEEN 0.03 AND 0.4",
    "distribution-shift": "occupancy BETWEEN 0.02 AND 0.4",
    "recurring-context": "occupancy BETWEEN 0.04 AND 0.4",
    "unseen-combination": "occupancy BETWEEN 0.02 AND 0.4",
    "budget-constrained": "occupancy BETWEEN 0.04 AND 0.4",
}

MULTI_SEGMENT_FAMILIES: frozenset[str] = frozenset(
    {"distribution-shift", "recurring-context", "unseen-combination"}
)


@lru_cache(maxsize=64)
def _family_pool(
    family: ScenarioFamily, roles: tuple[SplitRole, ...] | None, time_bin: int | None
) -> tuple[WindowRef, ...]:
    predicate = FAMILY_PREDICATES[family]
    if time_bin is not None:
        predicate = f"({predicate}) AND time_bin = {time_bin}"
    return tuple(find_windows(where=predicate, order_by="occupancy DESC", limit=4096, roles=roles))


def sample_scenario(
    family: ScenarioFamily,
    *,
    seed: int,
    roles: tuple[SplitRole, ...] | None = None,
    n_regions: int = DEFAULT_REGIONS,
    segment_steps: int = DEFAULT_SEGMENT_STEPS,
    receiver: ReceiverSpec | None = None,
    reward: RewardWeights | None = None,
    time_bin: int | None = None,
) -> ScenarioSpec:
    """Draw one randomised environment from a family of *real* windows.

    Each seed selects a different measured window (and, for multi-segment
    families, a different pairing of receivers), so a multi-seed evaluation
    averages over environments instead of re-running one episode.
    """
    if family == "unseen-combination":
        roles = ("unseen",)
    pool = _family_pool(family, roles, time_bin)
    if not pool:
        raise LookupError(
            f"no cached window satisfies the '{family}' family"
            f"{f' for roles {roles}' if roles else ''}"
        )
    rng = np.random.default_rng(seed)
    chosen = pool[int(rng.integers(len(pool)))]
    bin_size = chosen.time_bin
    steps = min(segment_steps, chosen.n_steps)

    segments: list[SegmentSpec] = []
    if family in MULTI_SEGMENT_FAMILIES:
        others = [ref for ref in pool if ref.station != chosen.station and ref.time_bin == bin_size]
        if not others:
            raise LookupError(
                f"family '{family}' needs two different stations at time_bin {bin_size}"
            )
        partner = others[int(rng.integers(len(others)))]
        if family == "recurring-context":
            returns = [
                ref
                for ref in _family_pool(family, roles, bin_size)
                if ref.station == chosen.station and ref.start_step != chosen.start_step
            ]
            revisit = returns[int(rng.integers(len(returns)))] if returns else chosen
            phase_steps = max(1, steps // 3)
            segments = [
                replace(_segment(chosen, phase="A"), n_steps=phase_steps),
                replace(_segment(partner, phase="B"), n_steps=phase_steps),
                replace(_segment(revisit, phase="A-prime"), n_steps=phase_steps),
            ]
        else:
            phase_steps = max(1, steps // 2)
            segments = [
                replace(_segment(chosen, phase="A"), n_steps=phase_steps),
                replace(_segment(partner, phase="B"), n_steps=phase_steps),
            ]
    else:
        segments = [replace(_segment(chosen, phase=family), n_steps=steps)]

    horizon = sum(segment.n_steps for segment in segments)
    return ScenarioSpec(
        scenario_id=f"{family}-s{seed}",
        name=f"{family.replace('-', ' ').title()} (seed {seed})",
        description=(
            f"Randomised draw from the '{family}' family: "
            + " then ".join(f"{s.recording_id} @ +{s.start_step}" for s in segments)
        ),
        family=family,
        segments=tuple(segments),
        n_regions=n_regions,
        time_bin=bin_size,
        receiver=receiver or ReceiverSpec(),
        reward=reward or RewardWeights(),
        budget=round(0.35 * horizon, 2) if family == "budget-constrained" else None,
        split="unseen" if roles == ("unseen",) else "train",
        tags=(family, *sorted({segment.recording_id.split("/")[0] for segment in segments})),
    )
