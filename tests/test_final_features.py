from src.simulation_engine import SimulationEngine


def test_ready_made_scenario_enables_replay_and_safe_mode():
    engine = SimulationEngine()
    assert engine.apply_scenario("mixed_emergency") is True
    snapshot = engine.snapshot()
    assert snapshot["attack"]["active"] is True
    assert snapshot["attack"]["replay_enabled"] is True
    assert snapshot["defense_dashboard"]["safe_mode"]["active"] is True


def test_ai_assistant_explanation_has_actionable_summary():
    engine = SimulationEngine()
    engine.apply_preset("gps_spoofing")
    snapshot = engine.snapshot()
    explanation = engine.ai_assistant_explanation(snapshot)
    assert "DriveFort AI classified" in explanation
    assert snapshot["risks"]["action"] in explanation


def test_recent_incidents_store_records_active_attack():
    engine = SimulationEngine()
    engine.apply_preset("throttle_injection")
    engine.snapshot()
    incidents = engine.recent_incidents()
    assert len(incidents) >= 1
    assert incidents[0]["scenario"] == "throttle_injection"
