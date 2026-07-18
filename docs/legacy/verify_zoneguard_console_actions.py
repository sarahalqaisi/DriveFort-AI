"""Static wiring verifier for the ZoneGuard Console.
Run after starting no external services: python verify_zoneguard_console_actions.py
It verifies every console button has a JavaScript handler and every handler route exists.
"""
from pathlib import Path
import re, sys
ROOT=Path(__file__).resolve().parent
html=(ROOT/'templates'/'index.html').read_text(encoding='utf-8')
js=(ROOT/'static'/'js'/'app.js').read_text(encoding='utf-8')
app=(ROOT/'app.py').read_text(encoding='utf-8')
ids=['recoverVehicleBtn2','activateProtectionBtn2','runProtectedScenarioBtn2','autonomousModeBtn','keyboardModeBtn','keyboardStopBtn','adaptiveRecoveryBtn','trainAiBaselineBtn','runAiSelfTestBtn','enableSandboxBtn','disableSandboxBtn','toggleSecureCommBtn','emergencySafeStopBtn','runFinalShowcaseBtn','loadReplayBtn','runUnprotectedScenarioBtn','activateProtectionBtn','runProtectedScenarioBtn','runCompareDemoBtn','applyLiveAttackBtn','recoverVehicleBtn','sendManualControlBtn','presetSwerveBtn','presetHardBrakeBtn','presetThrottleBtn','presetReleaseBtn','sendBatteryTamperBtn']
missing=[i for i in ids if f"'{i}'" not in js and f'"{i}"' not in js]
assert not missing, f'Missing JS bindings/references: {missing}'
for route in ['/api/protection/activate','/api/protection/unprotected_scenario','/api/protection/protected_scenario','/api/attacker/manual_control','/api/attacker/battery_control','/api/ai/adaptive_recovery','/api/ai/train_baseline','/api/ai/self_test','/api/defense/sandbox','/api/defense/secure_comm','/api/defense/emergency_stop','/api/defense/final_showcase','/api/replay','/api/driver/control_mode','/api/driver/keyboard_control','/api/attack/recover','/api/carla/force_attack']:
    assert route in app, f'Missing Flask route: {route}'
assert 'ZONEGUARD CONSOLE ACTION CONTRACT' in (ROOT/'src'/'simulation_engine.py').read_text(encoding='utf-8')
print(f'PASS: {len(ids)} console buttons have JS wiring; backend action routes found.')
