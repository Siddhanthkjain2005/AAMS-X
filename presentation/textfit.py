"""Measure text the way the slide will lay it out, so nothing overflows its box.

PowerPoint does the real wrapping, and python-pptx cannot ask it anything. So this
module wraps and measures with matplotlib's font metrics instead. DejaVu Sans runs
a few per cent wider than Arial at the same point size, which makes every estimate
here slightly pessimistic — the safe direction: a block that fits by this measure
fits in PowerPoint too.
"""
from __future__ import annotations

from functools import lru_cache

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

_FIG = plt.figure(figsize=(4, 4), dpi=100)
_AX = _FIG.add_axes((0, 0, 1, 1))
_AX.axis("off")
_FIG.canvas.draw()
_R = _FIG.canvas.get_renderer()


@lru_cache(maxsize=200000)
def _w(text: str, size: float, bold: bool) -> float:
    """Rendered width of `text` in inches at `size` pt."""
    t = _AX.text(0, 0, text, fontsize=size, fontweight="bold" if bold else "normal")
    bb = t.get_window_extent(renderer=_R)
    t.remove()
    return bb.width / 100.0


def n_lines(text: str, size: float, width_in: float, *, bold: bool = False,
            indent_in: float = 0.0) -> int:
    """Greedy line count for `text` wrapped at `width_in`, first line unindented."""
    if not text:
        return 1
    words = text.split()
    lines, cur = 1, ""
    avail = width_in
    for word in words:
        trial = (cur + " " + word).strip()
        if _w(trial, size, bold) > avail and cur:
            lines += 1
            cur = word
            avail = width_in - indent_in
        else:
            cur = trial
    return lines


def block_height(rows, *, size: float, width_in: float, gap_pt: float,
                 line: float = 0.94, indent_in: float = 0.13,
                 lead_ratio: float = 1.30) -> float:
    """Height in inches of a bulleted block: rows are (lead, rest) pairs.

    `lead_ratio` is PowerPoint's single-space line height as a multiple of the
    font size; 1.2 is the usual figure for Arial, and 1.30 keeps a margin.
    """
    lh = size * line * lead_ratio / 72.0
    total = 0.0
    for i, (lead, rest) in enumerate(rows):
        text = f"{lead}  {rest}" if lead and rest else (lead or rest)
        total += n_lines("▪  " + text, size, width_in, bold=False,
                         indent_in=indent_in) * lh
        if i:
            total += gap_pt / 72.0
    return total


def best_size(rows, *, width_in: float, height_in: float, hi: float = 10.4,
              lo: float = 6.6, gap_pt: float = 4.0, step: float = 0.2,
              line: float = 0.94) -> float:
    """Largest size in [lo, hi] whose block fits `height_in`. Returns `lo` if none do."""
    size = hi
    while size > lo:
        if block_height(rows, size=size, width_in=width_in,
                        gap_pt=max(gap_pt * size / hi, 1.6), line=line) <= height_in:
            return round(size, 2)
        size -= step
    return lo


def para_height(text: str, size: float, width_in: float, *, bold: bool = False,
                line: float = 0.95, lead_ratio: float = 1.30) -> float:
    return n_lines(text, size, width_in, bold=bold) * size * line * lead_ratio / 72.0
