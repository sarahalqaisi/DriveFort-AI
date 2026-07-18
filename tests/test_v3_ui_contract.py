from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def test_v3_innovation_ui_has_unique_ids_and_all_controls_are_wired():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    ids = re.findall(r'\bid="([^"]+)"', html)
    assert len(ids) == len(set(ids)), "Duplicate DOM ids make button/render wiring ambiguous."
    required = {
        "innovationLab", "v3TwinSvg", "v3RunBenchmarkBtn", "v3BuildChainBtn",
        "v3AdvanceChainBtn", "v3ActivateVirtualEcuBtn", "v3PreparePlaybookBtn",
        "v3AdvancePlaybookBtn", "v3StartScenarioBtn", "v3AdvanceScenarioBtn",
        "v3ShareThreatBtn", "v3VerifyOtaBtn", "v3CopilotAskBtn", "v3FeatureMatrix",
    }
    assert required.issubset(set(ids))
    for element_id in required - {"innovationLab", "v3TwinSvg", "v3FeatureMatrix"}:
        assert element_id in js
    assert "data-tab=\"innovation\"" in html
    assert "innovation-lab-panel" in js


def test_v3_frontend_references_all_mutating_innovation_routes():
    js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
    routes = {
        "/api/v3/benchmark/run",
        "/api/v3/attack-chain/configure",
        "/api/v3/attack-chain/advance",
        "/api/v3/adaptive-attacker/run",
        "/api/v3/stealth/start",
        "/api/v3/virtual-ecu/activate",
        "/api/v3/recovery/playbook/prepare",
        "/api/v3/recovery/playbook/advance",
        "/api/v3/scenario/start",
        "/api/v3/scenario/advance",
        "/api/v3/v2v/share",
        "/api/v3/ota/verify",
        "/api/v3/copilot/query",
    }
    for route in routes:
        assert route in js


def test_dashboard_uses_local_vendor_assets_without_external_cdns():
    html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    assert "https://" not in html
    required_assets = [
        ROOT / "static" / "vendor" / "chartjs" / "chart.umd.js",
        ROOT / "static" / "vendor" / "leaflet" / "leaflet.js",
        ROOT / "static" / "vendor" / "leaflet" / "leaflet.css",
        ROOT / "static" / "vendor" / "fontawesome" / "css" / "all.min.css",
        ROOT / "static" / "vendor" / "space-grotesk" / "space-grotesk.css",
    ]
    for asset in required_assets:
        assert asset.exists() and asset.stat().st_size > 100
