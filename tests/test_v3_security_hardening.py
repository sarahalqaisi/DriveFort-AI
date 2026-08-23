import hashlib
import hmac

import pytest

from app import app, v3_features
from src.v3.benchmark import BenchmarkResult, SYNTHETIC_MODEL_VERSION


@pytest.fixture
def client():
    app.config.update(TESTING=True)
    return app.test_client()


def _signed_manifest(secret, version="3.2.0"):
    package_name = "drivefort-policy-update.bin"
    payload = "verified-update-payload"
    actual_hash = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    signature = hmac.new(
        secret.encode("utf-8"),
        (package_name + "|" + version + "|" + actual_hash).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return {
        "package_name": package_name,
        "version": version,
        "payload": payload,
        "sha256": actual_hash,
        "signature": signature,
    }


def test_synthetic_benchmark_has_explicit_provenance_and_evidence(client):
    response = client.post(
        "/api/v3/benchmark/run",
        json={"attack": "gps_spoofing", "intensity": 0.65},
    )
    assert response.status_code == 200
    benchmark = response.get_json()["benchmark"]
    assert benchmark["source"] == "synthetic"
    assert benchmark["measured"] is False
    assert benchmark["model_version"] == SYNTHETIC_MODEL_VERSION
    assert benchmark["scenario_id"].startswith("synthetic-gps_spoofing-")
    assert isinstance(benchmark["scenario_seed"], int)
    assert benchmark["generated_at"]
    assert benchmark["metadata"]["metric_semantics"] == "synthetic_analytical_estimates"
    assert benchmark["evidence"]["attack_type"] == "gps_spoofing"
    assert benchmark["evidence"]["detection_latency_ms"] == benchmark["protected"]["detection_time_ms"]
    assert "not measured CARLA data" in benchmark["physical_validation_note"]


def test_synthetic_benchmark_is_reproducible_for_same_inputs(client):
    payload = {"attack": "brake_override", "intensity": 0.73}
    first = client.post("/api/v3/benchmark/run", json=payload).get_json()["benchmark"]
    second = client.post("/api/v3/benchmark/run", json=payload).get_json()["benchmark"]
    for field in ("scenario_id", "scenario_seed", "model_version", "source", "measured"):
        assert first[field] == second[field]
    for field in ("unprotected", "protected", "improvement", "replay", "evidence"):
        assert first[field] == second[field]


def test_benchmark_store_accepts_only_explicit_measured_carla_records():
    measured = BenchmarkResult(
        attack_type="steering_manipulation",
        intensity=0.8,
        detection_latency_ms=180,
        maximum_deviation_m=0.31,
        stabilization_time_sec=1.7,
        trust_loss_percent=11.2,
        protected_outcome="CONTAINED",
        unprotected_outcome="UNSAFE DEVIATION",
        source="carla",
        measured=True,
        model_version="carla-measurement-v1",
        scenario_id="carla-town03-seed42",
        generated_at="2026-08-23T00:00:00Z",
        scenario_seed=42,
    )
    stored = v3_features.attack_simulation_service.record_carla_result(measured)
    assert stored is measured
    assert v3_features.attack_simulation_service.evidence_store.latest().measured is True
    with pytest.raises(ValueError):
        BenchmarkResult(
            attack_type="gps_spoofing", intensity=0.5,
            detection_latency_ms=100, maximum_deviation_m=0.2,
            stabilization_time_sec=1.0, trust_loss_percent=5,
            protected_outcome="CONTAINED", unprotected_outcome="UNSAFE",
            source="synthetic", measured=True, model_version="invalid",
            scenario_id="invalid", generated_at="2026-08-23T00:00:00Z",
        )


def test_ota_rejects_missing_secret(monkeypatch, client):
    monkeypatch.delenv("DRIVEFORT_OTA_SECRET", raising=False)
    ota = client.post("/api/v3/ota/verify", json=_signed_manifest("unused")).get_json()["ota"]
    assert ota["accepted"] is False
    assert ota["configuration_ready"] is False
    assert ota["decision"] == "CONFIGURATION_REQUIRED"


def test_ota_rejects_weak_secret_configuration(monkeypatch, client):
    monkeypatch.setenv("DRIVEFORT_OTA_SECRET", "too-short")
    ota = client.post(
        "/api/v3/ota/verify", json=_signed_manifest("too-short")
    ).get_json()["ota"]
    assert ota["accepted"] is False
    assert ota["configuration_ready"] is False
    assert ota["decision"] == "CONFIGURATION_REQUIRED"


def test_ota_rejects_invalid_signature_and_malformed_hash(monkeypatch, client):
    secret = "hardening-test-secret-at-least-32-bytes"
    monkeypatch.setenv("DRIVEFORT_OTA_SECRET", secret)
    invalid_signature = _signed_manifest("wrong-secret-also-at-least-32-bytes")
    ota = client.post("/api/v3/ota/verify", json=invalid_signature).get_json()["ota"]
    assert ota["hash_ok"] is True
    assert ota["signature_ok"] is False
    assert ota["accepted"] is False

    malformed = _signed_manifest(secret)
    malformed["sha256"] = "not-a-sha256"
    malformed["signature"] = "also-not-a-signature"
    ota = client.post("/api/v3/ota/verify", json=malformed).get_json()["ota"]
    assert ota["hash_format_ok"] is False
    assert ota["signature_format_ok"] is False
    assert ota["accepted"] is False


def test_ota_rejects_incompatible_version_even_with_valid_signature(monkeypatch, client):
    secret = "hardening-test-secret-at-least-32-bytes"
    monkeypatch.setenv("DRIVEFORT_OTA_SECRET", secret)
    ota = client.post(
        "/api/v3/ota/verify", json=_signed_manifest(secret, version="2.9.0")
    ).get_json()["ota"]
    assert ota["hash_ok"] is True
    assert ota["signature_ok"] is True
    assert ota["compatible"] is False
    assert ota["accepted"] is False


def test_demo_signature_never_exposed_in_normal_runtime(monkeypatch, client):
    secret = "hardening-test-secret-at-least-32-bytes"
    monkeypatch.setenv("DRIVEFORT_OTA_SECRET", secret)
    monkeypatch.setenv("DRIVEFORT_ALLOW_MOCK", "1")
    monkeypatch.setenv("DRIVEFORT_OTA_DEMO_SIGNING", "1")
    monkeypatch.setenv("DRIVEFORT_RUNTIME_MODE", "normal")
    manifest = _signed_manifest(secret)
    manifest["include_demo_signature"] = True
    normal = client.post("/api/v3/ota/verify", json=manifest).get_json()["ota"]
    assert normal["expected_demo_signature"] is None

    monkeypatch.setenv("DRIVEFORT_RUNTIME_MODE", "synthetic")
    synthetic = client.post("/api/v3/ota/verify", json=manifest).get_json()["ota"]
    assert synthetic["expected_demo_signature"] == manifest["signature"]


def test_internal_engine_exception_is_logged_but_not_leaked(monkeypatch, client, caplog):
    secret_marker = "internal-secret-path-/srv/drivefort"

    def fail_engine_action(*_args, **_kwargs):
        raise RuntimeError(secret_marker)

    monkeypatch.setattr(v3_features.engine, "apply_carla_attack_console", fail_engine_action)
    client.post(
        "/api/v3/attack-chain/configure",
        json={"name": "hardening", "stages": [{"attack": "gps_spoofing"}]},
    )
    with caplog.at_level("ERROR"):
        response = client.post("/api/v3/attack-chain/advance", json={})
    body = response.get_json()
    assert response.status_code == 200
    assert secret_marker not in response.get_data(as_text=True)
    assert body["engine_result"]["message"] == "Engine stage could not be applied safely."
    assert secret_marker in caplog.text


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/v3/overview", "get"),
        ("/api/v3/benchmark/run", "post"),
        ("/api/v3/report/executive/pdf", "get"),
    ],
)
def test_v3_security_responses_disable_caching(client, path, method):
    kwargs = {"json": {}} if method == "post" else {}
    response = getattr(client, method)(path, **kwargs)
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_validation_errors_are_sanitized_and_non_cacheable(client):
    marker = "do-not-reflect-this-value"
    response = client.post("/api/v3/benchmark/run", json={"attack": marker})
    assert response.status_code == 400
    body = response.get_json()
    assert body["error"]["code"] == "invalid_request"
    assert marker not in response.get_data(as_text=True)
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
