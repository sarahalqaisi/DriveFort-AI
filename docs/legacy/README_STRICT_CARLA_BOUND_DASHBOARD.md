# Strict CARLA-Bound Dashboard Fix

This version makes the dashboard CARLA-first and prevents fake telemetry.

## What changed

- Added `carla_binding` to `/api/state`.
- Dashboard panels now show live values only when CARLA is connected and an ego vehicle actor is linked.
- Attack buttons, manual sliders, BMS controls, recovery/scenario buttons, and vehicle-control actions are disabled in the UI until CARLA is live.
- Backend mutating endpoints return HTTP 400 when CARLA is not live instead of silently updating mock state.
- `/api/update_driver` forwards direct steer/throttle/brake updates to CARLA when live.
- Reset tries to recover the live CARLA actor and restore natural driving when CARLA is live.
- Existing offline unit tests and analytical simulations still work under pytest or when `ZONEGUARD_ALLOW_MOCK=1` is set.

## Runtime behavior

Start CARLA, then use the dashboard Connect/Spawn button. Until the state reports:

```json
"carla_binding": {
  "live": true,
  "source": "CARLA live actor",
  "allows_vehicle_commands": true,
  "allows_attacks": true
}
```

vehicle telemetry, attack effects, collision claims, steering, throttle, and brake controls remain locked.

## Why

The graduation report states that ZoneGuard EV avoids fake telemetry and verifies cyber-physical effects through CARLA. This patch enforces that principle in both frontend and backend.
