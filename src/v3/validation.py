from __future__ import annotations

import math

from flask import jsonify, request


class PayloadValidationError(ValueError):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def validation_error_response(error):
    detail = {"code": "invalid_request", "message": error.message}
    if error.field:
        detail["field"] = error.field
    return jsonify({"ok": False, "error": detail}), 400


def json_object():
    """Return an optional JSON object and reject malformed/non-object bodies."""
    if not request.data:
        return {}
    payload = request.get_json(silent=True)
    if payload is None:
        raise PayloadValidationError("Request body must contain valid JSON.")
    if not isinstance(payload, dict):
        raise PayloadValidationError("Request body must be a JSON object.")
    return payload


def string(payload, field, default="", *, choices=None, max_length=None, allow_empty=True):
    value = payload.get(field, default)
    if not isinstance(value, str):
        raise PayloadValidationError("{} must be a string.".format(field), field)
    value = value.strip()
    if not allow_empty and not value:
        raise PayloadValidationError("{} must not be empty.".format(field), field)
    if max_length is not None and len(value) > max_length:
        raise PayloadValidationError("{} must be at most {} characters.".format(field, max_length), field)
    if choices is not None and value not in choices:
        raise PayloadValidationError(
            "{} must be one of: {}.".format(field, ", ".join(sorted(choices))), field
        )
    return value


def number(payload, field, default, *, minimum=None, maximum=None):
    value = payload.get(field, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PayloadValidationError("{} must be a number.".format(field), field)
    value = float(value)
    if not math.isfinite(value):
        raise PayloadValidationError("{} must be finite.".format(field), field)
    if minimum is not None and value < minimum:
        raise PayloadValidationError("{} must be at least {}.".format(field, minimum), field)
    if maximum is not None and value > maximum:
        raise PayloadValidationError("{} must be at most {}.".format(field, maximum), field)
    return value


def boolean(payload, field, default=False):
    value = payload.get(field, default)
    if not isinstance(value, bool):
        raise PayloadValidationError("{} must be a boolean.".format(field), field)
    return value


def string_list(payload, field, default=None, *, max_items=50):
    value = payload.get(field, default)
    if value is None:
        return None
    if not isinstance(value, list):
        raise PayloadValidationError("{} must be an array of strings.".format(field), field)
    if len(value) > max_items or any(not isinstance(item, str) or not item.strip() for item in value):
        raise PayloadValidationError(
            "{} must contain at most {} non-empty strings.".format(field, max_items), field
        )
    return [item.strip() for item in value]


def attack_stages(payload, approved_attacks):
    stages = payload.get("stages", [])
    if not isinstance(stages, list):
        raise PayloadValidationError("stages must be an array.", "stages")
    if len(stages) > 8:
        raise PayloadValidationError("stages must contain at most 8 items.", "stages")
    validated = []
    for index, stage in enumerate(stages):
        field = "stages[{}]".format(index)
        if not isinstance(stage, dict):
            raise PayloadValidationError("{} must be an object.".format(field), field)
        item = dict(stage)
        item["attack"] = string(item, "attack", "steering_manipulation", choices=approved_attacks)
        item["intensity"] = number(item, "intensity", 0.65, minimum=0.05, maximum=1.0)
        item["duration_sec"] = number(item, "duration_sec", 4, minimum=1, maximum=30)
        item["condition"] = string(item, "condition", "previous_stage_complete", max_length=100)
        validated.append(item)
    return validated
