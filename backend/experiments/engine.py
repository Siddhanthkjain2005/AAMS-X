"""Fair experiment ownership: one immutable world, independent receiver/policy pairs."""

import hashlib
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np

from backend import __version__
from backend.contracts import DecisionContext, ExperimentConfig, PublicReceiver
from backend.environment import SpectrumEnvironment, World, make_simulation
from backend.metrics import MetricAccumulator
from backend.scheduler import Policy


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def view_frame(frame: dict, judge: bool = False) -> dict:
    """Truth is opt-in for the UI and is never part of a policy's input contract."""
    if judge:
        return frame
    return {key: ({name: {k: v for k, v in policy.items() if k != "evaluation"} for name, policy in value.items()} if key == "policies" else value) for key, value in frame.items() if key != "evaluation"}


class Experiment:
    def __init__(self, config: ExperimentConfig, world: World | None = None):
        self.config = config
        self.world = world if world is not None else make_simulation(config)
        if self.world.energy.shape != (config.horizon, config.receiver.bands):
            raise ValueError("Artifact geometry and experiment configuration differ")
        self.id = f"AX-{uuid.uuid4().hex[:12].upper()}"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.environment_hash = self.world.fingerprint
        self.receiver_hash = hashlib.sha256(canonical_json(config.receiver.model_dump()).encode()).hexdigest()
        self.environments = {name: SpectrumEnvironment(self.world, config.receiver) for name in config.algorithms}
        # Notice what is NOT passed here: no scenario, world, source labels, or future timeline.
        public = PublicReceiver.from_config(config.receiver)
        self.policies = {name: Policy(name, public, config.seed ^ 0xA4D5) for name in config.algorithms}
        self.evaluators = {name: MetricAccumulator(self.world, config.receiver.slot_ms) for name in config.algorithms}
        self.previous = {name: None for name in config.algorithms}
        self.frames: list[dict] = []
        self.state = "paused"
        self.error: str | None = None

    def step(self) -> dict:
        t = len(self.frames)
        if t >= self.config.horizon:
            raise StopIteration("Experiment complete")
        frame = {"step": t, "timestamp_ms": t * self.config.receiver.slot_ms, "policies": {}}
        for name, policy in self.policies.items():
            previous = self.previous[name]
            decision = policy.select_action(DecisionContext(t, previous))
            observation = self.environments[name].step(decision.action)
            policy.update(observation)
            measured = self.evaluators[name].update(observation, decision, previous is not None and previous != decision.action.start)
            observation_data = asdict(observation)
            observation_data["values"] = list(observation_data["values"])
            frame["policies"][name] = {
                "algorithm": name, "selected_window": {"start": decision.action.start, "width": decision.action.width, "end": decision.action.start + decision.action.width - 1},
                "previous_window": previous, "retune_cost": observation.retune_cost,
                "observations": observation_data, "hit_count": sum(v.detected for v in observation.values),
                "decision": asdict(decision), "belief": policy.snapshot(t), **measured,
            }
            self.previous[name] = decision.action.start
        frame["evaluation"] = {
            "label": "EVALUATION / JUDGE VIEW — unavailable to policy",
            "active_bands": np.flatnonzero(self.world.truth[t]).tolist() if self.world.truth is not None else None,
            "energy": [round(float(v), 4) if np.isfinite(v) else None for v in self.world.energy[t]],
        }
        self.frames.append(frame)
        if len(self.frames) == self.config.horizon:
            self.state = "completed"
        return frame

    def run(self):
        self.state = "running"
        while len(self.frames) < self.config.horizon:
            self.step()
        return self

    def summary(self) -> dict:
        return {
            "id": self.id, "created_at": self.created_at, "state": self.state, "error": self.error,
            "step": len(self.frames), "config": self.config.model_dump(), "dataset": self.world.metadata,
            "environment_hash": self.environment_hash, "receiver_hash": self.receiver_hash,
            "frequencies_mhz": self.world.frequencies.round(6).tolist(),
            "metrics": {name: evaluator.snapshot() for name, evaluator in self.evaluators.items()},
            "engine_version": __version__, "policy_input": "observations_only",
            "fairness": {"same_world": True, "same_noise": True, "same_receiver": True, "same_horizon": True, "independent_policy_state": True},
        }

    def record(self) -> dict:
        return {**self.summary(), "trace_hash": hashlib.sha256(canonical_json(self.frames).encode()).hexdigest(), "frames": self.frames, "evaluation_tracks": list(self.world.tracks), "recording_label": "Recorded reproducible experiment replay"}
