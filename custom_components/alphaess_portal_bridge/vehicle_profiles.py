"""Vehicle charging profiles for the planned PV self-consumption mode."""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------
from __future__ import annotations

import copy
from typing import Any, Mapping

PROFILE_NAME = "name"
PROFILE_POWER_1P = "power_1p"
PROFILE_POWER_3P = "power_3p"
PROFILE_UNSTABLE_STAGES = "unstable_stages"
PROFILE_EXCLUDED_STAGES = "excluded_stages"

PHASES = (1, 3)
CURRENTS = tuple(range(6, 16))
POWER_KEYS = {1: PROFILE_POWER_1P, 3: PROFILE_POWER_3P}
MAX_POWER_W = {1: 4000, 3: 12000}

DEFAULT_VEHICLE_PROFILE_ID = "standard"
# Theoretical nominal power ratings (230 V per phase: 1p = A * 230 W, 3p = A * 690 W).
DEFAULT_VEHICLE_PROFILE: dict[str, Any] = {
    PROFILE_NAME: "Standardfahrzeug",
    PROFILE_POWER_1P: {
        "6": 1380, "7": 1610, "8": 1840, "9": 2070, "10": 2300,
        "11": 2530, "12": 2760, "13": 2990, "14": 3220, "15": 3450,
    },
    PROFILE_POWER_3P: {
        "6": 4140, "7": 4830, "8": 5520, "9": 6210, "10": 6900,
        "11": 7590, "12": 8280, "13": 8970, "14": 9660, "15": 10350,
    },
    PROFILE_UNSTABLE_STAGES: [],
    PROFILE_EXCLUDED_STAGES: [],
}


def stage_key(phases: int, current: int) -> str:
    """Return the storage key of one phase/current combination."""
    return f"{phases}_{current}"


STAGE_KEYS = tuple(stage_key(p, a) for p in PHASES for a in CURRENTS)


def stage_label(key: str) -> str:
    """Return a short language-neutral label such as ``3-ph 7 A``."""
    phases, current = key.split("_")
    return f"{phases}-ph {current} A"


def get_profiles(options: Mapping[str, Any], profiles_key: str) -> dict[str, dict[str, Any]]:
    """Return saved profiles or the measured default profile."""
    profiles = options.get(profiles_key)
    if isinstance(profiles, Mapping) and profiles:
        return copy.deepcopy(dict(profiles))
    return {DEFAULT_VEHICLE_PROFILE_ID: copy.deepcopy(DEFAULT_VEHICLE_PROFILE)}


def normalize_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Convert form input into the stored profile representation."""
    normalized: dict[str, Any] = {
        PROFILE_NAME: str(profile.get(PROFILE_NAME, "")).strip(),
    }
    for phases, power_key in POWER_KEYS.items():
        values = profile.get(power_key, {})
        normalized[power_key] = {
            str(current): int(round(float(values[str(current)])))
            for current in CURRENTS
            if values.get(str(current)) is not None
        }
    for list_key in (PROFILE_UNSTABLE_STAGES, PROFILE_EXCLUDED_STAGES):
        normalized[list_key] = [
            key for key in STAGE_KEYS if key in set(profile.get(list_key) or [])
        ]
    return normalized


def validate_profile(
    profile: Mapping[str, Any],
    other_names: list[str] | tuple[str, ...] = (),
) -> str | None:
    """Return a translation error key, or None if the profile is usable."""
    name = profile.get(PROFILE_NAME, "")
    if not name:
        return "name_required"
    if name.casefold() in {other.casefold() for other in other_names}:
        return "name_duplicate"
    for phases, power_key in POWER_KEYS.items():
        values = profile.get(power_key, {})
        powers = [values.get(str(current)) for current in CURRENTS]
        if any(power is None or power <= 0 or power > MAX_POWER_W[phases] for power in powers):
            return "power_invalid"
        if any(later < earlier for earlier, later in zip(powers, powers[1:])):
            return "power_not_increasing"
    unstable = set(profile.get(PROFILE_UNSTABLE_STAGES, []))
    excluded = set(profile.get(PROFILE_EXCLUDED_STAGES, []))
    if unstable & excluded:
        return "stage_conflict"
    if excluded >= set(STAGE_KEYS):
        return "no_usable_stage"
    return None
