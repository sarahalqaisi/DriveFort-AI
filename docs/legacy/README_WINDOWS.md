# ZoneGuard EV - Windows Quick Start

## One-click launch
1. Unzip the project.
2. Double-click `run_windows.bat`.
3. The app opens at `http://127.0.0.1:5000`.

## Manual launch
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

## CARLA mode
CARLA is optional. The dashboard works in mock mode without CARLA.

To use CARLA:
1. Start CARLA on the same machine.
2. Spawn a vehicle in CARLA.
3. Open ZoneGuard and press **Connect CARLA**.
4. If no vehicle actor is found, ZoneGuard stays in mock mode and shows the connection reason.

## New in this build
- Safer API input validation and bounded numeric ranges.
- Production-safe default Flask startup (`debug=False`).
- Guided demo flow with automatic phase progression.
- Additional attack scenarios: GPS spoofing, sensor spoofing, throttle injection, and camera/LiDAR blinding.
- Markdown incident report export.
- Updated explainability and defense strategies for perception and powertrain attacks.

## Final Solution Add-ons

This build adds the full final-demo package:

- Professional dashboard with live risk cards, radar, timeline, KPIs, trust analytics, and system load.
- Smart alerts with UI, simulated audio/SOC/email channels, and incident evidence logging.
- Automatic Safe Mode response with speed limits, command blocking, and recovery status.
- SQLite incident database stored at `data/zoneguard_incidents.db`.
- PDF incident report endpoint: `http://127.0.0.1:5000/api/report/pdf`.
- Ready-made scenarios: Urban Attack, Highway Attack, Sensor Failure, and Mixed Emergency.
- Explainable AI assistant endpoint: `http://127.0.0.1:5000/api/assistant/explain`.
- Replay metadata and event frames for scripted demos.
- API-ready endpoints for integration and testing.
- CARLA remains optional; the app safely falls back to mock mode when CARLA is unavailable.

### Useful API endpoints

```text
GET  /api/state
POST /api/scenario/urban_attack
POST /api/scenario/highway_attack
POST /api/scenario/sensor_failure
POST /api/scenario/mixed_emergency
POST /api/random_attack
GET  /api/incidents
GET  /api/report/pdf
GET  /api/assistant/explain
```

## Pro Edition additions

This build adds a deeper defensive layer on top of the original ZoneGuard demo:

- Sensor Trust Score for GPS, IMU, camera, LiDAR, speed, steering, brake, throttle, battery, and network channels.
- Sensor Fusion that favors trusted sensors and suppresses compromised channels.
- Multi-level Safe Mode: Normal, Alert, Restricted, Emergency, and Full Stop.
- Auto Security Testing from the dashboard and `/api/pro/security_test`.
- Performance metrics: detection time, response time, events per second, false-positive estimate.
- Command Authentication using HMAC-SHA256 signatures.
- Network-layer attack simulation: latency, packet drop, tampering, and bus load.
- Threat Prediction for the next 10 seconds.
- Plugin System catalog to show how future attacks can be added.
- Voice Alerts via browser speech synthesis.
- Mobile-friendly Pro dashboard cards.
- Docker support with `Dockerfile` and `docker-compose.yml`.

### Pro API examples

Run automated security test:

```bat
curl -X POST http://127.0.0.1:5000/api/pro/security_test -H "Content-Type: application/json" -d "{\"rounds\":12}"
```

Sign a command:

```bat
curl -X POST http://127.0.0.1:5000/api/pro/command/sign -H "Content-Type: application/json" -d "{\"steer\":0.1,\"throttle\":0.2,\"brake\":0,\"issued_by\":\"operator\"}"
```

Run with Docker:

```bat
docker compose up --build
```

## CARLA Full Integration mode

This package includes a CARLA Full Integration version in addition to Mock mode.

### Run with CARLA

1. Start CARLA first:

```bat
CarlaUE4.exe -quality-level=Low
```

2. Make sure CARLA's Python egg is on `PYTHONPATH`. Example:

```bat
set PYTHONPATH=C:\CARLA_0.9.13\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-py3.8-win-amd64.egg;%PYTHONPATH%
```

3. Run:

```bat
run_carla_windows.bat
```

4. Open `http://127.0.0.1:5000` and press **Connect CARLA Full**.

The dashboard can now spawn/connect a Electric Vehicle, enable synchronous ticks, read live state and sensors, and apply attack/defense controls back to the CARLA vehicle.

Full details are in `docs/CARLA_FULL_INTEGRATION.md`.

## CARLA/Python auto-compatibility

Use `run_carla_windows.bat` for live CARLA mode. It checks your local Python version against the CARLA Python API egg and automatically adds the matching egg to the app path when found. If no matching egg is available, it prints the mismatch and continues in safe Mock mode.

If CARLA is installed outside common folders, set `CARLA_ROOT` first:

```bat
set CARLA_ROOT=C:\CARLA_0.9.xx
run_carla_windows.bat
```

For a standalone diagnosis, run:

```bat
python check_carla_python_compat.py
```

See `docs/CARLA_PYTHON_COMPATIBILITY_WINDOWS.md` for details.
