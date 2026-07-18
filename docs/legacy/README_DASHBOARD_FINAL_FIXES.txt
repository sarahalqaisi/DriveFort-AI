ZoneGuard EV - Final Dashboard Fixes
===================================

This build includes the practical dashboard upgrades and final visual fixes:

1. Smooth Vehicle Tracking
   - Replaced the cartoon car with a clean EV mechanical cutaway.
   - Fixed sizing/cropping so the full vehicle appears inside the dashboard card.
   - Attack-related components are highlighted by ZoneGuard status.

2. Vehicle Prototype / Internal Driver Impact
   - Replaced the abstract outline with a realistic EV diagnostic cutaway.
   - Removed duplicated ECU/CAN label.
   - Fixed object-fit/positioning so the full internal structure is visible.

3. Live Map
   - Added Leaflet/OpenStreetMap live map layer.
   - Added CARLA coordinate projection to a real-looking map area.
   - Added live marker and risk circle overlay.
   - Fallback grid remains visible if internet is unavailable.

4. Driver Control Mode
   - Added Autonomous Driving and Human Keyboard Control modes.
   - Keyboard controls: W accelerate, S brake, A/D steer, Space brake, R recovery.
   - ZoneGuard safety filter remains above driver/autopilot control and can override unsafe commands.

Run:
1. Start CARLA.
2. Run: py -3.7 app.py
3. Open: http://127.0.0.1:5000
4. Press Ctrl+F5 in browser after replacing files.

Note:
Python syntax was checked. Full pytest run was not completed in the packaging environment because Flask is not installed there.
