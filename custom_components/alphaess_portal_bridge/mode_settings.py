"""Persist the user-controlled settings of each original charging mode."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_MODE_SETTINGS


class ModeSettings:
    """Keep mode-specific setpoints separate from the PV controller."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, serial: str | None) -> None:
        self.hass = hass
        self.entry = entry
        self.serial = serial

    def get(self, generation: str, mode: int) -> dict[str, Any]:
        saved = self.entry.options.get(CONF_MODE_SETTINGS, {})
        values = saved.get(f"{self.serial}:{generation}:{mode}", {}) if isinstance(saved, dict) else {}
        return dict(values) if isinstance(values, dict) else {}

    def save(self, generation: str, mode: int, settings: dict[str, Any]) -> None:
        if not self.serial:
            raise ValueError("Die Seriennummer der Wallbox ist nicht verfügbar")
        values = self.get(generation, mode)
        current = settings.get("chargeCurrent")
        if type(current) in (int, float) and current in range(6, 17):
            values["chargeCurrent"] = int(current)
        if generation == "g2T":
            phase = settings.get("obcPhase")
            smart = settings.get("smartMode")
            if type(phase) in (int, float) and phase in (1, 2, 3):
                values["obcPhase"] = int(phase)
            if isinstance(smart, bool):
                values["smartMode"] = smart
        if not values:
            return
        saved = self.entry.options.get(CONF_MODE_SETTINGS, {})
        saved = dict(saved) if isinstance(saved, dict) else {}
        key = f"{self.serial}:{generation}:{mode}"
        if saved.get(key) == values:
            return
        saved[key] = values
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_MODE_SETTINGS: saved}
        )
