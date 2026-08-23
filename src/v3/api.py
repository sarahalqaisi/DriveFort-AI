from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from .advanced_features import APPROVED_ATTACKS, ECU_LABELS
from .reporting import render_report_pdf
from .validation import (
    PayloadValidationError,
    attack_stages,
    boolean,
    json_object,
    number,
    string,
    string_list,
    validation_error_response,
)


def create_v3_blueprint(features, snapshot_provider):
    bp = Blueprint("drivefort_v3", __name__, url_prefix="/api/v3")

    @bp.after_request
    def secure_v3_response(response):
        # V3 payloads contain live security and incident state. They should
        # never be replayed from browser or intermediary caches.
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @bp.errorhandler(PayloadValidationError)
    def invalid_payload(error):
        return validation_error_response(error)

    def snapshot():
        return snapshot_provider()

    @bp.get("/overview")
    def overview():
        snap = snapshot()
        return jsonify({"ok": True, "innovation_lab": snap.get("innovation_lab", {}), "snapshot": snap})

    @bp.get("/features")
    def features_matrix():
        snap = snapshot()
        lab = snap.get("innovation_lab", {})
        matrix = lab.get("feature_matrix", [])
        return jsonify({
            "ok": True,
            "version": lab.get("version"),
            "implemented": sum(1 for item in matrix if item.get("status") == "implemented"),
            "total": len(matrix),
            "features": matrix,
        })

    @bp.get("/time-machine")
    def time_machine():
        limit = request.args.get("limit", 180, type=int)
        return jsonify(features.timeline(limit))

    @bp.post("/time-machine/clear")
    def time_machine_clear():
        json_object()
        return jsonify(features.clear_timeline())

    @bp.get("/ghost-twin")
    def ghost_twin():
        snap = snapshot()
        return jsonify({"ok": True, "ghost_twin": (snap.get("innovation_lab") or {}).get("ghost_twin", {})})

    @bp.post("/benchmark/run")
    def benchmark_run():
        payload = json_object()
        attack = string(payload, "attack", "steering_manipulation", choices=APPROVED_ATTACKS)
        intensity = number(payload, "intensity", 0.92, minimum=0.05, maximum=1.0)
        result = features.run_benchmark(attack, intensity)
        return jsonify({"ok": True, "benchmark": result})

    @bp.get("/benchmark")
    def benchmark_get():
        snap = snapshot()
        return jsonify({"ok": True, "benchmark": (snap.get("innovation_lab") or {}).get("defense_benchmark", {})})

    @bp.get("/ecu-integrity")
    def ecu_integrity():
        snap = snapshot()
        return jsonify({"ok": True, "ecu_integrity": (snap.get("innovation_lab") or {}).get("ecu_integrity", {})})

    @bp.get("/safety-envelope")
    def safety_envelope():
        snap = snapshot()
        return jsonify({"ok": True, "safety_envelope": (snap.get("innovation_lab") or {}).get("safety_envelope", {})})

    @bp.get("/ai/explain")
    def ai_explain():
        snap = snapshot()
        return jsonify({"ok": True, "explanation": (snap.get("innovation_lab") or {}).get("decision_explainer", {})})

    @bp.post("/copilot/query")
    def copilot_query():
        payload = json_object()
        question = string(payload, "question", "", max_length=300)
        return jsonify(features.copilot_query(snapshot(), question))

    @bp.get("/threat-fusion")
    def threat_fusion():
        snap = snapshot()
        return jsonify({"ok": True, "threat_fusion": (snap.get("innovation_lab") or {}).get("threat_fusion", {})})

    @bp.post("/attack-chain/configure")
    def attack_chain_configure():
        payload = json_object()
        name = string(payload, "name", "", max_length=80)
        stages = attack_stages(payload, APPROVED_ATTACKS)
        return jsonify({"ok": True, "attack_chain": features.configure_attack_chain(name, stages)})

    @bp.post("/attack-chain/advance")
    def attack_chain_advance():
        json_object()
        return jsonify(features.advance_attack_chain())

    @bp.get("/attack-chain")
    def attack_chain_get():
        snap = snapshot()
        return jsonify({"ok": True, "attack_chain": (snap.get("innovation_lab") or {}).get("attack_chain", {})})

    @bp.post("/adaptive-attacker/run")
    def adaptive_attacker_run():
        payload = json_object()
        return jsonify(features.adaptive_attack(snapshot(), boolean(payload, "apply_to_engine", False)))

    @bp.post("/stealth/start")
    def stealth_start():
        payload = json_object()
        return jsonify(features.start_stealth_attack(
            string(payload, "attack", "gps_spoofing", choices=APPROVED_ATTACKS),
            number(payload, "intensity", 0.22, minimum=0.05, maximum=0.38),
            boolean(payload, "apply_to_engine", False),
        ))

    @bp.post("/stealth/stop")
    def stealth_stop():
        json_object()
        return jsonify({"ok": True, "stealth_mode": features.stop_stealth_attack()})

    @bp.post("/virtual-ecu/activate")
    def virtual_ecu_activate():
        payload = json_object()
        ecu_id = string(payload, "ecu_id", "steering_ecu", choices=set(ECU_LABELS))
        return jsonify({"ok": True, "virtual_ecu": features.activate_virtual_ecu(ecu_id)})

    @bp.post("/virtual-ecu/deactivate")
    def virtual_ecu_deactivate():
        payload = json_object()
        ecu_id = string(payload, "ecu_id", "steering_ecu", choices=set(ECU_LABELS))
        return jsonify(features.deactivate_virtual_ecu(ecu_id))

    @bp.post("/recovery/playbook/prepare")
    def recovery_prepare():
        payload = json_object()
        attack = string(payload, "attack", "steering_manipulation", choices=APPROVED_ATTACKS)
        return jsonify({"ok": True, "playbook": features.prepare_playbook(attack)})

    @bp.post("/recovery/playbook/advance")
    def recovery_advance():
        payload = json_object()
        return jsonify(features.advance_playbook(boolean(payload, "execute_engine_recovery", False)))

    @bp.get("/incident/storyboard")
    def incident_storyboard():
        snap = snapshot()
        return jsonify({"ok": True, "storyboard": (snap.get("innovation_lab") or {}).get("incident_storyboard", {})})

    @bp.get("/evidence/verify")
    def evidence_verify():
        return jsonify({"ok": True, "verification": features.verify_evidence()})

    @bp.get("/report/<level>")
    def report(level):
        return jsonify({"ok": True, "report": features.build_report(snapshot(), level)})


    @bp.get("/report/<level>/pdf")
    def report_pdf(level):
        report_data = features.build_report(snapshot(), level)
        filename = "drivefort_v3_{}_report.pdf".format(report_data.get("level", "executive"))
        return Response(
            render_report_pdf(report_data),
            mimetype="application/pdf",
            headers={"Content-Disposition": "attachment; filename={}".format(filename)},
        )

    @bp.get("/attack-graph")
    def attack_graph():
        snap = snapshot()
        return jsonify({"ok": True, "attack_graph": (snap.get("innovation_lab") or {}).get("attack_graph", {})})

    @bp.get("/mission-control")
    def mission_control():
        snap = snapshot()
        return jsonify({"ok": True, "mission_control": (snap.get("innovation_lab") or {}).get("mission_control", {})})

    @bp.get("/scenarios")
    def scenario_catalog():
        return jsonify({"ok": True, "scenarios": features.scenario_catalog()})

    @bp.post("/scenario/start")
    def scenario_start():
        payload = json_object()
        scenario_ids = {item["id"] for item in features.scenario_catalog()}
        scenario_id = string(payload, "scenario_id", "gps_spoofing_demo", choices=scenario_ids)
        return jsonify({"ok": True, "scenario_director": features.start_scenario(scenario_id)})

    @bp.post("/scenario/advance")
    def scenario_advance():
        json_object()
        return jsonify(features.advance_scenario())

    @bp.get("/performance-score")
    def performance_score():
        snap = snapshot()
        return jsonify({"ok": True, "performance_score": (snap.get("innovation_lab") or {}).get("performance_score", {})})

    @bp.get("/fleet")
    def fleet():
        snap = snapshot()
        return jsonify({"ok": True, "fleet": (snap.get("innovation_lab") or {}).get("fleet", {})})

    @bp.post("/v2v/share")
    def v2v_share():
        payload = json_object()
        targets = string_list(payload, "target_vehicle_ids", None, max_items=50)
        return jsonify(features.share_v2v_threat(snapshot(), targets))

    @bp.post("/ota/verify")
    def ota_verify():
        payload = json_object()
        for field, maximum in (("package_name", 100), ("version", 32), ("payload", 1000000), ("sha256", 64), ("signature", 128)):
            if field in payload:
                string(payload, field, max_length=maximum)
        if "include_demo_signature" in payload:
            boolean(payload, "include_demo_signature")
        return jsonify({"ok": True, "ota": features.verify_ota(payload)})

    return bp
