"""Number entities for AlphaESS Wallbox Bridge."""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfElectricCurrent, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import AuthenticationError, PortalConnectionError
from .const import CONF_ALLOWED_DEFICIT, CONTROL_NUMBER_SETTINGS, DOMAIN
from .coordinator import AlphaESSWallboxCoordinator
from .entity import AlphaESSWallboxEntity, time_period


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: AlphaESSWallboxCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            AlphaESSWallboxChargeCurrentNumber(coordinator, entry),
            AlphaESSHouseholdCurrentNumber(coordinator, entry),
            *(AlphaESSTimePeriodCurrentNumber(coordinator, entry, index) for index in range(3)),
            AlphaESSAllowedDeficitNumber(coordinator, entry),
        ]
    )


class AlphaESSAllowedDeficitNumber(AlphaESSWallboxEntity, NumberEntity):
    """Mode 5: power by which charging may exceed the PV surplus."""

    _attr_name = "Zulässiges Defizit"
    _attr_icon = "mdi:transmission-tower-import"
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AlphaESSWallboxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "pv_allowed_deficit")
        _, minimum, maximum, step, _ = CONTROL_NUMBER_SETTINGS[CONF_ALLOWED_DEFICIT]
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.pv_mode.add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """A local setting that does not depend on the portal."""
        return True

    @property
    def native_value(self) -> float:
        return self.coordinator.pv_mode.allowed_deficit()

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {
            "Hinweis": (
                "Modus 5 rechnet mit PV-Überschuss + diesem Wert (Starten, "
                "Erhöhen, Senken). Gedeckt aus Hausakku oder Netz. 0 = nur "
                "PV-Überschuss. Wirkt sofort ohne Neustart der Regelung; "
                "entspricht der gleichnamigen Integrationsoption."
            )
        }

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.pv_mode.set_allowed_deficit(value)
        self.async_write_ha_state()


class _CurrentNumberBase(AlphaESSWallboxEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 6
    _attr_native_max_value = 16
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_entity_category = EntityCategory.CONFIG


class AlphaESSWallboxChargeCurrentNumber(_CurrentNumberBase):
    """Set the requested charging current in any charging mode."""

    _attr_name = "Ladestrom (kundenspezifisch)"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: AlphaESSWallboxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "custom_charge_current")

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {
            "Hinweis": (
                "Dies ist der vom AlphaESS-Portal gemeldete Soll-Ladestrom. "
                "Die Eingabe ist in allen Lademodi verfügbar und wechselt den "
                "Lademodus nicht. "
                "Eine erfolgreiche API-Antwort oder geänderte Anzeige bestätigt "
                "noch keine physisch erfolgte Ladeleistungsänderung. "
                "Für den tatsächlichen Ladezustand die Live-Leistung prüfen."
            )
        }

    @property
    def native_value(self) -> float | None:
        value = self.settings.get("chargeCurrent")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.api.async_update_wallbox_settings(charge_current=int(value))
        except (AuthenticationError, PortalConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err) or "Der Ladestrom wurde nicht übernommen") from err
        await self.coordinator.async_request_refresh()


class AlphaESSHouseholdCurrentNumber(AlphaESSWallboxEntity, NumberEntity):
    """Set the installation/household current limit exposed by AlphaESS."""

    _attr_name = "Hausstrom-Einstellung"
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 25
    _attr_native_max_value = 1000
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: AlphaESSWallboxCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "household_current")

    @property
    def native_value(self) -> float | None:
        # houseHoldCurrent is part of the wallbox object inside the full
        # configuration document (not a top-level coordinator key).  Reuse
        # the same resolver as the diagnostic sensors so the value is shown
        # immediately after every refresh.
        value = self.wallbox.get("houseHoldCurrent")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.api.async_update_wallbox_settings(
                household_current=int(value)
            )
        except (AuthenticationError, PortalConnectionError, ValueError) as err:
            raise HomeAssistantError(
                str(err) or "Die Hausstrom-Einstellung wurde nicht übernommen"
            ) from err
        await self.coordinator.async_request_refresh()


class AlphaESSTimePeriodCurrentNumber(_CurrentNumberBase):
    """Custom current for one G2T schedule period."""

    def __init__(
        self, coordinator: AlphaESSWallboxCoordinator, entry: ConfigEntry, index: int
    ) -> None:
        super().__init__(coordinator, entry, f"time_period_{index + 1}_current")
        self._index = index
        self._attr_name = f"Zeitrahmen {index + 1} Maximaler Strom"

    @property
    def available(self) -> bool:
        period = time_period(self.coordinator, self._index)
        return (
            super().available
            and self.settings_generation == "g2T"
            and bool(period)
            and period.get("chargeMode") == 4
        )

    @property
    def native_value(self) -> float | None:
        value = time_period(self.coordinator, self._index).get("chargeCurrent")
        return float(value) if isinstance(value, (int, float)) else None

    async def async_set_native_value(self, value: float) -> None:
        if time_period(self.coordinator, self._index).get("chargeMode") != 4:
            raise HomeAssistantError(
                "Wähle für diesen Zeitrahmen zuerst Benutzerdefinierte Ladeleistung"
            )
        try:
            await self.coordinator.api.async_update_time_period(
                self._index, charge_current=int(value)
            )
        except (AuthenticationError, PortalConnectionError, ValueError) as err:
            raise HomeAssistantError(str(err) or "Der Ladestrom wurde nicht übernommen") from err
        await self.coordinator.async_request_refresh()
