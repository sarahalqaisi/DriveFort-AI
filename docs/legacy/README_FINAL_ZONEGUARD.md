# ZoneGuard Final Edition

This final edition adds a complete CARLA-ready automotive cyber-defense demo:

1. **No Protection Scenario**: attacker commands reach the vehicle.
2. **ZoneGuard Protected Scenario**: command validation blocks unsafe steering/brake/throttle/BMS commands.
3. **AI Anomaly Detection**: live risk scoring, threat classification and confidence.
4. **Predictive Protection**: estimates risk before/while attacks happen.
5. **Secure Communication Simulation**: signed/trusted command layer with rejected command counters.
6. **Attack Sandbox**: isolates attacker commands so they do not persist in CARLA.
7. **Safe Mode + Emergency Safe Stop**: limits controls and stabilizes the vehicle.
8. **Adaptive Recovery**: restores safe driving and stabilizes the BMS digital twin.
9. **Attack Replay**: dashboard timeline of baseline, attack attempts, blocked commands and recovery.
10. **Owner Awareness**: owner-facing diagnosis, affected systems and recommended action.

Run:

```bat
run_carla_windows.bat
```

Recommended demo flow:

```text
Connect + Spawn -> Start Normal Drive -> Run Final Showcase
```

Manual comparison flow:

```text
Attack Unprotected Vehicle -> Activate ZoneGuard Protection -> Attack Protected Vehicle -> Run Adaptive Recovery
```
