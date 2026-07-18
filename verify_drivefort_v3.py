"""Offline verification entry point for DriveFort AI V3.

Run with:
    DRIVEFORT_ALLOW_MOCK=1 python verify_drivefort_v3.py

This validates API contracts and analytical features without claiming live CARLA
physics. Live simulator validation is a separate checklist in docs/VALIDATION_V3.md.
"""
from __future__ import annotations

import os
os.environ.setdefault("DRIVEFORT_OTA_SECRET", "standalone-verifier-ota-secret")
os.environ.setdefault("DRIVEFORT_OTA_DEMO_SIGNING", "1")
import sys

os.environ.setdefault("DRIVEFORT_ALLOW_MOCK", "1")

from app import app  # noqa: E402


def check(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    client = app.test_client()
    checks = []

    def get(path):
        response = client.get(path)
        check(response.status_code == 200, "GET {} returned {}".format(path, response.status_code))
        checks.append("GET {}".format(path))
        return response.get_json()

    def post(path, payload=None):
        response = client.post(path, json=payload or {})
        check(response.status_code == 200, "POST {} returned {}".format(path, response.status_code))
        checks.append("POST {}".format(path))
        return response.get_json()

    state = get("/api/state")
    lab = state.get("innovation_lab") or {}
    check(lab.get("version") == "3.1.0", "V3 version missing")
    check(len(lab.get("feature_matrix") or []) == 23, "Expected 23 implemented capabilities")

    get("/api/v3/time-machine")
    get("/api/v3/ghost-twin")
    get("/api/v3/ecu-integrity")
    get("/api/v3/safety-envelope")
    get("/api/v3/ai/explain")
    get("/api/v3/threat-fusion")
    get("/api/v3/attack-graph")
    get("/api/v3/mission-control")
    get("/api/v3/performance-score")
    get("/api/v3/fleet")
    get("/api/v3/evidence/verify")
    get("/api/v3/report/executive")
    get("/api/v3/report/technical")
    get("/api/v3/report/forensic")

    post("/api/v3/benchmark/run", {"attack": "steering_manipulation", "intensity": 0.9})
    post("/api/v3/attack-chain/configure", {"name": "verification chain", "stages": [{"attack": "gps_spoofing"}, {"attack": "can_bus_injection"}]})
    post("/api/v3/attack-chain/advance")
    post("/api/v3/adaptive-attacker/run", {"apply_to_engine": False})
    post("/api/v3/stealth/start", {"attack": "gps_spoofing", "apply_to_engine": False})
    post("/api/v3/stealth/stop")
    post("/api/v3/virtual-ecu/activate", {"ecu_id": "steering_ecu"})
    prepared = post("/api/v3/recovery/playbook/prepare", {"attack": "steering_manipulation"})
    for _ in range(len(prepared["playbook"]["steps"]) + 1):
        post("/api/v3/recovery/playbook/advance", {"execute_engine_recovery": False})
    post("/api/v3/scenario/start", {"scenario_id": "protected_comparison"})
    post("/api/v3/scenario/advance")
    post("/api/v3/v2v/share")
    post("/api/v3/copilot/query", {"question": "Summarize the security state for the committee."})

    print("DriveFort AI V3 offline verification passed: {} API checks.".format(len(checks)))
    print("Feature matrix: 23/23 implemented.")
    print("Important: live CARLA physics still require the separate simulator checklist.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("Verification failed: {}".format(exc), file=sys.stderr)
        sys.exit(1)
