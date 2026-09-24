"""Build the SIH 2026 Idea Submission deck from the provided template.

Rules taken from the template's own instruction slide: six slides maximum
including the title, points/diagrams/infographics rather than paragraphs, and the
provided template only. So this script opens the uploaded file, keeps every
master element (blue footer band, SIH logo, team oval, slide numbers), replaces
only the prompt text boxes, deletes the instruction slide, and writes to a new
path — the uploaded template is never modified.

Every number placed on a slide comes from reports/out/*.json, docs/, or a
measured property of the cached recordings. Nothing here is illustrative.
"""
from __future__ import annotations

import json

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

import textfit as TF
from deckkit import (ACCENT, BAD, CARD, CARD2, FAINT, FONT, GOOD, INK, INK_DIM, LINE,
                     MAG, MUTED, SIGNAL, SIH, SIH_DARK, TEMPLATE, WARN, WHITE, HERE,
                     bar, caption, drop, drop_slide, fit, para, picture, rich,
                     rounded, shape_by_name, textbox)

I = Inches
ROOT = HERE.parent
BENCH = json.loads((ROOT / "reports/out/benchmark.json").read_text())
ABL = json.loads((ROOT / "reports/out/ablation.json").read_text())

# ─── measured constants, each with the file it came from ──────────────────────
TEAM = dict(ps_id="SIH26055",
            ps_title="Smart Scan Strategy for Electronic Warfare",
            theme="Robotics and Drones",
            category="Software",
            team_id="< Team ID >",
            team_name="Alpha")

RGB_TINT = RGBColor(0xE8, 0xF1, 0xF9)   # 12 % SIH blue on white

ONE_LINER = ("A receiver can only listen to a slice of the band at a time. AAMS-X decides "
             "where to point it next — on real public spectrum recordings, with every "
             "decision explainable and every number reproducible.")


def rule(slide, x, y, w, *, color=LINE, h=I(0.014)):
    return bar(slide, x, y, w, h, fill=color)


def kicker(slide, x, y, w, text, *, color=SIH, size=8.5):
    _, tf = textbox(slide, x, y, w, I(0.20))
    para(tf, text.upper(), size=size, bold=True, color=color, first=True, line=0.9)


def bullets(tf, rows, *, size=10.2, gap=3.2, dot=ACCENT, first_gap=0, first=True):
    """Point-form rows of (lead, rest). `lead` is bolded; empty lead = plain line."""
    for i, (lead, rest) in enumerate(rows):
        chunks = [("▪  ", {"size": size, "bold": True, "color": dot})]
        if lead:
            chunks.append((lead, {"size": size, "bold": True, "color": INK}))
            if rest:
                chunks.append(("  " + rest, {"size": size, "color": INK_DIM}))
        else:
            chunks.append((rest, {"size": size, "color": INK_DIM}))
        rich(tf, chunks, first=(first and i == 0),
             space_before=(first_gap if i == 0 else gap),
             line=0.94, bullet_indent=0.13)


def statcard(slide, x, y, w, h, value, unit, label, sub, *, color=ACCENT):
    rounded(slide, x, y, w, h, fill=CARD, edge=LINE, adj=0.10)
    bar(slide, x, y, I(0.045), h, fill=color)
    _, tf = textbox(slide, x + I(0.16), y + I(0.075), w - I(0.28), h - I(0.15))
    para(tf, label.upper(), size=7.2, bold=True, color=MUTED, first=True, line=0.9)
    rich(tf, [(value, {"size": 19, "bold": True, "color": color}),
              (" " + unit, {"size": 9, "bold": True, "color": MUTED})],
         space_before=1.5, line=0.86)
    para(tf, sub, size=7.4, color=INK_DIM, space_before=1.5, line=0.95)


def chip(slide, x, y, w, h, text, *, fill=CARD2, color=SIH_DARK, size=8.0, bold=True):
    sh = rounded(slide, x, y, w, h, fill=fill, edge=None, adj=0.28)
    tf = sh.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    tf.margin_left = tf.margin_right = Emu(int(I(0.04)))
    tf.margin_top = tf.margin_bottom = 0
    para(tf, text, size=size, bold=bold, color=color, align=PP_ALIGN.CENTER, first=True, line=0.9)
    return sh


def arrow(slide, x, y, w, h, *, color=FAINT):
    sh = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, Emu(int(x)), Emu(int(y)),
                                Emu(int(w)), Emu(int(h)))
    sh.fill.solid()
    sh.fill.fore_color.rgb = color
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def panel(slide, x, y, w, h, title, *, accent=SIH, fill=WHITE):
    """A titled content panel. Returns the text frame for the body."""
    rounded(slide, x, y, w, h, fill=fill, edge=LINE, adj=0.045)
    bar(slide, x, y, w, I(0.035), fill=accent)
    _, tf = textbox(slide, x + I(0.155), y + I(0.135), w - I(0.31), I(0.20))
    para(tf, title.upper(), size=8.4, bold=True, color=accent, first=True, line=0.9)
    _, body = textbox(slide, x + I(0.155), y + I(0.40), w - I(0.31), h - I(0.55))
    return body


# ─── layout constants, measured against the template's own furniture ──────────
LEFT, RIGHT = I(0.36), I(12.97)            # content margins
TOP_L = I(0.94)                            # top for anything left of the SIH logo
TOP_R = I(1.24)                            # the logo occupies (10.70, 0)-(13.16, 1.16)
BOTTOM = I(6.86)                           # the blue footer band starts at 6.95
FULL_W = RIGHT - LEFT
LOGO_X = I(10.70)


def place_title(s, text: str | None = None) -> None:
    """Move the section title clear of the template's "Your Team Name" oval."""
    t = shape_by_name(s, "Title 1")
    t.left, t.top = Emu(int(I(1.86))), Emu(int(I(0.02)))
    t.width, t.height = Emu(int(I(8.60))), Emu(int(I(0.86)))
    if text is not None:
        tf = t.text_frame
        tf.clear()
        para(tf, text, size=27, bold=True, color=INK, first=True, line=0.9)


def fitted(slide, x, y, w, h, title, rows, *, accent=SIH, hi=9.6, lo=7.0,
           gap=4.0, fill=WHITE, dot=None):
    """A titled panel whose bullet size is chosen so the text cannot overflow."""
    body_w = Emu(w).inches - 0.31 - 0.02
    body_h = Emu(h).inches - 0.55
    size = TF.best_size(rows, width_in=body_w, height_in=body_h, hi=hi, lo=lo, gap_pt=gap)
    tf = panel(slide, x, y, w, h, title, accent=accent, fill=fill)
    bullets(tf, rows, size=size, gap=max(gap * size / hi, 1.6), dot=dot or accent)
    return size


# ══════════════════════════════════════════════════════════════════════════════
# Slide 1 — title
# ══════════════════════════════════════════════════════════════════════════════
EVIDENCE = [
    ("7 real e-CALLISTO recordings", "139 MB cached · 218 M spectrogram cells · "
     "is_synthetic: false, always"),
    ("252 benchmark episodes", "6 seeds × 6 policies × 7 presets — wins and losses "
     "both published"),
    ("406 / 406 published values re-derive", "1,456 stored comparisons audited, "
     "0 disagreements"),
    ("0.31 ms median decision", "against a 250 ms environment step · CPU only, no GPU"),
    ("Deployed and running", "http://98.130.46.223 — Docker Compose behind nginx"),
]


SCOPE = [
    ("Domain", "public e-CALLISTO solar-radio recordings, replayed from a local cache."),
    ("Out of scope on purpose", "no transmission, no jamming, no emitter identification, "
     "no geolocation, no hardware control."),
    ("Transferable part", "budgeted active sensing under non-stationarity \u2014 the "
     "mathematics is domain-independent."),
]


def slide1(s) -> None:
    drop(shape_by_name(s, "Picture 4"))          # decorative SIH mark, under the screenshot
    drop(shape_by_name(s, "Freeform: Shape 26"))  # decorative wedge, same region

    hdr = shape_by_name(s, "Title 7")             # "SMART INDIA HACKATHON 2026"
    hdr.left, hdr.top = Emu(int(LEFT)), Emu(int(I(0.04)))
    hdr.width, hdr.height = Emu(int(I(5.62))), Emu(int(I(0.52)))
    hsz = next((z for z in (19, 18, 17, 16, 15, 14)
                if TF.n_lines("SMART INDIA HACKATHON 2026", z, 5.58, bold=True) == 1), 14)
    tf = hdr.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    para(tf, "SMART INDIA HACKATHON 2026", size=hsz, bold=True, color=SIH_DARK,
         first=True, line=0.9)

    sub = shape_by_name(s, "Subtitle 3")
    sub.left, sub.width = Emu(int(LEFT)), Emu(int(I(5.62)))
    sub.top, sub.height = Emu(int(I(0.64))), Emu(int(I(1.72)))
    tf = sub.text_frame
    tf.clear()
    tf.word_wrap = True
    para(tf, "AAMS-X", size=36, bold=True, color=SIH_DARK, first=True, line=0.9)
    para(tf, "Adaptive Active Multi-band Spectrum eXplorer", size=15, bold=True,
         color=ACCENT, space_before=2, line=0.95)
    para(tf, "An explainable active-sensing scheduler for wideband receivers, "
             "measured on real public spectrum.",
         size=10.5, color=INK_DIM, space_before=5, line=1.0)

    box = shape_by_name(s, "TextBox 9")
    box.left, box.top = Emu(int(I(0.36))), Emu(int(I(2.46)))
    box.width, box.height = Emu(int(I(5.62))), Emu(int(I(2.30)))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = 0
    for i, (k, v) in enumerate([("Problem Statement ID", TEAM["ps_id"]),
                                ("Problem Statement Title", TEAM["ps_title"]),
                                ("Theme", TEAM["theme"]),
                                ("PS Category", TEAM["category"]),
                                ("Team ID", TEAM["team_id"]),
                                ("Team Name", TEAM["team_name"])]):
        rich(tf, [(k + " – ", {"size": 10.5, "bold": True, "color": MUTED}),
                  (v, {"size": 10.5, "bold": True, "color": INK})],
             first=(i == 0), space_before=0 if i == 0 else 4.5, line=0.95)

    # Evidence strip — the five things a judge can check in the repository itself.
    y, h = I(4.84), I(1.88)
    rounded(s, I(0.36), y, I(5.62), h, fill=CARD, edge=LINE, adj=0.055)
    bar(s, I(0.36), y, I(0.05), h, fill=ACCENT)
    _, tf = textbox(s, I(0.54), y + I(0.12), I(5.28), h - I(0.24))
    para(tf, "WORKING SYSTEM  ·  REAL DATA  ·  REPRODUCIBLE", size=8.2, bold=True,
         color=ACCENT, first=True, line=0.9)
    size = TF.best_size(EVIDENCE, width_in=5.10, height_in=1.30, hi=8.4, lo=6.4, gap_pt=3.6)
    bullets(tf, EVIDENCE, size=size, gap=3.0, dot=ACCENT, first_gap=4.0, first=False)

    # The product itself, on the title slide: this is a working system, not a proposal.
    sx = I(6.20)
    sw, sh_ = fit("command_center", w=RIGHT - sx)
    picture(s, "command_center", sx, TOP_R, w=sw)
    caption(s, sx, TOP_R + Emu(sh_) + I(0.04), Emu(sw),
            "Command Center, live \u2014 real recording replaying, belief map, the "
            "eight-term decision decomposition, run KPIs.")
    py_ = I(5.22)
    fitted(s, sx, py_, Emu(sw), BOTTOM - py_, "Scope, stated up front", SCOPE,
           accent=MUTED, hi=8.8, lo=6.8, gap=3.6, fill=WHITE)


# ══════════════════════════════════════════════════════════════════════════════
# Slide 2 — IDEA TITLE
# ══════════════════════════════════════════════════════════════════════════════
NOVELTY = [
    ("Contiguous-window action space.", "The scheduler picks a physically realisable "
     "tuning — a start channel and a span — not an unordered set of regions."),
    ("Memory of contexts, not actions.", "24 bounded prototypes; retrieval is one "
     "modern-Hopfield step at β = 12, so a returning environment is recognised, "
     "not relearned."),
    ("The score is the algorithm.", "8 additive terms with published weights. The UI shows "
     "the chosen window and the runner-up, term by term — no post-hoc attribution."),
    ("Change detection gates memory.", "A Page-Hinkley + EWMA detector suppresses stale "
     "recall the moment the environment moves."),
    ("Losses are published.", "3 significant wins, 2 significant losses across 7 presets, "
     "each with the mechanism named."),
]
FLOW = [("Sense", "replay a real recording; only the chosen window is revealed"),
        ("Believe", "per-region Beta posterior, decaying while unobserved"),
        ("Decide", "score every contiguous window on 8 terms, then sample"),
        ("Explain", "emit the decomposition, the runner-up and a note")]
ADDRESSES = [
    ("Scarcity is the constraint", "8.3 % of the band is visible per step; the policy turns "
     "that into an information-maximising schedule instead of a sweep."),
    ("Non-stationarity is explicit", "periodicity and change detection are separate, "
     "measurable terms — not hyperparameters."),
    ("Trust is a requirement", "an operator can read why the receiver moved; a deep-RL "
     "policy cannot supply that."),
]
VERIFY = [
    ("Open the provenance panel", "source URL, retrieval time, preprocessing chain, "
     "licence, is_synthetic: false."),
    ("Toggle the truth overlay off", "the scheduler never had it; belief tracks it anyway."),
    ("Run the arena, then the ablation", "a preset it wins, then one it loses."),
    ("Press Replay on a history row", "the episode re-runs and must reproduce the metrics."),
]


def slide2(s) -> None:
    drop(shape_by_name(s, "TextBox 8"))
    place_title(s)

    y = I(0.92)
    rounded(s, LEFT, y, FULL_W, I(0.56), fill=RGB_TINT, edge=None, adj=0.24)
    _, tf = textbox(s, LEFT + I(0.22), y + I(0.06), FULL_W - I(0.44), I(0.44),
                    anchor=MSO_ANCHOR.MIDDLE)
    rich(tf, [("THE IDEA IN ONE LINE  —  ", {"size": 8.6, "bold": True, "color": SIH}),
              (ONE_LINER, {"size": 10.4, "color": INK})], first=True, line=0.95)

    # Row A — the scarcity that defines the problem, and what is new about the answer.
    ay = I(1.62)
    aw, ah = fit("problem_aperture", w=I(6.30))
    picture(s, "problem_aperture", LEFT, ay, w=aw)
    caption(s, LEFT, ay + Emu(ah) + I(0.03), Emu(aw),
            "Measured from the cache: 4 of 48 regions visible per step — 8.3 % of the band.")

    px = LEFT + Emu(aw) + I(0.30)
    fitted(s, px, TOP_R, RIGHT - px, ay + Emu(ah) - TOP_R, "What is new", NOVELTY,
           accent=MAG, hi=9.4, lo=7.2, gap=4.6)

    # Flow strip — legible at projector distance, unlike a shrunken diagram.
    fy = ay + Emu(ah) + I(0.28)
    kicker(s, LEFT, fy, I(6.0), "How it works · one decision, four stages")
    cy = fy + I(0.22)
    gap, aw2 = I(0.30), I(0.24)
    n = len(FLOW)
    cw = (FULL_W - (gap + aw2) * (n - 1) - I(0.06) * 0) / n
    for i, (name, sub) in enumerate(FLOW):
        x = LEFT + (cw + gap + aw2) * i
        sh = rounded(s, Emu(int(x)), cy, Emu(int(cw)), I(0.50), fill=CARD, edge=LINE, adj=0.16)
        bar(s, Emu(int(x)), cy, I(0.042), I(0.50), fill=(ACCENT, SIGNAL, MAG, WARN)[i])
        tfx = sh.text_frame
        tfx.word_wrap = True
        tfx.vertical_anchor = MSO_ANCHOR.MIDDLE
        tfx.margin_left = Emu(int(I(0.14)))
        tfx.margin_right = Emu(int(I(0.06)))
        tfx.margin_top = tfx.margin_bottom = 0
        para(tfx, f"{i + 1}. {name}", size=9.6, bold=True, color=INK, first=True, line=0.9)
        para(tfx, sub, size=7.6, color=INK_DIM, space_before=1.2, line=0.92)
        if i < n - 1:
            arrow(s, Emu(int(x + cw + I(0.035))), cy + I(0.17), Emu(int(gap - I(0.07))),
                  I(0.16), color=FAINT)

    # Row B
    ry = cy + I(0.60)
    rh = BOTTOM - ry
    w1 = I(6.30)
    fitted(s, LEFT, ry, w1, rh, "How it addresses the problem", ADDRESSES,
           accent=ACCENT, hi=9.4, lo=6.6, gap=4.2)
    x2 = LEFT + w1 + I(0.30)
    fitted(s, x2, ry, RIGHT - x2, rh, "What a judge can check in 60 seconds", VERIFY,
           accent=SIGNAL, hi=9.4, lo=6.6, gap=4.2)


# ══════════════════════════════════════════════════════════════════════════════
# Slide 3 — TECHNICAL APPROACH
# ══════════════════════════════════════════════════════════════════════════════
STACK = [
    ("Core", "Python 3.11 · NumPy · SciPy — 72 modules, 12,007 lines, mypy clean"),
    ("Service", "FastAPI · Pydantic v2 · Uvicorn — 24 HTTP routes + 1 WebSocket, "
     "OpenAPI generated"),
    ("Interface", "React 19 · TypeScript · Vite · Tailwind — 13 screens, Canvas waterfall "
     "at 60 fps"),
    ("Data", "Parquet + DuckDB window index (3,350 windows) · SQLite run registry"),
    ("Policies", "MAG-NTS + 5 classical baselines · optional DQN behind a Torch extra"),
    ("Delivery", "Docker Compose · nginx · AWS EC2 · fully offline after the first fetch"),
    ("Quality", "pytest (507 collected) · ruff · mypy · verify_docs.py re-derives every "
     "published number"),
]
SCORE = [
    ("Weights, published", "detection 0.942 · information 0.066 · memory 0.565 · "
     "periodicity 0.270 · uncertainty 0.234 · recency 0.172 · cost 0.292 · switching 0.103"),
    ("Tuned on train receivers only", "45 candidates, 3 seeds, roles: [\"train\"] — the "
     "record is in data/index/mag_nts_tuning.json (advantage +28.57, win-rate 1.0)."),
]
COUPLINGS = [
    ("Change gating", "a detected shift damps the memory term for that step."),
    ("Memory gating", "recall applies only above a similarity threshold."),
    ("Budget pressure", "remaining budget rescales the cost and switching terms."),
    ("Σc(aₜ) ≤ B enforced", "the environment rejects an over-budget action; it is not a "
     "soft penalty."),
]


def slide3(s) -> None:
    drop(shape_by_name(s, "TextBox 8"))
    place_title(s)

    ay = TOP_L
    aw, ah = fit("architecture", w=I(6.90))
    picture(s, "architecture", LEFT, ay, w=aw)
    caption(s, LEFT, ay + Emu(ah) + I(0.03), Emu(aw),
            "Five layers, each one directory. The sealed boundary is enforced by tests.")

    px = LEFT + Emu(aw) + I(0.30)
    fitted(s, px, TOP_R, RIGHT - px, ay + Emu(ah) - TOP_R, "Technologies used", STACK,
           accent=SIH, hi=9.6, lo=7.4, gap=4.6, dot=SIGNAL)

    ry = ay + Emu(ah) + I(0.36)
    rh = BOTTOM - ry
    dw, dh = fit("decision_score", h=rh)
    picture(s, "decision_score", LEFT, ry, h=dh)

    tx = LEFT + Emu(dw) + I(0.30)
    half = (RIGHT - tx - I(0.24)) / 2
    fitted(s, tx, ry, Emu(int(half)), rh, "The eight-term score — this is the algorithm",
           SCORE, accent=ACCENT, hi=9.2, lo=7.0, gap=4.2)
    fitted(s, tx + Emu(int(half)) + I(0.24), ry, Emu(int(half)), rh,
           "Three couplings, plus a hard budget", COUPLINGS,
           accent=MAG, hi=9.2, lo=7.0, gap=4.2)


# ══════════════════════════════════════════════════════════════════════════════
# Slide 4 — FEASIBILITY AND VIABILITY
# ══════════════════════════════════════════════════════════════════════════════
LAPTOP = [
    ("0.31 ms median decision", "against a 250 ms step — three orders of magnitude of "
     "headroom."),
    ("CPU only", "NumPy and SciPy; no GPU, no cluster, no broker."),
    ("139 MB, fetched once", "then fully offline."),
    ("Already deployed", "Docker Compose behind nginx on one EC2 instance."),
]
CHALLENGES = [
    ("Abrupt change breaks recall", "memory retrieves a prior for a context that is gone: "
     "−85.89 reward on sudden-shift.",
     "Gating retrieval on the change posterior is specified but not implemented — doing it "
     "after seeing the held-out result would be tuning on the test set."),
    ("No per-emitter ground truth", "no public archive of this kind has one.",
     "A stated derived label: excess above max(1.5 dB, 5σ) over a drift-tracked P10 "
     "baseline. Every panel from it is tagged derived-label."),
    ("Six seeds is a small sample", "gaps under roughly ±20 reward are not resolvable.",
     "Welch t and Mann-Whitney U must both pass at α = 0.05; anything else is reported as "
     "not significant, in either direction."),
    ("Not production-hardened", "the API is unauthenticated and one query path builds SQL "
     "fragments.",
     "Both are logged in docs/QUALITY_AND_RISKS.md with a fix order; the demo host is "
     "single-operator."),
]


def slide4(s) -> None:
    drop(shape_by_name(s, "TextBox 8"))
    place_title(s)

    ay = TOP_L
    rw, rh_ = fit("reproducibility", w=I(7.30))
    picture(s, "reproducibility", LEFT, ay, w=rw)
    caption(s, LEFT, ay + Emu(rh_) + I(0.04), Emu(rw),
            "Five stages from public archive to a number the panel can re-derive here.")

    px = LEFT + Emu(rw) + I(0.30)
    pw = RIGHT - px
    lw, lh = fit("latency", w=I(4.30))
    picture(s, "latency", px + (pw - Emu(lw)) / 2, TOP_R, w=lw)
    cy = TOP_R + Emu(lh) + I(0.17)
    bot = ay + Emu(rh_) + I(0.30)
    fitted(s, px, cy, pw, bot - cy, "It runs on the laptop in front of you",
           LAPTOP, accent=ACCENT, hi=9.0, lo=6.6, gap=4.0)

    # Challenges and mitigations — four columns so nothing turns into a paragraph.
    ry = bot + I(0.16)
    kicker(s, LEFT, ry, I(8.0), "Potential challenges  →  how each one is handled")
    gy = ry + I(0.22)
    gh = BOTTOM - gy
    gap = I(0.16)
    cw = (FULL_W - gap * 3) / 4
    inner_w = Emu(int(cw)).inches - 0.30
    for i, (head, evid, fixtext) in enumerate(CHALLENGES):
        x = LEFT + (cw + gap) * i
        rounded(s, Emu(int(x)), gy, Emu(int(cw)), gh, fill=CARD, edge=LINE, adj=0.055)
        bar(s, Emu(int(x)), gy, Emu(int(cw)), I(0.034), fill=WARN)
        _, tf = textbox(s, Emu(int(x + I(0.15))), gy + I(0.14), Emu(int(cw - I(0.30))),
                        gh - I(0.26))
        avail = Emu(gh).inches - 0.26
        size = 8.2
        while size > 6.0:
            need = (TF.para_height(head, size + 0.4, inner_w, bold=True)
                    + TF.para_height(evid, size, inner_w) + 3.0 / 72.0
                    + TF.para_height("→ " + fixtext, size, inner_w) + 4.0 / 72.0)
            if need <= avail:
                break
            size -= 0.2
        para(tf, head, size=size + 0.4, bold=True, color=INK, first=True, line=0.92)
        para(tf, evid, size=size, color=INK_DIM, space_before=2.0, line=0.95)
        rich(tf, [("→  ", {"size": size, "bold": True, "color": GOOD}),
                  (fixtext, {"size": size, "color": GOOD})], space_before=3.0, line=0.95)


# ══════════════════════════════════════════════════════════════════════════════
# Slide 5 — IMPACT AND BENEFITS
# ══════════════════════════════════════════════════════════════════════════════
KPI = [
    ("+54.26", "reward vs. best classical baseline", "high-noise · p = 0.0006 · 6 seeds",
     GOOD),
    ("+99.07", "reward contributed by memory alone", "high-noise · p = 0.00005 · ablation",
     MAG),
    ("−69.43", "reward on the held-out receivers", "unseen-generalization · p = 0.0079",
     BAD),
    ("0.5594", "of the oracle's achievable reward", "vs. 0.4331 for the best baseline",
     SIGNAL),
]
WHO = [
    ("Spectrum monitoring teams", "the same decision — which slice to sample next under a "
     "hard budget — appears in interference hunting, shared-spectrum enforcement and "
     "radio-astronomy RFI surveys."),
    ("Researchers", "a reproducible active-sensing benchmark on public recordings: 7 "
     "stations, 3,350 indexed windows, 7 presets, fixed seeds."),
    ("Students and reviewers", "an explainable scheduler where the eight-term score is "
     "the algorithm, not a post-hoc attribution."),
]
BENEFITS = [
    ("Economic", "one commodity CPU replaces a wider or faster receiver for the same "
     "detection yield — 0.5594 of oracle reward within a fixed 1,200-step budget."),
    ("Scientific", "wins and losses both published, with the mechanism named; the "
     "ablation says which component earns each effect."),
    ("Social", "no transmission, no jamming, no emitter identification, no geolocation, "
     "no hardware control — an academic scheduler on public scientific data."),
]


def slide5(s) -> None:
    drop(shape_by_name(s, "TextBox 8"))
    place_title(s)

    dw, dh = fit("delta_both", w=I(6.55))
    picture(s, "delta_both", LEFT, TOP_L, w=dw)
    caption(s, LEFT, TOP_L + Emu(dh) + I(0.03), Emu(dw),
            "Every preset, both directions. A bar counts only when Welch t and "
            "Mann-Whitney U both pass at α = 0.05.")

    # 2x2 KPI grid — four cards read at projector distance, five stacked did not.
    kx = LEFT + Emu(dw) + I(0.30)
    kw = RIGHT - kx
    gap = I(0.14)
    cw = (kw - gap) / 2
    ch = I(1.475)
    for i, (big, mid, small, col) in enumerate(KPI):
        x = kx + (cw + gap) * (i % 2)
        y = TOP_R + (ch + gap) * (i // 2)
        rounded(s, Emu(int(x)), Emu(int(y)), Emu(int(cw)), ch, fill=CARD, edge=LINE,
                adj=0.06)
        bar(s, Emu(int(x)), Emu(int(y)), Emu(int(cw)), I(0.036), fill=col)
        _, tf = textbox(s, Emu(int(x + I(0.16))), Emu(int(y + I(0.16))),
                        Emu(int(cw - I(0.32))), ch - I(0.28))
        para(tf, big, size=25, bold=True, color=col, first=True, line=0.88)
        para(tf, mid, size=8.6, bold=True, color=INK, space_before=2.0, line=0.94)
        para(tf, small, size=7.4, color=MUTED, space_before=1.5, line=0.96)

    ry = TOP_R + (ch + gap) * 2 + I(0.10)
    fitted(s, kx, ry, kw, BOTTOM - ry, "Who benefits", WHO, accent=SIH,
           hi=9.0, lo=6.8, gap=4.0)

    by = TOP_L + Emu(dh) + I(0.42)
    fitted(s, LEFT, by, Emu(dw), BOTTOM - by, "Benefits, measured rather than asserted",
           BENEFITS, accent=ACCENT, hi=9.4, lo=7.0, gap=4.4)


# ══════════════════════════════════════════════════════════════════════════════
# Slide 6 — RESEARCH AND REFERENCES
# ══════════════════════════════════════════════════════════════════════════════
PROV = [
    ("Archive", "e-CALLISTO, the international network of solar radio spectrometers "
     "(FHNW Institute for Data Science, Brugg/Windisch)."),
    ("Per recording, stored", "source URL, retrieval timestamp, source file count, "
     "SHA of the cached cube, full preprocessing chain, licence, is_synthetic: false."),
    ("Derived label, not ground truth", "excess above max(1.5 dB, 5σ), σ from a "
     "first-difference MAD estimate against a drift-tracking P10 baseline. Every panel "
     "computed from it is tagged derived-label."),
    ("Split roles are declared", "train / validation / unseen; the held-out receivers "
     "appear in exactly one preset, asserted by a test that fails the build."),
]
REFS_METHOD = [
    ("Thompson, 1933", "posterior sampling — extended here to contiguous windows."),
    ("Auer, Cesa-Bianchi & Fischer, 2002", "UCB1 — the confidence-bound baseline."),
    ("Raj & Kalyani, 2017", "Taming non-stationary bandits (arXiv:1707.09727) — the NTS "
     "control policy."),
    ("Ramsauer et al., 2021", "Hopfield Networks is All You Need (arXiv:2008.02217) — "
     "single-step retrieval at β = 12."),
    ("Page, 1954", "continuous inspection schemes — the Page-Hinkley detector."),
    ("Garivier & Moulines, 2011", "UCB policies for switching bandits — the change-aware "
     "framing."),
    ("Lindley, 1956", "information provided by an experiment — the information term."),
    ("Chaloner & Verdinelli, 1995", "Bayesian experimental design — the objective."),
]
OWN = [
    ("Welch, 1947 and Mann & Whitney, 1947", "the two tests every claim must pass; both "
     "at α = 0.05, or the difference is reported as not significant in either direction."),
    ("Ours", "the contiguous-window action space, the eight-term score with its three "
     "couplings, the change-gated bounded context memory, and the 7-preset benchmark on "
     "public recordings."),
    ("Written down", "docs/EXPERIMENTS.md (every measured number, wins and losses), "
     "LIMITATIONS.md (what it does not do), QUALITY_AND_RISKS.md (verification state "
     "and open risks)."),
    ("Re-derivable", "scripts/verify_docs.py re-computes 406 published values from the "
     "stored JSON and audits 1,456 comparisons; a mismatch fails."),
]


def slide6(s) -> None:
    drop(shape_by_name(s, "TextBox 8"))
    place_title(s)

    sw, sh_ = fit("stations", w=I(6.40))
    picture(s, "stations", LEFT, TOP_L, w=sw)
    caption(s, LEFT, TOP_L + Emu(sh_) + I(0.04), Emu(sw),
            "Seven public receivers, four continents. Roles are fixed in the catalogue \u2014 "
            "the held-out stations drive exactly one preset.", h=I(0.32))

    px = LEFT + Emu(sw) + I(0.30)
    pw = RIGHT - px
    ph = TOP_L + Emu(sh_) - TOP_R
    fitted(s, px, TOP_R, pw, ph, "Data provenance and labelling", PROV,
           accent=SIH, hi=9.2, lo=7.0, gap=4.2)

    ry = TOP_L + Emu(sh_) + I(0.42)
    rh = BOTTOM - ry
    w1 = I(6.40)
    fitted(s, LEFT, ry, w1, rh, "Methods we build on", REFS_METHOD,
           accent=MAG, hi=8.6, lo=6.2, gap=2.8)

    x2 = LEFT + w1 + I(0.30)
    fitted(s, x2, ry, RIGHT - x2, rh, "How claims are decided, and what is ours", OWN,
           accent=ACCENT, hi=9.2, lo=6.8, gap=4.0)


# ══════════════════════════════════════════════════════════════════════════════
def main() -> None:
    prs = Presentation(str(TEMPLATE))
    slides = prs.slides
    for fn, idx in ((slide1, 0), (slide2, 1), (slide3, 2), (slide4, 3), (slide5, 4),
                    (slide6, 5)):
        fn(slides[idx])
    drop_slide(prs, 6)                      # the template's own instruction slide
    out = HERE / "AAMS-X-SIH2026-Idea-Submission.pptx"
    prs.save(str(out))
    kb = out.stat().st_size / 1024
    print(f"wrote {out.name}  {kb:.0f} kB  {len(prs.slides._sldIdLst)} slides")


if __name__ == "__main__":
    main()
