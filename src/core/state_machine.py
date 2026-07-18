"""Derive a clear operator-facing lifecycle phase from a DriveFort snapshot.

This is intentionally deterministic and stateless for the V3 migration.
It gives the dashboard a stable contract now, while the simulation engine is
incrementally refactored away from legacy monkey patches.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping


PHASES = (
    "DISCONNECTED",
    "READY",
    "BASELINE",
    "UNDER_ATTACK",
    "DETECTED",
    "MITIGATING",
    "RECOVERING",
    "RECOVERED",
)


def derive_system_phase(snapshot: Mapping[str, Any]) -> Dict[str, Any]:
    carla = snapshot.get("carla") or {}
    attack = snapshot.get("attack") or {}
    risks = snapshot.get("risks") or {}
    final_defense = snapshot.get("final_defense") or {}
    recovery = (snapshot.get("evidence_recorder") or {}).get("recovery") or {}
    console = snapshot.get("drivefort_console") or snapshot.get("zoneguard_console") or {}

    connected = bool(carla.get("connected") and (carla.get("actor_found") or carla.get("vehicle_id")))
    attack_active = bool(attack.get("active"))
    risk = float(risks.get("overall") or 0.0)
    protection = bool(console.get("protection_enabled") or final_defense.get("sandbox_mode"))
    recovery_status = str(recovery.get("status") or "").lower()
    console_status = str(console.get("status") or "").lower()

    if not connected and str(carla.get("mode") or "mock") == "carla":
        phase = "DISCONNECTED"
        detail = "CARLA mode is selected, but no live ego vehicle is available."
    elif recovery_status in {"running", "recovering", "active"} or console_status == "recovering":
        phase = "RECOVERING"
        detail = "DriveFort is restoring trusted control and a stable vehicle state."
    elif recovery_status in {"complete", "completed", "recovered"} or console_status == "complete":
        phase = "RECOVERED"
        detail = "Recovery completed and the vehicle returned to a stable state."
    elif attack_active and protection:
        phase = "MITIGATING"
        detail = "An active threat is being constrained by the DriveFort defense stack."
    elif attack_active and risk >= 0.35:
        phase = "DETECTED"
        detail = "An active cyber-physical threat has been detected and classified."
    elif attack_active:
        phase = "UNDER_ATTACK"
        detail = "An attack scenario is active and telemetry is being evaluated."
    elif connected:
        phase = "BASELINE"
        detail = "The live vehicle is connected and operating under baseline monitoring."
    else:
        phase = "READY"
        detail = "The platform is ready in analytical mode. Connect CARLA for live control."

    return {
        "phase": phase,
        "phase_index": PHASES.index(phase),
        "detail": detail,
        "connected": connected,
        "attack_active": attack_active,
        "protection_active": protection,
    }
