"""Checks for vehicle profiles and PV control option defaults."""
from __future__ import annotations

import json
from pathlib import Path
import re
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "alphaess_portal_bridge"
CONSTANTS = runpy.run_path(str(COMPONENT / "const.py"))
PROFILES = runpy.run_path(str(COMPONENT / "vehicle_profiles.py"))
TRANSLATION_FILES = ("strings.json", "translations/en.json", "translations/de.json")

MEASURED_1P = [1420, 1640, 1840, 2075, 2250, 2480, 2720, 2960, 3170, 3400]
MEASURED_3P = [2990, 3440, 5540, 6260, 6960, 7550, 8280, 9000, 9650, 10350]


def profile(**changes):
    result = PROFILES["normalize_profile"](PROFILES["DEFAULT_VEHICLE_PROFILE"])
    result.update(changes)
    return result


class VehicleProfileTests(unittest.TestCase):
    def test_default_profile_uses_stable_measured_values(self):
        default = PROFILES["DEFAULT_VEHICLE_PROFILE"]
        currents = [str(a) for a in range(6, 16)]
        self.assertEqual([default["power_1p"][a] for a in currents], MEASURED_1P)
        self.assertEqual([default["power_3p"][a] for a in currents], MEASURED_3P)

    def test_three_phase_seven_amps_is_allowed_but_unstable(self):
        default = PROFILES["DEFAULT_VEHICLE_PROFILE"]
        self.assertEqual(default["unstable_stages"], ["3_7"])
        self.assertEqual(default["excluded_stages"], [])

    def test_default_profile_is_valid(self):
        self.assertIsNone(PROFILES["validate_profile"](profile()))

    def test_validation_errors(self):
        validate = PROFILES["validate_profile"]
        power_3p = dict(profile()["power_3p"], **{"8": 3000})
        cases = {
            "name_required": (profile(name=""), ()),
            "name_duplicate": (profile(), ("standardfahrzeug",)),
            "power_invalid": (profile(power_1p={**profile()["power_1p"], "6": 0}), ()),
            "power_not_increasing": (profile(power_3p=power_3p), ()),
            "stage_conflict": (profile(excluded_stages=["3_7"]), ()),
            "no_usable_stage": (
                profile(unstable_stages=[], excluded_stages=list(PROFILES["STAGE_KEYS"])),
                (),
            ),
        }
        for error, (candidate, names) in cases.items():
            with self.subTest(error=error):
                self.assertEqual(validate(candidate, names), error)

    def test_normalize_converts_form_numbers_and_orders_stages(self):
        raw = {
            "name": "  Testauto ",
            "power_1p": {str(a): float(a * 230) for a in range(6, 16)},
            "power_3p": {str(a): float(a * 690) for a in range(6, 16)},
            "unstable_stages": ["3_9", "1_6", "unknown"],
            "excluded_stages": None,
        }
        normalized = PROFILES["normalize_profile"](raw)
        self.assertEqual(normalized["name"], "Testauto")
        self.assertEqual(normalized["power_1p"]["6"], 1380)
        self.assertIsInstance(normalized["power_3p"]["15"], int)
        self.assertEqual(normalized["unstable_stages"], ["1_6", "3_9"])
        self.assertEqual(normalized["excluded_stages"], [])

    def test_missing_profiles_fall_back_to_independent_default_copy(self):
        get_profiles = PROFILES["get_profiles"]
        profiles = get_profiles({}, "vehicle_profiles")
        self.assertEqual(list(profiles), [PROFILES["DEFAULT_VEHICLE_PROFILE_ID"]])
        profiles["standard"]["power_3p"]["7"] = 1
        self.assertEqual(PROFILES["DEFAULT_VEHICLE_PROFILE"]["power_3p"]["7"], 3440)
        saved = {"abc": profile(name="Saved")}
        self.assertEqual(get_profiles({"vehicle_profiles": saved}, "vehicle_profiles"), saved)


class ControlSettingTests(unittest.TestCase):
    def test_defaults_lie_on_allowed_steps(self):
        for key, (default, minimum, maximum, step, _unit) in CONSTANTS["CONTROL_NUMBER_SETTINGS"].items():
            with self.subTest(key=key):
                self.assertTrue(minimum <= default <= maximum)
                self.assertEqual((default - minimum) % step, 0)

    def test_measured_defaults(self):
        settings = CONSTANTS["CONTROL_NUMBER_SETTINGS"]
        self.assertEqual(settings["average_window_seconds"][0], 120)
        self.assertEqual(settings["unstable_average_window_seconds"][0], 240)
        self.assertEqual(settings["current_change_wait_seconds"][0], 60)
        self.assertEqual(settings["phase_change_wait_seconds"][0], 90)
        self.assertEqual(settings["sensor_stale_seconds"][0], 10)
        self.assertEqual(settings["sensor_recovery_seconds"][0], 30)
        self.assertEqual(CONSTANTS["DEFAULT_CONTROL_STRATEGY"], "step")


class OptionsTranslationTests(unittest.TestCase):
    def setUp(self):
        self.flow_source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        self.translations = {
            name: json.loads((COMPONENT / name).read_text(encoding="utf-8"))
            for name in TRANSLATION_FILES
        }

    def test_every_translated_step_has_a_flow_method(self):
        for name, data in self.translations.items():
            for step_id in data["options"]["step"]:
                with self.subTest(file=name, step=step_id):
                    self.assertIn(f"async def async_step_{step_id}(", self.flow_source)

    def test_menu_options_are_translated(self):
        menus = {
            step: re.findall(r'"(\w+)"', options)
            for step, options in re.findall(
                r'step_id="(\w+)",\s*menu_options=\[([^\]]*)\]', self.flow_source
            )
        }
        self.assertEqual(set(menus), {"init", "vehicles"})
        for name, data in self.translations.items():
            for step, options in menus.items():
                with self.subTest(file=name, step=step):
                    self.assertEqual(
                        set(data["options"]["step"][step]["menu_options"]), set(options)
                    )

    def test_control_and_vehicle_fields_are_translated(self):
        control_keys = set(CONSTANTS["CONTROL_NUMBER_SETTINGS"]) | {
            "active_vehicle_profile",
            "control_strategy",
        }
        for name, data in self.translations.items():
            steps = data["options"]["step"]
            with self.subTest(file=name):
                self.assertEqual(set(steps["control"]["data"]), control_keys)
                self.assertEqual(
                    set(data["selector"]["control_strategy"]["options"]),
                    set(CONSTANTS["CONTROL_STRATEGIES"]),
                )
                for step in ("vehicle_add", "vehicle_edit"):
                    self.assertEqual(
                        set(steps[step]["data"]),
                        {"name", "unstable_stages", "excluded_stages"},
                    )
                    for section in ("power_1p", "power_3p"):
                        self.assertEqual(
                            set(steps[step]["sections"][section]["data"]),
                            {f"current_{a}" for a in range(6, 16)},
                        )

    def test_flow_errors_are_translated(self):
        validate_source = (COMPONENT / "vehicle_profiles.py").read_text(encoding="utf-8")
        errors = set(re.findall(r'return "(\w+)"', validate_source)) | {"last_profile"}
        for name, data in self.translations.items():
            with self.subTest(file=name):
                self.assertTrue(errors <= set(data["options"]["error"]))


if __name__ == "__main__":
    unittest.main()
