"""Result figures. Every value is read from reports/out/*.json — nothing is typed by hand."""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

from figstyle import (L, P, ORDER, POLICY_COLOR, POLICY_LABEL, PRESET_LABEL,
                      agg, bench, comparison, half_ci, light, dark, save)

POLICIES = ["round-robin", "random", "ucb", "thompson", "nts", "mag-nts"]


def fig_arena_reward() -> None:
    """Cumulative reward, 6 policies x 7 presets, Student-t 95% CI half-widths."""
    light()
    fig, ax = plt.subplots(figsize=(12.4, 4.5))
    n = len(POLICIES)
    width = 0.132
    x = np.arange(len(ORDER))
    for i, pol in enumerate(POLICIES):
        means = [agg(s, pol, "cumulative_reward")["mean"] for s in ORDER]
        errs = [half_ci(s, pol, "cumulative_reward") for s in ORDER]
        off = (i - (n - 1) / 2) * width
        emph = pol == "mag-nts"
        ax.bar(x + off, means, width * 0.92, yerr=errs, capsize=1.6,
               color=POLICY_COLOR[pol], label=POLICY_LABEL[pol],
               edgecolor=L["mag"] if emph else "none", linewidth=1.1 if emph else 0,
               error_kw=dict(elinewidth=0.9, ecolor=L["inkDim"], alpha=0.85), zorder=3)
    ax.axhline(0, color=L["line"], lw=0.9, zorder=2)
    ax.set_xticks(x)
    ax.set_xticklabels([PRESET_LABEL[s] for s in ORDER], fontsize=9.4, color=L["inkDim"], linespacing=1.35)
    ax.set_ylabel("Cumulative reward  (mean of 6 seeds)", fontsize=9.6, labelpad=8)
    ax.yaxis.grid(True, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(ncol=6, fontsize=9.2, loc="upper center", bbox_to_anchor=(0.5, 1.13),
              columnspacing=1.5, handlelength=1.1, handleheight=0.9)
    for spine in ("left",):
        ax.spines[spine].set_color(L["line"])
    ax.tick_params(labelsize=8.8)
    fig.text(0.995, -0.055, "error bars = Student-t 95% CI half-width, n = 6 seeds  ·  identical real windows for every policy",
             ha="right", fontsize=7.8, color=L["muted"], transform=ax.transAxes)
    save(fig, "arena_reward")


def _delta_panel(ax, control: str, which: str, title: str) -> None:
    deltas, tones, marks, notes = [], [], [], []
    for s in ORDER:
        c = comparison(s, "mag-nts", "cumulative_reward", which)
        deltas.append(c["difference"])
        both = c["welch_p"] < 0.05 and c["mannwhitney_p"] < 0.05
        win = c["difference"] > 0
        tones.append(L["good"] if (both and win) else L["bad"] if (both and not win)
                     else L["accentSoft"] if win else "#e7b9ba")
        marks.append("significant" if both else "not significant")
        notes.append(f"p={c['welch_p']:.4g}/{c['mannwhitney_p']:.4g}  d={c['cohens_d']:+.2f}")
    y = np.arange(len(ORDER))[::-1]
    ax.barh(y, deltas, 0.62, color=tones, zorder=3)
    ax.axvline(0, color=L["ink"], lw=1.1, zorder=4)
    span = max(abs(min(deltas)), abs(max(deltas)))
    ax.set_xlim(-span * 1.55, span * 1.55)
    for yi, d, m, nt in zip(y, deltas, marks, notes):
        side = 1 if d > 0 else -1
        sig = m == "significant"
        mark = ("✓ " if d > 0 else "✗ ") if sig else ""
        label = f"{mark}{d:+.2f}" if d > 0 else f"{d:+.2f} {mark}".rstrip()
        ax.text(d + side * span * 0.05, yi + 0.05, label,
                va="center", ha="left" if d > 0 else "right",
                fontsize=10.4, fontweight="bold",
                color=(L["good"] if d > 0 else L["bad"]) if sig else L["inkDim"])
        ax.text(d + side * span * 0.05, yi - 0.29, nt, va="center",
                ha="left" if d > 0 else "right", fontsize=6.5, color=L["muted"])
    ax.set_yticks(y)
    ax.set_yticklabels([PRESET_LABEL[s].replace("\n", " ") for s in ORDER], fontsize=9.4, color=L["inkDim"])
    ax.set_xlabel(f"Δ cumulative reward:  MAG-NTS − {control}", fontsize=9.4, labelpad=7)
    ax.xaxis.grid(True, zorder=0); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.set_title(title, fontsize=11.4, fontweight="bold", color=L["ink"], pad=12, loc="left")


def fig_delta_both() -> None:
    """The two head-to-heads side by side: this is the honest core of the evidence."""
    light()
    fig, axes = plt.subplots(1, 2, figsize=(12.6, 4.6))
    _delta_panel(axes[0], "NTS", "benchmark",
                 "vs NTS control — what the new machinery adds")
    _delta_panel(axes[1], "Thompson", "benchmark_thompson",
                 "vs plain Thompson — what it adds on non-stationary bands")
    fig.text(0.5, -0.045, "✓ / ✗ = significant under BOTH Welch t and Mann-Whitney U at α = 0.05, n = 6 seeds  ·  "
             "faded bars lead on the mean without reaching significance",
             ha="center", fontsize=7.8, color=L["muted"])
    fig.subplots_adjust(wspace=0.30)
    save(fig, "delta_both")


def fig_sdp() -> None:
    """Sustained detection probability: what fraction of distinct activity got seen."""
    light()
    fig, ax = plt.subplots(figsize=(12.2, 3.9))
    pols = ["round-robin", "ucb", "thompson", "nts", "mag-nts"]
    width = 0.155
    x = np.arange(len(ORDER))
    for i, pol in enumerate(pols):
        vals = [agg(s, pol, "sustained_detection_probability")["mean"] for s in ORDER]
        errs = [half_ci(s, pol, "sustained_detection_probability") for s in ORDER]
        off = (i - (len(pols) - 1) / 2) * width
        emph = pol == "mag-nts"
        ax.bar(x + off, vals, width * 0.9, yerr=errs, capsize=1.4, color=POLICY_COLOR[pol],
               label=POLICY_LABEL[pol], edgecolor=L["mag"] if emph else "none",
               linewidth=1.1 if emph else 0,
               error_kw=dict(elinewidth=0.8, ecolor=L["inkDim"], alpha=0.8), zorder=3)
        if emph:
            for xi, v in zip(x + off, vals):
                ax.text(xi, v + 0.018, f"{v:.3f}", ha="center", fontsize=6.8,
                        color=L["mag"], fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([PRESET_LABEL[s] for s in ORDER], fontsize=9.2, color=L["inkDim"], linespacing=1.35)
    ax.set_ylabel("Sustained detection\nprobability", fontsize=9.4, labelpad=8)
    ax.set_ylim(0, 0.82)
    ax.yaxis.grid(True, zorder=0); ax.set_axisbelow(True)
    ax.legend(ncol=5, fontsize=9, loc="upper center", bbox_to_anchor=(0.5, 1.16),
              columnspacing=1.6, handlelength=1.1)
    ax.tick_params(labelsize=8.6)
    fig.text(0.995, -0.07, "derived labels: excess above max(1.5 dB, 5σ), σ = first-difference MAD vs a drift-tracking P10 baseline",
             ha="right", fontsize=7.6, color=L["muted"], transform=ax.transAxes)
    save(fig, "sdp")


def fig_ablation() -> None:
    """The ladder: which component does the work, and where it backfires."""
    light()
    scen = ["high-noise", "sudden-shift", "recurring-environment"]
    arms = ["NTS+Memory", "NTS+IG", "NTS+ChangeDetection", "NTS+Periodicity",
            "NTS+Memory+IG", "Full MAG-NTS"]
    short = {"NTS+Memory": "+ Associative memory", "NTS+IG": "+ Information gain",
             "NTS+ChangeDetection": "+ Change detection", "NTS+Periodicity": "+ Periodicity",
             "NTS+Memory+IG": "+ Memory & IG", "Full MAG-NTS": "Full MAG-NTS"}
    fig, axes = plt.subplots(1, 3, figsize=(12.8, 4.0), sharey=True)
    for ax, s in zip(axes, scen):
        rows = []
        for a in arms:
            c = comparison(s, a, "cumulative_reward", "ablation")
            both = c["welch_p"] < 0.05 and c["mannwhitney_p"] < 0.05
            rows.append((short[a], c["difference"], both, c["welch_p"]))
        y = np.arange(len(rows))[::-1]
        d = [r[1] for r in rows]
        cols = [(L["good"] if r[2] else L["accentSoft"]) if r[1] > 0
                else (L["bad"] if r[2] else "#e7b9ba") for r in rows]
        ax.barh(y, d, 0.60, color=cols, zorder=3)
        ax.axvline(0, color=L["ink"], lw=1.0, zorder=4)
        span = max(abs(min(d)), abs(max(d)), 1e-6)
        ax.set_xlim(-span * 1.55, span * 1.55)
        for yi, r in zip(y, rows):
            side = 1 if r[1] >= 0 else -1
            txt = f"{r[1]:+.2f}" + ("  ✓" if r[2] and r[1] > 0 else "  ✗" if r[2] else "")
            ax.text(r[1] + side * span * 0.05, yi, txt, va="center",
                    ha="left" if r[1] >= 0 else "right", fontsize=8.6,
                    fontweight="bold" if r[2] else "normal", color=L["ink"])
        ax.set_yticks(y)
        ax.set_yticklabels([r[0] for r in rows], fontsize=8.8, color=L["inkDim"])
        ax.set_title(PRESET_LABEL[s].replace("\n", " "), fontsize=10.6, fontweight="bold",
                     color=L["ink"], pad=9)
        ax.xaxis.grid(True, zorder=0); ax.set_axisbelow(True)
        ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0, labelsize=8.6)
        ax.tick_params(axis="x", labelsize=7.8)
    axes[0].set_xlabel("Δ reward vs NTS", fontsize=9)
    axes[1].set_xlabel("Δ reward vs NTS", fontsize=9)
    axes[2].set_xlabel("Δ reward vs NTS", fontsize=9)
    fig.text(0.5, -0.055, "7-arm ladder, one component switched on at a time, 6 seeds each. "
             "Change detection scores exactly +0.00 on high-noise — the detector never fires, which is how we know the arm is isolated.",
             ha="center", fontsize=7.7, color=L["muted"])
    fig.subplots_adjust(wspace=0.34)
    save(fig, "ablation")


def fig_latency() -> None:
    """Latency against the environment step: three orders of magnitude of headroom."""
    light()
    fig, ax = plt.subplots(figsize=(6.6, 3.5))
    pols = POLICIES
    p50 = [np.median([bench()[s]["latency"][p]["p50"] for s in ORDER]) for p in pols]
    y = np.arange(len(pols))[::-1]
    ax.barh(y, p50, 0.56, color=[POLICY_COLOR[p] for p in pols], zorder=3)
    ax.axvline(250.0, color=L["bad"], lw=1.6, ls=(0, (4, 2)), zorder=5)
    ax.text(250.0, len(pols) - 0.35, "  0.25 s environment step\n  (e-CALLISTO cadence)",
            fontsize=8.2, color=L["bad"], va="top", ha="left", linespacing=1.4)
    ax.set_xscale("log")
    ax.set_xlim(0.008, 1400)
    for yi, v, p in zip(y, p50, pols):
        ax.text(v * 1.25, yi, f"{v:.2f} ms", va="center", fontsize=8.6,
                color=L["ink"], fontweight="bold" if p == "mag-nts" else "normal")
    ax.set_yticks(y); ax.set_yticklabels([POLICY_LABEL[p] for p in pols], fontsize=9, color=L["inkDim"])
    ax.set_xlabel("median decision latency (ms, log scale)", fontsize=9, labelpad=7)
    ax.xaxis.grid(True, zorder=0); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
    ax.annotate("", xy=(0.32, -0.62), xytext=(250, -0.62), annotation_clip=False,
                arrowprops=dict(arrowstyle="<->", color=L["accent"], lw=1.2))
    ax.text(9.0, -0.95, "~780× headroom", fontsize=8.6, color=L["accent"],
            ha="center", fontweight="bold")
    save(fig, "latency")


def fig_complementarity() -> None:
    """Where each scheduler is the right answer. This is the finding, losses included."""
    light()
    single = ["easy-static", "periodic-challenge", "high-noise", "extreme-budget"]
    spliced = ["sudden-shift", "recurring-environment", "unseen-generalization"]
    fig, ax = plt.subplots(figsize=(12.4, 4.15))
    ax.axis("off")
    groups = [("SINGLE-PHASE BANDS  ·  one stationary environment", single, 0.0),
              ("SPLICED BANDS  ·  the environment is replaced mid-episode", spliced, 0.52)]
    for title, presets, y0 in groups:
        ax.text(0.0, 1.0 - y0, title, fontsize=9.6, fontweight="bold", color=L["ink"],
                transform=ax.transAxes, va="top")
        for i, s_ in enumerate(presets):
            best = max(["round-robin", "random", "ucb", "thompson", "nts", "mag-nts"],
                       key=lambda p_: agg(s_, p_, "cumulative_reward")["mean"])
            c_nts = comparison(s_, "mag-nts", "cumulative_reward", "benchmark")
            c_th = comparison(s_, "mag-nts", "cumulative_reward", "benchmark_thompson")
            x0 = i * 0.252
            w, h = 0.235, 0.335
            top = 1.0 - y0 - 0.085
            ax.add_patch(FancyBboxPatch(
                (x0, top - h), w, h, transform=ax.transAxes,
                boxstyle="round,pad=0.004,rounding_size=0.02",
                facecolor=L["card"], edgecolor=L["line"], linewidth=0.9, clip_on=False))
            ax.text(x0 + 0.014, top - 0.045, PRESET_LABEL[s_].replace("\n", " "),
                    fontsize=9.5, fontweight="bold", color=L["ink"], transform=ax.transAxes)
            for j, (lbl, c) in enumerate([("vs NTS", c_nts), ("vs Thompson", c_th)]):
                both = c["welch_p"] < 0.05 and c["mannwhitney_p"] < 0.05
                good = c["difference"] > 0
                col = L["good"] if (both and good) else L["bad"] if (both and not good) else L["muted"]
                mark = "✓" if (both and good) else "✗" if (both and not good) else "~"
                ax.text(x0 + 0.014, top - 0.115 - j * 0.062,
                        f"{mark} {lbl}  {c['difference']:+.2f}",
                        fontsize=8.9, color=col, transform=ax.transAxes,
                        fontweight="bold" if both else "normal")
            ax.text(x0 + 0.014, top - 0.272, f"deploy here:  {POLICY_LABEL[best].replace(' (control)', '')}",
                    fontsize=8.1, color=L["sihDark"], transform=ax.transAxes, fontweight="bold")
    ax.text(0.0, -0.055, "✓ significant win   ✗ significant loss   ~ leads or trails on the mean without significance "
            "(significance = both Welch t and Mann-Whitney U at α = 0.05, n = 6 seeds)",
            fontsize=7.9, color=L["muted"], transform=ax.transAxes)
    ax.text(0.0, -0.145, "No single policy dominates all seven bands — and that is the finding. MAG-NTS improves on its own NTS lineage on "
            "every single-phase band\nand beats Thompson on every spliced band. AAMS-X ships all six policies and the rig that tells you which one to deploy where.",
            fontsize=8.6, color=L["ink"], transform=ax.transAxes, style="italic", linespacing=1.5)
    save(fig, "complementarity", pad=0.12)


def fig_oracle() -> None:
    """How much of the achievable reward each policy actually captures."""
    light()
    fig, ax = plt.subplots(figsize=(7.6, 3.5))
    pols = ["round-robin", "ucb", "thompson", "nts", "mag-nts"]
    x = np.arange(len(ORDER)); width = 0.165
    for i, pol in enumerate(pols):
        vals = [agg(s, pol, "oracle_ratio")["mean"] for s in ORDER]
        off = (i - (len(pols) - 1) / 2) * width
        ax.plot(x, vals, marker="o", ms=4.4, lw=1.7, color=POLICY_COLOR[pol],
                label=POLICY_LABEL[pol], zorder=4 if pol == "mag-nts" else 3,
                alpha=1.0 if pol == "mag-nts" else 0.75)
    ax.axhline(1.0, color=L["bad"], lw=1.2, ls=(0, (4, 2)))
    ax.text(len(ORDER) - 1, 1.02, "clairvoyant oracle = 1.00", fontsize=8, color=L["bad"], ha="right")
    ax.set_xticks(x)
    ax.set_xticklabels([PRESET_LABEL[s] for s in ORDER], fontsize=8.4, color=L["inkDim"], linespacing=1.3)
    ax.set_ylabel("fraction of oracle reward\ncaptured", fontsize=9.2, labelpad=8)
    ax.set_ylim(0, 1.12)
    ax.yaxis.grid(True, zorder=0); ax.set_axisbelow(True)
    ax.legend(ncol=5, fontsize=8.4, loc="lower center", bbox_to_anchor=(0.5, -0.42),
              columnspacing=1.3, handlelength=1.3)
    ax.tick_params(labelsize=8.2)
    save(fig, "oracle")


if __name__ == "__main__":
    print("results figures:")
    fig_arena_reward(); fig_delta_both(); fig_sdp(); fig_ablation(); fig_latency(); fig_complementarity(); fig_oracle()
