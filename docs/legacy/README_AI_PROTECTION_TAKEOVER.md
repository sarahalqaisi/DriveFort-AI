# ZoneGuard AI Protection + Attacker Takeover Extension

This version adds a higher-level innovation layer for the CARLA demo:

## New defense features
- AI anomaly detection from live behavior, controls, thermal values and CARLA sensor events.
- Threat classification with target component and confidence.
- Live AI risk score.
- Adaptive recovery that chooses safe mode / control limiting / autopilot restore.
- Owner/Defense console remains separated from Attacker Console.

## New attacker simulation features
- Attacker Console can still apply predefined attacks.
- New Attacker Takeover Mode sends steering, throttle and brake commands directly to the CARLA simulator.
- Presets: swerve right, hard brake, forced acceleration, release inputs.

## Suggested demo flow
1. Start CARLA.
2. Run `run_carla_windows.bat`.
3. Press `Connect + Spawn`.
4. Press `Start Normal Drive`.
5. Use Attacker Takeover Mode or Apply Selected Attack.
6. Show AI risk score and classification rising.
7. Press `Run Adaptive Recovery` or activate protected scenario.
8. Explain that ZoneGuard blocks malicious control, isolates the command path, activates safe mode and restores safe autonomous behavior.

All attacker controls are simulator-only and target the local CARLA vehicle object.
