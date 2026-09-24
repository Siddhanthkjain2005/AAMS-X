import json

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        yield client


def test_api_health_catalog_and_validation(client):
    assert client.get("/api/status").json()["policy_input"] == "observations_only"
    assert len(client.get("/api/scenarios").json()) == 10
    assert {d["category"] for d in client.get("/api/datasets").json()} == {"CONTROLLED_SIMULATION", "REAL_MEASURED_RF", "OFFICIAL_SYNTHETIC_RADAR"}
    assert client.post("/api/experiment/start", json={"horizon": -1}).status_code == 422
    assert client.post("/api/experiment/start", json={"dataset_id": "not-installed"}).status_code == 404


def test_api_pause_step_export_reset_and_judge_visibility(client):
    response = client.post("/api/experiment/start?autoplay=false", json={"horizon": 24})
    assert response.status_code == 200
    run = response.json()
    run_id = run["id"]
    for _ in range(3):
        frame = client.post(f"/api/experiment/{run_id}/step").json()
    assert frame["step"] == 2 and "evaluation" not in frame
    trace = client.get(f"/api/experiment/{run_id}/trace").json()
    assert len(trace["frames"]) == 3
    assert "evaluation" not in trace["frames"][0]["policies"]["magnts"]
    assert client.get(f"/api/experiment/{run_id}/trace?judge=true").json()["frames"][0]["evaluation"]
    assert client.get(f"/api/experiment/{run_id}/evaluation").status_code == 403
    assert client.get(f"/api/experiment/{run_id}/evaluation?judge=true").status_code == 200
    assert len(client.get(f"/api/experiment/{run_id}/decisions").json()) == 3
    assert client.get(f"/api/experiment/{run_id}/metrics").status_code == 200
    exported = client.get(f"/api/experiment/{run_id}/export")
    assert len(json.loads(exported.content)["frames"]) == 3
    assert "seed" in client.get(f"/api/experiment/{run_id}/export?format=csv").text.splitlines()[0]
    reset = client.post("/api/experiment/reset", json={"experiment_id": run_id}).json()
    assert reset["environment_hash"] == run["environment_hash"] and reset["step"] == 0
    assert reset["id"] != run_id


def test_websocket_default_does_not_stream_hidden_truth(client):
    run = client.post("/api/experiment/start?autoplay=false", json={"horizon": 24}).json()
    client.post(f"/api/experiment/{run['id']}/step")
    with client.websocket_connect(f"/ws/experiment/{run['id']}") as websocket:
        message = websocket.receive_json()
        assert message["mode"] == "LIVE"
        assert message["frames"][0]["step"] == 0
        assert "evaluation" not in message["frames"][0]
    with client.websocket_connect(f"/ws/experiment/{run['id']}?judge=true") as websocket:
        assert "evaluation" in websocket.receive_json()["frames"][0]


def test_paused_single_step_and_resume_controls(client):
    run = client.post("/api/experiment/start?autoplay=false", json={"horizon": 24}).json()
    assert client.post("/api/experiment/speed", json={"experiment_id": run["id"], "speed": 4}).json()["speed"] == 4
    assert client.post("/api/experiment/resume", json={"experiment_id": run["id"]}).json()["state"] == "running"
    assert client.post("/api/experiment/pause", json={"experiment_id": run["id"]}).json()["state"] == "paused"
    assert client.post("/api/experiment/stop", json={"experiment_id": run["id"]}).json()["state"] == "cancelled"


def test_reset_completed_run_preserves_recorded_completion(client):
    run = client.post("/api/experiment/start?autoplay=false", json={"horizon": 24}).json()
    for _ in range(24):
        assert client.post(f"/api/experiment/{run['id']}/step").status_code == 200
    reset = client.post("/api/experiment/reset", json={"experiment_id": run["id"]}).json()
    assert reset["step"] == 0 and reset["state"] == "paused"
    assert reset["environment_hash"] == run["environment_hash"]
    assert client.get(f"/api/experiment/{run['id']}").json()["state"] == "completed"
