from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import random
import secrets
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

from .attack_catalog import canonical_attack, ADOPTED_ATTACK_ORDER

SECRET = os.environ.get("DRIVEFORT_COMMAND_SECRET") or os.environ.get("ZONEGUARD_COMMAND_SECRET") or secrets.token_hex(32)
SENSORS = ["gps", "imu", "camera", "lidar", "speed", "steering", "brake", "throttle", "battery", "network"]


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def sign_command(command: Dict[str, Any], secret: str = SECRET) -> str:
    body = json.dumps(command, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_command(command: Dict[str, Any], signature: Optional[str], secret: str = SECRET) -> bool:
    if not signature:
        return False
    expected = sign_command(command, secret)
    return hmac.compare_digest(expected, str(signature))


def sensor_trust_scores(vehicle, attack, risk) -> Dict[str, Dict[str, Any]]:
    scores = {name: 94.0 for name in SENSORS}
    reasons: Dict[str, List[str]] = {name: ["Baseline telemetry is stable."] for name in SENSORS}
    if getattr(vehicle, "weather", "clear") in {"fog", "rain"}:
        scores["camera"] -= 8
        scores["lidar"] -= 4
        reasons["camera"].append("Weather reduces visual confidence.")
    if getattr(vehicle, "driver_attention", "focused") != "focused":
        scores["steering"] -= 3
        reasons["steering"].append("Driver attention is degraded.")
    vectors = attack.active_vectors() if getattr(attack, "active_vectors", None) else []
    effects = {
        "gps_spoofing": {"gps": 45, "network": 12},
        "sensor_spoofing": {"camera": 28, "lidar": 24, "imu": 10},
        "camera_lidar_blinding": {"camera": 46, "lidar": 42},
        "throttle_injection": {"throttle": 44, "speed": 18, "network": 8},
        "steering_manipulation": {"steering": 48, "imu": 12},
        "brake_injection": {"brake": 46, "speed": 16},
        "brake_override": {"brake": 50, "speed": 20},
        "acceleration_injection": {"throttle": 48, "speed": 22, "network": 8},
        "can_bus_injection": {"network": 50, "steering": 22, "brake": 18, "throttle": 18},
        "lane_drift_attack": {"steering": 36, "imu": 18, "camera": 12},
        "pedestrian_detection_attack": {"camera": 44, "lidar": 32, "brake": 18},
        "battery_thermal_tampering": {"battery": 50, "network": 8},
        "can_flooding": {"network": 52},
        "dos": {"network": 58},
        "telemetry_scraping": {"network": 32, "gps": 10},
        "mixed_attack": {"network": 42, "steering": 22, "brake": 18, "gps": 16, "camera": 10},
    }
    for attack_name in vectors:
        attack_name = canonical_attack(attack_name)
        for sensor, penalty in effects.get(attack_name, {}).items():
            scores[sensor] -= penalty * max(0.35, getattr(attack, "intensity", 0.0))
            reasons[sensor].append(f"Affected by {attack_name.replace('_', ' ')} indicators.")
    output = {}
    for sensor, value in scores.items():
        value = round(max(5.0, min(99.0, value)), 1)
        status = "trusted" if value >= 75 else "degraded" if value >= 45 else "untrusted"
        output[sensor] = {"score": value, "status": status, "reasons": reasons[sensor][-3:]}
    return output


def sensor_fusion(vehicle, trust_scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    gps_w = trust_scores["gps"]["score"] / 100
    imu_w = trust_scores["imu"]["score"] / 100
    speed_w = trust_scores["speed"]["score"] / 100
    camera_w = trust_scores["camera"]["score"] / 100
    lidar_w = trust_scores["lidar"]["score"] / 100
    weights = {"gps": gps_w, "imu": imu_w, "speed": speed_w, "camera": camera_w, "lidar": lidar_w}
    weighted_speed = (vehicle.speed_kmh * speed_w + vehicle.speed_kmh * 0.96 * imu_w + vehicle.speed_kmh * 1.02 * gps_w) / max(0.01, speed_w + imu_w + gps_w)
    lane_confidence = clamp((camera_w + lidar_w + imu_w) / 3)
    navigation_confidence = clamp((gps_w + imu_w + speed_w) / 3)
    primary_sources = [k for k, v in sorted(weights.items(), key=lambda item: item[1], reverse=True)[:3]]
    ignored_sources = [k for k, v in weights.items() if v < 0.45]
    return {
        "fused_speed_kmh": round(weighted_speed, 1),
        "lane_confidence": round(lane_confidence, 2),
        "navigation_confidence": round(navigation_confidence, 2),
        "primary_sources": primary_sources,
        "ignored_sources": ignored_sources,
        "explanation": "Fusion favors high-trust sensors and suppresses untrusted channels before control decisions.",
    }


def safe_mode_levels(risk, vehicle, trust_scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    untrusted = [name for name, item in trust_scores.items() if item["status"] == "untrusted"]
    overall = getattr(risk, "overall", 0.0)
    if overall >= 0.88 or len(untrusted) >= 3:
        level = 4
        action = "Controlled full stop"
        speed_limit = 0
    elif overall >= 0.72:
        level = 3
        action = "Emergency crawl and isolate attacker"
        speed_limit = 12
    elif overall >= 0.48:
        level = 2
        action = "Reduce speed and restrict commands"
        speed_limit = 35
    elif overall >= 0.28:
        level = 1
        action = "Warn operator and increase monitoring"
        speed_limit = min(80, vehicle.speed_kmh)
    else:
        level = 0
        action = "Normal operation"
        speed_limit = 180
    return {
        "level": level,
        "label": ["Normal", "Alert", "Restricted", "Emergency", "Full Stop"][level],
        "action": action,
        "speed_limit_kmh": speed_limit,
        "untrusted_sensors": untrusted,
        "blocked_commands": ["unsigned", "unsafe throttle", "high steering delta"] if level >= 2 else ["unsigned"] if level == 1 else [],
    }


def network_attack_layer(attack, features: Dict[str, Any]) -> Dict[str, Any]:
    vectors = attack.active_vectors() if getattr(attack, "active_vectors", None) else []
    delay = 8 + int(features.get("drop_rate", 0.02) * 180)
    canon_vectors = [canonical_attack(v) for v in vectors]
    if "dos" in canon_vectors or "can_bus_injection" in canon_vectors:
        delay += 55
    packet_drop = clamp(features.get("drop_rate", 0.02), 0, 0.95)
    tampering = "command_tampering" if any(v in canon_vectors for v in ["steering_manipulation", "acceleration_injection", "brake_override", "can_bus_injection", "lane_drift_attack"]) else "none"
    return {
        "latency_ms": delay,
        "packet_drop_rate": round(packet_drop, 2),
        "tampering": tampering,
        "bus_load_percent": round(min(99, 20 + features.get("message_rate", 15) * 0.55), 1),
        "mitigation": "Rate limit anomalous ECU messages, verify command signatures, and isolate noisy nodes.",
    }


def performance_metrics(risk, features: Dict[str, Any], start_time: Optional[float] = None) -> Dict[str, Any]:
    detection_ms = int(35 + risk.overall * 120 + features.get("message_rate", 15) * 0.18)
    response_ms = int(detection_ms + 45 + risk.overall * 90)
    return {
        "detection_time_ms": detection_ms,
        "response_time_ms": response_ms,
        "false_positive_estimate": round(max(0.01, 0.12 - risk.ai_confidence * 0.08), 3),
        "detection_confidence": round(risk.ai_confidence, 2),
        "events_per_second": round(features.get("message_rate", 15) / 2, 1),
    }


def threat_prediction(risk, previous_risk: float, trust_scores: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    risk_delta = risk.overall - previous_risk
    weakest = min(trust_scores.items(), key=lambda item: item[1]["score"])
    score = clamp(0.22 + risk_delta * 1.6 + (0.25 if weakest[1]["score"] < 55 else 0.0) + risk.overall * 0.25)
    return {
        "probability_next_10s": round(score, 2),
        "weakest_sensor": weakest[0],
        "trend": "rising" if risk_delta > 0.04 else "stable" if abs(risk_delta) <= 0.04 else "falling",
        "recommendation": "Pre-arm safe mode and increase sampling rate." if score >= 0.55 else "Continue monitoring.",
    }


def plugin_catalog() -> Dict[str, Any]:
    return {
        "interface": "Every plugin exposes detect(data) and respond(context).",
        "loaded_plugins": [
            {"name": "GPSDriftPlugin", "detects": "gps_spoofing", "status": "loaded"},
            {"name": "CANInjectionPlugin", "detects": "can_bus_injection/dos", "status": "loaded"},
            {"name": "ControlInjectionPlugin", "detects": "steering/brake/acceleration/lane drift", "status": "loaded"},
            {"name": "PedestrianSafetyPlugin", "detects": "pedestrian_detection_attack", "status": "loaded"},
        ],
        "example": "class NewAttackPlugin: detect(self, data) -> bool; respond(self, context) -> dict",
    }


def voice_alerts(risk, safe_mode: Dict[str, Any]) -> Dict[str, Any]:
    if safe_mode["level"] >= 3:
        text = "Warning. Critical vehicle attack detected. Emergency safe mode is active."
    elif safe_mode["level"] == 2:
        text = "Security warning. Vehicle commands are restricted."
    elif safe_mode["level"] == 1:
        text = "Security notice. Increased monitoring is active."
    else:
        text = "DriveFort AI status normal."
    return {"enabled": True, "text": text, "browser_speech_supported": True}


def auto_security_test(engine, rounds: int = 12) -> Dict[str, Any]:
    attacks = list(ADOPTED_ATTACK_ORDER)
    original_attack = engine.attack
    original_vehicle = engine.vehicle
    results = []
    detected = 0
    total_response = 0
    for idx in range(max(1, min(30, int(rounds)))):
        attack_name = attacks[idx % len(attacks)]
        engine.apply_preset(attack_name)
        engine.attack.intensity = round(0.58 + (idx % 5) * 0.09, 2)
        snap = engine.snapshot()
        is_detected = snap["risks"]["overall"] >= 0.35 or snap["risks"]["threat_level"] != "NORMAL"
        detected += 1 if is_detected else 0
        total_response += snap.get("pro", {}).get("performance_metrics", {}).get("response_time_ms", 150)
        results.append({
            "attack": attack_name,
            "intensity": engine.attack.intensity,
            "detected": is_detected,
            "risk": snap["risks"]["overall"],
            "safe_mode_level": snap.get("pro", {}).get("safe_mode_levels", {}).get("level", 0),
        })
    engine.attack = original_attack
    engine.vehicle = original_vehicle
    return {
        "rounds": len(results),
        "detection_rate": round(detected / max(1, len(results)), 2),
        "average_response_ms": int(total_response / max(1, len(results))),
        "results": results,
    }
