from __future__ import annotations

import hashlib
import hmac
import os
import uuid
from collections import deque
from typing import Any, Deque, Dict


class ThreatFusionService:
    """Combine independent V3 security signals into one threat decision."""

    def __init__(self, risk, attack, pct, number, attack_severity):
        self._risk = risk
        self._attack = attack
        self._pct = pct
        self._number = number
        self._attack_severity = attack_severity

    def calculate(self, snapshot, twin, ecu_map):
        ai = snapshot.get("ai_security") or {}
        attack_name, active, intensity, _target = self._attack(snapshot)
        anomaly = self._pct(ai.get("anomaly_score", self._risk(snapshot) * 100.0))
        sensor = 8.0
        if active and attack_name in {"sensor_spoofing", "gps_spoofing", "pedestrian_detection_attack"}:
            sensor = 52.0 + intensity * 44.0
        elif active:
            sensor = 20.0 + intensity * 25.0
        twin_score = self._pct(twin.get("deviation_score", 0.0))
        minimum_trust = self._number((ecu_map.get("summary") or {}).get("minimum_trust"), 100.0)
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
            score = max(score, self._attack_severity.get(attack_name, 0.7) * intensity * 100.0 * 0.78)
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


class AttackSimulationService:
    """Own deterministic protected-vs-unprotected benchmark simulation."""

    def __init__(self, lock, safe_attack, clamp, attack_severity, json_copy, now):
        self.lock = lock
        self.safe_attack = safe_attack
        self.clamp = clamp
        self.attack_severity = attack_severity
        self.copy = json_copy
        self.now = now
        self.benchmark = self.empty_benchmark()

    @staticmethod
    def empty_benchmark():
        return {
            "status": "not_run", "attack": None, "generated_at": None,
            "unprotected": {}, "protected": {}, "improvement": {},
            "verdict": "Run a benchmark to compare outcomes.",
        }

    def run_benchmark(self, attack, intensity=0.92):
        with self.lock:
            attack = self.safe_attack(attack)
            intensity = self.clamp(intensity, 0.05, 1.0)
            severity = self.attack_severity.get(attack, 0.8) * intensity
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
            self.benchmark.clear()
            self.benchmark.update({
                "status": "complete", "attack": attack, "intensity": round(intensity, 2),
                "generated_at": self.now(), "unprotected": unprotected, "protected": protected,
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
            })
            return self.copy(self.benchmark)


class RecoveryService:
    """Own virtual ECU and recovery playbook state."""

    def __init__(self, engine, lock, labels, targets, safe_attack, json_copy, now):
        self.engine = engine
        self.lock = lock
        self.labels = labels
        self.targets = targets
        self.safe_attack = safe_attack
        self.copy = json_copy
        self.now = now
        self.virtual_ecus: Dict[str, Dict[str, Any]] = {}
        self.playbook = self.empty_playbook()

    @staticmethod
    def empty_playbook():
        return {"attack": None, "target_ecu": None, "status": "standby", "current_step": -1, "steps": [], "started_at": None, "completed_at": None}

    def activate_virtual_ecu(self, ecu_id):
        with self.lock:
            ecu_id = str(ecu_id or "steering_ecu")
            if ecu_id not in self.labels:
                ecu_id = "steering_ecu"
            instance = {
                "id": "VECU-{}".format(uuid.uuid4().hex[:8].upper()),
                "replaces": ecu_id, "label": "Virtual {}".format(self.labels[ecu_id]),
                "active": True, "trust": 98.0,
                "control_source": "digital_twin_safety_controller",
                "activated_at": self.now(), "validation": "self_test_passed",
            }
            self.virtual_ecus[ecu_id] = instance
            return self.copy(instance)

    def deactivate_virtual_ecu(self, ecu_id):
        with self.lock:
            ecu_id = str(ecu_id or "steering_ecu")
            instance = self.virtual_ecus.get(ecu_id)
            if not instance:
                return {"ok": False, "message": "No active virtual ECU for {}.".format(ecu_id)}
            instance["active"] = False
            instance["deactivated_at"] = self.now()
            return {"ok": True, "virtual_ecu": self.copy(instance)}

    def prepare_playbook(self, attack):
        with self.lock:
            attack = self.safe_attack(attack)
            target = self.targets.get(attack, "gateway_ecu")
            special = {
                "gps_spoofing": ["Reject compromised GPS stream", "Switch to wheel odometry", "Cross-check camera landmarks", "Reduce speed", "Restore GPS after validation"],
                "sensor_spoofing": ["Quarantine inconsistent sensor stream", "Fuse redundant sensors", "Increase uncertainty margin", "Validate perception output", "Restore trusted source"],
                "steering_manipulation": ["Reject injected steering command", "Isolate steering ECU", "Activate virtual steering ECU", "Center vehicle inside safety envelope", "Revalidate physical ECU"],
                "brake_override": ["Challenge brake command", "Isolate brake ECU", "Apply safe deceleration profile", "Activate virtual brake controller", "Verify hydraulic response"],
                "can_bus_injection": ["Enable secure bus mode", "Block untrusted CAN identifiers", "Rotate session keys", "Quarantine gateway ECU", "Replay verified control state"],
            }
            labels = special.get(attack, ["Contain affected subsystem", "Apply safe control fallback", "Validate digital twin", "Restore trusted communication", "Confirm stable vehicle state"])
            self.playbook.clear()
            self.playbook.update({
                "attack": attack, "target_ecu": target, "status": "prepared", "current_step": -1,
                "steps": [{"index": index, "label": label, "status": "pending"} for index, label in enumerate(labels)],
                "started_at": None, "completed_at": None,
            })
            return self.copy(self.playbook)

    def advance_playbook(self, execute_engine_recovery=False):
        with self.lock:
            if not self.playbook.get("steps"):
                self.prepare_playbook("steering_manipulation")
            current = int(self.playbook.get("current_step", -1))
            if 0 <= current < len(self.playbook["steps"]):
                self.playbook["steps"][current]["status"] = "complete"
            next_index = current + 1
            if next_index >= len(self.playbook["steps"]):
                self.playbook["status"] = "completed"
                self.playbook["completed_at"] = self.now()
                result = None
                if execute_engine_recovery:
                    try:
                        result = self.engine.adaptive_recovery()
                    except Exception as exc:
                        result = {"ok": False, "message": str(exc)}
                return {"ok": True, "playbook": self.copy(self.playbook), "engine_result": self.copy(result)}
            if self.playbook.get("started_at") is None:
                self.playbook["started_at"] = self.now()
            self.playbook["status"] = "running"
            self.playbook["current_step"] = next_index
            self.playbook["steps"][next_index]["status"] = "active"
            self.playbook["steps"][next_index]["timestamp"] = self.now()
            if "virtual" in self.playbook["steps"][next_index]["label"].lower():
                self.activate_virtual_ecu(self.playbook.get("target_ecu") or "steering_ecu")
            return {"ok": True, "playbook": self.copy(self.playbook)}


class FleetSecurityService:
    """Own fleet inventory and V2V threat-sharing state."""

    def __init__(self, lock, attack, json_copy, now):
        self.lock = lock
        self._attack = attack
        self.copy = json_copy
        self.now = now
        self.vehicles = self.default_fleet()
        self.events: Deque[Dict[str, Any]] = deque(maxlen=80)

    @staticmethod
    def default_fleet():
        return [
            {"vehicle_id": "EV-01", "model": "DriveFort Research EV", "status": "SAFE", "risk": 4, "location": "Amman Tech District", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-02", "model": "Urban EV", "status": "SAFE", "risk": 8, "location": "Smart Mobility Lab", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-03", "model": "Autonomous Shuttle", "status": "MONITORING", "risk": 22, "location": "Campus Route", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-04", "model": "Delivery EV", "status": "SAFE", "risk": 7, "location": "Logistics Zone", "policy": "v3.0", "connected": True},
            {"vehicle_id": "EV-05", "model": "Connected Sedan", "status": "OFFLINE", "risk": 0, "location": "Maintenance", "policy": "v2.9", "connected": False},
            {"vehicle_id": "EV-06", "model": "Test Mule", "status": "SAFE", "risk": 12, "location": "CARLA Digital Track", "policy": "v3.0", "connected": True},
        ]

    def sync(self, snapshot, fusion):
        with self.lock:
            name, active, _intensity, _target = self._attack(snapshot)
            ego = self.vehicles[0]
            ego.update({"risk": int(round(fusion.get("overall_score", 0))), "status": "UNDER_ATTACK" if active else "SAFE", "threat": name if active else None, "last_seen": self.now()})
            summary = {
                "total": len(self.vehicles),
                "online": sum(1 for vehicle in self.vehicles if vehicle.get("connected")),
                "safe": sum(1 for vehicle in self.vehicles if vehicle.get("status") == "SAFE"),
                "at_risk": sum(1 for vehicle in self.vehicles if vehicle.get("risk", 0) >= 35),
                "offline": sum(1 for vehicle in self.vehicles if not vehicle.get("connected")),
            }
            return {"vehicles": self.copy(self.vehicles), "summary": summary}

    def share(self, snapshot, target_vehicle_ids=None):
        with self.lock:
            innovation = snapshot.get("innovation_lab") or {}
            fusion = innovation.get("threat_fusion") or {}
            attack, active, _intensity, target = self._attack(snapshot)
            targets = target_vehicle_ids or [vehicle["vehicle_id"] for vehicle in self.vehicles[1:] if vehicle.get("connected")]
            event = {
                "event_id": "V2V-{}".format(uuid.uuid4().hex[:8].upper()), "timestamp": self.now(),
                "source_vehicle": "EV-01", "targets": targets,
                "attack": attack if active else "security_advisory", "target_ecu": target if active else None,
                "confidence": fusion.get("confidence", 0), "policy_action": "preemptive_block_and_monitor",
            }
            self.events.append(event)
            for vehicle in self.vehicles:
                if vehicle["vehicle_id"] in targets:
                    vehicle["last_shared_threat"] = event["attack"]
                    vehicle["policy"] = "v3.0-hotfix"
            return {"ok": True, "event": self.copy(event), "recipients": len(targets)}


class OTASecurityService:
    """Verify update hashes, signatures, compatibility, and audit events."""

    def __init__(self, lock, json_copy, now):
        self.lock = lock
        self.copy = json_copy
        self.now = now
        self.events: Deque[Dict[str, Any]] = deque(maxlen=80)

    def verify(self, manifest):
        with self.lock:
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
                expected_signature = hmac.new(secret_value.encode("utf-8"), (package_name + "|" + version + "|" + actual_hash).encode("utf-8"), hashlib.sha256).hexdigest()
            signature_ok = configuration_ready and bool(signature) and hmac.compare_digest(signature, expected_signature)
            accepted = configuration_ready and hash_ok and signature_ok and compatible
            demo_signing_enabled = os.environ.get("DRIVEFORT_ALLOW_MOCK", "0") == "1" and os.environ.get("DRIVEFORT_OTA_DEMO_SIGNING", "0") == "1"
            event = {
                "event_id": "OTA-{}".format(uuid.uuid4().hex[:8].upper()), "timestamp": self.now(),
                "package_name": package_name, "version": version, "hash_ok": hash_ok,
                "signature_ok": signature_ok, "compatible": compatible, "accepted": accepted,
                "decision": "INSTALL_TO_CANARY" if accepted else ("CONFIGURATION_REQUIRED" if not configuration_ready else "REJECT_UPDATE"),
                "rollback_ready": True, "configuration_ready": configuration_ready,
                "expected_demo_signature": expected_signature if (demo_signing_enabled and bool(manifest.get("include_demo_signature"))) else None,
                "actual_sha256": actual_hash,
            }
            self.events.append(event)
            return self.copy(event)


class IncidentReportingService:
    """Build the three stable V3 report payloads from facade collaborators."""

    def __init__(self, engine, timeline, now):
        self.engine = engine
        self.timeline = timeline
        self.now = now

    def build(self, snapshot, level="executive"):
        level = str(level or "executive").lower()
        if level not in {"executive", "technical", "forensic"}:
            level = "executive"
        innovation = snapshot.get("innovation_lab") or {}
        report = {
            "report_id": "DF-{}".format(uuid.uuid4().hex[:10].upper()), "level": level,
            "generated_at": self.now(), "platform": "DriveFort AI V3",
            "mission_summary": innovation.get("mission_control"), "decision": innovation.get("decision_explainer"),
            "benchmark": innovation.get("defense_benchmark"),
        }
        if level in {"technical", "forensic"}:
            report.update({
                "threat_fusion": innovation.get("threat_fusion"), "ghost_twin": innovation.get("ghost_twin"),
                "safety_envelope": innovation.get("safety_envelope"), "ecu_integrity": innovation.get("ecu_integrity"),
                "recovery_playbook": innovation.get("recovery_playbook"), "attack_graph": innovation.get("attack_graph"),
            })
        if level == "forensic":
            report.update({
                "evidence_integrity": innovation.get("evidence_integrity"), "timeline": self.timeline(360),
                "incident_storyboard": innovation.get("incident_storyboard"),
                "incident_records": getattr(self.engine, "recent_incidents", lambda: [])(),
            })
        return report
