"""Approximate renderer for a .pptx, so slide layout can actually be looked at.

LibreOffice is not installed on this machine, so there is no true renderer. This
draws each slide from python-pptx geometry: pictures at their real placement,
autoshapes as filled rectangles, and every run of text wrapped at the box width
using matplotlib's own font metrics. It is not pixel-accurate against PowerPoint,
but it is accurate enough to catch the two defects that matter — text that
overflows its box, and shapes that collide.
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle
from pptx import Presentation
from pptx.util import Emu

EMU_IN = 914400
DPI = 132


def _hex(color_fmt):
    try:
        return "#%02x%02x%02x" % tuple(color_fmt.rgb)
    except Exception:
        return None


def fill_of(sh):
    try:
        if sh.fill.type is None:
            return None
        if sh.fill.type == 5:            # background / none
            return None
        return _hex(sh.fill.fore_color)
    except Exception:
        return None


def line_of(sh):
    try:
        if sh.line.fill.type in (None, 5):
            return None
        return _hex(sh.line.color)
    except Exception:
        return None


def wrap(ax, fig, text, size_pt, box_w_in, bold, italic):
    """Greedy wrap using rendered widths, so overflow is real overflow."""
    if not text:
        return [""]
    renderer = fig.canvas.get_renderer()
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        t = ax.text(0, 0, trial, fontsize=size_pt, fontweight="bold" if bold else "normal",
                    fontstyle="italic" if italic else "normal")
        bb = t.get_window_extent(renderer=renderer)
        t.remove()
        if bb.width / fig.dpi > box_w_in and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    lines.append(cur)
    return lines


def draw_slide(prs, slide, index, out: Path):
    W, H = Emu(prs.slide_width).inches, Emu(prs.slide_height).inches
    fig = plt.figure(figsize=(W, H), dpi=DPI)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    ax.add_patch(Rectangle((0, 0), W, H, facecolor="white", edgecolor="none", zorder=-10))
    fig.canvas.draw()

    for sh in slide.shapes:
        if sh.left is None:
            continue
        x, y = Emu(sh.left).inches, Emu(sh.top).inches
        w, h = Emu(sh.width).inches, Emu(sh.height).inches
        st = str(sh.shape_type)
        if "PICTURE" in st:
            try:
                import io
                from PIL import Image
                im = Image.open(io.BytesIO(sh.image.blob)).convert("RGB")
                ax.imshow(im, extent=(x, x + w, y + h, y), zorder=2, aspect="auto")
            except Exception:
                ax.add_patch(Rectangle((x, y), w, h, facecolor="#dddddd", zorder=2))
            continue
        fc, ec = fill_of(sh), line_of(sh)
        if fc or ec:
            ax.add_patch(FancyBboxPatch(
                (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.04",
                facecolor=fc or "none", edgecolor=ec or "none",
                linewidth=0.8, zorder=1))
        if not sh.has_text_frame:
            continue
        tf = sh.text_frame
        pad_l = Emu(tf.margin_left).inches if tf.margin_left else 0
        pad_t = Emu(tf.margin_top).inches if tf.margin_top else 0
        anchor = str(tf.vertical_anchor)
        # Lay paragraphs out top-down; measure the total so overflow is visible.
        blocks = []
        for p in tf.paragraphs:
            runs = [(r.text, (r.font.size.pt if r.font.size else 12),
                     bool(r.font.bold), bool(r.font.italic),
                     _hex(r.font.color) or "#222222") for r in p.runs if r.text]
            if not runs:
                blocks.append((None, (p.space_before.pt if p.space_before else 0)
                               + 6, 0, "l", None))
                continue
            size = max(r[1] for r in runs)
            joined = "".join(r[0] for r in runs)
            lines = wrap(ax, fig, joined, size, max(w - 2 * pad_l - 0.03, 0.3),
                         runs[0][2], runs[0][3])
            ls = (p.line_spacing or 1.0)
            ls = ls if ls > 0.2 else 1.0
            al = {"CENTER (2)": "c", "RIGHT (3)": "r"}.get(str(p.alignment), "l")
            blocks.append((lines, (p.space_before.pt if p.space_before else 0),
                           size, al, runs[0][4], size * ls * 1.30 / 72.0))
        total = sum((b[1] / 72.0 + (len(b[0]) * b[5] if b[0] else 0.0))
                    for b in blocks if len(b) > 5)
        cy = y + pad_t
        if "MIDDLE" in anchor:
            cy = y + max((h - total) / 2, 0)
        for b in blocks:
            if len(b) <= 5:
                cy += b[1] / 72.0
                continue
            lines, sb, size, al, col, lh = b
            cy += sb / 72.0
            for ln in lines:
                tx = x + pad_l
                ha = "left"
                if al == "c":
                    tx, ha = x + w / 2, "center"
                elif al == "r":
                    tx, ha = x + w - pad_l, "right"
                ax.text(tx, cy + lh * 0.78, ln, fontsize=size, color=col, ha=ha,
                        va="baseline", zorder=6,
                        fontweight="bold" if b[0] and lines and False else "normal")
                cy += lh
        if cy > y + h + 0.02 and any(t.strip() for t, *_ in [(pp.text,) for pp in tf.paragraphs]):
            ax.add_patch(Rectangle((x, y), w, h, facecolor="none", edgecolor="#ff00ff",
                                   linewidth=1.4, linestyle=":", zorder=9))
            print(f"  slide {index}: OVERFLOW {sh.name!r} box h={h:.2f} needs {cy - y:.2f}")

    fig.savefig(out, dpi=DPI)
    plt.close(fig)


def main(path: str, outdir: str):
    prs = Presentation(path)
    od = Path(outdir)
    od.mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(prs.slides, 1):
        draw_slide(prs, s, i, od / f"slide{i}.png")
    print("rendered", len(list(prs.slides)), "slides to", od)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
