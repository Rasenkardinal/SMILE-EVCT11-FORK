"""Config flow for AlphaESS Portal Bridge."""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------
from __future__ import annotations

import copy
from typing import Any
from uuid import uuid4

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult, section
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .api import AlphaESSPortalApi, AuthenticationError, PortalConnectionError
from .const import (
    CONF_ACTIVE_VEHICLE_PROFILE,
    CONF_BATTERY_POWER_ENTITY,
    CONF_BATTERY_SOC_ENTITY,
    CONF_CONTROL_STRATEGY,
    CONF_GRID_POWER_ENTITY,
    CONF_HOUSEHOLD_POWER_ENTITY,
    CONF_PASSWORD,
    CONF_PV_POWER_ENTITY,
    CONF_SYSTEM_SERIAL,
    CONF_UPDATE_INTERVAL,
    CONF_USERNAME,
    CONF_VEHICLE_PROFILES,
    CONF_WALLBOX_SERIAL,
    CONTROL_NUMBER_SETTINGS,
    CONTROL_STRATEGIES,
    DEFAULT_CONTROL_STRATEGY,
    DEFAULT_G2T_UPDATE_INTERVAL_SECONDS,
    DEFAULT_UPDATE_INTERVAL_SECONDS,
    DOMAIN,
    UPDATE_INTERVAL_OPTIONS,
    UPDATE_INTERVAL_STEP_SECONDS,
)
from .vehicle_profiles import (
    CURRENTS,
    DEFAULT_VEHICLE_PROFILE,
    MAX_POWER_W,
    POWER_KEYS,
    PROFILE_EXCLUDED_STAGES,
    PROFILE_NAME,
    PROFILE_UNSTABLE_STAGES,
    STAGE_KEYS,
    get_profiles,
    normalize_profile,
    stage_label,
    validate_profile,
)


class AlphaESSPortalBridgeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Set up the bridge through the current AlphaESS portal session API."""

    VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> AlphaESSPortalBridgeOptionsFlow:
        """Return the editable integration options."""
        return AlphaESSPortalBridgeOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] | None = None
        if user_input is not None:
            user_input = dict(user_input)
            user_input[CONF_SYSTEM_SERIAL] = user_input[CONF_SYSTEM_SERIAL].strip().upper()
            if user_input.get(CONF_WALLBOX_SERIAL):
                user_input[CONF_WALLBOX_SERIAL] = user_input[CONF_WALLBOX_SERIAL].strip().upper()
            else:
                user_input.pop(CONF_WALLBOX_SERIAL, None)
            await self.async_set_unique_id(user_input[CONF_SYSTEM_SERIAL])
            self._abort_if_unique_id_configured()
            api = AlphaESSPortalApi(self.hass, user_input)
            try:
                await api.async_validate_login()
            except AuthenticationError as err:
                errors["base"] = (
                    "session_rejected"
                    if err.step == "session validation"
                    else "system_access_denied"
                    if err.step == "system check"
                    else "invalid_auth"
                )
            except PortalConnectionError as err:
                if err.status is None:
                    errors["base"] = "cannot_connect"
                else:
                    errors["base"] = "portal_status"
                    description_placeholders = {"step": err.step, "status": str(err.status)}
            else:
                return self.async_create_entry(
                    title=f"AlphaESS Wallbox {user_input[CONF_SYSTEM_SERIAL]}",
                    data=user_input,
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_SYSTEM_SERIAL): str,
                vol.Optional(CONF_WALLBOX_SERIAL): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add or replace the wallbox serial on an existing connection."""
        entry = self._get_reconfigure_entry()
        if user_input is not None:
            wallbox_serial = user_input[CONF_WALLBOX_SERIAL].strip().upper()
            self.hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_WALLBOX_SERIAL: wallbox_serial},
                title=f"AlphaESS Wallbox {entry.data[CONF_SYSTEM_SERIAL]}",
            )
            await self.hass.config_entries.async_reload(entry.entry_id)
            return self.async_abort(reason="reconfigure_successful")

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({vol.Required(CONF_WALLBOX_SERIAL): str}),
        )


def _default_update_interval(hass: Any, entry: config_entries.ConfigEntry) -> int:
    """Choose the model-specific default when no interval has been saved."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    generation = AlphaESSPortalApi.wallbox_generation(
        getattr(coordinator, "data", None)
    )
    if generation == "g2T":
        return DEFAULT_G2T_UPDATE_INTERVAL_SECONDS
    return DEFAULT_UPDATE_INTERVAL_SECONDS


class AlphaESSPortalBridgeOptionsFlow(config_entries.OptionsFlowWithReload):
    """Configure refresh interval, monitoring sensors, control and vehicles."""

    _edit_profile_id: str | None = None

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "control", "vehicles"],
        )

    def _save(self, updates: dict[str, Any]) -> FlowResult:
        options = dict(self.config_entry.options)
        options.update(updates)
        return self.async_create_entry(title="", data=options)

    async def async_step_general(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self._save(user_input)

        current_interval = self.config_entry.options.get(CONF_UPDATE_INTERVAL)
        if current_interval not in UPDATE_INTERVAL_OPTIONS:
            current_interval = _default_update_interval(self.hass, self.config_entry)
        current_options = self.config_entry.options
        sensor_entities = (
            CONF_PV_POWER_ENTITY,
            CONF_BATTERY_SOC_ENTITY,
            CONF_HOUSEHOLD_POWER_ENTITY,
            CONF_GRID_POWER_ENTITY,
            CONF_BATTERY_POWER_ENTITY,
        )
        schema: dict[Any, Any] = {
            vol.Required(
                CONF_UPDATE_INTERVAL,
                default=current_interval,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=min(UPDATE_INTERVAL_OPTIONS),
                    max=max(UPDATE_INTERVAL_OPTIONS),
                    step=UPDATE_INTERVAL_STEP_SECONDS,
                    unit_of_measurement="s",
                    mode=NumberSelectorMode.BOX,
                )
            ),
        }
        for entity_key in sensor_entities:
            saved_entity = current_options.get(entity_key)
            field = (
                vol.Optional(entity_key, default=saved_entity)
                if saved_entity
                else vol.Optional(entity_key)
            )
            schema[field] = EntitySelector(EntitySelectorConfig(domain="sensor"))

        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(schema),
        )

    def _profiles(self) -> dict[str, dict[str, Any]]:
        return get_profiles(self.config_entry.options, CONF_VEHICLE_PROFILES)

    def _profile_selector(self) -> SelectSelector:
        return SelectSelector(
            SelectSelectorConfig(
                options=[
                    SelectOptionDict(value=profile_id, label=profile[PROFILE_NAME])
                    for profile_id, profile in self._profiles().items()
                ],
                mode=SelectSelectorMode.DROPDOWN,
            )
        )

    async def async_step_control(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        options = self.config_entry.options
        profiles = self._profiles()
        if user_input is not None:
            updates = dict(user_input)
            for key in CONTROL_NUMBER_SETTINGS:
                updates[key] = int(updates[key])
            if CONF_VEHICLE_PROFILES not in options:
                updates[CONF_VEHICLE_PROFILES] = profiles
            return self._save(updates)

        active = options.get(CONF_ACTIVE_VEHICLE_PROFILE)
        if active not in profiles:
            active = next(iter(profiles))
        schema: dict[Any, Any] = {
            vol.Required(CONF_ACTIVE_VEHICLE_PROFILE, default=active): self._profile_selector(),
            vol.Required(
                CONF_CONTROL_STRATEGY,
                default=options.get(CONF_CONTROL_STRATEGY, DEFAULT_CONTROL_STRATEGY),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(CONTROL_STRATEGIES),
                    translation_key=CONF_CONTROL_STRATEGY,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
        for key, (default, minimum, maximum, step, unit) in CONTROL_NUMBER_SETTINGS.items():
            schema[vol.Required(key, default=options.get(key, default))] = NumberSelector(
                NumberSelectorConfig(
                    min=minimum,
                    max=maximum,
                    step=step,
                    unit_of_measurement=unit,
                    mode=NumberSelectorMode.BOX,
                )
            )
        return self.async_show_form(step_id="control", data_schema=vol.Schema(schema))

    async def async_step_vehicles(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return self.async_show_menu(
            step_id="vehicles",
            menu_options=["vehicle_add", "vehicle_select", "vehicle_delete"],
        )

    def _profile_schema(self, profile: dict[str, Any]) -> vol.Schema:
        stage_options = [SelectOptionDict(value=key, label=stage_label(key)) for key in STAGE_KEYS]
        schema: dict[Any, Any] = {
            vol.Required(PROFILE_NAME, default=profile.get(PROFILE_NAME, "")): TextSelector(),
        }
        for phases, power_key in POWER_KEYS.items():
            values = profile.get(power_key, {})
            fields = {
                vol.Required(
                    f"current_{current}",
                    **(
                        {"default": values[str(current)]}
                        if values.get(str(current)) is not None
                        else {}
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=0,
                        max=MAX_POWER_W[phases],
                        step=10,
                        unit_of_measurement="W",
                        mode=NumberSelectorMode.BOX,
                    )
                )
                for current in CURRENTS
            }
            schema[vol.Required(power_key)] = section(vol.Schema(fields), {"collapsed": False})
        for list_key in (PROFILE_UNSTABLE_STAGES, PROFILE_EXCLUDED_STAGES):
            schema[vol.Optional(list_key, default=list(profile.get(list_key, [])))] = SelectSelector(
                SelectSelectorConfig(
                    options=stage_options,
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            )
        return vol.Schema(schema)

    @staticmethod
    def _profile_from_input(user_input: dict[str, Any]) -> dict[str, Any]:
        raw = dict(user_input)
        for power_key in POWER_KEYS.values():
            raw[power_key] = {
                str(current): value
                for current in CURRENTS
                if (value := user_input.get(power_key, {}).get(f"current_{current}")) is not None
            }
        return normalize_profile(raw)

    async def _profile_form(
        self, step_id: str, profile_id: str | None, user_input: dict[str, Any] | None
    ) -> FlowResult:
        profiles = self._profiles()
        errors: dict[str, str] = {}
        if user_input is not None:
            profile = self._profile_from_input(user_input)
            other_names = [
                p[PROFILE_NAME] for pid, p in profiles.items() if pid != profile_id
            ]
            error = validate_profile(profile, other_names)
            if error is None:
                profiles[profile_id or uuid4().hex[:8]] = profile
                updates: dict[str, Any] = {CONF_VEHICLE_PROFILES: profiles}
                if self.config_entry.options.get(CONF_ACTIVE_VEHICLE_PROFILE) not in profiles:
                    updates[CONF_ACTIVE_VEHICLE_PROFILE] = next(iter(profiles))
                return self._save(updates)
            errors["base"] = error
            shown = profile
        elif profile_id is None:
            shown = {**copy.deepcopy(DEFAULT_VEHICLE_PROFILE), PROFILE_NAME: ""}
        else:
            shown = profiles[profile_id]
        return self.async_show_form(
            step_id=step_id,
            data_schema=self._profile_schema(shown),
            errors=errors,
        )

    async def async_step_vehicle_add(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self._profile_form("vehicle_add", None, user_input)

    async def async_step_vehicle_select(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            self._edit_profile_id = user_input["profile"]
            return await self.async_step_vehicle_edit()
        return self.async_show_form(
            step_id="vehicle_select",
            data_schema=vol.Schema({vol.Required("profile"): self._profile_selector()}),
        )

    async def async_step_vehicle_edit(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if self._edit_profile_id not in self._profiles():
            return await self.async_step_vehicle_select()
        return await self._profile_form("vehicle_edit", self._edit_profile_id, user_input)

    async def async_step_vehicle_delete(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        profiles = self._profiles()
        errors: dict[str, str] = {}
        if user_input is not None:
            if len(profiles) <= 1:
                errors["base"] = "last_profile"
            else:
                profiles.pop(user_input["profile"], None)
                updates: dict[str, Any] = {CONF_VEHICLE_PROFILES: profiles}
                if self.config_entry.options.get(CONF_ACTIVE_VEHICLE_PROFILE) not in profiles:
                    updates[CONF_ACTIVE_VEHICLE_PROFILE] = next(iter(profiles))
                return self._save(updates)
        return self.async_show_form(
            step_id="vehicle_delete",
            data_schema=vol.Schema({vol.Required("profile"): self._profile_selector()}),
            errors=errors,
        )
