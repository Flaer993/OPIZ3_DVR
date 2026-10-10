from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "display": {
        "backend": "simulator", "controller": "st7735", "width": 128, "height": 160, "rotation": 0,
        "spi_bus": 1, "spi_device": 0, "spi_hz": 32_000_000,
        "gpio_chip": "/dev/gpiochip0", "dc_line": 0, "reset_line": 0,
        "backlight_line": None, "x_offset": 0, "y_offset": 0,
        "bgr": True, "invert": True,
    },
    "button": {
        "enabled": False, "gpio_chip": "/dev/gpiochip0", "line": 0,
        "active_low": True, "debounce_ms": 80, "long_press_ms": 800,
    },
    "refresh_seconds": 1.0,
    "network_interface": None,
    "server": {"url": "http://127.0.0.1:8080/health", "ip_address": "", "timeout_seconds": 0.7, "status_file": ""},
    "storage": {"raid_type": "auto", "devices": []},
    "cameras": [],
    "media": {"path": "assets/visual.png", "frame_ms": 80},
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(path: str | Path) -> tuple[dict[str, Any], Path]:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("r", encoding="utf-8") as handle:
        user_config = json.load(handle)
    config = _merge(copy.deepcopy(DEFAULT_CONFIG), user_config)
    config["_base_dir"] = str(config_path.parent)
    return config, config_path


def resolve_path(config: dict[str, Any], value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    return path if path.is_absolute() else Path(config["_base_dir"]) / path
