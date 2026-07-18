# Live CARLA Attacker Console

This build links the Attacker Console to real CARLA vehicle controls.

Flow:
1. Start `CarlaUE4.exe`.
2. Run `run_carla_windows.bat`.
3. Press `Connect + Spawn`.
4. Press `Start Normal Drive`.
5. Choose an attack in `LIVE ATTACKER CONSOLE`.
6. Press `Apply to CARLA`.
7. Use `Recover Vehicle` to restore natural autonomous driving.

Implemented physical effects:
- Steering Manipulation: disables autopilot and forces steering drift.
- Brake Injection: disables autopilot and applies hard braking.
- Throttle Injection: disables autopilot and applies acceleration.
- CAN Flooding / DoS: applies degraded limp-control behavior.
- GPS Spoofing / Sensor Spoofing: forces route/lane drift.
- Camera/LiDAR Blinding: slows/brakes due perception loss.
- Battery Thermal Tampering: simulates limp mode and thermal owner diagnostics.
- Telemetry Scraping: owner privacy diagnostics with subtle control signature.
- Mixed Emergency Chain: combined steering, braking and multi-system damage.
