"""Conservative recurrence estimates from irregular, observed-only event times.

At least four separated observed episodes and three candidate cycles are needed.
Integer-multiple interval fitting tolerates missed episodes; observed misses near
the predicted phase lower confidence. Aliasing remains possible and is exposed.
"""

import math
from collections import deque

import numpy as np


class PeriodicityEstimator:
    def __init__(self, bands: int):
        self.events = [deque(maxlen=32) for _ in range(bands)]
        self.observations = [deque(maxlen=160) for _ in range(bands)]
        self.last_hit = np.full(bands, -1000)
        self.estimates: dict[int, dict] = {}

    def update(self, band: int, step: int, hit: bool):
        self.observations[band].append((step, hit))
        if not hit:
            return
        # Adjacent detections in one burst are not separate recurrence evidence.
        separated = step - self.last_hit[band] > 3
        self.last_hit[band] = step
        if separated:
            self.events[band].append(step)
            self._fit(band)

    def _fit(self, band: int):
        events = np.array(self.events[band], dtype=float)
        if len(events) < 4 or events[-1] - events[0] < 18:
            return
        intervals = np.diff(events)
        candidates = {int(round(gap / k)) for gap in intervals for k in range(1, 5)}
        candidates = [p for p in candidates if 6 <= p <= 100 and events[-1] - events[0] >= 3 * p]
        best = None
        for period in sorted(candidates):
            phase_vector = np.mean(np.exp(2j * np.pi * events / period))
            phase = float(np.angle(phase_vector) * period / (2 * np.pi) % period)
            distances = abs((events - phase + period / 2) % period - period / 2)
            alignment = float(np.mean(np.exp(-0.5 * (distances / 2.0) ** 2)))
            interval_error = abs(intervals / period - np.round(intervals / period))
            consistency = float(np.mean(interval_error <= 2.5 / period))
            near_phase = [hit for time, hit in self.observations[band] if abs((time - phase + period / 2) % period - period / 2) < 1.5]
            support = (sum(near_phase) + 1) / (len(near_phase) + 2)
            evidence = min(1.0, (len(events) - 2) / 5)
            confidence = alignment * consistency * (0.55 + 0.45 * support) * evidence
            # Prefer the fundamental over a divisor when agreement is similar.
            score = confidence + 0.015 * math.log(period)
            if best is None or score > best[0]:
                best = (score, {"band": band, "period_slots": period, "phase": round(phase, 3), "confidence": round(confidence, 4), "observed_events": events.astype(int).tolist(), "fit_step": int(events[-1]), "evidence_count": len(events), "interval_mae_slots": round(float(np.mean(interval_error * period)), 3)})
        if best and best[1]["confidence"] >= 0.28:
            self.estimates[band] = best[1]
        else:
            self.estimates.pop(band, None)

    def predictions(self, step: int) -> list[dict]:
        results = []
        for estimate in self.estimates.values():
            period, phase = estimate["period_slots"], estimate["phase"]
            age = step - estimate["fit_step"]
            confidence = estimate["confidence"] * math.exp(-max(0, age - 3 * period) / (3 * period))
            results.append({**estimate, "confidence": round(confidence, 4), "next_slot": round(phase + math.ceil((step + 1 - phase) / period) * period, 2), "status": "supported" if confidence >= 0.6 else "tentative"})
        return sorted(results, key=lambda e: e["confidence"], reverse=True)

    def opportunity(self, step: int, bands: int) -> np.ndarray:
        result = np.zeros(bands)
        for e in self.predictions(step):
            distance = abs((step - e["phase"] + e["period_slots"] / 2) % e["period_slots"] - e["period_slots"] / 2)
            result[e["band"]] = e["confidence"] * math.exp(-0.5 * (distance / 2.0) ** 2)
        return result
