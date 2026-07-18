# ZoneGuard Evidence + Recovery Plus

This build adds the complete high-value demo flow:

1. **Evidence Recorder**
   - Captures baseline, attack and recovery frames.
   - Stores speed, battery, thermal data, coordinates, CARLA control values, damaged parts and sensor metadata.

2. **Live Severity Meter**
   - Calculates an owner-facing severity score from risk, attack intensity and CARLA control impact.
   - Shows NORMAL / ELEVATED / HIGH / CRITICAL.

3. **Real Recovery Mode**
   - Clears the active attack state.
   - Resets steering, brake and throttle.
   - Restores CARLA Traffic Manager autopilot.
   - Keeps the smooth follow camera active.

4. **Scenario Script**
   - `Run Full Demo` now performs:
     Normal drive -> Live attack -> Evidence capture -> Recovery -> PDF-ready report.

5. **Stronger Incident PDF**
   - Adds severity meter, recovery status and evidence capture rows to the PDF.

## Recommended demo order

```text
Connect + Spawn
Start Normal Drive
Choose attack type
Apply to CARLA
Recover Vehicle
Download PDF
```

Or use:

```text
Run Full Demo
```

The selected attack in the Attacker Console is used by Run Full Demo.
