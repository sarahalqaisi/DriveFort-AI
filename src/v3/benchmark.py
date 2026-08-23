from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Dict, Optional


SYNTHETIC_MODEL_VERSION = "synthetic-counterfactual-v1.0"


@dataclass(frozen=True)
class BenchmarkResult:
    """Evidence record shared by synthetic and future CARLA benchmarks."""

    attack_type: str
    intensity: float
    detection_latency_ms: Optional[float]
    maximum_deviation_m: Optional[float]
    stabilization_time_sec: Optional[float]
    trust_loss_percent: Optional[float]
    protected_outcome: str
    unprotected_outcome: str
    source: str
    measured: bool
    model_version: str
    scenario_id: str
    generated_at: str
    scenario_seed: Optional[int] = None
    protected: Dict[str, Any] = field(default_factory=dict)
    unprotected: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.source not in {"synthetic", "carla"}:
            raise ValueError("Benchmark source must be synthetic or carla.")
        if self.measured != (self.source == "carla"):
            raise ValueError("Only CARLA benchmark records may be labeled measured.")

    def evidence(self):
        return {
            "attack_type": self.attack_type,
            "intensity": self.intensity,
            "detection_latency_ms": self.detection_latency_ms,
            "maximum_deviation_m": self.maximum_deviation_m,
            "stabilization_time_sec": self.stabilization_time_sec,
            "trust_loss_percent": self.trust_loss_percent,
            "protected_outcome": self.protected_outcome,
            "unprotected_outcome": self.unprotected_outcome,
        }

    def metadata(self):
        return {
            "source": self.source,
            "measured": self.measured,
            "model_version": self.model_version,
            "scenario_id": self.scenario_id,
            "scenario_seed": self.scenario_seed,
            "generated_at": self.generated_at,
            "metric_semantics": "measured_simulator_output" if self.measured else "synthetic_analytical_estimates",
        }


class BenchmarkEvidenceStore:
    """Bounded in-memory evidence store; persistence can be added for CARLA runs."""

    def __init__(self, lock, max_records=100):
        self._lock = lock
        self._records: Deque[BenchmarkResult] = deque(maxlen=max_records)

    def add(self, result):
        with self._lock:
            self._records.append(result)
            return result

    def latest(self):
        with self._lock:
            return self._records[-1] if self._records else None

    def all(self):
        with self._lock:
            return list(self._records)
