# DriveFort AI Tesla - CARLA Full Integration Version

This version keeps the normal Mock mode, but adds a real CARLA live mode.

## What is now integrated

- Direct CARLA client connection to `localhost:2000` by default.
- Tesla Model 3 actor discovery, with optional spawn if no vehicle exists.
- Live vehicle state reading: speed, steering, throttle, brake, heading and location.
- Live sensors: GNSS, IMU, collision, lane invasion, RGB camera metadata and LiDAR point count.
- Optional synchronous simulation ticks.
- Live loop start/stop from API.
- Attack effects applied back to CARLA control.
- Safe mode and defense actions applied back to CARLA control.
- Mock fallback when CARLA is not installed or not running.

## Windows setup

1. Install CARLA for Windows.
2. Start CARLA first, for example:

```bat
CarlaUE4.exe -quality-level=Low
```

3. Make the CARLA Python package visible to this project. Example:

```bat
set PYTHONPATH=C:\CARLA_0.9.13\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-py3.8-win-amd64.egg;%PYTHONPATH%
```

Use the egg that matches your CARLA and Python version.

4. Run:

```bat
run_carla_windows.bat
```

5. Open:

```text
http://127.0.0.1:5000
```

6. Press `Connect CARLA` in the dashboard, or call the API below.

## API endpoints

### Connect full live mode

```http
POST /api/carla/connect
Content-Type: application/json

{
  "host": "localhost",
  "port": 2000,
  "spawn_if_missing": true,
  "synchronous": true,
  "fps": 20
}
```

### Spawn or connect vehicle

```http
POST /api/carla/spawn
```

### One deterministic tick

```http
POST /api/carla/tick
```

### Start/stop live loop

```http
POST /api/carla/live/start
POST /api/carla/live/stop
```

### Sensor snapshot

```http
GET /api/carla/sensors
```

## Full dynamic behavior

When CARLA mode is active, every dashboard refresh does this sequence:

1. Read live vehicle and sensor state from CARLA.
2. Run DriveFort AI risk assessment.
3. Run attack/fusion/trust/defense logic.
4. Apply attack effect to CARLA vehicle control.
5. Apply safe-mode defense to CARLA vehicle control.
6. Return updated state to the dashboard.

## Limitations

- RGB camera preview is stored as metadata in this lightweight build. For full video streaming, add JPEG encoding from CARLA raw BGRA frames and expose it as an MJPEG endpoint.
- CARLA version and Python version must match. This is a CARLA requirement, not a DriveFort AI limitation.
- The project still runs without CARLA in Mock mode for presentations and testing.
