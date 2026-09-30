# Validation record

## Executed in this workspace

- Python 3.12.5 and Node.js 22.23.2.
- **32 backend tests passed:** observation truth boundary and counterfactual noninterference, receiver limits/dwell, seed/configuration round trips, beliefs, memory, CUSUM, periodicity, baseline/ablation geometry, hand-calculated metrics, prospective forecasting, recording checksums, exports, HTTP/WebSocket behavior, FITS/HDF5 ingestion, missing channels and causal calibration.
- Backend/script Ruff checks.
- TypeScript production build and ESLint.
- Complete seeded sudden, periodic, agile and genuine measured RF scheduler runs.
- Exact deterministic reruns and JSON/CSV replay/export checks.
- A 30-world / 180-policy benchmark over all ten presets and consecutive seeds 42–44.
- **Four Chromium browser workflows passed:** live controls, decision explanations, downloads, replay, all navigation, periodic candidates, a genuine **WebGL 2 / Three.js** renderer, camera controls, measured-data inspection, benchmark execution, responsive navigation and missing-dataset fallback.
- The production `./start_demo.sh` launcher was started successfully; the dashboard, health/catalog API, bundled benchmark and observation-only trace endpoint were verified at `http://127.0.0.1:8000`.
- Screenshots in `docs/screenshots/` are captured from the running application, not mockups.

Commands and locked dependencies are supplied so these checks can be repeated locally. The current FastAPI/Starlette test client emits upstream deprecation notices; Vite reports the large Three.js vendor chunk. These are distinct from application runtime errors.

## Fixes found through validation

- Normalized receiver defaults and time-coordinate dtype so a serialized/reset configuration reproduces the identical world fingerprint.
- Preserved all-NaN duplicate FITS channels without an empty-mean warning.
- Removed redundant frontend updates for empty WebSocket heartbeat batches.
- Disabled replay controls while a new trace is loading and prevented stale trace fetches from truncating later received frames.
- Bundled the full benchmark's exact traces, so replay links work with an initially empty local registry.
- Kept WebGL fallback content from mounting an unnecessary nested canvas.
- Rendered original dataset previews on physical time/frequency coordinates, preserving irregular gaps.

## Official TSRD evaluation (2026-09-30)

The authorized official validation recording is installed: 648,034 pulses, source and processed artifact checksums verified. Executed 24 paired worlds / 192 policy evaluations, across six seeds, four receiver budgets and eight policies. All 24 replay files passed checksum verification. The backend suite now passes 36 tests, including actual-recording provenance, deterministic reruns, official benchmark HTTP acceptance and HTTP response compression. TypeScript and production frontend builds passed. GitHub Actions independently repeated all 36 tests and the production build successfully. See [full results](validation/tsrd/README.md).

Fresh publisher downloads require account-holder approval. The current evaluation covers one synthetic validation recording with modeled receiver energy. It does not establish field performance or the publisher's separate deinterleaving benchmark accuracy.

## Public Azure validation (2026-09-30)

The public HTTPS website passed a fresh Chromium workflow covering all eleven pages, official TSRD availability, the four stored benchmarks and CSV exports, replay navigation, 3D camera interaction, a complete 96-slot live TSRD run and observation-only trace retrieval. A 390-pixel mobile workflow exercised the navigation and Benchmark Lab. The desktop browser recorded no JavaScript page errors. Public screenshots accompany the repository. These are software/browser checks, not operational radar trials or a guarantee of uninterrupted hosting.

## Validation scope

The browser checks cover Chromium and a 390-pixel mobile viewport; they are not a comprehensive cross-browser or accessibility certification. The simulator and digital twin are software abstractions. No live SDR hardware, calibrated operational RF receiver or field trial was evaluated.
