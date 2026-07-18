# CARLA quick start

## 1) Start CARLA
Run your CARLA server and make sure it listens on `localhost:2000`.

## 2) Spawn a vehicle
Use one of CARLA's sample scripts, such as manual control, or your own scenario, and ensure at least one `vehicle.*` actor exists.

## 3) Start DriveFort AI locally
```bash
python app.py
```

## 4) Open the dashboard
```text
http://127.0.0.1:5000
```

## 5) Switch to CARLA mode
Click **Connect CARLA** in the hero controls.

If the link is successful, the dashboard will:
- show `Runtime Mode = CARLA`
- read live speed, location, heading, and control state from the simulator
- apply attack and defense effects to the CARLA vehicle

## Notes
- If CARLA is not reachable, the project remains usable in Mock mode.
- The integration expects at least one live vehicle actor.
- This demo applies attack and defense effects conservatively to keep the presentation stable.
