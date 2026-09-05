"""``aamsx`` — the command line entry point.

One process, no server required.  Everything here runs the *same* code the API
runs, so a number produced at the terminal and a number produced in the browser
come from one implementation.

Two rules shape this module:

* **Nothing is invented.**  ``report`` renders whatever the reproducibility
  registry actually holds.  If the registry is empty it says so and exits
  non-zero rather than emitting an empty document that looks like a result.
* **Every run is recorded.**  ``run``, ``arena`` and ``ablation`` write into the
  registry with their seed, configuration hash and code version before they
  start and their full result when they finish, which is what makes ``report``
  and ``replay`` honest afterwards.

Run ``aamsx --help`` for the subcommand list.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from aamsx.config import Settings, get_settings
from aamsx.contracts.scenario import ScenarioSpec
from aamsx.logging import configure_logging, get_logger
from aamsx.version import CODE_VERSION, SCHEDULER_VERSION

log = get_logger(__name__)

#: Printed by ``run`` and ``arena``; the same metrics the HTML report leads with.
HEADLINE = (
    ("cumulative_reward", "cumulative reward", 2),
    ("sustained_detection_probability", "P(detect | sustained)", 3),
    ("sustained_detection_delay", "detection delay (steps)", 2),
    ("false_alarm_rate", "false-alarm rate", 3),
    ("detections_per_cost", "detections / cost", 3),
    ("band_coverage", "band coverage", 3),
    ("oracle_ratio", "fraction of oracle", 3),
)

ABLATION_FIELDS = (
    "memory",
    "information_gain",
    "change_detection",
    "periodicity",
    "temporal_encoder",
    "uncertainty_exploration",
    "neural_encoder",
)


# ---- small helpers -----------------------------------------------------------


def _emit(payload: Any) -> None:
    """JSON to stdout, so the CLI composes with jq and other tools."""
    json.dump(payload, sys.stdout, indent=2, default=str, sort_keys=False)
    sys.stdout.write("\n")


def _fail(message: str, *, hint: str = "") -> int:
    print(f"error: {message}", file=sys.stderr)
    if hint:
        print(f"hint:  {hint}", file=sys.stderr)
    return 2


def _table(rows: Sequence[Sequence[str]], *, headers: Sequence[str]) -> str:
    """Fixed-width table. No dependency, no colour codes to strip from a log."""
    columns = [headers, *rows]
    widths = [max(len(str(row[i])) for row in columns) for i in range(len(headers))]
    line = "  ".join(str(h).ljust(w) for h, w in zip(headers, widths, strict=True)).rstrip()
    rule = "  ".join("-" * w for w in widths)
    body = [
        "  ".join(str(cell).ljust(w) for cell, w in zip(row, widths, strict=True)).rstrip()
        for row in rows
    ]
    return "\n".join([line, rule, *body])


def _flags(args: argparse.Namespace):
    """Build ``AblationFlags`` from repeated ``--off NAME`` / ``--on NAME``."""
    from aamsx.schedulers.base import AblationFlags

    hint = f"one of: {', '.join(ABLATION_FIELDS)}"
    flags = AblationFlags()
    for state, names in ((False, getattr(args, "off", None)), (True, getattr(args, "on", None))):
        for name in list(names or []):
            if name not in ABLATION_FIELDS:
                raise SystemExit(_fail(f"unknown component {name!r}", hint=hint))
            flags = replace(flags, **{name: state})
    return flags


def _spec(scenario_id: str) -> ScenarioSpec:
    """Resolve a preset, translating a cache miss into an actionable message."""
    from aamsx.environment.scenarios import PRESET_ORDER, preset

    try:
        return preset(scenario_id)
    except KeyError:
        raise SystemExit(
            _fail(
                f"unknown preset {scenario_id!r}",
                hint=f"presets: {', '.join(PRESET_ORDER)}",
            )
        ) from None
    except (LookupError, FileNotFoundError) as exc:
        raise SystemExit(
            _fail(
                f"preset {scenario_id!r} cannot be built from the current cache: {exc}",
                hint="run `make data && make index` to fetch and characterise real recordings",
            )
        ) from None


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def _print_metrics(metrics: dict[str, Any]) -> None:
    rows = [
        (label, f"{float(metrics[key]):.{digits}f}")
        for key, label, digits in HEADLINE
        if key in metrics and metrics[key] is not None
    ]
    missing = [label for key, label, _ in HEADLINE if key not in metrics]
    print(_table(rows, headers=("metric", "value")))
    if missing:
        print(f"\nnot measured in this result: {', '.join(missing)}")


# ---- run ---------------------------------------------------------------------


def cmd_run(args: argparse.Namespace) -> int:
    """Run one episode, record it, print its headline metrics."""
    from aamsx.experiments.registry import Registry
    from aamsx.experiments.runner import run_episode

    settings = get_settings()
    spec = _spec(args.scenario)
    flags = _flags(args)
    registry = Registry(settings)
    experiment_id = _new_id("cli")

    config = {
        "kind": "episode",
        "scenario": spec.to_dict(),
        "scheduler": args.scheduler,
        "seed": args.seed,
        "flags": flags.to_dict(),
        "scheduler_kwargs": {},
        "source": "cli",
    }
    registry.create(
        experiment_id=experiment_id,
        kind="episode",
        scenario_id=spec.scenario_id,
        scheduler=args.scheduler,
        seed=args.seed,
        ablation=flags.label,
        recordings=[segment.recording_id for segment in spec.segments],
        config=config,
    )
    if not args.json:
        print(f"{args.scheduler} on {spec.name} (seed {args.seed}, ablation {flags.label})")

    try:
        result = run_episode(spec, args.scheduler, seed=args.seed, flags=flags, settings=settings)
    except KeyboardInterrupt:
        registry.finish(experiment_id, status="cancelled", error="interrupted at the terminal")
        return 130
    except Exception as exc:
        registry.finish(experiment_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        return _fail(f"episode failed: {type(exc).__name__}: {exc}")

    payload = result.to_dict()
    registry.finish(experiment_id, status="completed", metrics=result.metrics, result=payload)

    if args.json:
        _emit({"experiment_id": experiment_id, **payload})
        return 0
    _print_metrics(dict(result.metrics))
    print(
        f"\n{result.steps} steps in {result.duration_sec:.2f}s · "
        f"decision p50 {result.decision_ms.get('p50', float('nan')):.3f} ms · "
        f"experiment {experiment_id}"
    )
    return 0


# ---- batches -----------------------------------------------------------------


def _run_batch(
    *,
    kind: str,
    spec: ScenarioSpec,
    jobs: list,
    baseline: str | None,
    workers: int | None,
    settings: Settings,
    as_json: bool,
) -> int:
    """Shared body of ``arena`` and ``ablation``: execute, record, summarise."""
    from aamsx.experiments.batch import run_recorded_batch

    total = len(jobs)
    variants = sorted({job.key for job in jobs})
    # A terminal gets a redrawn counter; a log file gets one line per decile, so a
    # captured run does not end up with 500 progress fragments on one line.
    interactive = sys.stdout.isatty()
    stride = max(1, total // 10)

    def progress(message: dict[str, Any]) -> None:
        if as_json:
            return
        done = int(message.get("done", 0))
        if interactive:
            print(f"\r  {done}/{total} episodes", end="", flush=True)
        elif done % stride == 0 or done == total:
            print(f"  {done}/{total} episodes", flush=True)

    if not as_json:
        print(f"{kind} \u00b7 {spec.name} \u00b7 {total} episodes over {len(variants)} variants")
    try:
        experiment_id, payload = run_recorded_batch(
            jobs,
            kind=kind,
            baseline=baseline,
            workers=workers,
            progress=progress,
            settings=settings,
            source="cli",
        )
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        return _fail(f"batch failed: {type(exc).__name__}: {exc}")
    if not as_json and interactive:
        print()
    aggregates = payload["aggregates"]
    comparisons = payload["comparisons"]

    if as_json:
        _emit({"experiment_id": experiment_id, **payload})
        return 0

    rows = []
    for variant in payload["variants"]:
        entry = aggregates[variant]
        cells = [variant]
        for key, _, digits in HEADLINE[:4]:
            stat = entry.get(key, {})
            mean, low, high = stat.get("mean"), stat.get("ci_low"), stat.get("ci_high")
            if mean is None:
                cells.append("not measured")
            elif low is None or high is None:
                cells.append(f"{mean:.{digits}f}")
            else:
                cells.append(f"{mean:.{digits}f} ±{(high - low) / 2:.{digits}f}")
        rows.append(cells)
    print(
        _table(
            rows,
            headers=("variant", *(f"{label} (mean ±95% CI)" for _, label, _ in HEADLINE[:4])),
        )
    )
    if comparisons:
        print(f"\nagainst control {baseline!r} (Welch t / Mann-Whitney, alpha 0.05):")
        comp_rows = [
            (
                str(row["treatment"]),
                str(row["metric"]),
                f"{float(row['difference']):+.3f}",
                f"{float(row['welch_p']):.4f}",
                f"{float(row['mannwhitney_p']):.4f}",
                f"{float(row['cohens_d']):+.2f}",
                "yes" if float(row["welch_p"]) < 0.05 else "n.s.",
            )
            for row in comparisons
            if row["metric"] == "cumulative_reward"
        ]
        print(_table(comp_rows, headers=("variant", "metric", "delta", "p(t)", "p(U)", "d", "sig")))
    pareto = payload.get("pareto", {})
    if pareto.get("vacuous"):
        print(
            "\nPareto frontier not computed: no aggregate for "
            f"{', '.join(pareto.get('axes_missing', ()))}"
        )
    elif pareto.get("frontier"):
        print(f"\nPareto frontier: {', '.join(pareto['frontier'])}")
    print(f"\nexperiment {experiment_id}")
    return 0


def cmd_arena(args: argparse.Namespace) -> int:
    """Every policy, identical scenario and seeds — the Algorithm Arena."""
    from aamsx.experiments.batch import arena_jobs
    from aamsx.schedulers import ARENA_ORDER, available

    settings = get_settings()
    spec = _spec(args.scenario)
    schedulers = list(args.schedulers or ARENA_ORDER)
    unknown = [name for name in schedulers if name not in available()]
    if unknown:
        return _fail(
            f"unregistered scheduler(s): {', '.join(unknown)}",
            hint=f"registered: {', '.join(sorted(available()))}",
        )
    if args.baseline and args.baseline not in schedulers:
        return _fail(
            f"baseline {args.baseline!r} is not in the compared set",
            hint=f"compared: {', '.join(schedulers)}",
        )
    jobs = arena_jobs(spec, schedulers, range(args.seeds))
    return _run_batch(
        kind="arena",
        spec=spec,
        jobs=jobs,
        baseline=args.baseline,
        workers=args.workers,
        settings=settings,
        as_json=args.json,
    )


def cmd_ablation(args: argparse.Namespace) -> int:
    """The ablation ladder: one component added at a time up to the full policy."""
    from aamsx.experiments.batch import ablation_jobs

    settings = get_settings()
    spec = _spec(args.scenario)
    jobs = ablation_jobs(spec, range(args.seeds), scheduler=args.scheduler)
    return _run_batch(
        kind="ablation",
        spec=spec,
        jobs=jobs,
        baseline=args.baseline,
        workers=args.workers,
        settings=settings,
        as_json=args.json,
    )


# ---- replay ------------------------------------------------------------------


def cmd_replay(args: argparse.Namespace) -> int:
    """Re-execute a stored episode and compare the new metrics with the old ones."""
    from aamsx.experiments.registry import Registry
    from aamsx.experiments.runner import run_episode
    from aamsx.schedulers.base import AblationFlags

    settings = get_settings()
    registry = Registry(settings)
    record = registry.get(args.experiment_id)
    if record is None:
        return _fail(
            f"no experiment {args.experiment_id!r} in the registry",
            hint="`aamsx history` lists what is stored",
        )
    if record.config.get("kind") != "episode":
        return _fail(
            f"experiment {args.experiment_id!r} is a {record.config.get('kind')} batch",
            hint="replay covers single episodes; re-run a batch with `aamsx arena`",
        )
    if record.code_version != CODE_VERSION or record.scheduler_version != SCHEDULER_VERSION:
        # A mismatch is allowed but never hidden: the numbers may legitimately differ.
        print(
            f"note: recorded under code {record.code_version} / scheduler "
            f"{record.scheduler_version}; this build is {CODE_VERSION} / {SCHEDULER_VERSION}",
            file=sys.stderr,
        )

    spec = ScenarioSpec.from_dict(record.config["scenario"])
    flags = AblationFlags(**record.config["flags"])
    result = run_episode(
        spec,
        record.config["scheduler"],
        seed=record.config["seed"],
        flags=flags,
        settings=settings,
    )
    stored = (registry.load_result(args.experiment_id) or {}).get("metrics", {})
    rows = []
    drift = 0
    for key, label, digits in HEADLINE:
        now = result.metrics.get(key)
        then = stored.get(key)
        if now is None or then is None:
            rows.append((label, "not measured" if now is None else f"{now:.{digits}f}", "-", "-"))
            continue
        delta = float(now) - float(then)
        if abs(delta) > 1e-9:
            drift += 1
        rows.append(
            (label, f"{float(then):.{digits}f}", f"{float(now):.{digits}f}", f"{delta:+.{digits}f}")
        )

    if args.json:
        _emit(
            {
                "replay_of": args.experiment_id,
                "config_hash": record.config_hash,
                "identical": drift == 0,
                "stored": stored,
                "replayed": result.metrics,
            }
        )
        return 0
    print(f"replay of {args.experiment_id} · config hash {record.config_hash[:16]}")
    print(_table(rows, headers=("metric", "stored", "replayed", "delta")))
    print(
        "\nbit-identical: every metric reproduced exactly."
        if drift == 0
        else f"\n{drift} metric(s) differ — see the code/scheduler version note above."
    )
    return 0 if drift == 0 else 1


# ---- report ------------------------------------------------------------------


def cmd_report(args: argparse.Namespace) -> int:
    """Render the HTML report from stored results only."""
    from aamsx.experiments.registry import Registry
    from aamsx.reports.html import render

    settings = get_settings()
    registry = Registry(settings)

    if args.id:
        ids = list(args.id)
        missing = [name for name in ids if registry.get(name) is None]
        if missing:
            return _fail(f"not in the registry: {', '.join(missing)}")
    else:
        records = [
            record
            for record in registry.history(limit=max(args.latest * 4, args.latest))
            if record.status == "completed"
        ]
        ids = [record.experiment_id for record in records[: args.latest]]

    if not ids:
        return _fail(
            "the reproducibility registry holds no completed experiments, so there is "
            "nothing to report",
            hint="run `aamsx arena easy-static --seeds 3` (or `make benchmark`) first; "
            "this command will not fabricate a report",
        )

    target = render(ids, title=args.title, notes=args.notes, settings=settings)
    if args.json:
        _emit({"path": str(target), "experiment_ids": ids})
        return 0
    print(f"wrote {target}")
    print(f"sections: {len(ids)} experiment(s) — {', '.join(ids)}")
    return 0


# ---- inspection --------------------------------------------------------------


def cmd_history(args: argparse.Namespace) -> int:
    """What the reproducibility registry holds."""
    from aamsx.experiments.registry import Registry

    registry = Registry(get_settings())
    records = registry.history(limit=args.limit, kind=args.kind)
    if args.json:
        _emit([record.to_dict() for record in records])
        return 0
    if not records:
        print("registry is empty")
        return 0
    rows = [
        (
            record.experiment_id,
            record.kind,
            record.scenario_id,
            record.scheduler[:28],
            str(record.seed),
            record.ablation,
            record.status,
            record.created_at[:19].replace("T", " "),
        )
        for record in records
    ]
    print(
        _table(
            rows,
            headers=(
                "id",
                "kind",
                "scenario",
                "scheduler",
                "seed",
                "ablation",
                "status",
                "created",
            ),
        )
    )
    print(f"\n{registry.stats()}")
    return 0


def cmd_presets(args: argparse.Namespace) -> int:
    """Which presets the current real-data cache can actually build."""
    from aamsx.environment.scenarios import PRESET_ORDER, list_presets

    specs = list_presets()
    if args.json:
        _emit([spec.to_dict() for spec in specs])
        return 0
    rows = [
        (
            spec.scenario_id,
            spec.split,
            spec.family,
            str(spec.n_regions),
            str(spec.horizon),
            f"{spec.effective_budget():.0f}",
            ", ".join(sorted({segment.recording_id for segment in spec.segments})),
        )
        for spec in specs
    ]
    print(
        _table(
            rows,
            headers=("preset", "split", "family", "regions", "horizon", "budget", "recordings"),
        )
    )
    unbuildable = [
        name for name in PRESET_ORDER if name not in {spec.scenario_id for spec in specs}
    ]
    if unbuildable:
        print(f"\nnot buildable from the current cache: {', '.join(unbuildable)}")
        print("run `make data && make index` to fetch and characterise more real recordings")
    return 0


def cmd_schedulers(args: argparse.Namespace) -> int:
    """Every registered policy, including the flagged optional ones."""
    from aamsx.schedulers import deep_rl_available, describe_all

    entries = describe_all()
    if args.json:
        _emit({"schedulers": entries, "deep_rl_available": deep_rl_available()})
        return 0
    rows = [
        (
            str(entry["name"]),
            str(entry["display_name"]),
            str(entry["family"]),
            "yes" if entry["stochastic"] else "no",
            "yes" if entry["uses_memory"] else "no",
            "yes" if entry["uses_information_gain"] else "no",
        )
        for entry in entries
    ]
    print(_table(rows, headers=("name", "display", "family", "stochastic", "memory", "IG")))
    if not deep_rl_available():
        print("\ndeep-RL policy not registered: PyTorch is absent (the default install)")
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """Environment, cache and adapter state — what this install can actually do."""
    from aamsx.datasets.electrosense import status as electrosense_status
    from aamsx.datasets.store import list_recordings
    from aamsx.experiments.registry import Registry
    from aamsx.schedulers import available, deep_rl_available

    settings = get_settings()
    registry = Registry(settings)
    recordings = list_recordings(settings=settings)
    cache_bytes = sum(
        path.stat().st_size for path in settings.cache_dir.glob("**/*") if path.is_file()
    )
    index = settings.index_dir / "windows.parquet"
    try:
        import torch  # noqa: F401

        torch_state = "installed"
    except ImportError:
        torch_state = "absent (optional extra)"

    payload = {
        "code_version": CODE_VERSION,
        "scheduler_version": SCHEDULER_VERSION,
        "python": sys.version.split()[0],
        "data_dir": str(settings.data_dir),
        "cached_recordings": len(recordings),
        "cached_mb": round(cache_bytes / 1e6, 1),
        "stations": sorted({record.station for record in recordings}),
        "recording_days": sorted({record.day for record in recordings}),
        "window_index": str(index) if index.exists() else "missing (run `make index`)",
        "registry": {"path": str(settings.registry_path), **registry.stats()},
        "reports_dir": str(settings.reports_dir),
        "network_allowed": settings.allow_network,
        "schedulers": sorted(available()),
        "torch": torch_state,
        "deep_rl_available": deep_rl_available(),
        "neural_encoder_flag": settings.enable_neural,
        "electrosense": electrosense_status(settings, probe=args.probe),
    }
    if args.json:
        _emit(payload)
        return 0
    for key, value in payload.items():
        print(f"{key:22} {value}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Run the API. Bound to localhost unless told otherwise, and never public by default."""
    try:
        import uvicorn
    except ImportError:
        return _fail("uvicorn is not installed", hint="pip install -e '.[dev]'")

    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        # Said out loud rather than assumed: the API has no authentication layer.
        print(
            f"warning: binding to {args.host} exposes an unauthenticated API to the network. "
            "Only do this on a trusted host.",
            file=sys.stderr,
        )
    uvicorn.run(
        "aamsx.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None,
    )
    return 0


# ---- parser ------------------------------------------------------------------


def _add_ablation_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--off",
        action="append",
        metavar="COMPONENT",
        help=f"disable one component (repeatable): {', '.join(ABLATION_FIELDS)}",
    )
    parser.add_argument(
        "--on",
        action="append",
        metavar="COMPONENT",
        help="enable one component (repeatable), e.g. --on neural_encoder",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aamsx",
        description=(
            "AAMS-X — adaptive associative active-sensing scheduler over real, cached "
            "spectrum recordings. Academic and simulation use only: nothing here "
            "transmits, tunes hardware, or identifies real-world emitters."
        ),
    )
    parser.add_argument("--version", action="version", version=f"aamsx {CODE_VERSION}")
    parser.add_argument(
        "--log-level",
        default="WARNING",
        help="root log level (default WARNING, so tables stay readable)",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    run = sub.add_parser("run", help="run one episode and record it")
    run.add_argument("scenario", help="preset id, e.g. easy-static")
    run.add_argument("--scheduler", default="mag-nts")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--json", action="store_true", help="emit the full result as JSON")
    _add_ablation_options(run)
    run.set_defaults(func=cmd_run)

    arena = sub.add_parser("arena", help="race every policy over identical seeds")
    arena.add_argument("scenario")
    arena.add_argument("--seeds", type=int, default=6, help="seeds per policy (default 6)")
    arena.add_argument(
        "--schedulers", nargs="+", metavar="NAME", help="policies to compare (default: all)"
    )
    arena.add_argument("--baseline", default="nts", help="control for the significance tests")
    arena.add_argument("--workers", type=int, default=None)
    arena.add_argument("--json", action="store_true")
    arena.set_defaults(func=cmd_arena)

    ablation = sub.add_parser("ablation", help="run the ablation ladder")
    ablation.add_argument("scenario")
    ablation.add_argument("--seeds", type=int, default=6)
    ablation.add_argument("--scheduler", default="mag-nts")
    ablation.add_argument("--baseline", default="NTS", help="ladder rung used as the control")
    ablation.add_argument("--workers", type=int, default=None)
    ablation.add_argument("--json", action="store_true")
    ablation.set_defaults(func=cmd_ablation)

    replay = sub.add_parser("replay", help="re-execute a stored episode and diff its metrics")
    replay.add_argument("experiment_id")
    replay.add_argument("--json", action="store_true")
    replay.set_defaults(func=cmd_replay)

    report = sub.add_parser("report", help="render an HTML report from stored results")
    report.add_argument("--latest", type=int, default=6, help="most recent completed experiments")
    report.add_argument("--id", action="append", metavar="EXPERIMENT_ID", help="explicit ids")
    report.add_argument("--title", default="AAMS-X Experiment Report")
    report.add_argument("--notes", default="")
    report.add_argument("--json", action="store_true")
    report.set_defaults(func=cmd_report)

    history = sub.add_parser("history", help="list stored experiments")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--kind", default=None, help="episode | arena | ablation")
    history.add_argument("--json", action="store_true")
    history.set_defaults(func=cmd_history)

    presets = sub.add_parser("presets", help="list buildable scenario presets")
    presets.add_argument("--json", action="store_true")
    presets.set_defaults(func=cmd_presets)

    schedulers = sub.add_parser("schedulers", help="list registered policies")
    schedulers.add_argument("--json", action="store_true")
    schedulers.set_defaults(func=cmd_schedulers)

    info = sub.add_parser("info", help="environment, cache and adapter state")
    info.add_argument(
        "--probe", action="store_true", help="contact the ElectroSense host (one request)"
    )
    info.add_argument("--json", action="store_true")
    info.set_defaults(func=cmd_info)

    serve = sub.add_parser("serve", help="run the API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    serve.set_defaults(func=cmd_serve)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.log_level)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130
    except SystemExit as exc:  # _fail() raised through a helper
        return int(exc.code or 0)


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
