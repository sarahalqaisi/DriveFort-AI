# ZoneGuard Battery + CARLA Telemetry Update

This version adds a CARLA-bound vehicle telemetry panel and a Battery Management System attack mode.

Important: CARLA 0.9.13 provides real speed, pose, heading, control and sensor data, but it does not provide a real EV battery/BMS model. ZoneGuard therefore uses an EV Battery Digital Twin: speed/controls/attacks from CARLA drive battery SOC, battery temperature and motor temperature.

New features:
- Live vehicle telemetry: speed, coordinates, heading, battery charge, battery temperature, motor temperature.
- BMS Attacker Console: temperature tampering, charge drain/false charge, limp-mode trigger.
- Battery attack affects risk score, AI anomaly detection, owner diagnostics, affected parts and PDF report.
- Recovery clears BMS attacker override and stabilizes thermal telemetry.
