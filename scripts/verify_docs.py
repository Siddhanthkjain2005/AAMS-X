#!/usr/bin/env python3
"""Diff every published number in the docs against the artefacts that produced them.

``docs/EXPERIMENTS.md`` and ``docs/LIMITATIONS.md`` quote several hundred measured values.
Hand-transcribed tables rot: a re-run moves a p-value in the fourth decimal, someone
rounds 0.003547 to 0.0036, a verdict mark survives a change to the significance rule. This
script re-reads every cell out of the markdown and compares it to
``reports/out/{benchmark,ablation,benchmark_thompson}.json``, at the precision the cell was
published at, and exits non-zero on any disagreement.

Two classes of check:

* **values** — means, CI half-widths, deltas, both p-values, effect sizes, detection
  probabilities, time-to-detect, band coverage, oracle ratios. These are deterministic in
  (spec, scheduler, seed), so they must reproduce exactly at the published precision.
* **claims** — every ✅/❌/○ mark is recomputed from ``welch_p`` and ``mannwhitney_p`` under
  the both-tests rule, so a published verdict cannot drift away from the rule that
  :mod:`aamsx.evaluation.statistics` implements.

Latency is handled separately and deliberately loosely: it is wall-clock, not a function of
the seed, and moved by up to 2x in the tails between two consecutive runs of the identical
command. The docs therefore publish p50 to two decimals, p95/p99 as upper bounds and the
ratios between policies, and this script checks the ordering and those bounds rather than
exact milliseconds.

Usage::

    python scripts/verify_docs.py          # or: make verify-docs
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = (ROOT / "docs/EXPERIMENTS.md").read_text(encoding="utf-8").splitlines()
ARENA = json.loads((ROOT / "reports/out/benchmark.json").read_text(encoding="utf-8"))
LADDER = json.loads((ROOT / "reports/out/ablation.json").read_text(encoding="utf-8"))
_TP = ROOT / "reports/out/benchmark_thompson.json"
THOMPSON = json.loads(_TP.read_text(encoding="utf-8")) if _TP.exists() else None
META = ("seeds", "mode", "baseline")
PRESETS = [k for k in ARENA if k not in META]

PASS: list[str] = []
FAIL: list[str] = []
VERDICTS: list[str] = []


def clean(cell: str) -> str:
    return cell.replace("−", "-").replace("**", "").replace("`", "").replace("*", "").strip()


def scalar(cell: str) -> tuple[float, int]:
    """Leading number in a doc cell, plus the decimals it was published at."""
    match = re.search(r"[-+]?\d+(?:\.\d+)?", clean(cell))
    if match is None:
        raise ValueError(f"no number in {cell!r}")
    text = match.group(0)
    return float(text), (len(text.split(".")[1]) if "." in text else 0)


def check(label: str, published: tuple[float, int], computed: float) -> bool:
    """Compare at the published precision: half a unit in the last printed place."""
    value, decimals = published
    tol = 0.5 * 10.0**-decimals * 1.02 + 1e-12
    if abs(value - computed) <= tol:
        PASS.append(label)
        return True
    FAIL.append(f"{label}: doc {value:g}  measured {computed:.6g}  (tol +-{tol:.2g})")
    return False


def section(title: str) -> list[str]:
    """Every line of the first heading whose text contains ``title``."""
    start = next(i for i, line in enumerate(DOC) if line.startswith("#") and title in line)
    end = next((i for i in range(start + 1, len(DOC)) if DOC[i].startswith("#")), len(DOC))
    return DOC[start:end]


def table(title: str) -> list[list[str]]:
    """Rows of the markdown table in that section, header first, rules dropped."""
    out: list[list[str]] = []
    for line in section(title):
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if all(set(c) <= set("-: ") for c in cells):
            continue
        out.append(cells)
    return out


def mean_ci(cell: str) -> tuple[tuple[float, int], tuple[float, int]]:
    """A `12.345 ± 6.789` cell. The `±` half-width is always `ci_high - mean`."""
    left, right = clean(cell).split("±")
    return scalar(left), scalar(right)


def agg(payload: dict, preset: str, variant: str, metric: str) -> dict:
    return payload[preset]["aggregates"][variant][metric]


def comparison(payload: dict, preset: str, treatment: str, control: str, metric: str) -> dict:
    for row in payload[preset]["comparisons"]:
        if (row["treatment"], row["control"], row["metric"]) == (treatment, control, metric):
            return row
    raise LookupError(f"{preset}: no {treatment} vs {control} on {metric}")


def verdict(row: dict) -> str:
    """The mark the both-tests rule implies for a stored comparison."""
    both = row["welch_p"] < 0.05 and row["mannwhitney_p"] < 0.05
    if not both:
        return "○"
    return "✅" if row["difference"] > 0 else "❌"


def mark(cell: str) -> str:
    for symbol in ("✅", "❌", "○"):
        if symbol in cell:
            return symbol
    return "?"


def check_mark(label: str, cell: str, row: dict) -> None:
    published, rule = mark(cell), verdict(row)
    if published == rule:
        return
    VERDICTS.append(
        f"{label}: doc {published}, both-tests rule {rule} "
        f"(welch {row['welch_p']:.4g}, mwu {row['mannwhitney_p']:.4g})"
    )


# ---- section 4: cumulative reward -------------------------------------------
rows = table("Cumulative reward")
policies = [clean(c) for c in rows[0][1:-1]]
for row in rows[1:]:
    preset = clean(row[0])
    for policy, cell in zip(policies, row[1:-1], strict=True):
        published = mean_ci(cell)
        cell_agg = agg(ARENA, preset, policy, "cumulative_reward")
        check(f"reward {preset}/{policy} mean", published[0], cell_agg["mean"])
        check(f"reward {preset}/{policy} ci", published[1], cell_agg["ci_high"] - cell_agg["mean"])
    delta = clean(row[-1])
    versus = comparison(ARENA, preset, "mag-nts", "nts", "cumulative_reward")
    check(f"reward {preset} delta", scalar(delta), versus["difference"])
    check_mark(f"reward {preset}", row[-1], versus)
    for pattern, key, name in (
        (r"p_W=([\d.]+)", "welch_p", "welch p"),
        (r"p_U=([\d.]+)", "mannwhitney_p", "mwu p"),
        (r"d=([-+]?[\d.]+)", "cohens_d", "cohen d"),
    ):
        found = re.search(pattern, delta)
        if found:
            check(f"reward {preset} {name}", scalar(found.group(1)), versus[key])

# ---- section 4: MAG-NTS against plain Thompson ------------------------------
TITLE = "MAG-NTS against plain Thompson"
if THOMPSON is None:
    FAIL.append(f"{_TP} missing: run run_benchmark.py --seeds 6 --baseline thompson")
else:
    for row in table(TITLE)[1:]:
        preset = clean(row[0])
        for variant, cell in (("thompson", row[1]), ("mag-nts", row[2])):
            published = mean_ci(cell)
            cell_agg = agg(THOMPSON, preset, variant, "cumulative_reward")
            check(f"vs-thompson {preset}/{variant} mean", published[0], cell_agg["mean"])
            check(
                f"vs-thompson {preset}/{variant} ci",
                published[1],
                cell_agg["ci_high"] - cell_agg["mean"],
            )
            # Same seeds and same episodes as the nts-control run, so the means must be
            # identical. That is also a determinism check on the whole episode loop.
            other = agg(ARENA, preset, variant, "cumulative_reward")["mean"]
            if abs(other - cell_agg["mean"]) > 1e-6:
                FAIL.append(f"{preset}/{variant} not reproducible: {other} vs {cell_agg['mean']}")
            else:
                PASS.append(f"vs-thompson {preset}/{variant} reproduces the arena run")
        versus = comparison(THOMPSON, preset, "mag-nts", "thompson", "cumulative_reward")
        check(f"vs-thompson {preset} delta", scalar(row[3]), versus["difference"])
        check(f"vs-thompson {preset} welch p", scalar(row[4]), versus["welch_p"])
        check(f"vs-thompson {preset} mwu p", scalar(row[5]), versus["mannwhitney_p"])
        check(f"vs-thompson {preset} cohen d", scalar(row[6]), versus["cohens_d"])
        check_mark(f"vs-thompson {preset}", row[7], versus)

    prose = " ".join(section(TITLE))
    span = prose.split("MAG-NTS − thompson:")[1].split("MAG-NTS finds")[0]
    for preset, value in re.findall(r"`([a-z-]+)`\s*\**([-+−]\d\.\d+)\**", span):
        measured = (
            agg(THOMPSON, preset, "mag-nts", "sustained_detection_probability")["mean"]
            - agg(THOMPSON, preset, "thompson", "sustained_detection_probability")["mean"]
        )
        check(f"vs-thompson SDP delta {preset}", scalar(value), measured)

# ---- section 4: sustained detection probability -----------------------------
rows = table("Sustained detection probability")
policies = [clean(c) for c in rows[0][1:]]
for row in rows[1:]:
    preset = clean(row[0])
    for policy, cell in zip(policies, row[1:], strict=True):
        check(
            f"SDP {preset}/{policy}",
            scalar(cell),
            agg(ARENA, preset, policy, "sustained_detection_probability")["mean"],
        )

# ---- section 4: band coverage -----------------------------------------------
band_coverage = {p: agg(ARENA, p, "mag-nts", "band_coverage")["mean"] for p in PRESETS}
prose = " ".join(section("Band coverage"))
low, high = re.search(r"\*\*(\d\.\d+)[-–](\d\.\d+)\*\*", prose).groups()
check("band coverage low", scalar(low), min(band_coverage.values()))
check("band coverage high", scalar(high), max(band_coverage.values()))
lowest = min(band_coverage, key=lambda k: band_coverage[k])
claimed = re.search(r"lowest on `([a-z-]+)`", prose).group(1)
(PASS if lowest == claimed else FAIL).append(
    f"band coverage lowest preset: doc {claimed}, measured {lowest}"
)
for policy in ("round-robin", "random"):
    for preset in PRESETS:
        check(
            f"band coverage {preset}/{policy} == 1.000",
            (1.0, 3),
            agg(ARENA, preset, policy, "band_coverage")["mean"],
        )


# ---- section 4: decision latency --------------------------------------------
# The one published quantity that is not deterministic in (spec, scheduler, seed), so the
# doc publishes bounds and ratios and this block checks the claim that was made.
def band(cell: str) -> tuple[float, float, int]:
    """A doc cell that is either `0.02` or `0.29-0.34`, plus its published precision."""
    parts = re.split(r"[-–]", clean(cell).lstrip("≤ ").strip())
    found = [re.search(r"[\d.]+", part) for part in parts]
    texts = [m.group(0) for m in found if m]
    decimals = max(len(t.split(".")[1]) if "." in t else 0 for t in texts)
    return (float(texts[0]), float(texts[-1]), decimals)


def within(label: str, low: float, high: float, decimals: int, values: list[float]) -> None:
    """Every measured value rounds into the published band at its published precision."""
    tol = 0.5 * 10.0**-decimals + 1e-12
    if any(not (low - tol <= v <= high + tol) for v in values):
        FAIL.append(f"{label}: doc {low}-{high}  measured {min(values):.4f}-{max(values):.4f}")
    else:
        PASS.append(label)


for row in table("Decision latency")[1:]:
    policy = clean(row[0])
    within(
        f"latency {policy} p50 band",
        *band(row[1]),
        [ARENA[p]["latency"][policy]["p50"] for p in PRESETS],
    )
    for stat, cell in (("p95", row[2]), ("p99", row[3])):
        bound = band(cell)[1]
        worst = max(ARENA[p]["latency"][policy][stat] for p in PRESETS)
        if worst <= bound:
            PASS.append(f"latency {policy} {stat} <= {bound}")
        else:
            FAIL.append(f"latency {policy} {stat} bound: doc <={bound}  measured {worst:.4f}")
    within(
        f"latency {policy} ratio band",
        *band(row[4]),
        [
            ARENA[p]["latency"][policy]["p50"] / ARENA[p]["latency"]["round-robin"]["p50"]
            for p in PRESETS
        ],
    )

# The ordering is what the prose leans on, so it is checked directly rather than implied.
ORDER = ["round-robin", "random", "ucb", "mag-nts"]
for preset in PRESETS:
    lat = ARENA[preset]["latency"]
    seq = [lat[q]["p50"] for q in ORDER]
    slowest = max(lat, key=lambda q: lat[q]["p50"])
    if seq == sorted(seq) and slowest == "mag-nts":
        PASS.append(f"latency ordering {preset}")
    else:
        FAIL.append(f"latency ordering {preset}: slowest is {slowest}, p50 sequence {seq}")

prose = " ".join(section("Decision latency"))
lo, hi = re.search(r"\*\*(\d+)[-–](\d+)× a round-robin", prose).groups()
within(
    "latency prose mag-nts vs round-robin",
    float(lo),
    float(hi),
    0,
    [
        ARENA[p]["latency"]["mag-nts"]["p50"] / ARENA[p]["latency"]["round-robin"]["p50"]
        for p in PRESETS
    ],
)
maxima = [ARENA[p]["latency"][pol]["max"] for p in PRESETS for pol in ARENA[p]["latency"]]
claimed_max = float(re.search(r"reaches ~(\d+) ms", prose).group(1))
(PASS if max(maxima) <= claimed_max else FAIL).append(
    f"latency max: doc ~{claimed_max:g} ms, measured {max(maxima):.3f} ms"
)

# ---- section 6: oracle ratio -------------------------------------------------
for value, preset in re.findall(r"(\d\.\d+)\s*\(`([a-z-]+)`\)", " ".join(section("Pseudo-regret"))):
    check(
        f"oracle_ratio {preset}",
        scalar(value),
        agg(ARENA, preset, "mag-nts", "oracle_ratio")["mean"],
    )

# ---- section 5: ablation ladder ---------------------------------------------
LADDER_SECTIONS = (
    ("high-noise", "high-noise — memory dominates"),
    ("sudden-shift", "sudden-shift — memory hurts"),
    ("recurring-environment", "recurring-environment — change detection helps"),
)
for preset, title in LADDER_SECTIONS:
    for row in table(title)[1:]:
        arm = clean(row[0])
        published = mean_ci(row[1])
        cell_agg = agg(LADDER, preset, arm, "cumulative_reward")
        check(f"ladder {preset}/{arm} reward", published[0], cell_agg["mean"])
        check(f"ladder {preset}/{arm} ci", published[1], cell_agg["ci_high"] - cell_agg["mean"])
        if arm != "NTS":
            versus = comparison(LADDER, preset, arm, "NTS", "cumulative_reward")
            check(f"ladder {preset}/{arm} delta", scalar(row[2]), versus["difference"])
            check(f"ladder {preset}/{arm} p", scalar(row[3]), versus["welch_p"])
            check_mark(f"ladder {preset}/{arm}", row[3], versus)
        check(
            f"ladder {preset}/{arm} SDP",
            scalar(row[4]),
            agg(LADDER, preset, arm, "sustained_detection_probability")["mean"],
        )
        check(
            f"ladder {preset}/{arm} TTD",
            scalar(row[5]),
            agg(LADDER, preset, arm, "time_to_detect_capped")["mean"],
        )

# ---- LIMITATIONS section 2: the same losses, quoted independently -----------
# The losses are published twice, in two documents, from one artefact. Checking both
# copies is the point: a fix applied to one and forgotten in the other shows up here.
LIMITS = (ROOT / "docs/LIMITATIONS.md").read_text(encoding="utf-8").splitlines()
for line in LIMITS:
    stripped = line.strip()
    if not stripped.startswith("| `"):
        continue
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    if len(cells) == 5:  # scenario | delta | welch | mwu | verdict
        preset = clean(cells[0]).split(" ")[0]
        metric = "sustained_detection_probability" if "SDP" in cells[0] else "cumulative_reward"
        versus = comparison(ARENA, preset, "mag-nts", "nts", metric)
        check(f"limits {preset}/{metric} delta", scalar(cells[1]), versus["difference"])
        check(f"limits {preset}/{metric} welch p", scalar(cells[2]), versus["welch_p"])
        check(f"limits {preset}/{metric} mwu p", scalar(cells[3]), versus["mannwhitney_p"])
        claimed_significant = "not significant" not in cells[4]
        if claimed_significant is not (versus["welch_p"] < 0.05 and versus["mannwhitney_p"] < 0.05):
            VERDICTS.append(f"limits {preset}/{metric} verdict: doc says {cells[4]!r}")
    elif len(cells) == 4 and clean(cells[0]).startswith("NTS"):  # arm | scenario | delta | p
        arm, preset = clean(cells[0]), clean(cells[1])
        versus = comparison(LADDER, preset, arm, "NTS", "cumulative_reward")
        check(f"limits ladder {preset}/{arm} delta", scalar(cells[2]), versus["difference"])
        check(f"limits ladder {preset}/{arm} p", scalar(cells[3]), versus["welch_p"])

# ---- every stored comparison, not only the published ones -------------------
# The docs quote a subset. The rule has to hold for all of them, or the next table
# published from these artefacts starts out wrong.
stored = 0
for payload, name in ((ARENA, "benchmark"), (LADDER, "ablation"), (THOMPSON, "benchmark_thompson")):
    if payload is None:
        continue
    for preset, block in payload.items():
        if not isinstance(block, dict) or "comparisons" not in block:
            continue
        for row in block["comparisons"]:
            stored += 1
            rule = row["welch_p"] < 0.05 and row["mannwhitney_p"] < 0.05
            if bool(row["significant"]) is not rule:
                VERDICTS.append(
                    f"{name}/{preset} {row['treatment']} vs {row['control']} "
                    f"on {row['metric']}: stored significant={row['significant']}, rule={rule}"
                )

print(f"latency max over every policy/preset: {min(maxima):.3f}-{max(maxima):.3f} ms")
print(
    f"checked {len(PASS) + len(FAIL)} published values: {len(PASS)} reproduce, {len(FAIL)} do not"
)
print(f"audited {stored} stored comparisons against the both-tests rule")
print(f"claims disagreeing with the both-tests rule: {len(VERDICTS)}")

for line in VERDICTS:
    print(f"  VERDICT   {line}")
for line in FAIL:
    print(f"  MISMATCH  {line}")
sys.exit(1 if FAIL or VERDICTS else 0)
