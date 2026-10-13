"""Home Assistant runtime for HA charging mode 5 (PV self-consumption)."""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .api import AuthenticationError, PortalConnectionError
from .const import (
    CONF_ACTIVE_VEHICLE_PROFILE,
    CONF_ALLOWED_DEFICIT,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CONTROL_STRATEGY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOUSEHOLD_POWER_ENTITY,
    CONF_PV_MODE_ACTIVE,
    CONF_PV_POWER_ENTITY,
    CONF_VEHICLE_PROFILES,
    CONTROL_NUMBER_SETTINGS,
)
from .coordinator import AlphaESSWallboxCoordinator
from .entity import settings_object
from .pv_control import (
    MODE_CUSTOM,
    MODE_SURPLUS,
    SAMPLE_INTERVAL_SECONDS,
    STRATEGY_DIRECT,
    Command,
    ControlSettings,
    Measurement,
    PVController,
    WallboxState,
)
from .vehicle_profiles import PROFILE_NAME, get_profiles

_LOGGER = logging.getLogger(__name__)
_NOTIFY_INTERVAL_SECONDS = 30

# (measurement field, option key, label, is power sensor)
_SENSORS = (
    ("pv", CONF_PV_POWER_ENTITY, "PV-Leistung", True),
    ("house", CONF_HOUSEHOLD_POWER_ENTITY, "Hauslast", True),
    ("grid", CONF_GRID_POWER_ENTITY, "Netzfluss", True),
    ("soc", CONF_BATTERY_SOC_ENTITY, "Hausakku-SOC", False),
)
STRATEGY_NAMES = {STRATEGY_DIRECT: "Direktregelung"}


class PVModeManager:
    """Run the mode-5 controller while the user has selected it."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, coordinator: AlphaESSWallboxCoordinator
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.active = bool(entry.options.get(CONF_PV_MODE_ACTIVE))
        self.controller: PVController | None = None
        self.profile_name = ""
        self.last_action: str | None = None
        self.last_action_at: datetime | None = None
        self._portal_problem: str | None = None
        self._unsub: Callable[[], None] | None = None
        self._busy = False
        self._listeners: list[Callable[[], None]] = []
        self._last_notify = 0.0
        self._last_signature: tuple[Any, ...] = ()

    # -- listeners -------------------------------------------------------
    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(listener)

        def remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return remove

    def _notify(self, force: bool = False) -> None:
        signature = (
            self.active,
            self.controller.state if self.controller else None,
            self.last_action,
            self._portal_problem,
        )
        now = time.monotonic()
        if (
            not force
            and signature == self._last_signature
            and now - self._last_notify < _NOTIFY_INTERVAL_SECONDS
        ):
            return
        self._last_signature = signature
        self._last_notify = now
        for listener in list(self._listeners):
            listener()

    # -- lifecycle -------------------------------------------------------
    async def async_start(self) -> None:
        """Resume mode 5 after a restart or options reload."""
        if self.active:
            self._start_controller()

    def stop(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None
        self.controller = None

    def _start_controller(self) -> None:
        self.stop()
        options = self.entry.options
        profiles = get_profiles(options, CONF_VEHICLE_PROFILES)
        profile_id = options.get(CONF_ACTIVE_VEHICLE_PROFILE)
        if profile_id not in profiles:
            profile_id = next(iter(profiles))
        profile = profiles[profile_id]
        self.profile_name = profile.get(PROFILE_NAME, "")
        settings = ControlSettings.from_options(
            options, CONTROL_NUMBER_SETTINGS, CONF_CONTROL_STRATEGY
        )
        self.controller = PVController(profile, settings)
        self._unsub = async_track_time_interval(
            self.hass, self._async_tick, timedelta(seconds=SAMPLE_INTERVAL_SECONDS)
        )

    def _persist(self) -> None:
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_PV_MODE_ACTIVE: self.active}
        )

    # -- permitted deficit (option and live number entity) ---------------
    def allowed_deficit(self) -> float:
        default = CONTROL_NUMBER_SETTINGS[CONF_ALLOWED_DEFICIT][0]
        value = self.entry.options.get(CONF_ALLOWED_DEFICIT, default)
        return float(value) if isinstance(value, (int, float)) else float(default)

    def set_allowed_deficit(self, value: float) -> None:
        """Store the value and apply it to the running controller.

        Writing the options directly does not reload the entry, so the
        running averages are kept and the next decision uses the new value.
        """
        _, minimum, maximum, _, _ = CONTROL_NUMBER_SETTINGS[CONF_ALLOWED_DEFICIT]
        value = float(min(max(value, minimum), maximum))
        self.hass.config_entries.async_update_entry(
            self.entry, options={**self.entry.options, CONF_ALLOWED_DEFICIT: value}
        )
        if self.controller is not None:
            self.controller.settings.allowed_grid_import_w = value
        self._notify(force=True)

    async def async_activate(self) -> None:
        generation, _ = settings_object(self.coordinator)
        if generation != "g2T":
            raise HomeAssistantError("Modus 5 benötigt eine G2T-Wallbox mit Phasenwahl")
        missing = [label for _, key, label, _ in _SENSORS if not self.entry.options.get(key)]
        if missing:
            raise HomeAssistantError(
                "Für Modus 5 in den Integrationsoptionen auswählen: " + ", ".join(missing)
            )
        if self.active and self.controller is not None:
            return
        self.active = True
        self._persist()
        self._start_controller()
        self._record("Modus 5 aktiviert")
        self._notify(force=True)

    async def async_deactivate(self) -> None:
        if not self.active:
            return
        self.active = False
        self._persist()
        self.stop()
        self._record("Modus 5 beendet")
        self._notify(force=True)

    def _record(self, action: str) -> None:
        self.last_action = action
        self.last_action_at = dt_util.now()

    # -- inputs ----------------------------------------------------------
    def _read_measurement(self, stale_seconds: float) -> Measurement:
        values: dict[str, float] = {}
        now = dt_util.utcnow()
        for field, key, label, is_power in _SENSORS:
            entity_id = self.entry.options.get(key)
            if not entity_id:
                return Measurement(problem=f"{label}: kein Sensor ausgewählt")
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                return Measurement(problem=f"{label} nicht verfügbar")
            try:
                value = float(state.state)
            except ValueError:
                return Measurement(problem=f"{label} ohne Zahlenwert")
            if is_power:
                if state.attributes.get("unit_of_measurement") == "kW":
                    value *= 1000
                # last_reported also advances when a sensor republishes an
                # unchanged value; last_changed would not.
                reported = getattr(state, "last_reported", None) or state.last_updated
                age = (now - reported).total_seconds()
                if age > stale_seconds:
                    return Measurement(problem=f"{label} seit {age:.0f} s ohne neuen Wert")
            values[field] = value
        return Measurement(**values)

    def _wallbox_state(self) -> WallboxState:
        data = self.coordinator.data or {}
        status_data = data.get("wallbox_status")
        status_data = status_data if isinstance(status_data, dict) else {}
        status = status_data.get("status")
        _, settings = settings_object(self.coordinator)
        power = status_data.get("power")
        return WallboxState(
            connected=isinstance(status, str) and status != "NotInsertedGun",
            charging=status == "Charging",
            schedule_active=settings.get("chargeStrategy") == 1,
            mode=settings.get("chargeMode"),
            phases=settings.get("obcPhase"),
            current=settings.get("chargeCurrent"),
            cloud_power=float(power) if isinstance(power, (int, float)) else None,
        )

    # -- control loop ----------------------------------------------------
    async def _async_tick(self, _now: Any) -> None:
        controller = self.controller
        if self._busy or not self.active or controller is None:
            return
        if not self.coordinator.last_update_success or not self.coordinator.data:
            self._portal_problem = "AlphaESS-Portal nicht erreichbar"
            self._notify()
            return
        self._portal_problem = None
        wallbox = self._wallbox_state()
        measurement = self._read_measurement(controller.settings.sensor_stale_seconds)
        command = controller.update(time.monotonic(), measurement, wallbox)
        if command is not None:
            previous = controller.current_stage(wallbox)
            self._busy = True
            success = False
            try:
                await self._async_send(command, wallbox)
                success = True
                target = command.stage.label if command.stage else "Modus 1 (Überschuss)"
                self._record(f"{target}: {command.reason}")
            except (AuthenticationError, PortalConnectionError, ValueError) as err:
                _LOGGER.warning("Modus 5: Wallbox-Befehl fehlgeschlagen: %s", err)
                self._record(f"Befehl fehlgeschlagen: {err}")
            finally:
                self._busy = False
            if self.controller is controller:
                controller.command_finished(time.monotonic(), command, previous, success)
            self._notify(force=True)
            return
        self._notify()

    async def _async_send(self, command: Command, wallbox: WallboxState) -> None:
        api = self.coordinator.api
        stage = command.stage
        if stage is None:
            await api.async_update_wallbox_settings(charge_mode=MODE_SURPLUS)
            return
        changes: dict[str, int] = {}
        if wallbox.mode != MODE_CUSTOM:
            changes["charge_mode"] = MODE_CUSTOM
        if wallbox.phases != stage.phases:
            changes["obc_phase"] = stage.phases
        if wallbox.current != stage.current:
            changes["charge_current"] = stage.current
        if changes:
            await api.async_update_wallbox_settings(**changes)

    # -- presentation ----------------------------------------------------
    def status(self) -> str:
        if not self.active:
            return "Aus"
        if self._portal_problem:
            return self._portal_problem
        return self.controller.state if self.controller else "Startet"

    def attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "Letzte Aktion": self.last_action,
            "Zeitpunkt letzte Aktion": (
                self.last_action_at.isoformat() if self.last_action_at else None
            ),
        }
        controller = self.controller
        if not self.active or controller is None:
            return attrs
        current = controller.current_stage(self._wallbox_state())
        attrs.update(
            {
                "Fahrzeugprofil": self.profile_name,
                "Regelungsart": STRATEGY_NAMES.get(
                    controller.settings.strategy, "Stufenregelung"
                ),
                "Grund": controller.reason,
                "Aktuelle Stufe": current.label if current else "Modus 1 (Überschuss)",
                "Zielstufe": controller.target.label if controller.target else None,
                "Mittelungszeitraum (s)": int(controller.window_seconds),
                "SOC-Schutz aktiv": controller.soc_lock,
                "Fallback aktiv": controller.fallback,
                "Erwartete Hauslast (W)": (
                    round(controller.expected_house_w)
                    if controller.expected_house_w is not None
                    else None
                ),
                "Reaktion erkannt nach (s)": (
                    round(controller.reaction_seconds)
                    if controller.reaction_seconds is not None
                    else None
                ),
            }
        )
        if controller.available_w is not None and controller.averages:
            attrs.update(
                {
                    "Verfügbar für Wallbox Ø (W)": round(controller.available_w),
                    "Ladebudget inkl. zulässigem Defizit (W)": round(
                        controller.available_w + controller.settings.allowed_grid_import_w
                    ),
                    "PV Ø (W)": round(controller.averages["pv"]),
                    "Hauslast Ø (W)": round(controller.averages["house"]),
                    "Netz Ø (W)": round(controller.averages["grid"]),
                    "Wallbox geschätzt Ø (W)": round(controller.averages["wallbox"]),
                }
            )
        return attrs
