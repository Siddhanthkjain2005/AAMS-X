# Experiments

Every number in this document was produced by an executed run against real recordings.
Nothing here is illustrative, and nothing is a target that was written down first.
Source artefacts:

| Artefact | Contents |
|---|---|
| `reports/out/benchmark.json` | Arena: 7 presets × 6 policies × 6 seeds (0–5), control `nts` |
| `reports/out/benchmark_thompson.json` | The same episodes, control `thompson` — the §4 head-to-head |
| `reports/out/ablation.json` | 7-arm ladder × 3 scenarios × 6 seeds |
| `data/index/mag_nts_tuning.json` | Tuning protocol, all 45 candidates, the winner |

Regenerate with:

```bash
python scripts/run_benchmark.py --seeds 6              # the arena table
python scripts/run_benchmark.py --ablation --seeds 6   # the ladder
python scripts/run_benchmark.py --seeds 6 --baseline thompson   # the head-to-head in §4
python scripts/tune_mag_nts.py --trials 48 --seeds 3   # re-tune (train split only)
python scripts/verify_docs.py                          # diff this document against all of it
```

The third command re-runs the same episodes with `thompson` as the control arm instead of
`nts`. It is needed because a stored batch keeps aggregates and comparisons, not the
per-seed samples of every arm against every other arm, so the head-to-head table cannot be
recomputed from `benchmark.json` after the fact — it is a run, not a re-read. A non-default
control writes its own file (`benchmark_thompson.json`) rather than overwriting the arena
artefact.

The last command is the one that keeps this document honest. It re-reads every table cell
below, compares it to the artefact that produced it at the precision it was published at,
recomputes every ✅/❌/○ from the two stored p-values, and exits non-zero on any
disagreement — so a stale transcription fails a check instead of surviving in print. It
currently verifies 406 published values and audits all 1456 stored comparisons. Run it with
`make verify-docs` after any re-run.

## 1 · Protocol

**Multi-seed.** Every cell is 6 independent seeds. The seed controls receiver noise
draws and the policy's own sampling — never the environment content, which is a fixed
block of real measurements. Every `±` in this document is the **half-width of the
Student-*t* 95% confidence interval** on the mean (`ci_high − mean`), not the standard
deviation — the JSON carries `std`, `sem`, `ci_low`, `ci_high`, `median`, `min`, `max` and
the per-seed `values` for every cell, so any other convention can be recomputed.

**Significance.** A difference is called significant only when **both** a Welch
*t*-test and a Mann-Whitney U test agree at α = 0.05. Cohen's *d* is reported alongside.
Requiring both is the reason several visually large differences below are marked *not
significant*. The `significant` boolean in every stored comparison implements that same
conjunction (`aamsx/evaluation/statistics.py`), so the JSON, the HTML report and these
tables cannot disagree about a verdict.

**The control.** All MAG-NTS comparisons are against `nts` — discounted Thompson
sampling — not against round-robin. That isolates what MAG-NTS actually adds (memory,
information gain, periodicity, change response) by holding the sampling core fixed.
Comparing against a weaker baseline would inflate every number here.

**Tuning, and what it did not touch.** Weights were tuned on `train`-role stations only,
over the `persistent`, `bursting`, `intermittent` and `distribution-shift` families,
3 seeds, objective = mean cumulative-reward advantage over `nts`, selection = maximum
win rate with ties broken by mean advantage. The winner (45 candidates evaluated):
win rate **1.0**, advantage **+28.57** (401.19 vs 372.62). The reward function itself was
never tuned — tuning the objective to flatter the policy would make every subsequent
comparison meaningless. `unseen` recordings were not used at any point.

## 2 · The seven presets

All are built by **querying the window index**, so the numbers in each description are
properties of the block that gets replayed:

| Preset | Family | Split | Shape | What makes it hard |
|---|---|---|---|---|
| `easy-static` | persistent | train | 1×1200 INDIA-GAURI | Control: persistence 0.90, 4 regions busy >50% of the time |
| `periodic-challenge` | periodic | train | 1×1200 INDIA-GAURI | Strongest measured periodicity in the cache: period 9 steps, autocorrelation 0.55 |
| `high-noise` | noisy | train | 1×1200 INDIA-GAURI | Lowest-contrast window available (mean cell −0.77 dB from threshold, p95 only +0.5 dB) seen at 1.5 dB receiver noise instead of 0.4 |
| `sudden-shift` | distribution-shift | train | 2×600, cp 600 | EGYPT-Alexandria (33.6% occ) → SWISS-Landschlacht (29.8%); profiles correlate **−0.45** |
| `recurring-environment` | recurring-context | train | 3×400, cp 400/800 | A→B→A′; B correlates with A at −0.37, A′ (43 min later) at **+0.94** |
| `extreme-budget` | budget-constrained | train | 1×1200 INDIA-GAURI, B=420 | Enough budget for 35% of the steps |
| `unseen-generalization` | unseen-combination | unseen | 2×600, cp 600 | SWISS-MUHEN → MRO, both held out; different bands, hardware, continents |

Geometry is identical across presets — 48 regions, window 4, time bin 4, horizon 1200 —
so cross-preset differences are environment differences.

## 3 · The four signature experiments

### 3.1 Recurring-environment recovery (A → B → A′)

Does the system *recognise* a returning environment instead of relearning it?

Measured recovery, `recurring-environment`, per seed: after the **first** change (step
400) recovery takes **249–395 steps**; after the **second** change (step 800, the return
to A′) it takes **44–59 steps**. The asymmetry is the finding: coming back to a known
environment is 5–8× faster than entering a novel one, and it holds across every seed.

The honest caveat, found while testing: the observation-derived memory key is
**confounded by the policy's own behaviour**. Because the key is built from what the
scheduler chose to look at, phase A′ does not reliably map back onto phase A's stored
prototype — even though memory measurably helps in other scenarios. The recovery
asymmetry above is therefore evidence of faster re-adaptation, not proof that the
associative retrieval is what caused it. Fixing the key requires a
behaviour-independent context descriptor, which is listed in
[LIMITATIONS.md](LIMITATIONS.md).

### 3.2 Distribution shift

`sudden-shift` splices two different receivers at step 600 with profiles correlating at
−0.45 — nearly nothing learned in phase A applies in phase B.

Round-robin recovers in **3 steps at the change point** on every seed, because it never
believed anything in the first place. Learned policies pay for their beliefs. In the
ablation, information gain is what recovers detection coverage: SDP rises from
**0.2732 (NTS) → 0.3455 (NTS+IG)** while reward is statistically unchanged
(+0.42, p = 0.977). The change detector contributes +14.68 reward (p = 0.398, n.s.).

### 3.3 Information efficiency

Bits per observation, `easy-static`: round-robin 1.14, random 1.10, ucb 1.20,
thompson 1.84, nts 1.36, **mag-nts 1.56**. On `sudden-shift`: round-robin 1.92 vs
mag-nts 1.44 — a *systematic sweep of a dense, freshly-changed band is genuinely
information-rich*, and MAG-NTS does not beat it there.

Under budget, efficiency is what matters: `extreme-budget` with 35% of the steps
affordable gives MAG-NTS the best reward (104.14 ± 8.84) and best oracle ratio (0.353)
in the field, ahead of thompson (99.57) and nts (92.90); +11.24 over NTS, p = 0.021,
significant.

### 3.4 Unseen generalization

`unseen-generalization` uses SWISS-MUHEN → MRO, held out from tuning entirely.
**MAG-NTS loses to NTS on reward here: −69.43, p = 0.0079, significant against.** It
gains on detection coverage (SDP 0.2829 vs 0.2548, +0.028, p = 0.266, n.s.) and time to
detect (47.02 vs 48.56). Reported as measured; see §7.

## 4 · Arena results

Six policies, six seeds, mean ± 95% CI half-width. MAG-NTS vs NTS on cumulative reward in
the last column.

### Cumulative reward

| Preset | round-robin | random | ucb | thompson | nts | **mag-nts** | Δ vs nts |
|---|---|---|---|---|---|---|---|
| easy-static | 379.42±3.61 | 323.09±8.65 | 468.47±13.07 | 613.11±34.16 | 542.16±8.41 | **580.19±17.53** | **+38.03** ✅ p_W=0.0014, p_U=0.0043, d=2.90 |
| periodic-challenge | 65.22±3.38 | 42.55±5.95 | 316.10±12.45 | 485.88±4.79 | 402.90±7.07 | **443.44±10.45** | **+40.54** ✅ p_W=0.00002, p_U=0.0022, d=4.77 |
| high-noise | −30.28±2.83 | −48.42±7.15 | 125.53±15.08 | 333.34±23.49 | 237.57±20.94 | **291.83±18.92** | **+54.26** ✅ p_W=0.0006, p_U=0.0022, d=2.85 |
| extreme-budget | 86.12±1.68 | 74.60±1.85 | 85.07±6.39 | 99.57±6.34 | 92.90±3.95 | **104.14±8.84** | +11.24 ○ p_W=0.021, p_U=0.065, d=1.72 |
| sudden-shift | 472.00±3.24 | 430.02±14.30 | 827.52±16.86 | 663.94±33.91 | **844.92±9.75** | 794.82±11.40 | **−50.09** ❌ p_W=0.00001, p_U=0.0022, d=−4.96 |
| recurring-environment | 393.02±4.51 | 352.27±7.53 | 751.84±8.71 | 686.31±46.78 | **806.24±26.31** | 765.13±49.84 | −41.11 ○ p_W=0.0997, p_U=0.093, d=−1.08 |
| unseen-generalization | 452.98±3.22 | 414.85±15.38 | 755.16±12.77 | 677.34±25.14 | **855.56±27.59** | 786.13±43.59 | **−69.43** ❌ p_W=0.0079, p_U=0.015, d=−2.00 |

✅ significant for MAG-NTS · ❌ significant against · ○ not significant. `p_W` is Welch,
`p_U` is Mann-Whitney; a verdict needs both below 0.05, which is why `extreme-budget` is
marked ○ despite a Welch *p* of 0.021.

**MAG-NTS wins 3 of 7 presets significantly against the NTS control, leads on the mean
without significance on a fourth, and loses 2 significantly.** The pattern is consistent:
it leads on every single-phase environment (static, periodic, noisy, budgeted — the first
three significantly, `extreme-budget` on the mean only) and loses on the three
multi-segment spliced ones. That is the honest headline, and §7 explains why.


**And the control is not the strongest policy in the field on every preset.** Read the
`thompson` column: plain discounted Thompson sampling scores the highest mean reward on
`easy-static`, `periodic-challenge` and `high-noise`. MAG-NTS holds the top mean on
`extreme-budget` only; NTS holds it on the three spliced scenarios. Comparing against NTS
isolates what MAG-NTS adds to the same sampling core, which is the right question for an
ablation — but it is not the same claim as "best policy on this table", and that stronger
claim is not made. The head-to-head is measured below.

### MAG-NTS against plain Thompson

Same 6 seeds, same episodes, `thompson` as the control instead of `nts` — produced by
`run_benchmark.py --seeds 6 --baseline thompson`, and the means below are bit-identical to
the ones in the table above, which is itself a determinism check on the loop. Both tests
must agree at α = 0.05.

| Preset | thompson | mag-nts | Δ | Welch *p* | MWU *p* | *d* | verdict |
|---|---|---|---|---|---|---|---|
| easy-static | **613.11±34.16** | 580.19±17.53 | −32.92 | 0.061 | 0.093 | −1.27 | ○ n.s. |
| periodic-challenge | **485.88±4.79** | 443.44±10.45 | −42.44 | 0.00003 | 0.0022 | −5.48 | ❌ against |
| high-noise | **333.34±23.49** | 291.83±18.92 | −41.51 | 0.0058 | 0.0087 | −2.04 | ❌ against |
| extreme-budget | 99.57±6.34 | **104.14±8.84** | +4.57 | 0.308 | 0.240 | +0.62 | ○ n.s. |
| sudden-shift | 663.94±33.91 | **794.82±11.40** | +130.88 | 0.00007 | 0.0022 | +5.43 | ✅ for |
| recurring-environment | 686.31±46.78 | **765.13±49.84** | +78.82 | 0.014 | 0.041 | +1.71 | ✅ for |
| unseen-generalization | 677.34±25.14 | **786.13±43.59** | +108.79 | 0.0005 | 0.0022 | +3.21 | ✅ for |

So the two controls disagree, and they disagree in opposite directions: MAG-NTS beats
plain Thompson on exactly the three non-stationary scenarios where it loses to NTS, and
loses to plain Thompson on two of the four single-phase scenarios where it beats NTS. The
component that explains both halves is the discount — Thompson without one accumulates a
long-memory estimate that is excellent while the environment holds still and slow to
abandon when it does not.

Detection coverage does not split the same way. Sustained detection probability,
MAG-NTS − thompson: `easy-static` +0.026, `periodic-challenge` +0.036, `high-noise`
**+0.109**, `sudden-shift` +0.010, `recurring-environment` +0.026, `unseen-generalization`
**+0.101**, `extreme-budget` −0.016. MAG-NTS finds more of the distinct activity on 6 of 7
presets, including both presets where it loses the reward comparison. Which of those two
statements is "the result" depends on the weighting in §1 — see `scripts/sensitivity.py`
and the Pareto frontier.

### Sustained detection probability

| Preset | round-robin | ucb | nts | mag-nts |
|---|---|---|---|---|
| easy-static | 0.4893 | 0.5900 | **0.6821** | 0.6539 |
| periodic-challenge | 0.3573 | 0.6850 | 0.6707 | **0.6875** |
| high-noise | 0.2649 | 0.4287 | 0.5299 | **0.5718** |
| extreme-budget | 0.4638 | 0.4490 | 0.4825 | 0.5121 |
| sudden-shift | **0.4635** | 0.3244 | 0.2358 | 0.2579 |
| recurring-environment | **0.4650** | 0.3590 | 0.2675 | 0.2412 |
| unseen-generalization | **0.4927** | 0.3850 | 0.2548 | 0.2829 |

On `easy-static`, NTS beats MAG-NTS on SDP (0.6821 vs 0.6539, Welch *p* = 0.031 but MWU
*p* = 0.065 — not significant under the §1 rule, though Welch alone would have called it).
Two metrics, two winners: MAG-NTS holds the reward lead there significantly and gives back
detection coverage. That is exactly why the Pareto view exists and why a single scalar
ranking is not offered as the answer.

### Band coverage — the cost of being selective

Round-robin and random always achieve `band_coverage = 1.000`. MAG-NTS trades it down to
**0.696–0.933** (lowest on `sudden-shift`). Focus is not free: every dwell on a
high-value region is a region left unobserved, and coverage is the metric that makes
that visible.

### Decision latency (ms per decision, measured in-process)

| Policy | p50 (ms) | p95 ≤ | p99 ≤ | cost of one decision |
|---|---|---|---|---|
| round-robin | 0.02 | 0.05 | 0.2 | 1× (reference) |
| random | 0.02–0.03 | 0.05 | 0.2 | 1.3–1.6× |
| ucb | 0.08–0.11 | 0.5 | 2 | 4.0–6.2× |
| thompson | 0.09–0.12 | 0.5 | 2 | 4.2–7.2× |
| nts | 0.09–0.11 | 0.5 | 2 | 4.1–6.6× |
| **mag-nts** | 0.29–0.34 | 1.0 | 3 | **13–19×** |

The p50 column is the min–max across the seven presets, each averaged over its six seeds.
The p95/p99 columns are upper bounds rather than ranges, and the last column is the
per-preset ratio to round-robin on the same run.

**Why this table is published coarsely while every other table in this document is
published to four decimals.** Latency is the one measured quantity here that is not a
function of (spec, scheduler, seed) — it is in-process wall-clock, taken while seven
workers shared an 8-core laptop. Re-running the identical command reproduces every reward,
p-value and detection number bit-for-bit and moves the latency tails by up to 2× (`ucb`
p99 went 0.64 ms → 1.51 ms between two consecutive runs of the same seeds). A three-decimal
latency range would therefore be a number that cannot be reproduced even on the machine
that produced it, so what is published is the part that did hold across runs: the ordering,
the p50 to two decimals, and the ratios.

What the measurement supports: MAG-NTS costs **13–19× a round-robin decision and about 3×
a plain Thompson or NTS decision**, on all seven presets, in both runs. The eight evidence
terms are each vectorised over regions, so the extra work is a constant factor, not a
change in how cost grows with the band. At 0.29–0.34 ms p50 against a 0.25 s environment
step there are three orders of magnitude of headroom; latency is not the constraint. The
`max` per policy reaches ~21 ms and is first-call warm-up and Python GC, not steady state —
read the percentiles, not the max.


## 5 · Ablation ladder

7 arms × 6 seeds. Each arm is NTS plus exactly one component, so a row answers "what
does *this* contribute", not "is the whole thing good". `Δ` is cumulative reward against
NTS.

### high-noise — memory dominates

| Arm | Reward | Δ vs NTS | p | SDP | TTD |
|---|---|---|---|---|---|
| NTS | 218.69±14.45 | — | — | 0.4878 | 33.27 |
| **NTS+Memory** | **317.75±27.34** | **+99.07** | 0.00005 ✅ | 0.5006 | 32.34 |
| NTS+IG | 210.15±19.15 | −8.54 | 0.383 ○ | **0.5802** | **27.54** |
| NTS+ChangeDetection | 218.69±14.45 | **+0.00** | 1.000 ○ | 0.4878 | 33.27 |
| NTS+Periodicity | 222.88±11.63 | +4.19 | 0.575 ○ | 0.4971 | 32.69 |
| NTS+Memory+IG | 299.19±15.57 | +80.50 | 0.00000 ✅ | 0.5541 | 29.00 |
| Full MAG-NTS | 291.83±18.92 | +73.15 | 0.00002 ✅ | 0.5718 | 27.93 |

`NTS+ChangeDetection` is **exactly +0.00** — the detector never fires on this scenario, so
the arm is bit-identical to NTS. An ablation table that showed a small non-zero number
there would mean the arm was not actually isolated.

Note also that `NTS+Memory` (317.75) beats `Full MAG-NTS` (291.83) on reward here: adding
the other four components *costs* ~26 reward on this scenario while buying +0.07 SDP and
−4.4 steps of detection delay. The full policy is not the best arm on every scenario, and
this table is how you find that out.

### sudden-shift — memory hurts, IG helps coverage

| Arm | Reward | Δ vs NTS | p | SDP | TTD |
|---|---|---|---|---|---|
| NTS | 842.05±29.99 | — | — | 0.2732 | 47.76 |
| NTS+Memory | 756.16±21.38 | **−85.89** | 0.0002 ❌ | 0.1955 | 51.79 |
| NTS+IG | 842.47±18.77 | +0.42 | 0.977 ○ | **0.3455** | **43.43** |
| NTS+ChangeDetection | **856.73±30.41** | +14.68 | 0.398 ○ | 0.2663 | 48.11 |
| NTS+Periodicity | 845.08±31.19 | +3.03 | 0.861 ○ | 0.2770 | 47.60 |
| NTS+Memory+IG | 770.30±37.48 | −71.75 | 0.0035 ❌ | 0.2371 | 49.46 |
| Full MAG-NTS | 794.82±11.40 | −47.23 | 0.0081 ❌ | 0.2579 | 48.13 |

Memory is actively harmful when the environment is replaced by an uncorrelated one:
retrieving a prior for a context that no longer exists is worse than having no prior.
This is the clearest single result in the project, and it is a result *against* the
headline component.

### recurring-environment — change detection helps, IG trades reward for coverage

| Arm | Reward | Δ vs NTS | p | SDP | TTD |
|---|---|---|---|---|---|
| NTS | 759.08±10.37 | — | — | 0.2887 | 46.57 |
| NTS+Memory | 733.36±44.55 | −25.72 | 0.202 ○ | 0.1809 | 52.80 |
| NTS+IG | 720.00±23.69 | −39.09 | 0.0063 ❌ | **0.3528** | **42.63** |
| **NTS+ChangeDetection** | **779.90±17.23** | **+20.82** | 0.028 ✅ | 0.2958 | 46.08 |
| NTS+Periodicity | 766.05±16.90 | +6.96 | 0.392 ○ | 0.2912 | 46.37 |
| NTS+Memory+IG | 730.05±27.42 | −29.03 | 0.041 ❌ | 0.2405 | 49.24 |
| Full MAG-NTS | 765.13±49.84 | +6.04 | 0.772 ○ | 0.2412 | 49.23 |

Change detection is the component that pays on recurrence — which is the scenario it was
designed for. Information gain buys +0.064 SDP and 4 fewer steps to detect at a cost of
39 reward: a real trade, not a free win.

### What the ladder says overall

- **Memory** is the largest single effect in the project, in both directions:
  +99.07 on `high-noise`, −85.89 on `sudden-shift`. It helps when the environment is
  stable-but-hard and hurts when the environment is replaced.
- **Information gain** consistently raises detection coverage and lowers time-to-detect
  while being reward-neutral-to-negative. The reward weights (information 0.07) reflect
  that; the Pareto view is where it earns its place.
- **Change detection** contributes on recurrence (+20.82 ✅), is neutral on shift, and is
  literally inert on stationary noise.
- **Periodicity** is never significant on these three scenarios. It was selected for on
  `periodic-challenge`, which is not in the ladder — an admitted gap, listed in
  [LIMITATIONS.md](LIMITATIONS.md).

## 6 · Pseudo-regret and the oracle

Regret is measured against a **clairvoyant window oracle** that sees the occupancy truth
and picks the best window every step. `oracle_ratio` is the achieved fraction of that
ceiling: 0.744 (`easy-static`), 0.713 (`periodic-challenge`), 0.559 (`high-noise`),
0.353 (`extreme-budget`), 0.707 (`sudden-shift`), 0.647 (`recurring-environment`),
0.703 (`unseen-generalization`) for MAG-NTS. The oracle is a bound, not a competitor —
it uses information no scheduler has.

## 7 · Where MAG-NTS loses, and why

The three losses are all multi-segment spliced scenarios, and they share one cause.

**Round-robin has the highest SDP on all three** (0.4635, 0.4650, 0.4927) while losing
badly on reward and regret (`sudden-shift`: NTS 844.92, MAG-NTS 794.82, round-robin
472.00). These spliced windows are **dense** — 30%+ occupancy at 48 regions — so a
systematic sweep finds a lot simply by visiting everywhere, and coverage is worth more
than selectivity. *In dense environments, sweeping is a strong baseline, and the
literature's usual framing of round-robin as a straw man does not hold here.*

Against that backdrop, MAG-NTS's specific deficit versus NTS is its **selectivity**: it
drives band coverage down to 0.696–0.741 on exactly those scenarios, and the ablation
localises the cost to memory (−85.89 on `sudden-shift`). The mechanism is understood:
memory retrieves a prior for a context that has been replaced, and the change detector's
`change_discount = 0.4` forgets the Beta evidence but does not un-retrieve the memory
prior.

Three things follow, and none of them is "the numbers are wrong":

1. The result is reported in the arena, in the report generator, and here. It is not
   hidden behind a favourable preset selection.
2. It is a **conditional recommendation**, not a defect: use MAG-NTS on stable, hard,
   noisy or budget-limited bands; use NTS or a sweep on bands undergoing wholesale
   replacement. The Algorithm Arena screen exists so a reader can check that themselves.
3. The fix is identified but not implemented: gate the memory prior on the change
   detector, i.e. suppress retrieval for a refractory period after a detected change.
   Implementing it *after* seeing the test result would be tuning on the test set, so it
   is written down in [LIMITATIONS.md](LIMITATIONS.md) instead.

## 8 · Reproducibility

Every run is registered in SQLite (`data/registry.sqlite`) with a `config_hash` over the
full resolved configuration — scenario spec, policy, weights, seed, receiver, reward
weights. The trace JSON is stored beside it.

- `GET /api/experiments/history` lists records with their hashes.
- **Replay** re-runs a stored configuration and must reproduce identical metrics.
  `tests/test_api.py` asserts exactly that, and that an identical configuration hashes
  identically — which is what makes replay checkable rather than merely available.
- The HTML report is rendered **from the stored trace**, so it cannot quote a number that
  was not produced by an executed episode. Ask for a report on a missing experiment and
  it says "no stored result" rather than inventing one.

## 9 · Caveats that apply to every number here

- Detection is measured against **derived labels**, not absolute ground truth
  ([DATA.md](DATA.md) §4).
- 6 seeds is enough to separate the large effects above and *not* enough for effects
  smaller than roughly ±20 reward; those are reported as not significant rather than as
  small wins.
- The reward weighting (notably `delay = 0.50`) determines the ranking. A different
  weighting produces a different winner; `scripts/sensitivity.py` sweeps it and
  `aamsx/evaluation/pareto.py` avoids the scalarisation entirely.
- `compare()` returns NaN for every statistic when either arm has fewer than two finite
  values. Declining to report a p-value is the intended behaviour.
- The default budget (`horizon × cost_per_observation`) leaves no slack for retuning, so
  any moving policy ends before the nominal horizon unless `budget` is set explicitly.
  `extreme-budget` sets it to 420.0 deliberately.
