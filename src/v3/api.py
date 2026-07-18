from __future__ import annotations

from flask import Blueprint, Response, jsonify, request


def _flatten_report(value, prefix="", depth=0):
    lines = []
    if depth > 5:
        return ["{}: ...".format(prefix or "value")]
    if isinstance(value, dict):
        for key, item in value.items():
            label = "{} / {}".format(prefix, key) if prefix else str(key)
            if isinstance(item, (dict, list)):
                lines.extend(_flatten_report(item, label, depth + 1))
            else:
                lines.append("{}: {}".format(label, item))
    elif isinstance(value, list):
        for index, item in enumerate(value[:40]):
            label = "{} [{}]".format(prefix, index)
            if isinstance(item, (dict, list)):
                lines.extend(_flatten_report(item, label, depth + 1))
            else:
                lines.append("{}: {}".format(label, item))
    else:
        lines.append("{}: {}".format(prefix or "value", value))
    return lines


def _pdf_escape(value):
    return str(value).replace("\\", "/").replace("(", "[").replace(")", "]").encode("latin-1", "replace").decode("latin-1")[:118]


def _report_pdf(report):
    title = "DRIVEFORT AI V3 {} REPORT".format(str(report.get("level", "executive")).upper())
    lines = [title, "Generated: {}".format(report.get("generated_at", "")), ""]
    lines.extend(_flatten_report(report))
    wrapped = []
    for line in lines[:360]:
        text = _pdf_escape(line)
        while len(text) > 100:
            wrapped.append(text[:100])
            text = "  " + text[100:]
        wrapped.append(text)
    pages = [wrapped[index:index + 44] for index in range(0, max(1, len(wrapped)), 44)] or [[title]]

    font_id = 3
    page_ids = []
    objects = {}
    next_id = 4
    for page_number, page_lines in enumerate(pages, 1):
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_ids.append(page_id)
        text_ops = ["BT", "/F1 15 Tf", "52 794 Td", "({}) Tj".format(_pdf_escape(title)), "ET"]
        y = 770
        for line in page_lines:
            size = 9
            text_ops.extend(["BT", "/F1 {} Tf".format(size), "52 {} Td".format(y), "({}) Tj".format(_pdf_escape(line)), "ET"])
            y -= 15
        text_ops.extend(["BT", "/F1 8 Tf", "510 28 Td", "(Page {} of {}) Tj".format(page_number, len(pages)), "ET"])
        stream = "\n".join(text_ops).encode("latin-1")
        objects[page_id] = "{} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 {} 0 R >> >> /Contents {} 0 R >> endobj\n".format(page_id, font_id, content_id).encode("latin-1")
        objects[content_id] = b"%d 0 obj << /Length %d >> stream\n" % (content_id, len(stream)) + stream + b"\nendstream endobj\n"

    kids = " ".join("{} 0 R".format(page_id) for page_id in page_ids)
    objects[1] = b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
    objects[2] = "2 0 obj << /Type /Pages /Kids [{}] /Count {} >> endobj\n".format(kids, len(page_ids)).encode("latin-1")
    objects[font_id] = b"3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0] * (max(objects) + 1)
    for object_id in range(1, max(objects) + 1):
        offsets[object_id] = len(pdf)
        pdf.extend(objects[object_id])
    xref = len(pdf)
    pdf.extend("xref\n0 {}\n0000000000 65535 f \n".format(len(offsets)).encode("latin-1"))
    for object_id in range(1, len(offsets)):
        pdf.extend("{:010d} 00000 n \n".format(offsets[object_id]).encode("latin-1"))
    pdf.extend("trailer << /Size {} /Root 1 0 R >>\nstartxref\n{}\n%%EOF\n".format(len(offsets), xref).encode("latin-1"))
    return bytes(pdf)


def create_v3_blueprint(features, snapshot_provider):
    bp = Blueprint("drivefort_v3", __name__, url_prefix="/api/v3")

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
        return jsonify(features.clear_timeline())

    @bp.get("/ghost-twin")
    def ghost_twin():
        snap = snapshot()
        return jsonify({"ok": True, "ghost_twin": (snap.get("innovation_lab") or {}).get("ghost_twin", {})})

    @bp.post("/benchmark/run")
    def benchmark_run():
        payload = request.get_json(silent=True) or {}
        result = features.run_benchmark(payload.get("attack", "steering_manipulation"), payload.get("intensity", 0.92))
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
        payload = request.get_json(silent=True) or {}
        return jsonify(features.copilot_query(snapshot(), payload.get("question", "")))

    @bp.get("/threat-fusion")
    def threat_fusion():
        snap = snapshot()
        return jsonify({"ok": True, "threat_fusion": (snap.get("innovation_lab") or {}).get("threat_fusion", {})})

    @bp.post("/attack-chain/configure")
    def attack_chain_configure():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "attack_chain": features.configure_attack_chain(payload.get("name", ""), payload.get("stages") or [])})

    @bp.post("/attack-chain/advance")
    def attack_chain_advance():
        return jsonify(features.advance_attack_chain())

    @bp.get("/attack-chain")
    def attack_chain_get():
        snap = snapshot()
        return jsonify({"ok": True, "attack_chain": (snap.get("innovation_lab") or {}).get("attack_chain", {})})

    @bp.post("/adaptive-attacker/run")
    def adaptive_attacker_run():
        payload = request.get_json(silent=True) or {}
        return jsonify(features.adaptive_attack(snapshot(), bool(payload.get("apply_to_engine", False))))

    @bp.post("/stealth/start")
    def stealth_start():
        payload = request.get_json(silent=True) or {}
        return jsonify(features.start_stealth_attack(
            payload.get("attack", "gps_spoofing"),
            payload.get("intensity", 0.22),
            bool(payload.get("apply_to_engine", False)),
        ))

    @bp.post("/stealth/stop")
    def stealth_stop():
        return jsonify({"ok": True, "stealth_mode": features.stop_stealth_attack()})

    @bp.post("/virtual-ecu/activate")
    def virtual_ecu_activate():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "virtual_ecu": features.activate_virtual_ecu(payload.get("ecu_id", "steering_ecu"))})

    @bp.post("/virtual-ecu/deactivate")
    def virtual_ecu_deactivate():
        payload = request.get_json(silent=True) or {}
        return jsonify(features.deactivate_virtual_ecu(payload.get("ecu_id", "steering_ecu")))

    @bp.post("/recovery/playbook/prepare")
    def recovery_prepare():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "playbook": features.prepare_playbook(payload.get("attack", "steering_manipulation"))})

    @bp.post("/recovery/playbook/advance")
    def recovery_advance():
        payload = request.get_json(silent=True) or {}
        return jsonify(features.advance_playbook(bool(payload.get("execute_engine_recovery", False))))

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
            _report_pdf(report_data),
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
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "scenario_director": features.start_scenario(payload.get("scenario_id", "gps_spoofing_demo"))})

    @bp.post("/scenario/advance")
    def scenario_advance():
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
        payload = request.get_json(silent=True) or {}
        targets = payload.get("target_vehicle_ids")
        return jsonify(features.share_v2v_threat(snapshot(), targets if isinstance(targets, list) else None))

    @bp.post("/ota/verify")
    def ota_verify():
        payload = request.get_json(silent=True) or {}
        return jsonify({"ok": True, "ota": features.verify_ota(payload)})

    return bp
