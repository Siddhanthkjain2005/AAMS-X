"""Neutral, seeded activity presets. These descriptions are never passed to policies."""

import numpy as np

from backend.contracts import EmitterSpec, ExperimentConfig

SCENARIOS = [
    {"id": "sparse", "name": "Sparse Spectrum", "description": "A few persistent and intermittent regions in a mostly quiet spectrum.", "tag": "Cold start"},
    {"id": "dense", "name": "Dense Spectrum", "description": "Many overlapping sources compete for limited receiver time.", "tag": "Capacity"},
    {"id": "sudden", "name": "Sudden Appearance", "description": "A new burst source activates one third into the run; another later disappears.", "tag": "Live demo"},
    {"id": "periodic", "name": "Periodic Intercept", "description": "Repeated activity windows allow recurrence learning from partial observations.", "tag": "Temporal learning"},
    {"id": "agile", "name": "Frequency-Agile", "description": "Sources move through the spectrum with structured frequency transitions.", "tag": "Agility"},
    {"id": "noise", "name": "High Noise", "description": "Low SNR and elevated background variance challenge energy detection.", "tag": "Robustness"},
    {"id": "changing", "name": "Changing Environment", "description": "Activity relocates and a recurring source changes its period mid-run.", "tag": "Non-stationarity"},
    {"id": "multi", "name": "Multi-Emitter", "description": "Continuous, bursting, periodic, and hopping sources coexist.", "tag": "Mixed behavior"},
    {"id": "unknown", "name": "Unknown Pattern", "description": "Seeded random source types, duty cycles, and activation times.", "tag": "Generalization"},
    {"id": "adversarial", "name": "Randomized Spectrum", "description": "Unpredictable frequencies and short events expose fundamental sensing limits.", "tag": "Stress test"},
]


def emitter_specs(config: ExperimentConfig, rng: np.random.Generator) -> list[EmitterSpec]:
    if config.emitters is not None:
        return config.emitters
    n, h = config.receiver.bands, config.horizon

    def e(kind, location, **kwargs):
        return EmitterSpec(kind=kind, band=min(n - 2, int(location * n)), **kwargs)

    base = [e("burst", 0.17, width=2, duty=0.7), e("periodic", 0.53, period=23, duration=6)]
    match config.scenario:
        case "sparse":
            return [e("continuous", 0.21, width=2), e("burst", 0.73, duty=0.35)]
        case "dense":
            return [e("burst", x, duty=0.65, width=2) for x in np.linspace(0.05, 0.9, 12)]
        case "sudden":
            return [
                e("burst", 0.16, width=2, duty=0.72, stop=2 * h // 3),
                e("periodic", 0.43, period=23, duration=5),
                e("burst", 0.79, width=2, start=h // 3, duty=0.85),
                e("hopping", 0.6, start=h // 2, duration=5, period=17, duty=0.45),
            ]
        case "periodic":
            return [e("periodic", 0.38, period=18, duration=4, width=2), e("burst", 0.82, duty=0.12)]
        case "agile":
            return [e("agile", 0.1, width=2, duty=0.8), e("hopping", 0.66, period=13, duration=8), *base[:1]]
        case "noise":
            return [e("burst", 0.22, width=2, duty=0.7, snr_offset=-5), e("periodic", 0.68, snr_offset=-4)]
        case "changing":
            return [e("changing", 0.3, width=2, period=18, duration=5), e("burst", 0.13, stop=h // 2), e("burst", 0.82, start=h // 2, duty=0.8, width=2)]
        case "multi":
            return [*base, e("continuous", 0.36), e("hopping", 0.7), e("agile", 0.86, start=h // 4)]
        case "unknown":
            return [e(str(rng.choice(["burst", "periodic", "hopping", "agile"])), float(rng.uniform(0.02, 0.9)), start=int(rng.integers(0, h // 3)), duty=float(rng.uniform(0.15, 0.85)), period=int(rng.integers(11, 39))) for _ in range(6)]
        case "adversarial":
            return [e("random", x, duty=0.65) for x in (0.2, 0.4, 0.6, 0.8)]
        case _:
            raise ValueError(f"Unknown scenario: {config.scenario}")
