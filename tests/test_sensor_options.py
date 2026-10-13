"""Regression checks for selectable local monitoring sensors."""
from __future__ import annotations

import json
from pathlib import Path
import runpy
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "alphaess_portal_bridge"
CONSTANTS = runpy.run_path(str(COMPONENT / "const.py"))
SENSOR_OPTION_KEYS = (
    "CONF_PV_POWER_ENTITY",
    "CONF_BATTERY_SOC_ENTITY",
    "CONF_HOUSEHOLD_POWER_ENTITY",
    "CONF_GRID_POWER_ENTITY",
    "CONF_BATTERY_POWER_ENTITY",
)


class SensorOptionsTests(unittest.TestCase):
    def test_sensor_option_keys_are_saved_in_the_options_flow(self):
        source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
        for name in SENSOR_OPTION_KEYS:
            with self.subTest(name=name):
                self.assertIn(name, source)
                self.assertIn(name, CONSTANTS)

    def test_sensor_options_are_translated(self):
        for filename in ("strings.json", "translations/en.json"):
            with self.subTest(filename=filename):
                translations = json.loads(
                    (COMPONENT / filename).read_text(encoding="utf-8")
                )
                options = translations["options"]["step"]["general"]["data"]
                for name in SENSOR_OPTION_KEYS:
                    self.assertIn(CONSTANTS[name], options)

    def test_wallbox_power_is_an_integration_sensor_not_an_option(self):
        source = (COMPONENT / "sensor.py").read_text(encoding="utf-8")
        self.assertIn('super().__init__(coordinator, entry, "power")', source)
        self.assertNotIn("wallbox_power_entity", source)


if __name__ == "__main__":
    unittest.main()
