"""Turn any standardized artifact into the same observation-only environment."""

import warnings

import numpy as np

from backend.contracts import ExperimentConfig, ReceiverConfig
from backend.environment import World, make_simulation

from .catalog import load_artifact


def regrid(values: np.ndarray, times: np.ndarray, frequencies: np.ndarray, slots: int, bands: int, occupancy: bool = False):
    dt = float(np.median(np.diff(times)))
    df = float(np.median(np.diff(frequencies)))
    time_end = times[-1] + dt
    f_min, f_max = frequencies[0] - df / 2, frequencies[-1] + df / 2
    ti = np.clip(((times - times[0]) / (time_end - times[0]) * slots).astype(int), 0, slots - 1)
    fi = np.clip(((frequencies - f_min) / (f_max - f_min) * bands).astype(int), 0, bands - 1)
    flat_ids = (ti[:, None] * bands + fi[None, :]).ravel()
    valid = np.isfinite(values.ravel())
    count = np.bincount(flat_ids[valid], minlength=slots * bands)
    sums = np.bincount(flat_ids[valid], weights=values.ravel()[valid], minlength=slots * bands)
    if occupancy:
        result = sums.reshape(slots, bands) > 0
    else:
        result = np.divide(sums, count, out=np.full(slots * bands, np.nan), where=count > 0).reshape(slots, bands)
    return result, (float(time_end - times[0]) / slots), (float(f_min), float(f_max))


def build_world(config: ExperimentConfig) -> tuple[ExperimentConfig, World]:
    if config.dataset_id == "simulation":
        return config, make_simulation(config)
    arrays, manifest = load_artifact(config.dataset_id)
    measured = manifest["category"] == "REAL_MEASURED_RF"
    calibration_slots = max(8, min(24, config.horizon // 10)) if measured else 0
    raw, slot_ms, frequency_bounds = regrid(arrays["intensity"], arrays["time_ms"], arrays["frequency_mhz"], config.horizon + calibration_slots, config.receiver.bands)
    receiver_dict = {**config.receiver.model_dump(), "slot_ms": slot_ms, "frequency_min_mhz": max(0, frequency_bounds[0]), "frequency_max_mhz": frequency_bounds[1]}
    try:
        receiver = ReceiverConfig(**receiver_dict)
    except ValueError as error:
        raise ValueError("Artifact time resolution cannot fit this receiver dwell/retune configuration. Reduce the horizon or timing costs.") from error
    effective = ExperimentConfig(**{**config.model_dump(), "receiver": receiver.model_dump()})
    rng = np.random.default_rng(config.seed)
    truth = None
    if measured:
        # Calibration precedes and is excluded from the evaluated replay interval.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            offset = np.nanmedian(raw[:calibration_slots], axis=0)
            scale = 1.4826 * np.nanmedian(abs(raw[:calibration_slots] - offset), axis=0)
        scale = np.maximum(1.0, scale)
        energy = receiver.noise_floor_db + (raw[calibration_slots:] - offset) / scale
        energy_unit = "calibration-standardized intensity (robust z-score above reference floor)"
    else:
        if "truth" in arrays:
            truth, _, _ = regrid(arrays["truth"].astype(float), arrays["time_ms"], arrays["frequency_mhz"], config.horizon, receiver.bands, occupancy=True)
        # Scan-mode data remains unlabelled; available pulses still drive energy.
        occupancy = truth if truth is not None else np.isfinite(raw)
        energy = receiver.noise_floor_db + receiver.snr_db * occupancy + rng.normal(0, receiver.noise_std_db, raw.shape)
        energy_unit = "simulated receiver dB over PDW-derived occupancy"
    shape = energy.shape
    metadata = {**manifest, "energy_unit": energy_unit, "time_resolution_ms": slot_ms, "calibration_slots": calibration_slots, "calibration_excluded_from_evaluation": measured, "evaluation_time_offset_ms": calibration_slots * slot_ms + float(arrays["time_ms"][0]), "ground_truth": truth is not None, "raw_energy_unit": manifest["energy_unit"], "regridding": "Mean measured intensity; OR aggregation of labelled pulse occupancy. Empty measured bins stay NaN."}
    world = World(energy.astype(np.float32), truth, rng.random(shape), rng.random(shape), np.linspace(frequency_bounds[0], frequency_bounds[1], receiver.bands, endpoint=False) + (frequency_bounds[1] - frequency_bounds[0]) / (2 * receiver.bands), np.arange(config.horizon) * slot_ms, metadata)
    return effective, world
