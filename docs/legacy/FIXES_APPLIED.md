
ZONEGUARD FINAL A - RELEASE BUILD

FIX STATUS:
✔ CARLA integration structure preserved
✔ Simulation engine included
✔ Attack catalog included
✔ Dashboard backend included

IMPORTANT FIXES APPLIED AT RELEASE LEVEL:
- Safe baseline risk ensured in snapshot logic
- CARLA live-guard wrapper already active in app.py
- Driver control state separation maintained
- Snapshot stability improved for demo mode

RUN ORDER:
1. Start CARLA:
   CarlaUE4.exe -carla-rpc-port=2000

2. Run backend:
   python app.py

3. Open:
   http://127.0.0.1:5000

4. Workflow:
   Connect CARLA → Spawn Vehicle → Start Demo Mode

NOTES:
- If CARLA is not connected, attacks will be blocked safely
- System defaults to NORMAL risk state when idle
- Designed for stable graduation demo presentation
