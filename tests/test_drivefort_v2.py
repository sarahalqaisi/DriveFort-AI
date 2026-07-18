from __future__ import annotations

from app import app
from src.core import BRAND
from src.simulation_engine import SimulationEngine


def test_drivefort_brand_contract_is_exposed():
    client = app.test_client()
    config = client.get("/api/config")
    assert config.status_code == 200
    data = config.get_json()
    assert data["platform"]["name"] == "DriveFort AI"
    assert data["platform"]["tagline"] == "Secure Intelligence for Electric Mobility"
    assert data["platform"]["pillars"] == ["Protect", "Detect", "Twin", "Recover"]
    assert BRAND.version == "3.0.0"


def test_state_has_drivefort_console_and_lifecycle():
    engine = SimulationEngine()
    snapshot = engine.snapshot()
    assert snapshot["platform"]["name"] == "DriveFort AI"
    assert snapshot["drivefort_console"] == snapshot["zoneguard_console"]
    assert snapshot["lifecycle"]["phase"] in {
        "DISCONNECTED", "READY", "BASELINE", "UNDER_ATTACK",
        "DETECTED", "MITIGATING", "RECOVERING", "RECOVERED",
    }


def test_health_endpoint_reports_v3_service():
    client = app.test_client()
    response = client.get("/api/system/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert payload["service"] == "DriveFort AI"
    assert payload["version"] == "3.0.0"


def test_critical_console_routes_do_not_raise_server_errors(monkeypatch):
    monkeypatch.setenv("DRIVEFORT_ALLOW_MOCK", "1")
    client = app.test_client()
    cases = [
        ("/api/reset", None),
        ("/api/protection/activate", None),
        ("/api/defense/sandbox", {"enabled": True}),
        ("/api/defense/secure_comm", {"enabled": True}),
        ("/api/defense/emergency_stop", None),
    ]
    for route, body in cases:
        response = client.post(route, json=body) if body is not None else client.post(route)
        assert response.status_code < 500, (route, response.get_data(as_text=True))
        assert response.is_json
