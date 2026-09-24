"""Shared figure style for the AAMS-X SIH deck.

Colours are lifted from web/src/lib/palette.ts so a chart on a slide means the same
thing as the same chart in the product: teal = measured signal, violet = memory /
MAG-NTS, blue = classical baseline, amber = uncertain, red = missed / loss,
green = confirmed / win.

Two surfaces exist on purpose:
  * LIGHT — charts that sit directly on the white SIH template.
  * DARK  — panels presented as product renders (waterfall, belief map).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ROOT = Path(__file__).resolve().parent.parent
FIG = Path(__file__).resolve().parent / "figures"
ASSETS = Path(__file__).resolve().parent / "assets"
FIG.mkdir(exist_ok=True)

DPI = 220

P = dict(
    void="#070a0e", abyss="#0b0f14", panel="#111820", panel2="#16202b",
    line="#1e2a36", lineBright="#2b3a4a", ink="#e6edf3", inkDim="#b6c2ce",
    muted="#8b9bab", faint="#5d6b7a", accent="#4fd1c5", accentDim="#2a8b83",
    signal="#38bdf8", mag="#a78bfa", warn="#f0b429", bad="#f2686b", good="#63c98b",
)
# Ink-on-white variants: the product hues darkened just enough to hold contrast on paper.
L = dict(
    bg="#ffffff", card="#f4f7fa", card2="#eaf0f6", line="#d3dde7", lineSoft="#e6edf3",
    ink="#0d1b2a", inkDim="#3d5163", muted="#6b7d8f", faint="#93a3b3",
    accent="#0f8b80", accentSoft="#7fd8cf", signal="#1f7fc4", mag="#6d4fd8",
    magSoft="#b9a6f5", warn="#b7791f", bad="#c8383c", good="#2f8b52", sih="#0070C0",
    sihDark="#004e86",
)

POLICY_COLOR = {
    "round-robin": L["faint"], "random": "#b4c2ce", "ucb": L["signal"],
    "thompson": "#8a5cf0", "nts": L["accent"], "mag-nts": L["mag"],
}
POLICY_LABEL = {
    "round-robin": "Round Robin", "random": "Random", "ucb": "UCB1",
    "thompson": "Thompson", "nts": "NTS (control)", "mag-nts": "MAG-NTS",
}
PRESET_LABEL = {
    "easy-static": "Easy\nStatic", "periodic-challenge": "Periodic\nChallenge",
    "high-noise": "High\nNoise", "extreme-budget": "Extreme\nBudget",
    "sudden-shift": "Sudden\nShift", "recurring-environment": "Recurring\nEnvironment",
    "unseen-generalization": "Unseen\nGeneralization",
}
ORDER = ["easy-static", "periodic-challenge", "high-noise", "extreme-budget",
         "sudden-shift", "recurring-environment", "unseen-generalization"]

SPECTRUM_STOPS = ["#05080c", "#0a1a26", "#0f3a44", "#16706b", "#28b0a0", "#6fe3c8", "#c8fff0", "#ffffff"]
BELIEF_STOPS = ["#0b0f14", "#1a2740", "#2f4a7a", "#4f7fc4", "#8fb8e8", "#dbe9f8"]
HEAT_STOPS = ["#0b0f14", "#173a5e", "#2a7bb8", "#4fd1c5", "#f0b429", "#f2686b"]
CM_SPECTRUM = LinearSegmentedColormap.from_list("spectrum", SPECTRUM_STOPS)
CM_BELIEF = LinearSegmentedColormap.from_list("belief", BELIEF_STOPS)
CM_HEAT = LinearSegmentedColormap.from_list("heat", HEAT_STOPS)

FAMILY = ["DejaVu Sans", "Helvetica Neue", "Arial"]


def _base(rc: dict) -> None:
    plt.rcParams.update({
        "font.family": "sans-serif", "font.sans-serif": FAMILY,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.8, "xtick.major.size": 0, "ytick.major.size": 0,
        "xtick.major.pad": 6, "ytick.major.pad": 5,
        "figure.autolayout": False, "savefig.dpi": DPI, "figure.dpi": DPI,
        "mathtext.fontset": "dejavusans", "legend.frameon": False,
        **rc,
    })


def light() -> None:
    _base({
        "figure.facecolor": L["bg"], "axes.facecolor": L["bg"],
        "savefig.facecolor": L["bg"], "text.color": L["ink"],
        "axes.labelcolor": L["inkDim"], "axes.edgecolor": L["line"],
        "xtick.color": L["muted"], "ytick.color": L["muted"],
        "grid.color": L["lineSoft"], "grid.linewidth": 0.8,
    })


def dark() -> None:
    _base({
        "figure.facecolor": P["void"], "axes.facecolor": P["abyss"],
        "savefig.facecolor": P["void"], "text.color": P["ink"],
        "axes.labelcolor": P["inkDim"], "axes.edgecolor": P["line"],
        "xtick.color": P["muted"], "ytick.color": P["muted"],
        "grid.color": P["line"], "grid.linewidth": 0.7,
    })


def save(fig, name: str, *, transparent: bool = False, pad: float = 0.06) -> Path:
    path = FIG / f"{name}.png"
    fig.savefig(path, bbox_inches="tight", pad_inches=pad, transparent=transparent)
    plt.close(fig)
    kb = path.stat().st_size / 1024
    print(f"  {name:34s} {kb:7.0f} kB")
    return path


_CACHE: dict[str, dict] = {}


def bench(which: str = "benchmark") -> dict:
    if which not in _CACHE:
        _CACHE[which] = json.loads((ROOT / "reports/out" / f"{which}.json").read_text())
    return _CACHE[which]


def agg(scenario: str, policy: str, metric: str, which: str = "benchmark"):
    return bench(which)[scenario]["aggregates"][policy][metric]


def half_ci(scenario: str, policy: str, metric: str, which: str = "benchmark") -> float:
    a = agg(scenario, policy, metric, which)
    return (a["ci_high"] - a["ci_low"]) / 2.0


def comparison(scenario: str, treatment: str, metric: str, which: str = "benchmark") -> dict | None:
    for c in bench(which)[scenario]["comparisons"]:
        if c["treatment"] == treatment and c["metric"] == metric:
            return c
    return None


def station(name: str):
    z = np.load(ASSETS / f"{name}.npz")
    meta = json.loads((ASSETS / f"{name}.json").read_text())
    return z, meta


def rounded_panel(ax, *, color=None, lw=1.0, radius=0.02):
    """Draw the product's rounded-card border around an axes."""
    from matplotlib.patches import FancyBboxPatch
    color = color or L["line"]
    ax.add_patch(FancyBboxPatch(
        (0, 0), 1, 1, transform=ax.transAxes, boxstyle=f"round,pad=0,rounding_size={radius}",
        linewidth=lw, edgecolor=color, facecolor="none", clip_on=False, zorder=10))
