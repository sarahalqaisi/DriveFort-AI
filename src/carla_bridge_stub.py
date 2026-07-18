"""Optional CARLA integration stub.

This file shows where CARLA state would be translated into DriveFort AI vehicle state.
It is intentionally safe and optional, so the project remains runnable without CARLA.
"""

from .models import VehicleState


def map_carla_state_to_vehicle_state() -> VehicleState:
    return VehicleState(location_label="CARLA Map", autopilot_enabled=True)
