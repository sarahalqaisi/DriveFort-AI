from concurrent.futures import ThreadPoolExecutor

import pytest

from app import app, v3_features
from src.v3.reporting import flatten_report, render_report_pdf
from src.v3.services import (
    AttackSimulationService,
    FleetSecurityService,
    IncidentReportingService,
    OTASecurityService,
    RecoveryService,
    ThreatFusionService,
)


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def test_facade_exposes_extracted_services_without_changing_public_methods():
    assert isinstance(v3_features.threat_fusion_service, ThreatFusionService)
    assert isinstance(v3_features.attack_simulation_service, AttackSimulationService)
    assert isinstance(v3_features.recovery_service, RecoveryService)
    assert isinstance(v3_features.fleet_security_service, FleetSecurityService)
    assert isinstance(v3_features.ota_security_service, OTASecurityService)
    assert isinstance(v3_features.reporting_service, IncidentReportingService)
    for method in (
        "enrich_snapshot", "run_benchmark", "configure_attack_chain",
        "activate_virtual_ecu", "prepare_playbook", "build_report",
        "share_v2v_threat", "verify_ota",
    ):
        assert callable(getattr(v3_features, method))


@pytest.mark.parametrize(
    "path,payload,field",
    [
        ("/api/v3/benchmark/run", {"intensity": "high"}, "intensity"),
        ("/api/v3/stealth/start", {"intensity": 0.9}, "intensity"),
        ("/api/v3/adaptive-attacker/run", {"apply_to_engine": "false"}, "apply_to_engine"),
        ("/api/v3/attack-chain/configure", {"stages": "not-a-list"}, "stages"),
        ("/api/v3/v2v/share", {"target_vehicle_ids": [1]}, "target_vehicle_ids"),
        ("/api/v3/ota/verify", {"version": 3.1}, "version"),
    ],
)
def test_invalid_post_payloads_return_consistent_400_errors(client, path, payload, field):
    response = client.post(path, json=payload)
    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["field"] == field
    assert body["error"]["message"]


def test_non_object_and_malformed_json_are_rejected(client):
    non_object = client.post("/api/v3/benchmark/run", json=[])
    assert non_object.status_code == 400
    assert non_object.get_json()["error"]["message"] == "Request body must be a JSON object."
    malformed = client.post(
        "/api/v3/benchmark/run", data="{", content_type="application/json"
    )
    assert malformed.status_code == 400
    assert malformed.get_json()["error"]["message"] == "Request body must contain valid JSON."


def test_successful_endpoint_response_shapes_remain_backward_compatible(client):
    benchmark = client.post(
        "/api/v3/benchmark/run",
        json={"attack": "steering_manipulation", "intensity": 0.9},
    )
    assert benchmark.status_code == 200
    assert set(benchmark.get_json()) == {"ok", "benchmark"}
    virtual = client.post(
        "/api/v3/virtual-ecu/activate", json={"ecu_id": "steering_ecu"}
    )
    assert virtual.status_code == 200
    assert set(virtual.get_json()) == {"ok", "virtual_ecu"}
    overview = client.get("/api/v3/overview").get_json()
    assert set(overview) == {"ok", "innovation_lab", "snapshot"}
    assert len(overview["innovation_lab"]["feature_matrix"]) == 23


def test_reporting_module_flattens_and_renders_valid_pdf():
    report = {
        "level": "technical",
        "generated_at": "2026-01-01T00:00:00Z",
        "nested": {"items": ["one", "two"], "decision": "MONITOR"},
    }
    lines = flatten_report(report)
    assert "nested / decision: MONITOR" in lines
    pdf = render_report_pdf(report)
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.endswith(b"%%EOF\n")
    assert b"DRIVEFORT AI V3 TECHNICAL REPORT" in pdf


def test_mutable_service_state_remains_thread_safe():
    snapshot = {
        "attack": {"active": False, "attack_name": "normal"},
        "innovation_lab": {"threat_fusion": {"confidence": 12}},
    }

    def share(_index):
        return v3_features.share_v2v_threat(snapshot, ["EV-02"])

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(share, range(40)))

    assert all(result["ok"] and result["recipients"] == 1 for result in results)
    assert len(v3_features.fleet_security_service.events) <= 80
    assert v3_features.fleet_security_service.vehicles[1]["policy"] == "v3.0-hotfix"
