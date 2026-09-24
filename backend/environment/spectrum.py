"""Evaluation-owned worlds and a source-independent receiver interface.

World arrays are read-only; independent receiver cursors share identical energy
and random detector fields. No reference to these objects is given to a policy.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from backend.contracts import Action, ExperimentConfig, Observation, ReceiverConfig
from backend.receiver import Receiver

from .scenarios import emitter_specs


@dataclass(frozen=True)
class World:
    energy: np.ndarray
    truth: np.ndarray | None
    detector_uniform: np.ndarray
    false_alarm_uniform: np.ndarray
    frequencies: np.ndarray
    times_ms: np.ndarray
    metadata: dict[str, Any]
    tracks: tuple[dict, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.energy.ndim != 2:
            raise ValueError("World must have time × frequency geometry")
        for array in (self.truth, self.detector_uniform, self.false_alarm_uniform):
            if array is not None and array.shape != self.energy.shape:
                raise ValueError("World arrays must share time × frequency geometry")
        if len(self.frequencies) != self.energy.shape[1] or len(self.times_ms) != self.energy.shape[0]:
            raise ValueError("Coordinate dimensions do not match the spectrum")
        for array in (self.energy, self.truth, self.detector_uniform, self.false_alarm_uniform, self.frequencies, self.times_ms):
            if array is not None:
                array.flags.writeable = False

    @property
    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for array in (self.energy, self.truth, self.detector_uniform, self.false_alarm_uniform, self.frequencies, self.times_ms):
            if array is not None:
                digest.update(array.tobytes())
        return digest.hexdigest()


def make_simulation(config: ExperimentConfig) -> World:
    rng = np.random.default_rng(config.seed)
    c, h = config.receiver, config.horizon
    n = c.bands
    truth = np.zeros((h, n), dtype=bool)
    signal = np.zeros((h, n), dtype=np.float32)
    tracks = []
    for i, spec in enumerate(emitter_specs(config, rng)):
        cells, bursts = [], False
        stop = min(h, spec.stop if spec.stop is not None else h)
        for t in range(spec.start, stop):
            age = t - spec.start
            band = spec.band
            active = True
            if spec.kind == "periodic":
                active = age % spec.period < spec.duration
            elif spec.kind == "burst":
                if age % 5 == 0:
                    bursts = rng.random() < spec.duty
                active = bursts
            elif spec.kind == "hopping":
                active = age % spec.period < spec.duration
                band = (spec.band + (age // spec.period) * 7) % (n - spec.width + 1)
            elif spec.kind == "agile":
                active = rng.random() < spec.duty
                band = (spec.band + age // 7) % (n - spec.width + 1)
            elif spec.kind == "random":
                active = rng.random() < spec.duty
                band = int(rng.integers(0, n - spec.width + 1))
            elif spec.kind == "changing":
                period = spec.period if t < h // 2 else max(6, spec.period // 2 + 4)
                active = age % period < spec.duration
                band = spec.band if t < h // 2 else min(n - spec.width, spec.band + n // 3)
            if active:
                truth[t, band : band + spec.width] = True
                # Relative signal strength, not a calibrated propagation model.
                signal[t, band : band + spec.width] = np.maximum(signal[t, band : band + spec.width], c.snr_db + spec.snr_offset + rng.normal(0, 0.8))
                cells.append([t, band, spec.width])
        tracks.append({"id": f"E{i + 1:02}", "kind": spec.kind, "start": spec.start, "stop": stop, "cells": cells})
    noise_scale = c.noise_std_db * (2.2 if config.scenario == "noise" else 1)
    energy = (c.noise_floor_db + rng.normal(0, noise_scale, (h, n)) + signal).astype(np.float32)
    return World(
        energy, truth, rng.random((h, n)), rng.random((h, n)),
        np.linspace(c.frequency_min_mhz, c.frequency_max_mhz, n, endpoint=False) + (c.frequency_max_mhz - c.frequency_min_mhz) / (2 * n),
        np.arange(h, dtype=np.float64) * float(c.slot_ms),
        {"id": "simulation", "name": "Controlled RF environment", "category": "CONTROLLED_SIMULATION", "ground_truth": True, "energy_unit": "simulated dB", "scenario": config.scenario, "seed": config.seed, "time_resolution_ms": c.slot_ms, "note": "Seeded abstract band-occupancy model; not an electromagnetic propagation or field-validation model."},
        tuple(tracks),
    )


class SpectrumEnvironment:
    def __init__(self, world: World, receiver: ReceiverConfig):
        if world.energy.shape[1] != receiver.bands:
            raise ValueError("Receiver geometry must match the standardized artifact")
        self._world = world
        self._receiver_config = receiver
        self.reset()

    def reset(self):
        self._step = 0
        self._receiver = Receiver(self._receiver_config)
        self._last_observation: Observation | None = None

    def observe(self, window: Action) -> Observation:
        if self._step >= len(self._world.energy):
            raise StopIteration("Experiment horizon reached")
        if window.width != self._receiver_config.window_width or not 0 <= window.start <= self._receiver_config.bands - window.width:
            raise ValueError("Selected window violates instantaneous receiver bandwidth")
        sl = slice(window.start, window.start + window.width)
        return self._receiver.observe(self._step, window, self._world.energy[self._step, sl], self._world.detector_uniform[self._step, sl], self._world.false_alarm_uniform[self._step, sl])

    def step(self, action: Action) -> Observation:
        self._last_observation = self.observe(action)
        self._step += 1
        return self._last_observation

    def get_observation(self) -> Observation | None:
        return self._last_observation

    def get_truth_for_evaluation(self) -> np.ndarray | None:
        """Evaluation-only capability. The runner never passes this object to policy code."""
        return self._world.truth

    def get_metadata(self) -> dict:
        return dict(self._world.metadata)
