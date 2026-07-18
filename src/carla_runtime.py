"""CARLA 0.9.13 + Python 3.7 runtime helpers for Windows.

Configured for:
  - Python 3.7.x, tested with Python 3.7.9 64-bit
  - CARLA 0.9.13
  - CARLA wheel: carla-0.9.13-cp37-cp37m-win_amd64.whl
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

REQUIRED_CARLA_VERSION = "0.9.13"
REQUIRED_PYTHON_MAJOR = 3
REQUIRED_PYTHON_MINOR = 7
REQUIRED_PYTHON_DISPLAY = "3.7.9"
_REQUIRED_WHL_PREFIX = "carla-0.9.13-cp37-cp37m-win_amd64"
_REQUIRED_EGG_PREFIX = "carla-0.9.13-py3.7"


def current_python_is_supported() -> bool:
    return sys.version_info.major == REQUIRED_PYTHON_MAJOR and sys.version_info.minor == REQUIRED_PYTHON_MINOR


def current_python_is_64bit() -> bool:
    return sys.maxsize > 2**32


def _candidate_roots() -> List[Path]:
    roots: List[Path] = []
    for key in ("CARLA_ROOT", "CARLA_HOME", "CARLA_PATH"):
        value = os.environ.get(key)
        if value:
            roots.append(Path(value))
    for pattern in (
        r"D:\Downloads\CarlaSimulator*",
        r"D:\Downloads\CARLA*",
        r"C:\CARLA_0.9.13*",
        r"C:\carla-0.9.13*",
        r"C:\CARLA*",
        str(Path.home() / "Downloads" / "CarlaSimulator*"),
        str(Path.home() / "Downloads" / "CARLA*"),
        str(Path.home() / "CARLA_0.9.13*"),
    ):
        roots.extend(Path(p) for p in glob.glob(pattern))
    seen = set()
    unique: List[Path] = []
    for root in roots:
        text = str(root).lower()
        if text not in seen:
            seen.add(text)
            unique.append(root)
    return unique


def _dist_dirs(root: Path) -> List[Path]:
    return [
        root / "PythonAPI" / "carla" / "dist",
        root / "WindowsNoEditor" / "PythonAPI" / "carla" / "dist",
    ]


def _discover_carla_packages() -> List[Path]:
    files: List[Path] = []
    for key in ("CARLA_WHL_PATH", "CARLA_EGG_PATH", "PYTHONPATH"):
        for item in os.environ.get(key, "").split(os.pathsep):
            if item and Path(item).name.lower().startswith("carla-") and Path(item).suffix.lower() in (".whl", ".egg"):
                files.append(Path(item))
    for root in _candidate_roots():
        for dist_dir in _dist_dirs(root):
            if dist_dir.exists():
                files.extend(sorted(dist_dir.glob("carla-0.9.13-cp37-cp37m-win_amd64.whl")))
                files.extend(sorted(dist_dir.glob("carla-0.9.13-py3.7-win-amd64.egg")))
    seen = set()
    unique: List[Path] = []
    for p in files:
        text = str(p).lower()
        if text not in seen:
            seen.add(text)
            unique.append(p)
    return unique


def find_matching_carla_package() -> Tuple[Optional[Path], List[Path]]:
    packages = _discover_carla_packages()
    for p in packages:
        name = p.name.lower()
        if name.startswith(_REQUIRED_WHL_PREFIX) or name.startswith(_REQUIRED_EGG_PREFIX):
            return p, packages
    return None, packages


def find_matching_carla_egg() -> Tuple[Optional[Path], List[Path]]:
    return find_matching_carla_package()


def expected_egg_hint() -> str:
    return r"D:\Downloads\CarlaSimulator\WindowsNoEditor\PythonAPI\carla\dist\carla-0.9.13-cp37-cp37m-win_amd64.whl"


def _import_installed_carla() -> Tuple[bool, str]:
    try:
        import carla  # type: ignore
        version = getattr(carla, "__version__", REQUIRED_CARLA_VERSION)
        location = getattr(carla, "__file__", "installed package")
        return True, "Using installed CARLA Python API: %s at %s" % (version, location)
    except Exception as exc:
        return False, str(exc)


def ensure_carla_on_path() -> Tuple[bool, str]:
    if not current_python_is_supported():
        return False, (
            "This project is configured for Python 3.7.x with CARLA 0.9.13 cp37. "
            "Current Python is %s.%s.%s. Please launch with: py -3.7"
            % (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)
        )
    if not current_python_is_64bit():
        return False, "Python 3.7 is 32-bit. Install/use Python 3.7 64-bit because CARLA wheel is win_amd64."

    ok, msg = _import_installed_carla()
    if ok:
        return True, msg

    pkg, discovered = find_matching_carla_package()
    if pkg is not None:
        pkg_text = str(pkg)
        if pkg_text not in sys.path:
            sys.path.insert(0, pkg_text)
        ok2, msg2 = _import_installed_carla()
        if ok2:
            return True, msg2
        return False, 'Found compatible CARLA package but import failed. Install it with: py -3.7 -m pip install "%s". Reason: %s' % (pkg_text, msg2)

    if discovered:
        return False, "Found CARLA package(s), but not the required CARLA 0.9.13 cp37 win_amd64 package: " + ", ".join(p.name for p in discovered)
    return False, "CARLA 0.9.13 cp37 wheel was not found. Expected: " + expected_egg_hint()
