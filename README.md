# 🛰️ AAMS-X — Adaptive Associative Active-Sensing & Memory Scheduler

## 📋 Table of Contents

- [What is This Project About? (The Big Picture)](#-what-is-this-project-about-the-big-picture)
- [The Real-World Problem It Solves](#-the-real-world-problem-it-solves)
- [How AAMS-X Solves It — The Core Idea](#-how-aams-x-solves-it--the-core-idea)
- [The Complete Decision Loop — Step by Step](#-the-complete-decision-loop--step-by-step)
- [Key Algorithms Explained Like You're 5](#-key-algorithms-explained-like-youre-5)
- [Architecture — How the Code is Organized](#-architecture--how-the-code-is-organized)
- [Repository Map — Every File and Folder Explained](#-repository-map--every-file-and-folder-explained)
- [The Data — Where It Comes From and What It Looks Like](#-the-data--where-it-comes-from-and-what-it-looks-like)
- [The 6 Scheduling Policies (Algorithms) Compared](#-the-6-scheduling-policies-algorithms-compared)
- [The 7 Experiment Scenarios](#-the-7-experiment-scenarios)
- [The Experiment Results — What Was Found](#-the-experiment-results--what-was-found)
- [The Web Frontend — What You See](#-the-web-frontend--what-you-see)
- [The REST API — How Frontend Talks to Backend](#-the-rest-api--how-frontend-talks-to-backend)
- [Configuration and Environment Variables](#-configuration-and-environment-variables)
- [Setup and Installation — Getting It Running](#-setup-and-installation--getting-it-running)
- [Running with Docker](#-running-with-docker)
- [The Test Suite — How Quality is Ensured](#-the-test-suite--how-quality-is-ensured)
- [Key Technical Concepts Glossary](#-key-technical-concepts-glossary)
- [Limitations — Where It Falls Short](#-limitations--where-it-falls-short)
- [What This Project Is NOT](#-what-this-project-is-not)
- [Credits and License](#-credits-and-license)

---

## 🎯 What is This Project About? (The Big Picture)

**SIH26055 — Smart Scan Strategy for Electronic Warfare**

Imagine you have a radio that can only listen to **one small slice** of a huge radio frequency band at a time. There are signals popping up all over the band — some stay for a long time, some appear and disappear quickly, some come back in patterns. Your job is to decide **where to point your radio next** so you catch as much activity as possible, without wasting time on empty channels.

That's exactly what **AAMS-X** does. It is an **intelligent scheduling system** that decides which part of the radio spectrum to observe at each moment, learns from what it sees, and gets smarter over time.

> **Think of it like this:** You're a security guard with one camera in a building with 48 rooms. You can only watch 4 rooms at a time through the camera feed. Some rooms have activity, some don't. You need to figure out **which 4 rooms to watch next** to catch the most action. AAMS-X is the brain that makes that decision.

### Why is this project important?

In **electronic warfare (EW)** and **spectrum monitoring**, military or civilian receivers need to scan huge bands of radio frequencies. But the receiver hardware can physically only tune to a small window at any moment. Choosing WHERE to look is called **the scan scheduling problem**, and it's one of the hardest problems in signal intelligence.

AAMS-X tackles this using modern AI techniques — combining statistics, memory systems, information theory, and decision-making algorithms into one explainable system.

---

## 🔍 The Real-World Problem It Solves

### The Core Challenge: Partial Observability

Here is the problem stated precisely:

| Property | Description |
|---|---|
| **Band** | A wide radio frequency band divided into **R = 48 regions** |
| **Window** | You can observe only **W = 4 contiguous regions** per step |
| **Activity** | Signals appear/disappear across the band — you can't see what you're not watching |
| **Budget** | You have a limited number of observations you can make |
| **Switching Cost** | Moving the receiver to a different part of the band takes effort |
| **Goal** | Find as much activity as possible, as quickly as possible |

This is a type of problem called a **Multi-Armed Bandit (MAB)** — specifically a **non-stationary, restless, windowed bandit** under partial observability.

### What Makes It Hard?

1. **You can't see everything at once** — out of 48 regions, you can only watch 4
2. **Activity changes over time** — what was busy a minute ago might be quiet now
3. **Patterns exist but are hard to find** — some signals come back periodically
4. **The environment can shift dramatically** — the entire activity profile might change
5. **Every observation costs something** — you have a limited budget
6. **You must explain your decisions** — a black box is not acceptable

---

## 🧠 How AAMS-X Solves It — The Core Idea

AAMS-X uses an algorithm called **MAG-NTS** (Memory-Augmented, Information-Guided Non-Stationary Thompson Sampling). Let's break that name down:

| Part | Meaning |
|---|---|
| **Memory-Augmented** | It remembers situations it has seen before and uses that experience |
| **Information-Guided** | It picks observations that will teach it the most |
| **Non-Stationary** | It knows the world changes over time and adapts |
| **Thompson Sampling** | It uses a proven statistical method for exploration vs. exploitation |

### The One-Line Summary

> MAG-NTS combines **what it thinks is active** (belief), **what it doesn't know** (uncertainty), **what it remembers** (memory), **what it expects to learn** (information gain), **what patterns it detects** (periodicity), and **what has changed** (change detection) into a single score for every possible observation window, then picks the best one.

---

## 🔄 The Complete Decision Loop — Step by Step

Every single "step" in AAMS-X follows this loop. Here's what happens, in order:

```
┌──────────────────────────────────────────────────────────────────┐
│  Step 1: OBSERVE          │  Look at the 4 chosen regions       │
│  Step 2: ENCODE           │  Extract features from observation  │
│  Step 3: INFER            │  Update beliefs about all regions   │
│  Step 4: REMEMBER         │  Check if this situation looks      │
│                           │  familiar from memory               │
│  Step 5: ESTIMATE         │  Calculate uncertainty for each     │
│          UNCERTAINTY      │  region                             │
│  Step 6: PREDICT          │  Detect periodic patterns and       │
│                           │  sudden changes                     │
│  Step 7: VALUE            │  Calculate how much information     │
│          INFORMATION      │  each window would give             │
│  Step 8: SELECT           │  Score all windows, pick the best   │
│  Step 9: GET FEEDBACK     │  Learn what was actually there      │
│  Step 10: ADAPT           │  Update memory and parameters       │
│                           │                                     │
│  → Go back to Step 1      │                                     │
└──────────────────────────────────────────────────────────────────┘
```

### Detailed Walkthrough of One Step

**Step 1 — Observe:** The receiver tunes to a 4-region window (e.g., regions 20-23 out of 48). It measures the signal power in each region. Some will have signals (occupied), some won't.

**Step 2 — Encode:** The temporal encoder creates a "summary" of the current situation — how much activity there has been recently, whether it's increasing or decreasing, how concentrated the activity is across the band, etc. This produces ~18 named features like `activity_rate`, `spatial_concentration`, and `profile_drift`.

**Step 3 — Infer (Belief Filter):** For every region (all 48), the system maintains a **belief** — its best guess of whether that region is occupied or not. Regions it just observed get updated directly. Regions it *didn't* observe slowly drift toward their historical average activity rate (so a region that's usually busy stays a reasonable bet even when not watched).

**Step 4 — Remember (Associative Memory):** The system compares the current situation to stored "prototypes" — memories of previous situations. If the current context looks like something it's seen before (similarity > 0.90), it retrieves the action preferences that worked last time. This is what lets it skip re-learning when a familiar environment returns.

**Step 5 — Estimate Uncertainty:** For each region, two types of uncertainty are computed:
- **Aleatoric** (irreducible): How unpredictable is this region inherently? (A 50/50 region is maximally uncertain)
- **Epistemic** (reducible): How little have we looked at this region? (A region we haven't visited in 100 steps has high epistemic uncertainty)

**Step 6 — Predict:** Two sub-systems run:
- **Periodicity Engine:** Looks for recurring patterns (e.g., "this region is active every 9 steps")
- **Change Detector:** Checks if the overall activity pattern has suddenly shifted (using Page-Hinkley and EWMA statistical tests)

**Step 7 — Value Information:** For every possible observation window, compute the **expected information gain** — how many "bits" of uncertainty would be resolved. Mathematically: `IG(a) = H(b) − E[H(b′) | a]`. In plain English: "How much would I learn if I looked here?"

**Step 8 — Select (MAG-NTS Scoring):** Every possible window position gets scored using 8 weighted terms:

```
score(window) =  0.94 × detection          (sampled activity estimate)
               + 0.07 × information         (expected learning value)
               + 0.57 × memory              (similarity-weighted prior)
               + 0.27 × periodicity         (recurrence pattern score)
               + 0.23 × uncertainty         (exploration incentive)
               + 0.17 × recency            (how stale is this region?)
               − 0.29 × cost               (sensing/retuning expense)
               − 0.10 × switching           (penalty for moving far)
```

The window with the **highest score** is chosen.

**Step 9 — Get Feedback:** The environment reveals what was actually there (in the observed window only — you never learn about regions you didn't observe). This computes reward based on hits, misses, false alarms, delay cost, and switching cost.

**Step 10 — Adapt:** The system updates its internal state: Beta distribution parameters are updated, memory prototypes are adjusted, and change/periodicity detectors ingest new data.

---

## 🎓 Key Algorithms Explained Like You're 5

### 1. Thompson Sampling — The Foundation

**Analogy:** Imagine you're choosing between 48 slot machines. Each time you pull one, you learn a bit more about whether it pays out. Thompson Sampling works like this:

1. For each machine, keep track of "wins" (α) and "losses" (β)
2. Before choosing, randomly sample from each machine's "luck distribution" (Beta distribution)
3. Pick the machine whose random sample came out highest
4. Over time, machines that win a lot get higher samples, but there's always a chance you'll try a less-known one (exploration)

**Why it works:** It naturally balances **exploitation** (choosing what seems best) with **exploration** (trying things you're unsure about). The randomness is the magic — it prevents you from getting stuck.

### 2. Non-Stationarity — Handling Change

**The problem with regular Thompson Sampling:** It remembers everything equally. If a slot machine was great for 1000 pulls and then stopped paying out, it would take hundreds of pulls to realize things changed.

**The fix — Geometric Discounting:** At every step, all past evidence is multiplied by `discount = 0.995`. This means:
- Yesterday's evidence counts as 99.5% of today's
- Evidence from 100 steps ago counts as 0.995^100 ≈ 60.6%
- Evidence from 500 steps ago counts as 0.995^500 ≈ 8.2%

This makes the system **forgetful enough to adapt** but **remember enough to be stable**.

### 3. Belief Filter — What Do I Think Is Out There?

For each of the 48 regions, the system maintains a **belief** — a probability between 0 and 1 that the region is currently occupied.

**How beliefs update for observed regions:**
The raw measurement is converted to a likelihood ratio using the normal cumulative distribution function Φ. A strong signal (+6 dB) pushes belief strongly toward "occupied", while a weak signal (+0.3 dB) barely moves it. This soft updating is what makes it graceful — unlike a hard threshold that would say "occupied/not-occupied" with no nuance.

**How beliefs evolve for unobserved regions:**
Using a two-state Markov chain: a region's belief drifts toward its historical activity rate. If a region is usually 80% busy, its belief slowly drifts back toward 0.8 when you're not watching it. This is much smarter than just decaying toward 0.5 (which would say "I have no idea"), because it uses what you've learned about each region's character.

### 4. Associative Memory — "I've Seen This Before!"

**Analogy:** Imagine a chess grandmaster who has memorized thousands of board positions. When they see a new position, they don't calculate from scratch — they recognize it as similar to a known pattern and apply the strategy that worked before.

AAMS-X uses a **Modern Hopfield Network** — a type of associative memory that stores up to 24 "prototypes" (remembered situations). When a new situation comes in:

1. Compute similarity to all stored prototypes (using cosine similarity)
2. If the best match is > 0.90, the situation is "recognised" and the corresponding action preference is retrieved
3. If the best match is < 0.88, a new prototype is written (the system has learned a new type of situation)
4. Between 0.88 and 0.90, the nearest existing prototype is updated

**Why 24 prototypes maximum?** An unlimited memory would be a lookup table, not generalization. The limit forces the system to learn *categories* of situations, not individual moments.

### 5. Change Detection — "Something Just Changed!"

Two statistical detectors run in parallel:

**Page-Hinkley:** Tracks cumulative deviation. Like a bank account of "surprise" — if surprises keep piling up in the same direction, something has changed.

**EWMA (Exponentially Weighted Moving Average):** Tracks the signal level with exponential smoothing. If the smoothed level crosses 4 standard deviations from the mean for 3 consecutive steps, something has changed.

Both detectors must agree, and there's a 90-step refractory period (cooldown) to prevent false alarms.

**When a change is detected:** The system "forgets" 60% of its learned evidence (`change_discount = 0.4`) and boosts exploration, so it can quickly learn the new environment.

### 6. Information Gain — "Where Would I Learn the Most?"

For each possible observation window, the system computes:

```
IG(window) = Current uncertainty − Expected uncertainty after observing
```

Mathematically: `IG(a) = H(b) − E[H(b′) | a]`

**In plain English:** "If I look here, how much of my uncertainty will go away?"

This is computed **exactly** (not approximately) for the two-state model. Key properties:
- IG is always ≥ 0 (looking can never make you MORE confused)
- IG is highest for regions with beliefs near 0.5 (maximum uncertainty)
- A useless sensor (equal sensitivity and false-alarm rate) gives IG = 0

### 7. Periodicity Detection — "This Happens Every N Steps"

Uses **prominence-gated autocorrelation**: compute the autocorrelation of a region's activity signal, look for peaks that are both tall enough (above a Bartlett significance bound) and prominent enough (min_prominence = 0.12).

**Limitations by design:** Periods shorter than 4 steps or longer than 1/3 of the observation window are undetectable — the system honestly declares this rather than hallucinating patterns.

---

## 🏗️ Architecture — How the Code is Organized

AAMS-X is built in **5 layers**, each with a clear responsibility:

```
┌─────────────────────────────────────────────────────────┐
│ LAYER 5: DELIVERY                                       │
│   FastAPI REST API  →  WebSocket streaming  →  React UI │
├─────────────────────────────────────────────────────────┤
│ LAYER 4: MEASUREMENT                                    │
│   Runner  →  Metrics  →  Multi-seed Statistics  →       │
│   Pareto Frontier  →  HTML Report                       │
├─────────────────────────────────────────────────────────┤
│ LAYER 3: THE SCHEDULER (the core loop)                  │
│   Belief → Encoder → Memory → Change Detector →        │
│   Periodicity → Information Gain → MAG-NTS Select       │
├─────────────────────────────────────────────────────────┤
│ LAYER 2: ENVIRONMENT (replay only)                      │
│   Scenario Spec → Region Grid → Replay Environment →   │
│   Derived Truth + Receiver Model                        │
├─────────────────────────────────────────────────────────┤
│ LAYER 1: INGESTION (run once, offline)                  │
│   e-CALLISTO FITS Archive → Calibration → Parquet Cache │
│   → Window Index (DuckDB)                               │
└─────────────────────────────────────────────────────────┘
```

### Key Design Principles

1. **No simulated data anywhere.** Every experiment replays real radio recordings. If data is missing, the system errors loudly — it never silently substitutes synthetic data.

2. **Leakage prevention by construction.** The scheduler **never has a handle to the environment**. It receives a `DecisionContext` (containing only things it has observed) and returns an `ActionProposal`. Three mechanisms enforce this:
   - No handle (the scheduler function signature makes leakage impossible)
   - Sealing (accessing truth outside the scoring path raises `LeakageError`)
   - Freezing (arrays in the context are read-only — mutating them raises an error)

3. **Reproducibility.** Every run is stored with a `config_hash` (SHA-256 of the full configuration). Two runs with the same hash produce byte-identical results. Replay re-executes, not re-renders.

4. **Explainability is structural.** Every decision carries a full decomposition of the 8 scoring terms, human-readable notes, and per-region values. Nothing is reconstructed after the fact.

---

## 📁 Repository Map — Every File and Folder Explained

### Root Files

| File | What It Does |
|---|---|
| `pyproject.toml` | **The project's birth certificate.** Defines the package name (`aamsx`), version (`1.0.0`), Python version (≥3.12), all dependencies, dev tools (pytest, ruff, mypy), and the CLI entry point. Uses `hatchling` as the build system. |
| `Dockerfile` | **Multi-stage Docker build.** Stage 1 (`build`) installs dependencies in a virtual environment. Stage 2 (`runtime`) copies just the venv and code — no build tools. Runs as unprivileged user `aamsx`. Healthcheck pings `/api/health`. |
| `docker-compose.yml` | **Full stack orchestration.** Defines `api` (backend on port 8000), `web` (frontend on port 5173), and three one-shot jobs: `fetch` (download data), `index` (build window index), `benchmark` (run experiments). |
| `docker-compose.aws.yml` | AWS-specific overrides for production deployment. |
| `Makefile` | **One command per task.** `make setup` installs, `make data` downloads recordings, `make index` builds the window index, `make test` runs 440 tests, `make api` starts the server, `make benchmark` runs experiments. Type `make` alone to see all available commands. |
| `.env.example` | **Every configuration option documented.** Copy to `.env` to override. Nothing secret is required — the full demo runs with defaults. |
| `.gitignore` | Excludes `.env` files, Python caches, `node_modules`, IDE settings, and build artifacts. |

### `aamsx/` — The Python Package (Core Brain)

#### Top-level files

| File | Purpose |
|---|---|
| `__init__.py` | Package marker (mostly empty) |
| `config.py` | **Central configuration.** Uses Pydantic Settings to load from environment variables with `AAMSX_` prefix. Defines all paths (`data_dir`, `cache_dir`, `index_dir`, etc.), ingestion settings, calibration constants, experiment engine settings, and API config. `get_settings()` is a cached singleton. |
| `cli.py` | **Command-line interface.** Entry point `aamsx` — can run experiments, generate reports, inspect the registry, and more. |
| `logging.py` | Structured logging setup with configurable levels. |
| `version.py` | Version string — `1.0.0` |

#### `aamsx/contracts/` — The Language of the System

These are the **typed data structures** that every module agrees on. They define what flows between components.

| File | What It Defines |
|---|---|
| `observation.py` | **`Observation`** — what the receiver saw (regions, detected signals, margin in dB, availability). **`Feedback`** — scored outcome (true occupancy, reward terms, hits, misses, false alarms). **`DecisionContext`** — everything the scheduler needs to decide (belief, uncertainty, staleness, information gain, periodicity score, memory similarity, sensing cost, budget remaining, etc.). **`ActionProposal`** — the scheduler's decision (chosen regions, value, 8-factor decomposition, per-region values, notes). |
| `scenario.py` | **`ScenarioSpec`** — defines an experiment scenario (segments of recordings to replay, receiver config, reward weights, budget). **`ReceiverConfig`** — receiver parameters (window size, noise, cost). **`RewardWeights`** — the 5 reward terms. |
| `spectrum.py` | **`SpectrogramSlice`** — a chunk of real spectrum data. **`CalibrationResult`** — baseline, noise, thresholds per channel. |

#### `aamsx/datasets/` — Getting Real Data

| Submodule | What It Does |
|---|---|
| `callisto.py` | **e-CALLISTO adapter.** Downloads FITS files from the public solar radio archive, parses them, concatenates 15-minute files into continuous recordings. |
| `calibration.py` | **Measurement → labels.** Computes baseline (P10 per 10-min block), noise (first-difference MAD), excess power, and thresholds. Produces the derived occupancy labels. |
| `cache.py` | **Parquet cache manager.** Stores recordings as efficient Parquet files with manifest.json. Supports sliced reads (only loads the rows you need). |
| `index.py` | **Window index.** DuckDB-queryable table of 3350 characterized windows across all recordings, with 18 measured statistics per window. |
| `sigmf.py` | **SigMF importer.** Lets users upload their own recordings in the SigMF standard format (treated as untrusted input — validated, never executed). |
| `electrosense.py` | **ElectroSense adapter.** Implemented but currently unavailable (the service is offline). Reports `unavailable` rather than pretending. |

#### `aamsx/environment/` — The World to Play In

| Submodule | What It Does |
|---|---|
| `grid.py` | **Region grid.** Divides the frequency axis into R equal-channel-count regions. Not equal bandwidth — because channel spacing is non-linear in e-CALLISTO data. |
| `replay.py` | **ReplayEnvironment.** Steps through a block of real recorded data. On each step, returns the measured margins for the chosen window, adds receiver noise, and determines detections. Supports sealing (for leakage tests). |
| `receiver.py` | **Receiver model.** Simulates observation noise (`noise_db = 0.4`, calibrated to give 90% detection rate at 9.4% false alarm), switching costs, and settling penalties. |
| `truth.py` | **Derived truth.** Computes the "ground truth" occupancy from real measurements using the calibration policy. Clearly labeled as "derived" not "absolute". |
| `scenarios.py` | **Scenario library.** Defines the 7 preset scenarios and 10 randomized families. Scenarios are defined by querying the window index, not by hardcoded constants. |

#### `aamsx/belief/` — What Do I Think?

| File | What It Does |
|---|---|
| `filter.py` | **Two-state Markov belief filter.** Maintains per-region beliefs with soft Bayesian updating (likelihood ratio via Φ), prediction using learned transition rates, and uncertainty decomposition (aleatoric + epistemic). |

#### `aamsx/features/` — What Does the Situation Look Like?

| File | What It Does |
|---|---|
| `encoder.py` | **Temporal encoder.** Rolling buffer that produces ~18 named features per step: activity rate, moving averages, detection trend, spatial concentration (Herfindahl index), profile drift, budget fraction, steps-since-change. |
| `neural.py` | **(Optional) Neural encoder.** A single-layer GRU cell that replaces the memory key with a learned representation. Requires `pip install -e ".[neural]"`. Off by default; no published results use it. With random weights, it's a reservoir — a fixed random projection, not a trained model. |

#### `aamsx/memory/` — What Have I Seen Before?

| File | What It Does |
|---|---|
| `hopfield.py` | **Modern Hopfield associative memory.** Stores up to 24 context prototypes. Uses cosine similarity + softmax attention (β=12.0) for retrieval. Writes new prototypes when similarity < 0.88, updates existing ones otherwise. Features include utility-based eviction, prototype decay, preference tracking, and a `RunningStandardiser` for whitening inputs. |

#### `aamsx/change_detection/` — Has the World Changed?

| File | What It Does |
|---|---|
| `detector.py` | **Composite change detector.** Combines three symptoms (surprise, profile divergence, detection rate change) into a standardized statistic, then feeds it to both a Page-Hinkley detector and an EWMA detector. Both must agree. 90-step refractory period. When triggered, the scheduler discounts evidence by 60%. |

#### `aamsx/periodicity/` — Are There Patterns?

| File | What It Does |
|---|---|
| `engine.py` | **Prominence-gated autocorrelation.** Finds the dominant period in a signal (if any). Searches lags [4, n/3), requires Bartlett significance, and minimum prominence of 0.12. Returns (period, strength) or (0, 0.0) for noise/insufficient data. |

#### `aamsx/information_gain/` — Where Would I Learn the Most?

| File | What It Does |
|---|---|
| `engine.py` | **Expected information gain calculator.** Computes `IG(a) = H(b) − E[H(b′) | a]` exactly for the two-state model. Considers sensor sensitivity and false-alarm rate. Returns per-region IG in nats, and window-summed IG for each candidate anchor. |

#### `aamsx/schedulers/` — The Decision Makers

| File | What It Contains |
|---|---|
| `base.py` | **`BaseScheduler`** — abstract base class. Defines the interface: `reset(setup)`, `select(context) → ActionProposal`, `update(feedback)`. Provides helper methods for window scoring and switch penalty calculation. |
| `mag_nts.py` | **`MagNtsScheduler`** — the primary policy (described in detail above). 8-term weighted scoring, change gating, memory gating, budget pressure. **331 lines of Python** — the entire brain. |
| `thompson.py` | **`ThompsonScheduler`** — plain Beta-Bernoulli Thompson sampling (with optional discounting). The foundation that MAG-NTS builds on. |
| `baselines.py` | **`RoundRobinScheduler`**, **`RandomScheduler`**, **`UcbScheduler`** — the three simple baselines. Round-robin sweeps in order, random picks uniformly, UCB uses upper confidence bounds. |
| `dqn.py` | **`DqnScheduler`** — Deep Q-Network (behind `AAMSX_ENABLE_DEEP_RL` feature flag). Not part of any published result. Included for completeness, not recommended for this problem (1200 steps is too few for deep RL to learn meaningfully). |
| `__init__.py` | **Registry** — maps scheduler names to classes. `create_scheduler("mag-nts")` returns the right object. Lists all available schedulers and their display names. |

#### `aamsx/evaluation/` — Measuring How Well It Did

| Submodule | What It Does |
|---|---|
| `metrics.py` | **Per-step and cumulative metrics.** Computes reward (the 5-term weighted sum), detection rate, false alarm rate, band coverage, bits per observation, sensing cost, oracle comparison (regret against a clairvoyant oracle). |
| `events.py` | **Event detection.** Identifies sustained events (consecutive occupied steps in a region), measures time-to-detect and sustained detection probability. |
| `statistics.py` | **Statistical comparison.** Computes mean, std, SEM, 95% CI. Performs Welch t-test AND Mann-Whitney U test. Reports Cohen's d. A result is "significant" only when BOTH tests agree at α=0.05. Returns NaN when data is insufficient (honest, not a bug). |
| `pareto.py` | **Pareto frontier.** Computes dominance over 4 objectives: sustained detection probability (+), time-to-detect (−), false alarm rate (−), sensing cost (−). Avoids collapsing everything into one number. |

#### `aamsx/experiments/` — Running Everything

| Submodule | What It Does |
|---|---|
| `runner.py` | **Episode runner.** Executes one full episode: builds context, calls scheduler.select(), observes environment, computes feedback, calls scheduler.update(). Emits frames for live streaming. |
| `batch.py` | **Batch runner.** Runs arena (all policies × all seeds) and ablation (7-arm ladder) experiments. Manages concurrency with thread pools. |
| `engine.py` | **Experiment engine.** Async engine that spawns episodes in worker threads and publishes frames to WebSocket subscribers. Handles session lifecycle, retained frames (max 4000), and pacing. |
| `registry.py` | **SQLite registry.** Stores every run with its config_hash, status, and metrics. Supports lookup, replay validation, and history queries. |

#### `aamsx/reports/` — Making It Readable

| Submodule | What It Does |
|---|---|
| `generator.py` | **HTML report generator.** Renders self-contained HTML reports from stored experiment traces using Jinja2 templates. Can only report numbers that were actually computed — never invents data. |

#### `aamsx/api/` — Serving It All

| File | What It Does |
|---|---|
| `app.py` | **FastAPI application factory.** Mounts all routes under `/api`, sets up CORS, registers startup/shutdown hooks. |
| `deps.py` | **Dependency injection.** Provides `get_settings()`, experiment engine, scenario builder, and dataset manager to route handlers. |
| `schemas.py` | **API request/response models.** Pydantic models for all API endpoints. |
| `routes/` | **Route handlers** for health, status, datasets, scenarios, experiments, and reports. Each endpoint is documented in `docs/API.md`. |

### `web/` — The React Frontend

A React + TypeScript single-page application providing 13 screens:

| Screen | Route | What It Shows |
|---|---|---|
| **Command Center** | `/` | Live waterfall, band state, KPIs, decision terms. Launch and watch an episode. |
| **Real Spectrum Replay** | `/replay` | Browse cached recordings, view spectrograms with provenance. |
| **Event Timeline** | `/timeline` | Filter and scrub meaningful run events. |
| **Belief Map** | `/belief` | Posterior probability, uncertainty, staleness per region. |
| **Decision Inspector** | `/decision` | All 8 scoring terms decomposed for each step. |
| **Associative Memory** | `/memory` | Stored prototypes, retrieval weights, recognition history. |
| **Algorithm Arena** | `/arena` | Race policies head-to-head and compare statistical significance. |
| **Ablation Lab** | `/ablation` | Test each component in isolation (NTS + one thing at a time). |
| **Experiment Lab** | `/lab` | Build custom scenarios from real indexed windows. |
| **Analytics & Pareto** | `/analytics` | Multi-objective Pareto frontier, latency comparisons. |
| **Registry** | `/registry` | Browse all past experiments, replay, generate reports. |
| **Reports** | `/reports` | Generate and preview self-contained HTML reports. |
| **Demo Mode** | `/demo` | Full-screen presentation scenes. |

**Tech stack:** React 18, TypeScript, Vite (build tool), TanStack Query (server state), Zustand (session state), ECharts (charts), React Three Fiber/Three.js (3D visualizations), Canvas/WebGL (waterfalls).

**Key architecture:**
- One WebSocket per episode (not per screen) — navigating between screens doesn't re-connect
- 4000-frame circular buffer for live data
- 100ms throttled React updates (canvas components read raw buffer on `requestAnimationFrame`)
- Lazy-loaded screens (ECharts and Three.js are code-split)

### `data/` — The Data Store

```
data/
├── cached/              # Parquet recordings + manifests
│   └── <STATION>/<YYYYMMDD>/
│       ├── manifest.json    # Provenance, geometry, calibration
│       ├── power.parquet    # Quantized spectrogram (int16)
│       └── channels.parquet # Per-channel freq, baseline, noise, threshold
├── index/               # Window index (Parquet, queryable via DuckDB)
├── traces/              # Full episode results (JSON) for replay
└── registry.sqlite      # Experiment registry (id, config_hash, metrics)
```

### `docs/` — Documentation

| Document | What It Covers |
|---|---|
| `ARCHITECTURE.md` | Module boundaries, data flow, leakage prevention, async engine |
| `ALGORITHMS.md` | Every equation and constant, with justification |
| `DATA.md` | Where data comes from, calibration, derived labels, cache layout |
| `EXPERIMENTS.md` | All 4 signature experiments and measured results |
| `FRONTEND.md` | React architecture, routing, streaming, user flows |
| `API.md` | Every API endpoint with request/response shapes |
| `LIMITATIONS.md` | What AAMS-X doesn't do and where it loses |
| `DEVELOPER_GUIDE.md` | How to contribute and extend |
| `OPERATIONS.md` | Deployment, monitoring, troubleshooting |
| `QUALITY_AND_RISKS.md` | Quality assurance, known risks |
| `RUNTIME_AND_DATA.md` | Runtime behavior, data pipeline details |
| `SIH_DEMO.md` | Timed walkthrough for the evaluation panel |

### `scripts/` — Utility Scripts

| Script | What It Does |
|---|---|
| `fetch_real_data.py` | Downloads ~139 MB of real e-CALLISTO recordings (7 stations, ~12 hours each). Supports `--station`, `--hours`, `--date`, `--force` flags. |
| `build_index.py` | Characterizes every window in every recording and writes the window index (3350 windows with 18 statistics each). |
| `run_benchmark.py` | Runs the full arena (6 policies × 7 presets × 6 seeds) or ablation (7 arms × 3 scenarios × 6 seeds). |
| `tune_mag_nts.py` | Tunes MAG-NTS weights on training-split data only (48 candidates, 3 seeds). Records the full search. |
| `sensitivity.py` | Sweeps reward weights and reports how the policy ranking changes. |
| `survey_stations.py` | Surveys all e-CALLISTO stations to find ones suitable for experimentation. |
| `verify_docs.py` | Verifies every number in `docs/EXPERIMENTS.md` matches the stored experiment results. 406 values checked. |

### `tests/` — 440 Tests

| Test File | What It Tests |
|---|---|
| `test_api.py` | All API endpoints, error handling, path traversal, SQL injection |
| `test_belief.py` | Belief filter correctness |
| `test_change_detection.py` | Change detector sensitivity and specificity |
| `test_cli.py` | Command-line interface |
| `test_datasets.py` | Data loading, caching, calibration |
| `test_environment.py` | Environment replay, receiver model, region grid |
| `test_information_gain.py` | IG properties (non-negativity, bounds) |
| `test_memory.py` | Associative memory write/retrieve/eviction |
| `test_metrics.py` | Reward computation, event detection, statistics |
| `test_no_leakage.py` | **Critical.** Seals the environment and runs full episodes of every scheduler to prove no information leaks |
| `test_optional_and_untrusted.py` | SigMF import, untrusted input handling |
| `test_periodicity.py` | Periodicity detection accuracy |
| `test_properties.py` | Property-based tests (Hypothesis) for mathematical invariants |
| `test_reproducibility.py` | Same seed = same result, always |
| `test_scenarios.py` | Scenario building, train/test split enforcement |
| `test_schedulers.py` | All scheduler implementations |
| `test_statistics.py` | Statistical test correctness |

---

## 📡 The Data — Where It Comes From and What It Looks Like

### Source: e-CALLISTO Network

The **e-CALLISTO** (International Network of Solar Radio Spectrometers) is a worldwide network of solar radio spectrometers. It publishes data openly — no account, no API key, no rate limiting.

- **Format:** FITS files (standard astronomy format), one per 15-minute sweep
- **Archive URL:** `http://soleil.i4ds.ch/solarradio/data/2002-20yy_Callisto`
- **Time resolution:** 0.25 seconds per sample
- **Total cache size:** ~139 MB for 7 stations × ~12 hours each

### The 7 Curated Recordings

Each station was selected by a systematic survey (`scripts/survey_stations.py`) that measured frequency span, occupied-cell fraction, and live channel count:

| Station | Location | Band (MHz) | Character | Role |
|---|---|---|---|---|
| **INDIA-GAURI** | Gauribidanur, India | 30–90 | Dense, intermittent signals | Training |
| **SWISS-Landschlacht** | Switzerland | 45–175 | Persistent FM + intermittent | Training |
| **EGYPT-Alexandria** | Egypt | 45–165 | Intermittent, different hardware | Validation |
| **MRO** | Murchison, Australia | 50–846 | Wideband, radio-quiet reserve | Test (unseen) |
| **AUSTRIA-OE3FLB** | Litschau, Austria | 112–747 | Very sparse, 4% occupancy | Test (unseen) |
| **SSRT** | Badary, Russia | 45–441 | Low contrast, near threshold | Test (unseen) |
| **SWISS-MUHEN** | Muhen, Switzerland | 15–87 | HF, diurnal patterns | Test (unseen) |

### The Train/Validation/Test Split

This is **critical for scientific integrity**:

- **Training stations** (India, Switzerland): Used to tune MAG-NTS weights
- **Validation station** (Egypt): Used to check sanity, never for tuning
- **Unseen stations** (4 others): Used in exactly ONE experiment preset (`unseen-generalization`), never touched during development or tuning

A test (`test_scenarios.py`) enforces this split — if any preset accidentally uses an unseen station, the build fails.

### From Raw Data to Occupancy Labels

```
Raw FITS (digits) → Convert to dB (×0.25) → Compute baseline (P10 per 10 min)
→ Compute excess (power − baseline) → Estimate noise (first-difference MAD / √2)
→ Set threshold: max(1.5 dB, 5 × noise) per channel
→ Label: excess > threshold = "occupied"
```

> ⚠️ **These are derived labels, not ground truth.** The archive doesn't have per-emitter annotations. Every metric, API response, and report is tagged accordingly. Comparisons between policies are fair (same labels for everyone), but absolute detection numbers are not physical truth.

---

## 🏆 The 6 Scheduling Policies (Algorithms) Compared

| Policy | How It Works | Strengths | Weaknesses |
|---|---|---|---|
| **Round-Robin** | Sweep all regions in order. No learning. | Perfect band coverage (1.000). Always finds everything eventually. | Slow — wastes time on empty regions. Low reward. |
| **Random** | Pick a random window each step. | Simple baseline floor. | Worst performance on almost everything. |
| **UCB** | Upper Confidence Bound: picks the region with `hit_rate + √(2·ln(t)/n)`. | Systematic exploration. | Doesn't handle non-stationarity. |
| **Thompson** | Beta-Bernoulli sampling WITHOUT discounting. | Excellent in stable environments. | Slow to adapt when environment changes — remembers too much. |
| **NTS** | Thompson WITH geometric discount (0.995). | Adapts to changes. The fair control for MAG-NTS. | No memory, no information gain, no periodicity, no change response. |
| **MAG-NTS** ⭐ | NTS + memory + information gain + periodicity + change detection + budget pressure. | Best on stable/hard/noisy/budgeted scenarios. Fully explainable. | Loses on sudden wholesale environment replacement (memory retrieves stale context). |

---

## 🧪 The 7 Experiment Scenarios

| Preset | What Makes It Hard | Key Finding |
|---|---|---|
| **easy-static** | Stable: 4 regions busy >50% of the time | MAG-NTS wins on reward (+38.03 vs NTS, significant) |
| **periodic-challenge** | Strongest periodicity in cache (period 9 steps) | MAG-NTS +40.54 vs NTS (significant) |
| **high-noise** | Low contrast, 1.5 dB receiver noise (3.75× normal) | MAG-NTS +54.26 vs NTS (significant). Memory is the hero (+99.07 alone) |
| **extreme-budget** | Only 35% of steps affordable | MAG-NTS best reward and oracle ratio |
| **sudden-shift** | Two uncorrelated environments spliced at step 600 | **MAG-NTS loses** −50.09 vs NTS (significant). Memory hurts here (−85.89) |
| **recurring-environment** | A→B→A′ pattern (same environment returns) | Recovery 5–8× faster on return. Change detection helps (+20.82) |
| **unseen-generalization** | Held-out stations, different continents/hardware | **MAG-NTS loses** on reward (−69.43), gains on detection coverage (+0.028) |

### The Honest Headline

> **MAG-NTS wins 3 of 7 presets significantly, loses 2 significantly, and ties 2.** It excels on stable, hard, noisy, and budget-limited bands. It loses when the environment is wholesale replaced (because memory retrieves stale context). Both findings are published — this project does not hide its failures.

---

## 🖥️ The Web Frontend — What You See

### Starting the Frontend

```bash
cd web
npm ci          # Install dependencies
npm run dev     # Start Vite dev server on port 5173
```

The frontend connects to the backend at `http://localhost:8000` (configurable via `VITE_API_BASE`).

### Key User Flows

**1. Launch and Watch an Episode:**
Command Center → Choose scenario & policy → Click Launch → Watch the live waterfall, belief map, and KPIs update in real time

**2. Explore Real Data:**
Real Spectrum Replay → Pick a recording → See the actual spectrogram with provenance, calibration details, and retrospective analytics

**3. Compare Policies:**
Algorithm Arena → Choose a preset → Set seeds → Watch all policies race side-by-side → See statistical comparisons with p-values

**4. Test Components:**
Ablation Lab → Run the 7-arm ladder → See which component contributes what

**5. Build Custom Scenarios:**
Experiment Lab → Search indexed windows → Splice segments → Validate → Run

---

## 🔌 The REST API — How Frontend Talks to Backend

Base URL: `http://localhost:8000/api`

### Key Endpoints

| Method | Path | What It Does |
|---|---|---|
| `GET` | `/health` | Health check — never touches disk |
| `GET` | `/status` | System status (recordings, presets, warnings) |
| `GET` | `/datasets` | List cached recordings and adapter status |
| `GET` | `/datasets/index/windows` | Search the window index with SQL predicates |
| `GET` | `/datasets/{station}/{day}/spectrogram` | Get a real waterfall (margin in dB) |
| `GET` | `/scenarios` | List available presets and families |
| `POST` | `/experiments` | Launch one episode (returns immediately with ID) |
| `POST` | `/experiments/arena` | Launch a full policy comparison |
| `POST` | `/experiments/ablation` | Launch the ablation ladder |
| `WS` | `/experiments/{id}/stream` | Live frame streaming |
| `POST` | `/reports` | Generate HTML report from stored traces |

### Data Provenance Tags

Every response carrying numbers has a `kind` field:

| Tag | Meaning |
|---|---|
| `measured` | Straight from the archive, only unit conversion |
| `derived-label` | Computed under the labelling policy (a reference, not truth) |
| `model-inferred` | Produced by AAMS-X's own models |

Interactive API documentation is at: `http://localhost:8000/api/docs`

---

## ⚙️ Configuration and Environment Variables

All settings use the `AAMSX_` prefix. Copy `.env.example` to `.env` to customize.

### Paths
| Variable | Default | Meaning |
|---|---|---|
| `AAMSX_DATA_DIR` | `./data` | Where recordings, index, and registry live |
| `AAMSX_REPORTS_DIR` | `./reports/out` | Where HTML reports are saved |

### Ingestion
| Variable | Default | Meaning |
|---|---|---|
| `AAMSX_ALLOW_NETWORK` | `true` | Set `false` for air-gapped demos |
| `AAMSX_HTTP_TIMEOUT_SEC` | `45` | Download timeout |
| `AAMSX_FETCH_CONCURRENCY` | `8` | Parallel download connections |

### Calibration (changing these changes ALL derived labels!)
| Variable | Default | Meaning |
|---|---|---|
| `AAMSX_DB_PER_DIGIT` | `0.25` | e-CALLISTO scale factor |
| `AAMSX_OCCUPANCY_THRESHOLD_DB` | `1.5` | Minimum excess for "occupied" |
| `AAMSX_OCCUPANCY_K_MAD` | `5.0` | Per-channel significance multiplier |
| `AAMSX_BASELINE_PERCENTILE` | `10.0` | Quiet-time baseline quantile |

### Experiment Engine
| Variable | Default | Meaning |
|---|---|---|
| `AAMSX_MAX_CONCURRENT_EXPERIMENTS` | `4` | Parallel experiment limit |
| `AAMSX_ENABLE_NEURAL` | `false` | Enable optional neural encoder (needs PyTorch) |
| `AAMSX_ENABLE_DEEP_RL` | `false` | Enable DQN/SAC policies (needs PyTorch) |

### Frontend
| Variable | Default | Meaning |
|---|---|---|
| `VITE_API_BASE` | `http://localhost:8000` | Backend URL for the browser |
| `VITE_WS_BASE` | `ws://localhost:8000` | WebSocket URL |

---

## 🚀 Setup and Installation — Getting It Running

### Prerequisites

- **Python 3.12+** (required — uses modern syntax like `type[X]` and `X | Y`)
- **Node.js 20.19+** (for the frontend)
- **Git** (to clone the repository)

### Step-by-Step (Manual)

```bash
# 1. Clone the repository
git clone https://github.com/Siddhanthkjain2005/AAMS-X.git
cd AAMS-X

# 2. Create a Python virtual environment
python3.12 -m venv .venv

# On Linux/Mac:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# 3. Install the package with development dependencies
pip install -e ".[dev]"

# 4. Copy the example environment file
cp .env.example .env          # Nothing secret needed!

# 5. Download real radio recordings (~139 MB, needs internet, once)
python scripts/fetch_real_data.py

# 6. Build the window index (characterizes all recordings)
python scripts/build_index.py

# 7. Run the test suite (440 tests)
pytest

# 8. Start the API server
uvicorn aamsx.api.app:create_app --factory --reload
# → Backend running at http://127.0.0.1:8000/api/docs

# 9. (In another terminal) Start the frontend
cd web
npm ci
npm run dev
# → Frontend running at http://localhost:5173
```

### Step-by-Step (Using Makefile)

```bash
make setup          # Creates .venv, installs everything
make data           # Downloads real recordings
make index          # Builds the window index
make test           # Runs all 440 tests
make api            # Starts the API server
make web-install    # Installs frontend dependencies
make web            # Starts the frontend dev server
```

### Running Everything at Once

```bash
make all            # setup + data + index + test
```

---

## 🐳 Running with Docker

### Quick Start

```bash
# Build both images (backend + frontend)
docker compose build

# Download data (one-time, needs internet)
docker compose run --rm fetch

# Build the window index (one-time)
docker compose run --rm index

# Start the full stack
docker compose up
# → Backend on :8000, Frontend on :5173
```

### Architecture

- **`api` service:** Python backend on port 8000, runs as unprivileged user, healthcheck enabled
- **`web` service:** Nginx serving the React build on port 5173, proxies API requests
- **`./data` is a bind mount:** Recordings stay on the host, so the image stays small (~200 MB) and rebuilding doesn't re-download 139 MB of data
- **Network disabled by default** in the served demo (`AAMSX_ALLOW_NETWORK=false`)

### Running Experiments in Docker

```bash
docker compose run --rm benchmark              # Full arena: 7 presets × 6 policies × 6 seeds
docker compose run --rm benchmark --ablation   # Ablation ladder
```

---

## ✅ The Test Suite — How Quality is Ensured

```bash
pytest                    # Full suite (440 tests)
pytest -m "not slow" -x   # Fast subset
```

### What the Tests Prove

| Test Category | What It Guarantees |
|---|---|
| **No-leakage tests** | Schedulers CANNOT access ground truth during decisions |
| **Reproducibility tests** | Same seed = byte-identical results |
| **Property-based tests** | Mathematical invariants hold (IG ≥ 0, IG ≤ H(b), etc.) using Hypothesis |
| **API tests** | All endpoints return correct data, security (path traversal, SQL injection rejected) |
| **Split enforcement** | Unseen stations are only used in the unseen preset |
| **Integrity tests** | `is_synthetic == False` for all cached recordings |

### Code Quality Tools

```bash
ruff check .          # Linting
ruff format --check . # Formatting
mypy aamsx            # Type checking
```

---

## 📖 Key Technical Concepts Glossary

| Term | What It Means |
|---|---|
| **Region** | One slice of the frequency band. With 48 regions, each covers ~1/48th of the channels. |
| **Window** | The W=4 contiguous regions the receiver observes per step. |
| **Anchor** | The starting region of a window. Window at anchor 20 = regions 20, 21, 22, 23. |
| **Step** | One tick of the simulation clock. The scheduler observes once and decides once per step. |
| **Belief** | Per-region probability that it's currently occupied (0.0 to 1.0). |
| **Occupancy** | Fraction of time a region has signals present. |
| **Margin** | How far a signal is above the detection threshold, in dB. Positive = detected. |
| **Dwell** | Staying on the same window (not retuning). |
| **Retune** | Moving the receiver to a different window position. |
| **Episode** | One complete run — 1200 steps of observe→decide→learn. |
| **Preset** | A predefined experiment scenario (e.g., "easy-static", "sudden-shift"). |
| **Arena** | A comparison of all policies on the same preset with the same seeds. |
| **Ablation** | Testing each component in isolation (NTS + one thing at a time). |
| **Pareto frontier** | The set of policies where no other policy is better on ALL objectives simultaneously. |
| **Config hash** | SHA-256 of the full experiment configuration. Same hash = same result guaranteed. |
| **IG** | Information Gain — bits of uncertainty resolved by an observation. |
| **MAD** | Median Absolute Deviation — a robust measure of data spread. |
| **SDP** | Sustained Detection Probability — fraction of distinct events detected at least once. |
| **TTD** | Time-To-Detect — average steps until an event is first detected. |
| **Cohen's d** | Effect size measure — how many standard deviations apart are two groups. |
| **Welch t-test** | Statistical test for comparing means when variances differ. |
| **Mann-Whitney U** | Non-parametric rank-based statistical test (survives skewed data). |
| **Beta distribution** | The probability distribution used to model "batting average" — parameterized by successes (α) and failures (β). |
| **Thompson Sampling** | An algorithm that draws random samples from each option's probability distribution and picks the winner. |

---

## ⚠️ Limitations — Where It Falls Short

### Where MAG-NTS Loses (Measured, Not Guessed)

| Scenario | MAG-NTS vs NTS | Why |
|---|---|---|
| `sudden-shift` | **−50.09** (significant loss) | Memory retrieves stale context when the environment is replaced |
| `unseen-generalization` | **−69.43** (significant loss) | Same mechanism — different continents, different hardware |

**The root cause:** When the environment is wholesale replaced by an uncorrelated one, the memory module retrieves preferences that no longer apply. The change detector forgets the Beta evidence but doesn't suppress the retrieved memory prior.

**The identified fix:** Gate memory retrieval on the change detector (suppress retrieval for a refractory period after a detected change). This is NOT implemented — because the failure was found on the test set, and fixing it in response would be tuning on the test set.

### Other Known Limitations

1. **Labels are derived, not ground truth** — no absolute calibrated power from the archive
2. **6 seeds** — enough for large effects, not for effects smaller than ±20 reward
3. **One archive day** — all data comes from 2026-08-25
4. **Single-process engine** — no distributed computing, no Kubernetes
5. **No authentication** on the API — don't expose to a network without auth in front
6. **The memory key is confounded by the policy's behavior** — what you observe depends on what you chose to look at
7. **Periodicity has blind spots** — can't detect periods <4 steps or >1/3 of the window

---

## 🚫 What This Project Is NOT

| NOT This | Why |
|---|---|
| RF transmission or jamming | Receive-only. No transmit code exists. |
| Military emitter identification | No emitter labels in the data. |
| Hardware controller | No SDR driver, no serial port, no GPIO. |
| Geolocation system | Single-receiver, no direction information. |
| Tactical frequency recommendation | The output is "which slice to analyze next", not operational advice. |
| A simulator | Every experiment uses real recorded data — no synthetic fallback. |

> AAMS-X is an **academic research platform on public spectrum data**. The scheduling mathematics (Thompson sampling, associative recall, information-gain sensing) is domain-independent. The operational layer is absent on purpose.

---

## 📜 Credits and License

- **License:** MIT
- **Data Source:** e-CALLISTO — International Network of Solar Radio Spectrometers
  - Reference: Benz, Monstein & Meyer (2005), *CALLISTO — A New Concept for Solar Radio Spectrometers*, Solar Physics **226**, 143
- **SIH Problem Statement:** SIH26055 — Smart Scan Strategy for Electronic Warfare

---

## 🔧 Quick Reference Commands

```bash
# Setup
make setup                                    # Install everything
make data                                     # Download recordings
make index                                    # Build window index

# Development
make test                                     # Run 440 tests
make test-fast                                # Quick tests only
make lint                                     # Check code style
make fmt                                      # Auto-format code
make typecheck                                # Run mypy

# Running
make api                                      # Backend on :8000
make web                                      # Frontend on :5173

# Experiments
make benchmark                                # Full arena (6 policies × 7 presets × 6 seeds)
make ablation                                 # 7-arm component ladder
make tune                                     # Re-tune MAG-NTS weights
make sensitivity                              # Reward weight sweep
make report                                   # HTML report from latest results

# Docker
docker compose up --build                     # Full stack
docker compose run --rm fetch                 # Download data
docker compose run --rm index                 # Build index
docker compose run --rm benchmark             # Run benchmark

# Verification
make verify-docs                              # Check docs match stored results
python scripts/verify_docs.py                 # Same, without make
```

---

*This README was written for the `adithyap` branch to provide a complete, beginner-to-expert guide to the AAMS-X project.*
