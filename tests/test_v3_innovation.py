import hashlib
import hmac
import os

from app import app, v3_features


os.environ.setdefault("DRIVEFORT_ALLOW_MOCK", "1")


def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_v3_overview_exposes_all_23_features():
    response = client().get("/api/v3/overview")
    assert response.status_code == 200
    payload = response.get_json()
    lab = payload["innovation_lab"]
    assert lab["version"] == "3.0.0"
    assert len(lab["feature_matrix"]) == 23
    assert all(item["status"] == "implemented" for item in lab["feature_matrix"])
    assert "ghost_twin" in lab
    assert "threat_fusion" in lab
    assert "fleet" in lab


def test_time_machine_records_and_can_be_cleared():
    c = client()
    c.get("/api/state")
    payload = c.get("/api/v3/time-machine?limit=10").get_json()
    assert payload["status"] == "ready"
    assert payload["count"] >= 1
    cleared = c.post("/api/v3/time-machine/clear", json={}).get_json()
    assert cleared["ok"] is True
    c.get("/api/state")
    assert c.get("/api/v3/time-machine").get_json()["count"] >= 1


def test_ghost_twin_and_safety_envelope_contracts():
    c = client()
    twin = c.get("/api/v3/ghost-twin").get_json()["ghost_twin"]
    envelope = c.get("/api/v3/safety-envelope").get_json()["safety_envelope"]
    assert twin["status"] in {"SYNCHRONIZED", "DEGRADED", "DIVERGED"}
    assert len(twin["actual"]["path"]) == 12
    assert len(twin["expected"]["path"]) == 12
    assert 0 <= twin["deviation_score"] <= 100
    assert envelope["status"] in {"ENFORCED", "VIOLATED"}
    assert envelope["limits"]["steering_min"] <= envelope["limits"]["steering_max"]


def test_counterfactual_benchmark_has_both_outcomes():
    response = client().post("/api/v3/benchmark/run", json={"attack": "steering_manipulation", "intensity": 0.9})
    assert response.status_code == 200
    benchmark = response.get_json()["benchmark"]
    assert benchmark["status"] == "complete"
    assert benchmark["protected"]["collision_probability_percent"] < benchmark["unprotected"]["collision_probability_percent"]
    assert benchmark["improvement"]["deviation_reduction_percent"] > 0
    assert len(benchmark["replay"]["unprotected"]) == 4
    assert len(benchmark["replay"]["protected"]) == 4


def test_ecu_integrity_and_virtual_backup_ecu():
    c = client()
    before = c.get("/api/v3/ecu-integrity").get_json()["ecu_integrity"]
    assert len(before["nodes"]) == 7
    activated = c.post("/api/v3/virtual-ecu/activate", json={"ecu_id": "steering_ecu"}).get_json()
    assert activated["virtual_ecu"]["active"] is True
    after = c.get("/api/v3/ecu-integrity").get_json()["ecu_integrity"]
    steering = next(node for node in after["nodes"] if node["id"] == "steering_ecu")
    assert steering["status"] == "VIRTUAL_BACKUP_ACTIVE"


def test_ai_explainer_fusion_and_copilot():
    c = client()
    fusion = c.get("/api/v3/threat-fusion").get_json()["threat_fusion"]
    explanation = c.get("/api/v3/ai/explain").get_json()["explanation"]
    answer = c.post("/api/v3/copilot/query", json={"question": "Summarize for the committee"}).get_json()
    assert len(fusion["components"]) == 5
    assert 0 <= fusion["overall_score"] <= 100
    assert explanation["summary"]
    assert answer["status"] == "answered"
    assert "DriveFort AI" in answer["answer"]


def test_attack_chain_builder_and_advance():
    c = client()
    configured = c.post("/api/v3/attack-chain/configure", json={
        "name": "test chain",
        "stages": [
            {"attack": "gps_spoofing", "intensity": 0.2},
            {"attack": "can_bus_injection", "intensity": 0.6},
        ],
    }).get_json()["attack_chain"]
    assert len(configured["stages"]) == 2
    advanced = c.post("/api/v3/attack-chain/advance", json={}).get_json()
    assert advanced["attack_chain"]["current_index"] == 0
    assert advanced["attack_chain"]["stages"][0]["status"] == "active"


def test_adaptive_and_stealth_attacker_analytical_modes():
    c = client()
    adaptive = c.post("/api/v3/adaptive-attacker/run", json={"apply_to_engine": False}).get_json()
    assert adaptive["adaptive_attacker"]["status"] == "planned"
    stealth = c.post("/api/v3/stealth/start", json={"attack": "gps_spoofing", "intensity": 0.2, "apply_to_engine": False}).get_json()
    assert stealth["stealth_mode"]["enabled"] is True
    assert stealth["stealth_mode"]["intensity"] <= 0.38
    stopped = c.post("/api/v3/stealth/stop", json={}).get_json()
    assert stopped["stealth_mode"]["enabled"] is False


def test_recovery_playbook_advances_to_completion():
    c = client()
    prepared = c.post("/api/v3/recovery/playbook/prepare", json={"attack": "gps_spoofing"}).get_json()["playbook"]
    assert prepared["status"] == "prepared"
    for _ in range(len(prepared["steps"]) + 1):
        result = c.post("/api/v3/recovery/playbook/advance", json={"execute_engine_recovery": False}).get_json()
    assert result["playbook"]["status"] == "completed"


def test_storyboard_evidence_and_three_report_levels():
    c = client()
    c.get("/api/state")
    story = c.get("/api/v3/incident/storyboard").get_json()["storyboard"]
    verification = c.get("/api/v3/evidence/verify").get_json()["verification"]
    assert story["status"] in {"ready", "empty"}
    assert "integrity_verified" in verification
    for level in ("executive", "technical", "forensic"):
        response = c.get("/api/v3/report/{}".format(level))
        assert response.status_code == 200
        report = response.get_json()["report"]
        assert report["level"] == level
        assert report["platform"] == "DriveFort AI V3"
    forensic = c.get("/api/v3/report/forensic").get_json()["report"]
    assert "timeline" in forensic
    assert "evidence_integrity" in forensic


def test_attack_graph_mission_control_and_score():
    c = client()
    graph = c.get("/api/v3/attack-graph").get_json()["attack_graph"]
    mission = c.get("/api/v3/mission-control").get_json()["mission_control"]
    score = c.get("/api/v3/performance-score").get_json()["performance_score"]
    assert graph["nodes"]
    assert mission["mode"] == "committee_demo"
    assert 0 <= score["overall"] <= 100
    for key in ("safety", "cyber_defense", "vehicle_stability", "recovery_readiness", "ecu_integrity"):
        assert 0 <= score[key] <= 100
    assert score["grade"] in {"A", "B", "C", "D"}


def test_scenario_director_catalog_start_and_advance():
    c = client()
    catalog = c.get("/api/v3/scenarios").get_json()["scenarios"]
    assert len(catalog) == 5
    started = c.post("/api/v3/scenario/start", json={"scenario_id": "protected_comparison"}).get_json()["scenario_director"]
    assert started["status"] == "running"
    advanced = c.post("/api/v3/scenario/advance", json={}).get_json()["scenario_director"]
    assert advanced["step"] == 1


def test_fleet_and_v2v_threat_sharing():
    c = client()
    fleet = c.get("/api/v3/fleet").get_json()["fleet"]
    assert fleet["summary"]["total"] == 6
    shared = c.post("/api/v3/v2v/share", json={}).get_json()
    assert shared["ok"] is True
    assert shared["recipients"] >= 1


def test_ota_rejects_unsigned_and_accepts_valid_demo_signature(monkeypatch):
    monkeypatch.setenv("DRIVEFORT_OTA_SECRET", "test-ota-secret")
    monkeypatch.setenv("DRIVEFORT_ALLOW_MOCK", "1")
    monkeypatch.setenv("DRIVEFORT_OTA_DEMO_SIGNING", "1")
    c = client()
    package_name = "drivefort-policy-update.bin"
    version = "3.0.1"
    payload = "drivefort-demo-update"
    actual_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    secret = os.environ["DRIVEFORT_OTA_SECRET"].encode("utf-8")
    signature = hmac.new(secret, (package_name + "|" + version + "|" + actual_hash).encode("utf-8"), hashlib.sha256).hexdigest()
    rejected = c.post("/api/v3/ota/verify", json={"package_name": package_name, "version": version, "payload": payload}).get_json()["ota"]
    assert rejected["accepted"] is False
    accepted = c.post("/api/v3/ota/verify", json={
        "package_name": package_name, "version": version, "payload": payload,
        "sha256": actual_hash, "signature": signature,
    }).get_json()["ota"]
    assert accepted["accepted"] is True
    assert accepted["decision"] == "INSTALL_TO_CANARY"


def test_invalid_inputs_are_safely_normalized():
    c = client()
    benchmark = c.post("/api/v3/benchmark/run", json={"attack": "not-real", "intensity": 999}).get_json()["benchmark"]
    assert benchmark["attack"] == "steering_manipulation"
    assert benchmark["intensity"] == 1.0
    virtual = c.post("/api/v3/virtual-ecu/activate", json={"ecu_id": "unknown"}).get_json()["virtual_ecu"]
    assert virtual["replaces"] == "steering_ecu"


def test_three_report_levels_export_valid_pdf_files():
    c = client()
    for level in ("executive", "technical", "forensic"):
        response = c.get("/api/v3/report/{}/pdf".format(level))
        assert response.status_code == 200
        assert response.mimetype == "application/pdf"
        assert response.data.startswith(b"%PDF-1.4")
        assert b"%%EOF" in response.data[-64:]
        assert len(response.data) > 500


def test_protection_records_full_time_machine_response_sequence():
    c = client()
    c.post("/api/v3/time-machine/clear", json={})
    attack_response = c.post("/api/scenario/urban_attack")
    assert attack_response.status_code == 200
    c.get("/api/state")

    protected = c.post("/api/protection/activate")
    assert protected.status_code == 200

    frames = c.get("/api/v3/time-machine?limit=30").get_json()["frames"]
    phases = [frame.get("phase") for frame in frames]
    assert any(phase in {"UNDER_ATTACK", "DETECTED", "MITIGATING"} for phase in phases)
    assert "MITIGATING" in phases
    assert "RECOVERING" in phases
    assert "RECOVERED" in phases
    recovered = next(frame for frame in frames if frame.get("phase") == "RECOVERED")
    assert recovered["attack"] == "gps_spoofing"
    assert recovered["analytical_transition"] is True
