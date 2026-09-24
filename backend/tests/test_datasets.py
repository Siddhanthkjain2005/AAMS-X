import h5py
import numpy as np
import pandas as pd
import pytest
from astropy.io import fits

from backend.contracts import ExperimentConfig, ReceiverConfig
from backend.datasets.catalog import load_artifact, preview
from backend.datasets.environment import build_world, regrid
from backend.datasets.ingest import ingest_callisto, ingest_turing


def test_callisto_fits_axes_missing_data_and_lineage(tmp_path):
    image = np.arange(80, dtype=float).reshape(4, 20)
    image[3, 3] = np.nan
    primary = fits.PrimaryHDU(image)
    primary.header["DATE-OBS"] = "2024/05/10"
    primary.header["TIME-OBS"] = "12:00:00"
    primary.header["INSTRUME"] = "EXPLICIT-SYNTHETIC-TEST"
    table = fits.BinTableHDU.from_columns([
        fits.Column(name="FREQUENCY", format="4D", array=[[150, 100, 100, 125]]),
        fits.Column(name="TIME", format="20D", array=[np.arange(20) * 0.25]),
    ])
    path = tmp_path / "test.fit"
    fits.HDUList([primary, table]).writeto(path)
    manifest = ingest_callisto(path, directory=tmp_path, category="CONTROLLED_SIMULATION")
    arrays, metadata = load_artifact(manifest["id"], tmp_path)
    assert metadata["category"] == "CONTROLLED_SIMULATION"
    assert metadata["ground_truth"] is False
    assert arrays["intensity"].shape == (20, 3)
    assert arrays["frequency_mhz"].tolist() == [100, 125, 150]
    assert arrays["intensity"][0, 0] == 30  # duplicate frequency channels averaged
    assert np.isnan(arrays["intensity"][3, 1])
    assert arrays["time_ms"][1] == 250
    assert metadata["time_start_utc"].startswith("2024-05-10T12:00:00")
    assert "source_sha256" in metadata and "artifact_sha256" in metadata
    assert preview(manifest["id"], tmp_path)["intensity"][3][1] is None
    parquet = pd.read_parquet(tmp_path / f"{manifest['id']}.parquet")
    assert {"timestamp_ms", "timestamp_utc", "frequency_mhz", "intensity", "station", "source_file"} <= set(parquet.columns)
    assert parquet["intensity"].dtype == np.dtype("float32")


def test_fits_without_physical_frequency_axis_rejected(tmp_path):
    path = tmp_path / "invalid.fit"
    fits.PrimaryHDU(np.ones((4, 20))).writeto(path)
    with pytest.raises(ValueError, match="FREQUENCY"):
        ingest_callisto(path, directory=tmp_path)


@pytest.mark.parametrize("mode,has_truth", [("stare", True), ("scan", False)])
def test_turing_publisher_hdf5_schema_chunking_and_truth_scope(tmp_path, mode, has_truth):
    path = tmp_path / "explicit_synthetic_fixture.h5"
    with h5py.File(path, "w") as file:
        file.create_dataset("data", data=np.column_stack([np.arange(200) * 10000, np.tile([4000, 11000], 100), np.ones(200) * 2, np.ones(200) * 30, np.ones(200) * -70]))
        file.create_dataset("labels", data=np.tile([1, 2], 100))
        metadata = file.create_group("metadata")
        metadata.create_dataset("feature_names", data=np.array(["ToA", "CF", "PW", "AoA", "Amplitude"], dtype="S"))
    manifest = ingest_turing(path, mode, directory=tmp_path, max_pulses=160, slots=64, bands=32, category="CONTROLLED_SIMULATION")
    arrays, _ = load_artifact(manifest["id"], tmp_path)
    assert manifest["pulse_count"] == 160 and manifest["original_pulse_count"] == 200
    assert manifest["truncated"] is True
    assert manifest["ground_truth"] is has_truth
    assert ("truth" in arrays) is has_truth
    assert manifest["emitter_labels_available"]
    if has_truth:
        assert arrays["truth"].any()
    columns = pd.read_parquet(tmp_path / f"{manifest['id']}.parquet").columns
    assert {"toa_us", "frequency_mhz", "pulse_width_us", "aoa_deg", "amplitude_db", "emitter_id"} <= set(columns)


def test_regridding_preserves_empty_irregular_channels():
    values = np.ones((20, 3))
    result, _, _ = regrid(values, np.arange(20) * 100, np.array([50, 60, 200]), 10, 32)
    assert np.isnan(result).any()
    assert np.nanmin(result) == np.nanmax(result) == 1


def test_measured_calibration_excludes_future_data(monkeypatch):
    rng = np.random.default_rng(71)
    arrays = {"intensity": rng.normal(50, 1, (120, 8)), "time_ms": np.arange(120) * 1000, "frequency_mhz": np.arange(8) * 10.0 + 50}
    meta = {"id": "test", "category": "REAL_MEASURED_RF", "energy_unit": "digits", "note": "explicit synthetic test fixture"}
    monkeypatch.setattr("backend.datasets.environment.load_artifact", lambda _: (arrays, meta))
    config = ExperimentConfig(dataset_id="test", horizon=24, receiver=ReceiverConfig(bands=8, window_width=2))
    _, a = build_world(config)
    arrays["intensity"][90:] += 1000
    _, b = build_world(config)
    np.testing.assert_array_equal(a.energy[:10], b.energy[:10])
    assert a.truth is None
    assert a.metadata["calibration_excluded_from_evaluation"]
