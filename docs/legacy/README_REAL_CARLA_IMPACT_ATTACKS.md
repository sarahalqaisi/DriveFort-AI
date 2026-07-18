# Real CARLA Physical Impact Attacks

This build keeps the dashboard CARLA-only for live attack effects. No fake crash or fake damage is reported.

What changed:

- Each attacker-console option applies control to the live CARLA ego vehicle only when a CARLA vehicle actor is connected.
- Each attack spawns a real CARLA impact target such as a vehicle or roadside barrier/container near the ego route.
- The bridge holds the malicious control for several CARLA ticks so the effect is visible in the simulator.
- The API returns an `impact` object with `verified=true` only after the CARLA collision sensor fires.
- The dashboard shows whether the result is only an impact target spawned or a verified CARLA collision.

Attack impact mapping:

- Steering Manipulation: drift into roadside wall/barrier.
- Brake Injection: hard braking with rear-end impact risk.
- Throttle Injection: forced acceleration into a front vehicle.
- CAN Flooding / DoS: command availability loss with side collision setup.
- GPS Spoofing: wrong-route drift into roadside wall/barrier.
- Sensor Spoofing: missed obstacle/vehicle collision.
- Camera/LiDAR Blinding: blind forward obstacle impact.
- Battery Thermal Tampering: limp-mode braking with traffic impact risk.
- Telemetry Scraping: location-based trap/roadside impact scenario.
- Mixed Attack: multi-actor crash chain.

Important: if CARLA refuses to spawn an obstacle because the road is occupied, the dashboard will say the impact is not verified instead of pretending a crash happened. Move/spawn the vehicle on a clearer road and apply again.
