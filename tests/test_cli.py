"""The ``aamsx`` command line: does it do what the Makefile and the docs claim?

Two things matter here beyond "it runs".  First, ``report`` must refuse to render
a document when the registry holds nothing — a report that looks like a result
but contains none is worse than an error.  Second, ``run`` must leave a
replayable row behind, because ``replay`` and ``report`` both read it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aamsx.cli import build_parser, main
from aamsx.config import Settings, get_settings
from aamsx.experiments.registry import Registry
from tests.conftest import requires_cache


@pytest.fixture()
def isolated(tmp_path, monkeypatch):
    """Point the whole CLI at a throwaway data dir — registry, traces and reports."""
    monkeypatch.setenv("AAMSX_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("AAMSX_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("AAMSX_ALLOW_NETWORK", "0")
    get_settings.cache_clear()
    settings = get_settings()
    settings.ensure_dirs()
    yield settings
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# the parser
# --------------------------------------------------------------------------- #


def test_every_subcommand_the_makefile_and_docs_reference_exists():
    choices = next(action.choices for action in build_parser()._actions if action.dest == "command")
    assert {
        "run",
        "arena",
        "ablation",
        "replay",
        "report",
        "history",
        "presets",
        "schedulers",
        "info",
        "serve",
    } <= set(choices)


def test_report_defaults_match_the_makefile_target():
    args = build_parser().parse_args(["report", "--latest", "6"])
    assert (args.command, args.latest) == ("report", 6)


def test_a_command_is_required():
    with pytest.raises(SystemExit):
        build_parser().parse_args([])


def test_an_unknown_ablation_component_is_refused_by_name(capsys):
    assert main(["run", "easy-static", "--off", "telepathy"]) == 2
    assert "unknown component 'telepathy'" in capsys.readouterr().err


def test_an_unknown_preset_lists_the_real_ones(capsys):
    assert main(["run", "not-a-preset"]) == 2
    err = capsys.readouterr().err
    assert "unknown preset 'not-a-preset'" in err
    assert "easy-static" in err


# --------------------------------------------------------------------------- #
# read-only inspection
# --------------------------------------------------------------------------- #


def test_schedulers_lists_the_registered_policies_as_json(capsys):
    assert main(["schedulers", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    names = {entry["name"] for entry in payload["schedulers"]}
    assert {"round-robin", "random", "ucb", "thompson", "nts", "mag-nts"} <= names
    assert payload["deep_rl_available"] in (True, False)


def test_presets_only_lists_scenarios_the_real_cache_can_build(capsys):
    from aamsx.environment.scenarios import PRESET_ORDER

    assert main(["presets", "--json"]) == 0
    specs = json.loads(capsys.readouterr().out)
    ids = [spec["scenario_id"] for spec in specs]
    assert set(ids) <= set(PRESET_ORDER)
    assert ids == [name for name in PRESET_ORDER if name in set(ids)]
    for spec in specs:
        # A preset that claims no recording is a preset built from nothing.
        assert spec["segments"] and all(segment["recording_id"] for segment in spec["segments"])


def test_info_reports_the_cache_it_can_actually_see(capsys):
    assert main(["info", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cached_recordings"] >= 0
    if payload["cached_recordings"]:
        assert payload["stations"] and payload["cached_mb"] > 0
    assert payload["electrosense"]["status"] == "unavailable"


def test_info_never_prints_a_credential(capsys, monkeypatch):
    monkeypatch.setenv("AAMSX_ELECTROSENSE_USER", "alice")
    monkeypatch.setenv("AAMSX_ELECTROSENSE_PASSWORD", "s3cret")
    monkeypatch.setenv("AAMSX_ALLOW_NETWORK", "0")
    get_settings.cache_clear()
    try:
        assert main(["info", "--json"]) == 0
        out = capsys.readouterr().out
        assert "s3cret" not in out and "alice" not in out
        assert json.loads(out)["electrosense"]["credentials_configured"] is True
    finally:
        get_settings.cache_clear()


def test_history_on_an_empty_registry_says_so_rather_than_failing(isolated, capsys):
    assert main(["history"]) == 0
    assert "registry is empty" in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# the honesty rule
# --------------------------------------------------------------------------- #


def test_report_refuses_to_render_from_an_empty_registry(isolated, capsys):
    assert main(["report", "--latest", "6"]) == 2
    err = capsys.readouterr().err
    assert "nothing to report" in err
    assert "will not fabricate" in err
    assert not list(isolated.reports_dir.glob("*.html"))


def test_report_refuses_unknown_experiment_ids(isolated, capsys):
    assert main(["report", "--id", "does-not-exist"]) == 2
    assert "not in the registry" in capsys.readouterr().err


def test_replay_of_an_unknown_id_is_refused(isolated, capsys):
    assert main(["replay", "cli-nope"]) == 2
    assert "no experiment 'cli-nope'" in capsys.readouterr().err


def test_replay_declines_a_batch_and_says_which_command_to_use(isolated, capsys):
    Registry(isolated).create(
        experiment_id="arena-x",
        kind="arena",
        scenario_id="easy-static",
        scheduler="nts,mag-nts",
        seed=-1,
        ablation="batch",
        recordings=[],
        config={"kind": "arena", "scenario": {}, "variants": [], "seeds": [0]},
    )
    assert main(["replay", "arena-x"]) == 2
    err = capsys.readouterr().err
    assert "is a arena batch" in err
    assert "aamsx arena" in err


def test_a_running_row_is_not_reportable(isolated, capsys):
    """A crashed run leaves ``running`` behind; the report must not pick it up."""
    Registry(isolated).create(
        experiment_id="arena-crashed",
        kind="arena",
        scenario_id="easy-static",
        scheduler="nts",
        seed=-1,
        ablation="batch",
        recordings=[],
        config={"kind": "arena", "scenario": {}, "variants": [], "seeds": [0]},
    )
    assert main(["report", "--latest", "6"]) == 2
    assert "nothing to report" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# the round trip the Makefile depends on: run -> registry -> replay -> report
# --------------------------------------------------------------------------- #


@pytest.fixture()
def isolated_over_real_cache(tmp_path, monkeypatch):
    """Isolated registry and reports, but the real cache and window index.

    Symlinked rather than copied: 139 MB of recordings should not be duplicated
    per test, and the point of the exercise is that the CLI reads real data.
    """
    live = Settings()
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    for name, source in (("cached", live.cache_dir), ("index", live.index_dir)):
        if source.exists():
            (data / name).symlink_to(source, target_is_directory=True)
    monkeypatch.setenv("AAMSX_DATA_DIR", str(data))
    monkeypatch.setenv("AAMSX_REPORTS_DIR", str(tmp_path / "reports"))
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@requires_cache
def test_a_run_is_recorded_replayable_and_reportable(isolated_over_real_cache, capsys):
    settings = isolated_over_real_cache
    assert main(["run", "easy-static", "--scheduler", "nts", "--seed", "0", "--json"]) == 0
    episode = json.loads(capsys.readouterr().out)
    experiment_id = episode["experiment_id"]

    record = Registry(settings).get(experiment_id)
    assert record is not None
    assert record.status == "completed"
    assert record.recordings, "a recorded run must name the real recordings it replayed"

    # Replay must reproduce the stored metrics exactly, from the stored spec.
    assert main(["replay", experiment_id, "--json"]) == 0
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["identical"] is True
    assert replayed["replayed"]["cumulative_reward"] == episode["metrics"]["cumulative_reward"]

    # And only now is there something to report.
    assert main(["report", "--id", experiment_id, "--json"]) == 0
    target = Path(json.loads(capsys.readouterr().out)["path"])
    assert target.exists() and target.parent == settings.reports_dir
    html = target.read_text()
    assert experiment_id in html
    assert "not verified ground truth" in html, "the report must state that labels are derived"
    assert f"{episode['metrics']['cumulative_reward']:.2f}"[:5] in html


@requires_cache
def test_the_same_seed_and_scenario_give_the_same_episode_twice(isolated_over_real_cache, capsys):
    rewards = []
    for _ in range(2):
        assert main(["run", "easy-static", "--scheduler", "mag-nts", "--seed", "3", "--json"]) == 0
        rewards.append(json.loads(capsys.readouterr().out)["metrics"]["cumulative_reward"])
    assert rewards[0] == rewards[1]


@requires_cache
def test_an_arena_batch_records_a_discriminating_pareto_frontier(isolated_over_real_cache, capsys):
    assert (
        main(
            [
                "arena",
                "easy-static",
                "--seeds",
                "2",
                "--schedulers",
                "nts",
                "mag-nts",
                "round-robin",
                "--workers",
                "1",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    pareto = payload["pareto"]
    assert pareto["vacuous"] is False, "a frontier with a missing axis is not a finding"
    assert not pareto["axes_missing"]
    assert set(pareto["frontier"]) <= {"nts", "mag-nts", "round-robin"}
