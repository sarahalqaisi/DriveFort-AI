"""Canonical attack catalog for the graduation-project CARLA demo.

The project historically used a few internal names such as ``brake_injection``
and ``throttle_injection``.  This catalog keeps those aliases working while the
Dashboard and report use the final adopted attack names.
"""
from __future__ import annotations

from typing import Dict, List

ADOPTED_ATTACK_ORDER: List[str] = [
    "steering_manipulation",
    "brake_override",
    "acceleration_injection",
    "sensor_spoofing",
    "gps_spoofing",
    "can_bus_injection",
    "dos",
    "lane_drift_attack",
    "pedestrian_detection_attack",
]

ATTACK_ALIASES: Dict[str, str] = {
    "brake_injection": "brake_override",
    "throttle_injection": "acceleration_injection",
    "can_flooding": "can_bus_injection",
    "camera_lidar_blinding": "sensor_spoofing",
}

ATTACK_LABELS: Dict[str, Dict[str, str]] = {
    "steering_manipulation": {
        "en": "Steering Manipulation",
        "ar": "التلاعب بالمقود",
        "target": "Steering ECU / lateral control",
        "impact": "Forces a visible lane departure and side/building impact in CARLA.",
        "defense": "Steering clamp, rate limiting, lane recovery and fail-safe braking.",
    },
    "brake_override": {
        "en": "Brake Override",
        "ar": "تجاوز الفرامل",
        "target": "Brake ECU / ABS / brake-by-wire",
        "impact": "Suppresses needed braking or creates unsafe braking behavior, causing a front/rear collision scenario.",
        "defense": "Brake consistency check, throttle cut, emergency braking and time-to-collision validation.",
    },
    "acceleration_injection": {
        "en": "Acceleration Injection",
        "ar": "حقن التسارع",
        "target": "Powertrain ECU / throttle control",
        "impact": "Injects unsafe throttle and pushes the vehicle into a forward collision target.",
        "defense": "Throttle firewall, obstacle-aware speed limiting, emergency brake and AI spike detection.",
    },
    "sensor_spoofing": {
        "en": "Sensor Spoofing",
        "ar": "انتحال الحساسات",
        "target": "Perception / sensor-fusion stack",
        "impact": "Creates a missed-obstacle or false-perception collision scenario.",
        "defense": "Multi-sensor validation, trust scoring and perception mismatch alerts.",
    },
    "gps_spoofing": {
        "en": "GPS Spoofing",
        "ar": "انتحال GPS",
        "target": "GNSS / localization / route planning",
        "impact": "Pushes the vehicle toward a wrong-route wall or roadside target.",
        "defense": "Cross-check GPS with map, IMU, heading and vehicle motion; reduce GPS trust.",
    },
    "can_bus_injection": {
        "en": "CAN Bus Injection",
        "ar": "حقن شبكة CAN",
        "target": "Gateway ECU / internal vehicle network",
        "impact": "Injects conflicting steering/throttle/brake behavior for a visible loss-of-control scenario.",
        "defense": "Command authentication, conflict rejection, rate limiting and gateway isolation.",
    },
    "dos": {
        "en": "Denial of Service (DoS)",
        "ar": "حجب الخدمة",
        "target": "Gateway / controller availability",
        "impact": "Simulates delayed/lost control updates that drift the vehicle into an obstacle.",
        "defense": "Heartbeat monitoring, critical command prioritization and safe-stop mode.",
    },
    "lane_drift_attack": {
        "en": "Lane Drift Attack",
        "ar": "هجوم انحراف المسار",
        "target": "Lane keeping / lateral control",
        "impact": "Applies a small continuous steering bias until the vehicle visibly leaves the lane.",
        "defense": "AI time-series drift detection, lane recovery and controlled speed reduction.",
    },
    "pedestrian_detection_attack": {
        "en": "Pedestrian Detection Attack",
        "ar": "خداع كشف المشاة",
        "target": "Pedestrian perception / AEB decision layer",
        "impact": "Spawns a walker/obstacle ahead and demonstrates failure to stop unless Human Safety Mode reacts.",
        "defense": "Human Safety Mode, obstacle cross-checking, emergency brake and critical risk escalation.",
    },
}


def canonical_attack(name: str) -> str:
    value = str(name or "normal")
    return ATTACK_ALIASES.get(value, value)


def display_label(name: str) -> str:
    key = canonical_attack(name)
    meta = ATTACK_LABELS.get(key)
    if not meta:
        return str(name).replace("_", " ").title()
    return f"{meta['en']} — {meta['ar']}"


def adopted_attack_catalog() -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for key in ADOPTED_ATTACK_ORDER:
        meta = dict(ATTACK_LABELS[key])
        meta["id"] = key
        meta["label"] = display_label(key)
        output.append(meta)
    return output
