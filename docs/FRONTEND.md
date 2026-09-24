# Frontend guide

The frontend is a React single-page application under `web/`. It is an experiment
console, visualization layer and report launcher; it does not implement scientific
calculations that the backend could authoritatively provide.

## Runtime shape

```mermaid
flowchart TB
    Router[BrowserRouter] --> App[App shell]
    Query[TanStack Query] --> App
    Zustand[Zustand session choices] --> Live[LiveProvider]
    Live --> Socket[one ExperimentStream WebSocket]
    Socket --> Ring[4,000-frame ring]
    Socket --> State[throttled React snapshot]
    App --> Screens[lazy-loaded screens]
    Query --> REST[/api REST client]
    Ring --> Canvas[canvas / WebGL visuals]
    State --> Text[text, status and controls]
```

`web/src/main.tsx` mounts `QueryClientProvider`, `BrowserRouter`, `LiveProvider`, an
error boundary and `App`. Strict Mode is enabled. `App.tsx` provides the background,
sidebar, top bar and data-status banner. Demo Mode is rendered outside the normal shell.

Screens are lazy-loaded so ECharts and Three.js are split from the first application
chunk. Vite also creates named React, ECharts and Three.js groups. Production sourcemaps
are enabled.

## Route and feature map

| Route | Screen | Main purpose | Primary data |
|---|---|---|---|
| `/` | Command Center | launch and watch an episode; live waterfall, band state, KPIs and decision terms | shared stream + scenario detail |
| `/replay` | Real Spectrum Replay | browse cached recordings, spectrogram, provenance and retrospective analytics | datasets, spectrogram, analytics REST |
| `/timeline` | Event Timeline | filter meaningful run events and scrub all explain screens to a step | shared stream timeline + cursor |
| `/belief` | Belief Map | inspect posterior, uncertainty, staleness and optional reference overlay | shared frames + scenario detail |
| `/decision` | Decision Inspector | inspect candidate scores, eight contributions, reward and oracle comparison | shared frames |
| `/memory` | Associative Memory | inspect prototypes, retrieval weights, preference matrices and recognition history | stream plus stored episode result |
| `/arena` | Algorithm Arena | launch policy comparisons and inspect aggregate metrics/significance | batch socket + stored batch result |
| `/ablation` | Ablation Lab | launch and inspect seven component rungs | batch socket + stored batch result |
| `/lab` | Experiment Lab | choose presets, search indexed windows, assemble and validate a custom scenario | scenarios, datasets, window query, validation |
| `/analytics` | Analytics & Pareto | inspect objective frontier, comparisons, effects and latency | selected stored/live batch |
| `/registry` | Registry | filter runs, group by config hash, load/cancel/replay/select for reports | active + history REST |
| `/reports` | Reports | choose experiment sections, generate, preview and open self-contained reports | history + report REST |
| `/demo` | Demo Mode | full-screen presentation scenes over the selected episode | shared stream + stored result fallback |
| other | Not Found | route recovery | navigation list |

The navigation source is `web/src/lib/nav.ts`; the actual route source is `App.tsx`.
Both must change together. At present, two Registry buttons navigate to `/inspector`, but
the route is `/decision`; this is a known defect listed in the risk register.

## Server-state model

`web/src/api/client.ts` is the only HTTP client. It always uses a path base, normally
`/api`. An absolute `VITE_API_BASE` is intentionally ignored. Query parameters use
`URLSearchParams`, path parameters use `encodeURIComponent`, and JSON request bodies set
`Content-Type: application/json`.

Failed responses become `ApiError(status, detail, url)`. The client preserves FastAPI's
`detail` field for user-facing errors. A network failure becomes status 0 with a hint to
start the API.

`web/src/api/queries.ts` owns query keys and invalidation:

| Data | Cache/poll behavior |
|---|---|
| status | stale after 5 seconds, polled every 15 seconds |
| schedulers/scenarios/datasets/details | stale after 30 minutes; no focus refetch |
| active sessions | polls every 4 seconds when active, 12 seconds when idle |
| history | normal query defaults; parameters are part of key |
| experiment detail | caller controls polling/staleness |
| reports | stale after 1 minute |

Launches invalidate active sessions, all history keys and status. Cancels/replays use the
same invalidation. Report creation invalidates report listing. Mutations do not retry.

The TypeScript wire types in `web/src/api/types.ts` are handwritten. They must be compared
with Pydantic models, runner frames and batch result serialization whenever the backend
changes.

## Cross-screen user state

`web/src/state/session.ts` uses Zustand. It holds only choices that need to survive route
changes:

- selected episode id;
- scrub cursor (`null` means follow the live edge);
- selected batch id;
- next episode launch settings;
- report-section selection.

Only `launch` is persisted to localStorage under `aamsx.session`. Episode/batch ids,
cursor and report selection are intentionally not restored after a page reload. The
persisted launch includes scenario, scheduler, seed, pace, frame stride, ablation flags and
MAG-NTS weights.

TanStack Query, not Zustand, owns REST results. The frame ring, not Zustand or Query, owns
high-rate frames.

## Live streaming

`LiveProvider` watches the selected episode id and mounts one `ExperimentStream` for the
entire console. Navigating among explain screens therefore does not deliberately open a
new socket.

The stream class:

1. opens `ws://` or `wss://` to the current page host and `/api/experiments/{id}/stream`;
2. stores frame messages in a 4,000-slot circular buffer;
3. coalesces React notifications on a 100 ms interval;
4. sends session, status, timeline, progress, completion and errors directly to listeners;
5. retries once after an unfinished connection closes;
6. closes and clears listeners when the selected id changes or provider unmounts.

Canvas/WebGL components can read the mutable ring on `requestAnimationFrame`. Text
components receive the throttled immutable snapshot. This prevents a full React tree
render for every incoming frame.

The retry opens a new subscription and the server re-sends retained frames. The client
does not deduplicate by step or clear the ring before reconnecting, so a reconnect can
append duplicate frames. A slow server subscriber can also miss messages silently because
the server drops queue entries. These are documented risks, not guaranteed replay
semantics.

## Finished-run behavior

Stored experiment detail contains final results but not the 4,000 live frames. The shared
socket works only while the server process still retains that session. After session
eviction or restart, selecting an older episode can load its final curves/snapshots in
screens that explicitly query `GET /experiments/{id}`, but the waterfall, per-step belief
and decision screens cannot reconstruct all frames from the trace.

This differs from the optimistic comment in `RunPicker.tsx` that says a finished run loads
over the socket. Treat the implementation described here as authoritative.

## Core user flows

### Launch and inspect one episode

1. `LaunchPanel` loads scenarios and schedulers.
2. When no scenario is saved, it chooses the first buildable preset.
3. The user selects policy/seed and optionally pace, stride, flags and MAG weights.
4. `POST /api/experiments` returns a new id.
5. Zustand selects that id; `LiveProvider` opens the socket.
6. Command Center, Belief, Decision, Timeline and Memory read the same stream.
7. Dragging the status-bar slider sets a shared frame cursor; moving to the last retained
   frame resets it to live mode.
8. Cancel requests best-effort cancellation. Replay starts a new execution at pace 60 and
   selects the new id.

An ablation warning appears when any of six main intelligence flags is disabled. Neural
encoder state is not considered by `isFullPolicy`.

### Explore real recordings

1. Replay loads dataset catalogue and adapters.
2. It chooses a recording and local display controls for offset, span, region count and
   time bin.
3. Spectrogram and analytics queries share those parameters.
4. The waterfall/terrain renders measured margin; label and provenance panels explain the
   derived occupancy boundary.
5. Retrospective activity, change scan and region occupancy are explicitly separated from
   online scheduler results.

### Build a custom scenario

1. Experiment Lab gets recordings and builds a fixed-vocabulary SQL predicate in the
   browser; users do not enter free-form SQL in this screen.
2. It queries indexed windows and lets the user append up to six displayed phases.
3. It composes a `ScenarioRequest` with receiver, budget, split and segment data.
4. Validate calls `/scenarios/validate` and displays measured behavior.
5. Run sends the inline scenario directly to `/experiments` and selects the returned id.

The backend remains responsible for existence, geometry and horizon validation.

### Run an arena or ablation

1. `BatchLauncher` chooses a buildable preset and a seed count from 3, 5, 8, 12 or 20.
2. Arena allows toggling policies; ablation always estimates seven arms.
3. The launch stores the batch id in Zustand.
4. `useBatchResult` opens a dedicated batch WebSocket and also queries stored detail.
5. It prefers any complete live result, then the stored result, and never treats partial
   progress as final aggregate data.
6. Arena/Ablation/Analytics reuse that selected batch id.

### Generate a report

1. Registry or Reports adds up to 24 ids to an in-memory selection.
2. Reports resolves rows from history and posts the ordered ids, title and notes.
3. The API writes HTML and returns its name.
4. The browser previews the report in a sandboxed iframe or opens its API URL.

## Visualization ownership

Reusable visualization components live in `web/src/components/viz`:

- `Waterfall` and `FieldWaterfall` render frame history on Canvas;
- `RegionBars` renders band vectors and selected windows;
- `FactorBars` renders signed decision contributions;
- `Sparkline` renders compact trend lines;
- `Chart` wraps ECharts and error-bar helpers;
- `Surface3D` and `MemoryConstellation` use React Three Fiber;
- palette ramps centrally define measured spectrum, belief, uncertainty and memory colors.

Fixed color ramps help compare screens, but color does not establish data provenance. The
screen labels and backend `kind`/provenance fields carry that meaning.

## Loading, errors and accessibility

The shell and individual screens use explicit loading, empty and error states. The root
error boundary keeps the shell navigable after a screen exception. Query errors preserve
server detail. A 503 is considered missing setup data and is not retried.

Controls generally have labels or screen-reader text. Canvas and WebGL-heavy displays
need accompanying text/tables for accessibility. `usePrefersReducedMotion` exists for
motion-sensitive rendering, but not every Three.js animation is guaranteed to stop.

There is no frontend authentication flow, user identity, permission-aware navigation, or
internationalization layer.

## Development and validation

From `web/`:

```bash
npm ci
npm run dev
npm run typecheck
npm test
npm run build
```

The declared minimum is Node 20.19. Vite development serves port 5173 and proxies `/api`
and WebSocket upgrades to `AAMSX_API_TARGET`, default `http://127.0.0.1:8000`.

Vitest is configured for `src/**/*.test.ts`, but the repository currently contains no
frontend test files. `npm test` therefore exits nonzero unless `--passWithNoTests` is used.
TypeScript checking and production build are the current automated frontend safety net.

## Frontend change checklist

- [ ] Confirm the route and navigation strings match.
- [ ] Add/update the API method and shared query key.
- [ ] Match the Pydantic/runner field names exactly in `api/types.ts`.
- [ ] Decide whether data belongs in Query, the frame ring, or Zustand.
- [ ] Handle no id, connecting, live, complete, failed, cancelled and evicted states.
- [ ] Keep high-frequency data out of global React state.
- [ ] Add a readable text/table alternative to a visual result.
- [ ] Test reconnect and long-frame histories when changing stream code.
- [ ] Run typecheck and a Node 20.19+ production build.
- [ ] Add Vitest coverage when introducing behavior that can be tested outside a browser.
