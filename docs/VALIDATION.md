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

## Remaining external prerequisite

**An authorized Alan Turing Institute TSRD HDF5 subset is not installed.** The publisher requires account-holder access approval. The schema-specific importer is tested with explicitly synthetic test fixtures, but those fixtures are not distributed as official data and are never advertised as a genuine TSRD import.

Accept the publisher's conditions, then use `backend.datasets.fetch turing` with a locally supplied `HF_TOKEN`, or import an authorized local file using `backend.datasets.ingest turing ... --receiver-mode stare`. Until then, the UI reports **ACCESS REQUIRED**, and an end-to-end official-data evaluation cannot be claimed.

## Validation scope

The browser checks cover Chromium and a 390-pixel mobile viewport; they are not a comprehensive cross-browser or accessibility certification. The simulator and digital twin are software abstractions. No live SDR hardware, calibrated operational RF receiver or field trial was evaluated.
