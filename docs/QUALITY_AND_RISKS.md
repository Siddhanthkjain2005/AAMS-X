# Quality and risk register

This document records the current verification state, security and performance analysis,
technical debt, and places where names/comments/docs do not match executable behavior.
It is intentionally direct. Removing a risk requires code, tests and updated documentation.

## Audit basis

The repository was traced across all Python modules, route handlers, wire schemas, React
screens, state/client code, scripts, tests, data layouts, Docker and AWS files. Findings are
based on current code, not intended behavior in comments.

Limitations of the audit:

- This workspace has no readable `.git` directory, so history, blame, release tags and
  uncommitted-diff boundaries were unavailable.
- No live production load or penetration test was performed.
- The AWS code shape was reviewed, but cloud account controls, IAM, security-group rules,
  billing alarms and backups are not represented in this repository.
- Scientific published values were checked against the included result JSON, not against
  a fresh full multi-seed rerun.

## Verification snapshot — 2026-08-28

| Check | Result |
|---|---|
| Backend tests collected | 507 |
| Full backend run | 438 passed, 4 skipped, 65 setup errors |
| Shared setup-error cause | `Settings.ensure_dirs()` calls `mkdir` on symlinked cache/index paths in API/CLI fixtures and raises `FileExistsError` in this environment |
| Ruff check | pass |
| mypy over `aamsx` | pass, 72 source files |
| Published-doc value audit | 406/406 values reproduce; 1,456 comparisons agree with the both-tests rule |
| Frontend TypeScript check | pass |
| Frontend production build | pass with Node 24.19 (declared minimum is 20.19) |
| Frontend unit tests | no test files found; passes only with `--passWithNoTests` |
| Default machine Node | 18.20.8, too old for current Vite/Rolldown |

The README and SIH walkthrough previously said “440 tests, must be green.” The current
collected count is 507 and the full suite is not green in this environment. Do not repeat
the old claim until the shared setup issue is fixed and the entire suite passes.

Four skipped tests were data/optional-path skips reported by pytest. The 65 errors are not
65 independent failures: 62 API cases and 3 CLI integration cases fail before their test
body for the same directory/symlink setup issue. The remaining 438 tests passed.

## Priority register

### Critical before public production

| Risk | Evidence and impact | Recommended change |
|---|---|---|
| Unauthenticated state-changing API | Anyone who can reach the service can launch CPU-heavy batches, cancel runs, replay, query data and generate/read reports. AWS exposes nginx publicly. | Add identity, authorization, per-user ownership and access checks. |
| Raw SQL fragments over HTTP | `/datasets/index/windows` interpolates `where` and `order_by` after a small banned-token check. DuckDB expressions/functions and resource-heavy queries remain possible. | Replace SQL strings with typed filter/sort fields and parameterized query construction. |
| No enforced concurrency/rate limit | `max_concurrent_experiments` is unused; every request can start a thread/process-pool workload and retain large frames. | Engine semaphore/queue, per-principal quotas, request rate limit and hard worker cap. |
| HTTP-only AWS deployment | Traffic, actions and reports are unencrypted; HTTPS to the numeric address is not configured. | DNS + certificate + TLS termination + redirect; keep API private. |
| Internal errors exposed | Global 500 returns exception class/message. Registry history returns `error`, and engine failures persist short tracebacks. | Public error ids and generic text; keep details in protected logs. |

### High

| Risk | Evidence and impact | Recommended change |
|---|---|---|
| Slow WebSocket clients lose data silently | Subscriber queues are 512; queue-full drops messages. Client is not told which steps are missing. | Add monotonically increasing sequence ids, gap messages and range resync. |
| Reconnect duplicates frames | Server replays retained frames; client appends them to the existing ring without deduplication. | Clear/resync by step or deduplicate sequence ids. |
| Background cancellation is not definitive | Cancelling an asyncio wrapper does not kill `to_thread` or process-pool work immediately. | Cooperative cancellation token checked every loop/job, bounded shutdown and terminal-state tests. |
| Multi-worker deployment is unsafe | Session engine is process-local. A WebSocket handled by another Uvicorn worker cannot find the id; limits and frames are not shared. | Stay single-worker or add durable job/session broker and affinity. |
| Persistence updates are non-atomic | Result JSON and SQLite status are separate; cache/index/report writes are direct. Crashes can leave partial state. | Temp file + fsync + atomic rename; transaction/outbox or reconciliation tooling. |
| No schema migrations | SQLite table is created in place; manifest version is written but not checked. | Versioned migrations and compatibility tests. |
| Calibration summary inconsistency | `write_recording` computes configured calibration but calls `raw.to_cube()` without passing it for fresh raw data. Custom defaults can disagree with written calibration. | Attach/pass the computed calibration before summaries; add non-default-setting test. |
| Production source maps | Vite emits `.map` files, and nginx serves assets publicly. | Decide whether public source maps are intended; otherwise omit or publish privately. |
| No backup/retention controls | Registry/traces/reports grow indefinitely; no restore test or disk alarm. | Backup policy, reconciliation, retention and capacity monitoring. |

### Medium

| Risk | Evidence and impact | Recommended change |
|---|---|---|
| Engine task map grows forever | `_tasks` entries are never removed after completion. | done callback/finally removal and test. |
| Finished-frame claims overstate persistence | Trace JSON does not contain frames; older evicted sessions cannot drive per-step screens despite RunPicker comment. | Persist compressed frames or make UI limits explicit and disable unsupported screens. |
| Settings imply unused features | Four engine/ML flags are unused or partially used; operators may believe limits are active. | Wire them end to end or remove/deprecate them. |
| Health check is shallow | `/api/health` does not check disk, registry, index or presets. Containers can be healthy but unusable. | Keep liveness, add separate readiness endpoint. |
| Large JSON responses | Spectrogram can return roughly 1,200×256 rounded floats; analytics can return long arrays. | Binary/columnar or tiled endpoints, compression benchmarks, response limits. |
| Per-request DuckDB open | New in-memory database/view for each query; user expressions can be expensive. | Typed query API, pooling/prepared reads, execution time/resource limits. |
| DNS check on dataset listing | ElectroSense status can resolve DNS each call; `host_resolves` changes the process-wide default socket timeout. | Avoid global timeout mutation; cache non-probe status and use explicit socket timeout APIs. |
| Report filename collision | Name has one-second resolution; concurrent creates can overwrite. | Include UUID/experiment digest and atomic exclusive create. |
| No frontend behavior tests | Route, state and stream regressions rely on TypeScript/build/manual testing. | Add Vitest for client/ring/store and browser E2E for launch/stream/routes. |
| Browser route defect | Registry navigates to `/inspector`, while App defines `/decision`. | Use a shared route constant and add route test. |
| Manual wire types drift | Frontend types contain duplicate properties and fields not matching backend serialization. | Generate types from OpenAPI plus separate runtime-result schema, or add contract tests. |
| NaN is allowed into stored JSON | Metric cleaners return `float('nan')`; Python JSON writes non-standard `NaN`, while strict response encoders/clients may reject it. | Normalize unavailable metrics to `null` with explicit optional types. |

### Low/maintainability

- API Pydantic includes `WindowQuery`, but the route duplicates its validation rather than
  receiving that model.
- `python-multipart` is installed even though no upload route exists.
- `scikit-learn` is declared but the inspected core uses direct NumPy/SciPy/PCA code;
  confirm before removing because scripts/tests may import it indirectly.
- The Docker build installs the package once with only `version.py`, then again after
  copying source. It works, but is non-obvious and should be documented/tested on clean
  cache misses.
- Compose `depends_on: service_healthy` is useful with modern Compose but not a portable
  orchestration readiness contract.
- There is no central route constant shared between navigation and programmatic actions.
- Several scientific comments contain measured constants tied to included data. Those
  comments must move with calibration/benchmark changes or be linked to generated data.

## Configuration discrepancies

| Setting or claim | Actual behavior |
|---|---|
| `AAMSX_MAX_CONCURRENT_EXPERIMENTS=4` | never read outside `config.py`; no experiment limit |
| `AAMSX_EVENT_QUEUE_SIZE=4096` | never read; subscriber queues are hard-coded to 512 |
| `AAMSX_BATCH_WORKERS=0` | read by `tune_mag_nts.py`; API/CLI default uses `cpu_count - 1` |
| `AAMSX_ENABLE_NEURAL=false` | CLI reports the flag, but `AblationFlags.neural_encoder` directly controls import/use |
| `AAMSX_ENABLE_DEEP_RL=false` | DQN registers whenever PyTorch imports, regardless of flag |
| “DQN/SAC implemented” | only DQN exists; no SAC module or registry entry |
| `AAMSX_MAX_UPLOAD_BYTES` | enforced by local SigMF loader; no web upload path |
| `VITE_WS_BASE` | declared in Docker/env typing but never read |
| `.env.example` absolute `VITE_API_BASE` | client rejects absolute hosts and falls back to `/api`; dev proxy still makes that work |
| health docs include scheduler version | actual `/api/health` returns only status and code version |
| health Docker comment says no disk | true for handler, but app creation loads settings and creates directories before serving |

## Frontend contract discrepancies

Current `web/src/api/types.ts` issues:

- `WindowsResponse` declares `windows` twice.
- `RewardTerms` declares `information` twice.
- `Aggregate` expects `minimum` and `maximum`, while backend `to_dict` emits `min` and
  `max`. Current components mainly use mean/CI, so the mismatch can remain hidden.
- `SchedulerName` includes `sac`, which the backend does not implement.
- comments say every scheduler field is mirrored, but TypeScript cannot validate JSON at
  runtime and no generated contract test exists.
- `SessionSummary` comments imply more fields than `Session.summary()` returns.

Use the Python response builders and OpenAPI as source of truth until this is corrected.

## Documentation discrepancies found

The new documentation hub and this register supersede the following older statements:

- README and `SIH_DEMO.md`: “440 tests” is stale; 507 currently collect.
- `LIMITATIONS.md`: says concurrency is capped at four; it is not enforced.
- `LIMITATIONS.md` and `SIH_DEMO.md`: say DQN and SAC are behind a feature flag; only DQN
  exists and registration is based on whether PyTorch imports.
- `ARCHITECTURE.md`: says equal configuration hashes mean identical numbers. The hash does
  not include code version or cache content checksum, so this is conditional, not exact.
- `API.md`: old health example included `scheduler_version`; the handler does not.
- `API.md`: old WebSocket table omitted `status`, `timeline` and `batch_progress` and
  understated `complete` as metrics rather than the full result.
- `DATA.md`: describes SigMF metadata as a Pydantic model and wrong-magic HTTP 422 behavior;
  the current local importer uses explicit dict validation and there is no HTTP upload.
- engine and RunPicker comments say reconnect/finished runs resync cleanly; the client can
  duplicate frames, and evicted frame history is not stored.

Research values in `EXPERIMENTS.md` are separately machine-verified and were not modified
by this implementation audit.

## Security analysis by surface

### API and network

- No authentication, session, API token, authorization or tenant isolation.
- CORS restricts browser JavaScript origins but is not an access-control boundary.
- No CSRF design is needed only because there is currently no authenticated cookie; this
  changes once identity is added.
- No rate limiting, request id, IP policy or experiment quota.
- The AWS nginx config has no TLS, HSTS, CSP or explicit security headers.
- The API container is private in AWS Compose, which is good; local Compose publishes it.
- Global exception text and stored tracebacks disclose internal paths and implementation.
- OpenAPI/docs are public.

### Inputs and files

Positive controls:

- Pydantic caps scenario shape, geometry, seeds and report id count.
- Report fetch validates prefix/suffix and rejects `/`.
- SigMF limits metadata, samples, channels, data types, FFT and station slug.
- neural checkpoints use `torch.load(weights_only=True)`.
- Jinja2 report environment enables HTML autoescape.

Remaining issues:

- SQL fragments are not safely modeled.
- Spectrogram/analytics can consume substantial CPU/memory within valid ranges.
- Report title/notes length is not explicitly capped at the schema.
- History exposes full configs and error fields to any caller.
- SigMF provenance accepts uploader-declared license/author/description; it is labelled as
  unverified but still needs ownership/access controls before a public upload feature.
- Cache/index imports trust local filesystem files and do not verify manifest schema or
  trace integrity before every use.

### Dependencies and supply chain

- Python and npm dependencies use lower bounds or exact package versions, respectively;
  container base images are tags, not digests.
- No lock file exists for Python, so rebuilds can select newer dependency versions.
- npm has a lock file and Docker uses `npm ci`.
- No repository workflow for vulnerability, license or secret scanning was found.
- PyTorch checkpoints are treated as untrusted more carefully than ordinary local JSON,
  Parquet and SQLite files.

## Performance and scale analysis

### CPU

Episode computation is synchronous NumPy/SciPy work. The API moves it to a thread, while
batches may create `cpu_count - 1` worker processes. Multiple client launches can multiply
that count because there is no engine semaphore. Control process counts explicitly on a
small host.

MAG-NTS scores all contiguous anchors every step, primarily O(regions) with small fixed
memory capacity. Association reads compare at most 24 prototypes. The shipped 48-region,
1,200-step cases are small; API validation permits 256 regions and 20,000 steps.

### Memory

Each retained frame contains several region-length arrays, factors and nested snapshots.
4,000 Python dictionaries per session across 24 retained sessions can dominate the
backend memory, especially with 256 regions. Frontend keeps another 4,000 parsed frames.
No byte-based cap exists.

Truth assembly concatenates complete segment margin matrices. Index building loads a
full recording's region-margin series in chunks but concatenates all chunks before
profiling windows. The shipped cache is manageable; a much larger cache needs streaming or
partitioned processing.

### I/O and payloads

- `GET /datasets` reads every manifest and can perform DNS resolution.
- Spectrogram emits nested JSON floats rather than Arrow/binary tiles.
- Analytics loops over change-scan centers and returns full activity arrays.
- Every index query opens DuckDB and reads the Parquet view.
- SQLite creates a connection per operation with 15-second timeout, default journal mode,
  and no WAL/busy retry policy.
- Trace JSON and report files have no compression or retention.

### Browser bundle

The verified production build produced roughly 1.09 MB Three.js and 1.14 MB ECharts
uncompressed chunks, plus source maps. They are lazy/cached, but first use of 3-D or chart
screens is network- and parse-heavy on a slow client.

## Test coverage map

| Area | Main tests |
|---|---|
| HTTP, WebSocket, reports | `tests/test_api.py` |
| CLI lifecycle | `tests/test_cli.py` |
| calibration/cache/FITS/SigMF | `test_datasets.py`, `test_optional_and_untrusted.py` |
| replay geometry/budget | `test_environment.py` |
| scenarios and splits | `test_scenarios.py` |
| scheduler contracts | `test_schedulers.py` |
| hidden-truth boundary | `test_no_leakage.py` |
| belief/change/periodicity/memory/IG | component-named files |
| metrics/reward/statistics | `test_metrics.py`, `test_statistics.py` |
| seed/config reproducibility | `test_reproducibility.py` |
| invariants/fuzzed cases | `test_properties.py` |

Gaps:

- no frontend unit or end-to-end tests;
- no Docker/AWS infrastructure tests;
- no authentication/authorization tests because those features do not exist;
- no load, soak, backpressure or memory-cap tests;
- no migration/restore/corruption reconciliation tests;
- no test that configured concurrency/queue limits are enforced;
- no test that production nginx security/TLS configuration exists;
- no automated API↔TypeScript schema contract check.

## Recommended fix order

1. Fix symlink-safe settings directory creation and restore a fully green backend suite.
2. Correct the Registry `/inspector` route and add basic frontend route/client/ring tests.
3. Remove raw SQL from the public API.
4. Enforce concurrency, workers, rate limits and cancellation semantics.
5. Add TLS and authentication before further public AWS exposure.
6. Normalize error and NaN serialization.
7. Make writes atomic and introduce SQLite/cache migrations plus backup verification.
8. Align/remove unused settings and feature claims.
9. Generate or contract-test frontend wire types.
10. Add sequence-aware WebSocket resync and bounded byte-level retention.

## Completion criteria for this register

When fixing an item, include:

- a regression test that failed on the old behavior;
- operational or migration notes when persisted state is affected;
- updated API/frontend types for wire changes;
- updated risk row or removal with a link to the enforcing code/test;
- a fresh verification snapshot if test counts or status changed.
