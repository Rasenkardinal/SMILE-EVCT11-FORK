"""Constants for the AlphaESS Portal Bridge."""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------

DOMAIN = "alphaess_portal_bridge"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_SYSTEM_SERIAL = "system_serial"
CONF_WALLBOX_SERIAL = "wallbox_serial"
CONF_UPDATE_INTERVAL = "update_interval_seconds"
CONF_PV_POWER_ENTITY = "pv_power_entity"
CONF_BATTERY_SOC_ENTITY = "battery_soc_entity"
CONF_HOUSEHOLD_POWER_ENTITY = "household_power_entity"
CONF_GRID_POWER_ENTITY = "grid_power_entity"
CONF_BATTERY_POWER_ENTITY = "battery_power_entity"
CONF_VEHICLE_PROFILES = "vehicle_profiles"
CONF_ACTIVE_VEHICLE_PROFILE = "active_vehicle_profile"
CONF_CONTROL_STRATEGY = "control_strategy"
CONTROL_STRATEGY_STEP = "step"
CONTROL_STRATEGY_DIRECT = "direct"
CONTROL_STRATEGIES = (CONTROL_STRATEGY_STEP, CONTROL_STRATEGY_DIRECT)

# Settings for HA charging mode 5, keyed by option name:
# (default, minimum, maximum, step, unit). Defaults are derived from the
# measurement cycle of 2026-10-13 or proposed in docs/modus-5-...-design.md.
CONTROL_NUMBER_SETTINGS: dict[str, tuple[int, int, int, int, str]] = {
    "average_window_seconds": (120, 30, 900, 10, "s"),
    "unstable_average_window_seconds": (240, 60, 1800, 10, "s"),
    "current_change_wait_seconds": (60, 30, 600, 5, "s"),
    "phase_change_wait_seconds": (90, 30, 600, 5, "s"),
    "grid_import_limit_w": (200, 0, 5000, 50, "W"),
    "grid_import_protection_seconds": (30, 10, 300, 5, "s"),
    "reaction_confirm_seconds": (10, 0, 60, 5, "s"),
    "surplus_reserve_w": (200, 0, 3000, 50, "W"),
    "min_battery_soc": (20, 0, 100, 1, "%"),
    "battery_soc_hysteresis": (5, 1, 50, 1, "%"),
    "sensor_stale_seconds": (10, 5, 120, 1, "s"),
    "sensor_recovery_seconds": (30, 10, 600, 5, "s"),
}
DEFAULT_CONTROL_STRATEGY = CONTROL_STRATEGY_STEP
# Persisted user intent "HA mode 5 active"; kept separate from the AlphaESS
# mode actually written to the portal so fallbacks can return automatically.
CONF_PV_MODE_ACTIVE = "pv_mode_active"
PV_MODE_OPTION = "PV-Eigenverbrauch (Modus 5)"
DEFAULT_UPDATE_INTERVAL_SECONDS = 120
DEFAULT_G2T_UPDATE_INTERVAL_SECONDS = 30
UPDATE_INTERVAL_MIN_SECONDS = 5
UPDATE_INTERVAL_MAX_SECONDS = 300
UPDATE_INTERVAL_STEP_SECONDS = 1
UPDATE_INTERVAL_OPTIONS = tuple(
    range(
        UPDATE_INTERVAL_MIN_SECONDS,
        UPDATE_INTERVAL_MAX_SECONDS + 1,
        UPDATE_INTERVAL_STEP_SECONDS,
    )
)
PLATFORM_URL = "https://platform.alphaess.com"
API_URL = f"{PLATFORM_URL}/api"
