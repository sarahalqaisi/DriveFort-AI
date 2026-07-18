from src.carla_bridge import CarlaBridge


def test_carla_bridge_import_safe_without_carla_runtime():
    bridge = CarlaBridge()
    status = bridge.status.to_dict()
    assert "enabled" in status
    assert "sensors_ready" in status
    assert "live_loop_running" in status


def test_carla_sensor_snapshot_shape():
    bridge = CarlaBridge()
    snap = bridge.sensor_snapshot()
    assert "gnss" in snap
    assert "imu" in snap
    assert "age_ms" in snap
