"""HTTP + WebSocket integration tests over the real FastAPI application.

The whole app is exercised against the real offline cache, with one deliberate
piece of isolation: ``data_dir`` is redirected to a temporary directory whose
``cached/`` and ``index/`` entries are symlinks to the real ones.  Recordings and
the window index are therefore genuinely real, while the experiment registry,
traces and rendered reports written by these tests land in ``tmp_path`` instead
of the developer's working data directory.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from aamsx.api.app import create_app
from aamsx.config import get_settings
from aamsx.experiments import engine as engine_module
from tests.conftest import requires_cache, requires_index

pytestmark = [requires_cache, requires_index]

TIMEOUT_SEC = 90.0


@pytest.fixture(scope="module")
def client(tmp_path_factory, request):
    real = get_settings()
    root = tmp_path_factory.mktemp("aamsx-api-data")
    (root / "cached").symlink_to(real.cache_dir, target_is_directory=True)
    (root / "index").symlink_to(real.index_dir, target_is_directory=True)

    patch = pytest.MonkeyPatch()
    patch.setenv("AAMSX_DATA_DIR", str(root))
    patch.setenv("AAMSX_REPORTS_DIR", str(root / "reports"))
    get_settings.cache_clear()
    engine_module._ENGINE = None
    try:
        with TestClient(create_app()) as test_client:
            yield test_client
    finally:
        engine_module._ENGINE = None
        patch.undo()
        get_settings.cache_clear()


@pytest.fixture(scope="module")
def a_recording(client) -> dict:
    payload = client.get("/api/datasets").json()
    if not payload["recordings"]:
        pytest.skip("no cached recordings")
    return payload["recordings"][0]


def _custom_scenario(recording_id: str, *, n_steps: int = 60, **overrides) -> dict:
    scenario = {
        "scenario_id": "api-test",
        "name": "API Test",
        "description": "Short real segment used by the API tests.",
        "family": "intermittent",
        "segments": [{"recording_id": recording_id, "start_step": 0, "n_steps": n_steps}],
        "n_regions": 16,
        "time_bin": 4,
        "receiver": {"window_size": 4},
    }
    scenario.update(overrides)
    return scenario


def _await_finish(client: TestClient, experiment_id: str, *, timeout: float = TIMEOUT_SEC) -> dict:
    """Poll until the background task settles, as a real UI client would."""
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get(f"/api/experiments/{experiment_id}").json()
        if payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.05)
    pytest.fail(f"{experiment_id} did not finish within {timeout}s: {payload.get('status')}")


@pytest.fixture(scope="module")
def finished_episode(client, a_recording) -> dict:
    response = client.post(
        "/api/experiments",
        json={
            "scenario": _custom_scenario(a_recording["recording_id"]),
            "scheduler": "mag-nts",
            "seed": 1,
            "pace_hz": 0.0,
        },
    )
    assert response.status_code == 202, response.text
    experiment_id = response.json()["experiment_id"]
    payload = _await_finish(client, experiment_id)
    assert payload["status"] == "completed", payload.get("error")
    return {"experiment_id": experiment_id, **payload}


# --------------------------------------------------------------------------- #
# system
# --------------------------------------------------------------------------- #


def test_health_is_cheap_and_names_the_version(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["version"]


def test_status_tells_the_ui_what_data_it_is_looking_at(client):
    body = client.get("/api/status").json()
    assert "REAL PUBLIC SPECTRUM REPLAY" in body["data_mode"]
    assert body["recordings"] > 0
    assert body["windows_indexed"] > 0
    assert body["presets"] > 0
    assert body["cache_mb"] > 0.0
    assert isinstance(body["warnings"], list)
    assert {"version", "scheduler_version", "experiments"} <= set(body)


def test_status_warns_instead_of_pretending_when_something_is_missing(client):
    body = client.get("/api/status").json()
    if body["presets"] < 7:
        assert any("presets" in warning for warning in body["warnings"])
    else:
        assert not [w for w in body["warnings"] if "cache is empty" in w]


def test_the_scheduler_catalogue_leads_with_the_arena_order(client):
    body = client.get("/api/schedulers").json()
    names = [entry["name"] for entry in body["schedulers"]]
    assert names[: len(body["arena_order"])] == body["arena_order"]
    assert "mag-nts" in names
    assert {"round-robin", "random", "ucb", "thompson", "nts"} <= set(names)
    for entry in body["schedulers"]:
        assert entry["description"].strip(), f"{entry['name']} has no description for the UI"


def test_the_openapi_schema_is_served_for_the_generated_client(client):
    body = client.get("/api/openapi.json").json()
    assert body["info"]["title"] == "AAMS-X"
    assert "/api/experiments" in body["paths"]
    assert "/api/datasets/{station}/{day}/spectrogram" in body["paths"]


# --------------------------------------------------------------------------- #
# datasets
# --------------------------------------------------------------------------- #


def test_the_dataset_listing_declares_real_provenance_for_every_recording(client):
    body = client.get("/api/datasets").json()
    assert "REAL" in body["data_mode"]
    assert body["catalogue"]
    for record in body["recordings"]:
        assert record["kind"] == "measured"
        assert record["provenance"]["is_synthetic"] is False
        assert record["provenance"]["source_url"].startswith("http")
        assert record["n_times"] > 0
    adapters = {entry["name"]: entry["status"] for entry in body["adapters"]}
    assert adapters["e-callisto"] == "active"


def test_one_recording_carries_its_calibration_and_station_metadata(client, a_recording):
    station, day = a_recording["recording_id"].split("/")
    body = client.get(f"/api/datasets/{station}/{day}").json()
    assert body["recording_id"] == a_recording["recording_id"]
    assert body["calibration"]["db_per_digit"] > 0
    assert body["freq_max_mhz"] > body["freq_min_mhz"]
    assert body["kind"] == "measured"


def test_an_uncached_recording_is_a_404_that_lists_what_exists(client):
    response = client.get("/api/datasets/NOWHERE/20260101")
    assert response.status_code == 404
    assert "available" in response.json()["detail"]


def test_the_waterfall_returns_a_real_margin_matrix(client, a_recording):
    station, day = a_recording["recording_id"].split("/")
    body = client.get(
        f"/api/datasets/{station}/{day}/spectrogram",
        params={"n_steps": 400, "n_regions": 32, "time_bin": 4},
    ).json()
    assert body["n_regions"] == 32
    assert body["n_steps"] == len(body["margin_db"]) == 100
    assert all(len(row) == 32 for row in body["margin_db"])
    assert body["label_kind"] == "derived-label", "occupancy is a derived label, not truth"
    assert len(body["per_region_occupancy"]) == 32
    assert 0.0 <= body["occupancy"] <= 1.0
    assert len(body["grid"]["edges_mhz"]) == 33
    assert body["provenance"]["is_synthetic"] is False


def test_the_waterfall_downsamples_rather_than_returning_a_giant_payload(client, a_recording):
    station, day = a_recording["recording_id"].split("/")
    body = client.get(
        f"/api/datasets/{station}/{day}/spectrogram",
        params={"n_steps": 40000, "n_regions": 24, "time_bin": 1},
    ).json()
    assert body["n_steps"] <= 1200
    assert body["time_bin"] > 1, "the server must report the binning it applied"


@pytest.mark.parametrize(
    "params",
    [
        {"n_regions": 4},  # below the minimum
        {"n_regions": 9999},  # above the maximum
        {"n_steps": 2},  # below the minimum
        {"start_step": -5},  # negative offset
        {"time_bin": 0},  # impossible binning
    ],
)
def test_the_waterfall_rejects_impossible_geometry_at_the_edge(client, a_recording, params):
    station, day = a_recording["recording_id"].split("/")
    response = client.get(f"/api/datasets/{station}/{day}/spectrogram", params=params)
    assert response.status_code == 422


def test_a_frequency_range_too_narrow_to_fill_the_grid_is_explained(client, a_recording):
    station, day = a_recording["recording_id"].split("/")
    response = client.get(
        f"/api/datasets/{station}/{day}/spectrogram",
        params={"n_steps": 100, "n_regions": 64, "freq_min_mhz": 100.0, "freq_max_mhz": 100.5},
    )
    assert response.status_code == 422
    assert "regions" in response.json()["detail"]


def test_analytics_describes_the_recording_without_a_scheduler(client, a_recording):
    station, day = a_recording["recording_id"].split("/")
    body = client.get(
        f"/api/datasets/{station}/{day}/analytics", params={"n_steps": 4800, "n_regions": 24}
    ).json()
    assert body["stats"]["occupancy"] >= 0.0
    assert len(body["activity_per_step"]) == body["n_steps"]
    assert 0.0 <= body["periodicity"]["strength"] <= 1.0
    assert "autocorrelation" in body["periodicity"]["method"]
    assert len(body["change_scan"]["steps"]) == len(body["change_scan"]["scores"])
    assert "sliding split" in body["change_scan"]["method"]
    assert body["provenance"]["is_synthetic"] is False


def test_the_window_index_is_searchable(client):
    body = client.get(
        "/api/datasets/index/windows",
        params={"where": "occupancy > 0.01", "order_by": "occupancy DESC", "limit": 5},
    ).json()
    assert 0 < body["count"] <= 5
    assert "profile" not in body["windows"][0], "the 48-vector profile is excluded by design"
    assert body["windows"][0]["occupancy"] > 0.01


@pytest.mark.parametrize(
    "where",
    [
        "1=1; DROP TABLE windows",
        "1=1 -- comment",
        "1=1 /* block */",
        "occupancy > (ATTACH 'x')",
        "occupancy > 0 AND install foo",
    ],
)
def test_the_index_refuses_anything_but_a_simple_predicate(client, where):
    """Untrusted input: the query box must not be a DuckDB console."""
    response = client.get("/api/datasets/index/windows", params={"where": where})
    assert response.status_code == 422
    assert "simple SQL predicates" in response.json()["detail"]


def test_a_malformed_predicate_is_reported_not_swallowed(client):
    response = client.get("/api/datasets/index/windows", params={"where": "no_such_column > 1"})
    assert response.status_code == 422
    assert "invalid query" in response.json()["detail"]


# --------------------------------------------------------------------------- #
# scenarios
# --------------------------------------------------------------------------- #


def test_the_scenario_library_reports_what_it_can_and_cannot_build(client):
    body = client.get("/api/scenarios").json()
    built = {spec["scenario_id"] for spec in body["presets"]}
    assert built
    assert not (built & set(body["unavailable"]))
    assert len(body["families"]) == 10
    assert all(entry["predicate"] for entry in body["families"])
    for spec in body["presets"]:
        assert spec["segments"]
        assert spec["horizon"] == sum(seg["n_steps"] for seg in spec["segments"])


def test_a_preset_detail_carries_the_measured_occupancy_of_its_segments(client):
    presets = client.get("/api/scenarios").json()["presets"]
    scenario_id = presets[0]["scenario_id"]
    body = client.get(f"/api/scenarios/{scenario_id}").json()
    assert body["scenario_id"] == scenario_id
    assert len(body["segments_measured"]) == len(body["segments"])
    assert 0.0 <= body["truth_occupancy"] <= 1.0
    assert 0.0 <= body["availability"] <= 1.0


def test_an_unknown_preset_is_a_404(client):
    response = client.get("/api/scenarios/not-a-preset")
    assert response.status_code == 404


def test_a_family_can_be_sampled_by_seed(client):
    first = client.post("/api/scenarios/sample", params={"family": "intermittent", "seed": 3})
    second = client.post("/api/scenarios/sample", params={"family": "intermittent", "seed": 3})
    if first.status_code == 503:
        pytest.skip(first.json()["detail"])
    assert first.status_code == 200
    assert first.json()["segments"] == second.json()["segments"], "a seed must be reproducible"
    assert first.json()["family"] == "intermittent"


def test_an_unknown_family_lists_the_real_ones(client):
    response = client.post("/api/scenarios/sample", params={"family": "made-up"})
    assert response.status_code == 404
    assert "intermittent" in response.json()["detail"]


def test_a_custom_scenario_is_validated_against_the_cache(client, a_recording):
    body = client.post(
        "/api/scenarios/validate", json=_custom_scenario(a_recording["recording_id"])
    ).json()
    assert body["valid"] is True
    assert body["horizon"] == 60
    assert body["segments_measured"]


def test_a_segment_running_off_the_end_is_refused_with_arithmetic(client, a_recording):
    """The cache says how many samples exist; the error has to show the sum."""
    scenario = _custom_scenario(a_recording["recording_id"], n_steps=4000)
    scenario["segments"][0]["start_step"] = a_recording["n_times"] - 100
    response = client.post("/api/scenarios/validate", json=scenario)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert "samples" in detail and "time_bin" in detail
    assert str(a_recording["n_times"]) in detail


def test_an_absurd_horizon_is_refused_by_the_schema_before_any_disk_is_read(client, a_recording):
    response = client.post(
        "/api/scenarios/validate",
        json=_custom_scenario(a_recording["recording_id"], n_steps=10**6),
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"][-1] == "n_steps"


def test_a_scenario_naming_a_missing_recording_is_a_404(client):
    response = client.post("/api/scenarios/validate", json=_custom_scenario("NOWHERE/20260101"))
    assert response.status_code == 404


def test_a_window_wider_than_the_band_is_refused(client, a_recording):
    response = client.post(
        "/api/scenarios/validate",
        json=_custom_scenario(
            a_recording["recording_id"], n_regions=8, receiver={"window_size": 32}
        ),
    )
    assert response.status_code == 422


def test_more_regions_than_channels_is_refused(client, a_recording):
    response = client.post(
        "/api/scenarios/validate",
        json=_custom_scenario(a_recording["recording_id"], n_regions=256),
    )
    assert response.status_code == 422
    assert "channels" in response.json()["detail"]


def test_an_empty_segment_list_never_reaches_the_cache(client):
    response = client.post("/api/scenarios/validate", json={"segments": []})
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# experiments
# --------------------------------------------------------------------------- #


def test_an_episode_runs_end_to_end_and_stores_its_result(finished_episode):
    result = finished_episode["result"]
    assert result["steps"] > 0
    assert result["metrics"]["cumulative_reward"] != 0.0
    assert result["scheduler"] == "mag-nts"
    assert finished_episode["progress"] == pytest.approx(1.0)
    assert finished_episode["n_frames"] > 0


def test_a_finished_episode_appears_in_the_history(client, finished_episode):
    body = client.get("/api/experiments/history", params={"limit": 20}).json()
    found = [
        record
        for record in body["experiments"]
        if record["experiment_id"] == finished_episode["experiment_id"]
    ]
    assert found and found[0]["status"] == "completed"
    assert found[0]["config_hash"]


def test_history_can_be_filtered_by_kind(client, finished_episode):
    body = client.get("/api/experiments/history", params={"kind": "episode"}).json()
    assert body["count"] >= 1
    assert all(record["kind"] == "episode" for record in body["experiments"])


def test_retained_frames_can_be_scrubbed_without_a_socket(client, finished_episode):
    body = client.get(
        f"/api/experiments/{finished_episode['experiment_id']}/frames",
        params={"start": 0, "limit": 5},
    ).json()
    assert body["total"] > 0
    assert body["count"] == min(5, body["total"])
    frame = body["frames"][0]
    assert {"step", "progress"} <= set(frame)


def test_an_unknown_scheduler_is_a_404_that_lists_the_real_ones(client, a_recording):
    response = client.post(
        "/api/experiments",
        json={"scenario": _custom_scenario(a_recording["recording_id"]), "scheduler": "magic"},
    )
    assert response.status_code == 404
    assert "mag-nts" in response.json()["detail"]


def test_an_unknown_scenario_id_is_a_404(client):
    response = client.post("/api/experiments", json={"scenario_id": "nope"})
    assert response.status_code == 404


def test_neither_a_preset_nor_a_scenario_is_a_422(client):
    response = client.post("/api/experiments", json={"scheduler": "nts"})
    assert response.status_code == 422


def test_an_unknown_experiment_is_a_404(client):
    assert client.get("/api/experiments/nope").status_code == 404
    assert client.get("/api/experiments/nope/frames").status_code == 404


def test_cancelling_a_finished_experiment_is_a_conflict(client, finished_episode):
    response = client.post(f"/api/experiments/{finished_episode['experiment_id']}/cancel")
    assert response.status_code == 409


def test_the_active_list_is_json_and_settles_to_empty(client, finished_episode):
    body = client.get("/api/experiments/active").json()
    assert isinstance(body["active"], list)
    assert finished_episode["experiment_id"] not in [
        entry["experiment_id"] for entry in body["active"] if entry["status"] == "running"
    ]


def test_the_websocket_streams_session_frames_and_a_completion(client, a_recording):
    response = client.post(
        "/api/experiments",
        json={
            "scenario": _custom_scenario(a_recording["recording_id"], n_steps=40),
            "scheduler": "nts",
            "seed": 2,
            "pace_hz": 200.0,
        },
    )
    experiment_id = response.json()["experiment_id"]
    kinds: list[str] = []
    with client.websocket_connect(f"/api/experiments/{experiment_id}/stream") as socket:
        while True:
            message = socket.receive_json()
            kinds.append(message.get("type", "frame"))
            if message.get("type") in {"complete", "error"}:
                assert message["type"] == "complete", message
                assert message["result"]["steps"] > 0
                break
    assert kinds[0] == "session"
    assert any(kind == "frame" for kind in kinds), "the socket must carry per-step frames"
    assert kinds[-1] == "complete"


def test_a_socket_for_an_unknown_session_says_so_instead_of_hanging(client):
    with client.websocket_connect("/api/experiments/nope/stream") as socket:
        message = socket.receive_json()
    assert message["type"] == "error"
    assert "no live session" in message["error"]


def test_a_replay_re_executes_the_stored_configuration(client, finished_episode):
    response = client.post(
        f"/api/experiments/{finished_episode['experiment_id']}/replay", params={"pace_hz": 0.0}
    )
    assert response.status_code == 202
    body = response.json()
    assert body["replay_of"] == finished_episode["experiment_id"]
    replayed = _await_finish(client, body["experiment_id"])
    assert replayed["status"] == "completed"
    assert replayed["result"]["metrics"] == finished_episode["result"]["metrics"], (
        "a replay must reproduce the numbers, not merely re-render them"
    )
    history = {
        record["experiment_id"]: record
        for record in client.get("/api/experiments/history", params={"limit": 50}).json()[
            "experiments"
        ]
    }
    assert history[body["experiment_id"]]["config_hash"] == body["config_hash"], (
        "an identical configuration must hash identically, which is what makes replay checkable"
    )


def test_replaying_an_unknown_experiment_is_a_404(client):
    assert client.post("/api/experiments/nope/replay").status_code == 404


def test_an_arena_batch_races_every_policy_on_identical_seeds(client, a_recording):
    response = client.post(
        "/api/experiments/arena",
        json={
            "scenario": _custom_scenario(a_recording["recording_id"], n_steps=40),
            "schedulers": ["round-robin", "nts", "mag-nts"],
            "seeds": 2,
            "workers": 2,
        },
    )
    assert response.status_code == 202
    assert response.json()["n_jobs"] == 6
    payload = _await_finish(client, response.json()["experiment_id"])
    assert payload["status"] == "completed", payload.get("error")
    result = payload["result"]
    assert set(result["variants"]) == {"round-robin", "nts", "mag-nts"}
    assert result["aggregates"]


def test_an_arena_with_an_unknown_policy_is_a_404(client, a_recording):
    response = client.post(
        "/api/experiments/arena",
        json={
            "scenario": _custom_scenario(a_recording["recording_id"]),
            "schedulers": ["nts", "nope"],
        },
    )
    assert response.status_code == 404
    assert "nope" in response.json()["detail"]


def test_the_ablation_ladder_removes_one_component_at_a_time(client, a_recording):
    response = client.post(
        "/api/experiments/ablation",
        json={
            "scenario": _custom_scenario(a_recording["recording_id"], n_steps=40),
            "seeds": 1,
            "workers": 2,
        },
    )
    assert response.status_code == 202
    payload = _await_finish(client, response.json()["experiment_id"])
    assert payload["status"] == "completed", payload.get("error")
    labels = set(payload["result"]["aggregates"])
    assert len(labels) >= 3, labels


def test_too_many_seeds_is_refused_at_the_edge(client, a_recording):
    response = client.post(
        "/api/experiments/arena",
        json={"scenario": _custom_scenario(a_recording["recording_id"]), "seeds": 999},
    )
    assert response.status_code == 422


# --------------------------------------------------------------------------- #
# reports
# --------------------------------------------------------------------------- #


def test_a_report_is_rendered_from_stored_traces(client, finished_episode):
    response = client.post(
        "/api/reports",
        json={
            "experiment_ids": [finished_episode["experiment_id"]],
            "title": "API Test Report",
            "notes": "Generated by the integration tests.",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"].startswith("aamsx-report-")
    assert body["size_bytes"] > 1000

    html = client.get(body["url"]).text
    assert "API Test Report" in html
    assert finished_episode["experiment_id"] in html
    reward = finished_episode["result"]["metrics"]["cumulative_reward"]
    # The headline table renders cumulative reward to one decimal place.
    assert f"{reward:.1f}" in html, "the report must quote executed numbers, not placeholders"
    assert "derived from measurement" in html or "not absolute ground truth" in html


def test_a_missing_experiment_is_reported_as_missing_rather_than_invented(client):
    response = client.post("/api/reports", json={"experiment_ids": ["no-such-run"]})
    assert response.status_code == 201
    html = client.get(response.json()["url"]).text
    assert "no stored result" in html


def test_the_report_listing_shows_what_was_generated(client, finished_episode):
    client.post("/api/reports", json={"experiment_ids": [finished_episode["experiment_id"]]})
    body = client.get("/api/reports").json()
    assert body["reports"]
    assert all(entry["name"].startswith("aamsx-report-") for entry in body["reports"])
    assert body["reports"][0]["size_bytes"] > 0


@pytest.mark.parametrize(
    "name",
    ["../../etc/passwd", "aamsx-report-../x.html", "secret.html", "aamsx-report-x.txt"],
)
def test_a_report_name_that_is_not_ours_cannot_walk_the_filesystem(client, name):
    response = client.get(f"/api/reports/{name}")
    assert response.status_code in {400, 404}
    if response.status_code == 400:
        assert "report name" in response.json()["detail"]


def test_asking_for_no_experiments_is_refused(client):
    assert client.post("/api/reports", json={"experiment_ids": []}).status_code == 422
