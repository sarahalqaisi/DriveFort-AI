"""Static wiring verifier for the DriveFort AI dashboard console.

Run without CARLA: ``python verify_drivefort_console_actions.py``.
It checks that every critical button has a JavaScript reference and that the
matching Flask route exists.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent
html = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
js = (ROOT / "static" / "js" / "app.js").read_text(encoding="utf-8")
app = (ROOT / "app.py").read_text(encoding="utf-8")
engine = (ROOT / "src" / "simulation_engine.py").read_text(encoding="utf-8")

button_ids = [
    "recoverVehicleBtn2", "activateProtectionBtn2", "runProtectedScenarioBtn2",
    "autonomousModeBtn", "keyboardModeBtn", "keyboardStopBtn",
    "adaptiveRecoveryBtn", "trainAiBaselineBtn", "runAiSelfTestBtn",
    "enableSandboxBtn", "disableSandboxBtn", "toggleSecureCommBtn",
    "emergencySafeStopBtn", "runFinalShowcaseBtn", "loadReplayBtn",
    "runUnprotectedScenarioBtn", "activateProtectionBtn", "runProtectedScenarioBtn",
    "runCompareDemoBtn", "applyLiveAttackBtn", "recoverVehicleBtn",
    "sendManualControlBtn", "presetSwerveBtn", "presetHardBrakeBtn",
    "presetThrottleBtn", "presetReleaseBtn", "sendBatteryTamperBtn",
]

missing_html = [item for item in button_ids if f'id="{item}"' not in html]
missing_js = [item for item in button_ids if f"'{item}'" not in js and f'"{item}"' not in js]
assert not missing_html, f"Missing dashboard buttons: {missing_html}"
assert not missing_js, f"Missing JavaScript bindings/references: {missing_js}"

routes = [
    "/api/protection/activate", "/api/protection/unprotected_scenario",
    "/api/protection/protected_scenario", "/api/attacker/manual_control",
    "/api/attacker/battery_control", "/api/ai/adaptive_recovery",
    "/api/ai/train_baseline", "/api/ai/self_test", "/api/defense/sandbox",
    "/api/defense/secure_comm", "/api/defense/emergency_stop",
    "/api/defense/final_showcase", "/api/replay", "/api/driver/control_mode",
    "/api/driver/keyboard_control", "/api/attack/recover",
    "/api/carla/force_attack", "/api/config", "/api/system/health",
]
for route in routes:
    assert route in app, f"Missing Flask route: {route}"

assert "DRIVEFORT AI CONSOLE ACTION CONTRACT" in engine
print(
    f"PASS: {len(button_ids)} console controls, {len(routes)} backend routes, "
    "and the DriveFort console contract are present."
)
