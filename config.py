"""Persisted app settings: ~/.config/spotter-test/config.json.

Separate config dir from the existing Spotter app (~/.config/spotter/) so
the two apps never clobber each other's settings.
"""
from __future__ import annotations

import copy
import json
import os

DEFAULT_PATH = os.path.expanduser("~/.config/spotter-test/config.json")

DEFAULTS = {
    "host": "ve7cc.net",
    "port": 23,
    "callsign": "N6YU",
    "dedup_minutes": 10,
    "window_minutes": 10,
    "center_khz": 14025.0,
    "bandwidth_khz": 50.0,
    "selected_band": "20m",
}


def _merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class Config:
    def __init__(self, path: str = DEFAULT_PATH):
        self._path = path
        self.data: dict = {}

    def load(self) -> "Config":
        self.data = copy.deepcopy(DEFAULTS)
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (json.JSONDecodeError, OSError):
            return self
        self.data = _merge(self.data, saved)
        return self

    def save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str, default=None):
        return self.data.get(key, default)

    def set(self, key: str, value) -> None:
        self.data[key] = value
