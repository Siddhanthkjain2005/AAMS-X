"""Experiment report generation.

The report is assembled from stored experiment results only.  There is no path in
this module that can invent a number: if a metric is missing from the stored
result it is rendered as "not measured" rather than filled in.

Output is a single self-contained HTML file — no external CSS, no CDN, no
JavaScript required to read it — so it survives being emailed, archived or opened
on a machine with no network.  Charts are inline SVG drawn from the stored curves.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from aamsx.config import Settings, get_settings
from aamsx.experiments.registry import Registry
from aamsx.logging import get_logger
from aamsx.version import CODE_VERSION, SCHEDULER_VERSION

log = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"

HEADLINE = (
    ("cumulative_reward", "Cumulative reward", 1, "higher is better"),
    ("cumulative_regret", "Cumulative regret", 0, "lower is better"),
    ("sustained_detection_probability", "P(detect | sustained event)", 3, "higher is better"),
    ("time_to_detect_capped", "Time to detect (missed = cap)", 2, "lower is better"),
    ("false_alarm_rate", "False-alarm rate", 3, "lower is better"),
    ("detections_per_cost", "Detections per unit cost", 3, "higher is better"),
    ("information_per_observation", "Bits per observation", 3, "higher is better"),
    ("oracle_ratio", "Fraction of clairvoyant oracle", 3, "higher is better"),
)


@dataclass(frozen=True, slots=True)
class ReportSection:
    kind: str
    title: str
    payload: dict[str, Any]


def _sparkline(values: list[float], *, width: int = 520, height: int = 90) -> str:
    """Inline SVG polyline. Returns an empty string rather than a fake chart."""
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = (high - low) or 1.0
    step = width / (len(values) - 1)
    points = " ".join(
        f"{index * step:.1f},{height - (value - low) / span * (height - 6) - 3:.1f}"
        for index, value in enumerate(values)
    )
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" class="spark">'
        f'<polyline points="{points}" />'
        f"</svg>"
    )


def _environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["sparkline"] = _sparkline
    env.filters["tojson_pretty"] = lambda value: json.dumps(value, indent=2, default=str)
    return env


def _half_width(entry: dict[str, Any]) -> float:
    """Half the 95% CI, i.e. the ± figure the tables print."""
    return (entry.get("ci_high", float("nan")) - entry.get("ci_low", float("nan"))) / 2


def _format(value: Any, digits: int) -> str:
    if value is None:
        return "not measured"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number:  # NaN
        return "not measured"
    return f"{number:.{digits}f}"


def build_sections(experiment_ids: list[str], registry: Registry) -> list[ReportSection]:
    """Load every requested experiment and shape it for the template."""
    sections: list[ReportSection] = []
    for experiment_id in experiment_ids:
        record = registry.get(experiment_id)
        result = registry.load_result(experiment_id)
        if record is None or result is None:
            sections.append(
                ReportSection(
                    kind="missing",
                    title=experiment_id,
                    payload={
                        "reason": "no stored result for this id — it may still be running, "
                        "or its trace was evicted"
                    },
                )
            )
            continue
        if record.kind == "episode":
            sections.append(_episode_section(record, result))
        else:
            sections.append(_batch_section(record, result))
    return sections


def _episode_section(record, result: dict[str, Any]) -> ReportSection:
    metrics = result.get("metrics", {})
    rows = [
        {
            "label": label,
            "value": _format(metrics.get(key), digits),
            "direction": direction,
            "key": key,
        }
        for key, label, digits, direction in HEADLINE
    ]
    return ReportSection(
        kind="episode",
        title=f"{record.scheduler} on {result['scenario']['name']} (seed {record.seed})",
        payload={
            "record": record.to_dict(),
            "scenario": result["scenario"],
            "metrics": rows,
            "reward_curve": result.get("curves", {}).get("reward", []),
            "regret_curve": result.get("curves", {}).get("regret", []),
            "timeline": [
                entry
                for entry in result.get("timeline", [])
                if entry["severity"] in {"critical", "insight", "warning"}
            ][:24],
            "recovery": result.get("recovery", {}),
            "segments": result.get("segment_metrics", []),
            "decision_ms": result.get("decision_ms", {}),
            "flags": record.ablation,
        },
    )


def _batch_section(record, result: dict[str, Any]) -> ReportSection:
    aggregates = result.get("aggregates", {})
    variants = result.get("variants", [])
    table = []
    for variant in variants:
        entry = aggregates.get(variant, {})
        table.append(
            {
                "variant": variant,
                "cells": [
                    {
                        "label": label,
                        "mean": _format(entry.get(key, {}).get("mean"), digits),
                        "ci": (
                            f"±{_format(_half_width(entry.get(key, {})), digits)}"
                            if entry.get(key)
                            else ""
                        ),
                    }
                    for key, label, digits, _ in HEADLINE
                ],
            }
        )
    comparisons = [
        row
        for row in result.get("comparisons", [])
        if row["metric"] in {"cumulative_reward", "sustained_detection_probability"}
    ]
    return ReportSection(
        kind="batch",
        title=f"{record.kind} · {result['scenario']['name']}",
        payload={
            "record": record.to_dict(),
            "scenario": result["scenario"],
            "headers": [label for _, label, _, _ in HEADLINE],
            "table": table,
            "comparisons": comparisons,
            "pareto": result.get("pareto", {}),
            "latency": result.get("latency", {}),
            "n_runs": result.get("n_runs", {}),
        },
    )


def render(
    experiment_ids: list[str],
    *,
    title: str = "AAMS-X Experiment Report",
    notes: str = "",
    settings: Settings | None = None,
) -> Path:
    """Render an HTML report and return its path."""
    settings = settings or get_settings()
    registry = Registry(settings)
    sections = build_sections(experiment_ids, registry)
    template = _environment().get_template("report.html")
    html = template.render(
        title=title,
        notes=notes,
        sections=sections,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        code_version=CODE_VERSION,
        scheduler_version=SCHEDULER_VERSION,
    )
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    target = settings.reports_dir / f"aamsx-report-{stamp}.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    log.info("report.written", extra={"path": str(target), "sections": len(sections)})
    return target
