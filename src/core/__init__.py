"""DriveFort AI core configuration and lifecycle helpers."""

from .brand import BRAND
from .state_machine import derive_system_phase

__all__ = ["BRAND", "derive_system_phase"]
