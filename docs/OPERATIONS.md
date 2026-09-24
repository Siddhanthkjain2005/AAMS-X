# Operations and deployment

This is the runbook for local development, Docker, the current single-host AWS shape,
configuration, logs and failure diagnosis.

## First local run

### Backend and data

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

python scripts/fetch_real_data.py
python scripts/build_index.py

uvicorn aamsx.api.app:create_app --factory --reload --port 8000
```

The data fetch is the only required network step and is safe to rerun; already cached
manifests are skipped. The index must be rebuilt after the cache or calibration changes.
The API starts even if these steps were skipped, but scenario and data operations will
report the missing cache/index.

Verify:

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/api/status
```

Open `http://127.0.0.1:8000/api/docs` for the generated REST schema.

### Frontend

In another terminal:

```bash
cd web
npm ci
npm run dev
```

Use Node 20.19 or newer. Open `http://127.0.0.1:5173`. Vite proxies `/api` and WebSocket
upgrades to the backend, so the browser uses one origin.

### Make shortcuts

`make setup`, `make data`, `make index`, `make test`, `make api`, `make web`, and
`make web-build` wrap the commands above. `make` by itself lists targets.

## Configuration reference

Pydantic Settings uses the `AAMSX_` prefix, reads `.env`, ignores unknown fields, and is
cached after first access. Restart a running process after configuration changes.

| Variable | Default | Current use |
|---|---:|---|
| `AAMSX_DATA_DIR` | repository `data/` | cache, index, SQLite and trace root |
| `AAMSX_REPORTS_DIR` | `reports/out/` | generated reports and script outputs |
| `AAMSX_CALLISTO_ARCHIVE` | public HTTP archive | e-CALLISTO listing/download root |
| `AAMSX_HTTP_TIMEOUT_SEC` | 45 | HTTP clients/probes |
| `AAMSX_FETCH_CONCURRENCY` | 8 | parallel e-CALLISTO downloads |
| `AAMSX_ALLOW_NETWORK` | true | blocks ingestion/ElectroSense network paths when false |
| `AAMSX_ELECTROSENSE_API` | `https://electrosense.org/api` | optional retired-service adapter |
| `AAMSX_ELECTROSENSE_USER` | unset | optional Basic Auth, server-side only |
| `AAMSX_ELECTROSENSE_PASSWORD` | unset | optional Basic Auth, server-side only |
| `AAMSX_DB_PER_DIGIT` | 0.25 | fresh-recording calibration |
| `AAMSX_OCCUPANCY_THRESHOLD_DB` | 1.5 | minimum fresh-recording threshold |
| `AAMSX_OCCUPANCY_K_MAD` | 5.0 | fresh-recording noise multiplier |
| `AAMSX_BASELINE_PERCENTILE` | 10.0 | fresh-recording baseline quantile |
| `AAMSX_MAX_CONCURRENT_EXPERIMENTS` | 4 | **declared but not enforced** |
| `AAMSX_EVENT_QUEUE_SIZE` | 4096 | **declared but ignored; subscriber queue is 512** |
| `AAMSX_BATCH_WORKERS` | 0 | tuning script only; normal batch default ignores it |
| `AAMSX_ENABLE_NEURAL` | false | displayed by CLI only; ablation flag controls encoder |
| `AAMSX_ENABLE_DEEP_RL` | false | **not used to gate DQN registration** |
| `AAMSX_CORS_ORIGINS` | local Vite origins | CORS allowlist; preview origin is always added |
| `AAMSX_MAX_UPLOAD_BYTES` | 256 MiB | local SigMF loader; no HTTP upload route |
| `AAMSX_LOG_LEVEL` | INFO unless caller supplies | root logging threshold |
| `AAMSX_LOG_JSON` | false | JSON-line versus human log formatter |

Frontend/runtime build values:

| Variable | Use |
|---|---|
| `VITE_API_BASE` | build-time path such as `/api`; absolute hosts are rejected by client |
| `VITE_WS_BASE` | declared in Docker/env types but not read by the client |
| `AAMSX_API_TARGET` | Vite development proxy target only |

Do not put a secret in a `VITE_` variable; Vite embeds it in public JavaScript. Do not
commit `.env`.

### Calibration change procedure

Stored recordings carry their calibration arrays. Changing environment defaults alone
does not recalculate an already cached recording. To make a calibration change real:

1. record the old setting and intended scientific reason;
2. refetch/reimport with `--force` or provide a migration/recalibration command;
3. verify each manifest contains the new calibration;
4. rebuild the window index;
5. restart the API to clear preset caches;
6. rerun benchmark, ablation and sensitivity artefacts;
7. run `make verify-docs` and update research text.

There is a current writer discrepancy: for a fresh `RawRecording` without an attached
calibration, `write_recording` computes a calibration from Settings but calls
`raw.to_cube()` without passing it when building occupancy summaries. Defaults currently
coincide; non-default settings can make manifest/channel calibration and summary values
inconsistent. Fix this before using custom calibration for published results.

## Logs and observability

`aamsx/logging.py` configures the root logger. Human logs show time, level, logger and
message. JSON mode includes time, level, logger, message and extra scalar fields.

Useful events include API startup/cache warnings, cache/index writes, scenario
unavailability, engine failures, subscriber lag and report writes.

There are currently no:

- request ids or correlation ids;
- access-log configuration in application code;
- structured trace/span context;
- Prometheus metrics or dashboards;
- queue depth, experiment duration or memory gauges;
- alert rules;
- centralized log shipping configuration.

For local debugging, run Uvicorn in the foreground and set `AAMSX_LOG_LEVEL=DEBUG`.
Do not enable debug/error responses on an untrusted network; unhandled responses and
registry error fields can include internal details.

## Docker

### Local Compose

```bash
docker compose up --build -d
```

This publishes:

- API directly on host port 8000;
- nginx/frontend on host port 5173;
- API internally to nginx under `/api`.

It bind-mounts `./data` and `./reports/out`, disables network access in the serving API,
and preserves data across image rebuilds.

One-shot tool services are behind the `tools` profile:

```bash
docker compose run --rm fetch
docker compose run --rm index
docker compose run --rm benchmark
```

The backend image is a two-stage Python 3.12 slim build and runs as UID 10001. The
frontend image is Node 22 Alpine build output served by nginx 1.27 Alpine. Tags are not
pinned by digest.

### Health checks

- Backend: `GET /api/health`, which intentionally does not verify cache/index/SQLite.
- Frontend: nginx root page.
- `GET /api/status` is the operational readiness view for recordings, index rows and
  presets.

A green container health check proves the process answers, not that experiments are
ready. Read `/api/status` warnings as well.

## AWS single-host deployment

`docker-compose.aws.yml` and `deploy/aws-user-data.sh` describe a low-cost single-EC2
deployment:

```mermaid
flowchart LR
    Browser -->|HTTP 80| Nginx[web container / nginx]
    Nginx -->|private Docker network /api| API[FastAPI container]
    API --> Data[/opt/aamsx/data bind mount]
    API --> Reports[/opt/aamsx/reports/out bind mount]
```

The API is not published directly. nginx is the only public container port and proxies
REST plus WebSocket upgrades. The instance bootstrap:

1. installs Docker and tar on Amazon Linux;
2. enables a 2 GiB swap file;
3. downloads a prepared source/data bundle into `/opt/aamsx`;
4. builds both images on the instance;
5. creates a private Docker network;
6. starts and health-checks the API;
7. starts nginx on port 80;
8. marks deployment ready after local health succeeds.

The supplied configuration is **HTTP-only**. For the current numeric address, use
`http://16.112.158.79/`, not `https://16.112.158.79/`. The HTTPS URL will time out or fail
because nothing listens on port 443 and no certificate is configured. An EC2 public IP can
also change after stop/start unless an Elastic IP or DNS record is assigned.

### Instance update procedure

The bootstrap script is designed for first boot, not in-place upgrades: it uses fixed
container names and creates the network without an idempotent “already exists” path. For
a controlled update:

1. snapshot or copy `/opt/aamsx/data`, `registry.sqlite`, `data/traces`, and reports;
2. upload/extract the new bundle into a versioned directory;
3. build images before stopping the working containers;
4. run backend tests and frontend build for that bundle;
5. stop/replace containers with explicit names and the existing bind mounts;
6. check API health, `/api/status`, SPA load and one WebSocket experiment;
7. keep the previous images/bundle for rollback.

Do not rerun the current bootstrap unchanged on a live instance expecting a safe upgrade.

### Low-cost sizing

The UI and single episodes are suitable for a small CPU instance. Default arena/ablation
workers use `cpu_count - 1`; on a small instance explicitly set API `workers` to 1 or a
small number in the request. The configured `AAMSX_BATCH_WORKERS` does not constrain the
API. Concurrent 4,000-frame sessions can consume significant RAM, and no engine-wide
limit is enforced.

## Production-readiness gate

The current AWS shape is a demo/research deployment. Before treating it as a public
production service, complete at least:

- [ ] DNS name and TLS termination with HTTP→HTTPS redirect;
- [ ] authentication and authorization for experiments, data and reports;
- [ ] ownership/tenant fields in registry and report access control;
- [ ] replace the raw SQL window API with a typed filter grammar;
- [ ] per-IP/user rate limits and experiment concurrency enforcement;
- [ ] request/body/response limits at nginx and FastAPI;
- [ ] remove internal exception text/tracebacks from public responses;
- [ ] security headers and an explicit Content Security Policy;
- [ ] disable or separately publish production sourcemaps;
- [ ] backup, restore test, retention and disk-capacity alerts;
- [ ] atomic cache/index/trace/report writes and a SQLite migration strategy;
- [ ] centralized logs, metrics, request ids and alerts;
- [ ] graceful shutdown and active-job recovery semantics;
- [ ] immutable image versions, vulnerability scanning and dependency updates;
- [ ] load testing for spectrogram JSON, WebSockets and process-pool batches.

## Backup and recovery

No backup job is included. The material state is:

| State | Back up? | Recoverability |
|---|---|---|
| cached public recordings | optional but saves download time | refetchable while archive exists |
| window index | optional | rebuildable from cache |
| `mag_nts_tuning.json` | yes for audit | expensive to reproduce |
| `registry.sqlite` | yes | not reconstructable from traces alone without tooling |
| `data/traces` | yes | required for stored result/report detail |
| generated reports | optional if traces remain | regenerable from traces/registry |
| benchmark/ablation JSON | yes for published claims | reproducible but expensive |

Back up SQLite and traces together. Because result-file and row updates are not atomic,
validate that every completed registry id has readable trace JSON after a restore.

## Failure diagnosis

| Symptom | Check | Likely action |
|---|---|---|
| browser cannot connect to numeric AWS address | URL scheme and security group | use HTTP port 80; add TLS before HTTPS |
| nginx page loads but API fails | `/api/health`, API container logs/network | restart/replace API; verify `api` container name |
| `/api/status` warns cache empty | data bind mount and `AAMSX_DATA_DIR` | restore/fetch cache |
| scenarios unavailable | index file, index row count, recordings | rebuild index, then restart API |
| WebSocket closes for old id | in-memory session evicted or process restarted | inspect stored final result; rerun for per-frame views |
| batch overwhelms small host | request workers and concurrent runs | use worker 1; serialize batches |
| report missing content | registry row and trace JSON | wait for completion or repair missing trace |
| `npm` fails on `node:util styleText` | Node version | upgrade to Node 20.19+ |
| API/CLI integration tests fail creating symlinked temp dirs | `Settings.ensure_dirs` and test symlink targets | use a resolvable target or fix symlink-aware directory creation |
| old preset remains after rebuilding index | process cache | restart API/CLI process |

## Release verification

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy aamsx
.venv/bin/pytest
.venv/bin/python scripts/verify_docs.py

cd web
npm run typecheck
npm test
npm run build
```

Also manually check `/api/status`, OpenAPI, one episode WebSocket, one cancel/replay, one
small batch, a generated report, SPA deep-link refresh, and the exact deployed URL scheme.
