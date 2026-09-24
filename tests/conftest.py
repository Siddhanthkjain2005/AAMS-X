"""Shared fixtures.

Every fixture is backed by the real offline cache. There is no synthetic
environment anywhere in AAMS-X, so if the cache is empty the data-dependent
tests skip loudly rather than quietly testing a fake.
"""

from __future__ import annotations

import numpy as np
import pytest

from aamsx.config import get_settings
from aamsx.contracts.scenario import ReceiverSpec, ScenarioSpec, SegmentSpec
from aamsx.datasets.store import list_recordings
from aamsx.datasets.windows import index_path

SHORT_HORIZON = 160


def _recordings():
    return list_recordings(settings=get_settings())


requires_cache = pytest.mark.skipif(
    not _recordings(),
    reason="offline cache is empty; run scripts/fetch_real_data.py (no synthetic fallback exists)",
)

requires_index = pytest.mark.skipif(
    not index_path().exists(),
    reason="window index missing; run scripts/build_index.py",
)


@pytest.fixture(scope="session")
def recordings():
    found = _recordings()
    if not found:
        pytest.skip("offline cache is empty")
    return found


@pytest.fixture(scope="session")
def recording_id(recordings) -> str:
    """A single cached recording long enough for a short episode."""
    for record in recordings:
        if record.n_times >= SHORT_HORIZON * 4 + 8:
            return record.recording_id
    return recordings[0].recording_id


@pytest.fixture()
def short_spec(recording_id) -> ScenarioSpec:
    """A fast single-segment scenario over real data, for loop-level tests."""
    return ScenarioSpec(
        scenario_id="test-short",
        name="Test Short",
        description="Short real-data scenario used by the test suite.",
        family="intermittent",
        segments=(SegmentSpec(recording_id=recording_id, start_step=0, n_steps=SHORT_HORIZON),),
        n_regions=16,
        time_bin=4,
        receiver=ReceiverSpec(window_size=4),
    )


@pytest.fixture()
def two_phase_spec(recordings) -> ScenarioSpec:
    """Two different real stations spliced together — a genuine distribution shift."""
    if len(recordings) < 2:
        pytest.skip("need two cached recordings for a splice")
    first, second = recordings[0], recordings[1]
    half = SHORT_HORIZON // 2
    return ScenarioSpec(
        scenario_id="test-shift",
        name="Test Shift",
        description="Two real stations spliced at a known step.",
        family="distribution-shift",
        segments=(
            SegmentSpec(recording_id=first.recording_id, start_step=0, n_steps=half, phase="A"),
            SegmentSpec(recording_id=second.recording_id, start_step=0, n_steps=half, phase="B"),
        ),
        n_regions=16,
        time_bin=4,
        receiver=ReceiverSpec(window_size=4),
    )


@pytest.fixture()
def rng() -> np.random.Generator:
    return np.random.default_rng(20260827)
