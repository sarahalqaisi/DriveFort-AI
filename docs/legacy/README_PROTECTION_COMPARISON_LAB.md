# ZoneGuard Protection Comparison Lab

This version adds two dashboard-run CARLA scenarios:

1. **Unprotected Vehicle Scenario**: the vehicle drives normally, then the selected attacker-console attack is applied directly to CARLA. The dashboard records the unsafe result and affected systems.
2. **ZoneGuard Protected Scenario**: the same attack is attempted after enabling the innovative protection layer. The system rejects malicious control, enables safe mode, restores natural drive/autopilot, and records evidence.

## Recommended demo flow

1. Start CARLA.
2. Run `run_carla_windows.bat`.
3. Click **Connect + Spawn**.
4. Select an attack in **Live Attacker Console**.
5. Click **1 · Attack Unprotected Vehicle**.
6. Click **2 · Activate ZoneGuard Protection**.
7. Click **3 · Attack Protected Vehicle**.

Or click **Run Full Comparison** to execute the comparison sequence.

Recovery buttons are now separated into **Owner / Defense Console**, while the attacker console only applies attacks.
