"""Diagram and product-render figures for the AAMS-X SIH deck."""
from __future__ import annotations
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch, Circle, Rectangle, Wedge

from figstyle import (ASSETS, L, P, CM_SPECTRUM, CM_BELIEF, light, dark, save, station)


def _spectro(ax, name: str, *, t0: int = 0, t1: int = 1200, gamma: float = 0.62,
             lo_pct: float = 45.0, hi_pct: float = 99.2):
    """Draw a real recording the way the product's waterfall draws it.

    The top and bottom channels of an e-CALLISTO receiver carry a periodic calibration
    marker that saturates any linear scale, so the display range is taken from the
    interior channels only; the mild gamma matches SPECTRUM_STOPS in palette.ts, which
    expands the low end because real margins sit within a few dB of the threshold.
    """
    z, meta = station(name)
    ex = np.array(z["excess"][t0:t1], dtype=np.float32)
    freq = np.array(z["freq"], dtype=np.float32)
    interior = ex[:, 3:-3]
    lo, hi = np.percentile(interior, [lo_pct, hi_pct])
    norm = np.clip((ex - lo) / max(hi - lo, 1e-6), 0.0, 1.0) ** gamma
    ax.imshow(norm.T, aspect="auto", origin="lower", cmap=CM_SPECTRUM, vmin=0.0, vmax=1.0,
              extent=[0, ex.shape[0], freq[0], freq[-1]], interpolation="nearest")
    return z, meta, ex, freq


def fig_problem_aperture() -> None:
    """The hero visual: a real wide band, and the sliver a receiver can actually hear."""
    dark()
    fig = plt.figure(figsize=(12.8, 4.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[2.42, 1.0], wspace=0.10)

    ax = fig.add_subplot(gs[0, 0])
    z, meta, ex, freq = _spectro(ax, "MRO", t0=0, t1=1200)
    span = (freq[-1] - freq[0]) / 12.0
    for i, (t0, f0) in enumerate([(60, 120.0), (330, 520.0), (620, 250.0), (900, 700.0)]):
        ax.add_patch(Rectangle((t0, f0), 200, span, fill=False, edgecolor=P["warn"],
                               linewidth=1.6, zorder=6))
        ax.text(t0 + 100, f0 + span + 30, f"dwell {i + 1}", ha="center", fontsize=8.0,
                color=P["warn"], fontweight="bold")
    ax.set_ylabel("frequency (MHz)", fontsize=9.6, color=P["inkDim"])
    ax.set_xlabel("time  →   300 s of a real recording at 0.25 s cadence", fontsize=9.6, color=P["inkDim"])
    ax.set_title("REAL SPECTRUM  ·  MRO, Murchison (Australia)  ·  50–846 MHz  ·  200 channels  ·  no simulator",
                 fontsize=10.0, color=P["accent"], fontweight="bold", loc="left", pad=9)
    ax.tick_params(labelsize=8.4)
    for sp in ax.spines.values():
        sp.set_color(P["line"]); sp.set_visible(True)

    ax2 = fig.add_subplot(gs[0, 1])
    ax2.axis("off"); ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    ax2.text(0.02, 0.99, "THE CONSTRAINT", fontsize=10.4, color=P["warn"],
             fontweight="bold", va="top")
    stats = [("48", "regions in the band"),
             ("4", "audible per dwell"),
             ("8%", "of the band, at any instant"),
             ("1200", "decisions per episode")]
    y = 0.845
    for big, small in stats:
        ax2.add_patch(FancyBboxPatch((0.02, y - 0.145), 0.96, 0.135, transform=ax2.transAxes,
                                     boxstyle="round,pad=0.004,rounding_size=0.06",
                                     facecolor=P["panel"], edgecolor=P["line"], linewidth=0.9))
        ax2.text(0.075, y - 0.077, big, fontsize=19, color=P["accent"], fontweight="bold",
                 va="center", ha="left")
        ax2.text(0.44, y - 0.077, small, fontsize=9.2, color=P["inkDim"], va="center", ha="left")
        y -= 0.165
    ax2.add_patch(FancyBboxPatch((0.02, 0.005), 0.96, 0.185, transform=ax2.transAxes,
                                 boxstyle="round,pad=0.008,rounding_size=0.05",
                                 facecolor="#0d1f22", edgecolor=P["accentDim"], linewidth=1.1))
    ax2.text(0.055, 0.155, "Every dwell is a choice — and the band\nkeeps changing while you are looking\nsomewhere else.",
             fontsize=9.0, color=P["accent"], va="top", linespacing=1.65, style="italic")
    save(fig, "problem_aperture", pad=0.10)


LOOP = [
    ("Observe", "dwell on the chosen\nwindow, real samples"),
    ("Encode", "temporal features,\nno truth handle"),
    ("Infer", "Beta posterior per\nregion, discounted"),
    ("Remember", "bounded associative\nmemory, 24 prototypes"),
    ("Quantify", "aleatoric + epistemic\nuncertainty"),
    ("Predict", "periodicity phase &\nchange detector"),
    ("Value", "IG(a) = H(b) − E[H(b′)|a]"),
    ("Select", "8-term additive score\nunder Σc(aₜ) ≤ B"),
    ("Feedback", "hit / miss / cost\nback into the belief"),
    ("Adapt", "re-weight, discount,\nboost exploration"),
]


def fig_closed_loop() -> None:
    """The ten-stage loop, drawn as the ring it actually is."""
    light()
    fig, ax = plt.subplots(figsize=(8.4, 8.0))
    ax.set_xlim(-1.34, 1.34); ax.set_ylim(-1.34, 1.34)
    ax.axis("off"); ax.set_aspect("equal")
    n = len(LOOP)
    r = 0.97
    hues = [L["signal"], L["signal"], L["accent"], L["mag"], L["warn"],
            L["mag"], L["accent"], L["sih"], L["good"], L["accent"]]
    ax.add_patch(Circle((0, 0), r, fill=False, edgecolor=L["line"], lw=1.1, ls=(0, (2, 3))))
    for i, (name, sub) in enumerate(LOOP):
        a = np.pi / 2 - i * 2 * np.pi / n
        x, y = r * np.cos(a), r * np.sin(a)
        ax.add_patch(Circle((x, y), 0.135, facecolor="white", edgecolor=hues[i], lw=2.0, zorder=5))
        ax.text(x, y + 0.012, str(i + 1), ha="center", va="center", fontsize=12.5,
                color=hues[i], fontweight="bold", zorder=6)
        # label outside the ring, radially
        lx, ly = 1.20 * np.cos(a), 1.20 * np.sin(a)
        ha = "center"
        if abs(np.cos(a)) > 0.30:
            ha = "left" if np.cos(a) > 0 else "right"
        ax.text(lx, ly + 0.045, name, ha=ha, va="center", fontsize=11.4,
                color=L["ink"], fontweight="bold")
        ax.text(lx, ly - 0.075, sub, ha=ha, va="center", fontsize=7.5,
                color=L["muted"], linespacing=1.45)
        # arc arrow to the next node
        a2 = np.pi / 2 - (i + 1) * 2 * np.pi / n
        ax.add_patch(FancyArrowPatch(
            (0.845 * np.cos(a + 0.20), 0.845 * np.sin(a + 0.20)),
            (0.845 * np.cos(a2 - 0.20), 0.845 * np.sin(a2 - 0.20)),
            connectionstyle="arc3,rad=-0.22", arrowstyle="-|>,head_width=3.4,head_length=6",
            color=L["lineSoft"], lw=1.5, zorder=2, mutation_scale=1.0))
    ax.add_patch(Circle((0, 0), 0.535, facecolor=L["card"], edgecolor=L["line"], lw=1.0, zorder=3))
    ax.text(0, 0.185, "MAG-NTS", ha="center", fontsize=17.5, color=L["mag"],
            fontweight="bold", zorder=4)
    ax.text(0, 0.055, "Memory-Augmented,\nInformation-Guided,\nNon-Stationary\nThompson Sampling",
            ha="center", va="top", fontsize=8.6, color=L["inkDim"], linespacing=1.6, zorder=4)
    ax.text(0, -0.335, "explainable by construction", ha="center", fontsize=8.0,
            color=L["accent"], style="italic", zorder=4)
    ax.text(0, -0.44, "no black box · no truth leak", ha="center", fontsize=7.4,
            color=L["muted"], zorder=4)
    save(fig, "closed_loop", pad=0.02)


def fig_decision_score() -> None:
    """A real decision, decomposed. Values are a captured frame, not an illustration."""
    light()
    ep = json.loads((ASSETS / "ep_high-noise__mag-nts__s0.json").read_text())
    frame = ep["sample_frames"][2]
    f = frame["factors"]
    rows = [
        ("Detection", "detection", "sampled activity rate, discounted posterior", 0.94, "predicted_activity"),
        ("Memory", "memory", "retrieved preference × context similarity", 0.57, "memory_similarity"),
        ("Uncertainty", "uncertainty", "posterior + epistemic, gated by change state", 0.23, "uncertainty"),
        ("Information", "information", "expected entropy reduction, in bits", 0.07, "information_gain"),
        ("Recency", "recency", "how stale this region has become", 0.17, "staleness"),
        ("Periodicity", "periodicity", "phase-conditional recurrence lift", 0.27, "periodicity_score"),
        ("Cost", "cost", "sensing and retuning cost", 0.29, "sensing_cost"),
        ("Switching", "switching", "distance moved across the band", 0.10, "switching_penalty"),
    ]
    fig, ax = plt.subplots(figsize=(11.2, 4.35))
    y = np.arange(len(rows))[::-1]
    vals = [f[f"contribution.{k}"] for _, k, _, _, _ in rows]
    cols = [L["good"] if v > 0 else L["bad"] for v in vals]
    ax.barh(y, vals, 0.58, color=cols, zorder=3)
    ax.axvline(0, color=L["ink"], lw=1.1, zorder=4)
    total = frame["action_value"]
    for yi, (label, key, blurb, w, ev), v in zip(y, rows, vals):
        side = 1 if v >= 0 else -1
        ax.text(v + side * 0.014, yi + 0.055, f"{v:+.3f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=9.6, fontweight="bold",
                color=L["good"] if v > 0 else L["bad"])
        ax.text(v + side * 0.014, yi - 0.27, f"w = {w:.2f}  ×  {ev} = {f[ev]:.3f}",
                va="center", ha="left" if v >= 0 else "right", fontsize=6.7, color=L["muted"])
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10.2, color=L["ink"], fontweight="bold")
    ax.set_xlim(-0.40, 0.72)
    ax.set_xlabel("contribution to the action value of the chosen window", fontsize=9.4, labelpad=7)
    ax.xaxis.grid(True, zorder=0); ax.set_axisbelow(True)
    ax.spines["left"].set_visible(False); ax.tick_params(axis="y", length=0)
    ax.add_patch(FancyBboxPatch((0.452, -0.66), 0.262, 2.05, transform=ax.transData,
                                boxstyle="round,pad=0.012,rounding_size=0.03",
                                facecolor=L["card"], edgecolor=L["mag"], linewidth=1.3, clip_on=False))
    ax.text(0.583, 1.08, "action value", ha="center", fontsize=8.6, color=L["inkDim"])
    ax.text(0.583, 0.44, f"{total:.3f}", ha="center", fontsize=20, color=L["mag"], fontweight="bold")
    ax.text(0.583, -0.34, "= exact sum of the\neight terms above", ha="center", fontsize=7.6,
            color=L["muted"], linespacing=1.4)
    note = frame["notes"][0] if frame["notes"] else ""
    mem = frame["memory"]
    ax.set_title(f'Step {frame["step"]} of a real high-noise episode  ·  "{note}"',
                 fontsize=10.6, fontweight="bold", color=L["ink"], loc="left", pad=11)
    fig.text(0.5, -0.055, f'prototype #{mem["prototype_id"]} · {mem["visits"]} visits · label "{mem["label"]}" · '
             f'Hopfield top-3 weights {mem["top_weights"]}  —  captured from the same code path the Decision Inspector renders',
             ha="center", fontsize=7.5, color=L["muted"])
    save(fig, "decision_score")


STATIONS = [
    # (name, label, country, continent, lat, lon, band, occupancy, role, span)
    ("INDIA-GAURI", "Gauribidanur", "India", "Asia", 13.6, 77.4, "30–90 MHz", 0.0619, "train", 59.9),
    ("SWISS-Landschlacht", "Landschlacht", "Switzerland", "Europe", 47.6, 9.2, "45–175 MHz", None, "train", 129.6),
    ("EGYPT-Alexandria", "Alexandria", "Egypt", "Africa", 31.2, 29.9, "45–165 MHz", None, "validation", 119.9),
    ("MRO", "Murchison", "Australia", "Oceania", -26.7, 116.7, "50–846 MHz", None, "unseen", 796.2),
    ("AUSTRIA-OE3FLB", "OE3FLB", "Austria", "Europe", 48.1, 15.6, "112–747 MHz", None, "unseen", 635.2),
    ("SSRT", "Badary", "Russia", "Asia", 51.8, 102.2, "45–441 MHz", None, "unseen", 396.1),
    ("SWISS-MUHEN", "Muhen", "Switzerland", "Europe", 47.3, 8.1, "15–87 MHz", None, "unseen", 71.9),
]
ROLE_COLOR = {"train": None, "validation": None, "unseen": None}


def fig_stations() -> None:
    """Where the data comes from, and how the train / validation / unseen split falls."""
    light()
    ROLE_COLOR.update(train=L["accent"], validation=L["warn"], unseen=L["mag"])
    fig = plt.figure(figsize=(12.6, 4.5))
    gs = fig.add_gridspec(1, 2, width_ratios=[1.42, 1.0], wspace=0.11)

    ax = fig.add_subplot(gs[0, 0])
    ax.set_xlim(-180, 180); ax.set_ylim(-58, 78)
    ax.set_facecolor(L["card"])
    for lon in range(-180, 181, 30):
        ax.axvline(lon, color=L["line"], lw=0.5, alpha=0.7, zorder=1)
    for lat in range(-60, 91, 30):
        ax.axhline(lat, color=L["line"], lw=0.5, alpha=0.7, zorder=1)
    ax.axhline(0, color=L["lineSoft"], lw=1.3, zorder=1)
    ax.text(-176, 2.5, "equator", fontsize=6.6, color=L["faint"])
    for label, lon, lat in [("EUROPE", -18, 56), ("AFRICA", 20, -12), ("ASIA", 95, 68),
                            ("OCEANIA", 150, -46), ("AMERICAS", -80, 20)]:
        ax.text(lon, lat, label, fontsize=7.6, color=L["faint"], ha="center",
                fontweight="bold", alpha=0.85, zorder=2)
    # explicit label offsets: the three European sites sit within a few degrees of each
    # other, so their labels are fanned out and joined by leader lines.
    LABEL_DY = {"SWISS-Landschlacht": 16.0, "SWISS-MUHEN": -2.0, "AUSTRIA-OE3FLB": 7.0,
                "EGYPT-Alexandria": -13.0, "MRO": 8.0, "SSRT": 6.0, "INDIA-GAURI": 0.0}
    LABEL_SIDE = {"EGYPT-Alexandria": -1}
    for name, city, country, cont, lat, lon, band, occ, role, span in STATIONS:
        c = ROLE_COLOR[role]
        ax.scatter([lon], [lat], s=118, color=c, edgecolor="white", linewidth=1.5, zorder=6)
        ax.scatter([lon], [lat], s=330, color=c, alpha=0.16, zorder=5)
        dy = LABEL_DY[name]
        side = LABEL_SIDE.get(name, 1)
        lx, ly = lon + 8.5 * side, lat + dy
        ha = "left" if side > 0 else "right"
        if abs(dy) > 3:
            ax.plot([lon, lx - 1.5 * side], [lat, ly], color=c, lw=0.9, alpha=0.75, zorder=4)
        ax.text(lx, ly, name, fontsize=7.5, color=L["ink"], va="center", ha=ha,
                fontweight="bold", zorder=7)
        ax.text(lx, ly - 6.2, f"{band}  ·  {cont}", fontsize=6.4, color=L["muted"],
                va="center", ha=ha, zorder=7)
    ax.set_xticks([]); ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_visible(True); sp.set_color(L["line"])
    ax.set_title("7 public e-CALLISTO receivers  ·  4 continents  ·  139 MB cached on disk",
                 fontsize=10.4, fontweight="bold", color=L["ink"], loc="left", pad=9)
    handles = [plt.Line2D([], [], marker="o", ls="", ms=8, color=ROLE_COLOR[r],
                          label=f"{r}") for r in ("train", "validation", "unseen")]
    ax.legend(handles=handles, ncol=3, fontsize=8.4, loc="lower left",
              bbox_to_anchor=(0.0, -0.10), handletextpad=0.3, columnspacing=1.4)
    ax.text(1.0, -0.10, "positions plotted from published site coordinates — schematic graticule, not a survey map",
            transform=ax.transAxes, ha="right", fontsize=6.8, color=L["muted"])

    ax2 = fig.add_subplot(gs[0, 1]); ax2.axis("off")
    ax2.set_xlim(0, 1); ax2.set_ylim(0, 1)
    ax2.text(0.0, 1.0, "THE SPLIT IS THE GUARANTEE", fontsize=10.2, color=L["ink"],
             fontweight="bold", va="top")
    blocks = [
        (L["accent"], "TRAIN  ·  2 receivers",
         "MAG-NTS weights tuned here only.\n45 candidates, winner win-rate 1.0,\nadvantage +28.57 reward."),
        (L["warn"], "VALIDATION  ·  1 receiver",
         "Distribution-shift splices.\nNever used to pick a weight."),
        (L["mag"], "UNSEEN  ·  4 receivers",
         "Touched once, at the end.\nOne preset, one family — asserted by\ntest_only_the_held_out_preset_…"),
    ]
    y = 0.865
    for colour, head, body in blocks:
        ax2.add_patch(FancyBboxPatch((0.0, y - 0.245), 1.0, 0.228, transform=ax2.transAxes,
                                     boxstyle="round,pad=0.006,rounding_size=0.035",
                                     facecolor=L["card"], edgecolor=colour, linewidth=1.2))
        ax2.add_patch(Rectangle((0.0, y - 0.245), 0.012, 0.228, transform=ax2.transAxes,
                                facecolor=colour, edgecolor="none"))
        ax2.text(0.042, y - 0.048, head, fontsize=9.2, color=colour, fontweight="bold", va="top")
        ax2.text(0.042, y - 0.108, body, fontsize=7.9, color=L["inkDim"], va="top", linespacing=1.5)
        y -= 0.262
    ax2.text(0.0, 0.055, "The unseen result is a loss.\nIf we had tuned on it, it would not be.",
             fontsize=9.0, color=L["bad"], va="top", style="italic", linespacing=1.5)
    save(fig, "stations", pad=0.10)


ARCH = [
    ("PRESENTATION", L["signal"], "React 19 · TypeScript 5.9 · Vite 8 · Tailwind 4 · ECharts 6 · three.js + R3F · framer-motion",
     ["13 screens", "live WebSocket waterfall", "Decision Inspector", "Demo Mode (projector)"]),
    ("SERVICE", L["accent"], "FastAPI · Pydantic v2 · Uvicorn — 24 HTTP routes + 1 WebSocket, OpenAPI generated",
     ["/experiments arena · ablation", "/datasets spectrogram + provenance", "/reports self-contained HTML", "replay by config hash"]),
    ("SCHEDULING", L["mag"], "MAG-NTS + 5 classical baselines · optional DQN behind a Torch extra",
     ["8-term additive score", "change · memory · budget gating", "Σc(aₜ) ≤ B enforced", "no handle on the truth array"]),
    ("COGNITION", L["warn"], "belief · memory · information_gain · change_detection · periodicity · features",
     ["Beta posterior, decay per step", "24-prototype modern Hopfield, β = 12", "IG(a) = H(b) − E[H(b′)|a]", "Page-Hinkley + EWMA detector"]),
    ("EVALUATION", L["good"], "metrics · statistics · pareto · reward · events — 13 metrics per arm",
     ["Welch t AND Mann-Whitney U", "Student-t 95% CI, 6 seeds", "4-objective Pareto frontier", "oracle & pseudo-regret"]),
    ("DATA", L["sihDark"], "e-CALLISTO adapter · SigMF · FITS · ElectroSense · DuckDB window index",
     ["139 MB, 7 receivers, 4 continents", "uint8 digits → excess dB", "per-file provenance + checksum", "is_synthetic: false, always"]),
]


def fig_architecture() -> None:
    """Six layers, named modules, real dependency versions."""
    light()
    fig, ax = plt.subplots(figsize=(12.4, 6.35))
    ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")
    h = 0.147
    gap = 0.018
    y = 1.0 - h
    for name, colour, stack, bullets in ARCH:
        ax.add_patch(FancyBboxPatch((0.0, y), 0.795, h, transform=ax.transAxes,
                                    boxstyle="round,pad=0.003,rounding_size=0.02",
                                    facecolor=L["card"], edgecolor=L["line"], linewidth=0.9))
        ax.add_patch(Rectangle((0.0, y), 0.0085, h, transform=ax.transAxes,
                               facecolor=colour, edgecolor="none"))
        ax.text(0.024, y + h - 0.032, name, fontsize=10.4, color=colour, fontweight="bold", va="center")
        ax.text(0.024, y + h - 0.072, stack, fontsize=7.4, color=L["muted"], va="center")
        for j, b in enumerate(bullets):
            bx = 0.024 + (j % 2) * 0.395
            by = y + 0.048 - (j // 2) * 0.036
            ax.text(bx, by, f"▸ {b}", fontsize=7.6, color=L["inkDim"], va="center")
        y -= h + gap
    # the sealed boundary: the one architectural claim worth drawing
    ax.annotate("", xy=(0.815, 0.585), xytext=(0.815, 0.235), annotation_clip=False,
                arrowprops=dict(arrowstyle="-", color=L["bad"], lw=2.0))
    ax.add_patch(FancyBboxPatch((0.828, 0.228), 0.172, 0.357, transform=ax.transAxes,
                                boxstyle="round,pad=0.006,rounding_size=0.03",
                                facecolor="#fdf1f1", edgecolor=L["bad"], linewidth=1.2))
    ax.text(0.845, 0.556, "SEALED BOUNDARY", fontsize=9.0, color=L["bad"],
            fontweight="bold", va="top")
    ax.text(0.845, 0.512, "The scheduler receives a\nfrozen DecisionContext —\nnever the truth array.\n\nLeakage raises a\nLeakageError: a test\nfailure, not a\ncode-review question.",
            fontsize=7.2, color=L["bad"], va="top", linespacing=1.55)
    ax.add_patch(FancyBboxPatch((0.828, 0.615), 0.172, 0.30, transform=ax.transAxes,
                                boxstyle="round,pad=0.006,rounding_size=0.03",
                                facecolor=L["card2"], edgecolor=L["line"], linewidth=1.0))
    ax.text(0.845, 0.885, "AT A GLANCE", fontsize=9.2, color=L["ink"], fontweight="bold", va="top")
    for j, (k, v) in enumerate([("Python modules", "72"), ("lines of Python", "12,007"),
                                ("tests collected", "507"), ("TS/TSX files", "59"),
                                ("lines of frontend", "14,910"), ("GPU required", "none")]):
        ax.text(0.845, 0.822 - j * 0.037, k, fontsize=7.2, color=L["muted"], va="center")
        ax.text(0.992, 0.822 - j * 0.037, v, fontsize=7.6, color=L["ink"],
                va="center", ha="right", fontweight="bold")
    ax.add_patch(FancyBboxPatch((0.828, 0.012), 0.172, 0.196, transform=ax.transAxes,
                                boxstyle="round,pad=0.006,rounding_size=0.03",
                                facecolor="#eef7f6", edgecolor=L["accent"], linewidth=1.0))
    ax.text(0.845, 0.183, "RUNS OFFLINE", fontsize=9.0, color=L["accent"],
            fontweight="bold", va="top")
    ax.text(0.845, 0.134, "network_allowed: false.\nThe archive is fetched\nonce; the demo needs\nno connection at all.",
            fontsize=7.2, color="#0f6b64", va="top", linespacing=1.55)
    save(fig, "architecture", pad=0.06)
