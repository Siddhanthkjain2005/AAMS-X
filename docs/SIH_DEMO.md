# SIH demo walkthrough

A timed walkthrough for the evaluation panel: **8 minutes of demo, 4 minutes of
questions.** Problem statement SIH26055, *Smart Scan Strategy for Electronic Warfare*.

The one-sentence version, if you only get one sentence: **a receiver can only listen to a
slice of the band at a time, so AAMS-X decides where to point it next — on real public
spectrum recordings, with every decision explainable and every number reproducible.**

## Before the panel arrives

```bash
make setup && make data && make index      # ~10 min, downloads 139 MB of real recordings
make test                                  # 440 tests, must be green
make api                                   # backend on :8000
make web                                   # frontend on :5173
```

Checklist:

- [ ] `GET /api/status` → `warnings: []`, `recordings: 7`, `windows_indexed: 3350`, `presets: 7`
- [ ] `reports/out/benchmark.json` and `ablation.json` present (or run `make benchmark`, ~6 min)
- [ ] Demo Mode opens full-screen with no browser chrome (F11)
- [ ] Laptop on mains, display at 1920×1080, notifications off
- [ ] **A pre-rendered HTML report open in a second tab** — the fallback if anything live stalls

**Offline?** Everything above except `make data` works with no network at all. The cache
is on disk, the archive is only needed once. Say this out loud if the venue Wi-Fi is bad —
it is a strength, not an excuse.

## The 8 minutes

| # | Time | Screen | What you say | What you click |
|---|---|---|---|---|
| 1 | 0:00–0:45 | **Command Center** | "This is real spectrum, not a simulator. Seven public e-CALLISTO receivers, four continents, 139 MB on disk." | Point at the `REAL PUBLIC SPECTRUM REPLAY` badge and the live waterfall |
| 2 | 0:45–1:45 | **Real Spectrum Replay** | "Here is the provenance for one recording: source URL, retrieval time, every preprocessing step, `is_synthetic: false`. The labels are derived from a stated threshold policy — we call them derived labels, not ground truth." | Open MRO, expand the provenance panel, scroll the `preprocessing` list |
| 3 | 1:45–2:45 | **Belief Map** | "The scheduler never sees the truth. It sees this: a belief per region that decays when unobserved, split into aleatoric and epistemic uncertainty." | Toggle truth overlay **off**, let a few steps run, toggle it on to show the belief tracking it |
| 4 | 2:45–4:00 | **Decision Inspector** | "This is the part that is not a black box. Eight terms, each weighted, summing to the score for the window we chose — and the runner-up alongside it." | Click the current step; read one note aloud, e.g. *"context recognised (similarity 0.94) — retrieved prior applied"* |
| 5 | 4:00–5:00 | **Memory Visualizer** | "Bounded at 24 prototypes. It stores *contexts*, not actions, and retrieval is a single modern-Hopfield step at β=12." | Show a write, then a recognition hit above 0.90 |
| 6 | 5:00–6:15 | **Algorithm Arena** | "Six policies, six seeds, same real windows. MAG-NTS wins four presets significantly — and loses two significantly. Here is one it loses." | Run `high-noise` (win, +54.26, p=0.0006), then switch to `unseen-generalization` (loss, −69.43, p=0.0079) |
| 7 | 6:15–7:15 | **Ablation Lab** | "Which component actually does the work? On high-noise, memory: +99.07. On sudden-shift, the same memory *costs* 85.89. That is why we ship the ablation, not just the headline." | Show both ladders side by side |
| 8 | 7:15–8:00 | **Reports** | "Generated from stored traces with a config hash. Replay re-runs the episode and must reproduce the metrics." | Click Generate, then Replay Experiment on a history row |

Fifteen seconds spare per step. If you are behind, drop step 5 — memory shows up again in
step 7 with numbers attached.

## The one thing to say twice

**"We report where it loses."** Steps 6 and 7 exist for that. A panel that has watched
eight teams claim uniform improvement will remember the one that showed a significant
loss and explained the mechanism. The explanation, in one breath: *on the spliced
scenarios the environment is replaced by an uncorrelated one, so memory retrieves a prior
for a context that no longer exists; round-robin wins detection coverage there because
the band is dense and sweeping it is genuinely good. The fix — gating retrieval on the
change detector — is written down but not implemented, because implementing it after
seeing the held-out result would be tuning on the test set.*

## Demo Mode

Full-screen, no chrome, oversized type, auto-advancing. Built for a projector at the back
of a hall: KPI row, waterfall, belief map, decision decomposition and the arena table,
cycling on a fixed cadence with no interaction needed. Use it if you are presenting to a
room rather than across a desk. `Esc` returns to the normal UI; the same data drives both.

## Expected questions

**"Is this real data or simulated?"**
Real, and the provenance panel proves it per recording: archive URL, retrieval timestamp,
source file count, preprocessing chain, licence, `is_synthetic: false`. There is no
synthetic fallback anywhere in the codebase — if the cache is missing, `/api/status`
returns a warning telling you to fetch it. Substituting synthetic data silently is a
failure mode we designed against.

**"How do you know your detections are correct?"**
We do not have per-emitter ground truth — no public archive of this kind does. We have a
**derived label**: excess above `max(1.5 dB, 5σ)` where σ is a first-difference MAD
estimate against a drift-tracking P10 baseline. Every panel computed from it is tagged
`derived-label`, and the report says so in the body. Detection metrics are comparable
across policies because they share the label; they are not absolute physical truth.

**"Why not deep RL?"**
Two reasons. First, explainability is a requirement here, not a nicety — the Decision
Inspector shows an eight-term additive score because that decomposition *is* the
algorithm, not a post-hoc attribution. Second, we measured the alternative: DQN and SAC
are implemented behind `AAMSX_ENABLE_DEEP_RL` and Torch is an optional extra. They need
far more interaction than a 1200-step episode provides, and they cannot tell you why they
retuned. `/api/status` reports `deep_rl_available` so you can see it is real code, not a
slide.

**"Is round-robin not a straw man?"**
It is not, and our own numbers say so: on all three spliced scenarios round-robin has the
**highest** sustained detection probability (0.4635, 0.4650, 0.4927) and always achieves
band coverage 1.000. It loses badly on reward and regret. In dense environments,
systematic sweeping is a strong coverage baseline — we found that by measuring rather than
by assuming.

**"How do we know you did not tune on the test set?"**
Three independent mechanisms, each with a test that fails the build. The station catalogue
assigns `train` / `validation` / `unseen` roles; the held-out receivers appear in exactly
one preset and one family, asserted by
`test_only_the_held_out_preset_touches_the_held_out_receivers`. The environment is
**sealed** — the scheduler is handed a frozen `DecisionContext` and has no handle on the
truth array at all, so leakage is a `LeakageError`, not a code-review question. And the
tuning record in `data/index/mag_nts_tuning.json` names the roles it used: `["train"]`.
The unseen result is a loss; if we had tuned on it, it would not be.

**"What does it cost to run?"**
0.29 ms median per decision for MAG-NTS against a 0.25 s environment step — three orders
of magnitude of headroom. NumPy and SciPy only; no GPU, no cluster, no Kafka. The whole
system runs on the laptop in front of you.

**"Could this control a real receiver?"**
Deliberately not, and that is a scope decision rather than a gap. AAMS-X does not
transmit, does not jam, does not identify military emitters, does not geolocate, does not
control hardware and does not recommend tactical frequencies. It is an academic
active-sensing scheduler evaluated on public scientific recordings. The scheduling
mathematics is domain-independent; the operational parts are out of scope on purpose.

**"What is the single most important number?"**
On `high-noise`, memory contributes **+99.07 reward, p = 0.00005, over six seeds** — the
largest single effect in the project, and it is the component the problem statement is
really asking about: does remembering where signals were help you find them again. The
honest companion number is **−85.89 on `sudden-shift`**, same component, same protocol.

## If something breaks

| Symptom | Do this |
|---|---|
| Frontend blank | The backend is authoritative — switch to `/api/docs` and drive the demo through the API. It is less pretty and just as real. |
| Episode stalls | Cancel, drop `pace_hz` to 10, restart. Long horizons at 60 Hz can outrun a projector's compositor, not the backend. |
| Arena slow | Reduce seeds to 3. Say you are doing it: "six seeds is what the paper numbers use; three keeps us inside the time slot." |
| Cache missing | `/api/status` warnings tell you. Do **not** improvise data — open the pre-rendered report tab instead. |
| Network dead | Irrelevant. Nothing in the demo path needs it. |

## What to leave with them

- `docs/EXPERIMENTS.md` — every measured number, wins and losses
- `docs/LIMITATIONS.md` — what it does not do
- A generated HTML report from the run they just watched
