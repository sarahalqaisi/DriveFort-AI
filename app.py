from __future__ import annotations

import io
import os
import subprocess
import time
from pathlib import Path
from flask import Flask, jsonify, render_template, request, send_file
from src.simulation_engine import SimulationEngine
from src.attack_catalog import adopted_attack_catalog
from src.core import BRAND, derive_system_phase
from src.v3 import DriveFortV3Features
from src.v3.api import create_v3_blueprint

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=1 * 1024 * 1024)
app.json.sort_keys = False
engine = SimulationEngine()
v3_features = DriveFortV3Features(engine)

# Driver authority state for the dashboard: autonomous CARLA autopilot or human keyboard control.
driver_control_state = {
    "mode": "autonomous",
    "last_command": {"steer": 0.0, "throttle": 0.0, "brake": 0.0},
    "zoneguard_override": False,  # legacy API field
    "drivefort_override": False,
    "message": "Autonomous driving mode is active."
}




def _live_carla_required(action_name: str = "dashboard action"):
    # In real dashboard runtime, mutating vehicle actions require a live CARLA actor.
    # During offline unit tests, preserve analytical/mock testability.
    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("DRIVEFORT_ALLOW_MOCK", os.environ.get("ZONEGUARD_ALLOW_MOCK", "0")) == "1":
        return None
    live = bool(getattr(engine, "_carla_is_live", lambda: False)())
    if live:
        return None
    result = engine._carla_waiting_result(action_name) if hasattr(engine, "_carla_waiting_result") else {"ok": False, "message": "CARLA live vehicle is required.", "snapshot": engine.snapshot()}
    return jsonify(result), 400

def _snapshot_with_driver_control() -> dict:
    snap = engine.snapshot()

    # Dashboard baseline contract: before an operator activates a scenario, the
    # interface must never inherit a stale/high demo score from earlier state.
    # A normal, inactive scenario starts LOW/NORMAL; live CARLA connectivity is
    # shown separately and is not treated as a cyber-physical attack.
    attack = snap.get("attack") or {}
    if not bool(attack.get("active")):
        risks = dict(snap.get("risks") or {})
        risks.update({
            "overall": 0.05,
            "threat_level": "NORMAL",
            "action": "MONITOR",
            "summary": "Normal baseline monitoring. No active attack scenario.",
        })
        snap["risks"] = risks
        ai = dict(snap.get("ai_security") or {})
        ai["risk_score"] = 5
        ai["anomaly_score"] = 5
        ai["threat_class"] = "normal"
        classification = dict(ai.get("classification") or {})
        classification.update({"label": "normal", "confidence": 0.95})
        ai["classification"] = classification
        snap["ai_security"] = ai

    driver = dict(driver_control_state)
    driver["drivefort_override"] = bool(driver.get("zoneguard_override"))
    snap["driver_control"] = driver
    snap["platform"] = BRAND.to_dict()
    snap["lifecycle"] = derive_system_phase(snap)
    return v3_features.enrich_snapshot(snap)


app.register_blueprint(create_v3_blueprint(v3_features, _snapshot_with_driver_control))


def _pdf_escape(value: object) -> str:
    text = str(value).replace("\\", "/").replace("(", "[").replace(")", "]")
    return text.encode("latin-1", "replace").decode("latin-1")[:112]


def _pdf_report(snapshot: dict) -> bytes:
    risks = snapshot.get("risks", {})
    attack = snapshot.get("attack", {})
    vehicle = snapshot.get("vehicle", {})
    owner = snapshot.get("owner_diagnostics", {})
    demo = snapshot.get("full_demo", {})
    dashboard = snapshot.get("defense_dashboard", {})
    before = demo.get("before", {}) or {}
    after = demo.get("after", {}) or {}
    delta = demo.get("delta", {}) or {}
    components = ((owner.get("prototype") or {}).get("components") or [])
    damaged = [c for c in components if c.get("status") == "affected" or c.get("severity") in {"medium", "high", "critical"}]

    lines = [
        "DRIVEFORT AI INCIDENT REPORT",
        "",
        f"Threat Level: {risks.get('threat_level', 'NORMAL')}    Risk Score: {risks.get('overall', 0)}    Action: {risks.get('action', 'ALLOW')}",
        f"Scenario: {attack.get('attack_name', 'normal')}    Target ECU: {attack.get('target_ecu', 'none')}    Active: {attack.get('active', False)}",
        f"Owner Message: {owner.get('owner_message', 'No owner alert available.')}",
        f"Recommended Action: {owner.get('recommended_action', risks.get('action', 'Continue monitoring'))}",
        "",
        "BEFORE / AFTER METRICS",
        f"Speed: {before.get('speed_kmh', vehicle.get('speed_kmh', '--'))} -> {after.get('speed_kmh', vehicle.get('speed_kmh', '--'))} km/h    Delta: {delta.get('speed_kmh', 0)}",
        f"Battery: {before.get('battery_soc', vehicle.get('battery_soc', '--'))} -> {after.get('battery_soc', vehicle.get('battery_soc', '--'))}%    Delta: {delta.get('battery_soc', 0)}",
        f"Battery Temp: {before.get('battery_temp_c', vehicle.get('battery_temp_c', '--'))} -> {after.get('battery_temp_c', vehicle.get('battery_temp_c', '--'))} C    Delta: {delta.get('battery_temp_c', 0)}",
        f"Motor Temp: {before.get('motor_temp_c', vehicle.get('motor_temp_c', '--'))} -> {after.get('motor_temp_c', vehicle.get('motor_temp_c', '--'))} C    Delta: {delta.get('motor_temp_c', 0)}",
        f"Lane: {delta.get('lane_change', vehicle.get('lane_status', '--'))}",
        "",
        "AFFECTED COMPONENTS",
    ]
    if damaged:
        for c in damaged[:10]:
            lines.append(f"- {c.get('label', c.get('id', 'Component'))}: {c.get('severity', 'unknown')} / {c.get('description', c.get('status', 'affected'))}")
    else:
        lines.append("- No damaged owner-visible components detected in the current state.")
    lines += ["", "ROOT CAUSE"]
    lines += [f"- {x}" for x in (risks.get("root_cause") or ["No abnormal causal chain detected."])[:8]]
    lines += ["", "DEFENSE STRATEGY"]
    lines += [f"- {x}" for x in (risks.get("defense_strategy") or ["Continuous monitoring."])[:8]]
    evidence = snapshot.get("evidence_recorder", {}) or {}
    sev = evidence.get("severity_meter", {}) or {}
    rec = evidence.get("recovery", {}) or {}
    lines += ["", "EVIDENCE RECORDER"]
    lines.append(f"Severity Meter: {sev.get('score', 0)}% / {sev.get('level', 'NORMAL')} / {sev.get('label', '')}")
    lines.append(f"Recovery: {rec.get('status', 'standby')} - {rec.get('message', 'No recovery action recorded.')}")
    captures = evidence.get("captures") or []
    for cap in captures[-6:]:
        m = cap.get("metrics", {})
        lines.append(f"- {cap.get('stage', 'capture')}: {cap.get('note', '')} | speed={m.get('speed_kmh', '--')} km/h battery={m.get('battery_soc', '--')}% temp={m.get('battery_temp_c', '--')}C")
    lines += ["", "EVENT TIMELINE"]
    timeline = demo.get("timeline") or dashboard.get("attack_timeline") or []
    if timeline:
        for item in timeline[:8]:
            lines.append(f"- {item.get('title', item.get('stage', 'Step'))}: {item.get('detail', '')}")
    else:
        lines += [f"- {x}" for x in ((dashboard.get('incident_report', {}).get('evidence') or snapshot.get('event_log', []))[-10:])]

    text_ops = ["BT", "/F1 18 Tf", "54 792 Td", "(DRIVEFORT AI INCIDENT REPORT) Tj", "ET"]
    y = 760
    for line in lines[1:70]:
        size = 10 if line and not line.isupper() else 12
        if line == "":
            y -= 8
            continue
        text_ops.extend(["BT", f"/F1 {size} Tf", f"54 {y} Td", f"({_pdf_escape(line)}) Tj", "ET"])
        y -= 14 if size == 10 else 18
        if y < 48:
            break
    stream = "\n".join(text_ops).encode("latin-1")
    objects = []
    objects.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n")
    objects.append(b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n")
    objects.append(b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj\n")
    objects.append(b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n")
    objects.append(b"5 0 obj << /Length " + str(len(stream)).encode() + b" >> stream\n" + stream + b"\nendstream endobj\n")
    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf)); pdf.extend(obj)
    xref = len(pdf)
    pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode())
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(pdf)


def _default_carla_exe() -> str:
    """Return the CARLA executable path used by the Windows demo."""
    return os.environ.get(
        "CARLA_EXE_PATH",
        r"D:\Downloads\CarlaSimulator\WindowsNoEditor\CarlaUE4.exe",
    )


def _start_carla_process_if_needed() -> dict:
    """Start CARLA on Windows if it is not already listening/responding."""
    exe = _default_carla_exe()
    result = {"requested_exe": exe, "started": False, "message": "CARLA launch skipped."}
    try:
        # If the world is already reachable, do not open another CARLA window.
        status = engine.carla_bridge.connect(host="localhost", port=2000, spawn_if_missing=False, synchronous=False, fps=20)
        if status.connected:
            result["message"] = "CARLA is already running. Waiting for world readiness."
            return result
    except Exception:
        pass
    if not Path(exe).exists():
        result["message"] = "CARLA executable was not found. Set CARLA_EXE_PATH or edit run_carla_windows.bat."
        return result
    try:
        subprocess.Popen([exe], cwd=str(Path(exe).parent), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result["started"] = True
        result["message"] = "CARLA process started. Waiting for simulator world."
    except Exception as exc:
        result["message"] = f"Could not start CARLA automatically: {exc}"
    return result


def _wait_for_carla_world(timeout_sec: int = 90) -> dict:
    """Poll CARLA until get_world/map/spawn points are ready, then force respawn and drive."""
    deadline = time.time() + max(10, int(timeout_sec))
    last_message = "Waiting for CARLA world..."
    attempts = 0
    while time.time() < deadline:
        attempts += 1
        try:
            # Use force respawn because it validates map + spawn + autopilot in one place.
            result = engine.force_respawn_and_drive()
            status = result.get("status", result)
            if result.get("ok") or status.get("ok"):
                return {
                    "ok": True,
                    "attempts": attempts,
                    "message": status.get("message", "CARLA world ready. EV spawned and normal drive enabled."),
                    "snapshot": engine.snapshot(),
                }
            last_message = status.get("message") or result.get("message") or last_message
        except Exception as exc:
            last_message = str(exc)
        time.sleep(3)
    return {"ok": False, "attempts": attempts, "message": last_message, "snapshot": engine.snapshot()}


@app.get("/")
def index():
    return render_template("index.html", brand=BRAND.to_dict())


@app.get("/api/config")
def platform_config():
    """Stable platform metadata loaded once by clients and presentation tools."""
    return jsonify({"platform": BRAND.to_dict(), "api_version": "v3", "runtime_mode": engine.mode})


@app.get("/api/system/health")
def system_health():
    snapshot = _snapshot_with_driver_control()
    carla = snapshot.get("carla") or {}
    return jsonify({
        "ok": True,
        "service": BRAND.name,
        "version": BRAND.version,
        "runtime_mode": engine.mode,
        "carla_connected": bool(carla.get("connected")),
        "lifecycle": snapshot.get("lifecycle", {}),
    })


@app.get("/api/state")
def get_state():
    return jsonify(_snapshot_with_driver_control())


@app.get("/api/attacks/adopted")
def adopted_attacks():
    return jsonify({"attacks": adopted_attack_catalog(), "count": len(adopted_attack_catalog())})


@app.post("/api/update_driver")
def update_driver():
    blocked = _live_carla_required("driver telemetry/control update")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    engine.update_driver(payload)
    return jsonify(engine.snapshot())

def _get_carla_vehicle():
    bridge = getattr(engine, "carla_bridge", None)
    if bridge is None:
        return None, None
    return bridge, getattr(bridge, "vehicle", None)


def _apply_carla_control(steer: float, throttle: float, brake: float) -> bool:
    bridge, vehicle = _get_carla_vehicle()
    if vehicle is None:
        return False
    try:
        from src.carla_bridge import carla as carla_module
        if carla_module is None:
            return False
        vehicle.set_autopilot(False)
        control = carla_module.VehicleControl()
        control.steer = max(-1.0, min(1.0, float(steer)))
        control.throttle = max(0.0, min(1.0, float(throttle)))
        control.brake = max(0.0, min(1.0, float(brake)))
        control.hand_brake = False
        control.reverse = False
        control.manual_gear_shift = False
        vehicle.apply_control(control)
        return True
    except Exception:
        return False


def _zoneguard_filter_keyboard(steer: float, throttle: float, brake: float) -> dict:
    snap = engine.snapshot()
    risk = float(((snap.get("risks") or {}).get("overall") or 0.0))
    ai = snap.get("ai_security") or {}
    ai_risk = float(ai.get("risk_score") or 0.0) / 100.0
    attack_active = bool((snap.get("attack") or {}).get("active"))
    effective_risk = max(risk, ai_risk)
    safe = {"steer": max(-1.0, min(1.0, float(steer))), "throttle": max(0.0, min(1.0, float(throttle))), "brake": max(0.0, min(1.0, float(brake)))}
    override = False
    message = "Human keyboard command allowed by DriveFort AI."
    if effective_risk >= 0.75 or attack_active:
        safe = {"steer": 0.0, "throttle": 0.0, "brake": 1.0}
        override = True
        message = "DriveFort AI override: unsafe keyboard/autopilot command blocked and emergency braking applied."
    elif effective_risk >= 0.45 and safe["throttle"] > 0.25:
        safe["throttle"] = 0.0
        safe["brake"] = max(safe["brake"], 0.35)
        override = True
        message = "DriveFort AI warning: throttle limited because risk is elevated."
    safe["override"] = override
    safe["message"] = message
    return safe


@app.post("/api/driver/control_mode")
def driver_control_mode():
    blocked = _live_carla_required("driver control mode")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    mode = str(payload.get("mode") or "autonomous").lower()
    if mode not in {"autonomous", "keyboard"}:
        mode = "autonomous"
    result = engine.zoneguard_set_driver_mode(mode)
    driver_control_state["mode"] = mode
    driver_control_state["zoneguard_override"] = False
    driver_control_state["drivefort_override"] = False
    driver_control_state["message"] = result.get("message", "Driver mode updated.")
    return jsonify({"ok": bool(result.get("ok", True)), "snapshot": _snapshot_with_driver_control(), "message": driver_control_state["message"]})


@app.post("/api/driver/keyboard_control")
def driver_keyboard_control():
    blocked = _live_carla_required("keyboard vehicle control")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    steer = float(payload.get("steer", 0.0) or 0.0)
    throttle = float(payload.get("throttle", 0.0) or 0.0)
    brake = float(payload.get("brake", 0.0) or 0.0)
    safe = _zoneguard_filter_keyboard(steer, throttle, brake)
    applied = _apply_carla_control(safe["steer"], safe["throttle"], safe["brake"])
    driver_control_state["mode"] = "keyboard"
    driver_control_state["last_command"] = {"steer": safe["steer"], "throttle": safe["throttle"], "brake": safe["brake"]}
    driver_control_state["zoneguard_override"] = bool(safe["override"])
    driver_control_state["drivefort_override"] = bool(safe["override"])
    driver_control_state["message"] = safe["message"]
    engine.update_driver({
        "steer": safe["steer"], "throttle": safe["throttle"], "brake": safe["brake"],
        "autopilot_enabled": False, "manual_override": True, "lane_status": "keyboard_zoneguard_override" if safe["override"] else "keyboard_control"
    })
    return jsonify({"ok": True, "applied_to_carla": applied, "snapshot": _snapshot_with_driver_control()})


@app.post("/api/update_attack")
def update_attack():
    blocked = _live_carla_required("attack update")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    engine.update_attack(payload)
    return jsonify(engine.snapshot())


@app.post("/api/preset/<attack_name>")
def preset(attack_name: str):
    if attack_name != "normal":
        blocked = _live_carla_required(f"preset {attack_name}")
        if blocked:
            return blocked
    ok = engine.apply_preset(attack_name)
    return jsonify(engine.snapshot()), 200 if ok else 400


@app.post("/api/scenario/<scenario_name>")
def scenario(scenario_name: str):
    ok = engine.apply_scenario(scenario_name)
    return jsonify(engine.snapshot()), 200 if ok else 400

@app.post("/api/carla/normal_drive")
def carla_normal_drive():
    ok = engine.start_natural_drive()
    return jsonify(engine.snapshot()), 200 if ok else 400

@app.post("/api/carla/attack_after_drive")
def carla_attack_after_drive():
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or "mixed_attack")
    ok = engine.launch_owner_visible_attack(attack)
    return jsonify(engine.snapshot()), 200 if ok else 400

@app.post("/api/demo/full")
def full_demo():
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or "mixed_attack")
    summary = engine.run_full_demo(attack)
    return jsonify({"summary": summary, "snapshot": engine.snapshot()})


@app.post("/api/attack/apply")
def apply_live_attack():
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or payload.get("attack_name") or "mixed_attack")
    try:
        intensity = float(payload.get("intensity", 0.92))
    except Exception:
        intensity = 0.92
    result = engine.apply_carla_attack_console(attack, intensity)
    return jsonify(result), 200 if result.get("ok") else 400

@app.post("/api/attack/recover")
def recover_live_attack():
    return jsonify(engine.recover_vehicle_live())

@app.get("/api/evidence")
def evidence():
    return jsonify(engine.snapshot().get("evidence_recorder", {}))

@app.post("/api/random_attack")
def random_attack():
    blocked = _live_carla_required("random attack")
    if blocked:
        return blocked
    engine.random_attack()
    return jsonify(engine.snapshot())


@app.post("/api/reset")
def reset():
    engine.reset()
    return jsonify(engine.snapshot())


@app.post("/api/mode")
def set_mode():
    payload = request.get_json(silent=True) or {}
    mode = payload.get("mode", "mock")
    status = engine.set_mode(mode)
    return jsonify({"status": status, "snapshot": engine.snapshot()})


@app.post("/api/carla/connect")
def carla_connect():
    payload = request.get_json(silent=True) or {}
    status = engine.connect_carla_full(payload)
    return jsonify({"status": status, "snapshot": engine.snapshot()})


@app.post("/api/carla/spawn")
def carla_spawn():
    status = engine.connect_carla_full({"spawn_if_missing": True, "synchronous": True, "fps": 20})
    return jsonify({"status": status, "snapshot": engine.snapshot()})

@app.post("/api/carla/start_full")
def carla_start_full():
    status = engine.connect_carla_full({"spawn_if_missing": True, "synchronous": True, "fps": 20})
    live = engine.carla_live_start()
    try:
        engine.start_natural_drive()
    except Exception:
        pass
    return jsonify({"status": status, "live": live, "snapshot": engine.snapshot()})


@app.post("/api/carla/tick")
def carla_tick():
    return jsonify({"tick": engine.carla_tick(), "snapshot": engine.snapshot()})


@app.post("/api/carla/live/start")
def carla_live_start():
    status = engine.carla_live_start()
    return jsonify({"status": status, "snapshot": engine.snapshot()})


@app.post("/api/carla/live/stop")
def carla_live_stop():
    status = engine.carla_live_stop()
    return jsonify({"status": status, "snapshot": engine.snapshot()})


@app.get("/api/carla/sensors")
def carla_sensors():
    return jsonify(engine.carla_sensor_snapshot())


@app.post("/api/carla/disconnect")
def carla_disconnect():
    status = engine.set_mode("mock")
    return jsonify({"status": status, "snapshot": engine.snapshot()})


@app.post("/api/driver_action/<action_name>")
def driver_action(action_name: str):
    blocked = _live_carla_required(f"driver action {action_name}")
    if blocked:
        return blocked
    ok = engine.apply_driver_action(action_name)
    return jsonify(engine.snapshot()), 200 if ok else 400


@app.get("/api/report")
def report():
    return jsonify(engine.snapshot())


@app.get("/api/report/pdf")
def report_pdf():
    snapshot = engine.snapshot()
    data = _pdf_report(snapshot)
    return send_file(io.BytesIO(data), mimetype="application/pdf", as_attachment=True, download_name="drivefort_ai_incident_report.pdf")


@app.get("/api/incidents")
def incidents():
    return jsonify({"incidents": engine.recent_incidents()})




@app.get("/api/metrics")
def metrics():
    snapshot = engine.snapshot()
    return jsonify({
        "performance_dashboard": snapshot.get("performance_dashboard", {}),
        "context_aware_response": snapshot.get("context_aware_response", {}),
        "security_digital_twin": snapshot.get("security_digital_twin", {}),
        "forensic_audit": snapshot.get("forensic_audit", {}),
        "ecu_consensus": snapshot.get("ecu_consensus", {}),
        "xai": snapshot.get("xai", {}),
    })


@app.get("/api/forensic/verify")
def forensic_verify():
    snapshot = engine.snapshot()
    return jsonify(snapshot.get("forensic_audit", {}))


@app.get("/api/assistant/explain")
def assistant_explain():
    snapshot = engine.snapshot()
    return jsonify({"explanation": engine.ai_assistant_explanation(snapshot), "snapshot": snapshot})


@app.post("/api/demo/<action_name>")
def demo_action(action_name: str):
    if action_name == "start":
        engine.start_demo()
    elif action_name == "advance":
        engine.advance_demo()
    elif action_name == "stop":
        engine.stop_demo()
    return jsonify(engine.snapshot())



@app.get("/api/pro/security_test")
def pro_security_test_get():
    return jsonify({"last_security_test": engine.last_security_test})

@app.post("/api/pro/security_test")
def pro_security_test_run():
    payload = request.get_json(silent=True) or {}
    rounds = int(payload.get("rounds", 12))
    return jsonify(engine.run_security_test(rounds))

@app.post("/api/pro/command/sign")
def pro_command_sign():
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.sign_control_command(payload))

@app.post("/api/pro/command/apply")
def pro_command_apply():
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.apply_secure_command(payload))


@app.post("/api/protection/activate")
def protection_activate():
    return jsonify(engine.activate_innovative_protection())

@app.post("/api/protection/unprotected_scenario")
def protection_unprotected_scenario():
    blocked = _live_carla_required("unprotected comparison scenario")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or "steering_manipulation")
    return jsonify(engine.run_unprotected_attack_scenario(attack))

@app.post("/api/protection/protected_scenario")
def protection_protected_scenario():
    blocked = _live_carla_required("protected comparison scenario")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or "steering_manipulation")
    return jsonify(engine.run_protected_attack_scenario(attack))

@app.get("/api/protection/compare")
def protection_compare():
    return jsonify(engine.snapshot().get("protection_demo", {}))


@app.post("/api/attacker/manual_control")
def attacker_manual_control():
    blocked = _live_carla_required("manual attacker sliders")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.apply_attacker_manual_control(
        payload.get("steer", 0.0),
        payload.get("throttle", 0.0),
        payload.get("brake", 0.0),
    ))


@app.post("/api/attacker/battery_control")
def attacker_battery_control():
    blocked = _live_carla_required("battery/BMS dashboard control")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.apply_attacker_battery_control(
        payload.get("temp_delta", 0.0),
        payload.get("soc_delta", 0.0),
        payload.get("mode", "thermal_spike"),
    ))

@app.post("/api/ai/adaptive_recovery")
def ai_adaptive_recovery():
    return jsonify(engine.adaptive_recovery())

@app.get("/api/ai/security")
def ai_security():
    engine.ai_anomaly_detection()
    engine.classify_threat()
    return jsonify(engine.snapshot().get("ai_security", {}))



@app.post("/api/ai/train_baseline")
def ai_train_baseline():
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.train_ai_baseline(payload.get("samples", 18)))

@app.post("/api/ai/self_test")
def ai_self_test():
    return jsonify(engine.ai_self_test())

@app.post("/api/defense/sandbox")
def defense_sandbox():
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.set_attack_sandbox(bool(payload.get("enabled", True))))

@app.post("/api/defense/secure_comm")
def defense_secure_comm():
    payload = request.get_json(silent=True) or {}
    return jsonify(engine.set_secure_communication(bool(payload.get("enabled", True))))

@app.post("/api/defense/emergency_stop")
def defense_emergency_stop():
    return jsonify(engine.emergency_safe_stop())

@app.post("/api/defense/final_showcase")
def defense_final_showcase():
    blocked = _live_carla_required("final DriveFort AI showcase")
    if blocked:
        return blocked
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or "steering_manipulation")
    return jsonify(engine.run_final_showcase(attack))

@app.get("/api/replay")
def attack_replay():
    return jsonify(engine.get_attack_replay())

@app.post("/api/replay/clear")
def clear_attack_replay():
    if hasattr(engine, "final_defense"):
        engine.final_defense["attack_replay"] = []
    return jsonify(engine.get_attack_replay())



@app.post("/api/carla/auto_launch_wait")
def carla_auto_launch_wait():
    """Legacy endpoint retained for compatibility; manual CARLA launch is required."""
    return jsonify({
        "ok": False,
        "message": "Automatic CARLA launch is disabled. Start CarlaUE4.exe manually, then use Connect CARLA and Spawn Vehicle.",
        "snapshot": engine.snapshot(),
    }), 409

@app.post("/api/carla/force_respawn_drive")
def carla_force_respawn_drive():
    """Hard reset CARLA vehicle from the dashboard: destroy the old ego actor, spawn on a road spawn point, enable autopilot, and start the tick loop."""
    result = engine.force_respawn_and_drive()
    return jsonify(result), 200 if result.get("ok") else 400

@app.post("/api/carla/force_attack")
def carla_force_attack():
    """Apply a direct simulator attack even if protection/sandbox state was left enabled."""
    payload = request.get_json(silent=True) or {}
    attack = str(payload.get("attack") or "mixed_attack")
    try:
        intensity = float(payload.get("intensity", 0.95))
    except Exception:
        intensity = 0.95
    result = engine.force_direct_carla_attack(attack, intensity)
    return jsonify(result), 200 if result.get("ok") else 400

@app.get("/api/carla/attack_diagnostics")
def carla_attack_diagnostics():
    bridge = getattr(engine, "carla_bridge", None)
    out = {"ready": bool(bridge and bridge.is_ready())}
    if bridge and bridge.is_ready():
        try:
            c = bridge.vehicle.get_control()
            out["actor_control"] = {"steer": float(c.steer), "throttle": float(c.throttle), "brake": float(c.brake)}
            out["runtime"] = getattr(bridge, "_zg_attack_runtime", {}) or {}
            out["autopilot"] = bool(getattr(bridge, "_zg_autopilot_enabled", False))
        except Exception as exc:
            out["error"] = str(exc)
    return jsonify(out)


@app.errorhandler(400)
def handle_bad_request(error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "bad_request", "message": str(error)}), 400
    return error


@app.errorhandler(404)
def handle_not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "error": "not_found", "message": "API route not found."}), 404
    return error


@app.errorhandler(500)
def handle_internal_error(error):
    if request.path.startswith("/api/"):
        app.logger.exception("DriveFort API failure: %s", error)
        return jsonify({"ok": False, "error": "internal_error", "message": "The request could not be completed safely."}), 500
    return error


if __name__ == "__main__":
    debug = os.environ.get("DRIVEFORT_DEBUG", os.environ.get("ZONEGUARD_DEBUG", "0")) == "1"
    host = os.environ.get("DRIVEFORT_HOST", os.environ.get("ZONEGUARD_HOST", "127.0.0.1"))
    port = int(os.environ.get("DRIVEFORT_PORT", os.environ.get("ZONEGUARD_PORT", "5000")))
    app.run(host=host, port=port, debug=debug)
