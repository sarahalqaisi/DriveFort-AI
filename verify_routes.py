"""Verify the Flask route table without starting CARLA."""
from app import app
routes = sorted(rule.rule for rule in app.url_map.iter_rules())
required = "/api/carla/attack_diagnostics"
assert required in routes, f"Missing route: {required}"
print("OK: diagnostics route is registered before app.run()")
