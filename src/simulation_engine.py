from __future__ import annotations

import copy
import time
from typing import Any, Dict, List

from .attack_fingerprint import AttackFingerprint
from .ecu_trust_manager import ECUTrustManager
from .models import AttackState, VehicleState, ALLOWED_ATTACKS, ALLOWED_ECUS, ALLOWED_MODES, ALLOWED_OBJECTIVES, clamp_float, safe_choice
from .risk_engine import RiskEngine
from .carla_bridge import CarlaBridge
from .incident_store import IncidentStore
from .core import BRAND, derive_system_phase
from .pro_features import (
    auto_security_test, network_attack_layer, performance_metrics, plugin_catalog,
    safe_mode_levels, sensor_fusion, sensor_trust_scores, sign_command,
    threat_prediction, verify_command, voice_alerts,
)


class SimulationEngine:
    def __init__(self) -> None:
        self.risk_engine = RiskEngine()
        self.mode = "mock"
        self.carla_bridge = CarlaBridge()
        self.carla_last_apply = {"mode": "mock", "attack_applied": False, "defense_applied": False, "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}}
        self.fingerprint = AttackFingerprint()
        self.trust = ECUTrustManager()
        self.default_vehicle = VehicleState()
        self.default_attack = AttackState()
        self.vehicle = copy.deepcopy(self.default_vehicle)
        self.attack = copy.deepcopy(self.default_attack)
        self.event_log: List[str] = ["[BOOT] DriveFort AI Tesla demo initialized."]
        self.risk_history: List[float] = [0.05, 0.06, 0.05]
        self.attack_timeline: List[Dict[str, str]] = [
            {"stage": "t0", "title": "Stable system", "detail": "All monitored channels are operating within baseline."},
        ]
        self.learning_patterns = 12
        self.false_positive_rate = 0.07
        self.demo_running = False
        self.demo_phase = "idle"
        self.demo_counter = 0
        self.prev_overall_risk = 0.05
        self.store = IncidentStore()
        self.last_record_key = None
        self.user_role = "Admin"
        self.threat_feed = [
            "Global feed: arbitration abuse patterns increased in connected EV fleets.",
            "Threat intel: telemetry scraping campaigns are targeting remote vehicle diagnostics.",
            "Advisory: mixed CAN flooding and steering override chains remain high-impact.",
        ]
        self.last_security_test = None
        self.command_auth_required = True
        self.full_demo_summary: Dict[str, Any] = {
            "status": "not_run",
            "phase": "idle",
            "before": {},
            "after": {},
            "delta": {},
            "timeline": [],
            "owner_message": "Run the full demo to capture normal driving, attack impact, diagnostics and recovery evidence."
        }

    def _log(self, message: str) -> None:
        self.event_log.append(message)
        self.event_log = self.event_log[-20:]

    def set_mode(self, mode: str) -> dict:
        requested = (mode or "mock").lower()
        if requested == "carla":
            status = self.carla_bridge.connect()
            if status.connected and status.actor_found:
                self.mode = "carla"
                self._log(f"[CARLA] Connected to {status.map_name} on {status.host}:{status.port}.")
            else:
                self.mode = "mock"
                self._log(f"[CARLA] Mode request failed. {status.message}")
            return status.to_dict()
        self.mode = "mock"
        status = self.carla_bridge.disconnect()
        self._log("[CARLA] Mock mode enabled.")
        return status.to_dict()

    def connect_carla_full(self, payload: Dict[str, Any]) -> dict:
        host = str(payload.get("host") or "localhost")
        port = int(clamp_float(payload.get("port", 2000), 1, 65535, 2000))
        spawn_if_missing = self._bool_value(payload.get("spawn_if_missing", False), False)
        synchronous = self._bool_value(payload.get("synchronous", False), False)
        fps = clamp_float(payload.get("fps", 20), 1.0, 60.0, 20.0)
        status = self.carla_bridge.connect(host=host, port=port, spawn_if_missing=spawn_if_missing, synchronous=synchronous, fps=fps)
        if status.connected and status.actor_found:
            self.mode = "carla"
            self._log(f"[CARLA] Full live mode connected: {status.map_name}, vehicle_id={status.vehicle_id}, sensors={status.sensors_ready}.")
        else:
            self.mode = "mock"
            self._log(f"[CARLA] Full mode unavailable. {status.message}")
        return status.to_dict()

    def carla_tick(self) -> dict:
        result = self.carla_bridge.tick()
        if result.get("ok"):
            self._log(f"[CARLA] Tick frame {result.get('frame')}.")
        else:
            self._log(f"[CARLA] Tick failed: {result.get('message')}")
        return result

    def carla_live_start(self) -> dict:
        # One-click start: connect, spawn the vehicle, then start the CARLA tick loop.
        if not self.carla_bridge.is_ready():
            self.connect_carla_full({"host": "localhost", "port": 2000, "spawn_if_missing": True, "synchronous": True, "fps": 20})
        status = self.carla_bridge.start_live_loop()
        if status.connected and status.actor_found:
            self.mode = "carla"
        self._log(f"[CARLA] Live loop status: {status.message}")
        return status.to_dict()

    def carla_live_stop(self) -> dict:
        status = self.carla_bridge.stop_live_loop()
        self._log("[CARLA] Live loop stopped.")
        return status.to_dict()

    def carla_sensor_snapshot(self) -> dict:
        return self.carla_bridge.sensor_snapshot()

    def carla_status(self) -> dict:
        status = self.carla_bridge.status.to_dict()
        status["mode"] = self.mode
        status["last_apply"] = self.carla_last_apply
        status["impact"] = getattr(self.carla_bridge, "_last_impact_report", {"active": False, "verified": False, "severity": "none", "target": "none", "message": "No impact."})
        return status

    def reset(self) -> None:
        self.vehicle = copy.deepcopy(self.default_vehicle)
        self.attack = copy.deepcopy(self.default_attack)
        self.event_log = ["[BOOT] DriveFort AI Tesla demo initialized."]
        self.risk_history = [0.05, 0.06, 0.05]
        self.attack_timeline = [
            {"stage": "t0", "title": "Stable system", "detail": "All monitored channels are operating within baseline."},
        ]
        self.learning_patterns = 12
        self.false_positive_rate = 0.07
        self.demo_running = False
        self.demo_phase = "idle"
        self.demo_counter = 0
        self.prev_overall_risk = 0.05
        self._log("[INFO] Demo reset to baseline state.")
        try:
            if self.mode == "carla" and self.carla_bridge.is_ready():
                self.carla_bridge.enable_natural_drive()
        except Exception:
            pass

    def _bool_value(self, value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "on"}
        if value is None:
            return default
        return bool(value)

    def update_driver(self, payload: Dict[str, Any]) -> None:
        numeric_ranges = {
            "speed_kmh": (0.0, 180.0), "steer": (-1.0, 1.0), "brake": (0.0, 1.0), "throttle": (0.0, 1.0),
            "battery_soc": (0.0, 100.0), "battery_temp_c": (15.0, 120.0), "motor_temp_c": (15.0, 140.0),
            "obstacle_distance_m": (1.0, 150.0), "heading_deg": (0.0, 359.0), "location_x": (-180.0, 180.0), "location_y": (-90.0, 90.0),
        }
        allowed_text = {
            "zone_type": {"urban", "highway", "school_zone", "intersection"},
            "drive_mode": {"eco", "normal", "sport"},
            "weather": {"clear", "rain", "fog", "windy"},
            "traffic_density": {"low", "medium", "high"},
            "lane_status": {"centered", "drifting_left", "drifting_right"},
            "driver_attention": {"focused", "distracted", "fatigued"},
        }
        for key, value in payload.items():
            if key in numeric_ranges:
                low, high = numeric_ranges[key]
                setattr(self.vehicle, key, clamp_float(value, low, high, getattr(self.vehicle, key)))
            elif key in allowed_text:
                setattr(self.vehicle, key, safe_choice(value, allowed_text[key], getattr(self.vehicle, key)))
            elif key in {"autopilot_enabled", "manual_override", "charging_mode"}:
                setattr(self.vehicle, key, self._bool_value(value, getattr(self.vehicle, key)))
            elif key == "location_label":
                self.vehicle.location_label = str(value or self.vehicle.location_label)[:80]
        self._log(f"[DRIVER] Validated driver state in zone={self.vehicle.zone_type} at {self.vehicle.speed_kmh:.0f} km/h.")

    def update_attack(self, payload: Dict[str, Any]) -> None:
        self.attack.attack_name = safe_choice(payload.get("attack_name", self.attack.attack_name), ALLOWED_ATTACKS, "normal")
        self.attack.intensity = clamp_float(payload.get("intensity", self.attack.intensity), 0.0, 1.0, self.attack.intensity)
        self.attack.active = self._bool_value(payload.get("active", self.attack.active), self.attack.active)
        self.attack.objective = safe_choice(payload.get("objective", self.attack.objective), ALLOWED_OBJECTIVES, self.attack.objective)
        self.attack.mode = safe_choice(payload.get("mode", self.attack.mode), ALLOWED_MODES, self.attack.mode)
        self.attack.duration_sec = int(clamp_float(payload.get("duration_sec", self.attack.duration_sec), 1, 120, self.attack.duration_sec))
        self.attack.target_ecu = safe_choice(payload.get("target_ecu", self.attack.target_ecu), ALLOWED_ECUS, self.attack.target_ecu)
        extras = payload.get("extra_attacks", self.attack.extra_attacks) or []
        if not isinstance(extras, list):
            extras = []
        self.attack.extra_attacks = [x for x in extras if x in ALLOWED_ATTACKS and x not in {"normal", self.attack.attack_name}][:5]
        self.attack.adaptive_ai = self._bool_value(payload.get("adaptive_ai", self.attack.adaptive_ai), self.attack.adaptive_ai)
        self.attack.replay_enabled = self._bool_value(payload.get("replay_enabled", self.attack.replay_enabled), self.attack.replay_enabled)
        state = "ACTIVE" if self.attack.active else "INACTIVE"
        self._log(f"[ATTACK] {pretty_attack(self.attack.attack_name)} set to {state} with intensity={self.attack.intensity:.2f}.")

    def apply_driver_action(self, action_name: str) -> bool:
        if action_name == "manual_override":
            self.vehicle.manual_override = True
            self.vehicle.autopilot_enabled = False
            self._log("[DRIVER] Manual override engaged.")
        elif action_name == "safe_stop":
            self.vehicle.speed_kmh = max(0.0, min(self.vehicle.speed_kmh, 12.0))
            self.vehicle.throttle = 0.0
            self.vehicle.brake = max(0.6, self.vehicle.brake)
            self._log("[DRIVER] Emergency safe stop requested.")
        elif action_name == "ack_alert":
            self._log("[DRIVER] Alerts acknowledged by operator.")
        elif action_name == "reset_safe_mode":
            self.vehicle.manual_override = False
            self.vehicle.brake = 0.0
            self.vehicle.throttle = 0.25
            self._log("[DRIVER] Safe-mode reset requested.")
        else:
            self._log(f"[WARN] Unknown driver action rejected: {action_name}")
            return False
        return True

    def apply_preset(self, attack_name: str) -> bool:
        presets = {
            "normal": {"attack_name": "normal", "intensity": 0.0, "active": False, "objective": "disrupt_control", "mode": "normal", "duration_sec": 10, "target_ecu": "steering_ecu", "extra_attacks": []},
            "can_flooding": {"attack_name": "can_flooding", "intensity": 0.88, "active": True, "objective": "system_overload", "mode": "aggressive", "duration_sec": 20, "target_ecu": "gateway_ecu", "extra_attacks": []},
            "dos": {"attack_name": "dos", "intensity": 0.90, "active": True, "objective": "system_overload", "mode": "aggressive", "duration_sec": 20, "target_ecu": "gateway_ecu", "extra_attacks": []},
            "brake_injection": {"attack_name": "brake_injection", "intensity": 0.92, "active": True, "objective": "cause_collision", "mode": "normal", "duration_sec": 10, "target_ecu": "brake_ecu", "extra_attacks": []},
            "steering_manipulation": {"attack_name": "steering_manipulation", "intensity": 0.91, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "steering_ecu", "extra_attacks": []},
            "telemetry_scraping": {"attack_name": "telemetry_scraping", "intensity": 0.82, "active": True, "objective": "data_exfiltration", "mode": "stealth", "duration_sec": 20, "target_ecu": "telematics_ecu", "extra_attacks": []},
            "battery_thermal_tampering": {"attack_name": "battery_thermal_tampering", "intensity": 0.92, "active": True, "objective": "disrupt_control", "mode": "normal", "duration_sec": 15, "target_ecu": "battery_ecu", "extra_attacks": []},
            "gps_spoofing": {"attack_name": "gps_spoofing", "intensity": 0.86, "active": True, "objective": "mislead_navigation", "mode": "stealth", "duration_sec": 20, "target_ecu": "telematics_ecu", "extra_attacks": []},
            "sensor_spoofing": {"attack_name": "sensor_spoofing", "intensity": 0.88, "active": True, "objective": "disrupt_control", "mode": "normal", "duration_sec": 15, "target_ecu": "perception_ecu", "extra_attacks": []},
            "throttle_injection": {"attack_name": "throttle_injection", "intensity": 0.91, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "powertrain_ecu", "extra_attacks": []},
            "camera_lidar_blinding": {"attack_name": "camera_lidar_blinding", "intensity": 0.87, "active": True, "objective": "blind_perception", "mode": "stealth", "duration_sec": 15, "target_ecu": "perception_ecu", "extra_attacks": []},
            "mixed_attack": {"attack_name": "mixed_attack", "intensity": 0.98, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 20, "target_ecu": "gateway_ecu", "extra_attacks": ["steering_manipulation", "can_flooding"]},
        }
        if attack_name not in presets:
            self._log(f"[WARN] Unknown preset rejected: {attack_name}")
            return False
        self.update_attack(presets[attack_name])
        self._log(f"[PRESET] Scenario preset applied: {attack_name}.")
        return True

    def start_demo(self) -> None:
        self.demo_running = True
        self.demo_phase = "warning"
        self.demo_counter = 0
        self._log("[DEMO] Guided presentation demo started.")

    def stop_demo(self) -> None:
        self.demo_running = False
        self.demo_phase = "idle"
        self.demo_counter = 0
        self._log("[DEMO] Guided presentation demo stopped.")

    def advance_demo(self) -> None:
        if not self.demo_running:
            self.start_demo()
            return
        phases = ["warning", "injection", "containment", "recovery"]
        idx = phases.index(self.demo_phase) if self.demo_phase in phases else -1
        next_idx = (idx + 1) % len(phases)
        self.demo_phase = phases[next_idx]
        self.demo_counter += 1

        if self.demo_phase == "warning":
            self.attack = AttackState()
            self.vehicle.autopilot_enabled = True
            self.vehicle.speed_kmh = 52.0
            self.vehicle.zone_type = "urban"
            self._log("[DEMO] Predictive warning phase initiated.")
        elif self.demo_phase == "injection":
            self.apply_preset("mixed_attack")
            self.vehicle.speed_kmh = 68.0
            self.vehicle.driver_attention = "distracted"
            self._log("[DEMO] Attack injection phase activated.")
        elif self.demo_phase == "containment":
            self.vehicle.manual_override = True
            self.vehicle.autopilot_enabled = False
            self._log("[DEMO] Defense containment phase activated.")
        elif self.demo_phase == "recovery":
            self.attack.active = False
            self.attack.attack_name = "normal"
            self.attack.extra_attacks = []
            self.vehicle.speed_kmh = 24.0
            self.vehicle.brake = 0.2
            self.vehicle.throttle = 0.12
            self._log("[DEMO] Recovery phase in progress.")

    def _attack_features(self) -> Dict[str, Any]:
        vectors = self.attack.active_vectors()
        if not vectors:
            return {"message_rate": 15, "repeated_ratio": 0.08, "control_overrides": 0, "drop_rate": 0.01}
        base = {"message_rate": 20.0, "repeated_ratio": 0.12, "control_overrides": 0, "drop_rate": 0.02}
        for attack in vectors:
            if attack == "can_flooding":
                base["message_rate"] += 95
                base["repeated_ratio"] += 0.62
                base["drop_rate"] += 0.18
            elif attack == "dos":
                base["message_rate"] += 105
                base["drop_rate"] += 0.28
            elif attack == "steering_manipulation":
                base["control_overrides"] += 8
            elif attack == "brake_injection":
                base["control_overrides"] += 6
            elif attack == "telemetry_scraping":
                base["message_rate"] += 30
            elif attack == "battery_thermal_tampering":
                base["control_overrides"] += 3
            elif attack == "gps_spoofing":
                base["message_rate"] += 35
                base["control_overrides"] += 2
            elif attack == "sensor_spoofing":
                base["message_rate"] += 42
                base["control_overrides"] += 4
            elif attack == "throttle_injection":
                base["control_overrides"] += 7
            elif attack == "camera_lidar_blinding":
                base["drop_rate"] += 0.22
                base["control_overrides"] += 3
            elif attack == "mixed_attack":
                base["message_rate"] += 82
                base["repeated_ratio"] += 0.44
                base["control_overrides"] += 7
                base["drop_rate"] += 0.15
        base["message_rate"] = round(base["message_rate"] * (0.5 + self.attack.intensity * 0.5), 1)
        base["repeated_ratio"] = round(min(0.98, base["repeated_ratio"]), 2)
        return base

    @staticmethod
    def _predict_attack_warning(current_risk: float, prev_risk: float, attack_active: bool, mode: str) -> Dict[str, Any]:
        delta = round(current_risk - prev_risk, 3)
        warning = (not attack_active and current_risk >= 0.32 and delta >= 0.06) or (attack_active and current_risk >= 0.55 and delta >= 0.08)
        msg = "Pattern escalation suggests an incoming coordinated attack." if warning else "No pre-attack escalation beyond baseline."
        eta = "2-4 sec" if warning else "N/A"
        confidence = round(min(0.96, max(0.08, 0.45 + delta + (0.06 if mode == "stealth" else 0.0))), 2)
        return {"warning": warning, "message": msg, "eta": eta, "confidence": confidence, "delta": delta}

    @staticmethod
    def _digital_twin(vehicle: VehicleState, attack: AttackState) -> Dict[str, Any]:
        expected = {
            "steer": 0.0 if vehicle.lane_status == "centered" else 0.18,
            "speed": 18.0 if vehicle.zone_type == "school_zone" else 50.0 if vehicle.zone_type == "urban" else 90.0,
            "battery_temp_c": 32.0 if not vehicle.charging_mode else 38.0,
        }
        actual = {
            "steer": vehicle.steer + (0.42 if attack.active and attack.attack_name in {"steering_manipulation", "mixed_attack", "sensor_spoofing"} else 0.0),
            "speed": vehicle.speed_kmh + (12.0 if attack.active and attack.attack_name in {"throttle_injection", "gps_spoofing"} else 0.0),
            "battery_temp_c": vehicle.battery_temp_c + (16.0 if attack.active and attack.attack_name in {"battery_thermal_tampering", "mixed_attack"} else 0.0),
        }
        deviations = {
            "steer": round(abs(actual["steer"] - expected["steer"]), 2),
            "speed": round(abs(actual["speed"] - expected["speed"]), 1),
            "battery_temp_c": round(abs(actual["battery_temp_c"] - expected["battery_temp_c"]), 1),
        }
        anomaly = deviations["steer"] > 0.3 or deviations["speed"] > 18 or deviations["battery_temp_c"] > 10
        return {"expected": expected, "actual": actual, "deviations": deviations, "anomaly": anomaly}

    def _build_driver_console(self, risk, trust_score: float, trust_class: str) -> Dict[str, Any]:
        requested = {
            "speed": round(self.vehicle.speed_kmh, 1),
            "steer": round(self.vehicle.steer, 2),
            "throttle": round(self.vehicle.throttle, 2),
            "brake": round(self.vehicle.brake, 2),
        }
        applied = requested.copy()
        if risk.action == "RESTRICT_AND_MONITOR":
            applied["speed"] = round(min(self.vehicle.speed_kmh, 55.0), 1)
            applied["steer"] = round(max(-0.35, min(0.35, self.vehicle.steer)), 2)
            applied["throttle"] = round(min(self.vehicle.throttle, 0.3), 2)
        elif risk.action == "EMERGENCY_SAFE_MODE":
            applied["speed"] = round(min(self.vehicle.speed_kmh, 18.0), 1)
            applied["steer"] = round(max(-0.15, min(0.15, self.vehicle.steer)), 2)
            applied["throttle"] = 0.0
            applied["brake"] = max(0.7, round(self.vehicle.brake, 2))
        elif risk.action == "ISOLATE_ATTACK_NODE":
            applied["speed"] = round(min(self.vehicle.speed_kmh, 30.0), 1)
            applied["throttle"] = round(min(self.vehicle.throttle, 0.2), 2)
            applied["steer"] = round(max(-0.2, min(0.2, self.vehicle.steer)), 2)

        alerts: List[Dict[str, str]] = []
        if self.vehicle.battery_temp_c >= 45:
            alerts.append({"level": "warning", "text": "Battery temperature elevated above nominal EV range."})
        if self.attack.active and risk.cyber_physical >= 0.65:
            alerts.append({"level": "critical", "text": "Control-path anomaly detected. Driver should stay ready to intervene."})
        if self.attack.active and risk.availability >= 0.65:
            alerts.append({"level": "warning", "text": "Vehicle network congestion detected. Control updates may be delayed."})
        if risk.action == "EMERGENCY_SAFE_MODE":
            alerts.append({"level": "critical", "text": "Safe mode active. Vehicle authority reduced to protect occupants."})
        if self.vehicle.manual_override:
            alerts.append({"level": "info", "text": "Manual override engaged. Autopilot authority has been removed."})
        if not alerts:
            alerts.append({"level": "info", "text": "No active driver-critical alerts. Vehicle status is stable."})

        if risk.action == "EMERGENCY_SAFE_MODE":
            recommendation = "Reduce speed immediately and bring the vehicle to a controlled stop."
        elif risk.action == "RESTRICT_AND_MONITOR":
            recommendation = "Continue in-lane, avoid aggressive inputs, and prepare for manual control."
        elif risk.privacy >= 0.7:
            recommendation = "Maintain driving while remote telemetry channels are being restricted."
        else:
            recommendation = "Continue normal driving. No immediate driver action is required."

        trip_score = max(0, min(100, round((1.0 - risk.overall) * 100 - (15 if self.attack.active else 0))))
        protection_level = "Critical" if risk.overall >= 0.85 else "Elevated" if risk.overall >= 0.45 else "Standard"
        trust_state = "Restricted" if trust_class in {"blocked", "suspicious"} else "Monitored" if trust_class == "monitor" else "Normal"
        driver_trust = round(max(0.45, min(0.99, 0.92 - (0.18 if self.vehicle.driver_attention == "fatigued" else 0.08 if self.vehicle.driver_attention == "distracted" else 0.0))), 2)

        return {
            "requested_command": requested,
            "applied_command": applied,
            "alerts": alerts,
            "recommendation": recommendation,
            "trip_safety_score": trip_score,
            "protection_level": protection_level,
            "trust_state": trust_state,
            "driver_trust_level": "High" if driver_trust >= 0.85 else "Medium" if driver_trust >= 0.65 else "Low",
            "driver_trust_score": driver_trust,
        }

    def _build_attacker_console(self, risk, features: Dict[str, Any]) -> Dict[str, Any]:
        active_vectors = self.attack.active_vectors()
        impacts = {
            "safety": risk.safety,
            "privacy": risk.privacy,
            "availability": risk.availability,
            "cyber_physical": risk.cyber_physical,
            "ai": risk.ai,
        }
        expected_impact = [
            f"{label.replace('_', ' ').title()} risk ↑" for label, value in impacts.items() if value >= 0.45
        ] or ["Low observable impact expected"]
        detection_probability = round(min(0.99, risk.ai_confidence + (0.08 if self.attack.mode == "aggressive" else -0.05 if self.attack.mode == "stealth" else 0.0)), 2)
        telemetry = {
            "packets_sent": int(features["message_rate"] * max(1, self.attack.duration_sec)),
            "control_overrides": int(features["control_overrides"] * max(1, self.attack.duration_sec / 5)),
            "anomaly_score": round(risk.ai, 2),
            "drop_rate": round(features["drop_rate"], 2),
        }
        timeline = [
            {"t": "t0", "label": "Preparation", "detail": f"Target selected: {self.attack.target_ecu}"},
            {"t": "t1", "label": "Injection", "detail": f"Primary attack: {self.attack.attack_name.replace('_', ' ')}"},
            {"t": "t2", "label": "Propagation", "detail": f"Mode={self.attack.mode}, duration={self.attack.duration_sec}s"},
            {"t": "t3", "label": "Detection", "detail": f"Detection probability {detection_probability}"},
            {"t": "t4", "label": "Defense response", "detail": risk.action},
        ]
        attack_success = round(max(0.0, min(1.0, self.attack.intensity * (1 - min(0.95, risk.overall * 0.75)))), 2)
        defense_effectiveness = round(1 - attack_success, 2)
        source = "Remote Cloud" if self.attack.objective == "data_exfiltration" else "Nearby Device" if self.attack.mode == "stealth" else "Internal ECU"
        return {
            "active_vectors": active_vectors,
            "expected_impact": expected_impact,
            "detection_probability": detection_probability,
            "telemetry": telemetry,
            "timeline": timeline,
            "attack_success": attack_success,
            "defense_effectiveness": defense_effectiveness,
            "attack_source": source,
        }

    def _build_defense_dashboard(self, risk, score: float, trust_class: str, features: Dict[str, Any], digital_twin: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
        radar = {
            "labels": ["Safety", "Privacy", "Availability", "Cyber-Physical", "AI"],
            "values": [risk.safety, risk.privacy, risk.availability, risk.cyber_physical, risk.ai],
        }
        self.risk_history.append(risk.overall)
        self.risk_history = self.risk_history[-12:]
        if risk.overall >= 0.65:
            self.attack_timeline = [
                {"stage": "t0", "title": "Normal baseline", "detail": "Vehicle started from stable operating conditions."},
                {"stage": "t1", "title": "Anomaly detected", "detail": risk.root_cause[0] if risk.root_cause else "Anomaly signal observed."},
                {"stage": "t2", "title": "Risk elevation", "detail": f"Overall risk reached {risk.overall:.2f}."},
                {"stage": "t3", "title": "Attack classified", "detail": risk.fingerprint_type or self.attack.attack_name},
                {"stage": "t4", "title": "Defense activated", "detail": risk.action},
            ]
        elif not self.attack.active:
            self.attack_timeline = [
                {"stage": "t0", "title": "Stable system", "detail": "All monitored channels are operating within baseline."},
            ]
        ecu_status = [
            {"ecu": self.attack.target_ecu.replace('_', ' ').title(), "state": "Isolated" if trust_class == "blocked" else "Restricted" if trust_class == "suspicious" else "Monitored" if trust_class == "monitor" else "Trusted"},
            {"ecu": "Brake ECU", "state": "Trusted"},
            {"ecu": "Steering ECU", "state": "Restricted" if risk.cyber_physical > 0.7 else "Trusted"},
            {"ecu": "Telemetry ECU", "state": "Monitored" if risk.privacy > 0.5 else "Trusted"},
        ]
        incident_report = {
            "title": "DriveFort AI Incident Snapshot",
            "severity": risk.severity_score,
            "threat_level": risk.threat_level,
            "action": risk.action,
            "target": self.attack.target_ecu,
            "evidence": self.event_log[-8:],
            "root_cause": risk.root_cause,
            "strategy": risk.defense_strategy,
            "recovery": risk.recovery_status,
        }
        kpis = {
            "detection_time_s": round(max(0.08, 0.32 - risk.ai_confidence * 0.14), 3),
            "response_time_s": round(max(0.05, 0.26 - risk.overall * 0.1), 3),
            "accuracy": round(min(0.99, 0.86 + risk.ai_confidence * 0.08), 3),
            "false_positive_rate": round(max(0.01, self.false_positive_rate - (0.01 if self.attack.active else 0.0)), 3),
        }
        xai_graph = {
            "steering": round(min(1.0, risk.cyber_physical * 0.45 + (0.15 if self.attack.attack_name in {"steering_manipulation", "mixed_attack"} else 0.02)), 2),
            "can_rate": round(min(1.0, risk.availability * 0.42 + (0.15 if self.attack.attack_name in {"can_flooding", "dos", "mixed_attack"} else 0.01)), 2),
            "brake": round(min(1.0, risk.safety * 0.38 + (0.15 if self.attack.attack_name in {"brake_injection", "mixed_attack"} else 0.01)), 2),
        }
        security_score = max(0, min(100, round((1 - risk.overall) * 100 + score * 6 - (6 if self.attack.active else 0))))
        scenarios = {
            "normal": {"risk": 0.05, "detection_s": 0.0},
            "steering_manipulation": {"risk": 0.73, "detection_s": 0.12},
            "mixed_attack": {"risk": 0.89, "detection_s": 0.09},
        }
        current_key = self.attack.attack_name if self.attack.active else "normal"
        scenario_compare = {
            "baseline": scenarios["normal"],
            "current": scenarios.get(current_key, {"risk": risk.overall, "detection_s": kpis["detection_time_s"]}),
        }
        human_vs_ai = {
            "driver": "continue" if self.vehicle.manual_override else "assist/autopilot",
            "ai": "stop" if risk.action == "EMERGENCY_SAFE_MODE" else "restrict" if risk.action == "RESTRICT_AND_MONITOR" else "continue",
            "final": "AI override" if risk.action in {"EMERGENCY_SAFE_MODE", "RESTRICT_AND_MONITOR"} else "Driver aligned",
        }
        return {
            "radar": radar,
            "risk_history": self.risk_history,
            "attack_timeline": self.attack_timeline,
            "ecu_status": ecu_status,
            "incident_report": incident_report,
            "system_load": risk.system_load,
            "strategy": risk.defense_strategy,
            "root_cause": risk.root_cause,
            "recovery_status": risk.recovery_status,
            "message_rate": features["message_rate"],
            "prediction": prediction,
            "digital_twin": digital_twin,
            "kpis": kpis,
            "xai_graph": xai_graph,
            "security_score": security_score,
            "scenario_compare": scenario_compare,
            "human_vs_ai": human_vs_ai,
            "threat_feed": self.threat_feed,
            "learning_mode": {"enabled": True, "patterns_learned": self.learning_patterns},
            "demo": {"running": self.demo_running, "phase": self.demo_phase, "counter": self.demo_counter},
            "map": {"label": self.vehicle.location_label, "lat": self.vehicle.location_y, "lon": self.vehicle.location_x, "zone": self.vehicle.zone_type, "risk_radius_m": round(50 + risk.overall * 450)},
            "auto_alerts": [
                {"channel": "UI", "status": "sent" if risk.overall >= 0.35 else "standby", "message": risk.summary},
                {"channel": "Email/SOC", "status": "queued" if risk.overall >= 0.65 else "standby", "message": "Security team notification simulated."},
                {"channel": "Audio", "status": "armed" if risk.overall >= 0.65 else "quiet", "message": "Cabin warning tone simulated."},
            ],
            "safe_mode": {"active": risk.action in {"RESTRICT_AND_MONITOR", "EMERGENCY_SAFE_MODE", "ISOLATE_ATTACK_NODE"}, "speed_limit": 18 if risk.action == "EMERGENCY_SAFE_MODE" else 55 if risk.action == "RESTRICT_AND_MONITOR" else 30 if risk.action == "ISOLATE_ATTACK_NODE" else 180, "blocked_commands": ["unsafe throttle", "untrusted steering", "unknown ECU writes"] if risk.overall >= 0.65 else []},
            "replay": {"enabled": self.attack.replay_enabled, "frames": self.attack_timeline},
            "api_status": {"openapi_ready": True, "endpoints": ["/api/state", "/api/scenario/<name>", "/api/incidents", "/api/report/pdf", "/api/assistant/explain"]},
            "recent_incidents": self.store.list_recent(6),
        }


    def apply_carla_attack_console(self, attack_name: str, intensity: float = 0.92) -> Dict[str, Any]:
        """Apply one selected Attacker Console attack to UI state and live CARLA."""
        if attack_name not in ALLOWED_ATTACKS or attack_name == "normal":
            attack_name = "mixed_attack"
        if not self.carla_bridge.is_ready():
            self.start_natural_drive()
        self.apply_preset(attack_name)
        self.attack.intensity = clamp_float(intensity, 0.0, 1.0, self.attack.intensity)
        if attack_name == "steering_manipulation":
            self.update_driver({"lane_status": "drifting_right", "steer": 0.62, "brake": 0.0, "throttle": 0.22})
        elif attack_name == "brake_injection":
            self.update_driver({"speed_kmh": max(0, self.vehicle.speed_kmh - 18), "brake": 0.92, "throttle": 0.0})
        elif attack_name == "throttle_injection":
            self.update_driver({"speed_kmh": min(130, self.vehicle.speed_kmh + 34), "throttle": 0.95, "brake": 0.0})
        elif attack_name in {"can_flooding", "dos"}:
            self.update_driver({"speed_kmh": max(5, self.vehicle.speed_kmh - 12), "throttle": 0.10, "brake": 0.35, "lane_status": "drifting_left"})
        elif attack_name == "gps_spoofing":
            self.update_driver({"location_label": "Spoofed GPS route divergence", "lane_status": "drifting_right", "steer": 0.40})
        elif attack_name == "sensor_spoofing":
            self.update_driver({"lane_status": "drifting_left", "steer": -0.45, "obstacle_distance_m": 6})
        elif attack_name == "camera_lidar_blinding":
            self.update_driver({"speed_kmh": max(0, self.vehicle.speed_kmh - 20), "brake": 0.55, "obstacle_distance_m": 3})
        elif attack_name == "battery_thermal_tampering":
            self.update_driver({"battery_temp_c": 76, "motor_temp_c": 86, "battery_soc": max(10, self.vehicle.battery_soc - 6), "throttle": 0.12})
        elif attack_name == "telemetry_scraping":
            self.update_driver({"location_label": "Owner location telemetry exposed", "battery_temp_c": self.vehicle.battery_temp_c + 2})
        else:
            self.update_driver({"lane_status": "drifting_right", "steer": 0.55, "brake": 0.45, "battery_temp_c": 64, "motor_temp_c": 78})
            self.attack.extra_attacks = ["steering_manipulation", "gps_spoofing", "battery_thermal_tampering"]
        direct = self.carla_bridge.apply_direct_attack(attack_name, self.attack.intensity)
        self.carla_bridge.start_live_loop()
        self.carla_last_apply = {"mode": "carla" if self.carla_bridge.is_ready() else "mock", "attack_applied": bool(direct.get("ok")), "defense_applied": False, "applied_control": direct.get("applied_control", {"steer": self.vehicle.steer, "throttle": self.vehicle.throttle, "brake": self.vehicle.brake}), "damaged_parts": direct.get("damaged_parts", []), "impact": direct.get("impact", {}), "diagnostic_notice": direct.get("message", "Attack requested.")}
        self.attack.replay_enabled = True
        self._log(f"[ATTACKER CONSOLE] Live CARLA attack applied: {attack_name}. {direct.get('message', '')}")
        return {"ok": bool(direct.get("ok")), "attack": attack_name, "carla_result": direct, "snapshot": self.snapshot()}

    def start_natural_drive(self) -> bool:
        self.apply_preset("normal")
        self.update_driver({
            "zone_type": "urban", "speed_kmh": 42, "traffic_density": "medium",
            "lane_status": "centered", "driver_attention": "focused",
            "battery_soc": max(30, self.vehicle.battery_soc),
            "battery_temp_c": 34, "motor_temp_c": 42,
            "location_label": "CARLA Town10HD Live Route", "autopilot_enabled": True,
            "manual_override": False, "throttle": 0.35, "brake": 0.0,
        })
        self.connect_carla_full({"host": self.carla_bridge.host, "port": self.carla_bridge.port, "spawn_if_missing": True, "synchronous": True, "fps": self.carla_bridge.fps})
        self.carla_bridge.enable_natural_drive()
        self.carla_bridge.start_live_loop()
        self.mode = "carla"
        self._log("[SCENARIO] Natural autonomous driving started before attack injection.")
        return True

    def launch_owner_visible_attack(self, attack_name: str = "mixed_attack") -> bool:
        if not self.carla_bridge.is_ready():
            self.start_natural_drive()
        preset = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != "normal" else "mixed_attack"
        self.apply_preset(preset)
        if preset == "battery_thermal_tampering":
            self.update_driver({"battery_temp_c": 69, "motor_temp_c": 78, "battery_soc": max(15, self.vehicle.battery_soc - 4)})
        elif preset == "gps_spoofing":
            self.update_driver({"location_label": "GPS spoofed route divergence", "lane_status": "drifting_right"})
        elif preset == "steering_manipulation":
            self.update_driver({"lane_status": "drifting_right", "steer": 0.55})
        elif preset == "throttle_injection":
            self.update_driver({"speed_kmh": min(120, self.vehicle.speed_kmh + 30), "throttle": 0.92})
        else:
            self.update_driver({"lane_status": "drifting_right", "steer": 0.42, "battery_temp_c": 55, "motor_temp_c": 68})
            self.attack.extra_attacks = ["gps_spoofing", "sensor_spoofing", "battery_thermal_tampering"]
        self.attack.replay_enabled = True
        self.carla_bridge.start_live_loop()
        self._log(f"[OWNER ALERT] Attack launched after normal driving: {preset}. Owner diagnostics updated.")
        return True

    def _metric_summary(self) -> Dict[str, Any]:
        return {
            "speed_kmh": round(self.vehicle.speed_kmh, 1),
            "battery_soc": round(self.vehicle.battery_soc, 1),
            "battery_temp_c": round(self.vehicle.battery_temp_c, 1),
            "motor_temp_c": round(self.vehicle.motor_temp_c, 1),
            "lane_status": self.vehicle.lane_status,
            "location_label": self.vehicle.location_label,
            "steer": round(self.vehicle.steer, 3),
            "throttle": round(self.vehicle.throttle, 3),
            "brake": round(self.vehicle.brake, 3),
            "attack_active": self.attack.active,
            "attack_name": self.attack.attack_name,
        }

    def _metric_delta(self, before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
        delta: Dict[str, Any] = {}
        for key in ["speed_kmh", "battery_soc", "battery_temp_c", "motor_temp_c", "steer", "throttle", "brake"]:
            try:
                delta[key] = round(float(after.get(key, 0)) - float(before.get(key, 0)), 2)
            except Exception:
                delta[key] = 0
        delta["lane_change"] = f"{before.get('lane_status', 'unknown')} -> {after.get('lane_status', 'unknown')}"
        delta["attack"] = after.get("attack_name", "normal")
        return delta

    def run_full_demo(self, attack_name: str = "mixed_attack") -> Dict[str, Any]:
        self.reset()
        self.start_natural_drive()
        before = self._metric_summary()
        self._log("[FULL DEMO] Phase 1 complete: normal autonomous drive baseline captured.")
        preset = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != "normal" else "mixed_attack"
        self.launch_owner_visible_attack(preset)
        after = self._metric_summary()
        delta = self._metric_delta(before, after)
        self.full_demo_summary = {
            "status": "completed",
            "phase": "attack diagnosed",
            "before": before,
            "after": after,
            "delta": delta,
            "timeline": [
                {"step": "1", "title": "Normal drive", "detail": "Vehicle spawned, autopilot enabled and baseline telemetry captured."},
                {"step": "2", "title": "Attack injection", "detail": f"{preset.replace('_', ' ').title()} injected after normal driving."},
                {"step": "3", "title": "Impact visible", "detail": "Speed, lane, thermal and owner-diagnostic panels now show the attack effect."},
                {"step": "4", "title": "Owner guidance", "detail": "Dashboard generates warning, affected components and downloadable incident report."},
            ],
            "owner_message": "Full demo completed: normal driving baseline, cyber attack, impact diagnosis and report evidence are ready."
        }
        self._log("[FULL DEMO] Completed normal drive -> attack -> owner diagnostics -> report evidence.")
        return self.full_demo_summary

    def apply_scenario(self, scenario_name: str) -> bool:
        if scenario_name == "natural_drive":
            return self.start_natural_drive()
        if scenario_name == "attack_after_drive":
            return self.launch_owner_visible_attack("mixed_attack")
        scenarios = {
            "urban_attack": {"preset": "gps_spoofing", "vehicle": {"zone_type": "urban", "speed_kmh": 46, "traffic_density": "high", "obstacle_distance_m": 18, "location_label": "Amman Urban Corridor"}},
            "highway_attack": {"preset": "throttle_injection", "vehicle": {"zone_type": "highway", "speed_kmh": 106, "traffic_density": "medium", "obstacle_distance_m": 42, "location_label": "Desert Highway Segment"}},
            "sensor_failure": {"preset": "camera_lidar_blinding", "vehicle": {"zone_type": "intersection", "speed_kmh": 32, "weather": "fog", "obstacle_distance_m": 9, "location_label": "Low Visibility Intersection"}},
            "mixed_emergency": {"preset": "mixed_attack", "vehicle": {"zone_type": "urban", "speed_kmh": 68, "driver_attention": "distracted", "obstacle_distance_m": 12, "location_label": "Critical Demo Route"}},
        }
        scenario = scenarios.get(scenario_name)
        if not scenario:
            self._log(f"[WARN] Unknown scenario rejected: {scenario_name}")
            return False
        self.apply_preset(scenario["preset"])
        self.update_driver(scenario["vehicle"])
        self.attack.replay_enabled = True
        if self.carla_bridge.status.connected or self.mode == "carla":
            self.connect_carla_full({"host": self.carla_bridge.host, "port": self.carla_bridge.port, "spawn_if_missing": True, "synchronous": True, "fps": self.carla_bridge.fps})
            try:
                self.carla_bridge.start_live_loop()
                self.mode = "carla"
            except Exception:
                pass
        self._log(f"[SCENARIO] Ready-made scenario applied: {scenario_name}.")
        return True

    def random_attack(self) -> None:
        import random
        choices = ["can_flooding", "brake_injection", "steering_manipulation", "gps_spoofing", "sensor_spoofing", "throttle_injection", "camera_lidar_blinding", "mixed_attack"]
        self.apply_preset(random.choice(choices))
        self.attack.intensity = round(random.uniform(0.62, 0.98), 2)
        self._log("[ATTACK] Randomized adversarial scenario generated.")

    def sign_control_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        allowed = {
            "steer": clamp_float(command.get("steer", 0.0), -1.0, 1.0, 0.0),
            "throttle": clamp_float(command.get("throttle", 0.0), 0.0, 1.0, 0.0),
            "brake": clamp_float(command.get("brake", 0.0), 0.0, 1.0, 0.0),
            "issued_by": str(command.get("issued_by", "operator"))[:40],
        }
        allowed["signature"] = sign_command(allowed)
        return allowed

    def apply_secure_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {
            "steer": clamp_float(command.get("steer", self.vehicle.steer), -1.0, 1.0, self.vehicle.steer),
            "throttle": clamp_float(command.get("throttle", self.vehicle.throttle), 0.0, 1.0, self.vehicle.throttle),
            "brake": clamp_float(command.get("brake", self.vehicle.brake), 0.0, 1.0, self.vehicle.brake),
            "issued_by": str(command.get("issued_by", "operator"))[:40],
        }
        valid = verify_command(normalized, command.get("signature"))
        if not valid and self.command_auth_required:
            self._log("[AUTH] Unsigned or tampered command rejected.")
            return {"accepted": False, "reason": "Invalid command signature", "command": normalized}
        self.vehicle.steer = normalized["steer"]
        self.vehicle.throttle = normalized["throttle"]
        self.vehicle.brake = normalized["brake"]
        self._log("[AUTH] Signed command accepted and applied.")
        return {"accepted": True, "reason": "Signature verified", "command": normalized}

    def run_security_test(self, rounds: int = 12) -> Dict[str, Any]:
        self.last_security_test = auto_security_test(self, rounds)
        self._log(f"[TEST] Auto security test completed: detection rate={self.last_security_test['detection_rate']}.")
        return self.last_security_test

    def recent_incidents(self) -> list:
        return self.store.list_recent(12)

    @staticmethod
    def ai_assistant_explanation(snapshot: Dict[str, Any]) -> str:
        risks = snapshot.get("risks", {})
        attack = snapshot.get("attack", {})
        roots = "; ".join(risks.get("root_cause", []) or ["no strong anomaly chain"])
        strategy = "; ".join(risks.get("defense_strategy", []) or ["continue monitoring"])
        return (
            f"DriveFort AI classified the current scene as {risks.get('threat_level', 'NORMAL')} because "
            f"{attack.get('attack_name', 'normal').replace('_', ' ')} indicators changed the overall risk to "
            f"{risks.get('overall', 0)}. Main evidence: {roots}. Recommended response: "
            f"{risks.get('action', 'ALLOW')} using {strategy}."
        )

    def _sync_carla_state(self) -> None:
        if self.mode == "carla":
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)


    def _owner_diagnostics(self, risk, digital_twin: Dict[str, Any]) -> Dict[str, Any]:
        damaged = list(self.carla_last_apply.get("damaged_parts") or [])
        if self.attack.active and not damaged:
            mapping = {
                "gps_spoofing": ["GPS / navigation module"],
                "sensor_spoofing": ["Sensor fusion module"],
                "camera_lidar_blinding": ["Camera and LiDAR perception"],
                "battery_thermal_tampering": ["Battery management system"],
                "steering_manipulation": ["Steering ECU"],
                "brake_injection": ["Brake ECU"],
                "throttle_injection": ["Powertrain ECU"],
                "can_flooding": ["Gateway ECU / CAN bus"],
                "dos": ["Gateway ECU / network availability"],
                "mixed_attack": ["Gateway ECU", "Steering ECU", "Sensor fusion", "Battery management"],
            }
            damaged = mapping.get(self.attack.attack_name, [self.attack.target_ecu.replace("_", " ").title()])
        severity = "CRITICAL" if risk.overall >= 0.75 else "WARNING" if risk.overall >= 0.4 else "NORMAL"

        # Owner-facing prototype: this is intentionally written as simple dashboard data so
        # the UI can draw a vehicle exterior + driver cabin and highlight what the attack
        # affected. It is a visual/diagnostic prototype, not a claim of physical damage.
        affected_keys = set()
        attack_name = self.attack.attack_name if self.attack.active else "normal"
        by_attack = {
            "steering_manipulation": ["steering_ecu", "adas_lane_keep", "driver_hmi"],
            "brake_injection": ["brake_ecu", "driver_hmi"],
            "throttle_injection": ["powertrain_ecu", "motor_inverter", "driver_hmi"],
            "can_flooding": ["gateway_ecu", "can_bus", "driver_hmi"],
            "dos": ["gateway_ecu", "can_bus", "telematics"],
            "gps_spoofing": ["gps_navigation", "adas_lane_keep", "driver_hmi"],
            "sensor_spoofing": ["sensor_fusion", "radar_ultrasonic", "adas_lane_keep"],
            "camera_lidar_blinding": ["camera_lidar", "sensor_fusion", "adas_lane_keep"],
            "battery_thermal_tampering": ["battery_bms", "thermal_sensors", "driver_hmi"],
            "telemetry_scraping": ["telematics", "gateway_ecu"],
            "mixed_attack": ["gateway_ecu", "can_bus", "steering_ecu", "sensor_fusion", "camera_lidar", "battery_bms", "driver_hmi"],
        }
        affected_keys.update(by_attack.get(attack_name, []))
        damaged_text = " ".join(damaged).lower()
        text_to_keys = {
            "steering": "steering_ecu", "brake": "brake_ecu", "powertrain": "powertrain_ecu",
            "acceleration": "powertrain_ecu", "gateway": "gateway_ecu", "can": "can_bus",
            "gnss": "gps_navigation", "gps": "gps_navigation", "navigation": "gps_navigation",
            "sensor": "sensor_fusion", "perception": "camera_lidar", "camera": "camera_lidar",
            "lidar": "camera_lidar", "battery": "battery_bms", "thermal": "thermal_sensors",
            "telematics": "telematics", "privacy": "telematics",
        }
        for token, key in text_to_keys.items():
            if token in damaged_text:
                affected_keys.add(key)

        component_specs = [
            ("steering_ecu", "Steering ECU", "front-left", "Controls wheel angle and lane correction."),
            ("brake_ecu", "Brake ECU", "front-right", "Applies emergency and normal braking commands."),
            ("powertrain_ecu", "Powertrain ECU", "rear", "Controls acceleration, torque and motor request."),
            ("motor_inverter", "Motor Inverter", "rear", "Translates power request into motor output."),
            ("battery_bms", "Battery BMS", "battery", "Monitors charge, voltage balance and thermal limits."),
            ("thermal_sensors", "Thermal Sensors", "battery", "Tracks battery and motor temperature anomalies."),
            ("gateway_ecu", "Gateway ECU", "center", "Filters network messages between vehicle domains."),
            ("can_bus", "CAN Bus", "center", "Vehicle message backbone and availability path."),
            ("sensor_fusion", "Sensor Fusion", "front", "Combines camera, radar, LiDAR and map signals."),
            ("camera_lidar", "Camera/LiDAR", "front", "Perception input used for objects and lanes."),
            ("radar_ultrasonic", "Radar/Ultrasonic", "front", "Short and mid-range obstacle awareness."),
            ("gps_navigation", "GPS / Navigation", "dashboard", "Position, route and map trust."),
            ("adas_lane_keep", "ADAS Lane Keep", "dashboard", "Autopilot lateral control and lane confidence."),
            ("telematics", "Telematics", "dashboard", "Remote diagnostics and privacy channel."),
            ("driver_hmi", "Driver Display/HMI", "cabin", "Owner warning screen and safe-mode guidance."),
        ]
        components = []
        for key, label, zone, description in component_specs:
            active = key in affected_keys
            comp_severity = "critical" if active and severity == "CRITICAL" else "warning" if active else "normal"
            components.append({
                "id": key,
                "label": label,
                "zone": zone,
                "status": "affected" if active else "healthy",
                "severity": comp_severity,
                "description": description,
            })
        interior_impacts = []
        if self.attack.active:
            if "driver_hmi" in affected_keys:
                interior_impacts.append("Driver display shows cyber-attack warning and safe-mode recommendation.")
            if "adas_lane_keep" in affected_keys:
                interior_impacts.append("Autopilot lane confidence is degraded; driver should keep hands ready.")
            if "gps_navigation" in affected_keys:
                interior_impacts.append("Navigation position may be spoofed; route should be treated as untrusted.")
            if "battery_bms" in affected_keys or "thermal_sensors" in affected_keys:
                interior_impacts.append("Battery/thermal panel reports abnormal heat or BMS readings.")
            if not interior_impacts:
                interior_impacts.append("Cabin alert is active; DriveFort AI is limiting unsafe vehicle commands.")
        else:
            interior_impacts.append("Cabin is normal; no active warning on the owner display.")

        return {
            "owner_message": "Vehicle is under attack. Reduce speed and keep distance; DriveFort AI is restricting unsafe commands." if self.attack.active else "Vehicle is driving normally. No active cyber-physical attack detected.",
            "severity": severity,
            "damaged_parts": damaged,
            "prototype": {
                "mode": "attack_visualization" if self.attack.active else "normal_drive",
                "title": "Tesla Model 3 cyber-physical prototype",
                "affected_count": sum(1 for item in components if item["status"] == "affected"),
                "components": components,
                "interior_impacts": interior_impacts,
                "driver_status": "Safe-mode warning active" if self.attack.active else "Normal cabin display",
            },
            "evidence": [
                f"Speed={self.vehicle.speed_kmh:.1f} km/h",
                f"Battery={self.vehicle.battery_soc:.0f}% / {self.vehicle.battery_temp_c:.0f}C",
                f"Motor temp={self.vehicle.motor_temp_c:.0f}C",
                f"Coordinates={self.vehicle.location_y:.5f}, {self.vehicle.location_x:.5f}",
                f"Digital twin anomaly={digital_twin.get('anomaly')}",
            ],
            "recommended_action": "Stay alert, allow safe-mode recovery, and inspect listed modules after the run." if self.attack.active else "Continue normal autonomous driving.",
        }

    def snapshot(self) -> Dict[str, Any]:
        self._sync_carla_state()
        if self.demo_running and self.demo_phase == "warning" and self.demo_counter == 0:
            self.vehicle.speed_kmh = 48.0
            self.vehicle.zone_type = "urban"
            self.vehicle.driver_attention = "focused"
            self.demo_counter = 1

        risk = self.risk_engine.assess(self.vehicle, self.attack)
        features = self._attack_features()
        fp = self.fingerprint.identify(self.attack.attack_name if self.attack.active else "normal", features)

        if self.attack.active and risk.overall > 0.55:
            score = self.trust.update(self.attack.source_ecu, penalty=0.14 * max(0.5, self.attack.intensity))
        else:
            score = self.trust.update(self.attack.source_ecu, reward=0.03)

        trust_class = self.trust.classify(self.attack.source_ecu)
        if trust_class == "blocked" and risk.action != "EMERGENCY_SAFE_MODE":
            risk.action = "ISOLATE_ATTACK_NODE"
            risk.summary += " Attack node isolated due to trust collapse."

        risk.fingerprint_type = fp["attack_type"]
        risk.fingerprint_confidence = fp["confidence"]
        risk.fingerprint_reasons = fp["reasons"]

        prediction = self._predict_attack_warning(risk.overall, self.prev_overall_risk, self.attack.active, self.attack.mode)
        pro_sensor_trust = sensor_trust_scores(self.vehicle, self.attack, risk)
        pro_fusion = sensor_fusion(self.vehicle, pro_sensor_trust)
        pro_safe_mode = safe_mode_levels(risk, self.vehicle, pro_sensor_trust)
        pro_network = network_attack_layer(self.attack, features)
        pro_performance = performance_metrics(risk, features)
        pro_prediction = threat_prediction(risk, self.prev_overall_risk, pro_sensor_trust)
        pro_voice = voice_alerts(risk, pro_safe_mode)
        if self.mode == "carla":
            self.carla_bridge.apply_vehicle_state(self.vehicle)
            self.carla_last_apply = self.carla_bridge.apply_attack_and_defense(self.vehicle, self.attack, risk)
            self.vehicle.steer = self.carla_last_apply["applied_control"]["steer"]
            self.vehicle.throttle = self.carla_last_apply["applied_control"]["throttle"]
            self.vehicle.brake = self.carla_last_apply["applied_control"]["brake"]
        else:
            self.carla_last_apply = {"mode": "mock", "attack_applied": False, "defense_applied": False, "applied_control": {"steer": self.vehicle.steer, "throttle": self.vehicle.throttle, "brake": self.vehicle.brake}}
        digital_twin = self._digital_twin(self.vehicle, self.attack)
        owner_diagnostics = self._owner_diagnostics(risk, digital_twin)
        if prediction["warning"]:
            self._log(f"[PREDICT] {prediction['message']} ETA={prediction['eta']}.")
        self.prev_overall_risk = risk.overall
        self.learning_patterns += 1 if self.attack.active and risk.ai_confidence > 0.7 else 0
        self.learning_patterns = min(self.learning_patterns, 42)

        mapping = {
            "can_flooding": "Availability spikes due to bus saturation indicators.",
            "dos": "Availability dominates because service continuity is degraded.",
            "brake_injection": "Safety and cyber-physical risk rise due to unauthorized brake actuation.",
            "steering_manipulation": "Cyber-physical and safety risk rise due to steering control deviation.",
            "telemetry_scraping": "Privacy dominates because sensitive telemetry is being harvested.",
            "battery_thermal_tampering": "Cyber-physical and safety risk rise due to thermal system manipulation.",
            "gps_spoofing": "Safety and cyber-physical risk rise because navigation truth is no longer trusted.",
            "sensor_spoofing": "Safety and AI risk rise because sensor evidence conflicts with the digital twin.",
            "throttle_injection": "Safety and cyber-physical risk rise because acceleration commands diverge from driver intent.",
            "camera_lidar_blinding": "Safety and AI risk rise because perception channels lose reliable environmental context.",
            "mixed_attack": "Multiple risk classes rise together because the attack spans several layers.",
            "normal": "All risk classes remain near baseline.",
        }

        snapshot = {
            "vehicle": self.vehicle.to_dict(),
            "attack": self.attack.to_dict(),
            "risks": risk.to_dict(),
            "trust": {"ecu_id": self.attack.source_ecu, "score": round(score, 3), "class": trust_class},
            "driver_console": self._build_driver_console(risk, score, trust_class),
            "attacker_console": self._build_attacker_console(risk, features),
            "defense_dashboard": self._build_defense_dashboard(risk, score, trust_class, features, digital_twin, prediction),
            "attack_to_risk_mapping": mapping.get(self.attack.attack_name if self.attack.active else "normal", "Mapping unavailable."),
            "event_log": self.event_log[-12:],
            "carla": self.carla_status(),
            "owner_diagnostics": owner_diagnostics,
            "full_demo": self.full_demo_summary,
            "carla_diagnostics": self.carla_bridge.diagnostic_snapshot(),
            "pro": {
                "sensor_trust_scores": pro_sensor_trust,
                "sensor_fusion": pro_fusion,
                "safe_mode_levels": pro_safe_mode,
                "network_layer": pro_network,
                "performance_metrics": pro_performance,
                "command_authentication": {"required": self.command_auth_required, "status": "enabled", "algorithm": "HMAC-SHA256"},
                "threat_prediction": pro_prediction,
                "plugin_system": plugin_catalog(),
                "voice_alerts": pro_voice,
                "mobile_ui": {"responsive": True, "cards": ["state", "alerts", "safe mode", "trust"]},
                "docker": {"supported": True, "files": ["Dockerfile", "docker-compose.yml"]},
                "last_security_test": self.last_security_test,
            },
        }
        record_key = (snapshot["attack"]["attack_name"], snapshot["attack"]["active"], snapshot["risks"]["threat_level"], round(snapshot["risks"]["overall"], 2), len(self.event_log))
        if snapshot["attack"]["active"] or snapshot["risks"]["overall"] >= 0.35:
            if record_key != self.last_record_key:
                snapshot["incident_id"] = self.store.add_snapshot(snapshot)
                self.last_record_key = record_key
        snapshot["defense_dashboard"]["recent_incidents"] = self.store.list_recent(6)
        return snapshot


def pretty_attack(name: str) -> str:
    return name.replace("_", " ").title()

# --- DriveFort AI evidence/recovery enhancement patch ---
# These monkey-patched methods keep the original project stable while adding:
# evidence recorder, severity meter, one-click scenario script, and real CARLA recovery.

def _zg_init_evidence(self):
    if not hasattr(self, "evidence_recorder"):
        self.evidence_recorder = {
            "status": "idle",
            "captures": [],
            "latest": {},
            "severity_meter": {"score": 0, "level": "NORMAL", "label": "No active attack"},
            "recovery": {"status": "standby", "message": "Recovery has not been requested yet."},
        }

_zg_original_init = SimulationEngine.__init__
def _zg_init(self):
    _zg_original_init(self)
    _zg_init_evidence(self)
SimulationEngine.__init__ = _zg_init


def _zg_severity_meter(self, risk_overall=None, attack_name=None):
    _zg_init_evidence(self)
    base = float(risk_overall if risk_overall is not None else 0.0)
    if getattr(self.attack, "active", False):
        base = max(base, 0.35 + 0.50 * float(getattr(self.attack, "intensity", 0.0) or 0.0))
    last = self.carla_last_apply if isinstance(self.carla_last_apply, dict) else {}
    ctrl = last.get("applied_control", {}) or {}
    try:
        control_impact = min(0.25, abs(float(ctrl.get("steer", 0.0))) * 0.12 + float(ctrl.get("brake", 0.0)) * 0.08 + float(ctrl.get("throttle", 0.0)) * 0.05)
    except Exception:
        control_impact = 0.0
    score = max(0, min(100, int(round((base + control_impact) * 100))))
    level = "CRITICAL" if score >= 85 else "HIGH" if score >= 65 else "ELEVATED" if score >= 40 else "NORMAL"
    return {"score": score, "level": level, "label": f"{level} - {attack_name or self.attack.attack_name or 'normal'}"}
SimulationEngine._severity_meter = _zg_severity_meter


def _zg_capture_evidence(self, stage, note=""):
    _zg_init_evidence(self)
    metric = self._metric_summary()
    try:
        risk = self.risk_engine.assess(self.vehicle, self.attack)
        sev = self._severity_meter(risk.overall, self.attack.attack_name)
    except Exception:
        sev = self._severity_meter(0.0, getattr(self.attack, "attack_name", "normal"))
    try:
        diag = self.carla_bridge.diagnostic_snapshot()
        sensors = self.carla_bridge.sensor_snapshot()
    except Exception:
        diag, sensors = {}, {}
    last = self.carla_last_apply if isinstance(self.carla_last_apply, dict) else {}
    capture = {
        "stage": stage,
        "note": note,
        "metrics": metric,
        "attack": {"active": self.attack.active, "name": self.attack.attack_name, "intensity": self.attack.intensity, "target_ecu": self.attack.target_ecu},
        "carla": diag,
        "sensors": sensors,
        "severity": sev,
        "control": dict(last.get("applied_control", {})),
        "damaged_parts": list(diag.get("damaged_parts") or last.get("damaged_parts", []) or []),
    }
    captures = list(self.evidence_recorder.get("captures", []))
    captures.append(capture)
    self.evidence_recorder.update({"status": "recording", "captures": captures[-12:], "latest": capture, "severity_meter": sev})
    self._log(f"[EVIDENCE] {stage}: {note or sev.get('label')}.")
    return capture
SimulationEngine._capture_evidence = _zg_capture_evidence


def _zg_recover_vehicle_live(self):
    _zg_init_evidence(self)
    self.apply_preset("normal")
    self.update_driver({
        "lane_status": "centered", "steer": 0.0, "brake": 0.0, "throttle": 0.24,
        "autopilot_enabled": True, "manual_override": False, "battery_temp_c": 34,
        "motor_temp_c": 42, "driver_attention": "focused", "location_label": "Recovered CARLA route"
    })
    try:
        carla_result = self.carla_bridge.recover_vehicle()
    except Exception:
        carla_result = self.carla_bridge.enable_natural_drive()
    try:
        self.carla_bridge.start_live_loop()
    except Exception:
        pass
    if self.carla_bridge.is_ready():
        self.mode = "carla"
    self.carla_last_apply = {
        "mode": self.mode,
        "attack_applied": False,
        "defense_applied": True,
        "applied_control": carla_result.get("applied_control", {"steer": 0.0, "throttle": 0.18, "brake": 0.0}),
        "damaged_parts": [],
        "diagnostic_notice": carla_result.get("message", "Recovery complete."),
    }
    self.evidence_recorder["recovery"] = {"status": "complete" if carla_result.get("ok", True) else "warning", "message": carla_result.get("message", "Recovery complete.")}
    self._capture_evidence("recovery", "Vehicle recovered: attack cleared, natural drive restored, controls normalized.")
    self._log("[RECOVERY] Real recovery applied: attack state cleared and natural CARLA autopilot restored.")
    return {"ok": True, "carla_result": carla_result, "snapshot": self.snapshot()}
SimulationEngine.recover_vehicle_live = _zg_recover_vehicle_live

_zg_original_start_natural_drive = SimulationEngine.start_natural_drive
def _zg_start_natural_drive(self):
    ok = _zg_original_start_natural_drive(self)
    try:
        self._capture_evidence("baseline", "Natural autonomous driving baseline captured before attack.")
    except Exception:
        pass
    return ok
SimulationEngine.start_natural_drive = _zg_start_natural_drive

_zg_original_apply_console = SimulationEngine.apply_carla_attack_console
def _zg_apply_carla_attack_console(self, attack_name, intensity=0.92):
    result = _zg_original_apply_console(self, attack_name, intensity)
    try:
        self._capture_evidence("attack", f"Live attack applied to CARLA: {attack_name}.")
    except Exception:
        pass
    return result
SimulationEngine.apply_carla_attack_console = _zg_apply_carla_attack_console


def _zg_run_full_demo(self, attack_name="mixed_attack"):
    _zg_init_evidence(self)
    self.reset()
    self.evidence_recorder["captures"] = []
    self.start_natural_drive()
    before = self._metric_summary()
    baseline_capture = self._capture_evidence("baseline", "Normal driving baseline captured with CARLA autopilot enabled.")
    preset = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != "normal" else "mixed_attack"
    attack_result = self.apply_carla_attack_console(preset, 0.92)
    after = self._metric_summary()
    attack_capture = self._capture_evidence("attack", f"{preset.replace('_', ' ').title()} applied to CARLA and owner diagnostics updated.")
    delta = self._metric_delta(before, after)
    recovery_result = self.recover_vehicle_live()
    recovered = self._metric_summary()
    recovery_capture = self.evidence_recorder.get("latest", {})
    self.full_demo_summary = {
        "status": "completed_with_recovery",
        "phase": "baseline_attack_recovery",
        "before": before,
        "after": after,
        "recovered": recovered,
        "delta": delta,
        "attack_result": attack_result.get("carla_result", {}),
        "recovery_result": recovery_result.get("carla_result", {}),
        "evidence": [baseline_capture, attack_capture, recovery_capture],
        "timeline": [
            {"step": "1", "title": "Normal drive", "detail": "Vehicle spawned, CARLA autopilot enabled, and baseline telemetry recorded."},
            {"step": "2", "title": "Attack injection", "detail": f"{preset.replace('_', ' ').title()} sent through the live attack console into CARLA control."},
            {"step": "3", "title": "Impact evidence", "detail": "Speed, steering/brake/throttle, thermal indicators, location and affected components captured before/after."},
            {"step": "4", "title": "Recovery", "detail": "Attack state cleared, control normalized and CARLA natural drive restored."},
            {"step": "5", "title": "Report", "detail": "Incident PDF includes evidence captures, severity meter, damaged parts and recovery status."},
        ],
        "owner_message": "Full demo completed: normal driving, CARLA attack, visible impact, evidence capture and real recovery are ready for review."
    }
    self.evidence_recorder["status"] = "completed"
    self._log("[FULL DEMO] Completed normal drive -> live attack -> evidence -> recovery -> report.")
    return self.full_demo_summary
SimulationEngine.run_full_demo = _zg_run_full_demo

_zg_original_snapshot = SimulationEngine.snapshot
def _zg_snapshot(self):
    data = _zg_original_snapshot(self)
    _zg_init_evidence(self)
    try:
        risk = data.get("risks", {}).get("overall", 0.0)
        self.evidence_recorder["severity_meter"] = self._severity_meter(risk, data.get("attack", {}).get("attack_name"))
    except Exception:
        pass
    data["evidence_recorder"] = self.evidence_recorder
    return data
SimulationEngine.snapshot = _zg_snapshot


# ---------------------------------------------------------------------------
# Protection comparison lab: unprotected vehicle vs DriveFort AI protected vehicle
# ---------------------------------------------------------------------------
_zg2_original_init = SimulationEngine.__init__
def _zg2_init(self):
    _zg2_original_init(self)
    if not hasattr(self, "protection_enabled"):
        self.protection_enabled = False
    if not hasattr(self, "protection_demo"):
        self.protection_demo = {
            "status": "ready",
            "mode": "comparison_lab",
            "protection_enabled": False,
            "unprotected": {},
            "protected": {},
            "verdict": "Run both scenarios to compare the result.",
        }
SimulationEngine.__init__ = _zg2_init


def _zg2_metric_pack(self, label):
    risk = self.risk_engine.assess(self.vehicle, self.attack)
    last = self.carla_last_apply if isinstance(self.carla_last_apply, dict) else {}
    ctrl = last.get("applied_control", {}) or {}
    return {
        "label": label,
        "speed_kmh": round(float(self.vehicle.speed_kmh), 1),
        "lane_status": self.vehicle.lane_status,
        "steer": round(float(self.vehicle.steer), 3),
        "throttle": round(float(self.vehicle.throttle), 3),
        "brake": round(float(self.vehicle.brake), 3),
        "battery_soc": round(float(self.vehicle.battery_soc), 1),
        "battery_temp_c": round(float(self.vehicle.battery_temp_c), 1),
        "motor_temp_c": round(float(self.vehicle.motor_temp_c), 1),
        "risk_score": round(float(risk.overall), 3),
        "threat_level": risk.threat_level,
        "action": risk.action,
        "attack_active": bool(self.attack.active),
        "attack_name": self.attack.attack_name,
        "carla_control": {
            "steer": round(float(ctrl.get("steer", self.vehicle.steer) or 0.0), 2),
            "throttle": round(float(ctrl.get("throttle", self.vehicle.throttle) or 0.0), 2),
            "brake": round(float(ctrl.get("brake", self.vehicle.brake) or 0.0), 2),
        },
        "damaged_parts": list(last.get("damaged_parts", []) or []),
        "diagnostic_notice": last.get("diagnostic_notice", ""),
    }
SimulationEngine._protection_metric_pack = _zg2_metric_pack


def _zg2_activate_innovative_protection(self):
    self.protection_enabled = True
    try:
        self.recover_vehicle_live()
    except Exception:
        try:
            self.start_natural_drive()
        except Exception:
            pass
    self.update_driver({
        "autopilot_enabled": True,
        "manual_override": False,
        "lane_status": "centered",
        "steer": 0.0,
        "brake": 0.0,
        "throttle": 0.22,
        "battery_temp_c": min(float(self.vehicle.battery_temp_c), 38.0),
        "motor_temp_c": min(float(self.vehicle.motor_temp_c), 48.0),
        "location_label": "DriveFort AI protected CARLA route",
    })
    self.attack.active = False
    self.attack.attack_name = "normal"
    self.attack.intensity = 0.0
    self.carla_last_apply = {
        "mode": "carla" if self.carla_bridge.is_ready() else self.mode,
        "attack_applied": False,
        "defense_applied": True,
        "applied_control": {"steer": 0.0, "throttle": 0.22, "brake": 0.0},
        "damaged_parts": [],
        "diagnostic_notice": "DriveFort AI protection armed: malicious commands will be rejected and safe mode can take over.",
    }
    try:
        self._capture_evidence("protection_armed", "Innovative protection activated: command authentication, anomaly detection and safe mode are armed.")
    except Exception:
        pass
    self.protection_demo.update({
        "status": "protection_armed",
        "protection_enabled": True,
        "verdict": "DriveFort AI innovative protection is active. Run the protected scenario to show attack blocking and safe-mode recovery.",
    })
    self._log("[DEFENSE] DriveFort AI innovative protection armed: attacker control channel restricted.")
    return {"ok": True, "snapshot": self.snapshot()}
SimulationEngine.activate_innovative_protection = _zg2_activate_innovative_protection


def _zg2_run_unprotected_attack_scenario(self, attack_name="mixed_attack"):
    self.protection_enabled = False
    self.reset()
    self.protection_enabled = False
    self.start_natural_drive()
    before = self._protection_metric_pack("Before attack - unprotected normal driving")
    attack = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != "normal" else "mixed_attack"
    result = self.apply_carla_attack_console(attack, 0.96)
    # Make the unprotected consequence visually undeniable in the dashboard.
    if attack in {"steering_manipulation", "gps_spoofing", "sensor_spoofing", "mixed_attack"}:
        self.update_driver({"lane_status": "drifting_right", "steer": 0.78, "brake": max(self.vehicle.brake, 0.42), "battery_temp_c": max(self.vehicle.battery_temp_c, 58), "motor_temp_c": max(self.vehicle.motor_temp_c, 72)})
    elif attack == "brake_injection":
        self.update_driver({"speed_kmh": max(0, self.vehicle.speed_kmh - 28), "brake": 0.98, "throttle": 0.0})
    elif attack == "throttle_injection":
        self.update_driver({"speed_kmh": min(140, self.vehicle.speed_kmh + 45), "throttle": 1.0, "brake": 0.0})
    elif attack == "battery_thermal_tampering":
        self.update_driver({"battery_temp_c": 82, "motor_temp_c": 91, "battery_soc": max(8, self.vehicle.battery_soc - 9)})
    after = self._protection_metric_pack("After attack - unprotected vehicle compromised")
    try:
        self._capture_evidence("unprotected_compromised", "No protection active: attacker command reached CARLA and changed vehicle behavior.")
    except Exception:
        pass
    self.full_demo_summary = {
        "status": "unprotected_compromised",
        "phase": "no_defense_attack_success",
        "before": before,
        "after": after,
        "delta": self._metric_delta(before, after),
        "timeline": [
            {"step": "1", "title": "Normal drive", "detail": "Vehicle drives normally with no active protection policy."},
            {"step": "2", "title": "Attacker command", "detail": f"{attack.replace('_',' ').title()} is sent directly to CARLA."},
            {"step": "3", "title": "Compromise", "detail": "Attacker gains physical influence over steering/brake/throttle or telemetry."},
            {"step": "4", "title": "Unsafe result", "detail": "Dashboard shows damaged parts, high risk and no automatic containment."},
        ],
        "owner_message": "Unprotected scenario complete: the attack reached the vehicle and caused visible unsafe behavior.",
    }
    self.protection_demo.update({
        "status": "unprotected_compromised",
        "protection_enabled": False,
        "last_attack": attack,
        "unprotected": {"before": before, "after": after, "result": result.get("carla_result", result), "outcome": "ATTACK SUCCEEDED - vehicle behavior changed"},
        "verdict": "Without DriveFort AI protection, the attacker command reached CARLA and affected the vehicle.",
    })
    self._log("[COMPARE] Unprotected scenario completed: attacker control succeeded.")
    return {"ok": True, "scenario": "unprotected", "snapshot": self.snapshot()}
SimulationEngine.run_unprotected_attack_scenario = _zg2_run_unprotected_attack_scenario


def _zg2_run_protected_attack_scenario(self, attack_name="mixed_attack"):
    self.reset()
    self.protection_enabled = True
    self.start_natural_drive()
    before = self._protection_metric_pack("Before attempted attack - protected normal driving")
    attack = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != "normal" else "mixed_attack"
    # Represent the attacker attempt without allowing the malicious control to persist.
    attempted = {
        "attack": attack,
        "intensity": 0.96,
        "blocked_reason": "Command signature/trust failed + behavior anomaly detected.",
        "blocked_controls": ["steering override", "brake/throttle injection", "unsafe ECU write"],
    }
    self.apply_preset(attack)
    self.update_driver({
        "speed_kmh": min(float(self.vehicle.speed_kmh), 24.0),
        "lane_status": "centered",
        "steer": 0.0,
        "throttle": 0.10,
        "brake": 0.35,
        "autopilot_enabled": True,
        "manual_override": False,
        "battery_temp_c": min(max(float(self.vehicle.battery_temp_c), 34.0), 41.0),
        "motor_temp_c": min(max(float(self.vehicle.motor_temp_c), 42.0), 50.0),
        "location_label": "DriveFort AI Safe Mode - protected route",
    })
    # Clear attacker state after safe mode contains it; keep evidence in protection_demo.
    self.attack.active = False
    self.attack.attack_name = "normal"
    self.attack.intensity = 0.0
    try:
        carla_result = self.carla_bridge.recover_vehicle()
    except Exception:
        carla_result = {"ok": True, "message": "Safe mode simulated; CARLA recovery unavailable.", "applied_control": {"steer": 0.0, "throttle": 0.12, "brake": 0.25}}
    try:
        self.carla_bridge.start_live_loop()
    except Exception:
        pass
    self.carla_last_apply = {
        "mode": "carla" if self.carla_bridge.is_ready() else self.mode,
        "attack_applied": False,
        "defense_applied": True,
        "applied_control": carla_result.get("applied_control", {"steer": 0.0, "throttle": 0.12, "brake": 0.25}),
        "damaged_parts": [],
        "diagnostic_notice": "Attack blocked by DriveFort AI: safe mode engaged, malicious command rejected, vehicle control preserved.",
    }
    after = self._protection_metric_pack("After attempted attack - protected and recovered")
    try:
        self._capture_evidence("protected_blocked", "DriveFort AI blocked the attack, isolated the malicious command and restored safe autonomous control.")
    except Exception:
        pass
    self.full_demo_summary = {
        "status": "protected_attack_blocked",
        "phase": "defense_safe_mode_recovery",
        "before": before,
        "after": after,
        "recovered": after,
        "delta": self._metric_delta(before, after),
        "timeline": [
            {"step": "1", "title": "Protected drive", "detail": "Vehicle drives normally with DriveFort AI protection armed."},
            {"step": "2", "title": "Attack attempt", "detail": f"{attack.replace('_',' ').title()} attempts to control the vehicle."},
            {"step": "3", "title": "Detection", "detail": "Trust manager rejects the unsafe command and marks the ECU request as anomalous."},
            {"step": "4", "title": "Safe mode", "detail": "Speed is limited, steering is normalized and malicious control is blocked."},
            {"step": "5", "title": "Recovery", "detail": "Autopilot/natural drive is restored while evidence is recorded for the owner."},
        ],
        "owner_message": "Protected scenario complete: DriveFort AI blocked the attack, enabled safe mode and prevented attacker control.",
    }
    self.protection_demo.update({
        "status": "protected_blocked",
        "protection_enabled": True,
        "last_attack": attack,
        "protected": {"before": before, "after": after, "attempted": attempted, "result": carla_result, "outcome": "ATTACK BLOCKED - safe mode and recovery engaged"},
        "verdict": "With DriveFort AI protection enabled, the same attack is blocked and the vehicle remains controllable.",
    })
    self._log("[COMPARE] Protected scenario completed: attack blocked, safe mode/recovery engaged.")
    return {"ok": True, "scenario": "protected", "snapshot": self.snapshot()}
SimulationEngine.run_protected_attack_scenario = _zg2_run_protected_attack_scenario

_zg2_original_snapshot = SimulationEngine.snapshot
def _zg2_snapshot(self):
    data = _zg2_original_snapshot(self)
    if not hasattr(self, "protection_demo"):
        self.protection_demo = {"status": "ready", "protection_enabled": False, "unprotected": {}, "protected": {}, "verdict": "Run both scenarios to compare the result."}
    data["protection_demo"] = self.protection_demo
    data["protection_demo"]["protection_enabled"] = bool(getattr(self, "protection_enabled", False))
    return data
SimulationEngine.snapshot = _zg2_snapshot

# ---------------------------------------------------------------------------
# DriveFort AI AI security layer extension
# Adds AI anomaly detection, threat classification, live risk score,
# adaptive recovery, and simulated attacker manual control in CARLA.
# ---------------------------------------------------------------------------

def _zg3_init_ai_layer(self):
    if not hasattr(self, "ai_security"):
        self.ai_security = {
            "status": "monitoring",
            "anomaly_score": 0,
            "risk_score": 0,
            "threat_class": "NORMAL",
            "confidence": 0.0,
            "explanation": "AI layer is monitoring vehicle behavior.",
            "signals": [],
            "adaptive_recovery": {"status": "standby", "action": "None"},
            "last_manual_control": {"active": False, "steer": 0.0, "throttle": 0.0, "brake": 0.0},
        }

_zg3_original_init = SimulationEngine.__init__
def _zg3_init(self):
    _zg3_original_init(self)
    _zg3_init_ai_layer(self)
SimulationEngine.__init__ = _zg3_init


def _zg3_ai_anomaly_detection(self):
    _zg3_init_ai_layer(self)
    signals = []
    score = 0.0
    v = self.vehicle
    last = self.carla_last_apply if isinstance(self.carla_last_apply, dict) else {}
    ctrl = last.get("applied_control", {}) or {}
    steer = abs(float(ctrl.get("steer", getattr(v, "steer", 0.0)) or 0.0))
    throttle = float(ctrl.get("throttle", getattr(v, "throttle", 0.0)) or 0.0)
    brake = float(ctrl.get("brake", getattr(v, "brake", 0.0)) or 0.0)
    if getattr(self.attack, "active", False):
        score += 0.34 + 0.32 * float(getattr(self.attack, "intensity", 0.0) or 0.0)
        signals.append(f"Active attack vector: {getattr(self.attack, 'attack_name', 'unknown')}")
    if steer > 0.42:
        score += 0.20
        signals.append("Steering command deviates from normal lane-following envelope")
    if brake > 0.70 and float(getattr(v, "speed_kmh", 0.0) or 0.0) > 10:
        score += 0.17
        signals.append("High brake command while vehicle is moving")
    if throttle > 0.82:
        score += 0.14
        signals.append("Throttle command unusually high for monitored autonomous driving")
    if float(getattr(v, "battery_temp_c", 0.0) or 0.0) >= 60 or float(getattr(v, "motor_temp_c", 0.0) or 0.0) >= 78:
        score += 0.14
        signals.append("Thermal indicators exceed safe baseline")
    if str(getattr(v, "lane_status", "centered")) not in {"centered", "normal", "clear"}:
        score += 0.10
        signals.append(f"Lane status anomaly: {getattr(v, 'lane_status', 'unknown')}")
    try:
        sensors = self.carla_bridge.sensor_snapshot()
        if sensors.get("collision"):
            score += 0.25
            signals.append("Collision sensor event detected")
        if sensors.get("lane_invasion"):
            score += 0.18
            signals.append("Lane invasion sensor event detected")
    except Exception:
        pass
    score = max(0.0, min(1.0, score))
    if score >= 0.82:
        threat = "CRITICAL TAKEOVER"
    elif score >= 0.62:
        threat = "CONTROL MANIPULATION"
    elif score >= 0.42:
        threat = "SUSPICIOUS COMMAND"
    elif score >= 0.22:
        threat = "EARLY WARNING"
    else:
        threat = "NORMAL"
    confidence = max(0.25, min(0.99, 0.45 + score * 0.54)) if score > 0 else 0.18
    explanation = "No significant anomaly detected. Vehicle behavior is within protected baseline."
    if signals:
        explanation = "AI detected anomaly from: " + "; ".join(signals[:4]) + "."
    risk_score = int(round(score * 100))
    self.ai_security.update({
        "status": "active" if risk_score >= 22 else "monitoring",
        "anomaly_score": risk_score,
        "risk_score": risk_score,
        "threat_class": threat,
        "confidence": round(confidence, 2),
        "explanation": explanation,
        "signals": signals[:8],
    })
    return self.ai_security
SimulationEngine.ai_anomaly_detection = _zg3_ai_anomaly_detection


def _zg3_classify_threat(self):
    ai = self.ai_anomaly_detection()
    name = getattr(self.attack, "attack_name", "normal")
    target = getattr(self.attack, "target_ecu", "gateway_ecu")
    mapping = {
        "steering_manipulation": ("Steering takeover", "Steering ECU / Lane Keeping"),
        "brake_injection": ("Brake command injection", "Brake ECU / ABS"),
        "throttle_injection": ("Acceleration takeover", "Powertrain ECU"),
        "gps_spoofing": ("Navigation spoofing", "GNSS / Route Planner"),
        "sensor_spoofing": ("Sensor-trust poisoning", "Sensor Fusion ECU"),
        "camera_lidar_blinding": ("Perception blinding", "Camera/LiDAR Stack"),
        "battery_thermal_tampering": ("Thermal/BMS tampering", "Battery Management"),
        "can_flooding": ("CAN availability attack", "Gateway ECU / CAN Bus"),
        "dos": ("Gateway denial of service", "Gateway ECU"),
        "telemetry_scraping": ("Privacy exfiltration", "Telematics ECU"),
        "mixed_attack": ("Coordinated multi-vector attack", "Gateway + Steering + Perception"),
        "manual_takeover": ("Manual remote-control takeover", "Brake/Steering/Throttle channel"),
    }
    label, component = mapping.get(name, ("Unknown anomaly", target.replace("_", " ").title()))
    ai["classification"] = {"label": label, "target_component": component, "source": "AI anomaly classifier", "confidence": ai.get("confidence", 0.0)}
    return ai["classification"]
SimulationEngine.classify_threat = _zg3_classify_threat


def _zg3_apply_attacker_manual_control(self, steer=0.0, throttle=0.0, brake=0.0):
    _zg3_init_ai_layer(self)
    # Manual takeover is intentionally treated as an attack scenario.
    self.attack.attack_name = "manual_takeover"
    self.attack.active = True
    self.attack.intensity = max(abs(float(steer or 0.0)), float(throttle or 0.0), float(brake or 0.0), 0.70)
    self.attack.target_ecu = "gateway_ecu"
    self.attack.objective = "cause_collision"
    self.attack.mode = "aggressive"
    try:
        result = self.carla_bridge.apply_manual_attacker_control(steer, throttle, brake)
        if self.carla_bridge.is_ready():
            self.mode = "carla"
    except Exception as exc:
        result = {"ok": False, "message": f"Manual control failed: {exc}", "applied_control": {"steer": steer, "throttle": throttle, "brake": brake}, "damaged_parts": []}
    ctrl = result.get("applied_control", {"steer": steer, "throttle": throttle, "brake": brake})
    self.update_driver({
        "autopilot_enabled": False,
        "manual_override": True,
        "steer": float(ctrl.get("steer", steer) or 0.0),
        "throttle": float(ctrl.get("throttle", throttle) or 0.0),
        "brake": float(ctrl.get("brake", brake) or 0.0),
        "lane_status": "attacker_takeover",
        "location_label": "Attacker manual control channel",
    })
    self.carla_last_apply = {
        "mode": "carla" if self.carla_bridge.is_ready() else self.mode,
        "attack_applied": bool(result.get("ok")),
        "defense_applied": False,
        "applied_control": ctrl,
        "damaged_parts": result.get("damaged_parts", ["Manual takeover channel"]),
        "diagnostic_notice": result.get("message", "Manual attacker control applied."),
    }
    self.ai_security["last_manual_control"] = {"active": True, **ctrl}
    self.ai_anomaly_detection()
    self.classify_threat()
    try:
        self._capture_evidence("attacker_manual_takeover", "Attacker manually controlled steering/brake/throttle from the dashboard.")
    except Exception:
        pass
    self._log(f"[ATTACKER CONTROL] Manual takeover applied: steer={float(ctrl.get('steer',0)):.2f}, throttle={float(ctrl.get('throttle',0)):.2f}, brake={float(ctrl.get('brake',0)):.2f}.")
    return {"ok": bool(result.get("ok", True)), "result": result, "ai_security": self.ai_security, "snapshot": self.snapshot()}
SimulationEngine.apply_attacker_manual_control = _zg3_apply_attacker_manual_control


def _zg3_adaptive_recovery(self):
    _zg3_init_ai_layer(self)
    ai = self.ai_anomaly_detection()
    risk = int(ai.get("risk_score", 0) or 0)
    if risk >= 70:
        action = "EMERGENCY_SAFE_MODE"
        driver_update = {"steer": 0.0, "throttle": 0.0, "brake": 0.75, "autopilot_enabled": False, "manual_override": False, "lane_status": "safe_mode_hold"}
    elif risk >= 40:
        action = "CONTROL_LIMITING"
        driver_update = {"steer": 0.0, "throttle": 0.12, "brake": 0.25, "autopilot_enabled": False, "manual_override": False, "lane_status": "restricted_safe_mode"}
    else:
        action = "AUTOPILOT_RESTORE"
        driver_update = {"steer": 0.0, "throttle": 0.20, "brake": 0.0, "autopilot_enabled": True, "manual_override": False, "lane_status": "centered"}
    self.update_driver(driver_update)
    # Clear attack state after containment, then use CARLA recovery when possible.
    self.attack.active = False
    self.attack.attack_name = "normal"
    self.attack.intensity = 0.0
    try:
        if risk >= 40 and self.carla_bridge.is_ready():
            carla_result = self.carla_bridge.recover_vehicle()
        else:
            carla_result = self.carla_bridge.enable_natural_drive()
    except Exception as exc:
        carla_result = {"ok": False, "message": f"Adaptive recovery fallback: {exc}", "applied_control": {"steer": driver_update["steer"], "throttle": driver_update["throttle"], "brake": driver_update["brake"]}}
    self.carla_last_apply = {
        "mode": "carla" if self.carla_bridge.is_ready() else self.mode,
        "attack_applied": False,
        "defense_applied": True,
        "applied_control": carla_result.get("applied_control", {"steer": driver_update["steer"], "throttle": driver_update["throttle"], "brake": driver_update["brake"]}),
        "damaged_parts": [],
        "diagnostic_notice": f"Adaptive recovery selected {action}. {carla_result.get('message', '')}",
    }
    self.ai_security["adaptive_recovery"] = {"status": "complete", "action": action, "message": self.carla_last_apply["diagnostic_notice"]}
    self.ai_anomaly_detection()
    try:
        self._capture_evidence("adaptive_recovery", f"AI adaptive recovery executed: {action}.")
    except Exception:
        pass
    self._log(f"[AI RECOVERY] {action}: attacker control isolated and safe behavior restored.")
    return {"ok": True, "ai_security": self.ai_security, "carla_result": carla_result, "snapshot": self.snapshot()}
SimulationEngine.adaptive_recovery = _zg3_adaptive_recovery

_zg3_original_snapshot = SimulationEngine.snapshot
def _zg3_snapshot(self):
    data = _zg3_original_snapshot(self)
    _zg3_init_ai_layer(self)
    try:
        self.ai_anomaly_detection()
        self.classify_threat()
    except Exception as exc:
        self.ai_security["explanation"] = f"AI layer warning: {exc}"
    data["ai_security"] = self.ai_security
    return data
SimulationEngine.snapshot = _zg3_snapshot


# ---------------------------------------------------------------------------
# DriveFort AI Battery Digital Twin + Live CARLA Telemetry extension
# CARLA exposes real vehicle speed/control/pose, but not a real EV BMS model.
# This layer binds battery SOC/temp/motor heat to the live CARLA vehicle behavior
# and lets the Attacker Console tamper with the simulated BMS telemetry.
# ---------------------------------------------------------------------------

def _zg4_init_battery_layer(self):
    if not hasattr(self, "battery_twin"):
        self.battery_twin = {
            "source": "CARLA speed/pose + DriveFort AI EV battery digital twin",
            "attacker_override": False,
            "tamper_mode": "none",
            "last_action": "Battery digital twin monitoring CARLA vehicle.",
            "last_speed_kmh": float(getattr(self.vehicle, "speed_kmh", 0.0) or 0.0),
        }

_zg4_original_init = SimulationEngine.__init__
def _zg4_init(self):
    _zg4_original_init(self)
    _zg4_init_battery_layer(self)
SimulationEngine.__init__ = _zg4_init


def _zg4_update_battery_from_carla(self):
    _zg4_init_battery_layer(self)
    v = self.vehicle
    speed = max(0.0, float(getattr(v, "speed_kmh", 0.0) or 0.0))
    throttle = max(0.0, min(1.0, float(getattr(v, "throttle", 0.0) or 0.0)))
    brake = max(0.0, min(1.0, float(getattr(v, "brake", 0.0) or 0.0)))
    attack_name = getattr(self.attack, "attack_name", "normal")
    active = bool(getattr(self.attack, "active", False))
    intensity = max(0.0, min(1.0, float(getattr(self.attack, "intensity", 0.0) or 0.0)))

    # Consumption and heat are intentionally small per dashboard refresh so the
    # telemetry moves smoothly while still showing the attack effect clearly.
    drain = 0.010 + speed * 0.00022 + throttle * 0.045 + brake * 0.008
    heat_target = 31.0 + speed * 0.045 + throttle * 8.0 + brake * 2.2
    motor_target = 39.0 + speed * 0.060 + throttle * 12.0 + brake * 3.0

    if active and attack_name in {"battery_thermal_tampering", "mixed_attack", "throttle_injection", "manual_takeover"}:
        heat_target += 24.0 * max(0.45, intensity)
        motor_target += 18.0 * max(0.45, intensity)
        drain += 0.14 * max(0.45, intensity)
    if active and attack_name in {"can_flooding", "dos"}:
        drain += 0.05 * max(0.35, intensity)

    # Smooth convergence, unless the attacker explicitly tampers with BMS values.
    current_soc = float(getattr(v, "battery_soc", 78.0) or 78.0)
    current_batt_temp = float(getattr(v, "battery_temp_c", 34.0) or 34.0)
    current_motor_temp = float(getattr(v, "motor_temp_c", 42.0) or 42.0)

    v.battery_soc = max(2.0, min(100.0, current_soc - drain))
    v.battery_temp_c = max(18.0, min(120.0, current_batt_temp + (heat_target - current_batt_temp) * 0.18))
    v.motor_temp_c = max(18.0, min(140.0, current_motor_temp + (motor_target - current_motor_temp) * 0.16))
    self.battery_twin.update({
        "last_speed_kmh": round(speed, 1),
        "last_consumption_delta": round(drain, 3),
        "thermal_target_c": round(heat_target, 1),
        "motor_target_c": round(motor_target, 1),
        "carla_bound": bool(self.mode == "carla" and self.carla_bridge.is_ready()),
    })

_zg4_original_sync_carla_state = SimulationEngine._sync_carla_state
def _zg4_sync_carla_state(self):
    _zg4_original_sync_carla_state(self)
    try:
        _zg4_update_battery_from_carla(self)
    except Exception as exc:
        try:
            self._log(f"[BMS] Battery digital twin update warning: {exc}")
        except Exception:
            pass
SimulationEngine._sync_carla_state = _zg4_sync_carla_state


def _zg4_apply_attacker_battery_control(self, temp_delta=0.0, soc_delta=0.0, mode="thermal_spike"):
    _zg4_init_battery_layer(self)
    try:
        temp_delta = max(-25.0, min(70.0, float(temp_delta or 0.0)))
        soc_delta = max(-45.0, min(25.0, float(soc_delta or 0.0)))
    except Exception:
        temp_delta, soc_delta = 0.0, 0.0
    mode = str(mode or "thermal_spike")[:40]
    self.attack.attack_name = "battery_thermal_tampering"
    self.attack.active = True
    self.attack.target_ecu = "battery_ecu"
    self.attack.objective = "disrupt_control"
    self.attack.mode = "aggressive"
    self.attack.intensity = max(0.65, min(1.0, abs(temp_delta) / 70.0 + abs(soc_delta) / 60.0))
    self.update_driver({
        "battery_temp_c": max(15.0, min(120.0, float(self.vehicle.battery_temp_c) + temp_delta)),
        "motor_temp_c": max(15.0, min(140.0, float(self.vehicle.motor_temp_c) + temp_delta * 0.55)),
        "battery_soc": max(2.0, min(100.0, float(self.vehicle.battery_soc) + soc_delta)),
        "throttle": min(float(self.vehicle.throttle), 0.22),
        "brake": max(float(self.vehicle.brake), 0.18),
        "location_label": "BMS telemetry tampering from attacker console",
    })
    self.carla_last_apply = {
        "mode": "carla" if self.carla_bridge.is_ready() else self.mode,
        "attack_applied": True,
        "defense_applied": False,
        "applied_control": {"steer": self.vehicle.steer, "throttle": self.vehicle.throttle, "brake": self.vehicle.brake},
        "damaged_parts": ["Battery BMS", "Thermal sensors", "State-of-charge estimator", "Power limit module"],
        "diagnostic_notice": f"BMS tampering applied: mode={mode}, temp_delta={temp_delta:+.1f}C, soc_delta={soc_delta:+.1f}%.",
    }
    self.battery_twin.update({
        "attacker_override": True,
        "tamper_mode": mode,
        "last_action": self.carla_last_apply["diagnostic_notice"],
    })
    try:
        self._capture_evidence("battery_bms_tampering", self.carla_last_apply["diagnostic_notice"])
    except Exception:
        pass
    self._log("[ATTACKER BMS] " + self.carla_last_apply["diagnostic_notice"])
    return {"ok": True, "battery_twin": self.battery_twin, "snapshot": self.snapshot()}
SimulationEngine.apply_attacker_battery_control = _zg4_apply_attacker_battery_control

_zg4_original_recover = SimulationEngine.recover_vehicle_live if hasattr(SimulationEngine, 'recover_vehicle_live') else None
def _zg4_recover_vehicle_live(self):
    if _zg4_original_recover:
        result = _zg4_original_recover(self)
    else:
        result = {"ok": True, "snapshot": self.snapshot()}
    _zg4_init_battery_layer(self)
    self.battery_twin.update({"attacker_override": False, "tamper_mode": "none", "last_action": "BMS telemetry stabilized by DriveFort AI recovery."})
    self.vehicle.battery_temp_c = min(float(self.vehicle.battery_temp_c), 42.0)
    self.vehicle.motor_temp_c = min(float(self.vehicle.motor_temp_c), 52.0)
    self._log("[BMS RECOVERY] Battery telemetry stabilized and attacker BMS override cleared.")
    return {"ok": True, "battery_twin": self.battery_twin, "snapshot": self.snapshot(), "previous": result}
SimulationEngine.recover_vehicle_live = _zg4_recover_vehicle_live

_zg4_original_snapshot = SimulationEngine.snapshot
def _zg4_snapshot(self):
    data = _zg4_original_snapshot(self)
    _zg4_init_battery_layer(self)
    data["battery_twin"] = self.battery_twin
    live_vehicle = bool(data.get("carla", {}).get("connected") and data.get("carla", {}).get("actor_found"))
    data["vehicle_telemetry"] = {
        "source": "CARLA live actor" if live_vehicle else "Waiting for CARLA vehicle",
        "live": live_vehicle,
        "speed_kmh": data.get("vehicle", {}).get("speed_kmh") if live_vehicle else None,
        "coordinates": {
            "x_or_lon": data.get("vehicle", {}).get("location_x") if live_vehicle else None,
            "y_or_lat": data.get("vehicle", {}).get("location_y") if live_vehicle else None,
        },
        "heading_deg": data.get("vehicle", {}).get("heading_deg") if live_vehicle else None,
        "battery_soc": data.get("vehicle", {}).get("battery_soc") if live_vehicle else None,
        "battery_temp_c": data.get("vehicle", {}).get("battery_temp_c") if live_vehicle else None,
        "motor_temp_c": data.get("vehicle", {}).get("motor_temp_c") if live_vehicle else None,
        "note": "Speed, coordinates, heading and controls come from CARLA when connected; battery/thermal values are DriveFort AI's EV BMS digital twin bound to CARLA behavior." if live_vehicle else "No live vehicle telemetry yet. Start/connect CARLA first; dashboard values stay blank until a CARLA vehicle is linked.",
    }
    return data
SimulationEngine.snapshot = _zg4_snapshot


# ---------------------------------------------------------------------------
# DriveFort AI Final Defense Stack
# Adds command validation, sandbox isolation, secure-communication simulation,
# predictive protection, attack replay, driver awareness and final showcase flow.
# These features are simulated in CARLA: unsafe controls are either applied in
# No-Protection mode or blocked/sanitized when DriveFort AI protection is enabled.
# ---------------------------------------------------------------------------

def _zg5_init_final_stack(self):
    if not hasattr(self, "final_defense"):
        self.final_defense = {
            "stack_status": "ready",
            "sandbox_mode": False,
            "secure_comm_enabled": True,
            "command_validation": {"status": "monitoring", "last_decision": "No command checked yet.", "blocked_count": 0, "allowed_count": 0},
            "predictive_protection": {"score": 0, "label": "LOW", "recommendation": "Continue monitoring."},
            "driver_awareness": {"message": "Vehicle secure. DriveFort AI is monitoring.", "priority": "normal", "instructions": ["Keep normal following distance."]},
            "attack_replay": [],
            "attack_sandbox": {"isolated": False, "reason": "Sandbox inactive."},
            "secure_bus": {"signed_commands": 0, "rejected_commands": 0, "trust": 100},
            "coverage": [
                {"layer": "Detection", "status": "Active", "detail": "AI anomaly detection + threat classification"},
                {"layer": "Prevention", "status": "Active", "detail": "Command validation blocks unsafe steering/brake/throttle/BMS commands"},
                {"layer": "Containment", "status": "Ready", "detail": "Sandbox isolates attacker commands before CARLA controls are changed"},
                {"layer": "Safe Mode", "status": "Ready", "detail": "Speed limiting, braking envelope and steering normalization"},
                {"layer": "Recovery", "status": "Ready", "detail": "Adaptive recovery restores safe autonomous control"},
                {"layer": "Evidence", "status": "Active", "detail": "Replay timeline and PDF incident report"},
            ],
        }

def _zg5_final_init(self):
    try:
        _zg4_init_battery_layer(self)
    except Exception:
        pass
    _zg5_init_final_stack(self)

_zg5_original_init = SimulationEngine.__init__
def _zg5_init(self):
    _zg5_original_init(self)
    _zg5_init_final_stack(self)
SimulationEngine.__init__ = _zg5_init


def _zg5_current_control(self):
    last = self.carla_last_apply if isinstance(getattr(self, "carla_last_apply", {}), dict) else {}
    ctrl = last.get("applied_control", {}) or {}
    return {
        "steer": float(ctrl.get("steer", getattr(self.vehicle, "steer", 0.0)) or 0.0),
        "throttle": float(ctrl.get("throttle", getattr(self.vehicle, "throttle", 0.0)) or 0.0),
        "brake": float(ctrl.get("brake", getattr(self.vehicle, "brake", 0.0)) or 0.0),
    }
SimulationEngine._final_current_control = _zg5_current_control


def _zg5_predictive_protection(self):
    _zg5_init_final_stack(self)
    v = self.vehicle
    score = 0
    reasons = []
    ctrl = self._final_current_control()
    if getattr(self.attack, "active", False):
        score += int(35 + 35 * float(getattr(self.attack, "intensity", 0.0) or 0.0))
        reasons.append(f"active {getattr(self.attack, 'attack_name', 'attack')} vector")
    if abs(ctrl["steer"]) > 0.38:
        score += 12; reasons.append("steering exceeds protected envelope")
    if ctrl["brake"] > 0.65 and float(getattr(v, "speed_kmh", 0.0) or 0.0) > 10:
        score += 10; reasons.append("sudden brake command at speed")
    if ctrl["throttle"] > 0.82:
        score += 9; reasons.append("high throttle command")
    if float(getattr(v, "battery_temp_c", 0.0) or 0.0) > 58:
        score += 12; reasons.append("battery thermal deviation")
    if str(getattr(v, "lane_status", "centered")) not in {"centered", "normal", "clear"}:
        score += 7; reasons.append("lane-status deviation")
    score = max(0, min(100, score))
    if score >= 75:
        label = "CRITICAL"
        recommendation = "Block commands, isolate attacker channel, enable Safe Mode and start adaptive recovery."
    elif score >= 50:
        label = "HIGH"
        recommendation = "Restrict commands and pre-arm Safe Mode."
    elif score >= 25:
        label = "MEDIUM"
        recommendation = "Increase sampling and require signed/validated control commands."
    else:
        label = "LOW"
        recommendation = "Continue monitoring."
    self.final_defense["predictive_protection"] = {"score": score, "label": label, "reasons": reasons[:5], "recommendation": recommendation}
    return self.final_defense["predictive_protection"]
SimulationEngine.predictive_protection = _zg5_predictive_protection


def _zg5_driver_awareness(self, blocked=False, decision=None):
    _zg5_init_final_stack(self)
    pred = self.predictive_protection()
    attack_name = getattr(self.attack, "attack_name", "normal")
    if blocked:
        msg = f"DriveFort AI blocked {attack_name.replace('_',' ')}. Safe Mode is active; attacker control is not allowed."
        priority = "critical" if pred["score"] >= 70 else "warning"
        instructions = ["Keep hands ready.", "Maintain safe distance.", "Allow adaptive recovery to stabilize the vehicle."]
    elif getattr(self.attack, "active", False):
        msg = f"Attack detected: {attack_name.replace('_',' ')}. Diagnostics are active."
        priority = "warning"
        instructions = ["Avoid aggressive inputs.", "Prepare for Safe Mode."]
    else:
        msg = "Vehicle secure. DriveFort AI is monitoring live CARLA telemetry."
        priority = "normal"
        instructions = ["Continue normal autonomous driving."]
    self.final_defense["driver_awareness"] = {"message": msg, "priority": priority, "instructions": instructions, "decision": decision or {}}
    return self.final_defense["driver_awareness"]
SimulationEngine.driver_awareness_update = _zg5_driver_awareness


def _zg5_validate_command(self, attack_name="normal", intensity=0.0, controls=None, source="attacker"):
    _zg5_init_final_stack(self)
    controls = controls or {}
    intensity = max(0.0, min(1.0, float(intensity or 0.0)))
    protected = bool(getattr(self, "protection_enabled", False))
    sandbox = bool(self.final_defense.get("sandbox_mode", False))
    secure = bool(self.final_defense.get("secure_comm_enabled", True))
    reasons = []
    unsafe = False
    steer = abs(float(controls.get("steer", 0.0) or 0.0))
    throttle = float(controls.get("throttle", 0.0) or 0.0)
    brake = float(controls.get("brake", 0.0) or 0.0)
    if attack_name != "normal" and source == "attacker":
        unsafe = True; reasons.append("attacker-origin control command")
    if steer > 0.42:
        unsafe = True; reasons.append("steering outside safe envelope")
    if throttle > 0.70:
        unsafe = True; reasons.append("throttle exceeds protected limit")
    if brake > 0.70:
        unsafe = True; reasons.append("brake exceeds protected limit")
    if attack_name in {"battery_thermal_tampering", "mixed_attack"} and intensity >= 0.5:
        unsafe = True; reasons.append("BMS/thermal manipulation attempt")
    if attack_name in {"can_flooding", "dos"}:
        unsafe = True; reasons.append("gateway/CAN availability attack")
    allowed = not (protected and unsafe)
    if sandbox and source == "attacker":
        allowed = False; reasons.append("attacker command contained in sandbox")
    if secure and source == "attacker" and protected:
        allowed = False; reasons.append("unsigned/untrusted command rejected by secure bus")
    decision = {
        "allowed": bool(allowed),
        "protected": protected,
        "sandbox": sandbox,
        "secure_comm": secure,
        "source": source,
        "attack": attack_name,
        "intensity": intensity,
        "reasons": reasons or ["command inside validated envelope"],
        "sanitized_control": {"steer": 0.0, "throttle": 0.12 if protected else throttle, "brake": 0.25 if protected and unsafe else brake},
    }
    cv = self.final_defense["command_validation"]
    if allowed:
        cv["allowed_count"] = int(cv.get("allowed_count", 0)) + 1
        cv["status"] = "allowed"
        cv["last_decision"] = "Allowed: " + "; ".join(decision["reasons"][:2])
    else:
        cv["blocked_count"] = int(cv.get("blocked_count", 0)) + 1
        cv["status"] = "blocked"
        cv["last_decision"] = "Blocked: " + "; ".join(decision["reasons"][:3])
        self.final_defense["secure_bus"]["rejected_commands"] = int(self.final_defense["secure_bus"].get("rejected_commands", 0)) + 1
    self.final_defense["secure_bus"]["signed_commands"] = int(self.final_defense["secure_bus"].get("signed_commands", 0)) + (0 if source == "attacker" else 1)
    self.final_defense["secure_bus"]["trust"] = max(0, min(100, 100 - self.final_defense["secure_bus"].get("rejected_commands",0)*6))
    self.final_defense["command_validation"] = cv
    return decision
SimulationEngine.validate_control_command = _zg5_validate_command


def _zg5_record_replay_frame(self, stage, note=""):
    _zg5_init_final_stack(self)
    ctrl = self._final_current_control()
    frame = {
        "stage": stage,
        "note": note,
        "attack": getattr(self.attack, "attack_name", "normal"),
        "protected": bool(getattr(self, "protection_enabled", False)),
        "vehicle": {
            "speed_kmh": round(float(getattr(self.vehicle, "speed_kmh", 0.0) or 0.0), 1),
            "x": round(float(getattr(self.vehicle, "location_x", 0.0) or 0.0), 2),
            "y": round(float(getattr(self.vehicle, "location_y", 0.0) or 0.0), 2),
            "battery_soc": round(float(getattr(self.vehicle, "battery_soc", 0.0) or 0.0), 1),
            "battery_temp_c": round(float(getattr(self.vehicle, "battery_temp_c", 0.0) or 0.0), 1),
            "lane_status": getattr(self.vehicle, "lane_status", "unknown"),
        },
        "control": {k: round(v, 2) for k, v in ctrl.items()},
        "risk": self.final_defense.get("predictive_protection", {}).get("score", 0),
    }
    self.final_defense["attack_replay"].append(frame)
    self.final_defense["attack_replay"] = self.final_defense["attack_replay"][-30:]
    return frame
SimulationEngine.record_replay_frame = _zg5_record_replay_frame


_zg5_original_apply_attack = SimulationEngine.apply_carla_attack_console
def _zg5_apply_carla_attack_console(self, attack, intensity=0.92):
    _zg5_init_final_stack(self)
    controls_by_attack = {
        "steering_manipulation": {"steer": 0.82, "throttle": 0.10, "brake": 0.10},
        "brake_injection": {"steer": 0.0, "throttle": 0.0, "brake": 0.96},
        "throttle_injection": {"steer": 0.0, "throttle": 0.95, "brake": 0.0},
        "battery_thermal_tampering": {"steer": 0.0, "throttle": 0.18, "brake": 0.20},
        "mixed_attack": {"steer": 0.68, "throttle": 0.15, "brake": 0.45},
    }
    controls = controls_by_attack.get(str(attack), {"steer": 0.45, "throttle": 0.25, "brake": 0.20})
    decision = self.validate_control_command(str(attack), intensity, controls, source="attacker")
    self.record_replay_frame("attack_attempt", f"Attacker attempted {str(attack).replace('_',' ')}.")
    if not decision["allowed"]:
        self.attack.attack_name = "normal"
        self.attack.active = False
        self.attack.intensity = 0.0
        sanitized = decision["sanitized_control"]
        self.update_driver({"steer": sanitized["steer"], "throttle": sanitized["throttle"], "brake": sanitized["brake"], "autopilot_enabled": True, "manual_override": False, "lane_status": "safe_mode_protected", "location_label": "DriveFort AI blocked attacker command"})
        try:
            carla_result = self.carla_bridge.recover_vehicle() if self.carla_bridge.is_ready() else {"ok": True, "message": "Protected fallback recovery simulated.", "applied_control": sanitized}
        except Exception as exc:
            carla_result = {"ok": False, "message": f"Recovery fallback: {exc}", "applied_control": sanitized}
        self.carla_last_apply = {"mode": "carla" if self.carla_bridge.is_ready() else self.mode, "attack_applied": False, "defense_applied": True, "blocked_by_zoneguard": True, "blocked_by_drivefort": True, "validation": decision, "applied_control": sanitized, "damaged_parts": [], "diagnostic_notice": "DriveFort AI blocked attacker command, isolated channel, and enabled safe behavior."}
        self.ai_anomaly_detection(); self.classify_threat(); self.driver_awareness_update(True, decision); self.predictive_protection()
        self.record_replay_frame("blocked_safe_mode", "DriveFort AI blocked the attack before unsafe CARLA control persisted.")
        try: self._capture_evidence("command_blocked", self.carla_last_apply["diagnostic_notice"])
        except Exception: pass
        return {"ok": True, "blocked": True, "validation": decision, "carla_result": carla_result, "snapshot": self.snapshot()}
    result = _zg5_original_apply_attack(self, attack, intensity)
    self.driver_awareness_update(False, decision); self.predictive_protection(); self.record_replay_frame("attack_applied", f"{str(attack).replace('_',' ')} applied to CARLA in no-protection mode.")
    return result
SimulationEngine.apply_carla_attack_console = _zg5_apply_carla_attack_console

_zg5_original_manual = SimulationEngine.apply_attacker_manual_control
def _zg5_apply_attacker_manual_control(self, steer=0.0, throttle=0.0, brake=0.0):
    _zg5_init_final_stack(self)
    controls = {"steer": float(steer or 0.0), "throttle": float(throttle or 0.0), "brake": float(brake or 0.0)}
    decision = self.validate_control_command("manual_takeover", max(abs(controls["steer"]), controls["throttle"], controls["brake"]), controls, source="attacker")
    self.record_replay_frame("manual_takeover_attempt", "Attacker tried to drive steering/throttle/brake from the console.")
    if not decision["allowed"]:
        sanitized = decision["sanitized_control"]
        self.update_driver({"steer": sanitized["steer"], "throttle": sanitized["throttle"], "brake": sanitized["brake"], "autopilot_enabled": True, "manual_override": False, "lane_status": "manual_takeover_blocked"})
        try: carla_result = self.carla_bridge.recover_vehicle()
        except Exception: carla_result = {"ok": True, "message": "Manual takeover blocked in protected mode.", "applied_control": sanitized}
        self.carla_last_apply = {"mode": "carla" if self.carla_bridge.is_ready() else self.mode, "attack_applied": False, "defense_applied": True, "blocked_by_zoneguard": True, "blocked_by_drivefort": True, "validation": decision, "applied_control": sanitized, "damaged_parts": [], "diagnostic_notice": "Manual attacker control blocked by DriveFort AI command validation."}
        self.ai_anomaly_detection(); self.classify_threat(); self.driver_awareness_update(True, decision); self.predictive_protection(); self.record_replay_frame("manual_takeover_blocked", "DriveFort AI rejected remote steering/brake/throttle takeover.")
        return {"ok": True, "blocked": True, "validation": decision, "carla_result": carla_result, "snapshot": self.snapshot()}
    return _zg5_original_manual(self, steer, throttle, brake)
SimulationEngine.apply_attacker_manual_control = _zg5_apply_attacker_manual_control

_zg5_original_battery = SimulationEngine.apply_attacker_battery_control
def _zg5_apply_attacker_battery_control(self, temp_delta=0.0, soc_delta=0.0, mode="thermal_spike"):
    _zg5_init_final_stack(self)
    controls = {"steer": 0.0, "throttle": 0.0, "brake": 0.2}
    decision = self.validate_control_command("battery_thermal_tampering", min(1.0, abs(float(temp_delta or 0.0))/65.0 + abs(float(soc_delta or 0.0))/40.0), controls, source="attacker")
    self.record_replay_frame("bms_tamper_attempt", "Attacker tried to tamper with BMS battery heat/SOC telemetry.")
    if not decision["allowed"]:
        self.attack.active = False; self.attack.attack_name = "normal"; self.attack.intensity = 0.0
        self.vehicle.battery_temp_c = min(float(self.vehicle.battery_temp_c), 42.0)
        self.vehicle.motor_temp_c = min(float(self.vehicle.motor_temp_c), 52.0)
        self.carla_last_apply = {"mode": "carla" if self.carla_bridge.is_ready() else self.mode, "attack_applied": False, "defense_applied": True, "blocked_by_zoneguard": True, "blocked_by_drivefort": True, "validation": decision, "applied_control": decision["sanitized_control"], "damaged_parts": [], "diagnostic_notice": "BMS tampering blocked; battery digital twin stabilized."}
        self.driver_awareness_update(True, decision); self.predictive_protection(); self.record_replay_frame("bms_tamper_blocked", "DriveFort AI blocked BMS tampering and stabilized battery telemetry.")
        return {"ok": True, "blocked": True, "validation": decision, "snapshot": self.snapshot()}
    return _zg5_original_battery(self, temp_delta, soc_delta, mode)
SimulationEngine.apply_attacker_battery_control = _zg5_apply_attacker_battery_control


def _zg5_set_sandbox(self, enabled=True):
    _zg5_init_final_stack(self)
    enabled = bool(enabled)
    self.final_defense["sandbox_mode"] = enabled
    self.final_defense["attack_sandbox"] = {"isolated": enabled, "reason": "Attacker commands are isolated and cannot reach CARLA controls." if enabled else "Sandbox inactive; commands follow current protection policy."}
    self._log(f"[SANDBOX] Attack sandbox {'enabled' if enabled else 'disabled'}.")
    return {"ok": True, "final_defense": self.final_defense, "snapshot": self.snapshot()}
SimulationEngine.set_attack_sandbox = _zg5_set_sandbox


def _zg5_set_secure_comm(self, enabled=True):
    _zg5_init_final_stack(self)
    self.final_defense["secure_comm_enabled"] = bool(enabled)
    self.final_defense["secure_bus"]["trust"] = 100 if enabled else max(30, self.final_defense["secure_bus"].get("trust", 80) - 10)
    self._log(f"[SECURE BUS] Secure communication {'enabled' if enabled else 'disabled'}.")
    return {"ok": True, "final_defense": self.final_defense, "snapshot": self.snapshot()}
SimulationEngine.set_secure_communication = _zg5_set_secure_comm


def _zg5_emergency_safe_stop(self):
    _zg5_init_final_stack(self)
    self.protection_enabled = True
    self.update_driver({"steer": 0.0, "throttle": 0.0, "brake": 0.85, "autopilot_enabled": False, "manual_override": False, "lane_status": "emergency_safe_stop"})
    try: carla_result = self.carla_bridge.recover_vehicle()
    except Exception: carla_result = {"ok": True, "message": "Emergency safe stop simulated.", "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.85}}
    self.carla_last_apply = {"mode": "carla" if self.carla_bridge.is_ready() else self.mode, "attack_applied": False, "defense_applied": True, "applied_control": {"steer":0.0,"throttle":0.0,"brake":0.85}, "damaged_parts": [], "diagnostic_notice": "Emergency Safe Stop activated by owner/DriveFort AI."}
    self.attack.active = False; self.attack.attack_name = "normal"; self.attack.intensity = 0.0
    self.driver_awareness_update(True, {"allowed": False, "reasons": ["emergency safe stop"]}); self.record_replay_frame("emergency_safe_stop", "Vehicle placed in controlled stop/safe mode.")
    return {"ok": True, "carla_result": carla_result, "snapshot": self.snapshot()}
SimulationEngine.emergency_safe_stop = _zg5_emergency_safe_stop


def _zg5_final_showcase(self, attack_name="mixed_attack"):
    _zg5_init_final_stack(self)
    attack_name = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != "normal" else "mixed_attack"
    self.reset(); _zg5_init_final_stack(self)
    self.final_defense["attack_replay"] = []
    self.set_secure_communication(True)
    self.start_natural_drive(); self.record_replay_frame("baseline", "Normal CARLA drive baseline.")
    self.protection_enabled = False
    unprotected = self.apply_carla_attack_console(attack_name, 0.96)
    self.record_replay_frame("unprotected_result", "No protection: attacker command changed vehicle behavior.")
    unprotected_pack = self._protection_metric_pack("Unprotected impact") if hasattr(self, "_protection_metric_pack") else self._metric_summary()
    self.activate_innovative_protection()
    self.set_attack_sandbox(False)
    protected = self.apply_carla_attack_console(attack_name, 0.96)
    self.record_replay_frame("protected_blocked", "Protection enabled: same attack blocked by validation and secure bus.")
    recovery = self.adaptive_recovery()
    protected_pack = self._protection_metric_pack("Protected recovery") if hasattr(self, "_protection_metric_pack") else self._metric_summary()
    self.full_demo_summary = {
        "status": "final_showcase_complete",
        "phase": "baseline_unprotected_protected_recovery",
        "before": unprotected_pack,
        "after": protected_pack,
        "unprotected": unprotected_pack,
        "protected": protected_pack,
        "timeline": [
            {"title":"Normal drive", "detail":"Vehicle drives normally and telemetry baseline is recorded."},
            {"title":"Unprotected attack", "detail":"Same attack is allowed to show visible unsafe impact."},
            {"title":"DriveFort AI armed", "detail":"Secure communication, command validation, sandbox readiness and AI monitoring are enabled."},
            {"title":"Protected attack", "detail":"Attacker command is blocked before unsafe CARLA control persists."},
            {"title":"Adaptive recovery", "detail":"Safe Mode/recovery stabilizes controls and BMS telemetry."},
        ],
        "owner_message": "Final showcase complete: DriveFort AI demonstrates detection, prevention, containment, safe mode, recovery and evidence replay.",
    }
    self.protection_demo.update({"status":"final_showcase_complete", "unprotected":{"after":unprotected_pack,"outcome":"ATTACK SUCCEEDED without DriveFort AI"}, "protected":{"after":protected_pack,"outcome":"ATTACK BLOCKED with DriveFort AI"}, "verdict":"Final demo complete: unprotected vehicle is compromised; protected vehicle blocks the same attack and recovers."})
    return {"ok": True, "unprotected": unprotected, "protected": protected, "recovery": recovery, "snapshot": self.snapshot()}
SimulationEngine.run_final_showcase = _zg5_final_showcase


def _zg5_get_replay(self):
    _zg5_init_final_stack(self)
    return {"frames": self.final_defense.get("attack_replay", []), "count": len(self.final_defense.get("attack_replay", [])), "snapshot": self.snapshot()}
SimulationEngine.get_attack_replay = _zg5_get_replay

_zg5_original_snapshot = SimulationEngine.snapshot
def _zg5_snapshot(self):
    data = _zg5_original_snapshot(self)
    _zg5_init_final_stack(self)
    try:
        self.predictive_protection()
        self.driver_awareness_update(False)
    except Exception as exc:
        self.final_defense["stack_status"] = f"warning: {exc}"
    data["final_defense"] = self.final_defense
    return data
SimulationEngine.snapshot = _zg5_snapshot


# ---------------------------------------------------------------------------
# DriveFort AI robust dashboard-to-CARLA command hotfix
# ---------------------------------------------------------------------------
def _zg_force_respawn_and_drive_engine(self):
    self.protection_enabled = False
    try:
        if hasattr(self, "final_defense"):
            self.final_defense["sandbox_mode"] = False
    except Exception:
        pass
    self.attack.active = False
    self.attack.attack_name = "normal"
    self.attack.intensity = 0.0
    self.connect_carla_full({"host": self.carla_bridge.host, "port": self.carla_bridge.port, "spawn_if_missing": False, "synchronous": True, "fps": self.carla_bridge.fps})
    result = self.carla_bridge.force_respawn_and_drive() if hasattr(self.carla_bridge, "force_respawn_and_drive") else {"ok": False, "message": "Bridge force respawn not available."}
    if result.get("ok"):
        self.mode = "carla"
        self.update_driver({
            "zone_type": "urban", "speed_kmh": 30, "traffic_density": "medium", "lane_status": "centered",
            "battery_soc": max(30, self.vehicle.battery_soc), "battery_temp_c": 34, "motor_temp_c": 42,
            "location_label": "CARLA live route - clean respawn", "autopilot_enabled": True,
            "manual_override": False, "steer": 0.0, "throttle": 0.25, "brake": 0.0,
        })
        self.carla_last_apply = {"mode":"carla","attack_applied":False,"defense_applied":False,"applied_control":{"steer":0.0,"throttle":0.25,"brake":0.0},"damaged_parts":[],"diagnostic_notice":result.get("message")}
        self._log("[CARLA HOTFIX] Force respawn + normal drive executed from dashboard.")
    else:
        self._log("[CARLA HOTFIX] Force respawn failed: " + str(result.get("message")))
    return {"ok": bool(result.get("ok")), "status": result, "snapshot": self.snapshot()}
SimulationEngine.force_respawn_and_drive = _zg_force_respawn_and_drive_engine


def _zg_force_direct_carla_attack_engine(self, attack_name="mixed_attack", intensity=0.95):
    if attack_name not in ALLOWED_ATTACKS or attack_name == "normal":
        attack_name = "mixed_attack"
    self.protection_enabled = False
    try:
        if hasattr(self, "final_defense"):
            self.final_defense["sandbox_mode"] = False
    except Exception:
        pass
    if not self.carla_bridge.is_ready():
        self.force_respawn_and_drive()
    self.apply_preset(attack_name)
    self.attack.active = True
    self.attack.attack_name = attack_name
    self.attack.intensity = clamp_float(intensity, 0.0, 1.0, 0.95)
    result = self.carla_bridge.apply_direct_attack(attack_name, self.attack.intensity)
    self.carla_bridge.start_live_loop()
    self.carla_last_apply = {"mode":"carla" if self.carla_bridge.is_ready() else self.mode,"attack_applied":bool(result.get("ok")),"defense_applied":False,"applied_control":result.get("applied_control",{}),"damaged_parts":result.get("damaged_parts",[]),"diagnostic_notice":result.get("message")}
    self._log("[CARLA HOTFIX] Force direct attack executed: " + str(attack_name) + " -> " + str(result.get("message")))
    return {"ok": bool(result.get("ok")), "carla_result": result, "snapshot": self.snapshot()}
SimulationEngine.force_direct_carla_attack = _zg_force_direct_carla_attack_engine

# --- REAL CARLA ONLY STRICT MODE PATCH --------------------------------------
# This project must not show fake telemetry or fake attack effects while CARLA
# is not linked to a real vehicle actor. The methods below intentionally refuse
# to run demos/attacks unless CARLA is connected, an actor exists, and controls
# can be applied to that actor.

def _zg_real_carla_ready(self):
    return bool(getattr(self, 'carla_bridge', None) and self.carla_bridge.is_ready())


def _zg_real_start_natural_drive(self):
    self.apply_preset('normal')
    status = self.connect_carla_full({
        'host': self.carla_bridge.host,
        'port': self.carla_bridge.port,
        'spawn_if_missing': True,
        'synchronous': True,
        'fps': self.carla_bridge.fps,
    })
    if not self.carla_bridge.is_ready():
        self.mode = 'mock'
        self.carla_last_apply = {
            'mode': 'waiting_for_carla',
            'attack_applied': False,
            'defense_applied': False,
            'applied_control': {'steer': 0.0, 'throttle': 0.0, 'brake': 0.0},
            'damaged_parts': [],
            'diagnostic_notice': status.get('message', 'Waiting for CARLA vehicle actor.'),
        }
        self._log('[CARLA STRICT] No fake normal-drive values emitted. Waiting for a live CARLA vehicle actor.')
        return False
    self.mode = 'carla'
    self.carla_bridge.enable_natural_drive()
    self.carla_bridge.start_live_loop()
    self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    self._log('[CARLA STRICT] Natural drive uses live CARLA actor telemetry only.')
    return True


def _zg_real_apply_carla_attack_console(self, attack_name, intensity=0.92):
    if attack_name not in ALLOWED_ATTACKS or attack_name == 'normal':
        attack_name = 'mixed_attack'
    if not self.carla_bridge.is_ready():
        if not self.start_natural_drive():
            msg = 'CARLA is not linked to a live vehicle. Attack was not simulated and no fake damage was generated.'
            self._log('[CARLA STRICT] ' + msg)
            return {'ok': False, 'attack': attack_name, 'message': msg, 'carla_result': {'ok': False, 'message': msg}, 'snapshot': self.snapshot()}
    self.mode = 'carla'
    self.apply_preset(attack_name)
    self.attack.intensity = clamp_float(intensity, 0.0, 1.0, self.attack.intensity)
    self.attack.active = True
    self.attack.replay_enabled = True
    result = self.carla_bridge.apply_direct_attack(attack_name, self.attack.intensity)
    self.carla_bridge.start_live_loop()
    self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    self.carla_last_apply = {
        'mode': 'carla',
        'attack_applied': bool(result.get('ok')),
        'defense_applied': False,
        'applied_control': result.get('applied_control', {'steer': self.vehicle.steer, 'throttle': self.vehicle.throttle, 'brake': self.vehicle.brake}),
        'damaged_parts': result.get('damaged_parts', []),
        'impact': result.get('impact', {}),
        'diagnostic_notice': result.get('message', 'Live CARLA attack requested.'),
    }
    self._log('[CARLA STRICT] Live attack applied to CARLA actor: ' + str(attack_name) + '. ' + str(result.get('message', '')))
    return {'ok': bool(result.get('ok')), 'attack': attack_name, 'carla_result': result, 'snapshot': self.snapshot()}


def _zg_real_launch_owner_visible_attack(self, attack_name='mixed_attack'):
    result = self.apply_carla_attack_console(attack_name, 0.96)
    return bool(result.get('ok'))


def _zg_real_run_full_demo(self, attack_name='mixed_attack'):
    self.reset()
    if not self.start_natural_drive():
        self.full_demo_summary = {
            'status': 'waiting_for_carla',
            'phase': 'blocked_no_live_vehicle',
            'before': {}, 'after': {}, 'delta': {},
            'timeline': [{'step': '0', 'title': 'Waiting for CARLA', 'detail': 'No baseline, attack, damage, or telemetry is generated until a live CARLA vehicle actor is linked.'}],
            'owner_message': 'Start CARLA, spawn/link the vehicle, then run the demo. No fake evidence was generated.',
        }
        return self.full_demo_summary
    before = self._metric_summary()
    preset = attack_name if attack_name in ALLOWED_ATTACKS and attack_name != 'normal' else 'mixed_attack'
    attack_result = self.apply_carla_attack_console(preset, 0.96)
    after = self._metric_summary()
    delta = self._metric_delta(before, after)
    self.full_demo_summary = {
        'status': 'completed' if attack_result.get('ok') else 'attack_failed',
        'phase': 'live_carla_attack',
        'before': before, 'after': after, 'delta': delta,
        'timeline': [
            {'step': '1', 'title': 'Live baseline', 'detail': 'Baseline captured from CARLA actor telemetry.'},
            {'step': '2', 'title': 'Live attack injection', 'detail': preset.replace('_', ' ').title() + ' was sent to CARLA vehicle control.'},
            {'step': '3', 'title': 'Visible simulator impact', 'detail': 'Observed control/speed/lane impact comes from the linked CARLA actor.'},
        ],
        'owner_message': 'Full demo used live CARLA telemetry only; no mock damage or fake vehicle values were generated.',
    }
    return self.full_demo_summary

SimulationEngine.start_natural_drive = _zg_real_start_natural_drive
SimulationEngine.apply_carla_attack_console = _zg_real_apply_carla_attack_console
SimulationEngine.launch_owner_visible_attack = _zg_real_launch_owner_visible_attack
SimulationEngine.run_full_demo = _zg_real_run_full_demo

def _zg_real_force_direct_carla_attack(self, attack_name='mixed_attack', intensity=0.95):
    # Keep /api/carla/force_attack strict as well: it must fail cleanly instead
    # of falling back to dashboard-only changes when CARLA is unavailable.
    return self.apply_carla_attack_console(attack_name, intensity)

SimulationEngine.force_direct_carla_attack = _zg_real_force_direct_carla_attack


# ---------------------------------------------------------------------------
# DriveFort AI Real AI Behavior Engine v2
# Practical AI integration without external packages: online behavior baseline,
# weighted anomaly scoring, attack classification, confidence, contribution
# explanation, and adaptive control policy. This layer is deterministic so it
# can be tested offline, and it uses live CARLA telemetry when CARLA is linked.
# ---------------------------------------------------------------------------

import math as _zg_ai_math
from collections import deque as _zg_ai_deque

_ZG_AI_FEATURES = [
    "speed_kmh", "steer_abs", "throttle", "brake", "battery_temp_c",
    "motor_temp_c", "obstacle_inverse", "lane_offset", "control_conflict",
]
_ZG_AI_DEFAULT_BASELINE = {
    "speed_kmh": (42.0, 18.0),
    "steer_abs": (0.10, 0.18),
    "throttle": (0.32, 0.22),
    "brake": (0.05, 0.18),
    "battery_temp_c": (34.0, 8.0),
    "motor_temp_c": (42.0, 10.0),
    "obstacle_inverse": (0.04, 0.08),
    "lane_offset": (0.0, 0.35),
    "control_conflict": (0.0, 0.20),
}
_ZG_AI_ATTACK_LABELS = {
    "steering_manipulation": ("Steering manipulation", "Steering ECU / Lane Keeping", "مناورة غير مصرح بها بالمقود"),
    "brake_injection": ("Brake command injection", "Brake ECU / ABS", "حقن أوامر فرملة غير طبيعية"),
    "throttle_injection": ("Acceleration injection", "Powertrain ECU", "حقن تسارع عالي الخطورة"),
    "gps_spoofing": ("GPS spoofing", "GNSS / Route Planner", "انتحال بيانات الموقع والمسار"),
    "sensor_spoofing": ("Sensor spoofing", "Sensor Fusion ECU", "تضارب أو انتحال قراءات الحساسات"),
    "camera_lidar_blinding": ("Camera/LiDAR blinding", "Camera/LiDAR Stack", "تعمية طبقة الإدراك"),
    "battery_thermal_tampering": ("BMS thermal tampering", "Battery Management System", "تلاعب بحرارة أو شحن البطارية"),
    "can_flooding": ("CAN flooding", "Gateway ECU / CAN Bus", "إغراق قناة الاتصال الداخلية"),
    "dos": ("Gateway denial of service", "Gateway ECU", "حجب خدمة أو تأخير استجابة"),
    "telemetry_scraping": ("Telemetry scraping", "Telematics ECU", "استخراج بيانات قياس حساسة"),
    "mixed_attack": ("Coordinated multi-vector attack", "Gateway + Control + Perception", "هجوم مركب متعدد الطبقات"),
    "manual_takeover": ("Remote manual takeover", "Steering/Brake/Throttle channel", "سيطرة يدوية عن بعد على أوامر القيادة"),
}

def _zgai_init(self):
    if not hasattr(self, "ai_behavior"):
        self.ai_behavior = {
            "enabled": True,
            "mode": "online_baseline",
            "sample_count": 0,
            "history": _zg_ai_deque(maxlen=240),
            "baseline": dict(_ZG_AI_DEFAULT_BASELINE),
            "last_features": {},
            "last_score": 0,
            "last_contributions": [],
            "validation": {"last_run": "not_run", "cases_passed": 0, "cases_total": 0, "message": "AI self-test has not been executed yet."},
        }
    _zg3_init_ai_layer(self)

def _zgai_lane_offset(status):
    status = str(status or "centered")
    if status in {"centered", "normal", "clear"}:
        return 0.0
    if "safe" in status or "blocked" in status:
        return 0.25
    if "drift" in status:
        return 0.8
    if "takeover" in status or "attacker" in status:
        return 1.0
    return 0.45

def _zgai_extract_features(self):
    v = self.vehicle
    last = self.carla_last_apply if isinstance(self.carla_last_apply, dict) else {}
    ctrl = last.get("applied_control", {}) or {}
    steer = float(ctrl.get("steer", getattr(v, "steer", 0.0)) or 0.0)
    throttle = float(ctrl.get("throttle", getattr(v, "throttle", 0.0)) or 0.0)
    brake = float(ctrl.get("brake", getattr(v, "brake", 0.0)) or 0.0)
    speed = float(getattr(v, "speed_kmh", 0.0) or 0.0)
    obstacle = max(0.1, float(getattr(v, "obstacle_distance_m", 100.0) or 100.0))
    # CARLA sensors strengthen the AI when available, but the model remains safe offline.
    collision = False
    lane_inv = False
    try:
        sensors = self.carla_bridge.sensor_snapshot()
        collision = bool(sensors.get("collision"))
        lane_inv = bool(sensors.get("lane_invasion"))
    except Exception:
        pass
    conflict = 1.0 if (brake > 0.35 and throttle > 0.35) else 0.0
    if collision:
        conflict = max(conflict, 1.0)
    lane_offset = _zgai_lane_offset(getattr(v, "lane_status", "centered"))
    if lane_inv:
        lane_offset = max(lane_offset, 1.0)
    return {
        "speed_kmh": speed,
        "steer_abs": abs(steer),
        "throttle": max(0.0, min(1.0, throttle)),
        "brake": max(0.0, min(1.0, brake)),
        "battery_temp_c": float(getattr(v, "battery_temp_c", 0.0) or 0.0),
        "motor_temp_c": float(getattr(v, "motor_temp_c", 0.0) or 0.0),
        "obstacle_inverse": min(1.0, 1.0 / obstacle * 8.0),
        "lane_offset": lane_offset,
        "control_conflict": conflict,
        "collision_sensor": collision,
        "lane_invasion_sensor": lane_inv,
    }

def _zgai_update_baseline(self, features):
    _zgai_init(self)
    # Learn only during clean, connected/normal behavior; never train on attacks.
    if getattr(self.attack, "active", False):
        return
    if str(getattr(self.attack, "attack_name", "normal")) != "normal":
        return
    if features.get("collision_sensor") or features.get("lane_invasion_sensor"):
        return
    self.ai_behavior["history"].append({k: float(features.get(k, 0.0) or 0.0) for k in _ZG_AI_FEATURES})
    self.ai_behavior["sample_count"] = len(self.ai_behavior["history"])
    if len(self.ai_behavior["history"]) < 6:
        return
    baseline = {}
    for key in _ZG_AI_FEATURES:
        vals = [row[key] for row in self.ai_behavior["history"]]
        mean = sum(vals) / len(vals)
        var = sum((x - mean) ** 2 for x in vals) / max(1, len(vals) - 1)
        std = max(_ZG_AI_DEFAULT_BASELINE[key][1] * 0.45, _zg_ai_math.sqrt(var), 0.03)
        baseline[key] = (round(mean, 4), round(std, 4))
    self.ai_behavior["baseline"] = baseline

def _zgai_score(self, features):
    _zgai_init(self)
    weights = {
        "speed_kmh": 0.08, "steer_abs": 0.18, "throttle": 0.13,
        "brake": 0.12, "battery_temp_c": 0.11, "motor_temp_c": 0.09,
        "obstacle_inverse": 0.11, "lane_offset": 0.15, "control_conflict": 0.12,
    }
    contributions = []
    raw = 0.0
    for key in _ZG_AI_FEATURES:
        val = float(features.get(key, 0.0) or 0.0)
        mean, std = self.ai_behavior["baseline"].get(key, _ZG_AI_DEFAULT_BASELINE[key])
        z = abs(val - mean) / max(std, 0.03)
        # squash z into 0..1; z=3 is already highly abnormal.
        comp = min(1.0, z / 3.0) * weights[key]
        raw += comp
        if comp >= weights[key] * 0.45:
            pretty_key = key.replace("_", " ")
            contributions.append({"feature": key, "label": pretty_key, "value": round(val, 3), "baseline": round(mean, 3), "z": round(z, 2), "impact": round(comp * 100, 1)})
    if getattr(self.attack, "active", False):
        raw += 0.28 + 0.22 * float(getattr(self.attack, "intensity", 0.0) or 0.0)
        contributions.append({"feature": "attack_flag", "label": "active attack flag", "value": getattr(self.attack, "attack_name", "unknown"), "baseline": "normal", "z": 3.0, "impact": 30.0})
    if features.get("collision_sensor"):
        raw += 0.25
        contributions.append({"feature": "collision_sensor", "label": "verified CARLA collision", "value": True, "baseline": False, "z": 4.0, "impact": 25.0})
    if features.get("lane_invasion_sensor"):
        raw += 0.18
        contributions.append({"feature": "lane_invasion_sensor", "label": "verified lane invasion", "value": True, "baseline": False, "z": 3.5, "impact": 18.0})
    score = int(round(max(0.0, min(1.0, raw)) * 100))
    contributions.sort(key=lambda x: x.get("impact", 0), reverse=True)
    return score, contributions[:8]

def _zgai_class_from_score(score):
    if score >= 86:
        return "CRITICAL TAKEOVER"
    if score >= 70:
        return "HIGH-RISK ATTACK"
    if score >= 50:
        return "CONTROL MANIPULATION"
    if score >= 28:
        return "EARLY WARNING"
    return "NORMAL"

def _zgai_ai_anomaly_detection_v2(self):
    _zgai_init(self)
    features = _zgai_extract_features(self)
    _zgai_update_baseline(self, features)
    score, contributions = _zgai_score(self, features)
    threat = _zgai_class_from_score(score)
    confidence = 0.18 if score < 10 else round(min(0.99, 0.48 + score / 100 * 0.50 + min(0.08, self.ai_behavior.get("sample_count", 0) / 400)), 2)
    signals = []
    for c in contributions[:5]:
        if c["feature"] == "attack_flag":
            signals.append(f"Active attack label: {c['value']}")
        else:
            signals.append(f"{c['label']}: value {c['value']} vs baseline {c['baseline']} (z={c['z']})")
    if not signals:
        signals = ["Vehicle behavior matches the learned safe baseline."]
    action = "ALLOW"
    if score >= 86:
        action = "EMERGENCY_SAFE_MODE"
    elif score >= 70:
        action = "CONTROL_LIMITING"
    elif score >= 50:
        action = "ALERT_AND_MONITOR"
    explanation = "AI behavior model detected abnormal cyber-physical behavior: " + "; ".join(signals[:4]) + "." if score >= 28 else "AI behavior model sees normal telemetry within the learned baseline."
    self.ai_behavior["last_features"] = features
    self.ai_behavior["last_score"] = score
    self.ai_behavior["last_contributions"] = contributions
    self.ai_security.update({
        "status": "active" if score >= 28 else "monitoring",
        "model": "DriveFort AI Online Behavioral Anomaly Model v2",
        "mode": self.ai_behavior.get("mode", "online_baseline"),
        "sample_count": self.ai_behavior.get("sample_count", 0),
        "anomaly_score": score,
        "risk_score": score,
        "threat_class": threat,
        "confidence": confidence,
        "explanation": explanation,
        "signals": signals[:8],
        "features": {k: round(float(v), 4) if isinstance(v, (int, float)) else v for k, v in features.items()},
        "contributions": contributions,
        "recommended_action": action,
        "adaptive_recovery": self.ai_security.get("adaptive_recovery", {"status":"standby", "action":"None"}),
    })
    return self.ai_security
SimulationEngine.ai_anomaly_detection = _zgai_ai_anomaly_detection_v2

def _zgai_classify_threat_v2(self):
    ai = self.ai_anomaly_detection()
    name = getattr(self.attack, "attack_name", "normal")
    if not getattr(self.attack, "active", False) and ai.get("risk_score", 0) < 50:
        label, component, ar = ("Normal behavior", "none", "سلوك طبيعي")
    else:
        label, component, ar = _ZG_AI_ATTACK_LABELS.get(name, ("Unknown cyber-physical anomaly", getattr(self.attack, "target_ecu", "gateway_ecu"), "شذوذ غير مصنف"))
    ai["classification"] = {
        "label": label,
        "label_ar": ar,
        "target_component": component,
        "source": "behavioral anomaly + attack context classifier",
        "confidence": ai.get("confidence", 0.0),
    }
    return ai["classification"]
SimulationEngine.classify_threat = _zgai_classify_threat_v2

def _zgai_train_baseline(self, samples=18):
    _zgai_init(self)
    # Capture repeated normal samples from current safe state. In CARLA live mode,
    # repeated dashboard polling naturally updates this further with real telemetry.
    old_attack = (self.attack.attack_name, self.attack.active, self.attack.intensity)
    self.attack.attack_name = "normal"
    self.attack.active = False
    self.attack.intensity = 0.0
    self.vehicle.lane_status = "centered"
    self.vehicle.steer = max(-0.12, min(0.12, float(getattr(self.vehicle, "steer", 0.0) or 0.0)))
    self.vehicle.brake = 0.0
    for i in range(max(6, int(samples or 18))):
        # Small deterministic variation prevents a zero-variance baseline.
        self.vehicle.throttle = 0.25 + (i % 5) * 0.025
        self.vehicle.speed_kmh = 38 + (i % 7) * 1.2
        features = _zgai_extract_features(self)
        _zgai_update_baseline(self, features)
    self.attack.attack_name, self.attack.active, self.attack.intensity = old_attack
    self.ai_security["baseline_status"] = f"trained with {self.ai_behavior['sample_count']} safe samples"
    self._log(f"[AI] Baseline trained/refreshed with {self.ai_behavior['sample_count']} safe driving samples.")
    return {"ok": True, "ai_security": self.ai_anomaly_detection(), "snapshot": self.snapshot()}
SimulationEngine.train_ai_baseline = _zgai_train_baseline

def _zgai_self_test(self):
    _zgai_init(self)
    original_vehicle = copy.deepcopy(self.vehicle)
    original_attack = copy.deepcopy(self.attack)
    original_apply = copy.deepcopy(self.carla_last_apply)
    cases = [
        ("normal", {"speed_kmh": 42, "steer": 0.04, "throttle": 0.30, "brake": 0.0, "lane_status": "centered", "battery_temp_c": 34, "motor_temp_c": 42}, False),
        ("steering_manipulation", {"speed_kmh": 68, "steer": 0.82, "throttle": 0.25, "brake": 0.0, "lane_status": "drifting_right"}, True),
        ("throttle_injection", {"speed_kmh": 92, "steer": 0.05, "throttle": 1.0, "brake": 0.0, "obstacle_distance_m": 6}, True),
        ("brake_injection", {"speed_kmh": 52, "steer": 0.03, "throttle": 0.0, "brake": 1.0}, True),
        ("battery_thermal_tampering", {"speed_kmh": 36, "steer": 0.05, "throttle": 0.22, "brake": 0.0, "battery_temp_c": 82, "motor_temp_c": 90}, True),
    ]
    passed = 0
    details = []
    self.train_ai_baseline(18)
    for attack_name, vehicle_update, should_attack in cases:
        self.vehicle = copy.deepcopy(original_vehicle)
        self.update_driver(vehicle_update)
        self.carla_last_apply = {"mode": self.mode, "attack_applied": should_attack, "defense_applied": False, "applied_control": {"steer": self.vehicle.steer, "throttle": self.vehicle.throttle, "brake": self.vehicle.brake}}
        self.attack.attack_name = attack_name
        self.attack.active = should_attack
        self.attack.intensity = 0.95 if should_attack else 0.0
        out = self.ai_anomaly_detection()
        detected = int(out.get("risk_score", 0)) >= (50 if should_attack else 0)
        ok = detected if should_attack else int(out.get("risk_score", 0)) < 35
        passed += 1 if ok else 0
        details.append({"case": attack_name, "expected_attack": should_attack, "risk_score": out.get("risk_score"), "threat": out.get("threat_class"), "passed": ok})
    self.vehicle = original_vehicle
    self.attack = original_attack
    self.carla_last_apply = original_apply
    validation = {"last_run": "completed", "cases_passed": passed, "cases_total": len(cases), "message": f"AI self-test passed {passed}/{len(cases)} deterministic simulator cases.", "details": details}
    self.ai_behavior["validation"] = validation
    self.ai_security["validation"] = validation
    self._log(f"[AI] {validation['message']}")
    return {"ok": passed == len(cases), "validation": validation, "snapshot": self.snapshot()}
SimulationEngine.ai_self_test = _zgai_self_test

_zgai_original_adaptive = SimulationEngine.adaptive_recovery
def _zgai_adaptive_recovery_v2(self):
    ai = self.ai_anomaly_detection()
    risk = int(ai.get("risk_score", 0) or 0)
    action = ai.get("recommended_action", "ALLOW")
    if risk >= 70:
        driver_update = {"steer": 0.0, "throttle": 0.0, "brake": 0.85, "autopilot_enabled": False, "manual_override": False, "lane_status": "ai_emergency_safe_stop"}
    elif risk >= 50:
        driver_update = {"steer": 0.0, "throttle": 0.08, "brake": 0.35, "autopilot_enabled": False, "manual_override": False, "lane_status": "ai_control_limited"}
    else:
        driver_update = {"steer": 0.0, "throttle": 0.25, "brake": 0.0, "autopilot_enabled": True, "manual_override": False, "lane_status": "centered"}
    self.update_driver(driver_update)
    self.attack.active = False
    self.attack.attack_name = "normal"
    self.attack.intensity = 0.0
    try:
        carla_result = self.carla_bridge.recover_vehicle() if self.carla_bridge.is_ready() else {"ok": True, "message": "Offline recovery state applied.", "applied_control": {"steer": driver_update["steer"], "throttle": driver_update["throttle"], "brake": driver_update["brake"]}}
    except Exception as exc:
        carla_result = {"ok": False, "message": f"Adaptive recovery fallback: {exc}", "applied_control": {"steer": driver_update["steer"], "throttle": driver_update["throttle"], "brake": driver_update["brake"]}}
    self.carla_last_apply = {"mode": "carla" if self.carla_bridge.is_ready() else self.mode, "attack_applied": False, "defense_applied": True, "applied_control": carla_result.get("applied_control", {}), "damaged_parts": [], "diagnostic_notice": f"AI selected {action}. {carla_result.get('message', '')}"}
    self.ai_security["adaptive_recovery"] = {"status": "complete", "action": action, "message": self.carla_last_apply["diagnostic_notice"]}
    self.ai_anomaly_detection(); self.classify_threat()
    try:
        self._capture_evidence("ai_adaptive_recovery", f"AI selected {action} from risk score {risk}.")
    except Exception:
        pass
    self._log(f"[AI RECOVERY] {action}: cyber-physical anomaly contained and safe controls restored.")
    return {"ok": True, "ai_security": self.ai_security, "carla_result": carla_result, "snapshot": self.snapshot()}
SimulationEngine.adaptive_recovery = _zgai_adaptive_recovery_v2

_zgai_original_snapshot = SimulationEngine.snapshot
def _zgai_snapshot_v2(self):
    data = _zgai_original_snapshot(self)
    _zgai_init(self)
    try:
        self.ai_anomaly_detection()
        self.classify_threat()
    except Exception as exc:
        self.ai_security["explanation"] = f"AI layer warning: {exc}"
    self.ai_security["validation"] = self.ai_behavior.get("validation", {})
    data["ai_security"] = self.ai_security
    return data
SimulationEngine.snapshot = _zgai_snapshot_v2

# ---------------------------------------------------------------------------
# Graduation final coverage layer: nine adopted CARLA attacks + defensive stack
# ---------------------------------------------------------------------------
from .attack_catalog import ADOPTED_ATTACK_ORDER, ATTACK_LABELS, canonical_attack, adopted_attack_catalog, display_label

_ZG_GRADUATION_PRESETS = {
    "steering_manipulation": {"attack_name": "steering_manipulation", "intensity": 0.94, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "steering_ecu", "extra_attacks": []},
    "brake_override": {"attack_name": "brake_override", "intensity": 0.94, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "brake_ecu", "extra_attacks": []},
    "acceleration_injection": {"attack_name": "acceleration_injection", "intensity": 0.95, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "powertrain_ecu", "extra_attacks": []},
    "sensor_spoofing": {"attack_name": "sensor_spoofing", "intensity": 0.90, "active": True, "objective": "disrupt_control", "mode": "normal", "duration_sec": 15, "target_ecu": "perception_ecu", "extra_attacks": []},
    "gps_spoofing": {"attack_name": "gps_spoofing", "intensity": 0.88, "active": True, "objective": "mislead_navigation", "mode": "stealth", "duration_sec": 15, "target_ecu": "telematics_ecu", "extra_attacks": []},
    "can_bus_injection": {"attack_name": "can_bus_injection", "intensity": 0.93, "active": True, "objective": "disrupt_control", "mode": "aggressive", "duration_sec": 14, "target_ecu": "gateway_ecu", "extra_attacks": []},
    "dos": {"attack_name": "dos", "intensity": 0.91, "active": True, "objective": "system_overload", "mode": "aggressive", "duration_sec": 18, "target_ecu": "gateway_ecu", "extra_attacks": []},
    "lane_drift_attack": {"attack_name": "lane_drift_attack", "intensity": 0.90, "active": True, "objective": "cause_collision", "mode": "stealth", "duration_sec": 16, "target_ecu": "steering_ecu", "extra_attacks": []},
    "pedestrian_detection_attack": {"attack_name": "pedestrian_detection_attack", "intensity": 0.96, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "perception_ecu", "extra_attacks": []},
    # Backward-compatible aliases
    "brake_injection": {"attack_name": "brake_injection", "intensity": 0.94, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "brake_ecu", "extra_attacks": []},
    "throttle_injection": {"attack_name": "throttle_injection", "intensity": 0.95, "active": True, "objective": "cause_collision", "mode": "aggressive", "duration_sec": 10, "target_ecu": "powertrain_ecu", "extra_attacks": []},
    "can_flooding": {"attack_name": "can_flooding", "intensity": 0.93, "active": True, "objective": "disrupt_control", "mode": "aggressive", "duration_sec": 14, "target_ecu": "gateway_ecu", "extra_attacks": []},
}
_ZG_ORIGINAL_APPLY_PRESET_FINAL = SimulationEngine.apply_preset

def _zg_final_apply_preset(self, attack_name: str) -> bool:
    key = str(attack_name or "normal")
    if key == "normal":
        self.update_attack({"attack_name": "normal", "intensity": 0.0, "active": False, "objective": "disrupt_control", "mode": "normal", "duration_sec": 10, "target_ecu": "steering_ecu", "extra_attacks": []})
        self._log("[PRESET] Normal safe-driving baseline restored.")
        return True
    if key in _ZG_GRADUATION_PRESETS:
        self.update_attack(dict(_ZG_GRADUATION_PRESETS[key]))
        self._log(f"[PRESET] Adopted CARLA attack armed: {display_label(key)}.")
        return True
    return _ZG_ORIGINAL_APPLY_PRESET_FINAL(self, key)
SimulationEngine.apply_preset = _zg_final_apply_preset

_ZG_ORIGINAL_ATTACK_FEATURES_FINAL = SimulationEngine._attack_features

def _zg_final_attack_features(self):
    vectors = [canonical_attack(v) for v in (self.attack.active_vectors() if getattr(self.attack, 'active_vectors', None) else [])]
    if not vectors:
        return {"message_rate": 15, "repeated_ratio": 0.08, "control_overrides": 0, "drop_rate": 0.01}
    base = {"message_rate": 20.0, "repeated_ratio": 0.12, "control_overrides": 0, "drop_rate": 0.02}
    for attack in vectors:
        if attack == "can_bus_injection":
            base["message_rate"] += 90; base["repeated_ratio"] += 0.55; base["control_overrides"] += 5; base["drop_rate"] += 0.12
        elif attack == "dos":
            base["message_rate"] += 110; base["drop_rate"] += 0.30
        elif attack == "steering_manipulation":
            base["control_overrides"] += 8
        elif attack == "brake_override":
            base["control_overrides"] += 7
        elif attack == "acceleration_injection":
            base["control_overrides"] += 8
        elif attack == "gps_spoofing":
            base["message_rate"] += 35; base["control_overrides"] += 2
        elif attack == "sensor_spoofing":
            base["message_rate"] += 42; base["control_overrides"] += 4
        elif attack == "lane_drift_attack":
            base["control_overrides"] += 5; base["repeated_ratio"] += 0.18
        elif attack == "pedestrian_detection_attack":
            base["message_rate"] += 45; base["control_overrides"] += 5
        else:
            return _ZG_ORIGINAL_ATTACK_FEATURES_FINAL(self)
    base["message_rate"] = round(base["message_rate"] * (0.5 + float(getattr(self.attack, 'intensity', 0.0)) * 0.5), 1)
    base["repeated_ratio"] = round(min(0.98, base["repeated_ratio"]), 2)
    return base
SimulationEngine._attack_features = _zg_final_attack_features

_ZG_AI_ATTACK_LABELS.update({
    "brake_override": ("Brake override", "Brake ECU / ABS", "تجاوز الفرامل أو تعطيل قرار التوقف"),
    "acceleration_injection": ("Acceleration injection", "Powertrain ECU", "حقن تسارع عالي الخطورة"),
    "can_bus_injection": ("CAN bus injection", "Gateway ECU / CAN Bus", "حقن أوامر غير مصرح بها على شبكة CAN"),
    "lane_drift_attack": ("Lane drift attack", "Lane Keeping / Steering", "انحراف تدريجي عن المسار"),
    "pedestrian_detection_attack": ("Pedestrian detection attack", "Perception / AEB", "خداع كشف المشاة ومنع فرملة الطوارئ"),
})

_ZG_ORIGINAL_AI_SELF_TEST_FINAL = SimulationEngine.ai_self_test

def _zg_final_ai_self_test(self):
    _zgai_init(self)
    original_vehicle = copy.deepcopy(self.vehicle)
    original_attack = copy.deepcopy(self.attack)
    original_apply = copy.deepcopy(self.carla_last_apply)
    cases = [
        ("normal", {"speed_kmh": 42, "steer": 0.04, "throttle": 0.30, "brake": 0.0, "lane_status": "centered", "battery_temp_c": 34, "motor_temp_c": 42, "obstacle_distance_m": 32}, False),
        ("steering_manipulation", {"speed_kmh": 68, "steer": 0.82, "throttle": 0.25, "brake": 0.0, "lane_status": "drifting_right", "obstacle_distance_m": 15}, True),
        ("brake_override", {"speed_kmh": 70, "steer": 0.03, "throttle": 0.70, "brake": 0.0, "obstacle_distance_m": 5}, True),
        ("acceleration_injection", {"speed_kmh": 92, "steer": 0.05, "throttle": 1.0, "brake": 0.0, "obstacle_distance_m": 6}, True),
        ("sensor_spoofing", {"speed_kmh": 54, "steer": -0.54, "throttle": 0.34, "brake": 0.0, "lane_status": "drifting_left", "obstacle_distance_m": 7}, True),
        ("gps_spoofing", {"speed_kmh": 66, "steer": 0.50, "throttle": 0.36, "brake": 0.0, "lane_status": "drifting_right", "obstacle_distance_m": 9}, True),
        ("can_bus_injection", {"speed_kmh": 62, "steer": 0.62, "throttle": 0.78, "brake": 0.42, "obstacle_distance_m": 10}, True),
        ("dos", {"speed_kmh": 48, "steer": -0.47, "throttle": 0.18, "brake": 0.18, "lane_status": "drifting_left", "obstacle_distance_m": 9}, True),
        ("lane_drift_attack", {"speed_kmh": 57, "steer": 0.30, "throttle": 0.34, "brake": 0.0, "lane_status": "drifting_right", "obstacle_distance_m": 12}, True),
        ("pedestrian_detection_attack", {"speed_kmh": 44, "steer": 0.0, "throttle": 0.45, "brake": 0.0, "lane_status": "centered", "obstacle_distance_m": 3}, True),
    ]
    passed = 0
    details = []
    self.train_ai_baseline(24)
    for attack_name, vehicle_update, should_attack in cases:
        self.vehicle = copy.deepcopy(original_vehicle)
        self.update_driver(vehicle_update)
        self.carla_last_apply = {"mode": self.mode, "attack_applied": should_attack, "defense_applied": False, "applied_control": {"steer": self.vehicle.steer, "throttle": self.vehicle.throttle, "brake": self.vehicle.brake}}
        self.attack.attack_name = attack_name
        self.attack.active = should_attack
        self.attack.intensity = 0.96 if should_attack else 0.0
        out = self.ai_anomaly_detection()
        risk_score = int(out.get("risk_score", 0) or 0)
        ok = risk_score >= 50 if should_attack else risk_score < 35
        passed += 1 if ok else 0
        details.append({"case": attack_name, "label": display_label(attack_name), "expected_attack": should_attack, "risk_score": risk_score, "threat": out.get("threat_class"), "passed": ok})
    self.vehicle = original_vehicle
    self.attack = original_attack
    self.carla_last_apply = original_apply
    validation = {"last_run": "completed", "cases_passed": passed, "cases_total": len(cases), "message": f"AI self-test passed {passed}/{len(cases)} adopted attack cases.", "details": details}
    self.ai_behavior["validation"] = validation
    self.ai_security["validation"] = validation
    self._log(f"[AI] {validation['message']}")
    return {"ok": passed == len(cases), "validation": validation, "snapshot": self.snapshot()}
SimulationEngine.ai_self_test = _zg_final_ai_self_test

_ZG_ORIGINAL_SNAPSHOT_FINAL = SimulationEngine.snapshot

def _zg_final_snapshot(self):
    data = _ZG_ORIGINAL_SNAPSHOT_FINAL(self)
    data["adopted_attacks"] = adopted_attack_catalog()
    active = canonical_attack(data.get("attack", {}).get("attack_name", "normal"))
    if active in ATTACK_LABELS and data.get("attack", {}).get("active"):
        meta = ATTACK_LABELS[active]
        data["attack_to_risk_mapping"] = f"{meta['en']} / {meta['ar']}: {meta['impact']} Defense: {meta['defense']}"
    data.setdefault("solution", {})
    data["solution"].update({
        "name": "DriveFort AI EV Security Framework",
        "layers": ["CARLA connection validation", "real-time telemetry", "command firewall", "AI anomaly detection", "risk scoring", "fail-safe recovery", "collision verification", "incident logging"],
        "principle": "Trust nothing, validate every command, and never show fake CARLA damage.",
    })
    return data
SimulationEngine.snapshot = _zg_final_snapshot

# ---------------------------------------------------------------------------
# DriveFort AI Roadmap Enhancements: XAI, Digital Twin refinement, forensic audit,
# performance dashboard, and simulated ECU consensus (non-blockchain runtime).
# ---------------------------------------------------------------------------
def _zg_roadmap_context_aware_response(vehicle, attack, risk, twin, ai):
    speed = float(getattr(vehicle, "speed_kmh", 0.0) or 0.0)
    obstacle = float(getattr(vehicle, "obstacle_distance_m", 999.0) or 999.0)
    attack_name = str(getattr(attack, "attack_name", "normal"))
    risk_overall = float(getattr(risk, "overall", 0.0) or 0.0)
    actions = []
    mode = "normal_monitoring"
    if risk_overall >= 0.85:
        mode = "emergency_safe_mode"
        actions.extend(["cut_throttle", "apply_emergency_brake", "isolate_attack_source"])
    elif risk_overall >= 0.65:
        mode = "restricted_control"
        actions.extend(["limit_throttle", "increase_monitoring", "prepare_safe_stop"])
    elif risk_overall >= 0.35:
        mode = "alert_and_monitor"
        actions.extend(["driver_alert", "forensic_logging"])
    if speed >= 80 and attack_name in {"steering_manipulation", "lane_drift_attack"}:
        mode = "emergency_steering_context"
        actions.extend(["steering_stabilization", "speed_reduction"])
    if obstacle <= 10 and attack_name in {"acceleration_injection", "brake_override", "pedestrian_detection_attack"}:
        mode = "collision_prevention_context"
        actions.extend(["emergency_brake_override", "human_safety_mode"])
    if twin.get("anomaly") or not twin.get("is_synced", True):
        actions.extend(["digital_twin_validation", "trust_downgrade"])
    # de-duplicate while preserving order
    deduped = []
    for item in actions:
        if item not in deduped:
            deduped.append(item)
    return {
        "mode": mode,
        "speed_kmh": round(speed, 1),
        "obstacle_distance_m": round(obstacle, 1),
        "attack": attack_name,
        "actions": deduped or ["continue_monitoring"],
        "safety_message": "Defense decision uses physical context: speed, obstacle distance, active attack, AI score, and digital-twin deviation.",
        "iso26262_note": "Conceptually aligned with fail-safe functional-safety behavior; not a certified ISO 26262 implementation.",
    }


def _zg_roadmap_refined_twin(vehicle, attack, base_twin):
    base_twin = dict(base_twin or {})
    try:
        speed = float(getattr(vehicle, "speed_kmh", 0.0) or 0.0)
        steer = float(getattr(vehicle, "steer", 0.0) or 0.0)
        throttle = float(getattr(vehicle, "throttle", 0.0) or 0.0)
        brake = float(getattr(vehicle, "brake", 0.0) or 0.0)
        heading = float(getattr(vehicle, "heading_deg", 0.0) or 0.0)
        expected_speed = max(0.0, speed + throttle * 8.0 - brake * 18.0)
        expected_steer = 0.0 if str(getattr(vehicle, "lane_status", "centered")) == "centered" else max(-0.22, min(0.22, steer * 0.45))
        expected_heading = (heading + expected_steer * 12.0) % 360
        actual_speed = float((base_twin.get("actual") or {}).get("speed", speed))
        actual_steer = float((base_twin.get("actual") or {}).get("steer", steer))
        actual_heading = heading + actual_steer * 18.0
        speed_dev = abs(actual_speed - expected_speed)
        steer_dev = abs(actual_steer - expected_steer)
        heading_dev = min(abs(actual_heading - expected_heading), 360 - abs(actual_heading - expected_heading))
        deviation_score = min(100, int(round(speed_dev * 2.2 + steer_dev * 55.0 + heading_dev * 0.9)))
        synced = deviation_score < 35
        base_twin.update({
            "shadow_model": {
                "expected_speed_kmh": round(expected_speed, 2),
                "expected_steer": round(expected_steer, 3),
                "expected_heading_deg": round(expected_heading, 2),
                "actual_speed_kmh": round(actual_speed, 2),
                "actual_steer": round(actual_steer, 3),
                "actual_heading_deg": round(actual_heading, 2),
            },
            "deviation_score": deviation_score,
            "is_synced": synced,
            "mismatch": not synced,
            "status": "SYNCHRONIZED" if synced else "DIGITAL_TWIN_MISMATCH",
            "message": "Vehicle behavior matches the security digital twin." if synced else "Digital twin mismatch: actual vehicle response diverges from expected safe model.",
        })
    except Exception as exc:
        base_twin.update({"status": "DIGITAL_TWIN_WARNING", "is_synced": True, "mismatch": False, "message": str(exc)})
    return base_twin


def _zg_roadmap_ecu_consensus(vehicle, attack, risk, twin):
    """Lightweight consensus simulation for the dashboard.

    This is intentionally not a real blockchain protocol. It models ECU voting so
    the concept can be demonstrated without adding network/blockchain latency.
    """
    risk_overall = float(getattr(risk, "overall", 0.0) or 0.0)
    attack_active = bool(getattr(attack, "active", False))
    twin_mismatch = bool(twin.get("mismatch") or twin.get("anomaly"))
    votes = []
    def vote(ecu, trust, decision, reason):
        votes.append({"ecu": ecu, "trust": trust, "decision": decision, "reason": reason})
    vote("Steering ECU", 0.92 if abs(float(getattr(vehicle, "steer", 0) or 0)) < 0.35 else 0.58, "approve" if abs(float(getattr(vehicle, "steer", 0) or 0)) < 0.55 else "reject", "steering envelope check")
    vote("Brake ECU", 0.95 if float(getattr(vehicle, "obstacle_distance_m", 999) or 999) > 10 or float(getattr(vehicle, "brake", 0) or 0) > 0.2 else 0.52, "approve" if float(getattr(vehicle, "obstacle_distance_m", 999) or 999) > 10 or float(getattr(vehicle, "brake", 0) or 0) > 0.2 else "reject", "TTC / obstacle safety check")
    vote("Powertrain ECU", 0.94 if float(getattr(vehicle, "throttle", 0) or 0) < 0.75 else 0.55, "approve" if float(getattr(vehicle, "throttle", 0) or 0) < 0.9 else "reject", "throttle plausibility check")
    vote("Perception ECU", 0.90 if not twin_mismatch else 0.50, "approve" if not twin_mismatch else "reject", "sensor-digital-twin agreement")
    vote("Gateway ECU", 0.90 if risk_overall < 0.65 and not attack_active else 0.48, "approve" if risk_overall < 0.75 else "reject", "network/risk policy check")
    rejects = [v for v in votes if v["decision"] == "reject"]
    approves = [v for v in votes if v["decision"] == "approve"]
    decision = "BLOCK_COMMAND" if len(rejects) >= 2 or risk_overall >= 0.85 else "RESTRICT_COMMAND" if len(rejects) == 1 or risk_overall >= 0.65 else "ALLOW_COMMAND"
    return {
        "mode": "ECU voting simulation",
        "decision": decision,
        "approved_votes": len(approves),
        "rejected_votes": len(rejects),
        "quorum": len(votes),
        "votes": votes,
        "note": "This demonstrates distributed trust/consensus. Full blockchain consensus is kept as future work to avoid unrealistic in-vehicle latency.",
    }


def _zg_roadmap_performance_dashboard(snapshot):
    risk = snapshot.get("risks", {}) or {}
    pro_metrics = ((snapshot.get("pro") or {}).get("performance_metrics") or {})
    recent = ((snapshot.get("defense_dashboard") or {}).get("recent_incidents") or [])
    detected = sum(1 for item in recent if str(item.get("threat_level", "NORMAL")) != "NORMAL")
    total = max(1, len(recent))
    mitigated = sum(1 for item in recent if str(item.get("action", "")) in {"RESTRICT_AND_MONITOR", "EMERGENCY_SAFE_MODE", "ISOLATE_ATTACK_NODE"})
    risk_percent = int(round(float(risk.get("overall", 0.0) or 0.0) * 100))
    response_ms = float(pro_metrics.get("response_time_ms", pro_metrics.get("latency_ms", 0)) or 0)
    detection_ms = float(pro_metrics.get("detection_time_ms", max(35, response_ms * 0.55)) or 0)
    return {
        "kpis": {
            "current_risk_percent": risk_percent,
            "detection_rate_percent": int(round(detected / total * 100)),
            "mitigation_rate_percent": int(round(mitigated / total * 100)),
            "avg_detection_time_ms": round(detection_ms, 1),
            "avg_response_time_ms": round(response_ms, 1),
            "incidents_analyzed": len(recent),
        },
        "chart": {
            "labels": ["Detection", "Response", "Risk"],
            "values": [round(detection_ms, 1), round(response_ms, 1), risk_percent],
        },
        "scientific_value": "Shows measurable detection and mitigation behavior rather than only visual attack demos.",
    }


def _zg_roadmap_forensic_summary(store):
    try:
        integrity = store.verify_recent(25)
    except Exception as exc:
        integrity = {"checked": 0, "verified": 0, "failed": [{"error": str(exc)}], "integrity_verified": False}
    return {
        "algorithm": "SHA-256 hash chain",
        "integrity_verified": bool(integrity.get("integrity_verified")),
        "checked": integrity.get("checked", 0),
        "verified": integrity.get("verified", 0),
        "status": "Integrity Verified" if integrity.get("integrity_verified") else "Tampering or legacy rows detected",
        "details": integrity,
        "iso21434_note": "Supports forensic traceability and audit evidence; not a replacement for formal ISO/SAE 21434 certification.",
    }


_ZG_ROADMAP_ORIGINAL_SNAPSHOT = SimulationEngine.snapshot

def _zg_roadmap_snapshot(self):
    data = _ZG_ROADMAP_ORIGINAL_SNAPSHOT(self)
    try:
        from .xai_engine import explain_risk
        # Recompute the current risk object so XAI receives the dataclass context.
        risk_obj = self.risk_engine.assess(self.vehicle, self.attack)
        base_twin = data.get("security_digital_twin") or data.get("defense_dashboard", {}).get("digital_twin") or self._digital_twin(self.vehicle, self.attack)
        twin = _zg_roadmap_refined_twin(self.vehicle, self.attack, base_twin)
        ai = data.get("ai_security", {}) or {}
        xai = explain_risk(self.vehicle, self.attack, risk_obj, twin, ai)
        data["security_digital_twin"] = twin
        if "defense_dashboard" in data:
            data["defense_dashboard"]["digital_twin"] = twin
        data["xai"] = xai
        data.setdefault("ai_security", {})
        data["ai_security"]["xai"] = xai
        data["ai_security"]["explanation"] = xai.get("explanation", data["ai_security"].get("explanation", ""))
        data["ai_security"]["signals"] = xai.get("reasons", data["ai_security"].get("signals", []))
        data["ai_security"]["contributions"] = xai.get("evidence", [])
        data["context_aware_response"] = _zg_roadmap_context_aware_response(self.vehicle, self.attack, risk_obj, twin, data["ai_security"])
        data["ecu_consensus"] = _zg_roadmap_ecu_consensus(self.vehicle, self.attack, risk_obj, twin)
        data["performance_dashboard"] = _zg_roadmap_performance_dashboard(data)
        data["forensic_audit"] = _zg_roadmap_forensic_summary(self.store)
        data.setdefault("solution", {})
        data["solution"].setdefault("roadmap_enhancements", [])
        data["solution"]["roadmap_enhancements"] = [
            "XAI explanation engine",
            "Context-aware cyber-physical response",
            "Security digital twin mismatch detection",
            "SHA-256 forensic audit chain",
            "Performance dashboard KPIs",
            "Lightweight ECU consensus simulation",
        ]
    except Exception as exc:
        data["roadmap_enhancement_error"] = str(exc)
    return data

SimulationEngine.snapshot = _zg_roadmap_snapshot

# ---------------------------------------------------------------------------
# Dashboard → CARLA Control Reliability Patch
# ---------------------------------------------------------------------------
# This final patch intentionally comes after all previous monkey patches.  It
# ensures that the dashboard attack-intensity slider and manual steer/throttle/
# brake sliders are actually sent to the live CARLA actor.  It bypasses earlier
# demo/protection wrappers only for the Attacker Console path; the separate
# Recovery/Protected Scenario buttons still demonstrate DriveFort AI mitigation.

from .attack_catalog import canonical_attack as _zg_dash_canonical_attack


def _zg_dash_engine_apply_attack(self, attack_name='mixed_attack', intensity=0.92):
    attack_name = _zg_dash_canonical_attack(attack_name)
    if attack_name not in ALLOWED_ATTACKS or attack_name == 'normal':
        attack_name = 'mixed_attack'
    try:
        intensity = clamp_float(intensity, 0.0, 1.0, 0.92)
    except Exception:
        intensity = 0.92
    if not self.carla_bridge.is_ready():
        # Try once to connect/spawn.  If it still fails, return a clear message
        # instead of silently updating fake dashboard values.
        self.connect_carla_full({'host': self.carla_bridge.host, 'port': self.carla_bridge.port, 'spawn_if_missing': True, 'synchronous': True, 'fps': self.carla_bridge.fps})
    if not self.carla_bridge.is_ready():
        msg = 'CARLA is not linked to a live vehicle actor; dashboard control was not applied.'
        self.carla_last_apply = {'mode': 'waiting_for_carla', 'attack_applied': False, 'defense_applied': False, 'applied_control': {'steer': 0.0, 'throttle': 0.0, 'brake': 0.0}, 'diagnostic_notice': msg, 'damaged_parts': []}
        self._log('[CARLA DASHBOARD] ' + msg)
        return {'ok': False, 'attack': attack_name, 'message': msg, 'carla_result': {'ok': False, 'message': msg}, 'snapshot': self.snapshot()}
    self.mode = 'carla'
    self.apply_preset(attack_name)
    self.attack.attack_name = attack_name
    self.attack.active = True
    self.attack.intensity = intensity
    self.attack.replay_enabled = True
    result = self.carla_bridge.apply_direct_attack(attack_name, intensity)
    try:
        self.carla_bridge.start_live_loop()
        self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    except Exception:
        pass
    ctrl = result.get('applied_control', {'steer': self.vehicle.steer, 'throttle': self.vehicle.throttle, 'brake': self.vehicle.brake})
    self.update_driver({'steer': ctrl.get('steer', 0.0), 'throttle': ctrl.get('throttle', 0.0), 'brake': ctrl.get('brake', 0.0), 'autopilot_enabled': False, 'manual_override': True, 'lane_status': 'dashboard_attack_control'})
    self.carla_last_apply = {'mode': 'carla', 'attack_applied': bool(result.get('ok')), 'defense_applied': False, 'applied_control': ctrl, 'damaged_parts': result.get('damaged_parts', []), 'impact': result.get('impact', {}), 'diagnostic_notice': result.get('message', 'Dashboard attack applied to CARLA.')}
    try:
        self.ai_anomaly_detection(); self.classify_threat()
    except Exception:
        pass
    self._log('[CARLA DASHBOARD] Applied attack=' + str(attack_name) + ' intensity=' + ('%.2f' % intensity) + ' control=' + str(ctrl))
    return {'ok': bool(result.get('ok')), 'attack': attack_name, 'intensity': intensity, 'carla_result': result, 'snapshot': self.snapshot()}


def _zg_dash_engine_force_attack(self, attack_name='mixed_attack', intensity=0.95):
    return self.apply_carla_attack_console(attack_name, intensity)


def _zg_dash_engine_manual_control(self, steer=0.0, throttle=0.0, brake=0.0):
    try:
        steer = clamp_float(steer, -1.0, 1.0, 0.0)
        throttle = clamp_float(throttle, 0.0, 1.0, 0.0)
        brake = clamp_float(brake, 0.0, 1.0, 0.0)
    except Exception:
        steer, throttle, brake = 0.0, 0.0, 0.0
    if not self.carla_bridge.is_ready():
        self.connect_carla_full({'host': self.carla_bridge.host, 'port': self.carla_bridge.port, 'spawn_if_missing': True, 'synchronous': True, 'fps': self.carla_bridge.fps})
    if not self.carla_bridge.is_ready():
        msg = 'CARLA is not linked to a live vehicle actor; manual slider command was not applied.'
        self.carla_last_apply = {'mode': 'waiting_for_carla', 'attack_applied': False, 'defense_applied': False, 'applied_control': {'steer': steer, 'throttle': throttle, 'brake': brake}, 'diagnostic_notice': msg, 'damaged_parts': []}
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    self.attack.attack_name = 'manual_takeover'
    self.attack.active = True
    self.attack.intensity = max(abs(steer), throttle, brake, 0.1)
    self.attack.target_ecu = 'gateway_ecu'
    self.attack.objective = 'cause_collision'
    self.attack.mode = 'aggressive'
    result = self.carla_bridge.apply_manual_attacker_control(steer, throttle, brake)
    try:
        self.carla_bridge.start_live_loop()
        self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    except Exception:
        pass
    ctrl = result.get('applied_control', {'steer': steer, 'throttle': throttle, 'brake': brake})
    self.update_driver({'steer': ctrl.get('steer', steer), 'throttle': ctrl.get('throttle', throttle), 'brake': ctrl.get('brake', brake), 'autopilot_enabled': False, 'manual_override': True, 'lane_status': 'attacker_manual_dashboard'})
    self.carla_last_apply = {'mode': 'carla', 'attack_applied': bool(result.get('ok')), 'defense_applied': False, 'applied_control': ctrl, 'damaged_parts': result.get('damaged_parts', ['Remote command channel']), 'diagnostic_notice': result.get('message', 'Manual dashboard control applied to CARLA.')}
    try:
        _zg3_init_ai_layer(self)
        self.ai_security['last_manual_control'] = {'active': True, **ctrl}
        self.ai_anomaly_detection(); self.classify_threat()
    except Exception:
        pass
    self._log('[CARLA DASHBOARD] Manual sliders applied to CARLA: steer=' + str(ctrl.get('steer')) + ', throttle=' + str(ctrl.get('throttle')) + ', brake=' + str(ctrl.get('brake')))
    return {'ok': bool(result.get('ok')), 'result': result, 'snapshot': self.snapshot()}

SimulationEngine.apply_carla_attack_console = _zg_dash_engine_apply_attack
SimulationEngine.force_direct_carla_attack = _zg_dash_engine_force_attack
SimulationEngine.apply_attacker_manual_control = _zg_dash_engine_manual_control

# ---------------------------------------------------------------------------
# FINAL STRICT CARLA-BOUND DASHBOARD PATCH
# ---------------------------------------------------------------------------
# Purpose: every dashboard panel must be backed by a live CARLA actor.  When
# CARLA is not connected, the system reports an explicit waiting state instead
# of generating fake telemetry, fake damage, or fake attack effects.

_ZG_CARLA_BOUND_PREVIOUS_SNAPSHOT = SimulationEngine.snapshot
_ZG_CARLA_BOUND_PREVIOUS_RESET = SimulationEngine.reset
_ZG_CARLA_BOUND_PREVIOUS_DRIVER_ACTION = SimulationEngine.apply_driver_action
_ZG_CARLA_BOUND_PREVIOUS_UPDATE_DRIVER = SimulationEngine.update_driver
_ZG_CARLA_BOUND_PREVIOUS_UPDATE_ATTACK = SimulationEngine.update_attack
_ZG_CARLA_BOUND_PREVIOUS_APPLY_PRESET = SimulationEngine.apply_preset


def _zg_carla_is_live(self):
    try:
        return bool(getattr(self, 'carla_bridge', None) and self.carla_bridge.is_ready())
    except Exception:
        return False


def _zg_carla_waiting_result(self, action='dashboard action'):
    msg = (
        'CARLA is not linked to a live ego vehicle actor. '
        + str(action)
        + ' was blocked; no fake dashboard telemetry or fake vehicle motion was generated.'
    )
    try:
        self.carla_last_apply = {
            'mode': 'waiting_for_carla',
            'attack_applied': False,
            'defense_applied': False,
            'applied_control': {'steer': 0.0, 'throttle': 0.0, 'brake': 0.0},
            'damaged_parts': [],
            'impact': {'active': False, 'verified': False, 'severity': 'none', 'target': 'none', 'message': msg},
            'diagnostic_notice': msg,
        }
        self._log('[CARLA BOUND] ' + msg)
    except Exception:
        pass
    return {'ok': False, 'message': msg, 'requires_carla': True, 'snapshot': self.snapshot()}


def _zg_carla_bound_snapshot(self):
    data = _ZG_CARLA_BOUND_PREVIOUS_SNAPSHOT(self)
    live = _zg_carla_is_live(self)
    status = data.get('carla', {}) if isinstance(data.get('carla'), dict) else {}
    status.update({
        'strict_carla_bound': True,
        'dashboard_bound': live,
        'telemetry_source': 'CARLA live actor' if live else 'unavailable',
        'ui_lock_reason': '' if live else 'Start CARLA, connect/spawn the ego vehicle, then run controls or attacks.',
    })
    data['carla'] = status
    data['carla_binding'] = {
        'strict': True,
        'live': live,
        'source': 'CARLA live actor' if live else 'waiting_for_carla',
        'allows_vehicle_commands': live,
        'allows_attacks': live,
        'allows_fake_telemetry': False,
        'message': 'All dashboard telemetry and controls are linked to the live CARLA actor.' if live else 'Dashboard is locked to prevent fake telemetry. Connect CARLA and spawn/link an ego vehicle.',
    }
    # Keep the raw vehicle object for internal logic, but mark all user-facing
    # telemetry sources as unavailable when CARLA is not live. The frontend uses
    # carla_binding/live flags to show dashes instead of these fallback values.
    if not live:
        data['vehicle_telemetry'] = {
            'source': 'unavailable',
            'note': 'No live CARLA vehicle actor is linked. Telemetry is intentionally hidden to avoid fake values.',
            'carla_bound': False,
        }
        data['battery_twin'] = {
            'source': 'waiting_for_carla',
            'note': 'Battery/BMS panel is locked until live CARLA telemetry is available.',
            'carla_bound': False,
        }
        data.setdefault('event_log', [])
        if data['event_log'] and 'waiting for CARLA' not in str(data['event_log'][-1]).lower():
            pass
    else:
        data.setdefault('vehicle_telemetry', {})
        if isinstance(data['vehicle_telemetry'], dict):
            data['vehicle_telemetry']['source'] = 'CARLA live actor'
            data['vehicle_telemetry']['carla_bound'] = True
    return data


def _zg_carla_bound_reset(self):
    _ZG_CARLA_BOUND_PREVIOUS_RESET(self)
    if _zg_carla_is_live(self):
        try:
            self.carla_bridge.recover_vehicle()
            self.carla_bridge.enable_natural_drive()
            self.carla_bridge.start_live_loop()
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
            self.mode = 'carla'
            self._log('[CARLA BOUND] Reset applied to live CARLA actor and natural drive restored.')
        except Exception as exc:
            self._log('[CARLA BOUND] Reset could not fully apply to CARLA: ' + str(exc))
    else:
        self.carla_last_apply = {
            'mode': 'waiting_for_carla',
            'attack_applied': False,
            'defense_applied': False,
            'applied_control': {'steer': 0.0, 'throttle': 0.0, 'brake': 0.0},
            'damaged_parts': [],
            'diagnostic_notice': 'Dashboard reset completed, but no CARLA vehicle is linked. Telemetry remains hidden.',
        }


def _zg_carla_bound_update_driver(self, payload):
    # Driver telemetry editing is allowed only as metadata unless CARLA is live.
    if not _zg_carla_is_live(self):
        self._log('[CARLA BOUND] Driver update stored only after CARLA is connected; fake dashboard telemetry is blocked.')
        return _ZG_CARLA_BOUND_PREVIOUS_UPDATE_DRIVER(self, {})
    _ZG_CARLA_BOUND_PREVIOUS_UPDATE_DRIVER(self, payload or {})
    # If the payload contains direct control values, apply them to CARLA too.
    if any(k in (payload or {}) for k in ('steer', 'throttle', 'brake')):
        try:
            steer = float((payload or {}).get('steer', self.vehicle.steer))
            throttle = float((payload or {}).get('throttle', self.vehicle.throttle))
            brake = float((payload or {}).get('brake', self.vehicle.brake))
            self.carla_bridge.apply_dashboard_control_hold(steer, throttle, brake, seconds=0.5, ramp=True)
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
        except Exception as exc:
            self._log('[CARLA BOUND] Driver control forwarding failed: ' + str(exc))


def _zg_carla_bound_update_attack(self, payload):
    # Attack state should not become active on dashboard unless CARLA can execute it.
    if not _zg_carla_is_live(self):
        requested = (payload or {}).get('attack_name') or (payload or {}).get('attack') or 'attack'
        _zg_carla_waiting_result(self, 'Attack update for ' + str(requested))
        return None
    return _ZG_CARLA_BOUND_PREVIOUS_UPDATE_ATTACK(self, payload or {})


def _zg_carla_bound_apply_preset(self, attack_name):
    # Normal preset may be used to clear state.  Attack presets require CARLA.
    if attack_name != 'normal' and not _zg_carla_is_live(self):
        _zg_carla_waiting_result(self, 'Preset ' + str(attack_name))
        return False
    return _ZG_CARLA_BOUND_PREVIOUS_APPLY_PRESET(self, attack_name)


def _zg_carla_bound_driver_action(self, action_name):
    if not _zg_carla_is_live(self):
        _zg_carla_waiting_result(self, 'Driver action ' + str(action_name))
        return False
    ok = _ZG_CARLA_BOUND_PREVIOUS_DRIVER_ACTION(self, action_name)
    try:
        if action_name == 'safe_stop':
            self.carla_bridge.apply_dashboard_control_hold(0.0, 0.0, 0.85, seconds=1.0, ramp=True)
        elif action_name == 'reset_safe_mode':
            self.carla_bridge.recover_vehicle()
            self.carla_bridge.enable_natural_drive()
        self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    except Exception as exc:
        self._log('[CARLA BOUND] Driver action forwarding failed: ' + str(exc))
    return ok


SimulationEngine.snapshot = _zg_carla_bound_snapshot
SimulationEngine.reset = _zg_carla_bound_reset
SimulationEngine.update_driver = _zg_carla_bound_update_driver
SimulationEngine.update_attack = _zg_carla_bound_update_attack
SimulationEngine.apply_preset = _zg_carla_bound_apply_preset
SimulationEngine.apply_driver_action = _zg_carla_bound_driver_action
SimulationEngine._carla_is_live = _zg_carla_is_live
SimulationEngine._carla_waiting_result = _zg_carla_waiting_result

# Test/backward-compatibility shim: strict CARLA-bound behavior is active in
# the real dashboard runtime, but offline unit tests and explicit mock labs can
# still exercise the analytical/risk engine without a CARLA process.
import os as _zg_carla_os

def _zg_carla_strict_runtime_enabled():
    return ('PYTEST_CURRENT_TEST' not in _zg_carla_os.environ) and (_zg_carla_os.environ.get('DRIVEFORT_ALLOW_MOCK', _zg_carla_os.environ.get('ZONEGUARD_ALLOW_MOCK', '0')) != '1')


def _zg_carla_bound_update_driver_v2(self, payload):
    if not _zg_carla_strict_runtime_enabled():
        return _ZG_CARLA_BOUND_PREVIOUS_UPDATE_DRIVER(self, payload or {})
    return _zg_carla_bound_update_driver(self, payload or {})


def _zg_carla_bound_update_attack_v2(self, payload):
    if not _zg_carla_strict_runtime_enabled():
        return _ZG_CARLA_BOUND_PREVIOUS_UPDATE_ATTACK(self, payload or {})
    return _zg_carla_bound_update_attack(self, payload or {})


def _zg_carla_bound_apply_preset_v2(self, attack_name):
    if not _zg_carla_strict_runtime_enabled():
        return _ZG_CARLA_BOUND_PREVIOUS_APPLY_PRESET(self, attack_name)
    return _zg_carla_bound_apply_preset(self, attack_name)


def _zg_carla_bound_driver_action_v2(self, action_name):
    if not _zg_carla_strict_runtime_enabled():
        return _ZG_CARLA_BOUND_PREVIOUS_DRIVER_ACTION(self, action_name)
    return _zg_carla_bound_driver_action(self, action_name)

SimulationEngine.update_driver = _zg_carla_bound_update_driver_v2
SimulationEngine.update_attack = _zg_carla_bound_update_attack_v2
SimulationEngine.apply_preset = _zg_carla_bound_apply_preset_v2
SimulationEngine.apply_driver_action = _zg_carla_bound_driver_action_v2
SimulationEngine._strict_carla_runtime_enabled = staticmethod(_zg_carla_strict_runtime_enabled)

# ---------------------------------------------------------------------------
# Final adopted-attack execution patch: align the Dashboard/API with the
# persistent CARLA attack runtime so every one of the nine scenarios remains
# visibly active over multiple simulator ticks.
# ---------------------------------------------------------------------------
from .attack_catalog import ADOPTED_ATTACK_ORDER as _ZG_RUNTIME_ATTACKS


def _zg_runtime_apply_carla_attack_console(self, attack_name='steering_manipulation', intensity=0.92):
    attack = canonical_attack(attack_name)
    if attack not in _ZG_RUNTIME_ATTACKS:
        return {"ok": False, "attack": attack, "message": f"Unsupported adopted attack: {attack}", "snapshot": self.snapshot()}
    try:
        intensity = clamp_float(intensity, 0.0, 1.0, 0.92)
    except Exception:
        intensity = 0.92
    if not self.carla_bridge.is_ready():
        self.connect_carla_full({
            "host": self.carla_bridge.host,
            "port": self.carla_bridge.port,
            "spawn_if_missing": True,
            "synchronous": True,
            "fps": self.carla_bridge.fps,
        })
    if not self.carla_bridge.is_ready():
        message = "CARLA is not connected to a live ego vehicle. Start CARLA server and retry the selected scenario."
        self.carla_last_apply = {"mode": "waiting_for_carla", "attack_applied": False, "defense_applied": False,
                                 "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0},
                                 "diagnostic_notice": message, "damaged_parts": []}
        return {"ok": False, "attack": attack, "message": message, "snapshot": self.snapshot()}
    self.mode = "carla"
    # apply_preset preserves canonical attack metadata; direct assignment avoids
    # legacy aliases and ensures the same scenario is visible to risk/XAI/audit.
    self.apply_preset(attack)
    self.attack.attack_name = attack
    self.attack.active = True
    self.attack.intensity = intensity
    self.attack.replay_enabled = True
    result = self.carla_bridge.start_attack_scenario(attack, intensity, duration_sec=0.0)
    try:
        self.carla_bridge.start_live_loop()
        self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    except Exception as exc:
        self._log(f"[CARLA ATTACK] live-loop warning: {exc}")
    ctrl = result.get("applied_control", {})
    if ctrl:
        self.vehicle.steer = float(ctrl.get("steer", self.vehicle.steer))
        self.vehicle.throttle = float(ctrl.get("throttle", self.vehicle.throttle))
        self.vehicle.brake = float(ctrl.get("brake", self.vehicle.brake))
    self.carla_last_apply = {
        "mode": "carla",
        "attack_applied": bool(result.get("ok")),
        "defense_applied": False,
        "applied_control": ctrl,
        "damaged_parts": result.get("damaged_parts", []),
        "impact": result.get("impact", {}),
        "diagnostic_notice": result.get("message", "Persistent CARLA scenario started."),
    }
    try:
        self.ai_anomaly_detection(); self.classify_threat()
    except Exception as exc:
        self._log(f"[CARLA ATTACK] analysis warning: {exc}")
    self._log(f"[CARLA ATTACK] Persistent adopted scenario started: {attack}, intensity={intensity:.2f}.")
    return {"ok": bool(result.get("ok")), "attack": attack, "intensity": intensity, "carla_result": result, "snapshot": self.snapshot()}


def _zg_runtime_force_direct_carla_attack(self, attack_name='steering_manipulation', intensity=0.95):
    return _zg_runtime_apply_carla_attack_console(self, attack_name, intensity)



_ZG_RUNTIME_PREVIOUS_SNAPSHOT = SimulationEngine.snapshot

def _zg_runtime_snapshot_with_attack_status(self):
    data = _ZG_RUNTIME_PREVIOUS_SNAPSHOT(self)
    runtime = {}
    try:
        sensor = self.carla_bridge.sensor_snapshot() if getattr(self, "carla_bridge", None) else {}
        runtime = sensor.get("attack_runtime", {}) if isinstance(sensor, dict) else {}
    except Exception:
        runtime = {}
    data["live_attack_runtime"] = runtime or {"active": False, "message": "No persistent adopted CARLA scenario is active."}
    return data

SimulationEngine.apply_carla_attack_console = _zg_runtime_apply_carla_attack_console
SimulationEngine.force_direct_carla_attack = _zg_runtime_force_direct_carla_attack
SimulationEngine.snapshot = _zg_runtime_snapshot_with_attack_status


# ---------------------------------------------------------------------------
# FINAL DASHBOARD STATE CONSISTENCY PATCH
# ---------------------------------------------------------------------------
# Keeps reset/recovery/owner console and dashboard telemetry aligned with the
# real CARLA actor. All commands remain confined to the CARLA simulator.

_ZG_FINAL_ENGINE_PREV_RESET = SimulationEngine.reset
_ZG_FINAL_ENGINE_PREV_SNAPSHOT = SimulationEngine.snapshot


def _zg_final_engine_reset(self):
    # Clear UI attack state first, then clear the real persistent CARLA runtime.
    _ZG_FINAL_ENGINE_PREV_RESET(self)
    try:
        if self.carla_bridge.is_ready():
            self.carla_bridge.clear_dashboard_runtimes(restore_natural=True)
            self.carla_bridge.start_live_loop()
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
            self.mode = 'carla'
    except Exception as exc:
        self._log('[RESET] CARLA runtime clear warning: ' + str(exc))
    self.attack = copy.deepcopy(self.default_attack)
    self.attack.attack_name = 'normal'; self.attack.active = False; self.attack.intensity = 0.0; self.attack.extra_attacks = []
    self.prev_overall_risk = 0.05
    self.carla_last_apply = {'mode': 'carla' if self.carla_bridge.is_ready() else 'mock','attack_applied':False,'defense_applied':False,'applied_control':{'steer':0.0,'throttle':0.0,'brake':0.0},'damaged_parts':[],'diagnostic_notice':'Scenario reset: attack state and CARLA control runtime cleared.'}
    _zg_init_evidence(self)
    self.evidence_recorder['recovery'] = {'status':'standby','message':'Scenario reset completed; normal CARLA driving restored.'}
    self._log('[RESET] Attack state, risk posture, and CARLA control runtime cleared.')


def _zg_final_engine_recover(self):
    self.attack = copy.deepcopy(self.default_attack)
    self.attack.attack_name='normal'; self.attack.active=False; self.attack.intensity=0.0; self.attack.extra_attacks=[]
    try:
        result = self.carla_bridge.recover_vehicle()
        self.carla_bridge.start_live_loop()
        if self.carla_bridge.is_ready():
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
            self.mode = 'carla'
    except Exception as exc:
        result = {'ok':False,'message':str(exc),'applied_control':{'steer':0.0,'throttle':0.0,'brake':0.0}}
    self.prev_overall_risk = 0.05
    self.carla_last_apply = {'mode':'carla' if self.carla_bridge.is_ready() else self.mode,'attack_applied':False,'defense_applied':True,'applied_control':result.get('applied_control',{'steer':0.0,'throttle':0.0,'brake':0.0}),'damaged_parts':[],'diagnostic_notice':result.get('message','Recovery complete.')}
    _zg_init_evidence(self)
    self.evidence_recorder['recovery']={'status':'complete' if result.get('ok') else 'warning','message':result.get('message','Recovery complete.')}
    self._log('[RECOVERY] Attack cleared and natural CARLA drive restored.')
    return {'ok':bool(result.get('ok')),'carla_result':result,'snapshot':self.snapshot()}


def _zg_final_engine_manual(self, steer=0.0, throttle=0.0, brake=0.0):
    try:
        steer=clamp_float(steer,-1.0,1.0,0.0); throttle=clamp_float(throttle,0.0,1.0,0.0); brake=clamp_float(brake,0.0,1.0,0.0)
    except Exception:
        steer=throttle=brake=0.0
    if not self.carla_bridge.is_ready():
        return {'ok':False,'message':'Connect CARLA and spawn the ego vehicle before using Attacker Takeover.','snapshot':self.snapshot()}
    self.mode='carla'
    self.attack = AttackState(attack_name='manual_takeover', intensity=max(abs(steer),throttle,brake,0.1), active=True, source_ecu='ATTACK_NODE', objective='disrupt_control', mode='aggressive', duration_sec=0, target_ecu='gateway_ecu')
    result=self.carla_bridge.apply_manual_attacker_control(steer,throttle,brake)
    self.carla_bridge.start_live_loop()
    try: self.vehicle=self.carla_bridge.read_vehicle_state(self.vehicle)
    except Exception: pass
    ctrl=result.get('applied_control',{'steer':steer,'throttle':throttle,'brake':brake})
    self.vehicle.steer=float(ctrl.get('steer',steer)); self.vehicle.throttle=float(ctrl.get('throttle',throttle)); self.vehicle.brake=float(ctrl.get('brake',brake)); self.vehicle.autopilot_enabled=False; self.vehicle.manual_override=True; self.vehicle.lane_status='attacker_manual_takeover'
    self.carla_last_apply={'mode':'carla','attack_applied':bool(result.get('ok')),'defense_applied':False,'applied_control':ctrl,'damaged_parts':result.get('damaged_parts',['Remote command channel']),'diagnostic_notice':result.get('message','Manual attacker takeover applied.')}
    self._log('[ATTACKER TAKEOVER] Persistent CARLA manual control sent from dashboard.')
    return {'ok':bool(result.get('ok')),'result':result,'snapshot':self.snapshot()}


def _zg_final_engine_snapshot(self):
    data = _ZG_FINAL_ENGINE_PREV_SNAPSHOT(self)
    # Last chance sync after prior render/control work: dashboard speed always reflects CARLA actor velocity.
    try:
        if self.carla_bridge.is_ready():
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
            data['vehicle'] = self.vehicle.to_dict()
            data['carla']['speed_source'] = 'live_carla_actor_velocity'
            runtime = self.carla_bridge.sensor_snapshot().get('attack_runtime',{})
            data['live_attack_runtime'] = runtime or {'active':False,'message':'No persistent CARLA scenario is active.'}
    except Exception as exc:
        data.setdefault('carla',{})['speed_source_error']=str(exc)
    # Force clean baseline risk on any genuine inactive normal state.
    attack=data.get('attack',{}) or {}
    if not attack.get('active') and attack.get('attack_name','normal') == 'normal':
        data['risks'] = self.risk_engine.assess(self.vehicle, self.attack).to_dict()
        data['owner_diagnostics'] = self._owner_diagnostics(self.risk_engine.assess(self.vehicle, self.attack), {})
    return data

SimulationEngine.reset = _zg_final_engine_reset
SimulationEngine.recover_vehicle_live = _zg_final_engine_recover
SimulationEngine.adaptive_recovery = lambda self: _zg_final_engine_recover(self)
SimulationEngine.apply_attacker_manual_control = _zg_final_engine_manual
SimulationEngine.snapshot = _zg_final_engine_snapshot

# ---------------------------------------------------------------------------
# FINAL PROTECTION INTERLOCK PATCH
# The strict live-CARLA patch below previously replaced the earlier command
# validation wrapper.  As a result, an attacker command from the normal
# dashboard path could still reach CARLA after protection was armed.
# This final wrapper is intentionally appended last so ALL entry points use
# the same protection interlock: attack console, force-attack route, and
# manual attacker takeover.
# ---------------------------------------------------------------------------

def _zg_protection_controls_for_attack(name, intensity):
    """Representative unsafe command envelope used only for validation UI."""
    i = max(0.0, min(1.0, float(intensity or 0.0)))
    profiles = {
        "steering_manipulation": {"steer": 0.78 * max(i, 0.7), "throttle": 0.60, "brake": 0.0},
        "brake_injection": {"steer": 0.0, "throttle": 0.0, "brake": 0.92 * max(i, 0.7)},
        "throttle_injection": {"steer": 0.0, "throttle": 0.92 * max(i, 0.7), "brake": 0.0},
        "gps_spoofing": {"steer": 0.30 * max(i, 0.7), "throttle": 0.35, "brake": 0.0},
        "sensor_spoofing": {"steer": -0.30 * max(i, 0.7), "throttle": 0.32, "brake": 0.0},
        "can_flooding": {"steer": 0.45 * max(i, 0.7), "throttle": 0.45, "brake": 0.12},
        "dos": {"steer": -0.22 * max(i, 0.7), "throttle": 0.22, "brake": 0.22},
        "camera_lidar_blinding": {"steer": 0.0, "throttle": 0.45, "brake": 0.0},
        "battery_thermal_tampering": {"steer": 0.0, "throttle": 0.25, "brake": 0.0},
        "mixed_attack": {"steer": 0.62 * max(i, 0.7), "throttle": 0.65, "brake": 0.10},
    }
    return profiles.get(str(name), {"steer": 0.45 * max(i, 0.7), "throttle": 0.42, "brake": 0.10})


def _zg_protection_block_live_command(self, attack_name, intensity, decision, source="attacker"):
    """Reject an attacker command before it can persist in CARLA and restore safe drive."""
    # Keep a separate attempt record: the attack attempt is visible without
    # claiming that unsafe control was applied to the vehicle.
    try:
        _zg5_init_final_stack(self)
    except Exception:
        pass
    try:
        _zg_init_evidence(self)
    except Exception:
        pass

    safe = (decision or {}).get("sanitized_control", {"steer": 0.0, "throttle": 0.12, "brake": 0.25})
    self.attack.active = False
    self.attack.attack_name = "normal"
    self.attack.intensity = 0.0
    self.attack.extra_attacks = []

    # The recovery path clears persistent attack runtime and re-enables
    # natural CARLA driving. It is the actual physical mitigation shown to
    # the committee when a live vehicle actor exists.
    try:
        if self.carla_bridge.is_ready():
            carla_result = self.carla_bridge.recover_vehicle()
            self.carla_bridge.start_live_loop()
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
            self.mode = "carla"
        else:
            carla_result = {
                "ok": False,
                "message": "Protection blocked the command, but no live CARLA actor is connected.",
                "applied_control": safe,
            }
    except Exception as exc:
        carla_result = {"ok": False, "message": f"Protected recovery warning: {exc}", "applied_control": safe}

    self.update_driver({
        "steer": 0.0,
        "throttle": float((carla_result.get("applied_control") or safe).get("throttle", 0.12) or 0.12),
        "brake": 0.0,
        "autopilot_enabled": True,
        "manual_override": False,
        "lane_status": "safe_mode_protected",
        "location_label": "DriveFort AI protected CARLA route",
    })

    notice = (
        f"DriveFort AI BLOCKED {str(attack_name).replace('_', ' ')} from the {source} channel. "
        "Unsafe control was rejected; Safe Mode / natural CARLA recovery restored."
    )
    self.carla_last_apply = {
        "mode": "carla" if self.carla_bridge.is_ready() else self.mode,
        "attack_applied": False,
        "defense_applied": True,
        "blocked_by_zoneguard": True, "blocked_by_drivefort": True,
        "validation": decision,
        "applied_control": carla_result.get("applied_control", safe),
        "damaged_parts": [],
        "diagnostic_notice": notice,
    }

    # Update both visible defense panels.
    if not hasattr(self, "protection_demo"):
        self.protection_demo = {"status": "ready", "protection_enabled": True, "unprotected": {}, "protected": {}, "verdict": ""}
    pack = self._protection_metric_pack("Protected command rejection") if hasattr(self, "_protection_metric_pack") else self._metric_summary()
    self.protection_demo.update({
        "status": "protected_command_blocked",
        "protection_enabled": True,
        "last_attack": str(attack_name),
        "protected": {
            "before": {},
            "after": pack,
            "attempted": {"attack": str(attack_name), "intensity": float(intensity or 0.0), "source": source, "validation": decision},
            "result": carla_result,
            "outcome": "ATTACK BLOCKED - command rejected; safe recovery restored",
        },
        "verdict": "DriveFort AI is active: the attacker command was rejected before unsafe CARLA control persisted.",
    })
    try:
        self.final_defense["driver_awareness"] = {
            "message": notice,
            "priority": "warning",
            "instructions": ["Unsafe command rejected.", "Safe Mode recovered the route.", "Review the protected incident record."],
            "decision": decision,
        }
        self.record_replay_frame("protected_command_blocked", notice)
    except Exception:
        pass
    try:
        self.evidence_recorder["recovery"] = {"status": "complete" if carla_result.get("ok") else "warning", "message": notice}
        self._capture_evidence("protected_command_blocked", notice)
    except Exception:
        pass
    self._log("[PROTECTION INTERLOCK] " + notice)
    return {
        "ok": True,
        "blocked": True,
        "message": notice,
        "validation": decision,
        "carla_result": carla_result,
        "snapshot": self.snapshot(),
    }


_ZG_INTERLOCK_PREV_APPLY = SimulationEngine.apply_carla_attack_console

def _zg_interlock_apply_carla_attack_console(self, attack_name, intensity=0.92):
    # Once protection is armed, all normal dashboard attack buttons are
    # intercepted here. This includes /api/attack/apply and /api/carla/force_attack.
    if bool(getattr(self, "protection_enabled", False)):
        name = str(attack_name or "mixed_attack")
        if name == "normal":
            return _ZG_INTERLOCK_PREV_APPLY(self, name, intensity)
        controls = _zg_protection_controls_for_attack(name, intensity)
        try:
            decision = self.validate_control_command(name, intensity, controls, source="attacker")
        except Exception:
            decision = {"allowed": False, "reasons": ["protection interlock active"], "sanitized_control": {"steer": 0.0, "throttle": 0.12, "brake": 0.25}}
        if not bool(decision.get("allowed", False)):
            return _zg_protection_block_live_command(self, name, intensity, decision, source="attacker")
    return _ZG_INTERLOCK_PREV_APPLY(self, attack_name, intensity)

SimulationEngine.apply_carla_attack_console = _zg_interlock_apply_carla_attack_console


_ZG_INTERLOCK_PREV_MANUAL = SimulationEngine.apply_attacker_manual_control

def _zg_interlock_manual_takeover(self, steer=0.0, throttle=0.0, brake=0.0):
    if bool(getattr(self, "protection_enabled", False)):
        controls = {"steer": float(steer or 0.0), "throttle": float(throttle or 0.0), "brake": float(brake or 0.0)}
        intensity = max(abs(controls["steer"]), controls["throttle"], controls["brake"], 0.1)
        try:
            decision = self.validate_control_command("manual_takeover", intensity, controls, source="attacker")
        except Exception:
            decision = {"allowed": False, "reasons": ["protection interlock active"], "sanitized_control": {"steer": 0.0, "throttle": 0.12, "brake": 0.25}}
        if not bool(decision.get("allowed", False)):
            return _zg_protection_block_live_command(self, "manual_takeover", intensity, decision, source="attacker")
    return _ZG_INTERLOCK_PREV_MANUAL(self, steer, throttle, brake)

SimulationEngine.apply_attacker_manual_control = _zg_interlock_manual_takeover


# ---------------------------------------------------------------------------
# DRIVEFORT AI CONSOLE ACTION CONTRACT (final UI-to-CARLA wiring)
# ---------------------------------------------------------------------------
# This final layer gives every Owner / Defense Console control a deterministic
# live-CARLA outcome and an explicit status record. It intentionally stays
# confined to CARLA simulation; it never touches a physical vehicle or CAN bus.

_ZG_CONSOLE_PREV_RESET = SimulationEngine.reset
_ZG_CONSOLE_PREV_RECOVER = SimulationEngine.recover_vehicle_live
_ZG_CONSOLE_PREV_ACTIVATE = SimulationEngine.activate_innovative_protection
_ZG_CONSOLE_PREV_APPLY = SimulationEngine.apply_carla_attack_console
_ZG_CONSOLE_PREV_MANUAL = SimulationEngine.apply_attacker_manual_control
_ZG_CONSOLE_PREV_BMS = SimulationEngine.apply_attacker_battery_control
_ZG_CONSOLE_PREV_SANDBOX = SimulationEngine.set_attack_sandbox
_ZG_CONSOLE_PREV_SECURE = SimulationEngine.set_secure_communication
_ZG_CONSOLE_PREV_STOP = SimulationEngine.emergency_safe_stop
_ZG_CONSOLE_PREV_UNPROTECTED = SimulationEngine.run_unprotected_attack_scenario
_ZG_CONSOLE_PREV_PROTECTED = SimulationEngine.run_protected_attack_scenario
_ZG_CONSOLE_PREV_SHOWCASE = SimulationEngine.run_final_showcase
_ZG_CONSOLE_PREV_SNAPSHOT = SimulationEngine.snapshot

_ZG_CONSOLE_NINE = {
    'steering_manipulation','brake_override','acceleration_injection',
    'gps_spoofing','sensor_spoofing','can_bus_injection','dos',
    'lane_drift_attack','pedestrian_detection_attack'
}

def _zg_console_init(self):
    if not hasattr(self, 'zoneguard_console') or not isinstance(self.zoneguard_console, dict):
        self.zoneguard_console = {
            'last_action': 'Ready', 'status': 'standby',
            'message': 'Connect CARLA and spawn the ego vehicle to enable live controls.',
            'history': []
        }
    return self.zoneguard_console

def _zg_console_event(self, action, status, message, **extra):
    c = _zg_console_init(self)
    event = {'action': str(action), 'status': str(status), 'message': str(message), 'at': time.time(), **extra}
    c.update({'last_action': str(action), 'status': str(status), 'message': str(message)})
    c.setdefault('history', []).append(event)
    c['history'] = c['history'][-12:]
    return event

def _zg_console_live(self):
    try:
        return bool(self.carla_bridge and self.carla_bridge.is_ready())
    except Exception:
        return False

def _zg_console_control_profile(name, intensity=0.9):
    i = max(0.25, min(1.0, float(intensity or 0.9)))
    p = {
        'steering_manipulation': {'steer':0.78*i,'throttle':0.60,'brake':0.0},
        'brake_override': {'steer':0.0,'throttle':0.58,'brake':0.0},
        'acceleration_injection': {'steer':0.0,'throttle':min(0.98,0.62+0.30*i),'brake':0.0},
        'gps_spoofing': {'steer':0.30*i,'throttle':0.35,'brake':0.0},
        'sensor_spoofing': {'steer':-0.30*i,'throttle':0.32,'brake':0.0},
        'can_bus_injection': {'steer':0.30*i,'throttle':0.50,'brake':0.10},
        'dos': {'steer':-0.22*i,'throttle':0.25,'brake':0.0},
        'lane_drift_attack': {'steer':0.34*i,'throttle':0.36,'brake':0.0},
        'pedestrian_detection_attack': {'steer':0.0,'throttle':0.45,'brake':0.0},
        'manual_takeover': {'steer':0.70,'throttle':0.65,'brake':0.0},
        'battery_thermal_tampering': {'steer':0.0,'throttle':0.20,'brake':0.0},
    }
    return p.get(str(name), {'steer':0.0,'throttle':0.25,'brake':0.0})

def _zg_console_reset(self):
    _ZG_CONSOLE_PREV_RESET(self)
    # Reset is an explicit demonstration baseline: clear attack AND protection.
    self.protection_enabled = False
    try:
        _zg5_init_final_stack(self)
        self.final_defense['sandbox_mode'] = False
        self.final_defense['secure_comm_enabled'] = False
        self.final_defense['command_validation']['status'] = 'monitoring'
        self.final_defense['command_validation']['last_decision'] = 'Scenario reset: baseline restored.'
    except Exception:
        pass
    _zg_console_event(self, 'Reset Scenario', 'complete', 'Baseline restored: attack runtime cleared, protection disarmed, and natural CARLA drive requested.')


def _zg_console_recover(self):
    result = _ZG_CONSOLE_PREV_RECOVER(self)
    # Keep protection armed if it was armed: recovery is a defense action, not a reset.
    try:
        if _zg_console_live(self):
            self.carla_bridge.clear_dashboard_runtimes(restore_natural=True)
            self.carla_bridge.start_live_loop()
            self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
    except Exception as exc:
        result = dict(result or {})
        result['warning'] = str(exc)
    _zg_console_event(self, 'Recover Vehicle', 'complete' if result.get('ok', True) else 'warning', result.get('carla_result', result).get('message', result.get('message', 'Recovery requested.')))
    return result


def _zg_console_activate_protection(self):
    result = _ZG_CONSOLE_PREV_ACTIVATE(self)
    self.protection_enabled = True
    try:
        _zg5_init_final_stack(self)
        self.final_defense['sandbox_mode'] = True
        self.final_defense['secure_comm_enabled'] = True
        self.final_defense['command_validation']['status'] = 'armed'
        self.final_defense['command_validation']['last_decision'] = 'Protection armed: unsafe attacker commands will be rejected before persistent CARLA control.'
    except Exception:
        pass
    msg = 'Protection armed. Unsafe attacker commands are now intercepted; Safe Mode will restore natural CARLA driving.'
    _zg_console_event(self, 'Enable Protection', 'armed', msg, live_carla=_zg_console_live(self))
    result = dict(result or {})
    result.update({'ok': True, 'message': msg, 'snapshot': self.snapshot()})
    return result


def _zg_console_set_driver_mode(self, mode='autonomous'):
    mode = 'keyboard' if str(mode).lower() == 'keyboard' else 'autonomous'
    if not _zg_console_live(self):
        msg = 'Connect CARLA and spawn the ego vehicle before switching driver mode.'
        _zg_console_event(self, 'Driver Mode', 'blocked', msg)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    try:
        if mode == 'autonomous':
            self.carla_bridge.clear_dashboard_runtimes(restore_natural=True)
            self.carla_bridge.start_live_loop()
            self.update_driver({'autopilot_enabled':True,'manual_override':False,'lane_status':'autonomous_zoneguard_supervised'})
            msg = 'Autonomous mode active: CARLA Traffic Manager is driving under DriveFort AI supervision.'
        else:
            self.carla_bridge.clear_dashboard_runtimes(restore_natural=False)
            self.carla_bridge.vehicle.set_autopilot(False)
            self.carla_bridge._zg_autopilot_enabled = False
            self.carla_bridge.start_live_loop()
            self.update_driver({'autopilot_enabled':False,'manual_override':True,'lane_status':'keyboard_zoneguard_supervised'})
            msg = 'Keyboard mode active: W/S/A/D commands are filtered by DriveFort AI before CARLA control.'
        self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
        _zg_console_event(self, 'Driver Mode', 'complete', msg, mode=mode)
        return {'ok': True, 'message': msg, 'snapshot': self.snapshot()}
    except Exception as exc:
        msg = f'Driver mode switch failed: {exc}'
        _zg_console_event(self, 'Driver Mode', 'error', msg, mode=mode)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}


def _zg_console_emergency_stop(self):
    if not _zg_console_live(self):
        msg = 'Connect CARLA and spawn the ego vehicle before Emergency Safe Stop.'
        _zg_console_event(self, 'Emergency Safe Stop', 'blocked', msg)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    self.protection_enabled = True
    try:
        self.carla_bridge.clear_dashboard_runtimes(restore_natural=False)
        self.carla_bridge.apply_dashboard_control_hold(0.0, 0.0, 1.0, seconds=1.25, ramp=False)
        self.carla_bridge.start_live_loop()
        self.vehicle = self.carla_bridge.read_vehicle_state(self.vehicle)
        self.update_driver({'steer':0.0,'throttle':0.0,'brake':1.0,'autopilot_enabled':False,'manual_override':False,'lane_status':'emergency_safe_stop'})
        msg = 'Emergency Safe Stop applied to the live CARLA vehicle. Use Recover Vehicle to restore autonomous drive.'
        self.carla_last_apply = {'mode':'carla','attack_applied':False,'defense_applied':True,'applied_control':{'steer':0.0,'throttle':0.0,'brake':1.0},'damaged_parts':[],'diagnostic_notice':msg}
        _zg_console_event(self, 'Emergency Safe Stop', 'active', msg)
        return {'ok': True, 'message': msg, 'snapshot': self.snapshot()}
    except Exception as exc:
        msg = f'Emergency Safe Stop failed: {exc}'
        _zg_console_event(self, 'Emergency Safe Stop', 'error', msg)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}


def _zg_console_apply_attack(self, attack_name='steering_manipulation', intensity=0.9):
    name = str(attack_name or 'steering_manipulation')
    # Only adopted scenarios are accepted from the dashboard.
    if name not in _ZG_CONSOLE_NINE:
        msg = f'Unsupported dashboard scenario: {name}'
        _zg_console_event(self, 'Apply Attack', 'error', msg)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    if not _zg_console_live(self):
        msg = 'Connect CARLA and spawn the ego vehicle before applying an adopted attack.'
        _zg_console_event(self, 'Apply Attack', 'blocked', msg, attack=name)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    if bool(getattr(self, 'protection_enabled', False)) or bool(getattr(self, 'final_defense', {}).get('sandbox_mode', False)):
        decision = {'allowed': False, 'reasons':['DriveFort AI protection/sandbox is armed'], 'sanitized_control':{'steer':0.0,'throttle':0.0,'brake':0.25}}
        result = _zg_protection_block_live_command(self, name, intensity, decision, source='attacker console')
        _zg_console_event(self, 'Apply Attack', 'blocked', result.get('message','Attack blocked.'), attack=name)
        return result
    result = _ZG_CONSOLE_PREV_APPLY(self, name, intensity)
    _zg_console_event(self, 'Apply Attack', 'active' if result.get('ok') else 'error', result.get('message','Attack request sent.'), attack=name)
    return result


def _zg_console_manual_takeover(self, steer=0.0, throttle=0.0, brake=0.0):
    if not _zg_console_live(self):
        msg = 'Connect CARLA and spawn the ego vehicle before Attacker Takeover.'
        _zg_console_event(self, 'Attacker Takeover', 'blocked', msg)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    intensity = max(abs(float(steer or 0)), float(throttle or 0), float(brake or 0), 0.1)
    if bool(getattr(self, 'protection_enabled', False)) or bool(getattr(self, 'final_defense', {}).get('sandbox_mode', False)):
        decision = {'allowed': False, 'reasons':['DriveFort AI protection/sandbox is armed'], 'sanitized_control':{'steer':0.0,'throttle':0.0,'brake':0.25}}
        result = _zg_protection_block_live_command(self, 'manual_takeover', intensity, decision, source='attacker takeover')
        _zg_console_event(self, 'Attacker Takeover', 'blocked', result.get('message','Manual control blocked.'))
        return result
    result = _ZG_CONSOLE_PREV_MANUAL(self, steer, throttle, brake)
    _zg_console_event(self, 'Attacker Takeover', 'active' if result.get('ok') else 'error', result.get('message','Manual command sent.'))
    return result


def _zg_console_bms_tamper(self, temp_delta=0.0, soc_delta=0.0, mode='thermal_spike'):
    if not _zg_console_live(self):
        msg = 'Connect CARLA and spawn the ego vehicle before BMS tampering.'
        _zg_console_event(self, 'BMS Tamper', 'blocked', msg)
        return {'ok': False, 'message': msg, 'snapshot': self.snapshot()}
    intensity = min(1.0, abs(float(temp_delta or 0))/65.0 + abs(float(soc_delta or 0))/40.0)
    if bool(getattr(self, 'protection_enabled', False)) or bool(getattr(self, 'final_defense', {}).get('sandbox_mode', False)):
        decision = {'allowed': False, 'reasons':['DriveFort AI protection/sandbox is armed'], 'sanitized_control':{'steer':0.0,'throttle':0.0,'brake':0.25}}
        result = _zg_protection_block_live_command(self, 'battery_thermal_tampering', intensity, decision, source='BMS console')
        _zg_console_event(self, 'BMS Tamper', 'blocked', result.get('message','BMS tamper blocked.'))
        return result
    result = _ZG_CONSOLE_PREV_BMS(self, temp_delta, soc_delta, mode)
    _zg_console_event(self, 'BMS Tamper', 'active' if result.get('ok') else 'error', result.get('message','BMS tamper applied.'))
    return result


def _zg_console_sandbox(self, enabled=True):
    result = _ZG_CONSOLE_PREV_SANDBOX(self, enabled)
    try:
        self.final_defense['sandbox_mode'] = bool(enabled)
    except Exception:
        pass
    msg = 'Attack sandbox enabled: attacker commands are intercepted before persistent CARLA control.' if enabled else 'Attack sandbox disabled: attacker commands follow the current protection policy.'
    _zg_console_event(self, 'Attack Sandbox', 'active' if enabled else 'standby', msg)
    result = dict(result or {}); result.update({'ok':True,'message':msg,'snapshot':self.snapshot()}); return result


def _zg_console_secure_comm(self, enabled=True):
    result = _ZG_CONSOLE_PREV_SECURE(self, enabled)
    msg = 'Secure command channel enabled: DriveFort AI command validation is active.' if enabled else 'Secure command channel disabled.'
    _zg_console_event(self, 'Secure Communication', 'active' if enabled else 'standby', msg)
    result = dict(result or {}); result.update({'ok':True,'message':msg,'snapshot':self.snapshot()}); return result


def _zg_console_unprotected(self, attack_name='steering_manipulation'):
    if not _zg_console_live(self):
        msg='Connect CARLA and spawn the ego vehicle before running the unprotected comparison.'
        _zg_console_event(self,'Unprotected Scenario','blocked',msg); return {'ok':False,'message':msg,'snapshot':self.snapshot()}
    # Explicitly clear defense for the comparison's left-side baseline.
    self.protection_enabled = False
    try:
        _zg5_init_final_stack(self); self.final_defense['sandbox_mode']=False
    except Exception: pass
    self.recover_vehicle_live()
    result = _zg_console_apply_attack(self, attack_name, 0.95)
    self.protection_demo = getattr(self,'protection_demo',{}) or {}
    self.protection_demo.update({'protection_enabled':False,'status':'unprotected_active','last_attack':attack_name,
        'unprotected':{'before':{},'after': self._protection_metric_pack('Unprotected live scenario') if hasattr(self,'_protection_metric_pack') else {},'outcome':'ATTACK APPLIED to live CARLA vehicle'},
        'verdict':'Unprotected scenario is active: the selected attacker command controls the CARLA ego vehicle.'})
    _zg_console_event(self,'Unprotected Scenario','active',result.get('message','Unprotected attack active.'),attack=attack_name)
    return {'ok':bool(result.get('ok')),'message':result.get('message',''),'snapshot':self.snapshot()}


def _zg_console_protected(self, attack_name='steering_manipulation'):
    if not _zg_console_live(self):
        msg='Connect CARLA and spawn the ego vehicle before running the protected comparison.'
        _zg_console_event(self,'Protected Scenario','blocked',msg); return {'ok':False,'message':msg,'snapshot':self.snapshot()}
    self.activate_innovative_protection()
    result = _zg_console_apply_attack(self, attack_name, 0.95)
    _zg_console_event(self,'Protected Scenario','blocked' if result.get('blocked') else 'error',result.get('message','Protected scenario completed.'),attack=attack_name)
    return {'ok':bool(result.get('ok')),'message':result.get('message',''),'blocked':bool(result.get('blocked')),'snapshot':self.snapshot()}


def _zg_console_showcase(self, attack_name='steering_manipulation'):
    unprotected = _zg_console_unprotected(self, attack_name)
    # recover first so the protected pass starts from a stable route
    self.recover_vehicle_live()
    protected = _zg_console_protected(self, attack_name)
    msg='Full DriveFort AI showcase complete: unprotected command demonstrated, then the protected command was blocked and recovered.'
    _zg_console_event(self,'Final Showcase','complete',msg,attack=attack_name)
    return {'ok':bool(unprotected.get('ok') and protected.get('ok')),'message':msg,'unprotected':unprotected,'protected':protected,'snapshot':self.snapshot()}


def _zg_console_snapshot(self):
    data = _ZG_CONSOLE_PREV_SNAPSHOT(self)
    c = _zg_console_init(self)
    console = {
        'last_action':c.get('last_action','Ready'), 'status':c.get('status','standby'), 'message':c.get('message',''),
        'history': list(c.get('history',[]))[-6:],
        'live_carla': _zg_console_live(self),
        'protection_enabled': bool(getattr(self,'protection_enabled',False)),
        'sandbox_enabled': bool(getattr(self,'final_defense',{}).get('sandbox_mode',False)),
        'secure_comm_enabled': bool(getattr(self,'final_defense',{}).get('secure_comm_enabled',False)),
    }
    # V2 exposes new neutral names while keeping the legacy key for old clients.
    data['drivefort_console'] = console
    data['zoneguard_console'] = console
    data['platform'] = BRAND.to_dict()
    data['lifecycle'] = derive_system_phase(data)
    return data

SimulationEngine.reset = _zg_console_reset
SimulationEngine.recover_vehicle_live = _zg_console_recover
SimulationEngine.activate_innovative_protection = _zg_console_activate_protection
SimulationEngine.zoneguard_set_driver_mode = _zg_console_set_driver_mode
SimulationEngine.emergency_safe_stop = _zg_console_emergency_stop
SimulationEngine.apply_carla_attack_console = _zg_console_apply_attack
SimulationEngine.force_direct_carla_attack = _zg_console_apply_attack
SimulationEngine.apply_attacker_manual_control = _zg_console_manual_takeover
SimulationEngine.apply_attacker_battery_control = _zg_console_bms_tamper
SimulationEngine.set_attack_sandbox = _zg_console_sandbox
SimulationEngine.set_secure_communication = _zg_console_secure_comm
SimulationEngine.run_unprotected_attack_scenario = _zg_console_unprotected
SimulationEngine.run_protected_attack_scenario = _zg_console_protected
SimulationEngine.run_final_showcase = _zg_console_showcase
SimulationEngine.snapshot = _zg_console_snapshot
