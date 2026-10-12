"""Tests for supported AlphaESS cloud polling intervals."""
from __future__ import annotations

import runpy
from pathlib import Path
import unittest


CONSTANTS_FILE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "alphaess_portal_bridge"
    / "const.py"
)
CONSTANTS = runpy.run_path(str(CONSTANTS_FILE))


class UpdateIntervalTests(unittest.TestCase):
    def test_every_whole_second_from_five_to_three_hundred_is_allowed(self):
        options = CONSTANTS["UPDATE_INTERVAL_OPTIONS"]
        self.assertEqual(options, tuple(range(5, 301)))
        self.assertEqual(CONSTANTS["UPDATE_INTERVAL_MIN_SECONDS"], 5)
        self.assertEqual(CONSTANTS["UPDATE_INTERVAL_MAX_SECONDS"], 300)
        self.assertEqual(CONSTANTS["UPDATE_INTERVAL_STEP_SECONDS"], 1)

    def test_model_defaults_remain_allowed(self):
        options = CONSTANTS["UPDATE_INTERVAL_OPTIONS"]
        self.assertIn(CONSTANTS["DEFAULT_G2T_UPDATE_INTERVAL_SECONDS"], options)
        self.assertIn(CONSTANTS["DEFAULT_UPDATE_INTERVAL_SECONDS"], options)


if __name__ == "__main__":
    unittest.main()
