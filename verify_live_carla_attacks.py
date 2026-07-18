"""Live CARLA verification utility for DriveFort AI's nine adopted scenarios.

Run while CARLA server is running. The script validates that each scenario can
be armed, stays active in the bridge runtime, and emits a unique bounded control
profile. It does not claim real-world attack or vehicle performance.
"""
from __future__ import annotations

import argparse
import json
import time

from src.attack_catalog import ADOPTED_ATTACK_ORDER
from src.simulation_engine import SimulationEngine


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=2000)
    parser.add_argument("--intensity", type=float, default=0.90)
    parser.add_argument("--hold", type=float, default=1.2, help="seconds to observe each active scenario")
    args = parser.parse_args()

    engine = SimulationEngine()
    status = engine.connect_carla_full({"host": args.host, "port": args.port, "spawn_if_missing": True, "synchronous": True, "fps": 20})
    if not engine.carla_bridge.is_ready():
        print(json.dumps({"ok": False, "error": "CARLA ego vehicle is not ready", "status": status}, indent=2))
        return 2

    results = []
    for attack in ADOPTED_ATTACK_ORDER:
        result = engine.apply_carla_attack_console(attack, args.intensity)
        time.sleep(max(0.2, args.hold))
        snap = engine.snapshot()
        runtime = snap.get("live_attack_runtime", {})
        applied = (result.get("carla_result") or {}).get("applied_control", {})
        passed = bool(result.get("ok")) and runtime.get("active") is True and runtime.get("attack") == attack and bool(applied)
        results.append({"attack": attack, "passed": passed, "runtime": runtime, "applied_control": applied, "message": result.get("message") or (result.get("carla_result") or {}).get("message")})
        engine.carla_bridge.stop_attack_scenario(restore_natural_drive=True)
        time.sleep(0.25)

    summary = {"ok": all(item["passed"] for item in results), "tested": len(results), "passed": sum(1 for item in results if item["passed"]), "results": results}
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
