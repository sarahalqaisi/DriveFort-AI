# Nine-Attack Live CARLA Reliability Fix

This patch replaces one-shot dashboard controls with a persistent CARLA attack runtime for the nine adopted **simulation-only** scenarios:

- steering_manipulation
- brake_override
- acceleration_injection
- sensor_spoofing
- gps_spoofing
- can_bus_injection
- dos
- lane_drift_attack
- pedestrian_detection_attack

## What changed

- Each selected attack now keeps applying a bounded, scenario-specific `carla.VehicleControl` profile on every CARLA tick.
- The active scenario is exposed in `sensor_snapshot().attack_runtime` and `GET /api/state` as `live_attack_runtime`.
- GPS, sensor, DoS, CAN-like, and pedestrian scenarios expose explicit simulator overlays so their state is visible even though they are not real RF/CAN/perception exploits.
- The existing `/api/attack/apply` and `/api/carla/force_attack` routes now activate the persistent runtime through `SimulationEngine.apply_carla_attack_console()`.
- `verify_live_carla_attacks.py` checks all nine scenarios while a CARLA server is running.

## Run

1. Start CARLA server first.
2. Install project dependencies.
3. Start the Flask app, connect/spawn the ego vehicle from the dashboard, then select an adopted scenario.
4. Optional live verification:

```bash
python verify_live_carla_attacks.py --host localhost --port 2000
```

## Boundary

All attack effects are bounded simulation behaviour in CARLA. The patch does **not** add real CAN, ECU, GNSS RF, or real-vehicle attack capability.
