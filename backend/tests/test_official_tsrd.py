"""Integration checks against the installed publisher recording."""
from pathlib import Path
import hashlib
import pytest
from backend.contracts import ExperimentConfig, ReceiverConfig
from backend.datasets.catalog import load_artifact
from backend.datasets.environment import build_world
from backend.experiments.benchmark import BenchmarkConfig
from backend.experiments.engine import Experiment
from backend.api import create_app
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
DATASET = "tsrd-stare-d25a4189f287"

def test_imported_benchmark_does_not_duplicate_simulator_scenarios():
    config = BenchmarkConfig(dataset_id=DATASET, scenarios=["sudden", "periodic"], runs=6)
    assert config.scenarios == ["recording"]

def test_official_recording_provenance_and_reproducibility():
    raw = ROOT / "data/raw/tsrd_val_stare_config_0.h5"
    if not raw.exists():
        pytest.skip("Install the authorized publisher recording first")
    arrays, manifest = load_artifact(DATASET)
    assert hashlib.sha256(raw.read_bytes()).hexdigest() == manifest["source_sha256"]
    assert manifest["pulse_count"] == 648034
    assert manifest["truncated"] is False
    assert manifest["category"] == "OFFICIAL_SYNTHETIC_RADAR"
    assert arrays
    config = ExperimentConfig(dataset_id=DATASET, scenario="recording", seed=42,
        horizon=24, receiver=ReceiverConfig(bands=64), algorithms=["magnts", "fixed", "thompson"])
    effective, world = build_world(config)
    first = Experiment(effective, world).run().record()
    effective2, world2 = build_world(config)
    second = Experiment(effective2, world2).run().record()
    assert first["trace_hash"] == second["trace_hash"]
    assert first["environment_hash"] == second["environment_hash"]

def test_official_benchmark_http_accepts_recording(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.post('/api/benchmark/start', json={
            "dataset_id": DATASET, "scenarios": ["sudden", "periodic"],
            "runs": 1, "horizon": 24, "algorithms": ["fixed", "magnts"]})
        assert response.status_code == 200, response.text
        assert response.json()["config"]["scenarios"] == ["recording"]

def test_remote_catalog_is_compressed_and_still_valid_json(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        response = client.get('/api/datasets', headers={'Accept-Encoding': 'gzip'})
        assert response.status_code == 200
        assert response.headers.get('content-encoding') == 'gzip'
        assert isinstance(response.json(), list)
