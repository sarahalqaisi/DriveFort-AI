ZoneGuard EV — Dashboard Runtime Fixes

This build fixes the practical CARLA demo issues:
1. Recovery Vehicle now clears persistent attack runtime and manual takeover, normalizes control, then restores CARLA natural drive.
2. Reset Scenario now clears attack state, risk posture, attack/manual runtime, and restores normal CARLA drive.
3. Dashboard risk starts from NORMAL when no attack is active. A previous attack cannot remain critical after reset/recovery.
4. Dashboard Speed is refreshed from the live CARLA actor velocity after each state snapshot.
5. Acceleration Injection prepares physics/autopilot/gear state and applies persistent high throttle + bounded launch assist when the actor is stationary.
6. Attacker Takeover sliders/presets are persistent CARLA commands, not one-frame requests; they are re-applied every CARLA tick.

Run order:
- Start CARLA manually.
- Start ZoneGuard with python app.py.
- Dashboard: Connect CARLA -> Spawn Vehicle.
- Test: Speed should come from live CARLA. Apply an attack or attacker control.
- Use Recover or Reset Scenario to clear the command and restore normal driving.

This remains a CARLA simulation prototype. No real vehicle, CAN bus, ECU, or physical safety claim is made.
