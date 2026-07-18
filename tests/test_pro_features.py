from src.simulation_engine import SimulationEngine


def test_pro_snapshot_contains_trust_fusion_and_auth():
    engine = SimulationEngine()
    engine.apply_preset("gps_spoofing")
    snapshot = engine.snapshot()
    assert "pro" in snapshot
    assert "sensor_trust_scores" in snapshot["pro"]
    assert "sensor_fusion" in snapshot["pro"]
    assert snapshot["pro"]["command_authentication"]["status"] == "enabled"


def test_secure_command_signature():
    engine = SimulationEngine()
    command = engine.sign_control_command({"steer": 0.1, "throttle": 0.2, "brake": 0.0, "issued_by": "tester"})
    assert engine.apply_secure_command(command)["accepted"] is True
    command["throttle"] = 0.9
    assert engine.apply_secure_command(command)["accepted"] is False


def test_auto_security_test_runs():
    engine = SimulationEngine()
    result = engine.run_security_test(4)
    assert result["rounds"] == 4
    assert result["detection_rate"] >= 0.5
