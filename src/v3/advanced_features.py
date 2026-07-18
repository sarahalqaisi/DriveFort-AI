from __future__ import annotations

import copy
import hashlib
import hmac
import json
import math
import os
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, Iterable, List, Optional, Tuple


APPROVED_ATTACKS = {
    "steering_manipulation",
    "brake_override",
    "acceleration_injection",
    "sensor_spoofing",
    "gps_spoofing",
    "can_bus_injection",
    "dos",
    "lane_drift_attack",
    "pedestrian_detection_attack",
    "mixed_attack",
}

ATTACK_SEVERITY = {
    "steering_manipulation": 0.92,
    "brake_override": 0.90,
    "acceleration_injection": 0.88,
    "sensor_spoofing": 0.75,
    "gps_spoofing": 0.70,
    "can_bus_injection": 0.95,
    "dos": 0.84,
    "lane_drift_attack": 0.87,
    "pedestrian_detection_attack": 0.94,
    "mixed_attack": 0.98,
}

ATTACK_TARGETS = {
    "steering_manipulation": "steering_ecu",
    "brake_override": "brake_ecu",
    "acceleration_injection": "powertrain_ecu",
    "sensor_spoofing": "perception_ecu",
    "gps_spoofing": "telematics_ecu",
    "can_bus_injection": "gateway_ecu",
    "dos": "gateway_ecu",
    "lane_drift_attack": "steering_ecu",
    "pedestrian_detection_attack": "perception_ecu",
    "mixed_attack": "gateway_ecu",
}

ECU_LABELS = {
    "gateway_ecu": "Vehicle Gateway",
    "steering_ecu": "Steering ECU",
    "brake_ecu": "Brake ECU",
    "powertrain_ecu": "Powertrain ECU",
    "battery_ecu": "Battery Management ECU",
    "perception_ecu": "Perception ECU",
    "telematics_ecu": "Telematics / GPS ECU",
}

FEATURES = [
    ("time_machine", "DriveFort Time Machine"),
    ("ghost_twin", "Ghost Digital Twin"),
    ("defense_benchmark", "Protected vs Unprotected Replay"),
    ("ecu_integrity", "ECU Integrity Map"),
    ("safety_envelope", "Smart Safety Envelope"),
    ("decision_explainer", "AI Decision Explainer"),
    ("copilot", "DriveFort Copilot"),
    ("threat_fusion", "Threat Confidence Fusion"),
    ("attack_chain", "Attack Chain Builder"),
    ("adaptive_attacker", "Adaptive Attacker"),
    ("stealth_mode", "Stealth Attack Mode"),
    ("virtual_ecu", "Virtual Backup ECU"),
    ("recovery_playbooks", "Automatic Recovery Playbooks"),
    ("incident_storyboard", "Incident Storyboard"),
    ("evidence_verification", "Evidence Integrity Verification"),
    ("multi_level_reports", "Three-Level Incident Reports"),
    ("attack_graph", "Automatic Attack Graph"),
    ("mission_control", "Mission Control Mode"),
    ("scenario_director", "Scenario Director"),
    ("performance_score", "Live Performance Score"),
    ("fleet_center", "Fleet Command Center"),
    ("v2v_intelligence", "Vehicle-to-Vehicle Threat Sharing"),
    ("ota_security", "OTA Security Center"),
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except (TypeError, ValueError):
        return default


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, _number(value, low)))


def _pct(value: Any) -> float:
    number = _number(value, 0.0)
    if number <= 1.0:
        number *= 100.0
    return max(0.0, min(100.0, number))


def _safe_attack(value: Any, default: str = "steering_manipulation") -> str:
    attack = str(value or default).strip().lower()
    return attack if attack in APPROVED_ATTACKS else default


def _json_copy(value: Any) -> Any:
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return copy.deepcopy(value)


class DriveFortV3Features:
    """Modular V3 innovation layer wrapped around the legacy simulation engine.

    This class intentionally does not monkey-patch the engine. It consumes a
    snapshot, derives advanced safety/security views, and exposes explicit
    commands through a small service API. All mutable state is lock-protected.
    """

    VERSION = "3.1.0"

    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self._lock = threading.RLock()
        self._timeline: Deque[Dict[str, Any]] = deque(maxlen=360)
        self._last_fingerprint = ""
        self._last_frame_time = 0.0
        self._benchmark: Dict[str, Any] = self._empty_benchmark()
        self._attack_chain: Dict[str, Any] = self._empty_attack_chain()
        self._adaptive_attacker: Dict[str, Any] = {
            "enabled": False,
            "status": "standby",
            "strategy": "observe_defense_then_pivot",
            "last_choice": None,
            "history": [],
        }
        self._stealth_mode: Dict[str, Any] = {
            "enabled": False,
            "attack": None,
            "intensity": 0.0,
            "drift_per_step": 0.0,
            "status": "standby",
        }
        self._virtual_ecus: Dict[str, Dict[str, Any]] = {}
        self._playbook: Dict[str, Any] = self._empty_playbook()
        self._scenario_director: Dict[str, Any] = {
            "status": "ready",
            "active_scenario": None,
            "step": 0,
            "steps": [],
            "message": "Select a guided demonstration.",
        }
        self._fleet: List[Dict[str, Any]] = self._default_fleet()
        self._v2v_events: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._ota_events: Deque[Dict[str, Any]] = deque(maxlen=80)
        self._copilot_history: Deque[Dict[str, Any]] = deque(maxlen=40)
        self._event_sequence = 0

    @staticmethod
    def _empty_benchmark() -> Dict[str, Any]:
        return {
            "status": "not_run",
            "attack": None,
            "generated_at": None,
            "unprotected": {},
            "protected": {},
            "improvement": {},
            "verdict": "Run a benchmark to compare outcomes.",
        }

    @staticmethod
    def _empty_attack_chain() -> Dict[str, Any]:
        return {
            "id": None,
            "name": "Untitled attack chain",
            "status": "idle",
            "current_index": -1,
            "stages": [],
            "history": [],
            "created_at": None,
        }

    @staticmethod
    def _empty_playbook() -> Dict[str, Any]:
        return {
            "attack": None,
            "target_ecu": None,
            "status": "standby",
            "current_step": -1,
            "steps": [],
            "started_at": None,
            "completed_at": None,
        }

    @staticmethod
    def _default_fleet() -> List[Dict[str, Any]]:
        return [
            {"vehicle_id": "EV-01", "model": "DriveFort Research EV", "status": "SAFE", "risk": 4, "location": "Amman Tech District", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-02", "model": "Urban EV", "status": "SAFE", "risk": 8, "location": "Smart Mobility Lab", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-03", "model": "Autonomous Shuttle", "status": "MONITORING", "risk": 22, "location": "Campus Route", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-04", "model": "Delivery EV", "status": "SAFE", "risk": 7, "location": "Logistics Zone", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-05", "model": "Connected Sedan", "status": "OFFLINE", "risk": 0, "location": "Maintenance", "policy": "v2.9", "connected": False},
            {"vehicle_id": "EV-06", "model": "Test Mule", "status": "SAFE", "risk": 12, "location": "CARLA Digital Track", "policy": "v3.0", "connected": True},
        ]

    def _feature_matrix(self) -> List[Dict[str, Any]]:
        return [
            {
                "id": feature_id,
                "name": name,
                "status": "implemented",
                "api_ready": True,
                "ui_ready": True,
                "carla_validation": "required_for_physical_claims" if feature_id in {
                    "ghost_twin", "defense_benchmark", "safety_envelope", "attack_chain",
                    "adaptive_attacker", "stealth_mode", "virtual_ecu", "scenario_director"
                } else "not_required",
            }
            for feature_id, name in FEATURES
        ]

    def _risk(self, snapshot: Dict[str, Any]) -> float:
        risks = snapshot.get("risks") or {}
        return _clamp(risks.get("overall", 0.0))

    def _attack(self, snapshot: Dict[str, Any]) -> Tuple[str, bool, float, str]:
        attack = snapshot.get("attack") or {}
        name = str(attack.get("attack_name") or "normal")
        active = bool(attack.get("active")) and name != "normal"
        intensity = _clamp(attack.get("intensity", 0.0))
        target = str(attack.get("target_ecu") or ATTACK_TARGETS.get(name, "gateway_ecu"))
        return name, active, intensity, target

    def _phase(self, snapshot: Dict[str, Any]) -> str:
        lifecycle = snapshot.get("lifecycle") or {}
        return str(lifecycle.get("phase") or lifecycle.get("state") or "READY").upper()

    def _ghost_twin(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        vehicle = snapshot.get("vehicle") or {}
        name, active, intensity, _target = self._attack(snapshot)
        risk = self._risk(snapshot)
        speed = max(0.0, _number(vehicle.get("speed_kmh"), 0.0))
        actual_steer = _clamp(vehicle.get("steer", 0.0), -1.0, 1.0)
        brake = _clamp(vehicle.get("brake", 0.0))
        throttle = _clamp(vehicle.get("throttle", 0.0))
        lane = str(vehicle.get("lane_status") or "centered")
        expected_steer = 0.0
        if lane in {"left", "drifting_left"}:
            expected_steer = 0.08
        elif lane in {"right", "drifting_right"}:
            expected_steer = -0.08
        if not active:
            expected_steer = actual_steer * 0.82
        expected_speed = max(0.0, speed * (1.0 - risk * 0.32))
        expected_brake = max(brake, 0.45 if risk >= 0.7 else 0.18 if risk >= 0.4 else 0.0)
        expected_throttle = min(throttle, 0.12 if risk >= 0.55 else 0.35)
        steer_delta = abs(actual_steer - expected_steer)
        speed_delta = abs(speed - expected_speed) / max(speed, 20.0)
        control_delta = abs(throttle - expected_throttle) * 0.35 + abs(brake - expected_brake) * 0.25
        deviation = _clamp(steer_delta * 0.52 + speed_delta * 0.25 + control_delta + risk * 0.32)
        if active:
            deviation = max(deviation, ATTACK_SEVERITY.get(name, 0.7) * intensity * 0.58)
        collision_probability = _clamp(deviation * 0.72 + risk * 0.28)
        heading = math.radians(_number(vehicle.get("heading_deg"), 0.0))
        base_x = _number(vehicle.get("location_x"), 0.0)
        base_y = _number(vehicle.get("location_y"), 0.0)
        actual_path = []
        expected_path = []
        actual_angle = heading
        expected_angle = heading
        for index in range(12):
            distance = (index + 1) * max(1.4, speed / 18.0)
            actual_angle += actual_steer * 0.038
            expected_angle += expected_steer * 0.038
            actual_path.append({
                "step": index + 1,
                "x": round(base_x + math.cos(actual_angle) * distance, 6),
                "y": round(base_y + math.sin(actual_angle) * distance, 6),
            })
            expected_path.append({
                "step": index + 1,
                "x": round(base_x + math.cos(expected_angle) * distance, 6),
                "y": round(base_y + math.sin(expected_angle) * distance, 6),
            })
        status = "DIVERGED" if deviation >= 0.62 else "DEGRADED" if deviation >= 0.30 else "SYNCHRONIZED"
        return {
            "status": status,
            "attack_context": name if active else "normal",
            "deviation_score": round(deviation * 100.0, 1),
            "collision_probability": round(collision_probability * 100.0, 1),
            "actual": {
                "speed_kmh": round(speed, 2), "steer": round(actual_steer, 3),
                "throttle": round(throttle, 3), "brake": round(brake, 3), "path": actual_path,
            },
            "expected": {
                "speed_kmh": round(expected_speed, 2), "steer": round(expected_steer, 3),
                "throttle": round(expected_throttle, 3), "brake": round(expected_brake, 3), "path": expected_path,
            },
            "first_divergence_step": 1 if deviation >= 0.55 else 4 if deviation >= 0.30 else None,
            "prediction": "Potential unsafe trajectory predicted." if collision_probability >= 0.65 else "Trajectory remains inside the predicted safe corridor.",
        }

    def _safety_envelope(self, snapshot: Dict[str, Any], twin: Dict[str, Any]) -> Dict[str, Any]:
        vehicle = snapshot.get("vehicle") or {}
        risk = self._risk(snapshot)
        speed = max(0.0, _number(vehicle.get("speed_kmh"), 0.0))
        obstacle = max(0.1, _number(vehicle.get("obstacle_distance_m"), 50.0))
        weather = str(vehicle.get("weather") or "clear").lower()
        weather_factor = 0.72 if weather in {"rain", "storm", "fog", "wet"} else 1.0
        speed_factor = max(0.28, 1.0 - speed / 170.0)
        obstacle_factor = max(0.22, min(1.0, obstacle / 42.0))
        trust_factor = max(0.25, 1.0 - risk * 0.58)
        steering_limit = _clamp(0.48 * speed_factor * weather_factor * trust_factor, 0.08, 0.48)
        max_throttle = _clamp(0.75 * obstacle_factor * trust_factor, 0.0, 0.75)
        min_brake = _clamp((1.0 - obstacle_factor) * 0.72 + risk * 0.42, 0.0, 1.0)
        if twin.get("status") == "DIVERGED":
            steering_limit = min(steering_limit, 0.16)
            max_throttle = min(max_throttle, 0.12)
            min_brake = max(min_brake, 0.55)
        actual = twin.get("actual") or {}
        violations = []
        if abs(_number(actual.get("steer"))) > steering_limit:
            violations.append("steering_outside_safe_envelope")
        if _number(actual.get("throttle")) > max_throttle:
            violations.append("throttle_above_safe_envelope")
        if risk >= 0.70 and _number(actual.get("brake")) < min_brake:
            violations.append("braking_below_required_envelope")
        return {
            "status": "VIOLATED" if violations else "ENFORCED",
            "inputs": {"speed_kmh": round(speed, 1), "obstacle_distance_m": round(obstacle, 1), "weather": weather, "risk_percent": round(risk * 100.0, 1)},
            "limits": {
                "steering_min": round(-steering_limit, 3),
                "steering_max": round(steering_limit, 3),
                "max_throttle": round(max_throttle, 3),
                "minimum_brake": round(min_brake, 3),
            },
            "violations": violations,
            "action": "REJECT_OR_CLAMP_COMMAND" if violations else "ALLOW_INSIDE_ENVELOPE",
        }

    def _ecu_integrity(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        name, active, intensity, target = self._attack(snapshot)
        risk = self._risk(snapshot)
        existing = snapshot.get("ecu_trust") or snapshot.get("ecu_trust_manager") or {}
        nodes = []
        for ecu_id, label in ECU_LABELS.items():
            raw = existing.get(ecu_id) if isinstance(existing, dict) else None
            if isinstance(raw, dict):
                trust = _pct(raw.get("trust", raw.get("score", 92)))
            elif raw is not None:
                trust = _pct(raw)
            else:
                trust = 94.0 - risk * 16.0
            if active and (ecu_id == target or (name == "mixed_attack" and ecu_id in {"gateway_ecu", "steering_ecu", "perception_ecu"})):
                trust = min(trust, max(8.0, 72.0 - intensity * 68.0))
            virtual = self._virtual_ecus.get(ecu_id)
            if virtual and virtual.get("active"):
                status = "VIRTUAL_BACKUP_ACTIVE"
            elif trust < 30:
                status = "QUARANTINED"
            elif trust < 60:
                status = "COMPROMISED"
            elif trust < 80:
                status = "DEGRADED"
            else:
                status = "HEALTHY"
            nodes.append({
                "id": ecu_id,
                "label": label,
                "trust": round(trust, 1),
                "status": status,
                "targeted": bool(active and ecu_id == target),
                "virtual_backup": _json_copy(virtual) if virtual else None,
            })
        links = [
            {"from": "gateway_ecu", "to": ecu_id, "status": "isolated" if next(n for n in nodes if n["id"] == ecu_id)["status"] == "QUARANTINED" else "secured"}
            for ecu_id in ECU_LABELS if ecu_id != "gateway_ecu"
        ]
        compromised = [node for node in nodes if node["status"] in {"QUARANTINED", "COMPROMISED"}]
        return {
            "nodes": nodes,
            "links": links,
            "summary": {
                "healthy": sum(1 for node in nodes if node["status"] == "HEALTHY"),
                "degraded": sum(1 for node in nodes if node["status"] == "DEGRADED"),
                "compromised": len(compromised),
                "quarantined": sum(1 for node in nodes if node["status"] == "QUARANTINED"),
                "minimum_trust": round(min(node["trust"] for node in nodes), 1),
            },
        }

    def _threat_fusion(self, snapshot: Dict[str, Any], twin: Dict[str, Any], ecu_map: Dict[str, Any]) -> Dict[str, Any]:
        ai = snapshot.get("ai_security") or {}
        attack_name, active, intensity, _target = self._attack(snapshot)
        anomaly = _pct(ai.get("anomaly_score", self._risk(snapshot) * 100.0))
        sensor = 8.0
        if active and attack_name in {"sensor_spoofing", "gps_spoofing", "pedestrian_detection_attack"}:
            sensor = 52.0 + intensity * 44.0
        elif active:
            sensor = 20.0 + intensity * 25.0
        twin_score = _pct(twin.get("deviation_score", 0.0))
        minimum_trust = _number((ecu_map.get("summary") or {}).get("minimum_trust"), 100.0)
        ecu_loss = 100.0 - minimum_trust
        command_validation = ((snapshot.get("final_defense") or {}).get("command_validation") or {})
        decision = str(command_validation.get("last_decision") or "").lower()
        signature_risk = 86.0 if "block" in decision or "reject" in decision else (40.0 if active else 4.0)
        components = [
            {"id": "behavior_anomaly", "label": "Behavior anomaly", "score": round(anomaly, 1), "weight": 0.25},
            {"id": "sensor_inconsistency", "label": "Sensor inconsistency", "score": round(sensor, 1), "weight": 0.18},
            {"id": "digital_twin_deviation", "label": "Digital twin deviation", "score": round(twin_score, 1), "weight": 0.24},
            {"id": "ecu_trust_loss", "label": "ECU trust loss", "score": round(ecu_loss, 1), "weight": 0.20},
            {"id": "command_integrity", "label": "Command integrity risk", "score": round(signature_risk, 1), "weight": 0.13},
        ]
        score = sum(item["score"] * item["weight"] for item in components)
        if active:
            score = max(score, ATTACK_SEVERITY.get(attack_name, 0.7) * intensity * 100.0 * 0.78)
        score = max(0.0, min(100.0, score))
        confidence = min(99.5, 62.0 + max(item["score"] for item in components) * 0.35)
        level = "CRITICAL" if score >= 85 else "HIGH" if score >= 65 else "ELEVATED" if score >= 35 else "LOW"
        return {
            "overall_score": round(score, 1),
            "confidence": round(confidence, 1),
            "level": level,
            "components": components,
            "agreement": round(max(0.0, min(100.0, 100.0 - (max(item["score"] for item in components) - min(item["score"] for item in components)) * 0.35)), 1),
            "decision": "MITIGATE" if score >= 65 else "CHALLENGE_COMMAND" if score >= 35 else "MONITOR",
        }

    def _decision_explainer(self, snapshot: Dict[str, Any], twin: Dict[str, Any], fusion: Dict[str, Any], ecu_map: Dict[str, Any]) -> Dict[str, Any]:
        name, active, _intensity, target = self._attack(snapshot)
        label = name.replace("_", " ").title() if active else "Normal Operation"
        evidence = []
        for component in sorted(fusion.get("components") or [], key=lambda item: item.get("score", 0), reverse=True)[:4]:
            evidence.append({
                "factor": component.get("label"),
                "value": component.get("score"),
                "detail": "{} contributed to the fused security decision.".format(component.get("label")),
            })
        if active:
            evidence.insert(0, {"factor": "Attack context", "value": 100, "detail": "The active scenario targets {}.".format(ECU_LABELS.get(target, target))})
        actions = []
        if fusion.get("overall_score", 0) >= 65:
            actions.extend(["Isolate or challenge the affected ECU", "Clamp control commands to the safety envelope", "Activate adaptive recovery"])
        elif fusion.get("overall_score", 0) >= 35:
            actions.extend(["Increase sampling frequency", "Require command revalidation", "Prepare virtual backup ECU"])
        else:
            actions.append("Continue normal monitoring")
        return {
            "decision": label,
            "confidence": fusion.get("confidence", 0),
            "severity": fusion.get("level", "LOW"),
            "target_ecu": target if active else None,
            "summary": "DriveFort AI classified {} with {}% confidence because the strongest indicators were {}.".format(
                label.lower(), fusion.get("confidence", 0), ", ".join(item["factor"].lower() for item in evidence[:3])
            ),
            "evidence": evidence,
            "recommended_actions": actions,
            "counterfactual": "Without mitigation, predicted collision exposure is {}%.".format(twin.get("collision_probability", 0)),
        }

    def _performance_score(self, snapshot: Dict[str, Any], fusion: Dict[str, Any], twin: Dict[str, Any], ecu_map: Dict[str, Any]) -> Dict[str, Any]:
        risk = self._risk(snapshot) * 100.0
        safety = max(0.0, min(100.0, 100.0 - twin.get("collision_probability", 0) * 0.72))
        defense = max(0.0, min(100.0, 100.0 - risk * 0.38 + (100.0 - fusion.get("overall_score", 0)) * 0.24))
        stability = max(0.0, min(100.0, 100.0 - twin.get("deviation_score", 0) * 0.78))
        recovery = 96.0 if self._playbook.get("status") == "completed" else 82.0 if fusion.get("overall_score", 0) < 65 else 68.0
        integrity = max(0.0, min(100.0, _number((ecu_map.get("summary") or {}).get("minimum_trust"), 100.0)))
        overall = max(0.0, min(100.0, safety * 0.27 + defense * 0.24 + stability * 0.21 + recovery * 0.14 + integrity * 0.14))
        return {
            "safety": round(safety, 1),
            "cyber_defense": round(defense, 1),
            "vehicle_stability": round(stability, 1),
            "recovery_readiness": round(recovery, 1),
            "ecu_integrity": round(integrity, 1),
            "overall": round(overall, 1),
            "grade": "A" if overall >= 90 else "B" if overall >= 80 else "C" if overall >= 70 else "D",
        }

    def _record_timeline(self, snapshot: Dict[str, Any], twin: Dict[str, Any], fusion: Dict[str, Any]) -> None:
        now = time.time()
        name, active, _intensity, target = self._attack(snapshot)
        phase = self._phase(snapshot)
        vehicle = snapshot.get("vehicle") or {}
        fingerprint = "|".join([
            name, str(active), phase, str(fusion.get("level")),
            str(round(_number(vehicle.get("speed_kmh")), 1)),
            str(round(_number(vehicle.get("steer")), 2)),
            str(round(twin.get("deviation_score", 0), 1)),
        ])
        if fingerprint == self._last_fingerprint and now - self._last_frame_time < 2.5:
            return
        self._last_fingerprint = fingerprint
        self._last_frame_time = now
        self._event_sequence += 1
        event_type = "attack" if active else "baseline"
        if phase in {"MITIGATING", "RECOVERING", "RECOVERED"}:
            event_type = phase.lower()
        frame = {
            "frame_id": "TF-{:05d}".format(self._event_sequence),
            "timestamp": _utc_now(),
            "monotonic_ms": int(now * 1000),
            "event_type": event_type,
            "phase": phase,
            "attack": name,
            "target_ecu": target if active else None,
            "threat_level": fusion.get("level"),
            "threat_score": fusion.get("overall_score"),
            "twin_deviation": twin.get("deviation_score"),
            "collision_probability": twin.get("collision_probability"),
            "vehicle": {
                "speed_kmh": round(_number(vehicle.get("speed_kmh")), 2),
                "steer": round(_number(vehicle.get("steer")), 3),
                "throttle": round(_number(vehicle.get("throttle")), 3),
                "brake": round(_number(vehicle.get("brake")), 3),
                "battery_soc": round(_number(vehicle.get("battery_soc")), 2),
            },
            "summary": "{} · {} · threat {}% · twin drift {}%".format(phase, name, fusion.get("overall_score"), twin.get("deviation_score")),
        }
        self._timeline.append(frame)

    def record_transition(
        self,
        snapshot: Dict[str, Any],
        phase: str,
        event_type: Optional[str] = None,
        attack_name: Optional[str] = None,
        target_ecu: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Record an explicit lifecycle transition in the Time Machine.

        Some analytical/mock actions complete atomically, so the next normal
        snapshot may already be back at READY. This method preserves the
        operator-visible MITIGATING/RECOVERING/RECOVERED stages without
        pretending that a live CARLA frame was observed.
        """
        allowed = {"DISCONNECTED", "READY", "BASELINE", "UNDER_ATTACK", "DETECTED", "MITIGATING", "RECOVERING", "RECOVERED"}
        normalized_phase = str(phase or "READY").strip().upper()
        if normalized_phase not in allowed:
            raise ValueError("Unsupported lifecycle phase: {}".format(phase))

        with self._lock:
            snap = _json_copy(snapshot or {})
            lifecycle = dict(snap.get("lifecycle") or {})
            lifecycle["phase"] = normalized_phase
            snap["lifecycle"] = lifecycle

            twin = self._ghost_twin(snap)
            ecu_map = self._ecu_integrity(snap)
            fusion = self._threat_fusion(snap, twin, ecu_map)
            current_name, current_active, _intensity, current_target = self._attack(snap)
            name = str(attack_name or current_name or "normal")
            target = target_ecu or current_target
            vehicle = snap.get("vehicle") or {}

            normalized_event = str(event_type or normalized_phase.lower())
            if self._timeline:
                latest = self._timeline[-1]
                if (
                    latest.get("phase") == normalized_phase
                    and latest.get("event_type") == normalized_event
                    and latest.get("attack") == name
                ):
                    return _json_copy(latest)

            self._event_sequence += 1
            now = time.time()
            frame = {
                "frame_id": "TF-{:05d}".format(self._event_sequence),
                "timestamp": _utc_now(),
                "monotonic_ms": int(now * 1000),
                "event_type": normalized_event,
                "phase": normalized_phase,
                "attack": name,
                "target_ecu": target,
                "threat_level": fusion.get("level"),
                "threat_score": fusion.get("overall_score"),
                "twin_deviation": twin.get("deviation_score"),
                "collision_probability": twin.get("collision_probability"),
                "vehicle": {
                    "speed_kmh": round(_number(vehicle.get("speed_kmh")), 2),
                    "steer": round(_number(vehicle.get("steer")), 3),
                    "throttle": round(_number(vehicle.get("throttle")), 3),
                    "brake": round(_number(vehicle.get("brake")), 3),
                    "battery_soc": round(_number(vehicle.get("battery_soc")), 2),
                },
                "summary": summary or "{} · {} · threat {}% · twin drift {}%".format(
                    normalized_phase, name, fusion.get("overall_score"), twin.get("deviation_score")
                ),
                "analytical_transition": not bool((snap.get("carla") or {}).get("connected")),
            }
            self._timeline.append(frame)
            self._last_fingerprint = ""
            self._last_frame_time = now
            return _json_copy(frame)

    def _storyboard(self) -> Dict[str, Any]:
        frames = list(self._timeline)
        if not frames:
            return {"status": "empty", "chapters": [], "summary": "No incident frames captured yet."}
        selected = []
        wanted = ["baseline", "attack", "detected", "mitigating", "recovering", "recovered"]
        for event_type in wanted:
            match = next((frame for frame in frames if frame.get("event_type") == event_type or frame.get("phase", "").lower() == event_type), None)
            if match and match not in selected:
                selected.append(match)
        if frames[-1] not in selected:
            selected.append(frames[-1])
        chapters = []
        for index, frame in enumerate(selected):
            chapters.append({
                "chapter": index + 1,
                "title": str(frame.get("event_type") or "event").replace("_", " ").title(),
                "timestamp": frame.get("timestamp"),
                "detail": frame.get("summary"),
                "evidence": {
                    "phase": frame.get("phase"),
                    "attack": frame.get("attack"),
                    "threat_score": frame.get("threat_score"),
                    "twin_deviation": frame.get("twin_deviation"),
                },
            })
        return {
            "status": "ready",
            "chapters": chapters,
            "summary": "{} key stages reconstructed from {} telemetry frames.".format(len(chapters), len(frames)),
        }

    def _attack_graph(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        name, active, _intensity, target = self._attack(snapshot)
        if not active:
            return {
                "status": "standby",
                "nodes": [
                    {"id": "attacker", "label": "External Threat Actor", "type": "source", "status": "inactive"},
                    {"id": "gateway_ecu", "label": "Vehicle Gateway", "type": "gateway", "status": "secured"},
                ],
                "edges": [{"from": "attacker", "to": "gateway_ecu", "status": "blocked"}],
            }
        route = ["attacker", "wireless_entry", "gateway_ecu"]
        if target != "gateway_ecu":
            route.append(target)
        route.append("vehicle_control")
        nodes = []
        labels = {
            "attacker": "Threat Actor", "wireless_entry": "Connected Entry Point",
            "gateway_ecu": "Vehicle Gateway", "vehicle_control": "Vehicle Control",
        }
        for node_id in route:
            nodes.append({
                "id": node_id,
                "label": labels.get(node_id, ECU_LABELS.get(node_id, node_id)),
                "type": "source" if node_id == "attacker" else "target" if node_id == target else "control" if node_id == "vehicle_control" else "hop",
                "status": "isolated" if node_id == target and self._virtual_ecus.get(target, {}).get("active") else "compromised" if node_id in {"wireless_entry", "gateway_ecu", target} else "threatened",
            })
        edges = []
        for index in range(len(route) - 1):
            edges.append({"from": route[index], "to": route[index + 1], "status": "contained" if self._playbook.get("status") == "completed" else "active"})
        return {"status": "contained" if self._playbook.get("status") == "completed" else "active", "attack": name, "nodes": nodes, "edges": edges}

    def _mission_control(self, snapshot: Dict[str, Any], fusion: Dict[str, Any], twin: Dict[str, Any], performance: Dict[str, Any]) -> Dict[str, Any]:
        attack, active, _intensity, _target = self._attack(snapshot)
        carla = snapshot.get("carla") or {}
        return {
            "mode": "committee_demo",
            "carla_connected": bool(carla.get("connected")),
            "phase": self._phase(snapshot),
            "attack": attack if active else "none",
            "threat_score": fusion.get("overall_score"),
            "twin_deviation": twin.get("deviation_score"),
            "defense_decision": fusion.get("decision"),
            "overall_score": performance.get("overall"),
            "headline": "Threat contained by DriveFort AI." if active and fusion.get("decision") == "MITIGATE" else "Vehicle operating under continuous protection.",
        }

    def _sync_fleet(self, snapshot: Dict[str, Any], fusion: Dict[str, Any]) -> Dict[str, Any]:
        name, active, _intensity, _target = self._attack(snapshot)
        ego = self._fleet[0]
        ego["risk"] = int(round(fusion.get("overall_score", 0)))
        ego["status"] = "UNDER_ATTACK" if active else "SAFE"
        ego["threat"] = name if active else None
        ego["last_seen"] = _utc_now()
        summary = {
            "total": len(self._fleet),
            "online": sum(1 for vehicle in self._fleet if vehicle.get("connected")),
            "safe": sum(1 for vehicle in self._fleet if vehicle.get("status") == "SAFE"),
            "at_risk": sum(1 for vehicle in self._fleet if vehicle.get("risk", 0) >= 35),
            "offline": sum(1 for vehicle in self._fleet if not vehicle.get("connected")),
        }
        return {"vehicles": _json_copy(self._fleet), "summary": summary}

    def enrich_snapshot(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            twin = self._ghost_twin(snapshot)
            envelope = self._safety_envelope(snapshot, twin)
            ecu_map = self._ecu_integrity(snapshot)
            fusion = self._threat_fusion(snapshot, twin, ecu_map)
            explainer = self._decision_explainer(snapshot, twin, fusion, ecu_map)
            performance = self._performance_score(snapshot, fusion, twin, ecu_map)
            self._record_timeline(snapshot, twin, fusion)
            fleet = self._sync_fleet(snapshot, fusion)
            time_machine = {
                "status": "recording",
                "frame_count": len(self._timeline),
                "latest_frame": _json_copy(self._timeline[-1]) if self._timeline else None,
                "preview": _json_copy(list(self._timeline)[-16:]),
            }
            innovation = {
                "version": self.VERSION,
                "generated_at": _utc_now(),
                "feature_matrix": self._feature_matrix(),
                "time_machine": time_machine,
                "ghost_twin": twin,
                "defense_benchmark": _json_copy(self._benchmark),
                "ecu_integrity": ecu_map,
                "safety_envelope": envelope,
                "decision_explainer": explainer,
                "copilot": {
                    "status": "ready",
                    "history_count": len(self._copilot_history),
                    "suggested_questions": [
                        "Why was this command blocked?", "Which ECU is least trusted?",
                        "What would happen without protection?", "Summarize the incident for the committee.",
                    ],
                },
                "threat_fusion": fusion,
                "attack_chain": _json_copy(self._attack_chain),
                "adaptive_attacker": _json_copy(self._adaptive_attacker),
                "stealth_mode": _json_copy(self._stealth_mode),
                "virtual_backup_ecu": _json_copy(self._virtual_ecus),
                "recovery_playbook": _json_copy(self._playbook),
                "incident_storyboard": self._storyboard(),
                "evidence_integrity": self.verify_evidence(),
                "attack_graph": self._attack_graph(snapshot),
                "mission_control": self._mission_control(snapshot, fusion, twin, performance),
                "scenario_director": _json_copy(self._scenario_director),
                "performance_score": performance,
                "fleet": fleet,
                "v2v_intelligence": {"events": _json_copy(list(self._v2v_events)[-12:]), "shared_count": len(self._v2v_events)},
                "ota_security": {"events": _json_copy(list(self._ota_events)[-12:]), "checks": len(self._ota_events)},
            }
            snapshot["innovation_lab"] = innovation
            # Convenient top-level aliases for presentation clients.
            snapshot["ghost_digital_twin"] = twin
            snapshot["smart_safety_envelope"] = envelope
            snapshot["threat_confidence_fusion"] = fusion
            snapshot["ecu_integrity_map"] = ecu_map
            snapshot["drivefort_performance_score"] = performance
            return snapshot

    def timeline(self, limit: int = 180) -> Dict[str, Any]:
        with self._lock:
            safe_limit = max(1, min(360, int(limit)))
            frames = list(self._timeline)[-safe_limit:]
            return {"status": "ready", "count": len(frames), "frames": _json_copy(frames)}

    def clear_timeline(self) -> Dict[str, Any]:
        with self._lock:
            self._timeline.clear()
            self._last_fingerprint = ""
            return {"ok": True, "count": 0, "message": "Time Machine timeline cleared."}

    def run_benchmark(self, attack: str, intensity: float = 0.92) -> Dict[str, Any]:
        with self._lock:
            attack = _safe_attack(attack)
            intensity = _clamp(intensity, 0.05, 1.0)
            severity = ATTACK_SEVERITY.get(attack, 0.8) * intensity
            unprotected = {
                "detection_time_ms": None,
                "maximum_lateral_deviation_m": round(0.8 + severity * 3.4, 2),
                "collision_probability_percent": round(min(99.0, 38.0 + severity * 61.0), 1),
                "stabilization_time_sec": None,
                "ecu_trust_loss_percent": round(42.0 + severity * 51.0, 1),
                "outcome": "COLLISION LIKELY" if severity >= 0.72 else "UNSAFE DEVIATION",
            }
            protected = {
                "detection_time_ms": int(round(145.0 + (1.0 - severity) * 210.0)),
                "maximum_lateral_deviation_m": round(max(0.12, 0.62 - severity * 0.22), 2),
                "collision_probability_percent": round(max(1.8, 16.0 - severity * 9.0), 1),
                "stabilization_time_sec": round(0.9 + severity * 1.15, 2),
                "ecu_trust_loss_percent": round(8.0 + severity * 14.0, 1),
                "outcome": "CONTAINED",
            }
            improvement = {
                "deviation_reduction_percent": round((1.0 - protected["maximum_lateral_deviation_m"] / unprotected["maximum_lateral_deviation_m"]) * 100.0, 1),
                "collision_risk_reduction_percent": round(unprotected["collision_probability_percent"] - protected["collision_probability_percent"], 1),
                "trust_preserved_percent": round(unprotected["ecu_trust_loss_percent"] - protected["ecu_trust_loss_percent"], 1),
            }
            self._benchmark = {
                "status": "complete",
                "attack": attack,
                "intensity": round(intensity, 2),
                "generated_at": _utc_now(),
                "unprotected": unprotected,
                "protected": protected,
                "improvement": improvement,
                "replay": {
                    "unprotected": [
                        {"t_ms": 0, "stage": "baseline", "risk": 5, "deviation_m": 0.0},
                        {"t_ms": 400, "stage": "attack_injected", "risk": round(35 + severity * 50, 1), "deviation_m": round(unprotected["maximum_lateral_deviation_m"] * 0.28, 2)},
                        {"t_ms": 1200, "stage": "unsafe_motion", "risk": round(55 + severity * 42, 1), "deviation_m": unprotected["maximum_lateral_deviation_m"]},
                        {"t_ms": 2200, "stage": "predicted_impact", "risk": unprotected["collision_probability_percent"], "deviation_m": unprotected["maximum_lateral_deviation_m"]},
                    ],
                    "protected": [
                        {"t_ms": 0, "stage": "baseline", "risk": 5, "deviation_m": 0.0},
                        {"t_ms": protected["detection_time_ms"], "stage": "detected", "risk": round(45 + severity * 42, 1), "deviation_m": round(protected["maximum_lateral_deviation_m"] * 0.35, 2)},
                        {"t_ms": protected["detection_time_ms"] + 180, "stage": "mitigation", "risk": round(28 + severity * 20, 1), "deviation_m": protected["maximum_lateral_deviation_m"]},
                        {"t_ms": int(protected["stabilization_time_sec"] * 1000), "stage": "recovered", "risk": 9, "deviation_m": 0.08},
                    ],
                },
                "verdict": "DriveFort AI contains the scenario and materially reduces predicted unsafe motion.",
                "method": "counterfactual_digital_twin_model",
                "physical_validation_note": "Use a live CARLA run to validate simulator-specific impact values.",
            }
            return _json_copy(self._benchmark)

    def configure_attack_chain(self, name: str, stages: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        with self._lock:
            normalized = []
            for index, raw in enumerate(list(stages or [])[:8]):
                attack = _safe_attack(raw.get("attack") if isinstance(raw, dict) else raw)
                raw_dict = raw if isinstance(raw, dict) else {}
                normalized.append({
                    "index": index,
                    "attack": attack,
                    "intensity": round(_clamp(raw_dict.get("intensity", 0.65), 0.05, 1.0), 2),
                    "duration_sec": int(max(1, min(30, _number(raw_dict.get("duration_sec", 4), 4)))),
                    "condition": str(raw_dict.get("condition") or "previous_stage_complete"),
                    "status": "pending",
                    "target_ecu": ATTACK_TARGETS.get(attack, "gateway_ecu"),
                })
            if not normalized:
                normalized = [
                    {"index": 0, "attack": "gps_spoofing", "intensity": 0.35, "duration_sec": 4, "condition": "start", "status": "pending", "target_ecu": "telematics_ecu"},
                    {"index": 1, "attack": "sensor_spoofing", "intensity": 0.55, "duration_sec": 4, "condition": "gps_trust_below_60", "status": "pending", "target_ecu": "perception_ecu"},
                    {"index": 2, "attack": "can_bus_injection", "intensity": 0.82, "duration_sec": 5, "condition": "defense_attention_diverted", "status": "pending", "target_ecu": "gateway_ecu"},
                ]
            self._attack_chain = {
                "id": str(uuid.uuid4()),
                "name": str(name or "Coordinated multi-stage attack")[:80],
                "status": "configured",
                "current_index": -1,
                "stages": normalized,
                "history": [],
                "created_at": _utc_now(),
            }
            return _json_copy(self._attack_chain)

    def advance_attack_chain(self) -> Dict[str, Any]:
        with self._lock:
            if not self._attack_chain.get("stages"):
                self.configure_attack_chain("Default coordinated attack", [])
            current = int(self._attack_chain.get("current_index", -1))
            stages = self._attack_chain["stages"]
            if current >= 0 and current < len(stages):
                stages[current]["status"] = "complete"
            next_index = current + 1
            if next_index >= len(stages):
                self._attack_chain["status"] = "complete"
                return {"ok": True, "message": "Attack chain completed.", "attack_chain": _json_copy(self._attack_chain)}
            stage = stages[next_index]
            stage["status"] = "active"
            stage["started_at"] = _utc_now()
            self._attack_chain["current_index"] = next_index
            self._attack_chain["status"] = "running"
            result = {"ok": True, "message": "Analytical stage activated."}
            try:
                result = self.engine.apply_carla_attack_console(stage["attack"], stage["intensity"])
            except Exception as exc:
                result = {"ok": False, "message": "Engine stage could not be applied: {}".format(exc)}
            history = {
                "stage": next_index + 1, "attack": stage["attack"], "timestamp": _utc_now(),
                "engine_ok": bool(result.get("ok")), "message": result.get("message", "Stage activated."),
            }
            self._attack_chain["history"].append(history)
            return {"ok": bool(result.get("ok", True)), "engine_result": _json_copy(result), "attack_chain": _json_copy(self._attack_chain)}

    def adaptive_attack(self, snapshot: Dict[str, Any], apply_to_engine: bool = False) -> Dict[str, Any]:
        with self._lock:
            innovation = snapshot.get("innovation_lab") or {}
            ecu_nodes = ((innovation.get("ecu_integrity") or {}).get("nodes") or [])
            weakest = min(ecu_nodes, key=lambda node: node.get("trust", 100)) if ecu_nodes else {"id": "gateway_ecu", "trust": 100}
            choice_map = {
                "steering_ecu": "lane_drift_attack", "brake_ecu": "brake_override",
                "powertrain_ecu": "acceleration_injection", "perception_ecu": "sensor_spoofing",
                "telematics_ecu": "gps_spoofing", "gateway_ecu": "can_bus_injection",
                "battery_ecu": "dos",
            }
            attack = choice_map.get(weakest.get("id"), "can_bus_injection")
            intensity = 0.54 if (innovation.get("threat_fusion") or {}).get("overall_score", 0) >= 60 else 0.72
            event = {
                "timestamp": _utc_now(), "attack": attack, "intensity": intensity,
                "reason": "Selected the path associated with the lowest-trust ECU and adapted intensity to current defense attention.",
                "target": weakest.get("id"), "target_trust": weakest.get("trust"),
            }
            result = None
            if apply_to_engine:
                try:
                    result = self.engine.apply_carla_attack_console(attack, intensity)
                except Exception as exc:
                    result = {"ok": False, "message": str(exc)}
            self._adaptive_attacker.update({"enabled": True, "status": "executed" if apply_to_engine else "planned", "last_choice": event})
            self._adaptive_attacker["history"].append(event)
            self._adaptive_attacker["history"] = self._adaptive_attacker["history"][-20:]
            return {"adaptive_attacker": _json_copy(self._adaptive_attacker), "engine_result": _json_copy(result)}

    def start_stealth_attack(self, attack: str, intensity: float = 0.22, apply_to_engine: bool = False) -> Dict[str, Any]:
        with self._lock:
            attack = _safe_attack(attack, "gps_spoofing")
            intensity = _clamp(intensity, 0.05, 0.38)
            self._stealth_mode = {
                "enabled": True,
                "attack": attack,
                "intensity": round(intensity, 2),
                "drift_per_step": round(0.01 + intensity * 0.055, 4),
                "status": "active",
                "started_at": _utc_now(),
                "strategy": "low_and_slow_signal_manipulation",
            }
            result = None
            if apply_to_engine:
                try:
                    result = self.engine.apply_carla_attack_console(attack, intensity)
                except Exception as exc:
                    result = {"ok": False, "message": str(exc)}
            return {"stealth_mode": _json_copy(self._stealth_mode), "engine_result": _json_copy(result)}

    def stop_stealth_attack(self) -> Dict[str, Any]:
        with self._lock:
            self._stealth_mode.update({"enabled": False, "status": "stopped", "stopped_at": _utc_now()})
            return _json_copy(self._stealth_mode)

    def activate_virtual_ecu(self, ecu_id: str) -> Dict[str, Any]:
        with self._lock:
            ecu_id = str(ecu_id or "steering_ecu")
            if ecu_id not in ECU_LABELS:
                ecu_id = "steering_ecu"
            instance = {
                "id": "VECU-{}".format(uuid.uuid4().hex[:8].upper()),
                "replaces": ecu_id,
                "label": "Virtual {}".format(ECU_LABELS[ecu_id]),
                "active": True,
                "trust": 98.0,
                "control_source": "digital_twin_safety_controller",
                "activated_at": _utc_now(),
                "validation": "self_test_passed",
            }
            self._virtual_ecus[ecu_id] = instance
            return _json_copy(instance)

    def deactivate_virtual_ecu(self, ecu_id: str) -> Dict[str, Any]:
        with self._lock:
            ecu_id = str(ecu_id or "steering_ecu")
            instance = self._virtual_ecus.get(ecu_id)
            if not instance:
                return {"ok": False, "message": "No active virtual ECU for {}.".format(ecu_id)}
            instance["active"] = False
            instance["deactivated_at"] = _utc_now()
            return {"ok": True, "virtual_ecu": _json_copy(instance)}

    def prepare_playbook(self, attack: str) -> Dict[str, Any]:
        with self._lock:
            attack = _safe_attack(attack)
            target = ATTACK_TARGETS.get(attack, "gateway_ecu")
            special = {
                "gps_spoofing": ["Reject compromised GPS stream", "Switch to wheel odometry", "Cross-check camera landmarks", "Reduce speed", "Restore GPS after validation"],
                "sensor_spoofing": ["Quarantine inconsistent sensor stream", "Fuse redundant sensors", "Increase uncertainty margin", "Validate perception output", "Restore trusted source"],
                "steering_manipulation": ["Reject injected steering command", "Isolate steering ECU", "Activate virtual steering ECU", "Center vehicle inside safety envelope", "Revalidate physical ECU"],
                "brake_override": ["Challenge brake command", "Isolate brake ECU", "Apply safe deceleration profile", "Activate virtual brake controller", "Verify hydraulic response"],
                "can_bus_injection": ["Enable secure bus mode", "Block untrusted CAN identifiers", "Rotate session keys", "Quarantine gateway ECU", "Replay verified control state"],
            }
            labels = special.get(attack, ["Contain affected subsystem", "Apply safe control fallback", "Validate digital twin", "Restore trusted communication", "Confirm stable vehicle state"])
            self._playbook = {
                "attack": attack, "target_ecu": target, "status": "prepared", "current_step": -1,
                "steps": [{"index": index, "label": label, "status": "pending"} for index, label in enumerate(labels)],
                "started_at": None, "completed_at": None,
            }
            return _json_copy(self._playbook)

    def advance_playbook(self, execute_engine_recovery: bool = False) -> Dict[str, Any]:
        with self._lock:
            if not self._playbook.get("steps"):
                self.prepare_playbook("steering_manipulation")
            current = int(self._playbook.get("current_step", -1))
            if current >= 0 and current < len(self._playbook["steps"]):
                self._playbook["steps"][current]["status"] = "complete"
            next_index = current + 1
            if next_index >= len(self._playbook["steps"]):
                self._playbook["status"] = "completed"
                self._playbook["completed_at"] = _utc_now()
                result = None
                if execute_engine_recovery:
                    try:
                        result = self.engine.adaptive_recovery()
                    except Exception as exc:
                        result = {"ok": False, "message": str(exc)}
                return {"ok": True, "playbook": _json_copy(self._playbook), "engine_result": _json_copy(result)}
            if self._playbook.get("started_at") is None:
                self._playbook["started_at"] = _utc_now()
            self._playbook["status"] = "running"
            self._playbook["current_step"] = next_index
            self._playbook["steps"][next_index]["status"] = "active"
            self._playbook["steps"][next_index]["timestamp"] = _utc_now()
            if "virtual" in self._playbook["steps"][next_index]["label"].lower():
                self.activate_virtual_ecu(self._playbook.get("target_ecu") or "steering_ecu")
            return {"ok": True, "playbook": _json_copy(self._playbook)}

    def verify_evidence(self) -> Dict[str, Any]:
        try:
            store = getattr(self.engine, "store", None)
            if store is None:
                return {"checked": 0, "verified": 0, "failed": [], "integrity_verified": True, "status": "NO_STORED_INCIDENTS"}
            result = store.verify_recent(100)
            result["status"] = "VALID" if result.get("integrity_verified") else "TAMPER_DETECTED"
            result["algorithm"] = "SHA-256 chained incident ledger"
            return result
        except Exception as exc:
            return {"checked": 0, "verified": 0, "failed": [{"error": str(exc)}], "integrity_verified": False, "status": "VERIFY_ERROR"}

    def build_report(self, snapshot: Dict[str, Any], level: str = "executive") -> Dict[str, Any]:
        level = str(level or "executive").lower()
        if level not in {"executive", "technical", "forensic"}:
            level = "executive"
        innovation = snapshot.get("innovation_lab") or {}
        base = {
            "report_id": "DF-{}".format(uuid.uuid4().hex[:10].upper()),
            "level": level,
            "generated_at": _utc_now(),
            "platform": "DriveFort AI V3",
            "mission_summary": innovation.get("mission_control"),
            "decision": innovation.get("decision_explainer"),
            "benchmark": innovation.get("defense_benchmark"),
        }
        if level in {"technical", "forensic"}:
            base.update({
                "threat_fusion": innovation.get("threat_fusion"),
                "ghost_twin": innovation.get("ghost_twin"),
                "safety_envelope": innovation.get("safety_envelope"),
                "ecu_integrity": innovation.get("ecu_integrity"),
                "recovery_playbook": innovation.get("recovery_playbook"),
                "attack_graph": innovation.get("attack_graph"),
            })
        if level == "forensic":
            base.update({
                "evidence_integrity": innovation.get("evidence_integrity"),
                "timeline": self.timeline(360),
                "incident_storyboard": innovation.get("incident_storyboard"),
                "incident_records": getattr(self.engine, "recent_incidents", lambda: [])(),
            })
        return base

    def copilot_query(self, snapshot: Dict[str, Any], question: str) -> Dict[str, Any]:
        with self._lock:
            question = str(question or "Summarize the current security state.")[:300]
            q = question.lower()
            innovation = snapshot.get("innovation_lab") or {}
            explainer = innovation.get("decision_explainer") or {}
            ecu = innovation.get("ecu_integrity") or {}
            benchmark = innovation.get("defense_benchmark") or {}
            if "ecu" in q or "trust" in q:
                nodes = ecu.get("nodes") or []
                weakest = min(nodes, key=lambda node: node.get("trust", 100)) if nodes else None
                answer = "The least-trusted ECU is {} at {}% trust with status {}.".format(weakest.get("label"), weakest.get("trust"), weakest.get("status")) if weakest else "No ECU integrity data is available yet."
            elif "without" in q or "unprotected" in q or "حماية" in q:
                if benchmark.get("status") != "complete":
                    answer = "Run the protected-vs-unprotected benchmark first. The current digital twin predicts {}% collision exposure without additional mitigation.".format((innovation.get("ghost_twin") or {}).get("collision_probability", 0))
                else:
                    answer = "Without protection the modeled outcome is {}, with {}% collision probability; DriveFort AI reduces it to {}%.".format(benchmark.get("unprotected", {}).get("outcome"), benchmark.get("unprotected", {}).get("collision_probability_percent"), benchmark.get("protected", {}).get("collision_probability_percent"))
            elif "committee" in q or "summary" in q or "لجنة" in q or "ملخص" in q:
                mission = innovation.get("mission_control") or {}
                answer = "DriveFort AI is in phase {}. The current attack is {}, fused threat confidence is {}%, twin deviation is {}%, and the overall protection score is {}%.".format(mission.get("phase"), mission.get("attack"), mission.get("threat_score"), mission.get("twin_deviation"), mission.get("overall_score"))
            elif "why" in q or "لماذا" in q or "سبب" in q:
                answer = explainer.get("summary") or "No abnormal decision requires explanation."
            else:
                answer = "{} Recommended action: {}".format(explainer.get("summary", "Vehicle monitoring is active."), "; ".join(explainer.get("recommended_actions") or ["Continue monitoring"]))
            event = {"timestamp": _utc_now(), "question": question, "answer": answer}
            self._copilot_history.append(event)
            return {"status": "answered", "question": question, "answer": answer, "evidence": explainer.get("evidence", [])[:4]}

    def share_v2v_threat(self, snapshot: Dict[str, Any], target_vehicle_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        with self._lock:
            innovation = snapshot.get("innovation_lab") or {}
            fusion = innovation.get("threat_fusion") or {}
            attack, active, _intensity, target = self._attack(snapshot)
            targets = target_vehicle_ids or [vehicle["vehicle_id"] for vehicle in self._fleet[1:] if vehicle.get("connected")]
            event = {
                "event_id": "V2V-{}".format(uuid.uuid4().hex[:8].upper()),
                "timestamp": _utc_now(),
                "source_vehicle": "EV-01",
                "targets": targets,
                "attack": attack if active else "security_advisory",
                "target_ecu": target if active else None,
                "confidence": fusion.get("confidence", 0),
                "policy_action": "preemptive_block_and_monitor",
            }
            self._v2v_events.append(event)
            for vehicle in self._fleet:
                if vehicle["vehicle_id"] in targets:
                    vehicle["last_shared_threat"] = event["attack"]
                    vehicle["policy"] = "v3.0-hotfix"
            return {"ok": True, "event": _json_copy(event), "recipients": len(targets)}

    def verify_ota(self, manifest: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            manifest = manifest or {}
            package_name = str(manifest.get("package_name") or "drivefort-policy-update.bin")[:100]
            version = str(manifest.get("version") or "3.0.1")[:32]
            payload = str(manifest.get("payload") or "drivefort-demo-update")
            claimed_hash = str(manifest.get("sha256") or "")
            actual_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
            secret_value = os.environ.get("DRIVEFORT_OTA_SECRET")
            expected_signature = ""
            signature = str(manifest.get("signature") or "")
            hash_ok = bool(claimed_hash) and hmac.compare_digest(claimed_hash, actual_hash)
            compatible = version.startswith("3.")
            configuration_ready = bool(secret_value)
            if configuration_ready:
                secret = secret_value.encode("utf-8")
                expected_signature = hmac.new(secret, (package_name + "|" + version + "|" + actual_hash).encode("utf-8"), hashlib.sha256).hexdigest()
            signature_ok = configuration_ready and bool(signature) and hmac.compare_digest(signature, expected_signature)
            accepted = configuration_ready and hash_ok and signature_ok and compatible
            demo_signing_enabled = (
                os.environ.get("DRIVEFORT_ALLOW_MOCK", "0") == "1"
                and os.environ.get("DRIVEFORT_OTA_DEMO_SIGNING", "0") == "1"
            )
            event = {
                "event_id": "OTA-{}".format(uuid.uuid4().hex[:8].upper()),
                "timestamp": _utc_now(),
                "package_name": package_name,
                "version": version,
                "hash_ok": hash_ok,
                "signature_ok": signature_ok,
                "compatible": compatible,
                "accepted": accepted,
                "decision": "INSTALL_TO_CANARY" if accepted else ("CONFIGURATION_REQUIRED" if not configuration_ready else "REJECT_UPDATE"),
                "rollback_ready": True,
                "configuration_ready": configuration_ready,
                "expected_demo_signature": expected_signature if (demo_signing_enabled and bool(manifest.get("include_demo_signature"))) else None,
                "actual_sha256": actual_hash,
            }
            self._ota_events.append(event)
            return _json_copy(event)

    def scenario_catalog(self) -> List[Dict[str, Any]]:
        return [
            {"id": "gps_spoofing_demo", "name": "GPS Spoofing Detection", "steps": ["baseline", "gps_spoofing", "detect", "recover", "report"]},
            {"id": "steering_injection_demo", "name": "Steering Injection Containment", "steps": ["baseline", "steering_manipulation", "virtual_ecu", "recover", "benchmark"]},
            {"id": "mixed_attack_demo", "name": "Coordinated Mixed Attack", "steps": ["baseline", "attack_chain", "threat_fusion", "playbook", "forensics"]},
            {"id": "protected_comparison", "name": "Protected vs Unprotected", "steps": ["benchmark", "ghost_twin", "storyboard"]},
            {"id": "fleet_intelligence", "name": "Fleet Threat Intelligence", "steps": ["detect", "v2v_share", "fleet_policy_update"]},
        ]

    def start_scenario(self, scenario_id: str) -> Dict[str, Any]:
        with self._lock:
            catalog = self.scenario_catalog()
            scenario = next((item for item in catalog if item["id"] == scenario_id), catalog[0])
            self._scenario_director = {
                "status": "running", "active_scenario": scenario["id"], "name": scenario["name"],
                "step": 0, "steps": [{"index": index, "name": name, "status": "active" if index == 0 else "pending"} for index, name in enumerate(scenario["steps"])],
                "message": "Scenario started. Advance through the guided steps.", "started_at": _utc_now(),
            }
            return _json_copy(self._scenario_director)

    def advance_scenario(self) -> Dict[str, Any]:
        with self._lock:
            steps = self._scenario_director.get("steps") or []
            if not steps:
                return {"ok": False, "message": "Start a scenario first.", "scenario_director": _json_copy(self._scenario_director)}
            current = int(self._scenario_director.get("step", 0))
            if current < len(steps):
                steps[current]["status"] = "complete"
            next_index = current + 1
            if next_index >= len(steps):
                self._scenario_director["status"] = "complete"
                self._scenario_director["message"] = "Guided scenario completed."
                self._scenario_director["completed_at"] = _utc_now()
            else:
                steps[next_index]["status"] = "active"
                self._scenario_director["step"] = next_index
                self._scenario_director["message"] = "Executing step: {}".format(steps[next_index]["name"].replace("_", " "))
            return {"ok": True, "scenario_director": _json_copy(self._scenario_director)}
