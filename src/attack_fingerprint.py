from typing import Dict, List

from .attack_catalog import canonical_attack


class AttackFingerprint:
    def identify(self, attack_name: str, features: Dict) -> Dict:
        reasons: List[str] = []
        confidence = 0.2
        attack_type = "unknown"

        attack_name = canonical_attack(attack_name)

        if attack_name in {"can_bus_injection", "dos"}:
            attack_type = attack_name
            if features.get("message_rate", 0) > 85:
                reasons.append("high message rate")
                confidence += 0.35
            if features.get("repeated_ratio", 0) > 0.6:
                reasons.append("repeated arbitration IDs")
                confidence += 0.25
            if attack_name == "dos":
                reasons.append("control latency spike")
                confidence += 0.15

        elif attack_name == "brake_override":
            attack_type = attack_name
            reasons.extend(["unexpected braking", "driver command mismatch"])
            confidence = 0.86

        elif attack_name == "steering_manipulation":
            attack_type = attack_name
            reasons.extend(["steering deviation", "lane instability"])
            confidence = 0.88

        elif attack_name == "telemetry_scraping":
            attack_type = attack_name
            reasons.extend(["repeated telemetry access", "privacy request surge"])
            confidence = 0.83

        elif attack_name == "battery_thermal_tampering":
            attack_type = attack_name
            reasons.extend(["battery thermal anomaly", "temperature rise inconsistent with load"])
            confidence = 0.9

        elif attack_name == "gps_spoofing":
            attack_type = attack_name
            reasons.extend(["GPS drift", "map and inertial mismatch"])
            confidence = 0.84

        elif attack_name == "sensor_spoofing":
            attack_type = attack_name
            reasons.extend(["sensor disagreement", "digital twin mismatch"])
            confidence = 0.86

        elif attack_name == "acceleration_injection":
            attack_type = attack_name
            reasons.extend(["unexpected acceleration", "driver throttle mismatch"])
            confidence = 0.88

        elif attack_name == "lane_drift_attack":
            attack_type = attack_name
            reasons.extend(["continuous steering bias", "gradual lane departure pattern"])
            confidence = 0.89

        elif attack_name == "pedestrian_detection_attack":
            attack_type = attack_name
            reasons.extend(["pedestrian perception mismatch", "obstacle proximity without braking"])
            confidence = 0.93

        elif attack_name == "camera_lidar_blinding":
            attack_type = attack_name
            reasons.extend(["perception confidence collapse", "camera and LiDAR occlusion pattern"])
            confidence = 0.87

        elif attack_name == "mixed_attack":
            attack_type = attack_name
            reasons.extend(["multi-vector anomaly", "simultaneous control and network indicators"])
            confidence = 0.94

        else:
            attack_type = "none"
            reasons = ["normal baseline"]
            confidence = 0.0

        return {
            "attack_type": attack_type,
            "confidence": min(1.0, round(confidence, 2)),
            "reasons": reasons,
        }
