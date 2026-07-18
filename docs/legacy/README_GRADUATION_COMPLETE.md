# ZoneGuard EV Graduation Build

This build focuses on the 9 adopted attacks and the defensive solution:

1. Steering Manipulation — التلاعب بالمقود
2. Brake Override — تجاوز الفرامل
3. Acceleration Injection — حقن التسارع
4. Sensor Spoofing — انتحال الحساسات
5. GPS Spoofing — انتحال GPS
6. CAN Bus Injection — حقن شبكة CAN
7. Denial of Service (DoS) — حجب الخدمة
8. Lane Drift Attack — هجوم انحراف المسار
9. Pedestrian Detection Attack — خداع كشف المشاة

## Adopted Solution

**ZoneGuard EV Security Framework** uses:

- CARLA connection/vehicle validation
- Real-time telemetry collection
- Command Firewall for steering, throttle and brake
- AI anomaly detection and self-test
- Risk scoring
- Fail-safe/adaptive recovery
- Multi-sensor trust validation
- Collision verification through CARLA sensors
- Incident logging and dashboard evidence

## Live CARLA verification

Start CARLA 0.9.13, then run:

```bat
py -3.7 verify_adopted_carla_attacks.py
```

The script runs the 9 adopted attacks against a live CARLA vehicle. It reports
whether CARLA control was applied, the impact target spawned, and whether the
collision sensor verified impact.

If CARLA is not ready, the script fails closed and does not report fake success.
