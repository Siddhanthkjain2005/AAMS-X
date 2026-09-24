"""Energy-only digital twin. Detection never branches on emitter truth."""

import math

import numpy as np

from backend.contracts import Action, BandObservation, Observation, PublicReceiver, ReceiverConfig


class Receiver:
    def __init__(self, config: ReceiverConfig):
        self.config = config
        self.public = PublicReceiver.from_config(config)
        self.previous: int | None = None

    def observe(
        self,
        step: int,
        action: Action,
        energy_slice: np.ndarray,
        detector_uniform_slice: np.ndarray,
        false_alarm_uniform_slice: np.ndarray,
    ) -> Observation:
        c = self.config
        if action.width != c.window_width or not 0 <= action.start <= c.bands - action.width:
            raise ValueError("Selected window violates instantaneous receiver bandwidth")
        if any(len(a) != action.width for a in (energy_slice, detector_uniform_slice, false_alarm_uniform_slice)):
            raise ValueError("Receiver must receive only the selected bandwidth slice")
        changed = self.previous is not None and self.previous != action.start
        dwell = c.slot_ms - c.scan_latency_ms - (c.retune_ms if changed else 0)
        exposure = dwell / c.slot_ms
        cost = self.public.retune_cost(self.previous, action.start)
        values = []
        for i, band in enumerate(action.bands):
            energy = float(energy_slice[i])
            valid = math.isfinite(energy)
            energy_probability = 1 / (1 + math.exp(-float(np.clip((energy - c.noise_floor_db - c.threshold_db) / 1.25, -40, 40)))) if valid else 0.0
            pd = energy_probability * exposure * (1 - c.miss_probability)
            detected = bool(valid and (detector_uniform_slice[i] < pd or false_alarm_uniform_slice[i] < c.false_alarm_probability * exposure))
            confidence = energy_probability if detected else 1 - energy_probability
            values.append(BandObservation(band, round(energy, 4) if valid else None, detected, round(confidence, 5), c.noise_floor_db, valid))
        self.previous = action.start
        return Observation(step, step * c.slot_ms, action, tuple(values), dwell, cost)
