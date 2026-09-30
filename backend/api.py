"""FastAPI HTTP/WebSocket interface and offline static frontend hosting."""

import asyncio
import json
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import __version__
from backend.contracts import ExperimentConfig
from backend.datasets.bootstrap import restore_bundled
from backend.datasets.catalog import ROOT, catalog, load_artifact, preview, safe_path, sha256
from backend.datasets.environment import build_world
from backend.environment.scenarios import SCENARIOS
from backend.experiments import Experiment, Registry
from backend.experiments.benchmark import Benchmark, BenchmarkConfig, benchmark_csv
from backend.experiments.engine import view_frame
from backend.experiments.registry import export_csv
from backend.metrics import METRIC_DEFINITIONS
from backend.scheduler import ALGORITHM_NAMES


class Control(BaseModel):
    experiment_id: str
    speed: Literal[1, 2, 4] = 1


class Runtime:
    def __init__(self, registry: Registry):
        self.registry = registry
        self.live: dict[str, Experiment] = {}
        self.speeds: dict[str, int] = {}
        self.locks: dict[str, asyncio.Lock] = {}
        self.tasks: list[asyncio.Task] = []
        self.benchmarks: dict[str, Benchmark] = {}

    async def start(self, config: ExperimentConfig, autoplay: bool):
        if sum(e.state in {"paused", "running"} for e in self.live.values()) >= 4:
            raise HTTPException(409, "Four experiments are already active. Reset or finish a run first.")
        effective, world = await asyncio.to_thread(build_world, config)
        experiment = Experiment(effective, world)
        experiment.state = "running" if autoplay else "paused"
        for run_id in list(self.live):
            if len(self.live) >= 8 and self.live[run_id].state in {"completed", "cancelled", "failed"}:
                self.live.pop(run_id)
                self.locks.pop(run_id, None)
                self.speeds.pop(run_id, None)
        self.live[experiment.id] = experiment
        self.speeds[experiment.id] = 1
        self.locks[experiment.id] = asyncio.Lock()
        self.tasks.append(asyncio.create_task(self.advance(experiment)))
        return experiment

    async def advance(self, experiment: Experiment):
        try:
            while experiment.state not in {"completed", "cancelled", "failed"}:
                if experiment.state == "running":
                    async with self.locks[experiment.id]:
                        if experiment.state == "running":
                            await asyncio.to_thread(experiment.step)
                await asyncio.sleep(0.1 / self.speeds.get(experiment.id, 1))
            await asyncio.to_thread(self.registry.save, experiment.record())
        except asyncio.CancelledError:
            raise
        except Exception as error:
            experiment.state = "failed"
            experiment.error = str(error)

    def get_live(self, run_id: str) -> Experiment:
        if run_id not in self.live:
            raise HTTPException(409, "This is a recorded run. Use replay or start a new live experiment.")
        return self.live[run_id]

    def record(self, run_id: str):
        return self.live[run_id].record() if run_id in self.live else self.registry.load(run_id)

    async def benchmark(self, job: Benchmark):
        try:
            for scenario in job.config.scenarios:
                for seed in range(job.config.seed, job.config.seed + job.config.runs):
                    await asyncio.to_thread(job.run_one, scenario, seed)
            job.state = "completed"
        except Exception as error:
            job.state, job.error = "failed", str(error)
        await asyncio.to_thread(job.persist)

    def benchmark_record(self, benchmark_id: str):
        if benchmark_id in self.benchmarks:
            return self.benchmarks[benchmark_id].snapshot()
        if not re.fullmatch(r"BENCH-[A-F0-9]{10}", benchmark_id):
            raise ValueError("Invalid benchmark ID")
        path = self.registry.directory / f"{benchmark_id}.json"
        if not path.exists():
            raise KeyError("Benchmark not found")
        return json.loads(path.read_text())


def create_app(registry_directory: Path | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application):
        if registry_directory is None:
            restore_bundled()
        directory = registry_directory or (Path(os.environ["AAMS_DATA_DIR"]) if "AAMS_DATA_DIR" in os.environ else None)
        runtime = Runtime(Registry(directory))
        application.state.runtime = runtime
        # Portable recordings are restored once if the local registry is empty.
        if registry_directory is None:
            known = {record["id"] for record in runtime.registry.list(10000)}
            for path in (ROOT / "data" / "demo").rglob("*.json.gz"):
                if path.name.removesuffix(".json.gz") in known:
                    continue
                import gzip
                record = json.loads(gzip.decompress(path.read_bytes()))
                if record["id"] not in known:
                    runtime.registry.import_record(record)
        if registry_directory is None:
            for path in (ROOT / "data" / "demo").glob("BENCH-*.json"):
                target = runtime.registry.directory / path.name
                if not target.exists():
                    target.write_bytes(path.read_bytes())
        yield
        for task in runtime.tasks:
            task.cancel()
        await asyncio.gather(*runtime.tasks, return_exceptions=True)

    app = FastAPI(title="AAMS-X Research API", version=__version__, lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(KeyError)
    async def not_found(_, error):
        return JSONResponse(status_code=404, content={"detail": str(error).strip("'")})

    @app.exception_handler(ValueError)
    async def invalid(_, error):
        return JSONResponse(status_code=422, content={"detail": str(error)})

    @app.get("/api/health")
    @app.get("/api/status")
    def status():
        datasets = catalog()
        default = next((d["id"] for d in datasets if d["category"] == "OFFICIAL_SYNTHETIC_RADAR" and d["status"] == "available" and d.get("ground_truth")), "simulation")
        return {"status": "ready", "version": __version__, "offline": True, "policy_input": "observations_only", "default_dataset": default, "available_datasets": sum(d["status"] == "available" for d in datasets), "algorithms": ALGORITHM_NAMES}

    @app.get("/api/scenarios")
    def scenarios():
        return SCENARIOS

    @app.get("/api/datasets")
    def datasets():
        return catalog()

    @app.get("/api/datasets/{dataset_id}/preview")
    def dataset_preview(dataset_id: str):
        return preview(dataset_id)

    @app.get("/api/datasets/{dataset_id}/export")
    def dataset_export(dataset_id: str, format: Literal["npz", "parquet"] = "npz"):
        _, manifest = load_artifact(dataset_id)
        path = safe_path(dataset_id, f".{format}")
        if not path.exists():
            raise KeyError("Requested dataset format is not available")
        expected = manifest["artifact_sha256" if format == "npz" else "parquet_sha256"]
        if sha256(path) != expected:
            raise ValueError("Dataset checksum mismatch")
        return FileResponse(path, filename=path.name, media_type="application/octet-stream")

    @app.get("/api/methodology")
    def methodology():
        return {"metrics": METRIC_DEFINITIONS, "truth_boundary": "Policies receive frozen PublicReceiver, DecisionContext, and selected-window Observation values only. No environment or evaluator reference is passed to a policy.", "algorithm": "MAG-NTS is an experimental composition of discounted Beta-Bernoulli learning, Thompson sampling, mutual information, observation-pattern memory, CUSUM, and recurrence fitting. Its composite score is a heuristic, not a proved optimal policy."}

    @app.post("/api/experiment/start")
    async def start(config: ExperimentConfig, autoplay: bool = True):
        experiment = await app.state.runtime.start(config, autoplay)
        return experiment.summary()

    @app.post("/api/experiment/pause")
    async def pause(control: Control):
        runtime = app.state.runtime
        experiment = runtime.get_live(control.experiment_id)
        async with runtime.locks[experiment.id]:
            if experiment.state == "running":
                experiment.state = "paused"
        return experiment.summary()

    @app.post("/api/experiment/resume")
    async def resume(control: Control):
        runtime = app.state.runtime
        experiment = runtime.get_live(control.experiment_id)
        runtime.speeds[experiment.id] = control.speed
        if experiment.state == "paused":
            experiment.state = "running"
        return experiment.summary()

    @app.post("/api/experiment/speed")
    async def speed(control: Control):
        runtime = app.state.runtime
        experiment = runtime.get_live(control.experiment_id)
        runtime.speeds[experiment.id] = control.speed
        return {"speed": control.speed}

    @app.post("/api/experiment/reset")
    async def reset(control: Control):
        runtime = app.state.runtime
        config = ExperimentConfig(**runtime.record(control.experiment_id)["config"])
        if control.experiment_id in runtime.live:
            async with runtime.locks[control.experiment_id]:
                if runtime.live[control.experiment_id].state in {"running", "paused"}:
                    runtime.live[control.experiment_id].state = "cancelled"
        return (await runtime.start(config, autoplay=False)).summary()

    @app.post("/api/experiment/stop")
    async def stop(control: Control):
        runtime = app.state.runtime
        experiment = runtime.get_live(control.experiment_id)
        async with runtime.locks[experiment.id]:
            if experiment.state in {"running", "paused"}:
                experiment.state = "cancelled"
        return experiment.summary()

    @app.post("/api/experiment/{run_id}/step")
    async def single_step(run_id: str, judge: bool = False):
        runtime = app.state.runtime
        experiment = runtime.get_live(run_id)
        async with runtime.locks[run_id]:
            if experiment.state != "paused":
                raise HTTPException(409, "Pause the live experiment before tracing one step")
            frame = await asyncio.to_thread(experiment.step)
        return view_frame(frame, judge)

    @app.get("/api/experiments")
    def experiments():
        runtime = app.state.runtime
        saved = {r["id"]: r for r in runtime.registry.list()}
        saved.update({key: exp.summary() for key, exp in runtime.live.items()})
        return sorted(saved.values(), key=lambda r: r["created_at"], reverse=True)[:60]

    @app.get("/api/experiment/{run_id}")
    def experiment(run_id: str):
        runtime = app.state.runtime
        record = runtime.live[run_id].summary() if run_id in runtime.live else runtime.registry.load(run_id)
        return {key: value for key, value in record.items() if key not in {"frames", "evaluation_tracks"}}

    @app.get("/api/experiment/{run_id}/metrics")
    def metrics(run_id: str):
        return experiment(run_id)["metrics"]

    @app.get("/api/experiment/{run_id}/trace")
    def trace(run_id: str, offset: int = Query(0, ge=0), limit: int = Query(360, ge=1, le=2000), judge: bool = False):
        runtime = app.state.runtime
        if run_id in runtime.live:
            run = runtime.live[run_id]
            frames, state = run.frames, run.state
        else:
            record = runtime.registry.load(run_id)
            frames, state = record["frames"], record["state"]
        return {"frames": [view_frame(f, judge) for f in frames[offset : offset + limit]], "total": len(frames), "state": state, "judge_view": judge}

    @app.get("/api/experiment/{run_id}/decisions")
    def decisions(run_id: str, policy: str = "magnts", offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)):
        frames = trace(run_id, offset, limit)["frames"]
        return [{"step": frame["step"], **frame["policies"][policy]["decision"]} for frame in frames if policy in frame["policies"]]

    @app.get("/api/experiment/{run_id}/evaluation")
    def evaluation(run_id: str, judge: bool = False):
        if not judge:
            raise HTTPException(403, "Enable EVALUATION / JUDGE VIEW to inspect hidden activity tracks")
        record = app.state.runtime.record(run_id)
        return {"label": "EVALUATION / JUDGE VIEW", "tracks": record["evaluation_tracks"], "ground_truth": record["dataset"].get("ground_truth", False)}

    @app.get("/api/experiment/{run_id}/export")
    def export(run_id: str, format: Literal["json", "csv"] = "json"):
        record = app.state.runtime.record(run_id)
        content = export_csv(record) if format == "csv" else json.dumps(record, allow_nan=False)
        return Response(content, media_type="text/csv" if format == "csv" else "application/json", headers={"Content-Disposition": f'attachment; filename="{run_id}.{format}"'})

    @app.post("/api/benchmark/start")
    async def start_benchmark(config: BenchmarkConfig):
        runtime = app.state.runtime
        if any(job.state == "running" for job in runtime.benchmarks.values()):
            raise HTTPException(409, "A benchmark is already running on this local instance")
        if config.dataset_id == "simulation" and any(s not in {p["id"] for p in SCENARIOS} for s in config.scenarios):
            raise ValueError("Unknown benchmark scenario")
        job = Benchmark(config, runtime.registry)
        runtime.benchmarks[job.id] = job
        runtime.tasks.append(asyncio.create_task(runtime.benchmark(job)))
        return job.snapshot()

    @app.get("/api/benchmarks")
    def benchmarks():
        runtime = app.state.runtime
        results = {path.stem: json.loads(path.read_text()) for path in runtime.registry.directory.glob("BENCH-*.json")}
        results.update({key: job.snapshot() for key, job in runtime.benchmarks.items()})
        return sorted(results.values(), key=lambda r: r["created_at"], reverse=True)

    @app.get("/api/benchmark/{benchmark_id}")
    def benchmark(benchmark_id: str):
        return app.state.runtime.benchmark_record(benchmark_id)

    @app.get("/api/benchmark/{benchmark_id}/export")
    def export_benchmark(benchmark_id: str, format: Literal["json", "csv"] = "csv"):
        record = app.state.runtime.benchmark_record(benchmark_id)
        return Response(benchmark_csv(record) if format == "csv" else json.dumps(record, allow_nan=False), media_type="text/csv" if format == "csv" else "application/json", headers={"Content-Disposition": f'attachment; filename="{benchmark_id}.{format}"'})

    @app.websocket("/ws/experiment/{run_id}")
    async def websocket(websocket: WebSocket, run_id: str):
        await websocket.accept()
        runtime = app.state.runtime
        try:
            judge = websocket.query_params.get("judge") == "true"
            cursor = max(0, int(websocket.query_params.get("since", "0")))
            recorded = None if run_id in runtime.live else await asyncio.to_thread(runtime.registry.load, run_id)
            while True:
                if recorded is not None:
                    frames, state = recorded["frames"], recorded["state"]
                else:
                    current = runtime.live.get(run_id)
                    if current is None:
                        break
                    frames, state = current.frames, current.state
                batch = frames[cursor : cursor + 8]
                await websocket.send_json({"type": "frames", "frames": [view_frame(f, judge) for f in batch], "state": state, "total": len(frames), "mode": "REPLAY" if recorded else "LIVE"})
                cursor += len(batch)
                try:
                    message = await asyncio.wait_for(websocket.receive_json(), timeout=0.09)
                    if message.get("command") == "judge":
                        judge = message.get("enabled") is True
                    elif message.get("command") == "seek":
                        cursor = max(0, int(message.get("step", 0)))
                except asyncio.TimeoutError:
                    pass
        except WebSocketDisconnect:
            pass
        except (KeyError, ValueError) as error:
            await websocket.send_json({"type": "error", "message": str(error)})
            await websocket.close(code=1008)

    static = ROOT / "frontend" / "dist"
    if static.exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="frontend")
    return app


app = create_app()
