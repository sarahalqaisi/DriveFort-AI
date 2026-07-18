from __future__ import annotations

from typing import Dict, List

from .models import AttackState, RiskBundle, VehicleState
from .attack_catalog import canonical_attack


class RiskEngine:
    ATTACK_MAP: Dict[str, Dict[str, float]] = {
        "normal": {"safety": 0.05, "privacy": 0.02, "availability": 0.02, "cyber_physical": 0.03, "ai": 0.04},
        "can_flooding": {"safety": 0.20, "privacy": 0.05, "availability": 0.90, "cyber_physical": 0.22, "ai": 0.76},
        "dos": {"safety": 0.28, "privacy": 0.04, "availability": 0.95, "cyber_physical": 0.26, "ai": 0.80},
        "brake_injection": {"safety": 0.92, "privacy": 0.08, "availability": 0.18, "cyber_physical": 0.84, "ai": 0.85},
        "brake_override": {"safety": 0.94, "privacy": 0.08, "availability": 0.22, "cyber_physical": 0.90, "ai": 0.88},
        "steering_manipulation": {"safety": 0.86, "privacy": 0.06, "availability": 0.16, "cyber_physical": 0.93, "ai": 0.88},
        "telemetry_scraping": {"safety": 0.12, "privacy": 0.91, "availability": 0.09, "cyber_physical": 0.08, "ai": 0.74},
        "battery_thermal_tampering": {"safety": 0.83, "privacy": 0.04, "availability": 0.14, "cyber_physical": 0.90, "ai": 0.87},
        "gps_spoofing": {"safety": 0.68, "privacy": 0.18, "availability": 0.22, "cyber_physical": 0.66, "ai": 0.78},
        "sensor_spoofing": {"safety": 0.76, "privacy": 0.12, "availability": 0.18, "cyber_physical": 0.72, "ai": 0.82},
        "throttle_injection": {"safety": 0.90, "privacy": 0.06, "availability": 0.16, "cyber_physical": 0.88, "ai": 0.86},
        "acceleration_injection": {"safety": 0.93, "privacy": 0.06, "availability": 0.18, "cyber_physical": 0.91, "ai": 0.88},
        "can_bus_injection": {"safety": 0.82, "privacy": 0.10, "availability": 0.78, "cyber_physical": 0.86, "ai": 0.86},
        "lane_drift_attack": {"safety": 0.84, "privacy": 0.05, "availability": 0.16, "cyber_physical": 0.87, "ai": 0.90},
        "pedestrian_detection_attack": {"safety": 0.98, "privacy": 0.06, "availability": 0.20, "cyber_physical": 0.96, "ai": 0.93},
        "camera_lidar_blinding": {"safety": 0.82, "privacy": 0.08, "availability": 0.36, "cyber_physical": 0.71, "ai": 0.84},
        "mixed_attack": {"safety": 0.84, "privacy": 0.74, "availability": 0.81, "cyber_physical": 0.88, "ai": 0.92},
    }

    def assess(self, vehicle: VehicleState, attack: AttackState) -> RiskBundle:
        active_vectors = attack.active_vectors()
        if not active_vectors:
            active_vectors = ["normal"]
        profile = self._combine_profiles(active_vectors)
        intensity = attack.intensity if attack.active else 0.0

        if attack.active:
            for key in list(profile.keys()):
                profile[key] = round(min(1.0, max(0.0, profile[key] * (0.45 + intensity * 0.55))), 3)

        if vehicle.speed_kmh > 90:
            profile["safety"] = min(1.0, round(profile["safety"] + 0.06, 3))
        if vehicle.battery_temp_c > 45:
            profile["cyber_physical"] = min(1.0, round(profile["cyber_physical"] + 0.07, 3))
        if vehicle.autopilot_enabled and attack.active:
            profile["ai"] = min(1.0, round(profile["ai"] + 0.05, 3))
        if vehicle.obstacle_distance_m < 10 and attack.active:
            profile["safety"] = min(1.0, round(profile["safety"] + 0.05, 3))
        if attack.mode == "stealth":
            profile["ai"] = max(0.0, round(profile["ai"] - 0.08, 3))
            profile["privacy"] = min(1.0, round(profile["privacy"] + 0.04, 3))
        if attack.mode == "aggressive":
            profile["availability"] = min(1.0, round(profile["availability"] + 0.06, 3))
            profile["cyber_physical"] = min(1.0, round(profile["cyber_physical"] + 0.06, 3))

        weighted = (
            0.28 * profile["safety"]
            + 0.18 * profile["privacy"]
            + 0.19 * profile["availability"]
            + 0.20 * profile["cyber_physical"]
            + 0.15 * profile["ai"]
        )
        overall = round(min(1.0, weighted + (0.06 if len(active_vectors) > 1 else 0.0)), 3)
        dominant_risk = max(profile, key=profile.get)

        if overall >= 0.85:
            action = "EMERGENCY_SAFE_MODE"
            threat_level = "CRITICAL"
            defense_mode = "Critical Lockdown"
        elif overall >= 0.65:
            action = "RESTRICT_AND_MONITOR"
            threat_level = "ATTACK"
            defense_mode = "Elevated Security"
        elif overall >= 0.35:
            action = "ALERT_AND_LOG"
            threat_level = "SUSPICIOUS"
            defense_mode = "Monitored"
        else:
            action = "ALLOW"
            threat_level = "NORMAL"
            defense_mode = "Normal"

        ai_label = "attack_likely" if profile["ai"] >= 0.75 else "suspicious" if profile["ai"] >= 0.4 else "normal"
        ai_confidence = round(min(0.98, 0.4 + profile["ai"] * 0.55 + (0.04 if len(active_vectors) > 1 else 0.0)), 3)
        ai_uncertainty = round(max(0.02, 1 - ai_confidence), 3)
        ai_reason = self._build_ai_reason(active_vectors, profile)
        summary = self._build_summary(active_vectors, dominant_risk, action)
        root_cause = self._build_root_cause(active_vectors, attack, vehicle)
        defense_strategy = self._build_defense_strategy(action, dominant_risk, attack)
        recovery_status = self._build_recovery_status(action, overall)
        ai_rule_split = {
            "ai": round(min(0.75, 0.38 + profile["ai"] * 0.35), 2),
            "rules": round(max(0.25, 0.62 - profile["ai"] * 0.35), 2),
        }
        system_load = {
            "cpu": round(18 + profile["availability"] * 40 + profile["ai"] * 18, 1),
            "message_rate": round(15 + profile["availability"] * 105, 1),
            "latency_ms": round(7 + profile["availability"] * 50 + (10 if attack.mode == "stealth" else 0), 1),
        }

        return RiskBundle(
            safety=profile["safety"],
            privacy=profile["privacy"],
            availability=profile["availability"],
            cyber_physical=profile["cyber_physical"],
            ai=profile["ai"],
            overall=overall,
            dominant_risk=dominant_risk,
            action=action,
            ai_label=ai_label,
            ai_reason=ai_reason,
            ai_confidence=ai_confidence,
            ai_uncertainty=ai_uncertainty,
            summary=summary,
            threat_level=threat_level,
            severity_score=round(overall * 10, 1),
            defense_mode=defense_mode,
            defense_strategy=defense_strategy,
            recovery_status=recovery_status,
            root_cause=root_cause,
            ai_rule_split=ai_rule_split,
            system_load=system_load,
        )

    def _combine_profiles(self, attacks: List[str]) -> Dict[str, float]:
        keys = ["safety", "privacy", "availability", "cyber_physical", "ai"]
        if attacks == ["normal"]:
            return self.ATTACK_MAP["normal"].copy()
        combined = {k: 0.0 for k in keys}
        for attack_name in attacks:
            attack_name = canonical_attack(attack_name)
            profile = self.ATTACK_MAP.get(attack_name, self.ATTACK_MAP["normal"])
            for key in keys:
                combined[key] = max(combined[key], profile[key])
        if len(attacks) > 1:
            for key in keys:
                combined[key] = min(1.0, round(combined[key] + 0.03, 3))
        return combined

    @staticmethod
    def _build_ai_reason(active_vectors: List[str], profile: Dict[str, float]) -> str:
        vector_text = ", ".join(v.replace("_", " ") for v in active_vectors if v != "normal") or "baseline"
        dominant = max(profile, key=profile.get)
        return f"{vector_text} indicators detected | dominant={dominant} | AI risk={profile['ai']}"

    @staticmethod
    def _build_summary(active_vectors: List[str], dominant_risk: str, action: str) -> str:
        if active_vectors == ["normal"]:
            return "Vehicle operating normally with low-risk profile."
        vector_text = ", ".join(v.replace("_", " ") for v in active_vectors)
        return f"Detected {vector_text}. Dominant risk is {dominant_risk}. Recommended action: {action}."

    @staticmethod
    def _build_root_cause(active_vectors: List[str], attack: AttackState, vehicle: VehicleState) -> List[str]:
        causes: List[str] = []
        for vector in active_vectors:
            vector = canonical_attack(vector)
            if vector in {"can_bus_injection", "dos"}:
                causes.append("abnormal CAN traffic rate and arbitration pressure")
            if vector == "steering_manipulation":
                causes.append("steering command deviates from expected lane context")
            if vector == "brake_override":
                causes.append("brake command is suppressed or injected against time-to-collision context")
            if vector == "telemetry_scraping":
                causes.append("high-frequency telemetry access targeting sensitive fields")
            if vector == "battery_thermal_tampering":
                causes.append("battery thermal profile inconsistent with drive load")
            if vector == "gps_spoofing":
                causes.append("reported GPS position jumps away from inertial and map context")
            if vector == "sensor_spoofing":
                causes.append("sensor readings conflict with digital-twin expectations")
            if vector == "acceleration_injection":
                causes.append("unexpected acceleration command without matching driver intent or obstacle context")
            if vector == "camera_lidar_blinding":
                causes.append("perception confidence drops while obstacle context becomes unreliable")
            if vector == "lane_drift_attack":
                causes.append("small continuous steering bias creates gradual lane departure")
            if vector == "pedestrian_detection_attack":
                causes.append("pedestrian perception or AEB decision is inconsistent with obstacle proximity")
            if vector == "mixed_attack":
                causes.append("multiple concurrent anomalies across network and control layers")
        if vehicle.driver_attention in {"distracted", "fatigued"}:
            causes.append(f"driver attention degraded: {vehicle.driver_attention}")
        if attack.mode == "stealth":
            causes.append("attack mode is stealth-oriented, reducing obvious signatures")
        return causes[:5] or ["no abnormal causal chain detected"]

    @staticmethod
    def _build_defense_strategy(action: str, dominant_risk: str, attack: AttackState) -> List[str]:
        strategy = ["continuous monitoring"]
        if action in {"RESTRICT_AND_MONITOR", "EMERGENCY_SAFE_MODE"}:
            strategy.append("steering clamping")
            strategy.append("speed limiting")
        if dominant_risk == "availability":
            strategy.append("message rate limiting")
        if dominant_risk == "privacy":
            strategy.append("telemetry channel restriction")
        if dominant_risk == "cyber_physical":
            strategy.append("manual override readiness")
        if attack.attack_name in {"gps_spoofing", "sensor_spoofing", "camera_lidar_blinding"}:
            strategy.append("cross-sensor validation")
        if attack.attack_name == "throttle_injection":
            strategy.append("powertrain command gating")
        if action == "EMERGENCY_SAFE_MODE":
            strategy.append("suspect node isolation")
        if attack.adaptive_ai:
            strategy.append("adaptive anomaly threshold hardening")
        return strategy

    @staticmethod
    def _build_recovery_status(action: str, overall: float) -> str:
        if action == "ALLOW":
            return "System stable. No recovery workflow is active."
        if action == "ALERT_AND_LOG":
            return "Monitoring for stabilization while keeping all systems online."
        if action == "RESTRICT_AND_MONITOR":
            return f"Recovery in progress. Risk is being reduced from {overall:.2f} through controlled limitation."
        return "Critical containment active. Vehicle is prioritizing safe-state recovery."
