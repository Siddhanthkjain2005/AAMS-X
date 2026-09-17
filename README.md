# AAMS-X

## Adaptive Autonomous Mission Spectrum eXplorer

An offline-first foundation for public RF recording inspection, reproducible
synthetic intensity demonstrations, provenance, and recorded playback.

## Scope of this build

This is a source-code foundation for the data and visualization portions of
a research platform. It is not the complete adaptive scheduling application.

Implemented in the supplied source:

- Deterministic, explicitly synthetic intensity demonstration.
- Validated common-layout e-CALLISTO FITS ingestion.
- Immutable local NPZ recordings and JSON provenance manifests.
- Source and artifact checksums.
- Missing-data preservation and irregular channel coordinates.
- FastAPI recording catalog, preview, export, and playback WebSocket.
- React recorded-spectrum dashboard.
- Time-frequency waterfall.
- Frequency profile with gaps for missing values.
- Buffered 3D time-frequency-intensity point cloud.
- Recorded playback, pause, reset, scrubbing, and display speed controls.
- Data provenance, architecture trace, and limitations screens.
- Backend tests and frontend type-check/build commands.

Not implemented:

- Adaptive receiver tasking or MAG-NTS.
- Interception optimization.
- Receiver or detector benchmarks.
- Emitter classification, localization, or targeting.
- Radar PDW ingestion.
- Live SDR hardware integration.
- Scheduler truth-isolation tests: no scheduler exists in this build.

The interface reports unavailable capabilities rather than displaying fabricated
metrics or fake public datasets.

## Research context

A bandwidth-limited receiver cannot simultaneously observe every frequency in a
larger monitored spectrum. That creates a partial-observation sensing problem.

Before evaluating any sensing model, the data pipeline must preserve frequency
and time coordinates, measurement units, missing data, source provenance, and
the distinction between synthetic and measured observations.

This build addresses that foundation. Its playback cursor is not a receiver
scan action. No policy is observing or learning from the displayed recordings.

## Architecture

The following is Mermaid diagram source, presented as an indented code block
to avoid nested file-listing fences:

    flowchart TD
        A[Seeded intensity demonstration] --> C[Validated ingestion]
        B[Local public e-CALLISTO FITS] --> C
        C --> D[NPZ recording]
        C --> E[JSON provenance and checksums]
        D --> F[Read-only FastAPI]
        E --> F
        F --> G[Bounded preview]
        F --> H[Original artifact export]
        F --> I[Recorded WebSocket playback]
        G --> J[React inspection dashboard]
        J --> K[Waterfall]
        J --> L[Frequency profile]
        J --> M[3D intensity cube]
        J --> N[Provenance and limitations]

## Requirements

- macOS or another Unix-like environment.
- Python 3.11 or newer.
- Node.js 20.19 or newer and npm.
- Internet for initial dependency installation only.
- A browser with WebGL for the optional 3D view.

The application uses system fonts. It has no remote font, analytics, map,
authentication, or dataset API dependency.

## Setup

From the repository root:

    bash scripts/setup.sh

This:

1. Creates `.venv`.
2. Installs backend and test dependencies.
3. Creates a seed-42 synthetic intensity recording.
4. Installs frontend dependencies.
5. Type-checks and builds the frontend.

After reviewing a successful installation, commit the generated
`frontend/package-lock.json` to lock the JavaScript dependency graph.

Python dependencies currently use bounded version ranges. For archival
reproducibility, record the tested environment:

    .venv/bin/python -m pip freeze > environment-tested.txt

A lock file is not supplied here because dependencies have not been resolved
or tested in an execution environment.

## Start

    bash start_demo.sh

Open:

- Dashboard: http://127.0.0.1:5173
- API docs: http://127.0.0.1:8000/docs

For executable script commands:

    chmod +x start_demo.sh run_tests.sh scripts/setup.sh
    ./start_demo.sh

The start script performs no dependency downloads.

Both services bind to localhost. This is not an internet-facing deployment.

## Demonstration

1. Open Spectrum replay.
2. Select the seed-42 intensity demonstration.
3. Read the CONTROLLED SIMULATION provenance notice.
4. Press Start replay.
5. Inspect the time-frequency waterfall and missing-data patch.
6. Pause and scrub to a recorded time.
7. Inspect the corresponding frequency profile.
8. Orbit the Spectrum Intelligence Cube.
9. Open Data provenance and inspect preprocessing lineage and checksums.
10. Export the original NPZ recording.
11. Use Architecture to trace the recording through ingestion and visualization.

Every playback mode is explicitly labelled recorded replay.

No detection, accuracy, interception, or improvement percentages are invented.

## Optional measured data

See [docs/data.md](docs/data.md) for supported e-CALLISTO FITS structure.

Example:

    .venv/bin/python -m backend.ingest callisto data/raw/recording.fit

Then press Refresh catalog.

The simulator demonstration remains usable when no public dataset is installed.

No measured data ships in this repository.

## API

| Method | Route | Purpose |
| --- | --- | --- |
| GET | /api/health | Service status and scope |
| GET | /api/datasets | Recordings and integration availability |
| GET | /api/recordings/{id} | Provenance manifest |
| GET | /api/recordings/{id}/preview | Bounded intensity preview |
| GET | /api/recordings/{id}/export | Original validated NPZ artifact |
| WS | /ws/recordings/{id} | Explicitly labelled recorded frames |

Preview parameters:

- `max_times`: 2–240, default 160.
- `max_channels`: 2–128, default 96.

WebSocket playback sends one sampled row at a time, rather than a full recording
matrix per frame.

The browser uses a cached bounded preview for immediate scrubbing. This is
recorded playback, not a disguised live stream.

## Internal format

    time_s: float64[T]
    frequency_mhz: float64[F]
    intensity: float32[T, F]

Intensity has no universal calibrated unit. The original BUNIT is retained when
available; otherwise it is labelled uncalibrated.

Missing values remain NaN on disk and become null in JSON.

Arrays are loaded with `allow_pickle=False`.

## Reproducibility

The seed controls the demonstration's array generation.

Artifact replay reproduces the saved values exactly. Unique recording IDs and
ingestion timestamps are metadata, not scientific result variation.

Artifact checksums are verified before preview and export.

Tests compare array values, not generated identifiers or compressed-container
timestamps.

## Testing

    bash run_tests.sh

Tests cover:

- Seed determinism.
- Channel sorting and missing values.
- Invalid axis rejection.
- Recording serialization and exact array replay.
- Strict JSON serialization.
- Checksum mismatch detection.
- Recording-ID path traversal rejection.
- Explicit synthetic FITS fixture ingestion.
- API health and export.
- Bounded previews.
- Explicitly labelled WebSocket playback.

Frontend validation consists of TypeScript checking and Vite production build.
No browser automation or screenshot tests are included.

## Performance

- Recording import is capped at 2,000,000 cells.
- Default preview is capped at 160 × 96 samples.
- WebSocket playback sends at most 96 intensity values per frame.
- The 3D view uses a single buffered point cloud with approximately 7,000 or
  fewer displayed points.
- Browser pixel ratio is capped for 3D rendering.
- Original arrays remain available through export.
- No raw dataset is repeatedly transmitted during playback.

Uniform index sampling is intended for inspection and may omit narrow or brief
features. It is not a substitute for analysis of the full original recording.

## Limitations

- This is a research recording viewer, not a full receiver digital twin.
- The synthetic demonstration is not a validated physical RF model.
- e-CALLISTO observations do not provide labelled EW emitter ground truth.
- The FITS adapter supports one explicit common layout, not every station
  convention or arbitrary FITS schema.
- Absolute time interpretation must be checked against source documentation.
- Public synthetic radar integration is not implemented.
- Checksums do not authenticate the origin of a downloaded source.
- Backend storage has no user authentication or multi-user access controls.
- No browser performance or accessibility audit has been executed.
- Results must not be described as operational field validation.

## Safe future extensions

- Additional verified public recording formats.
- Schema-specific dataset inspection.
- Calibration metadata validation.
- Large-recording chunking and multiresolution display artifacts.
- Browser automation and accessibility testing.
- Portable dependency locks after a tested installation.
- Dataset licensing and citation manifests.
- Better missing-channel visualization and uncertainty in measurement
  calibration.

## Validation status

The source includes tests and build commands. Their execution is not claimed.

Before demonstrating:

1. Run setup.
2. Run backend tests.
3. Run frontend type checking and build.
4. Start both services.
5. Verify replay, pause, reset, scrub, and speed controls.
6. Verify waterfall, profile, and 3D fallback.
7. Export and reopen an NPZ artifact.
8. Import an actual public FITS file if available.
9. Confirm measured versus synthetic badges.
10. Check browser console and backend logs.

Screenshots are intentionally not included until the application has been run.
