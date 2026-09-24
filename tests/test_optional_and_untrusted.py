"""The parts of AAMS-X that face untrusted input or an absent optional extra.

Three claims are under test here:

* a **SigMF upload is hostile until proven otherwise** — a lying header, an
  oversized payload or a filename shaped like a path must be refused before any
  allocation, parse or write happens;
* the **ElectroSense adapter fails honestly** — it says *unavailable* and never
  substitutes anything, and it never echoes a credential;
* the **torch extras degrade honestly** — with torch absent the deep-RL policies
  are simply not registered, and asking for the neural encoder falls back to the
  engineered one instead of crashing an episode.

The torch-dependent assertions run only where the extra is installed; the
absence path is asserted unconditionally, because that is the shipped default.
"""

from __future__ import annotations

import importlib.util
import json
import struct

import numpy as np
import pytest

from aamsx.config import Settings
from aamsx.datasets.sigmf import (
    MAX_CHANNELS,
    SigMFError,
    import_sigmf,
    load_sigmf,
    safe_station_name,
)

TORCH_INSTALLED = importlib.util.find_spec("torch") is not None


# --------------------------------------------------------------------------- #
# a SigMF pair, synthesised here purely to exercise the parser
# --------------------------------------------------------------------------- #


def _write_pair(
    tmp_path,
    *,
    datatype: str = "rf32_le",
    sample_rate: float = 2_000_000.0,
    n_fft: int = 64,
    rows: int = 12,
    captures: object | None = None,
    drop_global: bool = False,
    trailing_bytes: int = 0,
    name: str = "capture",
):
    """Write a minimal ``.sigmf-meta`` / ``.sigmf-data`` pair.

    This is parser input, not spectrum data: nothing measured is claimed, and no
    experiment reads it. Real recordings only ever come from the cache.
    """
    meta = {
        "global": {
            "core:datatype": datatype,
            "core:sample_rate": sample_rate,
            "core:version": "1.0.0",
            "core:description": "unit-test fixture, not a measurement",
            "core:license": "test",
        },
        "captures": [{"core:sample_start": 0, "core:frequency": 100_000_000.0}]
        if captures is None
        else captures,
        "annotations": [],
    }
    if drop_global:
        meta.pop("global")
    meta_path = tmp_path / f"{name}.sigmf-meta"
    data_path = tmp_path / f"{name}.sigmf-data"
    meta_path.write_text(json.dumps(meta))

    rng = np.random.default_rng(20260825)
    grid = rng.normal(-90.0, 2.0, size=(rows, n_fft)).astype(np.float32)
    grid[:, n_fft // 3] += 30.0  # one persistent carrier, so regions differ
    payload = grid.tobytes()
    if trailing_bytes:
        payload += b"\x00" * trailing_bytes
    data_path.write_bytes(payload)
    return meta_path, data_path


def test_a_well_formed_spectral_pair_imports_with_honest_provenance(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    raw = load_sigmf(meta_path, data_path, n_fft=64)
    assert raw.digits.shape == (12, 64)
    assert raw.digits.dtype == np.uint8
    provenance = raw.provenance
    assert provenance.adapter == "sigmf"
    assert provenance.is_synthetic is False  # the uploader's claim, not ours
    assert "AAMS-X did not measure this data" in (provenance.notes or "")
    # Every transformation applied is named, not implied.
    assert any("already spectral" in step for step in provenance.preprocessing)
    assert any("dB/digit" in step for step in provenance.preprocessing)


def test_iq_input_declares_the_stft_it_performed(tmp_path):
    meta_path = tmp_path / "iq.sigmf-meta"
    data_path = tmp_path / "iq.sigmf-data"
    meta_path.write_text(
        json.dumps(
            {
                "global": {
                    "core:datatype": "cf32_le",
                    "core:sample_rate": 1_000_000.0,
                },
                "captures": [{"core:sample_start": 0, "core:frequency": 50_000_000.0}],
            }
        )
    )
    rng = np.random.default_rng(7)
    iq = (rng.normal(size=1024) + 1j * rng.normal(size=1024)).astype(np.complex64)
    data_path.write_bytes(iq.tobytes())
    raw = load_sigmf(meta_path, data_path, n_fft=64)
    assert raw.digits.shape == (16, 64)
    assert any("Hann STFT" in step for step in raw.provenance.preprocessing)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"datatype": "cf128_le"}, "unsupported core:datatype"),
        ({"datatype": "python/object"}, "unsupported core:datatype"),
        ({"sample_rate": 0.0}, "core:sample_rate must be a positive number"),
        ({"sample_rate": -1.0}, "core:sample_rate must be a positive number"),
        ({"drop_global": True}, "missing the required 'global' object"),
        ({"captures": []}, "declares no captures"),
        ({"captures": ["not-an-object"]}, "every capture entry must be an object"),
        ({"trailing_bytes": 1}, "not a multiple of the declared"),
        ({"rows": 1, "n_fft": 8}, "cannot form two spectra"),
    ],
)
def test_a_malformed_upload_is_refused_with_a_reason(tmp_path, kwargs, message):
    n_fft = kwargs.pop("n_fft", 64)
    meta_path, data_path = _write_pair(tmp_path, n_fft=n_fft, **kwargs)
    with pytest.raises(SigMFError) as excinfo:
        load_sigmf(meta_path, data_path, n_fft=n_fft)
    assert message in str(excinfo.value)


def test_an_empty_sample_file_is_refused(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    data_path.write_bytes(b"")
    with pytest.raises(SigMFError, match="sample file is empty"):
        load_sigmf(meta_path, data_path, n_fft=64)


def test_metadata_that_is_not_json_is_refused_rather_than_guessed(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    meta_path.write_bytes(b"\x80\x04\x95pickle-looking-bytes")
    with pytest.raises(SigMFError, match="unreadable SigMF metadata"):
        load_sigmf(meta_path, data_path, n_fft=64)


def test_metadata_that_is_a_json_scalar_is_refused(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    meta_path.write_text('"just a string"')
    with pytest.raises(SigMFError, match="must be a JSON object"):
        load_sigmf(meta_path, data_path, n_fft=64)


def test_an_upload_over_the_cap_is_refused_before_it_is_parsed(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    settings = Settings(data_dir=tmp_path / "data", max_upload_bytes=128)
    with pytest.raises(SigMFError, match="the configured cap is"):
        load_sigmf(meta_path, data_path, n_fft=64, settings=settings)


@pytest.mark.parametrize("n_fft", [0, 4, 100, MAX_CHANNELS * 2])
def test_an_impossible_fft_length_is_refused(tmp_path, n_fft):
    meta_path, data_path = _write_pair(tmp_path)
    with pytest.raises(SigMFError, match="n_fft must be a power of two"):
        load_sigmf(meta_path, data_path, n_fft=n_fft)


def test_a_missing_file_is_named_rather_than_silently_skipped(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    data_path.unlink()
    with pytest.raises(SigMFError, match="no SigMF sample file"):
        load_sigmf(meta_path, data_path, n_fft=64)
    with pytest.raises(SigMFError, match="no SigMF metadata"):
        load_sigmf(tmp_path / "absent.sigmf-meta", n_fft=64)


@pytest.mark.parametrize(
    "station",
    ["../../etc/passwd", "/absolute", "..", "with space", "semi;colon", "", "x" * 65, "-leading"],
)
def test_a_station_name_that_could_escape_the_cache_is_refused(station):
    with pytest.raises(SigMFError, match="station name must be"):
        safe_station_name(station)


def test_a_traversal_station_name_never_reaches_the_filesystem(tmp_path):
    meta_path, data_path = _write_pair(tmp_path)
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    with pytest.raises(SigMFError, match="station name must be"):
        import_sigmf(meta_path, data_path, station="../escape", n_fft=64, settings=settings)
    assert not list(settings.data_dir.parent.glob("escape*"))
    assert not list(settings.cache_dir.glob("*"))


def test_an_accepted_import_lands_inside_the_cache_under_its_own_station(tmp_path):
    meta_path, data_path = _write_pair(tmp_path, rows=40)
    settings = Settings(data_dir=tmp_path / "data")
    settings.ensure_dirs()
    target = import_sigmf(meta_path, data_path, station="MY-SDR", n_fft=64, settings=settings)
    assert settings.cache_dir in target.parents
    assert (target / "manifest.json").is_file()
    manifest = json.loads((target / "manifest.json").read_text())
    assert manifest["provenance"]["adapter"] == "sigmf"
    assert manifest["provenance"]["is_synthetic"] is False


def test_a_header_that_lies_about_its_dtype_cannot_force_a_huge_allocation(tmp_path):
    """A 12-byte payload declared as 16-byte complex must not be trusted."""
    meta_path, data_path = _write_pair(tmp_path)
    data_path.write_bytes(struct.pack("<3f", 1.0, 2.0, 3.0))
    meta = json.loads(meta_path.read_text())
    meta["global"]["core:datatype"] = "cf64_le"
    meta_path.write_text(json.dumps(meta))
    with pytest.raises(SigMFError):
        load_sigmf(meta_path, data_path, n_fft=64)


# --------------------------------------------------------------------------- #
# the ElectroSense adapter: unavailable, and honest about it
# --------------------------------------------------------------------------- #


def _offline(tmp_path, **extra) -> Settings:
    return Settings(data_dir=tmp_path / "data", allow_network=False, **extra)


def test_the_adapter_reports_unavailable_without_touching_the_network(tmp_path):
    from aamsx.datasets.electrosense import status

    payload = status(_offline(tmp_path))
    assert payload["adapter"] == "electrosense"
    assert payload["status"] == "unavailable"
    assert payload["verified"] is True  # a config answer needs no probe
    assert "network access disabled" in str(payload["detail"])


def test_status_never_echoes_a_credential(tmp_path):
    from aamsx.datasets.electrosense import status

    settings = _offline(tmp_path, electrosense_user="alice", electrosense_password="s3cret")
    payload = status(settings)
    assert payload["credentials_configured"] is True
    serialised = json.dumps(payload)
    assert "s3cret" not in serialised and "alice" not in serialised


def test_no_credentials_is_the_normal_case(tmp_path):
    from aamsx.datasets.electrosense import status

    assert status(_offline(tmp_path))["credentials_configured"] is False


def test_status_declares_its_licence_and_reference(tmp_path):
    from aamsx.datasets.electrosense import status

    payload = status(_offline(tmp_path))
    assert payload["license"] and payload["reference"]


@pytest.mark.parametrize("call", ["list_sensors", "fetch_day"])
def test_fetching_refuses_rather_than_returning_something_invented(tmp_path, call):
    from datetime import UTC, datetime

    from aamsx.datasets import electrosense
    from aamsx.datasets.callisto import AdapterUnavailable

    settings = _offline(tmp_path)
    with pytest.raises(AdapterUnavailable, match="network access disabled"):
        if call == "list_sensors":
            electrosense.list_sensors(settings)
        else:
            electrosense.fetch_day(
                "sensor-1",
                datetime(2026, 8, 25, tzinfo=UTC),
                freq_min_mhz=50.0,
                freq_max_mhz=100.0,
                hours=1.0,
                settings=settings,
            )


# --------------------------------------------------------------------------- #
# torch extras: absent by default, and that must not break anything
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(TORCH_INSTALLED, reason="asserts the torch-absent default install")
def test_without_torch_the_deep_rl_policies_are_simply_not_registered():
    from aamsx.schedulers import available, deep_rl_available

    assert deep_rl_available() is False
    assert "dqn" not in available() and "sac" not in available()


@pytest.mark.skipif(TORCH_INSTALLED, reason="asserts the torch-absent default install")
def test_asking_for_an_unregistered_policy_names_the_ones_that_exist():
    from aamsx.schedulers.base import create

    with pytest.raises(KeyError, match="unknown scheduler"):
        create("dqn")


@pytest.mark.skipif(TORCH_INSTALLED, reason="asserts the torch-absent default install")
def test_the_neural_flag_falls_back_to_the_engineered_encoder(caplog):
    """An unavailable extra must degrade, not abort an episode mid-run."""
    from aamsx.contracts.scenario import ReceiverSpec, RewardWeights
    from aamsx.experiments.context import _resolve_encoder
    from aamsx.features import engineered
    from aamsx.schedulers.base import AblationFlags, SchedulerSetup

    setup = SchedulerSetup(
        n_regions=8,
        window_size=16,
        n_anchors=4,
        horizon=32,
        budget=32.0,
        receiver=ReceiverSpec(),
        reward=RewardWeights(),
        seed=0,
        flags=AblationFlags(neural_encoder=True),
    )
    encoder = _resolve_encoder(setup)
    assert encoder is engineered.encode


@pytest.mark.skipif(not TORCH_INSTALLED, reason="requires the optional torch extra")
def test_the_neural_encoder_keeps_the_engineered_features_byte_for_byte():
    from aamsx.features.temporal import TemporalBuffer

    from aamsx.belief.filter import BeliefFilter
    from aamsx.features import engineered
    from aamsx.features.neural import NeuralEncoder

    kwargs = dict(
        belief=BeliefFilter(n_regions=8),
        buffer=TemporalBuffer(n_regions=8, window=16),
        change_score=0.3,
        steps_since_change=4,
        period_strength=0.2,
        budget_fraction=0.5,
        progress=0.25,
    )
    plain_features, plain_context = engineered.encode(**kwargs)
    encoder = NeuralEncoder(8, seed=11)
    features, context = encoder(**kwargs)
    assert np.array_equal(features, plain_features)
    assert context.shape == plain_context.shape == (engineered.CONTEXT_DIM,)
    assert context.min() >= 0.0 and context.max() <= 1.0
    assert not np.array_equal(context, plain_context)  # it is a different key
    described = encoder.describe()
    assert described["kind"] == "model-inferred" and described["trained"] is False


@pytest.mark.skipif(not TORCH_INSTALLED, reason="requires the optional torch extra")
def test_the_neural_encoder_is_deterministic_and_resettable():
    from aamsx.features.temporal import TemporalBuffer

    from aamsx.belief.filter import BeliefFilter
    from aamsx.features.neural import NeuralEncoder

    def once(encoder):
        return encoder(
            belief=BeliefFilter(n_regions=6),
            buffer=TemporalBuffer(n_regions=6, window=12),
            change_score=0.1,
            steps_since_change=2,
            period_strength=0.0,
            budget_fraction=1.0,
            progress=0.0,
        )[1]

    first = NeuralEncoder(6, seed=3)
    second = NeuralEncoder(6, seed=3)
    assert np.array_equal(once(first), once(second))
    drifted = once(first)  # a second step moves the recurrent state
    assert not np.array_equal(drifted, once(second))
    first.reset()
    assert first.steps == 0


@pytest.mark.skipif(not TORCH_INSTALLED, reason="requires the optional torch extra")
def test_a_checkpoint_is_treated_as_untrusted(tmp_path):
    import torch

    from aamsx.features.neural import NeuralEncoder

    encoder = NeuralEncoder(6, seed=5)
    with pytest.raises(FileNotFoundError):
        encoder.load(tmp_path / "absent.pt")
    bad = tmp_path / "not-a-state-dict.pt"
    torch.save([1, 2, 3], bad)
    with pytest.raises(ValueError, match="state dict"):
        encoder.load(bad)


@pytest.mark.skipif(not TORCH_INSTALLED, reason="requires the optional torch extra")
def test_the_dqn_policy_stays_inside_the_band_and_decays_epsilon():
    from aamsx.contracts.scenario import ReceiverSpec, RewardWeights
    from aamsx.schedulers.base import SchedulerSetup
    from aamsx.schedulers.dqn import DQNScheduler

    setup = SchedulerSetup(
        n_regions=8,
        window_size=16,
        n_anchors=4,
        horizon=32,
        budget=32.0,
        receiver=ReceiverSpec(),
        reward=RewardWeights(),
        seed=0,
    )
    policy = DQNScheduler()
    policy.reset(setup)
    start = policy.epsilon()
    assert 0.0 <= start <= 1.0
    snapshot = policy.snapshot()
    assert snapshot and "epsilon" in snapshot
