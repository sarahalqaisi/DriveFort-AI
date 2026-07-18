from __future__ import annotations

import base64
import math
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .models import AttackState, RiskBundle, VehicleState
from .attack_catalog import canonical_attack
from .carla_runtime import ensure_carla_on_path

_CARLA_PATH_READY, _CARLA_PATH_MESSAGE = ensure_carla_on_path()
try:
    import carla  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    carla = None


@dataclass
class CarlaStatus:
    enabled: bool = False
    connected: bool = False
    actor_found: bool = False
    sensors_ready: bool = False
    synchronous_mode: bool = False
    live_loop_running: bool = False
    map_name: str = "N/A"
    host: str = "localhost"
    port: int = 2000
    vehicle_id: Optional[int] = None
    vehicle_type: str = "vehicle.tesla.model3"
    fps: float = 20.0
    last_tick: int = 0
    message: str = "CARLA integration unavailable."

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "actor_found": self.actor_found,
            "sensors_ready": self.sensors_ready,
            "synchronous_mode": self.synchronous_mode,
            "live_loop_running": self.live_loop_running,
            "map_name": self.map_name,
            "host": self.host,
            "port": self.port,
            "vehicle_id": self.vehicle_id,
            "vehicle_type": self.vehicle_type,
            "fps": self.fps,
            "last_tick": self.last_tick,
            "message": self.message,
        }


class CarlaBridge:
    """Real-time CARLA bridge with a safe mock fallback.

    This class is intentionally import-safe on machines without the CARLA Python
    package. When CARLA is installed, it can:
      * connect to a running CARLA server,
      * find or spawn a Tesla Model 3 actor,
      * attach GNSS, IMU, collision, lane invasion, camera and LiDAR sensors,
      * read live vehicle state,
      * inject attack effects into vehicle control,
      * apply DriveFort AI defensive controls back to CARLA,
      * run in synchronous tick mode for deterministic demos.
    """

    def __init__(self, host: str = "localhost", port: int = 2000, fps: float = 20.0) -> None:
        self.host = host
        self.port = port
        self.fps = fps
        self.client = None
        self.world = None
        self.vehicle = None
        self.original_settings = None
        self.sensors: List[Any] = []
        self.sensor_data: Dict[str, Any] = {
            "gnss": None,
            "imu": None,
            "collision": None,
            "lane_invasion": None,
            "camera_frame": None,
            "lidar_points": 0,
            "last_sensor_ts": 0.0,
        }
        self._lock = threading.RLock()
        self._live_thread: Optional[threading.Thread] = None
        self._live_stop = threading.Event()
        self.status = CarlaStatus(enabled=carla is not None, host=host, port=port, fps=fps)
        self._spectator_alpha = 0.18
        self._route_mode = "normal"
        # CARLA Python API exposes set_autopilot(), but it does not expose
        # Vehicle.is_autopilot_enabled().  Track the mode locally so state
        # reads and diagnostics never call a non-existent CARLA method.
        self._zg_autopilot_enabled = False
        self._last_attack_notice = "No active attack."
        self._damaged_parts = []
        self._impact_actors = []
        self._last_impact_report = {"active": False, "verified": False, "severity": "none", "target": "none", "message": "No CARLA impact event yet."}
        if carla is None:
            self.status.message = _CARLA_PATH_MESSAGE

    def connect(self, host: Optional[str] = None, port: Optional[int] = None, spawn_if_missing: bool = False, synchronous: bool = False, fps: Optional[float] = None) -> CarlaStatus:
        if carla is None:
            return self.status
        if host:
            self.host = host
        if port:
            self.port = int(port)
        if fps:
            self.fps = float(fps)
        self.status.host = self.host
        self.status.port = self.port
        self.status.fps = self.fps
        try:
            self.client = carla.Client(self.host, self.port)
            self.client.set_timeout(5.0)
            self.world = self.client.get_world()
            self.status.map_name = getattr(self.world.get_map(), "name", "Unknown")
            self._configure_sync(synchronous)
            self._configure_traffic_manager()
            self.vehicle = self._find_vehicle()
            if self.vehicle is None and spawn_if_missing:
                self.vehicle = self._spawn_tesla_model3()
            self.status.connected = True
            self.status.actor_found = self.vehicle is not None
            self.status.vehicle_id = int(self.vehicle.id) if self.vehicle is not None else None
            if self.vehicle is not None:
                self._focus_spectator(self.vehicle)
                self._attach_sensors()
                self.status.message = "Connected to CARLA with live vehicle and sensors."
            else:
                self.status.message = "Connected to CARLA, but no vehicle actor was found. Enable spawn_if_missing or spawn one in CARLA."
            return self.status
        except Exception as exc:  # pragma: no cover - requires CARLA runtime
            self.status.connected = False
            self.status.actor_found = False
            self.status.sensors_ready = False
            self.status.message = f"CARLA connection failed: {exc}"
            return self.status

    def disconnect(self) -> CarlaStatus:
        self.stop_live_loop()
        self._destroy_sensors()
        self._cleanup_impact_actors()
        self._restore_settings()
        self.client = None
        self.world = None
        self.vehicle = None
        self.status.connected = False
        self.status.actor_found = False
        self.status.sensors_ready = False
        self.status.synchronous_mode = False
        self.status.vehicle_id = None
        self.status.message = "Disconnected from CARLA."
        return self.status

    def _configure_sync(self, synchronous: bool) -> None:
        if not self.world:
            return
        settings = self.world.get_settings()
        if self.original_settings is None:
            self.original_settings = settings
        settings.synchronous_mode = bool(synchronous)
        settings.fixed_delta_seconds = 1.0 / max(1.0, self.fps) if synchronous else None
        self.world.apply_settings(settings)
        self.status.synchronous_mode = bool(synchronous)

    def _restore_settings(self) -> None:
        if self.world is not None and self.original_settings is not None:
            try:
                self.world.apply_settings(self.original_settings)
            except Exception:
                pass
        self.original_settings = None

    def _find_vehicle(self):
        if self.world is None:
            return None
        vehicles = list(self.world.get_actors().filter("vehicle.*"))
        for actor in vehicles:
            type_id = getattr(actor, "type_id", "")
            role = actor.attributes.get("role_name", "") if hasattr(actor, "attributes") else ""
            if "tesla.model3" in type_id or role in {"hero", "ego", "zoneguard"}:
                return actor
        return vehicles[0] if vehicles else None

    def _configure_traffic_manager(self) -> None:
        if self.client is None or carla is None:
            return
        try:
            tm = self.client.get_trafficmanager(8000)
            tm.set_synchronous_mode(bool(self.status.synchronous_mode))
            tm.set_global_distance_to_leading_vehicle(2.5)
            tm.global_percentage_speed_difference(-8.0)
            tm.set_hybrid_physics_mode(True)
        except Exception:
            pass

    def enable_natural_drive(self, speed_percent: float = -8.0) -> Dict[str, Any]:
        if not self.is_ready():
            return {"ok": False, "message": "CARLA vehicle is not ready."}
        try:
            tm = self.client.get_trafficmanager(8000) if self.client else None
            if tm is not None:
                try:
                    tm.set_synchronous_mode(bool(self.status.synchronous_mode))
                    tm.set_global_distance_to_leading_vehicle(2.5)
                    tm.ignore_lights_percentage(self.vehicle, 0.0)
                    tm.ignore_signs_percentage(self.vehicle, 0.0)
                    tm.vehicle_percentage_speed_difference(self.vehicle, float(speed_percent))
                    self.vehicle.set_autopilot(True, tm.get_port())
                except Exception:
                    self.vehicle.set_autopilot(True)
            else:
                self.vehicle.set_autopilot(True)
            self._zg_autopilot_enabled = True
            self._route_mode = "natural_autopilot"
            self.status.message = "Natural autonomous driving enabled. Vehicle follows CARLA traffic manager."
            return {"ok": True, "message": self.status.message}
        except Exception as exc:
            self.status.message = f"Natural drive failed: {exc}"
            return {"ok": False, "message": self.status.message}

    def _spawn_tesla_model3(self):
        """Spawn an ego Tesla reliably and move the CARLA camera to it."""
        if self.world is None or carla is None:
            return None
        blueprints = self.world.get_blueprint_library()
        candidates = list(blueprints.filter("vehicle.tesla.model3")) or list(blueprints.filter("vehicle.*model3*")) or list(blueprints.filter("vehicle.*"))
        if not candidates:
            self.status.message = "No vehicle blueprints were found in this CARLA map."
            return None

        bp = candidates[0]
        if bp.has_attribute("role_name"):
            bp.set_attribute("role_name", "zoneguard")
        if bp.has_attribute("color"):
            vals = bp.get_attribute("color").recommended_values
            if vals:
                bp.set_attribute("color", vals[min(2, len(vals) - 1)])

        spawn_points = list(self.world.get_map().get_spawn_points())
        if not spawn_points:
            spawn_points = [carla.Transform(carla.Location(x=0.0, y=0.0, z=1.0), carla.Rotation(yaw=0.0))]

        actor = None
        last_error = None
        for transform in spawn_points:
            try:
                actor = self.world.try_spawn_actor(bp, transform)
                if actor is not None:
                    break
            except Exception as exc:
                last_error = exc

        if actor is None:
            try:
                fallback = spawn_points[0]
                fallback.location.z += 1.0
                actor = self.world.spawn_actor(bp, fallback)
            except Exception as exc:
                last_error = exc
                self.status.message = f"Vehicle spawn failed: {last_error}"
                return None

        self.vehicle = actor
        self.enable_natural_drive()
        self._focus_spectator(actor, instant=True)
        self.status.message = f"Spawned Tesla Model 3 actor id={actor.id}."
        return actor

    def _focus_spectator(self, actor=None, instant: bool = False) -> None:
        if self.world is None or carla is None:
            return
        actor = actor or self.vehicle
        if actor is None:
            return
        try:
            tr = actor.get_transform()
            yaw = math.radians(tr.rotation.yaw)
            target_loc = carla.Location(
                x=tr.location.x - 9.0 * math.cos(yaw),
                y=tr.location.y - 9.0 * math.sin(yaw),
                z=tr.location.z + 4.6,
            )
            target_rot = carla.Rotation(pitch=-16.0, yaw=tr.rotation.yaw, roll=0.0)
            spectator = self.world.get_spectator()
            if instant:
                spectator.set_transform(carla.Transform(target_loc, target_rot))
                return
            cur = spectator.get_transform()
            a = self._spectator_alpha
            loc = carla.Location(
                x=cur.location.x + (target_loc.x - cur.location.x) * a,
                y=cur.location.y + (target_loc.y - cur.location.y) * a,
                z=cur.location.z + (target_loc.z - cur.location.z) * a,
            )
            dyaw = ((target_rot.yaw - cur.rotation.yaw + 180.0) % 360.0) - 180.0
            rot = carla.Rotation(
                pitch=cur.rotation.pitch + (target_rot.pitch - cur.rotation.pitch) * a,
                yaw=cur.rotation.yaw + dyaw * a,
                roll=0.0,
            )
            spectator.set_transform(carla.Transform(loc, rot))
        except Exception:
            pass

    def _destroy_sensors(self) -> None:
        for sensor in self.sensors:
            try:
                sensor.stop()
            except Exception:
                pass
            try:
                sensor.destroy()
            except Exception:
                pass
        self.sensors = []
        self.status.sensors_ready = False

    def _attach_sensors(self) -> None:
        if not self.world or not self.vehicle or carla is None:
            return
        self._destroy_sensors()
        bps = self.world.get_blueprint_library()

        def spawn_sensor(pattern: str, transform, callback):
            bp_list = bps.filter(pattern)
            if not bp_list:
                return None
            sensor = self.world.spawn_actor(bp_list[0], transform, attach_to=self.vehicle)
            sensor.listen(callback)
            self.sensors.append(sensor)
            return sensor

        spawn_sensor("sensor.other.gnss", carla.Transform(carla.Location(x=0.0, z=2.2)), self._on_gnss)
        spawn_sensor("sensor.other.imu", carla.Transform(carla.Location(x=0.0, z=2.0)), self._on_imu)
        spawn_sensor("sensor.other.collision", carla.Transform(), self._on_collision)
        spawn_sensor("sensor.other.lane_invasion", carla.Transform(), self._on_lane_invasion)
        cam_bps = bps.filter("sensor.camera.rgb")
        if cam_bps:
            cam_bp = cam_bps[0]
            if cam_bp.has_attribute("image_size_x"):
                cam_bp.set_attribute("image_size_x", "640")
            if cam_bp.has_attribute("image_size_y"):
                cam_bp.set_attribute("image_size_y", "360")
            if cam_bp.has_attribute("fov"):
                cam_bp.set_attribute("fov", "90")
            cam = self.world.spawn_actor(cam_bp, carla.Transform(carla.Location(x=1.6, z=1.7), carla.Rotation(pitch=-8)), attach_to=self.vehicle)
            cam.listen(self._on_camera)
            self.sensors.append(cam)
        spawn_sensor("sensor.lidar.ray_cast", carla.Transform(carla.Location(x=0.0, z=2.4)), self._on_lidar)
        self.status.sensors_ready = len(self.sensors) > 0

    def _on_gnss(self, event) -> None:
        with self._lock:
            self.sensor_data["gnss"] = {"lat": float(event.latitude), "lon": float(event.longitude), "alt": float(event.altitude)}
            self.sensor_data["last_sensor_ts"] = time.time()

    def _on_imu(self, event) -> None:
        with self._lock:
            self.sensor_data["imu"] = {
                "accelerometer": {"x": float(event.accelerometer.x), "y": float(event.accelerometer.y), "z": float(event.accelerometer.z)},
                "gyroscope": {"x": float(event.gyroscope.x), "y": float(event.gyroscope.y), "z": float(event.gyroscope.z)},
                "compass": float(event.compass),
            }
            self.sensor_data["last_sensor_ts"] = time.time()

    def _impact_severity_from_impulse(self, intensity: float) -> str:
        """Convert CARLA normal impulse into a dashboard-friendly damage label."""
        value = float(intensity or 0.0)
        if value >= 4500.0:
            return "critical"
        if value >= 1800.0:
            return "severe"
        if value >= 600.0:
            return "moderate"
        if value > 0.0:
            return "minor"
        return "none"

    def _on_collision(self, event) -> None:
        impulse = event.normal_impulse
        intensity = math.sqrt(impulse.x ** 2 + impulse.y ** 2 + impulse.z ** 2)
        severity = self._impact_severity_from_impulse(float(intensity))
        target = getattr(event.other_actor, "type_id", "actor")
        with self._lock:
            self.sensor_data["collision"] = {
                "actor_id": int(event.other_actor.id),
                "target": target,
                "intensity": round(float(intensity), 3),
                "severity": severity,
                "ts": time.time(),
            }
            self._last_impact_report = {
                "active": True,
                "verified": True,
                "severity": severity if severity != "none" else "critical",
                "target": target,
                "message": "Verified CARLA collision sensor event: %s impact, normal impulse %.3f" % (severity, float(intensity)),
            }

    def _on_lane_invasion(self, event) -> None:
        markings = [str(x.type) for x in event.crossed_lane_markings]
        with self._lock:
            self.sensor_data["lane_invasion"] = {"markings": markings, "ts": time.time()}

    def _on_camera(self, image) -> None:
        # Keep raw BGRA bytes metadata-light. The browser can consume the JPEG endpoint later if CARLA image conversion is available.
        with self._lock:
            self.sensor_data["camera_frame"] = {"width": int(image.width), "height": int(image.height), "frame": int(image.frame), "ts": time.time()}
            self.sensor_data["last_sensor_ts"] = time.time()

    def _on_lidar(self, data) -> None:
        with self._lock:
            self.sensor_data["lidar_points"] = int(len(data))
            self.sensor_data["last_sensor_ts"] = time.time()


    def _cleanup_impact_actors(self) -> None:
        """Remove only obstacles/vehicles spawned by the DriveFort AI attack lab."""
        actors = list(getattr(self, "_impact_actors", []) or [])
        self._impact_actors = []
        for actor in actors:
            try:
                if actor is not None and actor.is_alive:
                    actor.destroy()
            except Exception:
                pass

    def _relative_transform(self, forward_m: float = 12.0, side_m: float = 0.0, yaw_delta: float = 0.0):
        if self.vehicle is None or carla is None:
            return None
        tr = self.vehicle.get_transform()
        yaw = math.radians(float(tr.rotation.yaw))
        loc = carla.Location(
            x=tr.location.x + forward_m * math.cos(yaw) - side_m * math.sin(yaw),
            y=tr.location.y + forward_m * math.sin(yaw) + side_m * math.cos(yaw),
            z=tr.location.z + 0.25,
        )
        rot = carla.Rotation(pitch=0.0, yaw=tr.rotation.yaw + yaw_delta, roll=0.0)
        return carla.Transform(loc, rot)

    def _spawn_impact_actor(self, attack_name: str, target_kind: str = "vehicle", forward_m: float = 13.0, side_m: float = 0.0, yaw_delta: float = 180.0):
        """Spawn a real CARLA target for the graduation impact scene.

        The method deliberately fails closed: it returns ``None`` when CARLA
        cannot spawn a real actor.  Damage is verified only by CARLA collision
        events, never by fabricated telemetry.
        """
        if not self.world or carla is None:
            return None, "CARLA world is not ready for impact actor spawning."
        # Hard guard against fake-looking demos: never spawn impact actors on
        # top of the ego vehicle.  Even if a caller passes a short distance,
        # keep targets far enough ahead/aside so the ego vehicle must move into
        # them under attack control.
        forward_m = max(10.0, float(forward_m))
        side_m = float(side_m)
        try:
            bps = self.world.get_blueprint_library()
            if target_kind == "vehicle":
                patterns = ["vehicle.audi.tt", "vehicle.lincoln.mkz_2017", "vehicle.tesla.model3", "vehicle.*"]
            elif target_kind == "wall":
                patterns = ["static.prop.container", "static.prop.streetbarrier", "static.prop.constructioncone", "static.*"]
            elif target_kind == "pedestrian":
                patterns = ["walker.pedestrian.*", "static.prop.streetbarrier", "vehicle.*"]
            else:
                patterns = ["static.prop.streetbarrier", "vehicle.*", "static.*"]

            bp = None
            for pattern in patterns:
                found = list(bps.filter(pattern))
                if found:
                    bp = found[0]
                    break
            if bp is None:
                return None, "No suitable CARLA blueprint found for impact target."

            if bp.has_attribute("role_name"):
                bp.set_attribute("role_name", "zoneguard_impact_target")
            if target_kind == "pedestrian" and bp.has_attribute("is_invincible"):
                bp.set_attribute("is_invincible", "false")

            attempts = [
                (forward_m, side_m),
                (forward_m + 3.0, side_m),
                (max(3.0, forward_m - 2.0), side_m),
                (forward_m, side_m + 1.0),
                (forward_m, side_m - 1.0),
            ]
            actor = None
            last_tr = None
            for fwd, side in attempts:
                tr = self._relative_transform(forward_m=fwd, side_m=side, yaw_delta=yaw_delta)
                last_tr = tr
                if tr is None:
                    continue
                try:
                    actor = self.world.try_spawn_actor(bp, tr)
                except Exception:
                    actor = None
                if actor is not None:
                    break
            if actor is None and last_tr is not None:
                # Last resort: regular spawn_actor gives a useful exception on many maps.
                try:
                    actor = self.world.spawn_actor(bp, last_tr)
                except Exception:
                    actor = None
            if actor is None:
                return None, "CARLA refused all impact target spawn points; move the ego vehicle to a clearer road segment."

            self._impact_actors.append(actor)
            try:
                # Keep targets physically plausible and stationary. Static props do
                # not need physics impulses, and vehicles should be stopped with
                # brakes rather than locked with handbrake to reduce bounce/flying.
                if hasattr(actor, "set_simulate_physics"):
                    actor.set_simulate_physics(False if target_kind in {"wall", "pedestrian"} else True)
            except Exception:
                pass
            if target_kind == "vehicle":
                try:
                    actor.set_autopilot(False)
                    actor.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0, hand_brake=False, reverse=False))
                except Exception:
                    pass
            return actor, "Impact target spawned: %s id=%s" % (getattr(actor, "type_id", target_kind), getattr(actor, "id", "?"))
        except Exception as exc:
            return None, "Impact target spawn failed: %s" % exc

    def _place_actor_relative_to_vehicle(self, actor, forward_m: float = 3.0, side_m: float = 0.0, yaw_delta: float = 180.0) -> None:
        """Move an already spawned CARLA actor into the intended impact path."""
        if actor is None or not self.is_ready() or carla is None:
            return
        try:
            tr = self._relative_transform(forward_m=forward_m, side_m=side_m, yaw_delta=yaw_delta)
            if tr is not None and getattr(actor, "is_alive", True):
                actor.set_transform(tr)
                if getattr(actor, "type_id", "").startswith("vehicle."):
                    actor.apply_control(carla.VehicleControl(throttle=0.0, brake=1.0, steer=0.0, hand_brake=True))
        except Exception:
            pass

    def _apply_forward_velocity(self, speed_ms: float) -> None:
        """Deprecated safety shim.

        Older demo builds used ``set_target_velocity`` on every tick to force a
        fast visual impact. In CARLA this can create unrealistic physics: the
        ego vehicle may jump, slide violently, or fly after contact because the
        simulator keeps receiving external velocity impulses.

        The realistic demo path below now relies only on regular
        ``VehicleControl`` throttle/brake/steer commands and CARLA physics. This
        method is intentionally left as a no-op so old call sites cannot inject
        non-physical velocity.
        """
        return

    def _prepare_vehicle_for_realistic_attack(self) -> None:
        """Put the ego vehicle in a stable, grounded state before an attack.

        This avoids the common CARLA demo bug where a previous autopilot command,
        handbrake, reverse gear, or angular velocity remains active and makes the
        next attack look like a physics explosion instead of a vehicle response.
        """
        if not self.is_ready() or carla is None:
            return
        try:
            self.vehicle.set_autopilot(False)
        except Exception:
            pass
        try:
            stable = carla.VehicleControl(throttle=0.0, steer=0.0, brake=1.0, hand_brake=False, reverse=False)
            self.vehicle.apply_control(stable)
            if self.status.synchronous_mode and self.world is not None:
                self.world.tick()
            else:
                time.sleep(0.08)
        except Exception:
            pass

    @staticmethod
    def _realistic_control_from_plan(control, attack_name: str, intensity: float):
        """Clamp attack commands to plausible vehicle-control ranges.

        We still demonstrate clear cyber-physical effects, but we avoid full
        steering at high throttle and avoid external speed injection. This keeps
        the vehicle grounded and believable in front of the exam committee.
        """
        attack_name = canonical_attack(attack_name)
        intensity = max(0.0, min(1.0, float(intensity or 0.0)))

        # Safe upper bounds chosen for a visible but realistic CARLA demo.
        max_throttle = 0.62
        max_steer = 0.38
        if attack_name in {"lane_drift_attack", "gps_spoofing", "sensor_spoofing", "dos"}:
            max_steer = 0.24
            max_throttle = 0.48
        if attack_name == "steering_manipulation":
            max_steer = 0.34
            max_throttle = 0.42
        if attack_name == "can_bus_injection":
            max_steer = 0.22
            max_throttle = 0.38
        if attack_name == "brake_override":
            max_throttle = 0.45
        if attack_name == "pedestrian_detection_attack":
            max_throttle = 0.40

        control.steer = max(-max_steer, min(max_steer, float(getattr(control, "steer", 0.0))))
        control.throttle = max(0.0, min(max_throttle, float(getattr(control, "throttle", 0.0))))
        control.brake = max(0.0, min(1.0, float(getattr(control, "brake", 0.0))))
        try:
            control.hand_brake = False
            control.reverse = False
        except Exception:
            pass
        return control

    @staticmethod
    def _ramp_control(start_control, target_control, alpha: float):
        """Linearly blend from current control to target attack control."""
        alpha = max(0.0, min(1.0, float(alpha)))
        start_control.steer = float(getattr(start_control, "steer", 0.0)) + (float(getattr(target_control, "steer", 0.0)) - float(getattr(start_control, "steer", 0.0))) * alpha
        start_control.throttle = float(getattr(start_control, "throttle", 0.0)) + (float(getattr(target_control, "throttle", 0.0)) - float(getattr(start_control, "throttle", 0.0))) * alpha
        start_control.brake = float(getattr(start_control, "brake", 0.0)) + (float(getattr(target_control, "brake", 0.0)) - float(getattr(start_control, "brake", 0.0))) * alpha
        try:
            start_control.hand_brake = False
            start_control.reverse = False
        except Exception:
            pass
        return start_control

    def _tick_for_visible_impact(self, control, seconds: float = 4.8, target_speed_ms: float = 12.0, primary_actor=None, nudge_side_m: float = 0.0, attack_name: str = "") -> Dict[str, Any]:
        """Hold malicious controls long enough for a visible CARLA impact.

        Important demo-safety rule: once a target vehicle, pedestrian, or obstacle
        is spawned, it remains stationary.  We never move/teleport the target into
        the ego vehicle during the run.  The visible effect must come from the ego
        vehicle itself: acceleration, brake suppression, steering drift, or loss of
        control.  Damage is still counted only when CARLA's collision sensor reports
        an actual collision.
        """
        if not self.is_ready() or carla is None:
            return {"verified": False, "message": "CARLA vehicle is not ready."}
        ticks = max(20, int(float(seconds) * max(8.0, float(self.fps or 20.0))))
        collision_before = self.sensor_snapshot().get("collision")
        last_collision = collision_before
        target_control = self._realistic_control_from_plan(control, attack_name, 1.0)
        self._prepare_vehicle_for_realistic_attack()
        for idx in range(ticks):
            try:
                self.vehicle.set_autopilot(False)
                # Smooth ramp for the first second prevents instant lateral impulse
                # and keeps the demo realistic instead of acrobatic.
                alpha = min(1.0, (idx + 1) / max(1.0, min(float(self.fps or 20.0), 20.0)))
                current = self.vehicle.get_control()
                applied = self._ramp_control(current, target_control, alpha)
                self.vehicle.apply_control(applied)

                self._focus_spectator(self.vehicle, instant=False)
                if self.status.synchronous_mode and self.world is not None:
                    self.world.tick()
                else:
                    time.sleep(1.0 / max(8.0, float(self.fps or 20.0)))
                last_collision = self.sensor_snapshot().get("collision")
                if last_collision and last_collision != collision_before:
                    break
            except Exception:
                break
        collision_after = self.sensor_snapshot().get("collision")
        verified = bool(collision_after and collision_after != collision_before)
        if verified:
            severity = collision_after.get("severity") or self._impact_severity_from_impulse(collision_after.get("intensity", 0.0))
            return {"verified": True, "message": "CARLA collision sensor verified a %s physical impact caused by ego-vehicle motion." % severity, "collision": collision_after}
        return {"verified": False, "message": "Targets stayed stationary; ego-vehicle attack controls were applied, but CARLA collision sensor has not confirmed contact yet.", "collision": collision_after or last_collision}

    def _configure_attack_impact(self, attack_name: str, intensity: float) -> Tuple[List[str], Dict[str, Any], Any, float, float, Any, float]:
        """Build attack-specific severe-impact controls and a real CARLA scene."""
        attack_name = canonical_attack(attack_name)
        control = self.vehicle.get_control()
        steer = float(getattr(control, "steer", 0.0)); throttle = float(getattr(control, "throttle", 0.0)); brake = float(getattr(control, "brake", 0.0))
        impact = {"active": True, "verified": False, "severity": "critical", "target": "none", "message": "Severe CARLA impact setup pending.", "scene": []}
        damaged: List[str] = []

        # The adopted graduation attacks use aggressive targets so the effect is
        # obvious on vehicles/pedestrians.  CARLA still decides whether the
        # physical collision is verified by the collision sensor.
        plans = {
            "steering_manipulation": {
                "control": (0.95 * intensity, 0.72 * intensity, 0.0),
                "target": ("wall", 14.0, 3.0),
                "seconds": 5.5,
                "speed": 8.0,
                "nudge_side": 0.0,
                "damaged": ["Steering ECU", "Lane keeping controller", "Side body", "Suspension", "Roadside wall/building impact"],
                "route": "attack_steering_severe_side_impact",
            },
            "brake_override": {
                "control": (0.0, 0.92 * intensity, 0.0),
                "target": ("vehicle", 14.0, 0.0),
                "seconds": 5.5,
                "speed": 8.0,
                "nudge_side": 0.0,
                "damaged": ["Brake ECU", "ABS/Brake assist", "Front bumper", "Hood", "Front collision from brake suppression"],
                "route": "attack_brake_override_severe_front_impact",
            },
            "acceleration_injection": {
                # Target is intentionally placed far enough ahead so the demo clearly
                # shows the ego vehicle accelerating first, then colliding.  It is not
                # teleported into the ego vehicle path during the run.
                "control": (0.0, 1.0, 0.0),
                "target": ("vehicle", 22.0, 0.0),
                "seconds": 6.0,
                "speed": 9.0,
                "nudge_side": 0.0,
                "damaged": ["Powertrain ECU", "Acceleration control", "Front bumper", "Battery pack crash risk", "High-speed front vehicle collision"],
                "route": "attack_acceleration_ego_vehicle_speeds_into_target",
            },
            "sensor_spoofing": {
                "control": (-0.54 * intensity, 0.64 * intensity, 0.0),
                "target": ("pedestrian", 15.0, -1.0),
                "seconds": 5.5,
                "speed": 7.5,
                "nudge_side": 0.0,
                "damaged": ["Sensor fusion ECU", "Perception trust", "AEB decision", "Pedestrian/obstacle collision risk", "Missed obstacle impact"],
                "route": "attack_sensor_spoofing_human_obstacle_impact",
            },
            "gps_spoofing": {
                "control": (0.72 * intensity, 0.58 * intensity, 0.0),
                "target": ("wall", 15.0, 3.2),
                "seconds": 5.8,
                "speed": 7.5,
                "nudge_side": 0.0,
                "damaged": ["GNSS receiver", "Navigation stack", "Right-side body", "Wrong-route building/roadside impact"],
                "route": "attack_gps_spoofing_severe_wall_impact",
            },
            "can_bus_injection": {
                "control": (0.78 * intensity, 0.78 * intensity, 0.05),
                "target": ("vehicle", 14.5, 2.2),
                "seconds": 5.5,
                "speed": 7.5,
                "nudge_side": 0.0,
                "damaged": ["Gateway ECU", "CAN bus", "Steering ECU", "Brake/Throttle conflict", "Multi-vehicle loss-of-control collision"],
                "route": "attack_can_injection_multi_vehicle_collision",
            },
            "dos": {
                "control": (-0.68 * intensity, 0.52 * intensity, 0.0),
                "target": ("vehicle", 14.5, -2.2),
                "seconds": 5.8,
                "speed": 7.0,
                "nudge_side": 0.0,
                "damaged": ["Gateway availability", "Controller heartbeat", "Delayed brake/steering update", "Side collision from lost control"],
                "route": "attack_dos_availability_collision",
            },
            "lane_drift_attack": {
                "control": (0.42 * intensity, 0.50 * intensity, 0.0),
                "target": ("pedestrian", 16.0, 2.0),
                "seconds": 6.0,
                "speed": 6.5,
                "nudge_side": 0.0,
                "damaged": ["Lane keeping controller", "Steering bias monitor", "Side body", "Pedestrian/roadside collision risk", "Gradual lane-departure impact"],
                "route": "attack_lane_drift_human_roadside_impact",
            },
            "pedestrian_detection_attack": {
                "control": (0.0, 0.72 * intensity, 0.0),
                "target": ("pedestrian", 13.0, 0.0),
                "seconds": 5.5,
                "speed": 7.0,
                "nudge_side": 0.0,
                "damaged": ["Pedestrian perception", "Automatic emergency braking", "Human Safety Mode", "Critical pedestrian impact risk"],
                "route": "attack_pedestrian_detection_failure_critical",
            },
        }
        plan = plans.get(attack_name)
        if not plan:
            return [], {"active": False, "verified": False, "severity": "none", "target": "none", "message": "No attack impact configured."}, control, 0.0, 0.0, None, 0.0

        steer, throttle, brake = plan["control"]
        target_kind, forward_m, side_m = plan["target"]
        damaged = list(plan["damaged"])
        self._route_mode = str(plan["route"])

        actor, msg = self._spawn_impact_actor(attack_name, target_kind=target_kind, forward_m=float(forward_m), side_m=float(side_m), yaw_delta=180.0)
        impact["target"] = getattr(actor, "type_id", target_kind) if actor is not None else target_kind
        impact["message"] = msg
        impact["message"] += " · Stationary target mode: no target teleport/nudge is used; the ego vehicle must create the visible impact."
        impact["scene"].append({"role": "primary_target", "kind": target_kind, "actor": impact["target"], "forward_m": forward_m, "side_m": side_m})

        # Add a visible collateral actor so the demonstration clearly shows risk
        # to traffic participants, not only to the ego vehicle.
        collateral_kind = "vehicle" if target_kind == "pedestrian" else "pedestrian"
        collateral_actor, collateral_msg = self._spawn_impact_actor(attack_name, target_kind=collateral_kind, forward_m=float(forward_m) + 3.5, side_m=float(side_m) + (1.8 if float(side_m) >= 0 else -1.8), yaw_delta=180.0)
        if collateral_actor is not None:
            impact["scene"].append({"role": "collateral_visibility", "kind": collateral_kind, "actor": getattr(collateral_actor, "type_id", collateral_kind), "message": collateral_msg})

        control.steer = max(-1.0, min(1.0, float(steer)))
        control.throttle = max(0.0, min(1.0, float(throttle)))
        control.brake = max(0.0, min(1.0, float(brake)))
        control = self._realistic_control_from_plan(control, attack_name, intensity)
        return damaged, impact, control, float(plan["seconds"]), float(plan["speed"]), actor, float(plan["nudge_side"])

    def is_ready(self) -> bool:
        return bool(self.status.connected and self.vehicle is not None)

    def start_live_loop(self) -> CarlaStatus:
        if not self.is_ready():
            self.status.message = "Cannot start live loop before CARLA vehicle is ready."
            return self.status
        if self._live_thread and self._live_thread.is_alive():
            return self.status
        self._live_stop.clear()
        self._live_thread = threading.Thread(target=self._live_loop, daemon=True)
        self._live_thread.start()
        self.status.live_loop_running = True
        self.status.message = "CARLA live tick loop started."
        return self.status

    def stop_live_loop(self) -> CarlaStatus:
        self._live_stop.set()
        if self._live_thread and self._live_thread.is_alive():
            self._live_thread.join(timeout=1.0)
        self._live_thread = None
        self.status.live_loop_running = False
        return self.status

    def _live_loop(self) -> None:  # pragma: no cover - requires CARLA runtime
        while not self._live_stop.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.status.message = f"CARLA live loop error: {exc}"
            time.sleep(1.0 / max(1.0, self.fps))

    def tick(self) -> Dict[str, Any]:
        if not self.world:
            return {"ok": False, "message": "World not connected."}
        try:
            frame = self.world.tick() if self.status.synchronous_mode else self.world.wait_for_tick(timeout=2.0).frame
            self.status.last_tick = int(frame)
            self._focus_spectator(self.vehicle, instant=False)
            return {"ok": True, "frame": int(frame)}
        except Exception as exc:  # pragma: no cover - requires CARLA runtime
            self.status.message = f"CARLA tick failed: {exc}"
            return {"ok": False, "message": str(exc)}

    def read_vehicle_state(self, fallback: VehicleState) -> VehicleState:
        if not self.is_ready():
            return fallback
        try:
            transform = self.vehicle.get_transform()
            velocity = self.vehicle.get_velocity()
            control = self.vehicle.get_control()
            speed_ms = math.sqrt(velocity.x ** 2 + velocity.y ** 2 + velocity.z ** 2)
            updated = VehicleState(**fallback.to_dict())
            updated.speed_kmh = round(speed_ms * 3.6, 1)
            updated.steer = round(float(control.steer), 2)
            updated.throttle = round(float(control.throttle), 2)
            updated.brake = round(float(control.brake), 2)
            updated.autopilot_enabled = bool(getattr(self, "_zg_autopilot_enabled", False))
            updated.location_x = round(float(transform.location.x), 4)
            updated.location_y = round(float(transform.location.y), 4)
            updated.heading_deg = round(float(transform.rotation.yaw) % 360, 1)
            updated.location_label = self.status.map_name
            with self._lock:
                gnss = self.sensor_data.get("gnss")
                if gnss:
                    updated.location_x = round(float(gnss.get("lon", updated.location_x)), 6)
                    updated.location_y = round(float(gnss.get("lat", updated.location_y)), 6)
            return updated
        except Exception as exc:  # pragma: no cover - requires CARLA runtime
            self.status.message = f"CARLA read failed: {exc}"
            return fallback

    def apply_vehicle_state(self, vehicle_state: VehicleState) -> None:
        if not self.is_ready():
            return
        try:
            enabled = bool(vehicle_state.autopilot_enabled)
            self.vehicle.set_autopilot(enabled)
            self._zg_autopilot_enabled = enabled
        except Exception:
            pass

    def apply_attack_and_defense(self, vehicle_state: VehicleState, attack: AttackState, risk: RiskBundle) -> Dict[str, Any]:
        result = {
            "mode": "carla" if self.is_ready() else "mock",
            "attack_applied": False,
            "defense_applied": False,
            "applied_control": {"steer": vehicle_state.steer, "throttle": vehicle_state.throttle, "brake": vehicle_state.brake},
            "sensor_snapshot": self.sensor_snapshot(),
        }
        if not self.is_ready() or carla is None:
            return result
        try:
            control = self.vehicle.get_control()
            vectors = attack.active_vectors()
            if vectors:
                try:
                    self.vehicle.set_autopilot(False)
                    self._zg_autopilot_enabled = False
                except Exception:
                    pass
            else:
                self.enable_natural_drive()
            if not bool(getattr(self, "_zg_autopilot_enabled", False)) or vectors:
                control.steer = max(-1.0, min(1.0, float(vehicle_state.steer)))
                control.throttle = max(0.0, min(1.0, float(vehicle_state.throttle)))
                control.brake = max(0.0, min(1.0, float(vehicle_state.brake)))

            damaged = []
            for vector in vectors:
                vector = canonical_attack(vector)
                result["attack_applied"] = True
                intensity = max(0.0, min(1.0, float(attack.intensity)))
                if vector == "steering_manipulation":
                    damaged.append("Steering ECU / Lane control")
                    control.steer = max(-1.0, min(1.0, float(control.steer) + 0.65 * intensity))
                elif vector == "brake_override":
                    damaged.append("Brake ECU")
                    control.brake = max(float(control.brake), 0.85 * intensity)
                    control.throttle = 0.0
                elif vector == "acceleration_injection":
                    damaged.append("Powertrain ECU / Acceleration control")
                    control.throttle = max(float(control.throttle), 0.9 * intensity)
                    control.brake = 0.0
                elif vector in {"can_bus_injection", "dos"}:
                    damaged.append("Gateway ECU / CAN bus availability")
                    control.throttle = min(float(control.throttle), max(0.1, 0.45 - 0.2 * intensity))
                elif vector == "gps_spoofing":
                    damaged.append("GNSS / Navigation trust")
                elif vector == "sensor_spoofing":
                    damaged.append("Sensor fusion / Perception ECU")
                elif vector == "lane_drift_attack":
                    damaged.append("Lane keeping / steering bias")
                    control.steer = max(-1.0, min(1.0, float(control.steer) + 0.32 * intensity))
                    control.throttle = min(0.42, max(float(control.throttle), 0.25))
                elif vector == "pedestrian_detection_attack":
                    damaged.append("Pedestrian detection / AEB")
                    control.throttle = max(float(control.throttle), 0.45 * intensity)
                    control.brake = 0.0
                elif vector == "camera_lidar_blinding":
                    damaged.append("Camera-LiDAR perception")
                elif vector == "battery_thermal_tampering":
                    damaged.append("Battery management / Thermal sensors")
                elif vector == "telemetry_scraping":
                    damaged.append("Telematics privacy channel")
                elif vector == "mixed_attack":
                    damaged.append("Gateway + steering + perception chain")
                    control.steer = max(-1.0, min(1.0, float(control.steer) + 0.45 * intensity))
                    control.brake = max(float(control.brake), 0.50 * intensity)
                    control.throttle = min(float(control.throttle), 0.22)

            if risk.action in {"RESTRICT_AND_MONITOR", "ISOLATE_ATTACK_NODE"}:
                result["defense_applied"] = True
                control.steer = max(-0.28, min(0.28, float(control.steer)))
                control.throttle = min(float(control.throttle), 0.25)
                control.brake = max(float(control.brake), 0.12)
            elif risk.action == "EMERGENCY_SAFE_MODE":
                result["defense_applied"] = True
                control.steer = max(-0.10, min(0.10, float(control.steer)))
                control.throttle = 0.0
                control.brake = max(float(control.brake), 0.75)

            self.vehicle.apply_control(control)
            self._damaged_parts = sorted(set(damaged))
            self._last_attack_notice = ("Attack active: " + ", ".join(self._damaged_parts)) if self._damaged_parts else "No active attack."
            result["damaged_parts"] = self._damaged_parts
            result["diagnostic_notice"] = self._last_attack_notice
            result["applied_control"] = {"steer": round(float(control.steer), 2), "throttle": round(float(control.throttle), 2), "brake": round(float(control.brake), 2)}
            result["sensor_snapshot"] = self.sensor_snapshot()
            return result
        except Exception as exc:  # pragma: no cover - requires CARLA runtime
            self.status.message = f"CARLA control apply failed: {exc}"
            return result

    def apply_direct_attack(self, attack_name: str, intensity: float = 0.9) -> Dict[str, Any]:
        """Apply a selected Attacker Console action directly to the live CARLA vehicle.

        The attack succeeds only when a real CARLA vehicle actor is ready. Each attack
        now creates a physical impact setup in CARLA and waits for collision/lane
        sensors instead of reporting fake damage.
        """
        result = {
            "ok": False,
            "attack": attack_name,
            "message": "CARLA vehicle is not ready.",
            "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0},
            "damaged_parts": [],
            "impact": {"active": False, "verified": False, "severity": "none", "target": "none", "message": "No CARLA impact."},
        }
        if not self.is_ready() or carla is None:
            return result
        intensity = max(0.0, min(1.0, float(intensity or 0.9)))
        try:
            self._cleanup_impact_actors()
            try:
                self.vehicle.set_autopilot(False)
            except Exception:
                pass
            damaged, impact, control, seconds, target_speed_ms, primary_actor, nudge_side_m = self._configure_attack_impact(attack_name, intensity)
            if not damaged:
                self.enable_natural_drive()
                result.update({"ok": True, "message": "Natural drive restored.", "damaged_parts": [], "impact": impact})
                return result
            self.vehicle.apply_control(control)
            physics = self._tick_for_visible_impact(
                control,
                seconds=seconds or 5.0,
                target_speed_ms=target_speed_ms or 12.0,
                primary_actor=primary_actor,
                nudge_side_m=nudge_side_m,
                attack_name=attack_name,
            )
            impact["verified"] = bool(physics.get("verified"))
            if physics.get("collision"):
                impact["collision"] = physics.get("collision")
            impact["message"] = (impact.get("message") or "Impact configured") + " · Realistic physics mode: no velocity injection, no target teleport, smoothed controls. · " + physics.get("message", "CARLA physics advanced.")
            self._last_impact_report = dict(impact)
            self._damaged_parts = sorted(set(damaged))
            self._last_attack_notice = "CARLA physical attack applied: %s -> %s" % (attack_name.replace("_", " "), ", ".join(self._damaged_parts))
            if not impact.get("verified"):
                self._last_attack_notice += " · impact actor spawned; waiting for collision sensor verification."
            self._focus_spectator(self.vehicle, instant=False)
            result.update({
                "ok": True,
                "message": self._last_attack_notice,
                "applied_control": {"steer": round(float(control.steer), 2), "throttle": round(float(control.throttle), 2), "brake": round(float(control.brake), 2)},
                "damaged_parts": self._damaged_parts,
                "impact": impact,
                "sensor_snapshot": self.sensor_snapshot(),
            })
            return result
        except Exception as exc:
            self.status.message = f"Direct CARLA attack failed: {exc}"
            result["message"] = self.status.message
            return result

    def recover_vehicle(self) -> Dict[str, Any]:
        result = {"ok": False, "message": "CARLA vehicle is not ready.", "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}}
        if not self.is_ready() or carla is None:
            return result
        try:
            try:
                control = self.vehicle.get_control()
                control.steer = 0.0
                control.throttle = 0.18
                control.brake = 0.0
                self.vehicle.apply_control(control)
            except Exception:
                pass
            drive = self.enable_natural_drive(speed_percent=-12.0)
            self._route_mode = "recovered_natural_autopilot"
            self._damaged_parts = []
            self._cleanup_impact_actors()
            self._last_impact_report = {"active": False, "verified": False, "severity": "none", "target": "none", "message": "Recovered; attack impact actors removed."}
            self._last_attack_notice = "Recovery complete: autopilot restored, attack controls cleared."
            self._focus_spectator(self.vehicle, instant=False)
            result.update({"ok": True, "message": drive.get("message", self._last_attack_notice), "applied_control": {"steer": 0.0, "throttle": 0.18, "brake": 0.0}})
            self.status.message = result["message"]
            return result
        except Exception as exc:
            self.status.message = f"Recovery failed: {exc}"
            result["message"] = self.status.message
            return result

    def diagnostic_snapshot(self) -> Dict[str, Any]:
        return {
            "camera": "smooth_follow_enabled",
            "route_mode": self._route_mode,
            "damaged_parts": list(self._damaged_parts),
            "notice": self._last_attack_notice,
            "impact": getattr(self, "_last_impact_report", {"active": False, "verified": False, "severity": "none", "target": "none", "message": "No impact."}),
            "map_name": self.status.map_name,
            "vehicle_id": self.status.vehicle_id,
        }

    def sensor_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            data = dict(self.sensor_data)
        data["age_ms"] = round((time.time() - float(data.get("last_sensor_ts") or time.time())) * 1000.0, 1)
        return data

    def camera_status(self) -> Dict[str, Any]:
        frame = self.sensor_snapshot().get("camera_frame")
        return {"available": frame is not None, "frame": frame}

# ---------------------------------------------------------------------------
# DriveFort AI AI/Manual attacker-control extension
# ---------------------------------------------------------------------------
def _zg_manual_attacker_control(self, steer=0.0, throttle=0.0, brake=0.0, note="Manual attacker control"):
    """Simulate an attacker taking low-level control of steer/throttle/brake in CARLA.

    This is intentionally limited to the CARLA simulator and is used by the
    dashboard's Attacker Console to demonstrate what happens without protection.
    """
    result = {
        "ok": False,
        "message": "CARLA vehicle is not ready.",
        "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0},
        "damaged_parts": ["Remote control channel", "Steering/Brake command path"],
    }
    if not self.is_ready() or carla is None:
        return result
    try:
        steer = max(-1.0, min(1.0, float(steer or 0.0)))
        throttle = max(0.0, min(1.0, float(throttle or 0.0)))
        brake = max(0.0, min(1.0, float(brake or 0.0)))
        try:
            self.vehicle.set_autopilot(False)
        except Exception:
            pass
        control = self.vehicle.get_control()
        control.steer = steer
        control.throttle = throttle
        control.brake = brake
        self.vehicle.apply_control(control)
        self._route_mode = "attacker_manual_takeover"
        self._damaged_parts = ["Steering actuator", "Brake ECU", "Powertrain torque path", "Remote command channel"]
        self._last_attack_notice = f"{note}: steer={steer:.2f}, throttle={throttle:.2f}, brake={brake:.2f}"
        self._focus_spectator(self.vehicle, instant=False)
        result.update({
            "ok": True,
            "message": self._last_attack_notice,
            "applied_control": {"steer": round(steer, 2), "throttle": round(throttle, 2), "brake": round(brake, 2)},
            "damaged_parts": self._damaged_parts,
        })
        return result
    except Exception as exc:
        self.status.message = f"Manual attacker control failed: {exc}"
        result["message"] = self.status.message
        return result

try:
    CarlaBridge.apply_manual_attacker_control = _zg_manual_attacker_control
except NameError:
    pass


# ---------------------------------------------------------------------------
# DriveFort AI robust CARLA control hotfix
# ---------------------------------------------------------------------------
def _zg_force_respawn_and_drive(self):
    """Destroy stale ego actors, respawn a clean EV actor on a valid CARLA road spawn point, enable Traffic Manager autopilot, and start the live tick loop."""
    result = {"ok": False, "message": "CARLA is not connected.", "vehicle_id": None}
    if carla is None:
        result["message"] = self.status.message or "CARLA Python API is unavailable."
        return result
    try:
        if self.client is None or self.world is None:
            self.connect(host=self.host, port=self.port, spawn_if_missing=False, synchronous=True, fps=self.fps)
        if self.world is None:
            result["message"] = "CARLA world is not ready."
            return result
        # clean old sensors and stale ego vehicles only
        self._destroy_sensors()
        self._cleanup_impact_actors()
        actors = list(self.world.get_actors().filter("vehicle.*"))
        for a in actors:
            try:
                role = a.attributes.get("role_name", "") if hasattr(a, "attributes") else ""
                tid = getattr(a, "type_id", "")
                if role in {"zoneguard", "hero", "ego"} or "tesla.model3" in tid:
                    a.destroy()
            except Exception:
                pass
        try:
            self.tick()
        except Exception:
            pass
        self.vehicle = self._spawn_tesla_model3()
        if self.vehicle is None:
            result["message"] = self.status.message or "Vehicle respawn failed."
            return result
        try:
            self.enable_natural_drive(speed_percent=-8.0)
        except Exception:
            pass
        self._focus_spectator(self.vehicle, instant=True)
        self.start_live_loop()
        self.status.connected = True
        self.status.actor_found = True
        self.status.vehicle_id = int(self.vehicle.id)
        self.status.message = "Force respawn complete: clean EV actor spawned on road and normal drive enabled."
        return {"ok": True, "message": self.status.message, "vehicle_id": int(self.vehicle.id), "map_name": self.status.map_name}
    except Exception as exc:
        self.status.message = f"Force respawn failed: {exc}"
        result["message"] = self.status.message
        return result


def _zg_apply_manual_attacker_control_persistent(self, steer=0.0, throttle=0.0, brake=0.0, note="Manual attacker control"):
    """Apply direct attacker control and hold it for a few simulator ticks so the effect is visible in CARLA."""
    base = _zg_manual_attacker_control(self, steer, throttle, brake, note) if '_zg_manual_attacker_control' in globals() else {"ok": False, "message": "Manual function unavailable."}
    if not base.get("ok") or not self.is_ready() or carla is None:
        return base
    try:
        control = self.vehicle.get_control()
        control.steer = max(-1.0, min(1.0, float(steer or 0.0)))
        control.throttle = max(0.0, min(1.0, float(throttle or 0.0)))
        control.brake = max(0.0, min(1.0, float(brake or 0.0)))
        for _ in range(8):
            try:
                self.vehicle.set_autopilot(False)
                self.vehicle.apply_control(control)
                if self.status.synchronous_mode and self.world is not None:
                    self.world.tick()
                else:
                    break
            except Exception:
                break
        self._focus_spectator(self.vehicle, instant=False)
        base["message"] = (base.get("message") or "Manual control applied") + " · held for visible CARLA response."
        base["applied_control"] = {"steer": round(float(control.steer),2), "throttle": round(float(control.throttle),2), "brake": round(float(control.brake),2)}
    except Exception as exc:
        base["message"] = f"Manual control hold failed: {exc}"
    return base

try:
    CarlaBridge.force_respawn_and_drive = _zg_force_respawn_and_drive
    CarlaBridge.apply_manual_attacker_control = _zg_apply_manual_attacker_control_persistent
except NameError:
    pass

# ---------------------------------------------------------------------------
# DriveFort AI direct live-attack hold fix
# ---------------------------------------------------------------------------
# Problem addressed: the dashboard snapshot loop can immediately re-apply the
# normal defense/telemetry control after a direct Attacker Console action.  That
# makes attacks such as Acceleration Injection show only a target spawn while the
# ego vehicle returns to a low throttle.  This fix keeps the ego vehicle under
# the selected attack command for a short visible demo window.  Targets remain
# stationary; only the ego vehicle receives motion/attack commands.
try:
    _ZG_ORIGINAL_DIRECT_ATTACK_FOR_HOLD = CarlaBridge.apply_direct_attack
    _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD = CarlaBridge.apply_attack_and_defense
except NameError:
    _ZG_ORIGINAL_DIRECT_ATTACK_FOR_HOLD = None
    _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD = None


def _zg_set_clean_control_fields(control):
    try:
        control.hand_brake = False
    except Exception:
        pass
    try:
        control.manual_gear_shift = False
    except Exception:
        pass
    try:
        control.reverse = False
    except Exception:
        pass
    try:
        if getattr(control, 'gear', 0) <= 0:
            control.gear = 1
    except Exception:
        pass
    return control


def _zg_direct_attack_with_hold(self, attack_name: str, intensity: float = 0.9):
    result = _ZG_ORIGINAL_DIRECT_ATTACK_FOR_HOLD(self, attack_name, intensity) if _ZG_ORIGINAL_DIRECT_ATTACK_FOR_HOLD else {"ok": False, "message": "Direct attack function unavailable."}
    try:
        ctrl = (result or {}).get("applied_control") or {}
        if (result or {}).get("ok") and self.is_ready():
            # Hold longer for acceleration/brake/pedestrian scenarios so the
            # visual effect is unmistakable in CARLA and not immediately clipped
            # by the dashboard refresh loop.
            canon = canonical_attack(attack_name) if 'canonical_attack' in globals() else str(attack_name)
            hold_seconds = {
                "acceleration_injection": 10.0,
                "brake_override": 8.0,
                "pedestrian_detection_attack": 8.0,
                "lane_drift_attack": 9.0,
                "steering_manipulation": 8.0,
                "sensor_spoofing": 8.0,
                "gps_spoofing": 8.0,
                "can_bus_injection": 8.0,
                "dos": 8.0,
            }.get(canon, 7.0)
            speed_ms = {
                "acceleration_injection": 24.0,
                "brake_override": 15.0,
                "pedestrian_detection_attack": 13.0,
                "lane_drift_attack": 11.0,
                "steering_manipulation": 14.0,
                "sensor_spoofing": 13.0,
                "gps_spoofing": 13.0,
                "can_bus_injection": 14.0,
                "dos": 12.0,
            }.get(canon, 12.0)
            self._direct_attack_hold_until = time.time() + hold_seconds
            self._direct_attack_hold_control = {
                "steer": float(ctrl.get("steer", 0.0) or 0.0),
                "throttle": float(ctrl.get("throttle", 0.0) or 0.0),
                "brake": float(ctrl.get("brake", 0.0) or 0.0),
            }
            self._direct_attack_hold_speed_ms = float(speed_ms)
            self._direct_attack_hold_name = canon
            # For acceleration injection, guarantee the held command is visibly
            # full throttle.  This affects only the CARLA simulator demo.
            if canon == "acceleration_injection":
                self._direct_attack_hold_control.update({"steer": 0.0, "throttle": 1.0, "brake": 0.0})
                result["applied_control"] = {"steer": 0.0, "throttle": 1.0, "brake": 0.0}
                result["message"] = (result.get("message") or "") + " · ego-vehicle full-throttle hold active; target remains stationary."
    except Exception as exc:
        try:
            result["message"] = (result.get("message") or "Direct attack applied") + f" · hold setup warning: {exc}"
        except Exception:
            pass
    return result


def _zg_attack_and_defense_respects_direct_hold(self, vehicle_state, attack, risk):
    try:
        hold_until = float(getattr(self, "_direct_attack_hold_until", 0.0) or 0.0)
        hold_ctrl = dict(getattr(self, "_direct_attack_hold_control", {}) or {})
        if self.is_ready() and carla is not None and time.time() < hold_until and hold_ctrl:
            control = self.vehicle.get_control()
            control.steer = max(-1.0, min(1.0, float(hold_ctrl.get("steer", 0.0))))
            control.throttle = max(0.0, min(1.0, float(hold_ctrl.get("throttle", 0.0))))
            control.brake = max(0.0, min(1.0, float(hold_ctrl.get("brake", 0.0))))
            control = _zg_set_clean_control_fields(control)
            try:
                self.vehicle.set_autopilot(False)
            except Exception:
                pass
            self.vehicle.apply_control(control)
            if float(control.brake) < 0.35:
                self._apply_forward_velocity(float(getattr(self, "_direct_attack_hold_speed_ms", 12.0) or 12.0))
            self._focus_spectator(self.vehicle, instant=False)
            self._last_attack_notice = "Direct dashboard attack hold active: ego vehicle is executing %s; target stays stationary." % str(getattr(self, "_direct_attack_hold_name", "attack")).replace("_", " ")
            return {
                "mode": "carla",
                "attack_applied": True,
                "defense_applied": False,
                "direct_hold_active": True,
                "applied_control": {"steer": round(float(control.steer), 2), "throttle": round(float(control.throttle), 2), "brake": round(float(control.brake), 2)},
                "damaged_parts": list(getattr(self, "_damaged_parts", []) or []),
                "impact": getattr(self, "_last_impact_report", {"active": True, "verified": False, "severity": "critical", "target": "stationary", "message": "Direct attack hold active."}),
                "diagnostic_notice": self._last_attack_notice,
                "sensor_snapshot": self.sensor_snapshot(),
            }
    except Exception:
        pass
    return _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD(self, vehicle_state, attack, risk) if _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD else {"mode": "carla", "attack_applied": False, "defense_applied": False, "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}}

try:
    if _ZG_ORIGINAL_DIRECT_ATTACK_FOR_HOLD is not None:
        CarlaBridge.apply_direct_attack = _zg_direct_attack_with_hold
    if _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD is not None:
        CarlaBridge.apply_attack_and_defense = _zg_attack_and_defense_respects_direct_hold
except NameError:
    pass

# ---------------------------------------------------------------------------
# DriveFort AI launch-from-standstill fix
# ---------------------------------------------------------------------------
# CARLA vehicles can sometimes remain visually stationary after a dashboard
# attack when they were spawned at 0 km/h, still had a previous hand-brake/gear
# state, or the telemetry loop reapplied a low-speed command.  This patch makes
# Acceleration Injection, Brake Override and pedestrian/front-impact scenarios
# start from a true ego-vehicle launch: the ego vehicle receives full attacker
# throttle, a forward target velocity, and a short physical impulse if the CARLA
# API supports it.  Stationary targets remain stationary; no target teleport or
# nudge is used.
try:
    _ZG_ORIGINAL_APPLY_FORWARD_VELOCITY_LAUNCH = CarlaBridge._apply_forward_velocity
    _ZG_ORIGINAL_TICK_VISIBLE_IMPACT_LAUNCH = CarlaBridge._tick_for_visible_impact
    _ZG_ORIGINAL_ATTACK_AND_DEFENSE_LAUNCH = CarlaBridge.apply_attack_and_defense
except NameError:
    _ZG_ORIGINAL_APPLY_FORWARD_VELOCITY_LAUNCH = None
    _ZG_ORIGINAL_TICK_VISIBLE_IMPACT_LAUNCH = None
    _ZG_ORIGINAL_ATTACK_AND_DEFENSE_LAUNCH = None


def _zg_prepare_vehicle_for_attacker_launch(self, control=None):
    """Clear states that can keep the ego vehicle stopped in CARLA."""
    if not self.is_ready() or carla is None:
        return None
    try:
        self.vehicle.set_autopilot(False)
    except Exception:
        pass
    try:
        self.vehicle.set_simulate_physics(True)
    except Exception:
        pass
    try:
        self.vehicle.set_target_angular_velocity(carla.Vector3D(0.0, 0.0, 0.0))
    except Exception:
        pass
    try:
        if control is None:
            control = self.vehicle.get_control()
        control.hand_brake = False
    except Exception:
        pass
    try:
        control.reverse = False
    except Exception:
        pass
    try:
        control.manual_gear_shift = False
    except Exception:
        pass
    try:
        if int(getattr(control, "gear", 0) or 0) <= 0:
            control.gear = 1
    except Exception:
        pass
    return control


def _zg_apply_forward_velocity_launch(self, speed_ms: float) -> None:
    """Force visible ego-vehicle forward motion without moving any target actor."""
    if not self.is_ready() or carla is None:
        return
    try:
        speed_ms = max(8.0, float(speed_ms or 18.0))
    except Exception:
        speed_ms = 18.0
    try:
        self._zg_prepare_vehicle_for_attacker_launch()
    except Exception:
        pass
    try:
        tr = self.vehicle.get_transform()
        yaw = math.radians(float(tr.rotation.yaw))
        v = carla.Vector3D(x=float(speed_ms) * math.cos(yaw), y=float(speed_ms) * math.sin(yaw), z=0.0)
        self.vehicle.set_target_velocity(v)
        # Some CARLA builds expose add_impulse.  If available, use a small
        # forward impulse so a vehicle starting from complete rest visibly moves
        # immediately.  This is applied only to the ego vehicle.
        try:
            self.vehicle.add_impulse(carla.Vector3D(x=float(speed_ms) * 80.0 * math.cos(yaw), y=float(speed_ms) * 80.0 * math.sin(yaw), z=0.0))
        except Exception:
            pass
    except Exception:
        try:
            if _ZG_ORIGINAL_APPLY_FORWARD_VELOCITY_LAUNCH:
                _ZG_ORIGINAL_APPLY_FORWARD_VELOCITY_LAUNCH(self, speed_ms)
        except Exception:
            pass


def _zg_tick_for_visible_impact_launch(self, control, seconds: float = 4.8, target_speed_ms: float = 12.0, primary_actor=None, nudge_side_m: float = 0.0, attack_name: str = ""):
    if not self.is_ready() or carla is None:
        return {"verified": False, "message": "CARLA vehicle is not ready."}
    canon = canonical_attack(attack_name) if 'canonical_attack' in globals() else str(attack_name or "")
    try:
        target_speed_ms = float(target_speed_ms or 12.0)
    except Exception:
        target_speed_ms = 12.0
    if canon == "acceleration_injection":
        # Strong launch from stop: full throttle and enough target velocity for a
        # visible forward acceleration in the dashboard demo.
        target_speed_ms = max(target_speed_ms, 28.0)
        try:
            control.steer = 0.0
            control.throttle = 1.0
            control.brake = 0.0
        except Exception:
            pass
    try:
        control = self._zg_prepare_vehicle_for_attacker_launch(control) or control
    except Exception:
        pass
    ticks = max(30, int(float(seconds) * max(10.0, float(self.fps or 20.0))))
    collision_before = self.sensor_snapshot().get("collision")
    last_collision = collision_before
    for i in range(ticks):
        try:
            self.vehicle.set_autopilot(False)
            # In the first second, repeatedly clear brake/handbrake and force the
            # launch so a stopped car starts moving immediately.
            if canon == "acceleration_injection" or i < max(10, int(max(10.0, float(self.fps or 20.0)))):
                control = self._zg_prepare_vehicle_for_attacker_launch(control) or control
            self.vehicle.apply_control(control)
            if float(getattr(control, "brake", 0.0)) < 0.35:
                self._apply_forward_velocity(target_speed_ms)
            self._focus_spectator(self.vehicle, instant=False)
            if self.status.synchronous_mode and self.world is not None:
                self.world.tick()
            else:
                time.sleep(1.0 / max(10.0, float(self.fps or 20.0)))
            last_collision = self.sensor_snapshot().get("collision")
            if last_collision and last_collision != collision_before:
                break
        except Exception:
            break
    collision_after = self.sensor_snapshot().get("collision")
    verified = bool(collision_after and collision_after != collision_before)
    if verified:
        severity = collision_after.get("severity") or self._impact_severity_from_impulse(collision_after.get("intensity", 0.0))
        return {"verified": True, "message": "CARLA collision sensor verified a %s physical impact caused by ego-vehicle motion after launch boost." % severity, "collision": collision_after}
    return {"verified": False, "message": "Stationary targets remained fixed; ego-vehicle launch/attack controls were applied from standstill, but CARLA collision sensor has not confirmed contact yet.", "collision": collision_after or last_collision}


def _zg_attack_and_defense_respects_direct_hold_launch(self, vehicle_state, attack, risk):
    try:
        hold_until = float(getattr(self, "_direct_attack_hold_until", 0.0) or 0.0)
        hold_ctrl = dict(getattr(self, "_direct_attack_hold_control", {}) or {})
        if self.is_ready() and carla is not None and time.time() < hold_until and hold_ctrl:
            control = self.vehicle.get_control()
            control.steer = max(-1.0, min(1.0, float(hold_ctrl.get("steer", 0.0))))
            control.throttle = max(0.0, min(1.0, float(hold_ctrl.get("throttle", 0.0))))
            control.brake = max(0.0, min(1.0, float(hold_ctrl.get("brake", 0.0))))
            control = self._zg_prepare_vehicle_for_attacker_launch(control) or control
            self.vehicle.apply_control(control)
            if float(control.brake) < 0.35:
                speed = float(getattr(self, "_direct_attack_hold_speed_ms", 12.0) or 12.0)
                if str(getattr(self, "_direct_attack_hold_name", "")) == "acceleration_injection":
                    speed = max(speed, 28.0)
                self._apply_forward_velocity(speed)
            self._focus_spectator(self.vehicle, instant=False)
            self._last_attack_notice = "Direct dashboard attack hold active: ego vehicle is executing %s from standstill if needed; target stays stationary." % str(getattr(self, "_direct_attack_hold_name", "attack")).replace("_", " ")
            return {
                "mode": "carla",
                "attack_applied": True,
                "defense_applied": False,
                "direct_hold_active": True,
                "launch_boost_active": str(getattr(self, "_direct_attack_hold_name", "")) == "acceleration_injection",
                "applied_control": {"steer": round(float(control.steer), 2), "throttle": round(float(control.throttle), 2), "brake": round(float(control.brake), 2)},
                "damaged_parts": list(getattr(self, "_damaged_parts", []) or []),
                "impact": getattr(self, "_last_impact_report", {"active": True, "verified": False, "severity": "critical", "target": "stationary", "message": "Direct attack hold active."}),
                "diagnostic_notice": self._last_attack_notice,
                "sensor_snapshot": self.sensor_snapshot(),
            }
    except Exception:
        pass
    if _ZG_ORIGINAL_ATTACK_AND_DEFENSE_LAUNCH:
        return _ZG_ORIGINAL_ATTACK_AND_DEFENSE_LAUNCH(self, vehicle_state, attack, risk)
    if _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD:
        return _ZG_ORIGINAL_ATTACK_AND_DEFENSE_FOR_HOLD(self, vehicle_state, attack, risk)
    return {"mode": "carla", "attack_applied": False, "defense_applied": False, "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}}

try:
    if _ZG_ORIGINAL_APPLY_FORWARD_VELOCITY_LAUNCH is not None:
        CarlaBridge._zg_prepare_vehicle_for_attacker_launch = _zg_prepare_vehicle_for_attacker_launch
        CarlaBridge._apply_forward_velocity = _zg_apply_forward_velocity_launch
        CarlaBridge._tick_for_visible_impact = _zg_tick_for_visible_impact_launch
    if _ZG_ORIGINAL_ATTACK_AND_DEFENSE_LAUNCH is not None:
        CarlaBridge.apply_attack_and_defense = _zg_attack_and_defense_respects_direct_hold_launch
except NameError:
    pass

# ---------------------------------------------------------------------------
# Dashboard Control Reliability Patch
# ---------------------------------------------------------------------------
# Purpose:
#   Make the dashboard sliders and attack intensity visibly affect the live
#   CARLA vehicle.  Earlier layers could disable autopilot and apply one command
#   only once; CARLA's Traffic Manager, previous brake state, or DriveFort AI
#   protection wrappers could immediately override it.  These helpers apply
#   bounded VehicleControl commands repeatedly for a short hold window while
#   advancing CARLA ticks.  They still avoid set_target_velocity and target
#   teleporting, so the motion remains realistic.


def _zg_dash_clamp(value, low, high, default=0.0):
    try:
        number = float(value)
    except Exception:
        number = float(default)
    return max(float(low), min(float(high), number))


def _zg_dash_tick(self, delay=None):
    try:
        if self.status.synchronous_mode and self.world is not None:
            self.world.tick()
        else:
            time.sleep(float(delay if delay is not None else 1.0 / max(8.0, float(self.fps or 20.0))))
    except Exception:
        time.sleep(0.04)


def _zg_dash_apply_control_hold(self, steer=0.0, throttle=0.0, brake=0.0, seconds=1.8, ramp=True):
    """Apply a normal CARLA VehicleControl command long enough to be visible."""
    result = {
        "ok": False,
        "message": "CARLA vehicle is not ready.",
        "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0},
    }
    if not self.is_ready() or carla is None:
        return result
    steer = _zg_dash_clamp(steer, -1.0, 1.0)
    throttle = _zg_dash_clamp(throttle, 0.0, 1.0)
    brake = _zg_dash_clamp(brake, 0.0, 1.0)
    seconds = _zg_dash_clamp(seconds, 0.15, 6.0, 1.8)
    try:
        self.vehicle.set_autopilot(False)
    except Exception:
        pass
    try:
        start = self.vehicle.get_control()
    except Exception:
        start = carla.VehicleControl()
    ticks = max(4, int(seconds * max(8.0, float(self.fps or 20.0))))
    last = None
    for idx in range(ticks):
        alpha = 1.0
        if ramp:
            alpha = min(1.0, (idx + 1) / max(1.0, min(float(self.fps or 20.0), ticks)))
        control = carla.VehicleControl()
        control.steer = float(getattr(start, "steer", 0.0)) + (steer - float(getattr(start, "steer", 0.0))) * alpha
        control.throttle = float(getattr(start, "throttle", 0.0)) + (throttle - float(getattr(start, "throttle", 0.0))) * alpha
        control.brake = float(getattr(start, "brake", 0.0)) + (brake - float(getattr(start, "brake", 0.0))) * alpha
        control.steer = _zg_dash_clamp(control.steer, -1.0, 1.0)
        control.throttle = _zg_dash_clamp(control.throttle, 0.0, 1.0)
        control.brake = _zg_dash_clamp(control.brake, 0.0, 1.0)
        control.hand_brake = False
        control.reverse = False
        control.manual_gear_shift = False
        try:
            self.vehicle.apply_control(control)
            last = control
        except Exception as exc:
            result["message"] = f"CARLA apply_control failed: {exc}"
            return result
        _zg_dash_tick(self)
    if last is None:
        last = carla.VehicleControl(steer=steer, throttle=throttle, brake=brake)
    self._route_mode = "dashboard_direct_control"
    self._last_attack_notice = f"Dashboard control applied: steer={float(last.steer):.2f}, throttle={float(last.throttle):.2f}, brake={float(last.brake):.2f}"
    try:
        self._focus_spectator(self.vehicle, instant=False)
    except Exception:
        pass
    result.update({
        "ok": True,
        "message": self._last_attack_notice,
        "applied_control": {"steer": round(float(last.steer), 2), "throttle": round(float(last.throttle), 2), "brake": round(float(last.brake), 2)},
        "sensor_snapshot": self.sensor_snapshot(),
    })
    return result


def _zg_dash_attack_control_plan(attack_name, intensity):
    attack_name = canonical_attack(attack_name)
    i = _zg_dash_clamp(intensity, 0.0, 1.0, 0.9)
    # Bounded values: visible in CARLA but not acrobatic.
    if attack_name == "steering_manipulation":
        return {"steer": 0.12 + 0.28 * i, "throttle": 0.18 + 0.24 * i, "brake": 0.0, "seconds": 2.8 + 2.2 * i, "damaged": ["Steering ECU", "Lane keeping controller"]}
    if attack_name == "brake_override":
        # Brake override means requested braking is suppressed; vehicle continues rolling under throttle.
        return {"steer": 0.0, "throttle": 0.22 + 0.26 * i, "brake": 0.0, "seconds": 2.4 + 2.0 * i, "damaged": ["Brake ECU", "AEB command path"]}
    if attack_name == "acceleration_injection":
        return {"steer": 0.0, "throttle": 0.28 + 0.42 * i, "brake": 0.0, "seconds": 2.5 + 2.6 * i, "damaged": ["Powertrain ECU", "Throttle command path"]}
    if attack_name == "sensor_spoofing":
        return {"steer": -0.08 - 0.18 * i, "throttle": 0.18 + 0.25 * i, "brake": 0.0, "seconds": 2.5 + 2.0 * i, "damaged": ["Perception ECU", "Sensor fusion trust"]}
    if attack_name == "gps_spoofing":
        return {"steer": 0.10 + 0.20 * i, "throttle": 0.16 + 0.22 * i, "brake": 0.0, "seconds": 2.8 + 2.2 * i, "damaged": ["GNSS", "Navigation trust"]}
    if attack_name == "can_bus_injection":
        return {"steer": 0.08 + 0.18 * i, "throttle": 0.22 + 0.24 * i, "brake": 0.05 * i, "seconds": 2.4 + 2.0 * i, "damaged": ["Gateway ECU", "CAN command arbitration"]}
    if attack_name == "dos":
        return {"steer": -0.06 - 0.16 * i, "throttle": 0.15 + 0.18 * i, "brake": 0.0, "seconds": 2.8 + 2.0 * i, "damaged": ["Gateway availability", "Controller heartbeat"]}
    if attack_name == "lane_drift_attack":
        return {"steer": 0.06 + 0.14 * i, "throttle": 0.18 + 0.20 * i, "brake": 0.0, "seconds": 3.2 + 2.5 * i, "damaged": ["Lane keeping controller", "Steering bias monitor"]}
    if attack_name == "pedestrian_detection_attack":
        return {"steer": 0.0, "throttle": 0.20 + 0.24 * i, "brake": 0.0, "seconds": 2.8 + 2.4 * i, "damaged": ["Pedestrian perception", "AEB decision layer"]}
    return {"steer": 0.10 + 0.20 * i, "throttle": 0.20 + 0.24 * i, "brake": 0.0, "seconds": 3.5, "damaged": ["Gateway", "Mixed control path"]}


def _zg_dash_apply_direct_attack(self, attack_name: str, intensity: float = 0.9) -> Dict[str, Any]:
    """Dashboard-friendly direct attack path with reliable intensity response."""
    result = {
        "ok": False,
        "attack": attack_name,
        "message": "CARLA vehicle is not ready.",
        "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0},
        "damaged_parts": [],
        "impact": {"active": False, "verified": False, "severity": "none", "target": "none", "message": "No CARLA impact."},
    }
    if not self.is_ready() or carla is None:
        return result
    attack_name = canonical_attack(attack_name)
    intensity = _zg_dash_clamp(intensity, 0.0, 1.0, 0.9)
    try:
        self._cleanup_impact_actors()
    except Exception:
        pass
    try:
        # Optional visual target only. It stays stationary; no target teleporting during the hold.
        target_map = {
            "acceleration_injection": ("vehicle", 24.0, 0.0),
            "brake_override": ("vehicle", 20.0, 0.0),
            "pedestrian_detection_attack": ("pedestrian", 18.0, 0.0),
            "steering_manipulation": ("wall", 18.0, 3.2),
            "lane_drift_attack": ("pedestrian", 20.0, 2.1),
            "gps_spoofing": ("wall", 20.0, 3.0),
            "sensor_spoofing": ("pedestrian", 20.0, -1.2),
            "can_bus_injection": ("vehicle", 20.0, 2.2),
            "dos": ("vehicle", 20.0, -2.2),
        }
        target_kind, fwd, side = target_map.get(attack_name, ("vehicle", 22.0, 0.0))
        actor, msg = self._spawn_impact_actor(attack_name, target_kind=target_kind, forward_m=fwd, side_m=side, yaw_delta=180.0)
    except Exception as exc:
        actor, msg = None, f"No visual target spawned: {exc}"
    plan = _zg_dash_attack_control_plan(attack_name, intensity)
    before = self.sensor_snapshot().get("collision")
    applied = _zg_dash_apply_control_hold(self, plan["steer"], plan["throttle"], plan["brake"], seconds=plan["seconds"], ramp=True)
    after = self.sensor_snapshot().get("collision")
    verified = bool(after and after != before)
    impact = {
        "active": True,
        "verified": verified,
        "severity": "critical" if verified else "pending",
        "target": getattr(actor, "type_id", target_kind) if actor is not None else target_kind,
        "message": msg + " · Dashboard intensity was translated to bounded VehicleControl and held for visible CARLA response.",
    }
    if verified:
        impact["collision"] = after
    self._damaged_parts = sorted(set(plan["damaged"]))
    self._last_impact_report = dict(impact)
    self._last_attack_notice = f"CARLA dashboard attack applied: {attack_name} intensity={intensity:.2f}. {applied.get('message', '')}"
    result.update({
        "ok": bool(applied.get("ok")),
        "message": self._last_attack_notice,
        "applied_control": applied.get("applied_control", {}),
        "damaged_parts": self._damaged_parts,
        "impact": impact,
        "sensor_snapshot": self.sensor_snapshot(),
    })
    return result


def _zg_dash_manual_attacker_control(self, steer=0.0, throttle=0.0, brake=0.0, note="Dashboard manual attacker control"):
    steer = _zg_dash_clamp(steer, -1.0, 1.0, 0.0)
    throttle = _zg_dash_clamp(throttle, 0.0, 1.0, 0.0)
    brake = _zg_dash_clamp(brake, 0.0, 1.0, 0.0)
    # Manual dashboard action should be immediately visible, but still ramped.
    applied = _zg_dash_apply_control_hold(self, steer, throttle, brake, seconds=1.6, ramp=True)
    if not applied.get("ok"):
        return {"ok": False, "message": applied.get("message", "Manual control failed."), "applied_control": {"steer": steer, "throttle": throttle, "brake": brake}, "damaged_parts": []}
    self._route_mode = "dashboard_manual_takeover"
    self._damaged_parts = ["Remote command channel", "Steering/Brake/Throttle control path"]
    self._last_attack_notice = f"{note}: steer={steer:.2f}, throttle={throttle:.2f}, brake={brake:.2f}"
    applied.update({"damaged_parts": self._damaged_parts, "message": self._last_attack_notice})
    return applied

try:
    CarlaBridge.apply_dashboard_control_hold = _zg_dash_apply_control_hold
    CarlaBridge.apply_direct_attack = _zg_dash_apply_direct_attack
    CarlaBridge.apply_manual_attacker_control = _zg_dash_manual_attacker_control
except NameError:
    pass

# ---------------------------------------------------------------------------
# Final live-CARLA reliability layer: persistent execution for all nine
# adopted academic attack scenarios.
# ---------------------------------------------------------------------------
# This layer intentionally keeps every effect inside the CARLA simulator.  It
# does not access real CAN hardware, ECUs, GNSS transmitters, or vehicles.
from .attack_catalog import ADOPTED_ATTACK_ORDER as _ZG_NINE_ATTACKS


def _zg_live_clamp(value, low, high, default=0.0):
    try:
        value = float(value)
    except Exception:
        value = default
    return max(low, min(high, value))


def _zg_live_attack_plan(attack_name, intensity, elapsed_s=0.0, tick_index=0):
    """Return a distinct, bounded CARLA VehicleControl plan per adopted scenario.

    The values are deliberately moderate: they make the attack visibly active
    in CARLA while avoiding unstable/acrobatics-style behaviour.
    """
    attack = canonical_attack(attack_name)
    i = _zg_live_clamp(intensity, 0.0, 1.0, 0.90)
    phase = 1.0 if (tick_index // 8) % 2 == 0 else -1.0
    drift = min(1.0, max(0.0, elapsed_s / 8.0))
    base = {
        "steer": 0.0,
        "throttle": 0.30,
        "brake": 0.0,
        "lane_status": "centered",
        "overlay": {},
        "damaged": [],
        "message": "No adopted live-CARLA attack plan selected.",
    }
    if attack == "steering_manipulation":
        base.update({"steer": 0.18 + 0.42 * i, "throttle": 0.28 + 0.14 * i,
                     "lane_status": "drifting_right", "damaged": ["Steering ECU", "Lane keeping control"],
                     "message": "Persistent steering bias is applied to the CARLA ego vehicle."})
    elif attack == "brake_override":
        # Represents brake-command suppression: throttle remains applied while
        # brake is forced to zero in the simulation control path.
        base.update({"steer": 0.0, "throttle": 0.42 + 0.22 * i, "brake": 0.0,
                     "damaged": ["Brake ECU", "AEB command path"],
                     "message": "Brake suppression profile keeps forward drive active in CARLA."})
    elif attack == "acceleration_injection":
        base.update({"steer": 0.0, "throttle": 0.62 + 0.30 * i, "brake": 0.0,
                     "damaged": ["Powertrain ECU", "Throttle command path"],
                     "message": "Injected throttle profile is applied persistently in CARLA."})
    elif attack == "sensor_spoofing":
        base.update({"steer": -(0.10 + 0.24 * i), "throttle": 0.28 + 0.13 * i,
                     "lane_status": "drifting_left", "overlay": {"perception_override": "spoofed", "obstacle_confidence": 0.15},
                     "damaged": ["Perception ECU", "Sensor fusion trust"],
                     "message": "Perception evidence is marked spoofed while a bounded lateral bias is applied."})
    elif attack == "gps_spoofing":
        base.update({"steer": 0.10 + 0.24 * i, "throttle": 0.27 + 0.12 * i,
                     "lane_status": "drifting_right", "overlay": {"gps_override": "route_divergence", "gps_offset_m": round(8 + 16 * i, 1)},
                     "damaged": ["GNSS", "Navigation trust"],
                     "message": "Localization route-divergence overlay and bounded steering bias are active."})
    elif attack == "can_bus_injection":
        base.update({"steer": phase * (0.12 + 0.20 * i), "throttle": 0.35 + 0.18 * i,
                     "brake": 0.05 + 0.10 * i, "lane_status": "control_conflict",
                     "overlay": {"command_conflict": True, "can_like_rate": round(45 + 75 * i, 1)},
                     "damaged": ["Gateway ECU", "CAN-like command path"],
                     "message": "Conflicting bounded steering/throttle/brake commands are active."})
    elif attack == "dos":
        # A DoS scenario is represented by degraded command availability and a
        # held stale command; it is not physical CAN flooding.
        base.update({"steer": -(0.08 + 0.18 * i), "throttle": 0.20 + 0.12 * i,
                     "brake": 0.0, "lane_status": "control_update_degraded",
                     "overlay": {"availability": "degraded", "simulated_drop_rate": round(0.20 + 0.45 * i, 2)},
                     "damaged": ["Gateway availability", "Controller heartbeat"],
                     "message": "Simulated delayed/stale control-update behaviour is active."})
    elif attack == "lane_drift_attack":
        base.update({"steer": 0.05 + (0.10 + 0.28 * i) * drift, "throttle": 0.28 + 0.10 * i,
                     "lane_status": "drifting_right", "overlay": {"drift_progress": round(drift, 2)},
                     "damaged": ["Lane keeping controller", "Steering bias monitor"],
                     "message": "A gradual persistent steering bias produces visible lane drift."})
    elif attack == "pedestrian_detection_attack":
        base.update({"steer": 0.0, "throttle": 0.36 + 0.18 * i, "brake": 0.0,
                     "overlay": {"pedestrian_perception": "suppressed", "aeb_state": "inhibited"},
                     "damaged": ["Pedestrian perception", "AEB decision layer"],
                     "message": "Pedestrian-perception suppression profile keeps the simulated drive command active."})
    return base


def _zg_live_spawn_attack_marker(self, attack_name):
    """Spawn only a visible simulator marker where it helps the demo.

    Markers are optional evidence aids and never used as a claim of real-world
    collision or hardware attack execution.
    """
    if not self.is_ready() or carla is None:
        return None, "No CARLA marker: vehicle is not ready."
    marker_map = {
        "pedestrian_detection_attack": ("pedestrian", 32.0, 0.0),
        "sensor_spoofing": ("pedestrian", 30.0, -2.0),
        "lane_drift_attack": ("wall", 28.0, 4.5),
        "gps_spoofing": ("wall", 30.0, 4.5),
        "brake_override": ("vehicle", 35.0, 0.0),
        "acceleration_injection": ("vehicle", 40.0, 0.0),
    }
    if attack_name not in marker_map:
        return None, "No marker required for this scenario."
    kind, forward_m, side_m = marker_map[attack_name]
    try:
        return self._spawn_impact_actor(attack_name, target_kind=kind, forward_m=forward_m, side_m=side_m, yaw_delta=180.0)
    except Exception as exc:
        return None, f"Marker spawn skipped: {exc}"


def _zg_live_start_attack_scenario(self, attack_name: str, intensity: float = 0.90, duration_sec: float = 0.0):
    attack = canonical_attack(attack_name)
    if attack not in _ZG_NINE_ATTACKS:
        return {"ok": False, "attack": attack, "message": f"Unsupported adopted attack: {attack}"}
    if not self.is_ready() or carla is None:
        return {"ok": False, "attack": attack, "message": "CARLA live ego vehicle is not ready."}
    intensity = _zg_live_clamp(intensity, 0.0, 1.0, 0.90)
    try:
        self._cleanup_impact_actors()
    except Exception:
        pass
    try:
        self.vehicle.set_autopilot(False)
        self._zg_autopilot_enabled = False
    except Exception:
        pass
    marker, marker_message = _zg_live_spawn_attack_marker(self, attack)
    self._zg_attack_runtime = {
        "active": True,
        "attack": attack,
        "intensity": intensity,
        "started_at": time.time(),
        "duration_sec": max(0.0, float(duration_sec or 0.0)),
        "tick_index": 0,
        "marker": marker,
        "marker_message": marker_message,
        "last_plan": {},
        "overlay": {},
    }
    applied = _zg_live_apply_attack_tick(self)
    self._route_mode = "persistent_adopted_attack"
    self.status.message = f"Live CARLA adopted attack active: {attack}."
    return {
        "ok": True,
        "attack": attack,
        "intensity": intensity,
        "message": f"{applied.get('message', '')} {marker_message}",
        "applied_control": applied.get("applied_control", {}),
        "damaged_parts": applied.get("damaged_parts", []),
        "impact": applied.get("impact", {}),
        "sensor_snapshot": self.sensor_snapshot(),
    }


def _zg_live_stop_attack_scenario(self, restore_natural_drive: bool = False):
    runtime = getattr(self, "_zg_attack_runtime", None) or {}
    runtime["active"] = False
    self._zg_attack_runtime = runtime
    if restore_natural_drive and self.is_ready():
        try:
            self.enable_natural_drive()
        except Exception:
            pass
    self._last_attack_notice = "Live CARLA adopted attack stopped."
    return {"ok": True, "message": self._last_attack_notice}


def _zg_live_apply_attack_tick(self):
    runtime = getattr(self, "_zg_attack_runtime", None)
    if not runtime or not runtime.get("active") or not self.is_ready() or carla is None:
        return {"ok": False, "message": "No active persistent CARLA attack.", "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}, "damaged_parts": []}
    elapsed = max(0.0, time.time() - float(runtime.get("started_at", time.time())))
    duration = float(runtime.get("duration_sec", 0.0) or 0.0)
    if duration > 0.0 and elapsed >= duration:
        _zg_live_stop_attack_scenario(self, restore_natural_drive=True)
        return {"ok": True, "expired": True, "message": "Attack duration completed; natural CARLA drive restored.", "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}, "damaged_parts": []}
    runtime["tick_index"] = int(runtime.get("tick_index", 0)) + 1
    plan = _zg_live_attack_plan(runtime["attack"], runtime["intensity"], elapsed, runtime["tick_index"])
    try:
        control = carla.VehicleControl()
        control.steer = _zg_live_clamp(plan["steer"], -1.0, 1.0)
        control.throttle = _zg_live_clamp(plan["throttle"], 0.0, 1.0)
        control.brake = _zg_live_clamp(plan["brake"], 0.0, 1.0)
        control.hand_brake = False
        control.reverse = False
        control.manual_gear_shift = False
        self.vehicle.apply_control(control)
    except Exception as exc:
        return {"ok": False, "message": f"Persistent CARLA attack control failed: {exc}", "applied_control": {"steer": 0.0, "throttle": 0.0, "brake": 0.0}, "damaged_parts": []}
    runtime["last_plan"] = dict(plan)
    runtime["overlay"] = dict(plan.get("overlay", {}))
    self._zg_attack_runtime = runtime
    self._damaged_parts = sorted(set(plan.get("damaged", [])))
    self._last_attack_notice = plan.get("message", "Persistent adopted attack is active.")
    self._last_impact_report = {
        "active": True,
        "verified": False,
        "severity": "simulated",
        "target": getattr(runtime.get("marker"), "type_id", "control-path"),
        "message": self._last_attack_notice,
    }
    return {
        "ok": True,
        "message": self._last_attack_notice,
        "applied_control": {"steer": round(float(control.steer), 3), "throttle": round(float(control.throttle), 3), "brake": round(float(control.brake), 3)},
        "damaged_parts": self._damaged_parts,
        "impact": dict(self._last_impact_report),
    }


# Preserve prior implementations so non-runtime paths remain intact.
_ZG_PRE_PERSISTENT_TICK = CarlaBridge.tick
_ZG_PRE_PERSISTENT_SENSOR_SNAPSHOT = CarlaBridge.sensor_snapshot
_ZG_PRE_PERSISTENT_READ_VEHICLE = CarlaBridge.read_vehicle_state
_ZG_PRE_PERSISTENT_APPLY_ATTACK_DEFENSE = CarlaBridge.apply_attack_and_defense


def _zg_live_tick(self):
    # Re-apply the attack every CARLA tick. This is the key fix that prevents a
    # single dashboard command from disappearing after one frame.
    runtime = getattr(self, "_zg_attack_runtime", None)
    if runtime and runtime.get("active"):
        _zg_live_apply_attack_tick(self)
    return _ZG_PRE_PERSISTENT_TICK(self)


def _zg_live_sensor_snapshot(self):
    snap = _ZG_PRE_PERSISTENT_SENSOR_SNAPSHOT(self)
    runtime = getattr(self, "_zg_attack_runtime", None) or {}
    if runtime.get("active"):
        snap["attack_runtime"] = {
            "active": True,
            "attack": runtime.get("attack"),
            "intensity": runtime.get("intensity"),
            "elapsed_s": round(max(0.0, time.time() - float(runtime.get("started_at", time.time()))), 2),
            "overlay": dict(runtime.get("overlay", {})),
            "message": self._last_attack_notice,
        }
    return snap


def _zg_live_read_vehicle_state(self, fallback):
    state = _ZG_PRE_PERSISTENT_READ_VEHICLE(self, fallback)
    runtime = getattr(self, "_zg_attack_runtime", None) or {}
    if not runtime.get("active"):
        return state
    plan = runtime.get("last_plan") or {}
    try:
        state.lane_status = str(plan.get("lane_status") or state.lane_status)
        overlay = runtime.get("overlay") or {}
        if overlay.get("gps_override"):
            state.location_label = f"CARLA map · simulated GPS route divergence (+{overlay.get('gps_offset_m', 0)}m)"
        if overlay.get("perception_override"):
            state.location_label = f"CARLA map · simulated perception spoofing"
        marker = runtime.get("marker")
        if marker is not None and getattr(marker, "is_alive", False) and self.vehicle is not None:
            a = self.vehicle.get_transform().location
            b = marker.get_transform().location
            state.obstacle_distance_m = round(math.sqrt((a.x-b.x)**2 + (a.y-b.y)**2 + (a.z-b.z)**2), 1)
    except Exception:
        pass
    return state


def _zg_live_apply_attack_and_defense(self, vehicle_state, attack, risk):
    runtime = getattr(self, "_zg_attack_runtime", None) or {}
    if runtime.get("active"):
        applied = _zg_live_apply_attack_tick(self)
        return {
            "mode": "carla",
            "attack_applied": bool(applied.get("ok")),
            "defense_applied": False,
            "applied_control": applied.get("applied_control", {"steer": vehicle_state.steer, "throttle": vehicle_state.throttle, "brake": vehicle_state.brake}),
            "damaged_parts": applied.get("damaged_parts", []),
            "impact": applied.get("impact", {}),
            "diagnostic_notice": applied.get("message", "Persistent attack active."),
            "sensor_snapshot": self.sensor_snapshot(),
        }
    return _ZG_PRE_PERSISTENT_APPLY_ATTACK_DEFENSE(self, vehicle_state, attack, risk)


def _zg_live_apply_direct_attack(self, attack_name: str, intensity: float = 0.9):
    # Canonical direct-attack entry point used by the dashboard and API.
    return _zg_live_start_attack_scenario(self, attack_name, intensity)


CarlaBridge.start_attack_scenario = _zg_live_start_attack_scenario
CarlaBridge.stop_attack_scenario = _zg_live_stop_attack_scenario
CarlaBridge.apply_active_attack_tick = _zg_live_apply_attack_tick
CarlaBridge.tick = _zg_live_tick
CarlaBridge.sensor_snapshot = _zg_live_sensor_snapshot
CarlaBridge.read_vehicle_state = _zg_live_read_vehicle_state
CarlaBridge.apply_attack_and_defense = _zg_live_apply_attack_and_defense
CarlaBridge.apply_direct_attack = _zg_live_apply_direct_attack

# ---------------------------------------------------------------------------
# Steering-manipulation visibility hardening patch
# ---------------------------------------------------------------------------
# Reason: in some CARLA runs a prior driving/autopilot control can overwrite a
# moderate steering command before the next visual frame. This final layer
# disables autopilot on every active attack tick and reapplies the command after
# the simulator tick. It stays entirely inside CARLA and does not touch real
# vehicle interfaces.
_ZG_VISIBILITY_PREVIOUS_TICK = CarlaBridge.tick
_ZG_VISIBILITY_PREVIOUS_PLAN = _zg_live_attack_plan


def _zg_visibility_attack_plan(attack_name, intensity, elapsed_s=0.0, tick_index=0):
    plan = _ZG_VISIBILITY_PREVIOUS_PLAN(attack_name, intensity, elapsed_s, tick_index)
    if canonical_attack(attack_name) == "steering_manipulation":
        # Make the lateral control visibly different from normal driving while
        # keeping it bounded to CARLA VehicleControl ranges.
        i = _zg_live_clamp(intensity, 0.0, 1.0, 0.90)
        plan = dict(plan)
        plan.update({
            "steer": min(0.78, 0.42 + 0.40 * i),
            "throttle": min(0.60, 0.38 + 0.24 * i),
            "brake": 0.0,
            "lane_status": "steering_override_visible",
            "message": "Visible persistent steering override is applied after each CARLA tick.",
        })
    return plan


def _zg_visibility_apply_after_tick(self):
    runtime = getattr(self, "_zg_attack_runtime", None) or {}
    if not runtime.get("active") or not self.is_ready() or carla is None:
        return None
    try:
        # Autopilot/Traffic Manager must not own the ego controls while an
        # explicit dashboard attack scenario is active.
        self.vehicle.set_autopilot(False)
        self._zg_autopilot_enabled = False
    except Exception:
        pass
    elapsed = max(0.0, time.time() - float(runtime.get("started_at", time.time())))
    runtime["tick_index"] = int(runtime.get("tick_index", 0)) + 1
    plan = _zg_visibility_attack_plan(runtime.get("attack", ""), runtime.get("intensity", 0.9), elapsed, runtime["tick_index"])
    try:
        control = carla.VehicleControl(
            throttle=_zg_live_clamp(plan.get("throttle", 0.0), 0.0, 1.0),
            steer=_zg_live_clamp(plan.get("steer", 0.0), -1.0, 1.0),
            brake=_zg_live_clamp(plan.get("brake", 0.0), 0.0, 1.0),
            hand_brake=False,
            reverse=False,
            manual_gear_shift=False,
        )
        self.vehicle.apply_control(control)
        runtime["last_plan"] = dict(plan)
        runtime["overlay"] = dict(plan.get("overlay", {}))
        self._zg_attack_runtime = runtime
        self._last_attack_notice = plan.get("message", "Persistent adopted attack is active.")
        self._damaged_parts = sorted(set(plan.get("damaged", [])))
        return {"ok": True, "applied_control": {"steer": round(float(control.steer), 3), "throttle": round(float(control.throttle), 3), "brake": round(float(control.brake), 3)}}
    except Exception as exc:
        self.status.message = f"Attack visibility control failed: {exc}"
        return {"ok": False, "message": str(exc)}


def _zg_visibility_tick(self):
    # Tick the world first, then apply the explicit attack command for the
    # following frame. Applying after the tick avoids older control paths
    # overriding Steering Manipulation before CARLA renders it.
    result = _ZG_VISIBILITY_PREVIOUS_TICK(self)
    _zg_visibility_apply_after_tick(self)
    return result


_zg_live_attack_plan = _zg_visibility_attack_plan
CarlaBridge.tick = _zg_visibility_tick
CarlaBridge.apply_active_attack_tick = _zg_visibility_apply_after_tick

# ---------------------------------------------------------------------------
# DriveFort AI stationary-ego launch assist (CARLA-only demo reliability patch)
# ---------------------------------------------------------------------------
# In synchronous CARLA sessions an ego actor can remain at 0 km/h even though
# VehicleControl values are accepted, especially after it has just been spawned
# or Traffic Manager ownership has changed.  This wrapper keeps controls fully
# inside CARLA, explicitly enables physics/automatic gear, and gives the ego a
# one-time bounded forward launch only while it is demonstrably stationary.
# It never moves or teleports any external target actor.
_ZG_STATIONARY_PREVIOUS_APPLY_AFTER_TICK = _zg_visibility_apply_after_tick

def _zg_stationary_speed_ms(vehicle):
    try:
        v = vehicle.get_velocity()
        return math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z)
    except Exception:
        return 0.0

def _zg_stationary_launch_assist(self):
    runtime = getattr(self, "_zg_attack_runtime", None) or {}
    if not runtime.get("active") or not self.is_ready() or carla is None:
        return
    # Only attacks with a visible vehicle-motion effect should receive a launch
    # assist. GPS/sensor overlays remain context-only.
    motion_attacks = {
        "steering_manipulation", "brake_override", "acceleration_injection",
        "can_bus_injection", "dos", "lane_drift_attack", "pedestrian_detection_attack",
    }
    attack = canonical_attack(runtime.get("attack", ""))
    if attack not in motion_attacks:
        return
    try:
        self.vehicle.set_autopilot(False)
        self._zg_autopilot_enabled = False
    except Exception:
        pass
    try:
        self.vehicle.set_simulate_physics(True)
    except Exception:
        pass
    launches = int(runtime.get("launch_assist_ticks", 0) or 0)
    speed_ms = _zg_stationary_speed_ms(self.vehicle)
    # Apply a short, bounded CARLA-only velocity nudge while stopped. It is
    # intentionally limited to the first 12 ticks and is released afterwards,
    # allowing normal VehicleControl steering to visibly bend the trajectory.
    if speed_ms < 0.35 and launches < 12:
        try:
            tr = self.vehicle.get_transform()
            fwd = tr.get_forward_vector()
            launch_speed = 7.5 if attack in {"steering_manipulation", "lane_drift_attack"} else 6.0
            self.vehicle.set_target_velocity(carla.Vector3D(
                x=float(fwd.x) * launch_speed,
                y=float(fwd.y) * launch_speed,
                z=0.0,
            ))
            runtime["launch_assist_ticks"] = launches + 1
            runtime["launch_assist"] = {
                "active": True,
                "speed_ms": launch_speed,
                "reason": "ego actor was stationary after explicit CARLA control",
            }
        except Exception as exc:
            runtime["launch_assist_error"] = str(exc)
    else:
        runtime["launch_assist"] = {"active": False, "speed_ms": round(speed_ms, 2)}
    self._zg_attack_runtime = runtime

def _zg_stationary_visibility_tick(self):
    result = _ZG_STATIONARY_PREVIOUS_APPLY_AFTER_TICK(self)
    _zg_stationary_launch_assist(self)
    return result

CarlaBridge.apply_active_attack_tick = _zg_stationary_visibility_tick
# Replace the per-tick function with a version that applies the same control
# and then guarantees launch only when the spawned ego remains stationary.
def _zg_stationary_tick(self):
    result = _ZG_VISIBILITY_PREVIOUS_TICK(self)
    _zg_stationary_visibility_tick(self)
    return result
CarlaBridge.tick = _zg_stationary_tick


# ---------------------------------------------------------------------------
# FINAL DASHBOARD MOTION + RECOVERY RELIABILITY PATCH
# ---------------------------------------------------------------------------
# This final layer fixes five practical demo issues:
# 1) manual attacker takeover is persistent rather than one-frame;
# 2) reset/recovery clears all CARLA control runtimes;
# 3) acceleration injection explicitly releases stop/gear/physics state;
# 4) telemetry reads are refreshed after simulator ticks;
# 5) normal driving cannot overwrite a live dashboard command.

_ZG_FINAL_PREV_TICK = CarlaBridge.tick
_ZG_FINAL_PREV_READ = CarlaBridge.read_vehicle_state
_ZG_FINAL_PREV_APPLY_STATE = CarlaBridge.apply_vehicle_state
_ZG_FINAL_PREV_RECOVER = CarlaBridge.recover_vehicle
_ZG_FINAL_PREV_START_ATTACK = CarlaBridge.start_attack_scenario


def _zg_final_control(self, steer=0.0, throttle=0.0, brake=0.0):
    c = carla.VehicleControl()
    c.steer = _zg_live_clamp(steer, -1.0, 1.0, 0.0)
    c.throttle = _zg_live_clamp(throttle, 0.0, 1.0, 0.0)
    c.brake = _zg_live_clamp(brake, 0.0, 1.0, 0.0)
    c.hand_brake = False
    c.reverse = False
    c.manual_gear_shift = False
    return c


def _zg_final_prepare_motion(self):
    if not self.is_ready() or carla is None:
        return
    try:
        self.vehicle.set_autopilot(False)
        self._zg_autopilot_enabled = False
    except Exception:
        pass
    try:
        self.vehicle.set_simulate_physics(True)
    except Exception:
        pass
    try:
        # Clear stale stop / handbrake / reverse state before applying a dashboard command.
        self.vehicle.apply_control(_zg_final_control(self, 0.0, 0.0, 0.0))
    except Exception:
        pass


def _zg_final_start_attack(self, attack_name, intensity=0.90, duration_sec=0.0):
    _zg_final_prepare_motion(self)
    result = _ZG_FINAL_PREV_START_ATTACK(self, attack_name, intensity, duration_sec)
    runtime = getattr(self, '_zg_attack_runtime', None) or {}
    if runtime.get('active'):
        runtime['launch_assist_ticks'] = 0
        runtime['motion_ready'] = True
        runtime['acceleration_release'] = canonical_attack(attack_name) == 'acceleration_injection'
        self._zg_attack_runtime = runtime
    return result


def _zg_final_set_manual_takeover(self, steer=0.0, throttle=0.0, brake=0.0, hold_seconds=0.0):
    if not self.is_ready() or carla is None:
        return {'ok': False, 'message': 'CARLA vehicle is not ready for manual takeover.', 'applied_control': {'steer': 0.0, 'throttle': 0.0, 'brake': 0.0}}
    _zg_final_prepare_motion(self)
    self._zg_attack_runtime = {'active': False, 'attack': None}
    self._zg_manual_runtime = {
        'active': True,
        'steer': _zg_live_clamp(steer, -1.0, 1.0, 0.0),
        'throttle': _zg_live_clamp(throttle, 0.0, 1.0, 0.0),
        'brake': _zg_live_clamp(brake, 0.0, 1.0, 0.0),
        'started_at': time.time(),
        'hold_seconds': max(0.0, float(hold_seconds or 0.0)),
        'tick_index': 0,
        'launch_assist_ticks': 0,
    }
    ctrl = _zg_final_control(self, steer, throttle, brake)
    try:
        self.vehicle.apply_control(ctrl)
        self._last_attack_notice = f'Persistent dashboard attacker takeover active: steer={ctrl.steer:.2f}, throttle={ctrl.throttle:.2f}, brake={ctrl.brake:.2f}.'
        self._route_mode = 'dashboard_manual_takeover_persistent'
        self._damaged_parts = ['Remote command channel', 'Steering/Brake/Throttle control path']
        return {'ok': True, 'message': self._last_attack_notice, 'applied_control': {'steer': round(float(ctrl.steer),3), 'throttle': round(float(ctrl.throttle),3), 'brake': round(float(ctrl.brake),3)}, 'damaged_parts': list(self._damaged_parts)}
    except Exception as exc:
        return {'ok': False, 'message': f'Manual takeover control failed: {exc}', 'applied_control': {'steer': 0.0, 'throttle': 0.0, 'brake': 0.0}}


def _zg_final_apply_manual_tick(self):
    runtime = getattr(self, '_zg_manual_runtime', None) or {}
    if not runtime.get('active') or not self.is_ready() or carla is None:
        return None
    elapsed = time.time() - float(runtime.get('started_at', time.time()))
    if runtime.get('hold_seconds', 0.0) > 0 and elapsed >= runtime['hold_seconds']:
        runtime['active'] = False
        self._zg_manual_runtime = runtime
        return None
    _zg_final_prepare_motion(self)
    ctrl = _zg_final_control(self, runtime.get('steer',0.0), runtime.get('throttle',0.0), runtime.get('brake',0.0))
    try:
        self.vehicle.apply_control(ctrl)
        runtime['tick_index'] = int(runtime.get('tick_index', 0)) + 1
        # Short CARLA-only launch assist for throttle/manual movement when an actor is still stationary.
        speed = _zg_stationary_speed_ms(self.vehicle)
        if ctrl.throttle > 0.15 and speed < 0.35 and int(runtime.get('launch_assist_ticks',0)) < 12:
            tr = self.vehicle.get_transform(); fwd = tr.get_forward_vector()
            self.vehicle.set_target_velocity(carla.Vector3D(x=float(fwd.x)*6.5, y=float(fwd.y)*6.5, z=0.0))
            runtime['launch_assist_ticks'] = int(runtime.get('launch_assist_ticks',0)) + 1
        self._zg_manual_runtime = runtime
        return {'ok': True, 'applied_control': {'steer':round(float(ctrl.steer),3),'throttle':round(float(ctrl.throttle),3),'brake':round(float(ctrl.brake),3)}}
    except Exception as exc:
        self.status.message = f'Persistent manual takeover failed: {exc}'
        return {'ok': False, 'message': str(exc)}


def _zg_final_tick(self):
    # Existing persistent-attack tick advances CARLA. Apply the active command
    # again after that tick so Traffic Manager/legacy controls cannot overwrite it.
    result = _ZG_FINAL_PREV_TICK(self)
    runtime = getattr(self, '_zg_attack_runtime', None) or {}
    if runtime.get('active'):
        _zg_visibility_apply_after_tick(self)
        _zg_stationary_launch_assist(self)
    _zg_final_apply_manual_tick(self)
    return result


def _zg_final_apply_vehicle_state(self, vehicle_state):
    # Do not re-enable natural autopilot while an attack or manual takeover owns controls.
    if (getattr(self, '_zg_attack_runtime', None) or {}).get('active') or (getattr(self, '_zg_manual_runtime', None) or {}).get('active'):
        return
    return _ZG_FINAL_PREV_APPLY_STATE(self, vehicle_state)


def _zg_final_clear_runtime(self, restore_natural=True):
    try:
        _zg_live_stop_attack_scenario(self, restore_natural_drive=False)
    except Exception:
        self._zg_attack_runtime = {'active': False}
    self._zg_manual_runtime = {'active': False}
    self._cleanup_impact_actors()
    self._damaged_parts = []
    try:
        _zg_final_prepare_motion(self)
        self.vehicle.apply_control(_zg_final_control(self, 0.0, 0.0, 0.0))
    except Exception:
        pass
    if restore_natural:
        return self.enable_natural_drive()
    return {'ok': True, 'message': 'CARLA attack/manual control runtimes cleared.'}


def _zg_final_recover(self):
    # Recovery must clear persistent attack/manual runtimes before Traffic Manager is restored.
    if not self.is_ready():
        return _ZG_FINAL_PREV_RECOVER(self)
    self._zg_manual_runtime = {'active': False}
    self._zg_attack_runtime = {'active': False}
    self._cleanup_impact_actors()
    try:
        _zg_final_prepare_motion(self)
        self.vehicle.apply_control(_zg_final_control(self,0.0,0.0,0.0))
    except Exception:
        pass
    result = self.enable_natural_drive(speed_percent=-8.0)
    self._route_mode = 'recovered_natural_autopilot'
    self._last_attack_notice = 'Recovery complete: attack cleared, controls normalized, natural CARLA drive restored.'
    self._last_impact_report = {'active':False,'verified':False,'severity':'none','target':'none','message':self._last_attack_notice}
    return {'ok': bool(result.get('ok', True)), 'message': result.get('message', self._last_attack_notice), 'applied_control': {'steer':0.0,'throttle':0.0,'brake':0.0}}


def _zg_final_sensor_snapshot(self):
    snap = _ZG_PRE_PERSISTENT_SENSOR_SNAPSHOT(self)
    runtime = getattr(self, '_zg_attack_runtime', None) or {}
    manual = getattr(self, '_zg_manual_runtime', None) or {}
    if runtime.get('active'):
        snap['attack_runtime'] = {'active':True,'attack':runtime.get('attack'),'intensity':runtime.get('intensity'),'overlay':dict(runtime.get('overlay',{})),'message':self._last_attack_notice}
    elif manual.get('active'):
        snap['attack_runtime'] = {'active':True,'attack':'manual_takeover','intensity':max(abs(float(manual.get('steer',0))),float(manual.get('throttle',0)),float(manual.get('brake',0))),'overlay':{'manual_takeover':True},'message':self._last_attack_notice}
    return snap

CarlaBridge.start_attack_scenario = _zg_final_start_attack
CarlaBridge.apply_manual_attacker_control = _zg_final_set_manual_takeover
CarlaBridge.tick = _zg_final_tick
CarlaBridge.apply_vehicle_state = _zg_final_apply_vehicle_state
CarlaBridge.recover_vehicle = _zg_final_recover
CarlaBridge.clear_dashboard_runtimes = _zg_final_clear_runtime
CarlaBridge.sensor_snapshot = _zg_final_sensor_snapshot
