from __future__ import annotations

"""Explainable AI helper for DriveFort AI EV.

This module does not change the risk decision. It translates the current
vehicle/attack/risk state into human-readable evidence for the dashboard and
for viva/demo discussion.
"""

from typing import Any, Dict, List, Tuple


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _asdict(obj: Any) -> Dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "to_dict"):
        try:
            return obj.to_dict()
        except Exception:
            pass
    return dict(getattr(obj, "__dict__", {}) or {})


def _risk_dict(risk: Any) -> Dict[str, Any]:
    if isinstance(risk, dict):
        return risk
    if hasattr(risk, "to_dict"):
        try:
            return risk.to_dict()
        except Exception:
            pass
    return dict(getattr(risk, "__dict__", {}) or {})


def explain_risk(vehicle: Any, attack: Any, risk: Any, digital_twin: Any = None, ai_security: Any = None) -> Dict[str, Any]:
    vehicle_d = _asdict(vehicle)
    attack_d = _asdict(attack)
    risk_d = _risk_dict(risk)
    twin = digital_twin or {}
    ai = ai_security or {}

    speed = _num(vehicle_d.get("speed_kmh"))
    throttle = _num(vehicle_d.get("throttle"))
    brake = _num(vehicle_d.get("brake"))
    steer = abs(_num(vehicle_d.get("steer")))
    obstacle = _num(vehicle_d.get("obstacle_distance_m"), 999.0)
    battery_temp = _num(vehicle_d.get("battery_temp_c"))
    motor_temp = _num(vehicle_d.get("motor_temp_c"))
    lane_status = str(vehicle_d.get("lane_status", "centered"))
    attack_name = str(attack_d.get("attack_name", "normal"))
    attack_active = bool(attack_d.get("active", False)) and attack_name != "normal"
    risk_overall = _num(risk_d.get("overall"))
    ai_score = _num(ai.get("risk_score"), risk_overall * 100.0)

    contributions: List[Tuple[str, str, float, str]] = []
    if attack_active:
        contributions.append(("Attack Context", "Active attack vector: %s" % attack_name.replace("_", " "), 24.0 + _num(attack_d.get("intensity")) * 16.0, "Attack engine reports an active cyber-physical scenario."))
    if throttle >= 0.75:
        contributions.append(("Throttle Spike", "Throttle demand is %.0f%%" % (throttle * 100), min(18.0, throttle * 18.0), "High propulsion demand can cause unsafe acceleration."))
    if brake < 0.15 and obstacle <= 12 and speed >= 15:
        contributions.append(("Brake Override Context", "Obstacle %.1fm ahead while brake is low" % obstacle, 22.0, "Vehicle should slow down near close obstacles; low braking raises collision risk."))
    elif obstacle <= 20:
        contributions.append(("Obstacle Proximity", "Nearest target is %.1fm away" % obstacle, 12.0 if obstacle > 10 else 18.0, "Short time-to-collision increases severity."))
    if steer >= 0.35:
        contributions.append(("Steering Deviation", "Steering magnitude %.2f" % steer, min(20.0, steer * 22.0), "Large steering input may cause lane departure at speed."))
    if lane_status not in {"centered", "normal", "clear"}:
        contributions.append(("Lane Deviation", "Lane status: %s" % lane_status, 14.0, "Persistent lateral deviation suggests lane drift or steering manipulation."))
    if battery_temp >= 48 or motor_temp >= 72:
        contributions.append(("Thermal Anomaly", "Battery %.1f°C / Motor %.1f°C" % (battery_temp, motor_temp), 12.0, "Thermal behavior is outside expected EV operating baseline."))
    if twin.get("anomaly") or twin.get("mismatch") or not twin.get("is_synced", True):
        dev = twin.get("deviation_score", twin.get("deviations", {}))
        contributions.append(("Digital Twin Mismatch", "Observed state diverges from expected model", 20.0, "The shadow model predicted a different safe vehicle behavior. Deviation=%s" % dev))
    dominant = str(risk_d.get("dominant_risk", "normal"))
    if dominant not in {"normal", "none", ""} and risk_overall >= 0.35:
        contributions.append(("Dominant Risk Class", "Dominant risk: %s" % dominant.replace("_", " "), 10.0, "Risk engine weights this category as the strongest contributor."))

    # Merge risk-engine root causes as low-weight evidence without duplicating UI text.
    for cause in (risk_d.get("root_cause") or [])[:3]:
        contributions.append(("Root Cause", str(cause), 7.0, "Risk engine causal chain."))

    # Sort and normalize evidence.
    contributions.sort(key=lambda item: item[2], reverse=True)
    top = contributions[0][0] if contributions else "Normal operation"
    total = sum(c[2] for c in contributions) or max(0.0, risk_overall * 100.0)
    evidence = []
    for label, detail, weight, why in contributions[:8]:
        evidence.append({
            "factor": label,
            "detail": detail,
            "impact": int(round(min(100.0, max(1.0, weight)))),
            "why_it_matters": why,
        })

    if not evidence:
        reasons = ["Vehicle telemetry matches the learned safe baseline."]
        recommendation = "Continue monitoring. No defensive override is required."
    else:
        reasons = ["%s: %s" % (e["factor"], e["detail"]) for e in evidence[:5]]
        if risk_overall >= 0.85 or ai_score >= 86:
            recommendation = "Activate emergency safe mode: throttle cut, emergency braking, and command isolation."
        elif risk_overall >= 0.65 or ai_score >= 70:
            recommendation = "Restrict unsafe commands and monitor until telemetry returns to baseline."
        elif risk_overall >= 0.35 or ai_score >= 50:
            recommendation = "Alert operator and keep forensic logging active."
        else:
            recommendation = "Keep monitoring; anomaly is below intervention threshold."

    confidence = max(_num(risk_d.get("ai_confidence"), 0.0), _num(ai.get("confidence"), 0.0))
    if confidence <= 0:
        confidence = min(0.98, 0.42 + risk_overall * 0.5)

    return {
        "title": "Explainable AI Decision",
        "risk_level": round(risk_overall, 3),
        "risk_percent": int(round(max(risk_overall * 100.0, ai_score))),
        "threat_level": risk_d.get("threat_level", "NORMAL"),
        "top_factor": top,
        "reasons": reasons,
        "evidence": evidence,
        "explanation": "Risk is explained mainly by %s." % top if evidence else "No abnormal factor currently dominates the decision.",
        "recommendation": recommendation,
        "confidence": round(min(0.99, max(0.05, confidence)), 2),
        "audit_note": "XAI explains the existing decision; it does not replace the safety policy.",
    }
