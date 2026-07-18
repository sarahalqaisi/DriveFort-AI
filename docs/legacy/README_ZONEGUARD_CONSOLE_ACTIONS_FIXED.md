# ZoneGuard Console Actions — Live CARLA Wiring Fix

This build audits and wires the Owner / Defense Console, Attacker Console, Protection Comparison Lab, AI Recovery controls, and Final Defense Stack controls.

## Live-CARLA rule
For any vehicle-moving action, first:
1. Start `CarlaUE4.exe` manually.
2. Start ZoneGuard.
3. Click **Connect CARLA**.
4. Click **Spawn Vehicle**.
5. Confirm `/api/carla/attack_diagnostics` returns `"ready": true`.

## What each console action now does

| UI action | Live result |
|---|---|
| Reset Scenario | Clears active attack/manual runtime, disarms protection/sandbox, restores baseline natural drive. |
| Recover Vehicle | Clears attack/manual runtime and restores CARLA Traffic Manager/autopilot. |
| Enable Protection | Arms protection + sandbox + secure command validation. Subsequent attacker commands are blocked before persistent CARLA control. |
| Run Protected Scenario | Attempts selected attack, blocks it, applies safe recovery, and records the result. |
| Autonomous | Clears manual/attack runtime and restores CARLA autopilot. |
| Keyboard Control | Disables autopilot and allows W/S/A/D through the ZoneGuard safety filter. |
| Keyboard Safe Stop / Emergency Safe Stop | Applies full brake to the live CARLA actor; use Recover Vehicle to resume autonomous movement. |
| Adaptive Recovery | Uses the same reliable recovery path: clear runtime and restore natural drive. |
| Attack Sandbox | Intercepts attacker commands before they persist in CARLA. |
| Secure Communication | Enables command-validation posture and updates the final-defense status. |
| Final Showcase | Runs unprotected selected attack, recovers, then runs protected attempt and blocks it. |
| Attacker Apply / Manual Takeover / BMS Tamper | Apply only when protection/sandbox is off; get blocked and recovered when protection/sandbox is on. |
| Protection comparison buttons | Use the selected attack: unprotected sends it to CARLA; protected blocks the same command. |

## Validation included

Run:

```bat
python verify_zoneguard_console_actions.py
```

It verifies 27 relevant console button IDs have JavaScript wiring and their backend routes exist.

## Important boundary

This project controls only the CARLA simulator actor. It does not control physical vehicles, real CAN, real ECUs, or real braking systems.
