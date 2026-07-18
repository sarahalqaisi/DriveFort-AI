from src.attack_catalog import ADOPTED_ATTACK_ORDER, adopted_attack_catalog
from src.models import ALLOWED_ATTACKS
from src.simulation_engine import SimulationEngine


def test_all_adopted_attacks_are_allowed_and_have_metadata():
    catalog = adopted_attack_catalog()
    assert len(catalog) == 9
    assert [item["id"] for item in catalog] == ADOPTED_ATTACK_ORDER
    for item in catalog:
        assert item["id"] in ALLOWED_ATTACKS
        assert item["en"]
        assert item["ar"]
        assert item["impact"]
        assert item["defense"]


def test_each_adopted_attack_has_preset_risk_and_solution_snapshot():
    engine = SimulationEngine()
    for attack in ADOPTED_ATTACK_ORDER:
        assert engine.apply_preset(attack), attack
        snap = engine.snapshot()
        assert snap["attack"]["attack_name"] == attack
        assert snap["attack"]["active"] is True
        assert snap["risks"]["threat_level"] in {"SUSPICIOUS", "ATTACK", "CRITICAL"}
        assert snap["solution"]["name"] == "DriveFort AI EV Security Framework"
        assert attack in [a["id"] for a in snap["adopted_attacks"]]


def test_ai_self_test_covers_all_adopted_attacks():
    engine = SimulationEngine()
    result = engine.ai_self_test()
    assert result["ok"] is True
    validation = result["validation"]
    assert validation["cases_passed"] == validation["cases_total"]
    tested = {case["case"] for case in validation["details"] if case["case"] != "normal"}
    assert set(ADOPTED_ATTACK_ORDER) == tested
