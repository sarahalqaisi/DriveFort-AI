"""Run the 9 adopted DriveFort AI attacks against a live CARLA vehicle.

Usage on Windows after starting CARLA 0.9.13:
    py -3.7 verify_adopted_carla_attacks.py

The script intentionally fails closed: if CARLA is not connected or no vehicle is
ready, it does not report fake success. It prints one row per attack showing
whether CARLA control was applied, which target was spawned, whether a vehicle
or pedestrian participant was staged, and whether CARLA's collision sensor
verified severe/critical impact during the test window. The process exits with
non-zero status if any adopted attack is not verified.
"""
from __future__ import annotations

import json
import time

from src.attack_catalog import ADOPTED_ATTACK_ORDER, display_label
from src.simulation_engine import SimulationEngine


def main() -> int:
    engine = SimulationEngine()
    status = engine.connect_carla_full({"host": "127.0.0.1", "port": 2000, "spawn_if_missing": True, "synchronous": True, "fps": 20})
    if not (status.get("connected") and status.get("actor_found")):
        print("CARLA is not ready:", status.get("message"))
        return 2
    try:
        engine.carla_live_start()
        engine.start_natural_drive()
    except Exception:
        pass

    results = []
    for attack in ADOPTED_ATTACK_ORDER:
        print("\n===", display_label(attack), "===")
        try:
            # Reset to a clean road pose when available so each attack is visible.
            if hasattr(engine, "force_respawn_and_drive"):
                reset = engine.force_respawn_and_drive()
                print("reset:", reset.get("status", reset).get("message", reset.get("message", "done")))
                time.sleep(1.0)
            result = engine.apply_carla_attack_console(attack, 0.96)
            impact = (result.get("carla_result") or result).get("impact", {})
            collision = impact.get("collision") or {}
            row = {
                "attack": attack,
                "label": display_label(attack),
                "ok": bool(result.get("ok")),
                "message": result.get("message") or (result.get("carla_result") or {}).get("message"),
                "impact_target": impact.get("target"),
                "scene": impact.get("scene", []),
                "impact_verified": bool(impact.get("verified")),
                "severity": impact.get("severity") or collision.get("severity"),
                "collision_intensity": collision.get("intensity"),
                "impact_message": impact.get("message"),
            }
            print(json.dumps(row, ensure_ascii=False, indent=2))
            results.append(row)
            try:
                engine.recover_vehicle_live()
            except Exception:
                pass
            time.sleep(1.0)
        except Exception as exc:
            row = {"attack": attack, "label": display_label(attack), "ok": False, "error": str(exc)}
            print(json.dumps(row, ensure_ascii=False, indent=2))
            results.append(row)

    applied = sum(1 for r in results if r.get("ok"))
    verified = sum(1 for r in results if r.get("impact_verified"))
    severe_or_critical = sum(1 for r in results if str(r.get("severity") or "").lower() in {"severe", "critical"})
    summary = {
        "attacks": len(results),
        "carla_control_applied": applied,
        "collision_verified": verified,
        "severe_or_critical": severe_or_critical,
        "all_verified": applied == len(ADOPTED_ATTACK_ORDER) and verified == len(ADOPTED_ATTACK_ORDER),
        "results": results,
    }
    print("\nSUMMARY")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["all_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
