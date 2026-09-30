"""Reproduce official TSRD comparisons; never select only winning seeds."""
import json
from pathlib import Path
from backend.contracts import ReceiverConfig
from backend.datasets.catalog import load_artifact
from backend.experiments.benchmark import Benchmark, BenchmarkConfig, benchmark_csv
from backend.experiments.registry import Registry

ROOT = Path(__file__).resolve().parents[1]
DATASET = "tsrd-stare-d25a4189f287"

def main():
    _, manifest = load_artifact(DATASET)
    registry = Registry(ROOT / "data" / "experiments")
    output = ROOT / "docs" / "validation" / "tsrd"
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for width in (2, 4, 8, 16):
        config = BenchmarkConfig(dataset_id=DATASET, runs=6, seed=42,
            horizon=240, receiver=ReceiverConfig(bands=64, window_width=width),
            algorithms=["magnts", "no_memory", "no_information", "no_change", "thompson", "fixed", "random", "ucb"])
        benchmark = Benchmark(config, registry)
        for seed in range(42, 48):
            benchmark.run_one("recording", seed)
            print(f"width={width}/64 seed={seed} complete", flush=True)
        benchmark.state = "completed"
        benchmark.persist()
        record = benchmark.snapshot()
        records.append(record)
        (output / f"width-{width}.json").write_text(json.dumps(record, indent=2, allow_nan=False))
        (output / f"width-{width}.csv").write_text(benchmark_csv(record))
        for run in record["results"]:
            registry.load(run["experiment_id"])  # Verify saved replay checksums.
    report = {"dataset": manifest, "limitations": ["One official synthetic validation recording, not field radar measurements.", "Seeds vary modeled receiver noise and policy randomness, not independent source recordings.", "Receiver energy is simulated from source pulse occupancy; not measured IQ waveforms.", "Timing averages are conditional on intercepted episodes."], "benchmarks": records}
    (output / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    print("Saved report and verified all 24 replay artifacts", flush=True)

if __name__ == "__main__":
    main()
