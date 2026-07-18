from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Dict, List



ALLOWED_ATTACKS = {
    # Graduation-project approved attacks
    "normal", "steering_manipulation", "brake_override", "acceleration_injection",
    "sensor_spoofing", "gps_spoofing", "can_bus_injection", "dos",
    "lane_drift_attack", "pedestrian_detection_attack",
    # Backward-compatible internal aliases used by older UI/tests
    "can_flooding", "brake_injection", "throttle_injection", "camera_lidar_blinding",
    "telemetry_scraping", "battery_thermal_tampering", "mixed_attack",
}
ALLOWED_ECUS = {"steering_ecu", "brake_ecu", "gateway_ecu", "battery_ecu", "telematics_ecu", "powertrain_ecu", "perception_ecu"}
ALLOWED_OBJECTIVES = {"disrupt_control", "cause_collision", "data_exfiltration", "system_overload", "mislead_navigation", "blind_perception"}
ALLOWED_MODES = {"stealth", "normal", "aggressive"}


def clamp_float(value, low: float, high: float, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def safe_choice(value, allowed, default):
    value = str(value or default)
    return value if value in allowed else default
@dataclass
class VehicleState:
    vehicle_brand: str = "Tesla"
    vehicle_model: str = "Model 3 Performance"
    speed_kmh: float = 42.0
    steer: float = 0.12
    brake: float = 0.0
    throttle: float = 0.35
    autopilot_enabled: bool = True
    manual_override: bool = False
    battery_soc: float = 78.0
    battery_temp_c: float = 34.0
    motor_temp_c: float = 42.0
    charging_mode: bool = False
    drive_mode: str = "normal"
    weather: str = "clear"
    traffic_density: str = "medium"
    obstacle_distance_m: float = 34.0
    lane_status: str = "centered"
    heading_deg: float = 82.0
    driver_attention: str = "focused"
    location_label: str = "Amman Tech District"
    location_x: float = 35.9284
    location_y: float = 31.9632
    zone_type: str = "urban"

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class AttackState:
    attack_name: str = "normal"
    intensity: float = 0.0
    active: bool = False
    source_ecu: str = "ATTACK_NODE"
    objective: str = "disrupt_control"
    mode: str = "normal"
    duration_sec: int = 10
    target_ecu: str = "steering_ecu"
    extra_attacks: List[str] = field(default_factory=list)
    adaptive_ai: bool = False
    replay_enabled: bool = False

    def active_vectors(self) -> List[str]:
        vectors: List[str] = []
        if self.active and self.attack_name != "normal":
            vectors.append(self.attack_name)
        for item in self.extra_attacks:
            if self.active and item not in vectors and item != "normal":
                vectors.append(item)
        return vectors

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class RiskBundle:
    safety: float = 0.05
    privacy: float = 0.02
    availability: float = 0.02
    cyber_physical: float = 0.03
    ai: float = 0.04
    overall: float = 0.05
    dominant_risk: str = "normal"
    action: str = "ALLOW"
    ai_label: str = "normal"
    ai_reason: str = "normal runtime behavior"
    ai_confidence: float = 0.12
    ai_uncertainty: float = 0.88
    fingerprint_type: str = "none"
    fingerprint_confidence: float = 0.0
    fingerprint_reasons: List[str] = field(default_factory=list)
    summary: str = "Vehicle operating normally."
    threat_level: str = "NORMAL"
    severity_score: float = 0.5
    defense_mode: str = "Normal"
    defense_strategy: List[str] = field(default_factory=list)
    recovery_status: str = "System stable."
    root_cause: List[str] = field(default_factory=list)
    ai_rule_split: Dict[str, float] = field(default_factory=lambda: {"ai": 0.4, "rules": 0.6})
    system_load: Dict[str, float] = field(default_factory=lambda: {"cpu": 22.0, "message_rate": 15.0, "latency_ms": 8.0})

    def to_dict(self) -> Dict:
        return asdict(self)
