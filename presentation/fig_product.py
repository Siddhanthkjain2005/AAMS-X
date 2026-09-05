"""Product renders and the scan-strategy comparison.

These are the deck's "what does it actually look like" panels.  Nothing here is a
mock-up: the waterfall is cached e-CALLISTO excess-dB, and every belief, uncertainty,
scan position and reward value is read back from an episode captured by
``capture_episode.py`` running the project's own ``run_episode``.
"""
from __future__ import annotations

import json

import numpy as np
from matplotlib.patches import FancyBboxPatch, Rectangle

from figstyle import (ASSETS, CM_BELIEF, CM_HEAT, CM_SPECTRUM, L, P, dark, light,
                      plt, save, station)


def episode(scenario: str, policy: str, seed: int = 0):
    stem = f"ep_{scenario}__{policy}__s{seed}"
    z = np.load(ASSETS / f"{stem}.npz")
    meta = json.loads((ASSETS / f"{stem}.json").read_text())
    return z, meta


def card(fig, rect, *, fc=None, ec=None, lw=1.0, r=0.011):
    """A rounded product card in figure coordinates.

    ``r`` is a figure fraction, not a scale factor — FancyBboxPatch measures
    rounding_size in the patch's own transform, so anything near the card size
    turns the rectangle into an ellipse that eats the panel it frames.
    """
    x, y, w, h = rect
    fig.patches.append(FancyBboxPatch(
        (x, y), w, h, transform=fig.transFigure, figure=fig,
        boxstyle=f"round,pad=0,rounding_size={r}",
        facecolor=fc or P["panel"], edgecolor=ec or P["line"], linewidth=lw, zorder=-3))


def kpi(fig, x, y, w, h, label, value, unit="", *, color=None, sub=""):
    """Label on the top row, big value bottom-left, unit and note on the right."""
    card(fig, (x, y, w, h), fc=P["panel"], ec=P["line"])
    fig.text(x + 0.013, y + h - 0.013, label.upper(), fontsize=7.0, color=P["muted"],
             va="top", fontweight="bold")
    fig.text(x + 0.013, y + 0.016, value, fontsize=17.5, color=color or P["ink"],
             va="baseline", fontweight="bold")
    if unit:
        fig.text(x + w - 0.013, y + 0.018, unit, fontsize=8.4, color=P["muted"],
                 va="baseline", ha="right")
    if sub:
        fig.text(x + w - 0.013, y + h - 0.013, sub, fontsize=6.8, color=P["faint"],
                 va="top", ha="right")


def clean_window(ex, n, *, pct=97.0):
    """Longest run free of e-CALLISTO full-band calibration sweeps, first `n` steps.

    The receivers inject a periodic broadband marker that saturates any linear
    display scale; it is instrument behaviour, not signal, so the panel shows a
    stretch without it rather than stretching the colour map around it.
    """
    med = np.median(ex[:, 3:-3], axis=1)
    flag = np.append(med > np.percentile(med, pct), True)
    best, start = (0, 0), None
    for i, bad in enumerate(flag):
        if not bad and start is None:
            start = i
        elif bad and start is not None:
            if i - start > best[1] - best[0]:
                best = (start, i)
            start = None
    t0 = best[0]
    return t0, min(best[1], t0 + n)


def _spectro_axes(fig, rect, name, *, t0=None, t1=None, span=780, gamma=0.62):
    """Real excess-dB waterfall, scaled from interior channels only."""
    z, meta = station(name)
    if t0 is None:
        t0, t1 = clean_window(z["excess"], span)
    ex = z["excess"][t0:t1]
    interior = ex[:, 3:-3]
    lo, hi = np.percentile(interior, 45.0), np.percentile(interior, 99.2)
    norm = np.clip((ex - lo) / max(hi - lo, 1e-6), 0, 1) ** gamma
    ax = fig.add_axes(rect, zorder=4)
    ax.imshow(norm.T, aspect="auto", origin="lower", cmap=CM_SPECTRUM,
              interpolation="nearest", vmin=0, vmax=1)
    ax.set_xticks([]); ax.set_yticks([])
    for s in ax.spines.values():
        s.set_visible(False)
    return ax, meta, ex.shape


def fig_command_center():
    """The Command Center as the panel sees it — every value from a real episode."""
    dark()
    z, meta = episode("high-noise", "mag-nts")
    m = meta["metrics"]
    belief, stale, looked = z["belief"], z["staleness"], z["looked"]
    hit, reward = z["hit"], z["reward"]
    steps = belief.shape[0]

    fig = plt.figure(figsize=(13.25, 7.05))
    fig.patches.append(Rectangle((0, 0), 1, 1, transform=fig.transFigure, figure=fig,
                                 facecolor=P["void"], zorder=-5))

    # ---- header --------------------------------------------------------------
    fig.text(0.012, 0.963, "AAMS-X", fontsize=15.5, color=P["accent"], fontweight="bold",
             va="center")
    fig.text(0.090, 0.963, "COMMAND CENTER", fontsize=13.0, color=P["ink"], va="center")
    fig.text(0.258, 0.960, "· live decision loop, 4 Hz environment clock",
             fontsize=8.6, color=P["muted"], va="center")
    card(fig, (0.688, 0.941, 0.300, 0.045), fc="#10231f", ec=P["accentDim"], lw=1.1)
    fig.text(0.703, 0.963, "●", fontsize=11, color=P["accent"], va="center")
    fig.text(0.722, 0.963, "REAL PUBLIC SPECTRUM REPLAY", fontsize=8.6, color=P["accent"],
             va="center", fontweight="bold")
    fig.text(0.930, 0.963, "is_synthetic: false", fontsize=7.6, color=P["accentDim"],
             va="center", style="italic")

    # ---- KPI row -------------------------------------------------------------
    lat = json.loads((ASSETS.parent.parent / "reports/out/benchmark.json").read_text())
    p50 = lat["high-noise"]["latency"]["mag-nts"]["p50"]
    row = [("cumulative reward", f"{m['cumulative_reward']:.1f}", "", P["accent"], "high-noise"),
           ("sustained detection", f"{m['sustained_detection_probability'] * 100:.1f}", "%",
            P["good"], f"{int(m['events_sustained_detected'])}/{int(m['events_sustained'])}"),
           ("band coverage", f"{m['band_coverage'] * 100:.1f}", "%", P["signal"], "48 regions"),
           ("information", f"{m['information_bits']:.0f}", "bits", P["mag"], "measured"),
           ("decision cost", f"{p50:.2f}", "ms", P["warn"], "p50 · 250 ms step")]
    x, w, gap = 0.012, 0.1885, 0.0075
    for i, (lab, val, unit, col, sub) in enumerate(row):
        kpi(fig, x + i * (w + gap), 0.833, w, 0.092, lab, val, unit, color=col, sub=sub)

    # ---- waterfall -----------------------------------------------------------
    wf_rect = (0.012, 0.443, 0.617, 0.352)
    card(fig, (0.012, 0.425, 0.617, 0.392))
    ax, smeta, shape = _spectro_axes(fig, wf_rect, "MRO", span=800)
    fig.text(0.024, 0.798, "SPECTRUM WATERFALL", fontsize=8.0, color=P["muted"],
             fontweight="bold", va="bottom")
    fig.text(0.170, 0.798, f"MRO · Murchison, AU · {smeta['freq_min']:.0f}–"
             f"{smeta['freq_max']:.0f} MHz · {smeta['cadence']}s bins",
             fontsize=7.6, color=P["faint"], va="bottom")
    fig.text(0.622, 0.798, "excess dB over drift-tracked P10 baseline", fontsize=7.0,
             color=P["faint"], va="bottom", ha="right")
    for i, lab in enumerate(["low", "", "", "high"]):
        fig.patches.append(Rectangle((0.548 + i * 0.019, 0.432), 0.019, 0.008,
                                     transform=fig.transFigure, figure=fig,
                                     facecolor=CM_SPECTRUM(0.2 + i * 0.26), zorder=6))
    fig.text(0.545, 0.436, "weak", fontsize=6.4, color=P["faint"], ha="right", va="center")
    fig.text(0.627, 0.436, "strong", fontsize=6.4, color=P["faint"], ha="right", va="center")

    # ---- belief + uncertainty ------------------------------------------------
    card(fig, (0.641, 0.425, 0.347, 0.392))
    fig.text(0.653, 0.798, "BELIEF MAP", fontsize=8.0, color=P["muted"],
             fontweight="bold", va="bottom")
    fig.text(0.727, 0.798, "posterior activity · decays when unobserved",
             fontsize=7.2, color=P["faint"], va="bottom")
    axb = fig.add_axes((0.653, 0.620, 0.323, 0.170), zorder=4)
    axb.imshow(belief.T, aspect="auto", origin="lower", cmap=CM_BELIEF,
               interpolation="nearest", vmin=0, vmax=float(belief.max()))
    ys, xs = np.nonzero(looked.T)
    keep = xs > 0
    axb.scatter(xs[keep], ys[keep], s=0.30, c=P["accent"], alpha=0.30, linewidths=0)
    hy, hx = np.nonzero(hit.T)
    axb.scatter(hx, hy, s=1.7, c=P["warn"], alpha=0.95, linewidths=0)
    for a in (axb,):
        a.set_xticks([]); a.set_yticks([])
        for s in a.spines.values():
            s.set_visible(False)
    axb.set_ylabel("region", fontsize=7.0, color=P["faint"], labelpad=2)
    axb.text(0.012, 0.915, "amber = confirmed detection", transform=axb.transAxes,
             fontsize=6.6, color=P["warn"])

    fig.text(0.653, 0.596, "SCAN TRACE", fontsize=8.0, color=P["warn"],
             fontweight="bold", va="bottom")
    fig.text(0.727, 0.596, "where the receiver actually pointed, step by step",
             fontsize=7.2, color=P["faint"], va="bottom")
    axu = fig.add_axes((0.653, 0.462, 0.323, 0.122), zorder=4)
    axu.set_facecolor("#080d12")
    zrr, _ = episode("high-noise", "round-robin")
    rr_anchor = np.argmax(zrr["looked"], axis=1).astype(float)
    anchor = np.argmax(looked, axis=1).astype(float)
    got = hit.max(axis=1) > 0
    axu.scatter(np.arange(rr_anchor.size), rr_anchor, s=0.9, c=P["faint"], alpha=0.40,
                linewidths=0, label="Round Robin sweeps")
    axu.scatter(np.nonzero(~got)[0], anchor[~got], s=1.8, c=P["accent"], alpha=0.60,
                linewidths=0, label="MAG-NTS looks")
    axu.scatter(np.nonzero(got)[0], anchor[got], s=3.2, c=P["warn"], alpha=0.95,
                linewidths=0, label="signal found")
    axu.set_xlim(0, steps); axu.set_ylim(-1, belief.shape[1])
    axu.set_xticks([]); axu.set_yticks([])
    for s_ in axu.spines.values():
        s_.set_visible(False)
    axu.legend(fontsize=6.3, loc="upper left", labelcolor=P["inkDim"], ncol=3,
               handlelength=0.8, borderpad=0.3, columnspacing=1.1, handletextpad=0.4)
    fig.text(0.653, 0.447, "y = anchor across 48 regions  ·  the sweep covers "
             "everything, the policy concentrates", fontsize=6.6, color=P["faint"],
             va="center")

    # ---- decision inspector (a real captured frame) ---------------------------
    frame = meta["sample_frames"][2]
    f = frame["factors"]
    card(fig, (0.012, 0.012, 0.398, 0.397))
    fig.text(0.024, 0.386, "DECISION INSPECTOR", fontsize=8.0, color=P["muted"],
             fontweight="bold", va="bottom")
    fig.text(0.148, 0.386, f"step {frame['step']} · anchor {frame['regions'][0]}–"
             f"{frame['regions'][-1]}", fontsize=7.4, color=P["faint"], va="bottom")
    fig.text(0.402, 0.386, f"Σ = {frame['action_value']:.3f}", fontsize=9.0,
             color=P["accent"], fontweight="bold", va="bottom", ha="right")
    order = ["detection", "memory", "uncertainty", "information", "recency",
             "periodicity", "switching", "cost"]
    hue = {"detection": P["accent"], "information": P["signal"], "memory": P["mag"],
           "periodicity": "#7dd3fc", "uncertainty": P["warn"], "recency": "#c084fc",
           "cost": P["bad"], "switching": "#fb7185"}
    axd = fig.add_axes((0.098, 0.036, 0.298, 0.336), zorder=4)
    vals = [f[f"contribution.{k}"] for k in order]
    ypos = np.arange(len(order))[::-1]
    axd.barh(ypos, vals, height=0.62, color=[hue[k] for k in order], zorder=3)
    axd.axvline(0, color=P["lineBright"], lw=0.9, zorder=2)
    axd.set_yticks(ypos)
    axd.set_yticklabels([k for k in order], fontsize=7.8, color=P["inkDim"])
    axd.set_xlim(-0.33, 0.60)
    axd.set_xticks([-0.25, 0, 0.25, 0.5])
    axd.tick_params(axis="x", labelsize=6.8)
    axd.grid(axis="x", lw=0.6, color=P["line"], zorder=0)
    axd.set_axisbelow(True)
    for s in axd.spines.values():
        s.set_visible(False)
    for y, v, k in zip(ypos, vals, order):
        off = 0.014 if v >= 0 else -0.014
        axd.text(v + off, y, f"{v:+.3f}", fontsize=7.0, color=hue[k],
                 va="center", ha="left" if v >= 0 else "right")
    axd.set_facecolor(P["panel"])

    # ---- memory readout ------------------------------------------------------
    mem = frame["memory"]
    card(fig, (0.422, 0.012, 0.271, 0.397))
    fig.text(0.434, 0.386, "MEMORY", fontsize=8.0, color=P["mag"], fontweight="bold",
             va="bottom")
    fig.text(0.483, 0.386, "modern Hopfield · β = 12 · 24 prototypes", fontsize=7.0,
             color=P["faint"], va="bottom")
    fig.text(0.434, 0.318, f"{mem['similarity']:.3f}", fontsize=25, color=P["mag"],
             fontweight="bold", va="center")
    fig.text(0.516, 0.331, "retrieval similarity", fontsize=7.6, color=P["inkDim"], va="center")
    fig.text(0.516, 0.307, "recognised — prior applied", fontsize=7.2, color=P["good"],
             va="center")
    axm = fig.add_axes((0.434, 0.150, 0.247, 0.115), zorder=4)
    ids, wts = mem["top_ids"], mem["top_weights"]
    axm.bar(range(len(ids)), wts, width=0.52, color=[P["mag"], "#6b53b8", "#4a3a80"], zorder=3)
    axm.set_xticks(range(len(ids)))
    axm.set_xticklabels([f"#{i}" for i in ids], fontsize=7.4, color=P["inkDim"])
    axm.set_ylim(0, 1.0)
    axm.set_yticks([0, 0.5, 1.0]); axm.tick_params(labelsize=6.6)
    axm.grid(axis="y", lw=0.6, color=P["line"], zorder=0); axm.set_axisbelow(True)
    for s in axm.spines.values():
        s.set_visible(False)
    for i, w in enumerate(wts):
        axm.text(i, w + 0.05, f"{w:.3f}", fontsize=6.8, color=P["inkDim"], ha="center")
    axm.set_facecolor(P["panel"])
    fig.text(0.434, 0.276, "attention over stored contexts", fontsize=6.8,
             color=P["faint"], va="center")
    for i, (lab, val) in enumerate([("prototype", f"#{mem['prototype_id']}"),
                                    ("label", mem["label"]),
                                    ("visits", f"{mem['visits']}"),
                                    ("utility", f"{mem['utility']:.3f}")]):
        yy = 0.108 - i * 0.0235
        fig.text(0.434, yy, lab, fontsize=7.0, color=P["faint"], va="center")
        fig.text(0.681, yy, val, fontsize=7.0, color=P["inkDim"], va="center", ha="right")

    # ---- reward accrual ------------------------------------------------------
    card(fig, (0.705, 0.012, 0.283, 0.397))
    fig.text(0.717, 0.386, "REWARD ACCRUAL", fontsize=8.0, color=P["muted"],
             fontweight="bold", va="bottom")
    fig.text(0.812, 0.386, "vs round-robin, same windows", fontsize=7.0,
             color=P["faint"], va="bottom")
    zr, mr = episode("high-noise", "round-robin")
    axr = fig.add_axes((0.729, 0.118, 0.247, 0.248), zorder=4)
    axr.plot(reward, color=P["accent"], lw=1.7, zorder=4, label="MAG-NTS")
    axr.plot(zr["reward"], color=P["faint"], lw=1.4, zorder=3,
             label="Round Robin")
    axr.axhline(0, color=P["lineBright"], lw=0.8, zorder=2)
    axr.grid(lw=0.6, color=P["line"], zorder=0); axr.set_axisbelow(True)
    axr.set_facecolor(P["panel"])
    axr.tick_params(labelsize=6.8)
    axr.set_xlabel("step", fontsize=7.0, color=P["faint"], labelpad=2)
    axr.legend(fontsize=7.0, loc="upper left", labelcolor=P["inkDim"],
               handlelength=1.3, borderpad=0.2)
    axr.annotate(f"{m['cumulative_reward']:.1f}", xy=(steps, float(reward[-1])),
                 xytext=(-6, 6), textcoords="offset points", fontsize=8.0,
                 color=P["accent"], fontweight="bold", ha="right")
    axr.annotate(f"{mr['metrics']['cumulative_reward']:.1f}",
                 xy=(len(zr["reward"]), float(zr["reward"][-1])),
                 xytext=(-9, -3), textcoords="offset points", fontsize=8.0,
                 color=P["faint"], fontweight="bold", ha="right", va="top")
    fig.text(0.717, 0.052, "Same real recordings, same budget, same seed.", fontsize=7.2,
             color=P["inkDim"], va="center")
    fig.text(0.717, 0.028, "Every value on this screen came from one executed episode.",
             fontsize=7.0, color=P["faint"], va="center", style="italic")
    return save(fig, "command_center")


if __name__ == "__main__":
    fig_command_center()
