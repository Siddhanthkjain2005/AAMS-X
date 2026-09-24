# Limitations

What AAMS-X does not do, where it loses, and which of its numbers you should not
over-read. This document exists because a system that only publishes its wins cannot be
checked.

## 1 · Scope: what this system deliberately is not

AAMS-X is an **academic active-sensing scheduler evaluated on public scientific spectrum
recordings**. It does not, and is not intended to:

| Not implemented | Why |
|---|---|
| RF transmission or jamming | Receive-only by design. There is no transmit path anywhere in the codebase |
| Real-world military-emitter identification | The data has no emitter labels, and building a classifier for one would be a different project with different ethics |
| Operational targeting | Out of scope |
| Emitter geolocation | Single-receiver recordings carry no direction information; there is no TDOA/AOA code |
| Physical hardware control | No SDR driver, no serial port, no GPIO. Nothing in AAMS-X can tune a radio |
| Tactical frequency recommendations | The output is "which slice of a recorded band to analyse next", not operational advice |

The scheduling mathematics — Thompson sampling under non-stationarity, bounded
associative recall, information-gain-guided sensing under a budget — is
domain-independent. The operational layer is absent on purpose, not for lack of time.

## 2 · Where MAG-NTS loses

Measured, 6 seeds, MAG-NTS vs NTS cumulative reward. Both tests must agree at α = 0.05.

| Scenario | Δ | Welch *p* | MWU *p* | Verdict |
|---|---|---|---|---|
| `sudden-shift` | **−50.09** | 0.00001 | 0.0022 | **significant loss** |
| `unseen-generalization` | **−69.43** | 0.0079 | 0.015 | **significant loss** |
| `recurring-environment` | −41.11 | 0.0997 | 0.093 | not significant |
| `easy-static` (SDP) | −0.028 | 0.031 | 0.065 | not significant — Welch only |

The last row is kept rather than deleted: MAG-NTS does give back detection coverage on
`easy-static` while winning reward there, and the point survives the rank test failing to
confirm it. It is listed as unconfirmed, not as a loss.

And in the ablation, the flagship component in the other direction:

| Arm | Scenario | Δ vs NTS | p |
|---|---|---|---|
| NTS+Memory | `sudden-shift` | **−85.89** | 0.0002 |
| NTS+Memory | `recurring-environment` | −25.72 | 0.202 |
| NTS+IG | `recurring-environment` | −39.09 | 0.0063 |

**The mechanism.** All the losses are multi-segment spliced scenarios where an
uncorrelated environment replaces the previous one (profile correlations −0.45, −0.37,
−0.37). Memory then retrieves a prior for a context that no longer exists, and the change
detector's `change_discount = 0.4` forgets the *Beta evidence* while leaving the
*retrieved memory prior* in place. MAG-NTS's band coverage drops to 0.696–0.741 on exactly
those scenarios — it becomes selective about regions that have stopped mattering.

**The identified fix, and why it is not implemented.** Gate the memory prior on the change
detector: suppress retrieval for a refractory period after a detected change, and require
a fresh recognition before re-applying a prior. This is a small change to
`MagNtsScheduler._terms`. It is written here rather than in the code because the failure
was found on the **held-out** `unseen-generalization` split, and changing the algorithm in
response to a held-out result is tuning on the test set. Anyone is welcome to implement it
and re-run `scripts/run_benchmark.py`; the honest procedure is to fix it, re-tune on
`train`, and report a fresh unseen number.

**Round-robin is not a straw man.** On all three spliced scenarios it has the *highest*
sustained detection probability (0.4635 / 0.4650 / 0.4927) and always achieves band
coverage 1.000, while losing badly on reward and regret. In dense environments — 30 %+
occupancy across 48 regions — systematic sweeping is a strong coverage baseline. We found
this by measuring, and it contradicts the usual framing.

## 3 · The reward function decides the ranking

The headline metric is a weighted sum, and the weighting is a modelling choice, not a
fact. Measured: at `delay = 0.10`, plain discounted Thompson sampling beats every richer
policy **while detecting 30 % fewer distinct events** — the objective collapses into
"maximise raw detections", and camping on the busiest regions wins. AAMS-X ships
`delay = 0.50` so that leaving live activity unwatched costs about what finding it earns.

Consequences you should hold onto:

- Any statement of the form "MAG-NTS is better" is implicitly "…under these five weights".
- `scripts/sensitivity.py` sweeps the weights and reports how the ranking changes.
- `aamsx/evaluation/pareto.py` avoids the scalarisation entirely, over four declared
  objectives. On `easy-static`, NTS wins detection coverage while MAG-NTS wins reward —
  two metrics, two winners, and no scalar that makes that disagreement go away.

## 4 · Labels are derived, not ground truth

No public archive of this kind carries per-emitter annotation, and absolute calibrated
power is unavailable. Occupancy is `excess > max(1.5 dB, 5σ)` against a drift-tracking P10
baseline, with σ from a first-difference MAD estimate.

- A systematic labelling bias would shift every policy equally, so **comparisons are
  sound**; **absolute** detection rates are not physical truth.
- Weak signals near the threshold are labelled by the policy, not by physics. `SSRT` was
  included precisely because it is low-contrast and stresses this.
- `p_on` / `p_off` transition rates, the periodicity ground truth and the "sustained
  event" definition are all downstream of the same label.

Every affected API response is tagged `derived-label`, and the report prints the
disclaimer in the body rather than a footnote.

## 5 · Statistical limits

- **6 seeds.** Enough to separate the effects reported as significant; **not** enough for
  effects below roughly ±20 reward. Those are reported as not significant rather than as
  small wins. `recurring-environment` (−41.11, p = 0.0997) is exactly the case where more
  seeds would settle the question.
- **Seeds vary noise and policy sampling, not environment content.** Each preset replays
  one fixed block of real measurements, so the CIs describe *stochastic policy behaviour on
  this window*, not variation across the band or across days. The randomised families
  (`POST /api/scenarios/sample`) draw different real windows per seed and are the right
  tool for the broader claim; the headline table does not use them.
- **One archive day.** Everything shipped comes from 2026-08-25 06:00 UTC. A different day
  gives different windows and the presets rebuild themselves by query, but the specific
  numbers in [EXPERIMENTS.md](EXPERIMENTS.md) are that day's.
- `compare()` returns NaN for every statistic when either arm has fewer than two finite
  values. Declining to report a p-value is intended.

## 6 · Component-level caveats

**The memory key is confounded by the policy's own behaviour.** The context vector is
built from what the scheduler observed, and what it observed is what it chose to look at.
Consequently, on `recurring-environment`, phase A′ does **not** reliably map back onto
phase A's stored prototype, even though the profiles correlate at +0.94 and even though
memory measurably helps elsewhere. The measured recovery asymmetry (249–395 steps after the
first change vs 44–59 after the return) is evidence of faster re-adaptation; it is **not**
proof that associative retrieval caused it. A behaviour-independent context descriptor is
the right fix and is not implemented.

**Periodicity is bounded by construction.** `dominant_period` searches
`[min_lag=4, n//3)`, so periods shorter than 4 steps or longer than a third of the window
are undetectable — a period is only reported where roughly four cycles could have been
observed. Separately, the autocorrelation alone does **not** reject white noise at n = 600:
it returns a non-zero lag about 93 % of the time, though with strength ≤ 0.1644. Rejection
comes from the strength scaling plus the consecutive-confirmation guard, not from the lag
test. And periodicity is never statistically significant in the ablation — but the ladder
runs on `sudden-shift`, `recurring-environment` and `high-noise`, and **not** on
`periodic-challenge`, the scenario it was selected for. That is a gap in the ablation, not
evidence the component is inert.

**Change detection is conservative.** A lone detection-rate collapse does not trip it at
`delta = 2.0`; the *spatial profile* shift is what fires it. That buys a measured
1-false-alarm-in-28-episodes rate, and it costs sensitivity to changes that alter how much
is active without altering where. On `high-noise` the detector never fires at all —
`NTS+ChangeDetection` is bit-identical to NTS, Δ = +0.00.

**Information gain is exact for the two-state model, and only that model.** `IG(a) = H(b)
− E[H(b′)|a]` is computed exactly under the Bernoulli-per-region assumption. Real spectrum
has correlated regions (adjacent channels of one wide emitter), which the model treats as
independent. IG is therefore an upper bound on the information a correlated band actually
yields.

**The budget default is a trap, documented.** `horizon × cost_per_observation` leaves no
slack for retuning, so any moving policy exhausts it before the nominal horizon unless
`budget` is set explicitly. `extreme-budget` sets 420.0 deliberately.

**Deep RL is a feature flag, not a result.** DQN/SAC live behind `AAMSX_ENABLE_DEEP_RL`
with Torch as an optional extra. They are not in the arena table and no claim is made about
them: a 1200-step episode is far less interaction than they need, and they cannot produce
the decomposition the Decision Inspector requires. `/api/status` reports
`deep_rl_available` so you can see the code is real.

## 7 · Engineering limits

- **Single-process engine.** Concurrency is asyncio plus a thread pool for batches
  (`max_concurrent_experiments = 4`). No Kafka, no Spark, no Kubernetes — deliberate, and a
  ceiling. Very large sweeps belong in `scripts/run_benchmark.py`, not the API.
- **Frames are retained in memory** per live session. Long horizons at `frame_stride = 1`
  grow linearly; the UI scrubber and the stride parameter exist for that reason.
- **The window index is a single Parquet file** read by DuckDB. Fine at 3350 rows; a
  cache 100× larger would want partitioning.
- **Latency is the one published measurement that is not reproducible.** Every reward,
  p-value and detection figure in [EXPERIMENTS.md](EXPERIMENTS.md) is a deterministic
  function of (spec, scheduler, seed) and reproduces bit-for-bit; latency is in-process
  wall-clock on a shared laptop and moved by up to 2× in the tails between two consecutive
  runs of the identical command. That is why §4 publishes p50 to two decimals, p95/p99 as
  upper bounds and the ratios between policies, instead of exact ranges. `max` values
  (~21 ms) are warm-up and GC, not steady state.
- **No authentication.** The API binds localhost and is a demo/research service. Do not
  expose it to a network without putting authentication in front of it — the report and
  dataset endpoints serve files.
- **ElectroSense is unreachable, not unimplemented.** Measured 2026-08-27:
  `api.electrosense.org` has no DNS record; `electrosense.org` resolves but presents a
  certificate for another hostname, so TLS verification fails. The adapter reports
  `unavailable` (with `verified: false` until it has actually probed) and will work
  again if the API returns. Credentials stay optional and are never logged.

## 8 · Reproducibility caveats

Replay re-executes from the stored configuration and seed and must reproduce identical
metrics — asserted by the test suite. What that does *not* survive:

- **A different cache.** A recording fetched for another archive day changes the
  environment; the `config_hash` covers the scenario spec, and the spec names
  `recording_id` and `start_step`, so a mismatch is detectable but not automatically
  repaired.
- **A different NumPy/SciPy build.** Bit-identical floating-point reduction order is not
  guaranteed across BLAS implementations. Metrics agree to reporting precision; the last
  bits may not. One test asserts a mean lies within its own min/max to a documented
  relative tolerance for exactly this reason.
- **Wall-clock latency** is machine-dependent and is stored as measured, not normalised.

## 9 · What would move the numbers most

Ranked by expected effect, from what the ablation actually shows:

1. **Gate memory retrieval on change detection** (§2). The largest measured loss in the
   project, with an understood cause.
2. **A behaviour-independent memory key** (§6). Would make the A→B→A′ recurrence claim
   testable rather than suggestive.
3. **Extend the ablation to `periodic-challenge` and `extreme-budget`**, so every component
   is measured on the scenario it was designed for.
4. **More seeds** — 20+ would settle `recurring-environment` either way.
5. **Multi-day, multi-window sampling** in the headline table, so the CIs cover environment
   variation and not only policy stochasticity.
