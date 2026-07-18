ZONEGUARD PROTECTION INTERLOCK DEMO

This build fixes the live-defense behavior:
- Enable Protection now blocks the normal Attack Console buttons too.
- It also blocks Attacker Takeover controls (Swerve, Full Throttle, Hard Brake).
- Blocked commands do NOT persist on the CARLA actor.
- CARLA recovery restores natural/autopilot driving; dashboard records Safe Mode / command rejection.

COMMITTEE DEMO
1) Start CARLA manually, run ZoneGuard, Connect CARLA, then Spawn Vehicle.
2) Demonstrate the unprotected case:
   - Ensure Protection Standby.
   - Select Steering Manipulation (or Acceleration Injection) and Apply Attack.
   - Vehicle control changes in CARLA.
3) Click Enable Protection in Owner / Defense Console.
   - Dashboard must show Protection Active / Safe Mode Armed.
4) Press the SAME attacker button again.
   - Dashboard toast: "ZoneGuard blocked the attacker command — Safe Mode restored."
   - Owner/Protection panel shows: ATTACK BLOCKED.
   - CARLA returns to natural/autopilot behavior; the malicious steer/throttle does not persist.
5) Try Attacker Takeover (Swerve or Full Throttle) while protection is active.
   - It is blocked and recovery is shown.

NOTE
This is a CARLA simulation containment demonstration. It does not claim real-vehicle or real-CAN protection.
