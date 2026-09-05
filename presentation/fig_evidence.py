"""Evidence figures: how the numbers were produced, and what they buy.

Every claim drawn here is either read out of ``reports/out/*.json`` at render time or
taken from the verification snapshot in ``docs/QUALITY_AND_RISKS.md`` — including the
places where the project is *not* green.  A deck that hides its own risk register is
the deck a panel catches out in Q&A.
"""
from __future__ import annotations

import json

import numpy as np
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from figstyle import L, ORDER, ROOT, bench, light, plt, save


def _canvas(w=13.1, h=6.2):
    fig = plt.figure(figsize=(w, h))
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_axis_off()
    ax.set_xlim(0, 1); ax.set_ylim(0, 1)
    return fig, ax


def _box(ax, xy, w, h, *, fc, ec, lw=1.2, r=0.014, z=2):
    ax.add_patch(FancyBboxPatch(xy, w, h, transform=ax.transAxes, zorder=z,
                                boxstyle=f"round,pad=0,rounding_size={r}",
                                facecolor=fc, edgecolor=ec, linewidth=lw))


def _arrow(ax, a, b, *, color=None, lw=1.6, style="-|>", z=1):
    ax.add_patch(FancyArrowPatch(a, b, transform=ax.transAxes, zorder=z,
                                 arrowstyle=style, color=color or L["line"],
                                 linewidth=lw, mutation_scale=13,
                                 shrinkA=2, shrinkB=2))


STAGES = [
    ("1 · REAL RECORDING", L["signal"],
     ["e-CALLISTO public archive", "7 receivers · 4 continents", "139 MB on disk, fetched once"],
     "uint8 digits → excess dB\nover a drift-tracked P10\nbaseline. Per-file URL,\ntimestamp, checksum and\npreprocessing chain kept.",
     "is_synthetic: false"),
    ("2 · DERIVED LABEL", L["warn"],
     ["threshold = max(1.5 dB, 5σ)", "σ = 1.4826·MAD/√2", "stated policy, not truth"],
     "No public archive of this\nkind carries per-emitter\nground truth. Every panel\nbuilt on the label is tagged\nderived-label.",
     "comparable, not absolute"),
    ("3 · SEALED ENVIRONMENT", L["bad"],
     ["frozen DecisionContext", "truth array unreachable", "budget enforced per step"],
     "The scheduler is handed a\nread-only context inside\nenv.sealed(). Reaching for\nhidden state raises\nLeakageError.",
     "29 leakage tests"),
    ("4 · STORED TRACE", L["mag"],
     ["config hash per run", "6 seeds × 6 policies", "13 metrics per arm"],
     "Every episode persists its\nscenario, flags, curves,\ntimeline and latency, so a\nfigure can be rebuilt from\nthe record alone.",
     "replay re-runs it"),
    ("5 · VERIFIED CLAIM", L["good"],
     ["Welch t AND Mann-Whitney U", "α = 0.05, both must pass", "Student-t 95% CI, 6 seeds"],
     "verify_docs.py re-derives\nevery published number\nfrom the stored results\nand fails the build on a\nsingle disagreement.",
     "406/406 reproduce"),
]


def fig_reproducibility():
    light()
    fig, ax = _canvas(13.1, 6.35)
    ax.text(0.008, 0.965, "From a public recording to a number the panel can re-derive",
            fontsize=17.5, color=L["ink"], fontweight="bold", va="top")
    ax.text(0.008, 0.912, "Five stages, each with a mechanism that fails loudly rather "
            "than degrading quietly.", fontsize=10.2, color=L["inkDim"], va="top")

    w, gap = 0.1826, 0.0181
    for i, (title, col, bullets, body, stamp) in enumerate(STAGES):
        x = 0.008 + i * (w + gap)
        _box(ax, (x, 0.395), w, 0.455, fc=L["bg"], ec=L["line"], lw=1.15)
        ax.add_patch(FancyBboxPatch((x, 0.792), w, 0.058, transform=ax.transAxes,
                                    boxstyle="round,pad=0,rounding_size=0.014",
                                    facecolor=col, edgecolor=col, zorder=3))
        ax.text(x + 0.011, 0.821, title, fontsize=8.6, color="#ffffff",
                fontweight="bold", va="center", zorder=4)
        for j, b in enumerate(bullets):
            ax.text(x + 0.011, 0.760 - j * 0.032, "▪", fontsize=6.0, color=col, va="center")
            ax.text(x + 0.026, 0.760 - j * 0.032, b, fontsize=7.8, color=L["ink"], va="center")
        ax.text(x + 0.011, 0.645, body, fontsize=7.5, color=L["inkDim"], va="top",
                linespacing=1.62)
        _box(ax, (x + 0.011, 0.412), w - 0.022, 0.043, fc=L["card2"], ec=L["card2"], r=0.01)
        ax.text(x + w / 2, 0.4335, stamp, fontsize=8.0, color=col, fontweight="bold",
                ha="center", va="center", zorder=4)
        if i < len(STAGES) - 1:
            _arrow(ax, (x + w + 0.0025, 0.62), (x + w + gap - 0.0025, 0.62),
                   color=L["faint"], lw=1.7)
    return fig, ax


VERIFIED = [
    ("507 tests collect · 438 pass here", "ruff clean · mypy clean over 72 modules"),
    ("406 / 406 published values reproduce", "re-derived from the stored result JSON"),
    ("1,456 stored comparisons audited", "0 disagree with the both-tests rule"),
    ("6 seeds × 6 policies × 7 presets", "252 episodes behind the arena table"),
    ("0.29–0.31 ms median per decision", "against a 250 ms environment step"),
]
NOT_GREEN = [
    ("65 API/CLI fixtures error before their body", "one symlinked-cache mkdir issue, not 65 bugs"),
    ("No auth on the API", "single-operator demo host; documented, not shipped as production"),
    ("Only DQN exists, not SAC", "registered when Torch imports, not by the flag"),
    ("No frontend unit tests", "TypeScript + production build only"),
]


def _rows(ax, x, y, w, rows, *, col, head, note):
    _box(ax, (x, y - 0.050 - 0.054 * len(rows)), w, 0.054 * len(rows) + 0.105,
         fc=L["bg"], ec=col, lw=1.2)
    ax.text(x + 0.014, y + 0.030, head, fontsize=10.6, color=col, fontweight="bold", va="center")
    ax.text(x + w - 0.014, y + 0.030, note, fontsize=8.0, color=L["muted"], va="center", ha="right")
    for i, (a, b) in enumerate(rows):
        yy = y - 0.022 - i * 0.054
        ax.text(x + 0.014, yy, "✓" if col == L["good"] else "!", fontsize=9.6, color=col,
                fontweight="bold", va="center")
        ax.text(x + 0.037, yy + 0.010, a, fontsize=8.9, color=L["ink"], va="center")
        ax.text(x + 0.037, yy - 0.018, b, fontsize=7.7, color=L["muted"], va="center")


def fig_reproducibility_full():
    fig, ax = fig_reproducibility()
    _rows(ax, 0.008, 0.330, 0.492, VERIFIED, col=L["good"],
          head="MEASURED AND RE-DERIVED", note="scripts/verify_docs.py · pytest · mypy")
    _rows(ax, 0.518, 0.330, 0.474, NOT_GREEN, col=L["warn"],
          head="OPEN, AND WRITTEN DOWN", note="docs/QUALITY_AND_RISKS.md")
    ax.text(0.008, 0.862, "A risk register is part of the deliverable — every open row is in "
            "the repository with a recommended fix. We would rather be asked about it "
            "than caught by it.", fontsize=9.4, color=L["warn"], va="top", style="italic")
    return save(fig, "reproducibility")


if __name__ == "__main__":
    fig_reproducibility_full()
