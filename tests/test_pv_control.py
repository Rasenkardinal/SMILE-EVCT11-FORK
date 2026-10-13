"""Decision tests for the HA charging mode 5 controller."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import runpy
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "custom_components" / "alphaess_portal_bridge"
CONSTANTS = runpy.run_path(str(COMPONENT / "const.py"))
PROFILES = runpy.run_path(str(COMPONENT / "vehicle_profiles.py"))

_SPEC = importlib.util.spec_from_file_location("pv_control_under_test", COMPONENT / "pv_control.py")
pc = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = pc
_SPEC.loader.exec_module(pc)

PROFILE = PROFILES["normalize_profile"](PROFILES["DEFAULT_VEHICLE_PROFILE"])
P3 = PROFILE["power_3p"]
P1 = PROFILE["power_1p"]


def settings(strategy="direct", **changes):
    options = {"control_strategy": strategy, **changes}
    return pc.ControlSettings.from_options(
        options, CONSTANTS["CONTROL_NUMBER_SETTINGS"], "control_strategy"
    )


def wallbox(mode=4, phases=3, current=6, charging=True, **changes):
    values = dict(
        connected=True,
        charging=charging,
        schedule_active=False,
        mode=mode,
        phases=phases,
        current=current,
        cloud_power=None,
    )
    values.update(changes)
    return pc.WallboxState(**values)


def run(controller, wb, *, pv, house, grid=0.0, soc=60.0, start=0.0, seconds=120):
    """Feed constant samples every 5 s; return (time, first command)."""
    t = start
    while t <= start + seconds:
        command = controller.update(t, pc.Measurement(pv=pv, house=house, grid=grid, soc=soc), wb)
        if command is not None:
            return t, command
        t += pc.SAMPLE_INTERVAL_SECONDS
    return t, None


def house_with_wallbox(stage_power, base=500.0):
    return base + stage_power


class LadderTests(unittest.TestCase):
    def test_single_phase_only_below_smallest_three_phase_stage(self):
        ladder = pc.build_ladder(PROFILE)
        three = [s for s in ladder if s.phases == 3]
        one = [s for s in ladder if s.phases == 1]
        self.assertEqual(len(three), 10)
        self.assertTrue(all(s.power < three[0].power for s in one))
        self.assertEqual(ladder, sorted(ladder, key=lambda s: s.power))
        self.assertEqual(ladder[-1].key, "3_15")

    def test_excluded_stage_is_skipped_and_unstable_flag_kept(self):
        ladder = pc.build_ladder({**PROFILE, "excluded_stages": ["3_8"]})
        keys = [s.key for s in ladder]
        self.assertNotIn("3_8", keys)
        self.assertTrue(next(s for s in ladder if s.key == "3_7").unstable)

    def test_excluding_three_phase_six_amps_extends_single_phase_range(self):
        base = [s.key for s in pc.build_ladder(PROFILE) if s.phases == 1]
        wider = [
            s.key
            for s in pc.build_ladder({**PROFILE, "excluded_stages": ["3_6"]})
            if s.phases == 1
        ]
        self.assertGreater(len(wider), len(base))


class DirectStrategyTests(unittest.TestCase):
    def test_jumps_from_six_to_highest_fitting_stage_in_one_command(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(current=6)
        # 7400 W available for the wallbox: 3-ph 10 A (6960 W) fits with 200 W reserve.
        _, command = run(controller, wb, pv=7900, house=house_with_wallbox(P3["6"]))
        self.assertIsNotNone(command)
        self.assertEqual(command.stage.key, "3_10")

    def test_no_command_before_full_window(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        t, command = run(controller, wallbox(), pv=9000, house=1000, seconds=100)
        self.assertIsNone(command)
        self.assertEqual(controller.state, pc.STATE_AVERAGING)

    def test_deficit_drops_directly_to_fitting_stage(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(current=12)
        # Only about 3000 W available while charging at 3-ph 12 A.
        _, command = run(controller, wb, pv=3600, house=house_with_wallbox(P3["12"], 600))
        self.assertEqual(command.stage.key, "3_6")

    def test_no_surplus_switches_to_mode_one(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        _, command = run(controller, wallbox(current=6), pv=800, house=house_with_wallbox(P3["6"]))
        self.assertIsNotNone(command)
        self.assertIsNone(command.stage)

    def test_mode_one_with_surplus_starts_with_fitting_stage(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(mode=1, charging=False)
        _, command = run(controller, wb, pv=3800, house=500)
        self.assertEqual(command.stage.key, "3_6")

    def test_small_surplus_uses_single_phase(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(mode=1, charging=False)
        _, command = run(controller, wb, pv=2500, house=500)
        self.assertEqual(command.stage.phases, 1)
        self.assertLessEqual(command.stage.power, 1800)

    def test_stays_when_stage_fits(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(current=10)
        _, command = run(controller, wb, pv=7600, house=house_with_wallbox(P3["10"]))
        self.assertIsNone(command)
        self.assertEqual(controller.state, pc.STATE_ACTIVE)


class StepStrategyTests(unittest.TestCase):
    def test_moves_only_one_stage_up(self):
        controller = pc.PVController(PROFILE, settings("step"))
        _, command = run(controller, wallbox(current=6), pv=12000, house=house_with_wallbox(P3["6"]))
        self.assertEqual(command.stage.key, "3_7")

    def test_moves_only_one_stage_down(self):
        controller = pc.PVController(PROFILE, settings("step"))
        _, command = run(controller, wallbox(current=12), pv=3600, house=house_with_wallbox(P3["12"], 600))
        self.assertEqual(command.stage.key, "3_11")


class ProtectionTests(unittest.TestCase):
    def test_grid_import_reacts_after_protection_span(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(current=12)
        t, command = run(
            controller, wb, pv=9000, house=house_with_wallbox(P3["12"]), grid=2000
        )
        self.assertIsNotNone(command)
        self.assertLess(t, 60)
        self.assertGreaterEqual(t, 30)
        self.assertLessEqual(command.stage.power, P3["12"] - 1800)

    def test_grid_import_protection_time_is_configurable(self):
        controller = pc.PVController(
            PROFILE, settings("direct", grid_import_protection_seconds=60)
        )
        t, command = run(
            controller, wallbox(current=12), pv=9000, house=house_with_wallbox(P3["12"]), grid=2000
        )
        self.assertIsNotNone(command)
        self.assertGreaterEqual(t, 60)
        self.assertLess(t, 90)

    def test_grid_import_protection_never_waits_longer_than_window(self):
        controller = pc.PVController(
            PROFILE, settings("direct", grid_import_protection_seconds=300)
        )
        t, command = run(
            controller, wallbox(current=12), pv=9000, house=house_with_wallbox(P3["12"]), grid=2000
        )
        self.assertIsNotNone(command)
        self.assertLessEqual(t, 120)

    def test_soc_lock_and_hysteresis(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        _, command = run(controller, wallbox(current=6), pv=9000, house=1000, soc=19, seconds=5)
        self.assertIsNone(command.stage)
        self.assertTrue(controller.soc_lock)
        mode_one = wallbox(mode=1, charging=False)
        _, command = run(controller, mode_one, pv=9000, house=1000, soc=22, start=10, seconds=200)
        self.assertIsNone(command)
        self.assertTrue(controller.soc_lock)
        _, command = run(controller, mode_one, pv=9000, house=1000, soc=25, start=300)
        self.assertFalse(controller.soc_lock)
        self.assertIsNotNone(command.stage)

    def test_sensor_fault_falls_back_and_recovers_after_delay(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        command = controller.update(0, pc.Measurement(problem="PV nicht verfügbar"), wallbox())
        self.assertIsNone(command.stage)
        self.assertEqual(controller.state, pc.STATE_FALLBACK)
        controller.command_finished(0, command, None, True)
        mode_one = wallbox(mode=1, charging=False)
        valid = pc.Measurement(pv=9000, house=1000, grid=0, soc=60)
        self.assertIsNone(controller.update(100, valid, mode_one))
        self.assertEqual(controller.state, pc.STATE_RECOVERY)
        self.assertIsNone(controller.update(125, valid, mode_one))
        self.assertEqual(controller.state, pc.STATE_RECOVERY)
        controller.update(130, valid, mode_one)
        self.assertFalse(controller.fallback)

    def test_failed_fallback_command_is_retried_after_wait(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        bad = pc.Measurement(problem="Hauslast nicht verfügbar")
        command = controller.update(0, bad, wallbox())
        controller.command_finished(0, command, None, False)
        self.assertIsNone(controller.update(30, bad, wallbox()))
        self.assertIsNotNone(controller.update(60, bad, wallbox()))


class GridAllowanceTests(unittest.TestCase):
    def test_allowance_starts_charging_without_full_surplus(self):
        wb = wallbox(mode=1, charging=False)
        # 3000 W surplus is below 3-ph 6 A; 1000 W of grid import makes it fit.
        _, command = run(
            pc.PVController(PROFILE, settings("direct")), wb, pv=3500, house=500
        )
        self.assertEqual(command.stage.phases, 1)
        controller = pc.PVController(PROFILE, settings("direct", allowed_grid_import_w=1000))
        _, command = run(controller, wb, pv=3500, house=500)
        self.assertEqual(command.stage.phases, 3)
        self.assertLessEqual(command.stage.power, 3000 + 1000 - 200)
        self.assertIn("Netzbezug 1000 W", command.reason)

    def test_allowance_keeps_stage_despite_deficit(self):
        # About 800 W short for 3-ph 10 A; grid shows that import.
        house = house_with_wallbox(P3["10"])
        pv = P3["10"] - 800 + 500
        _, command = run(
            pc.PVController(PROFILE, settings("step")), wallbox(current=10),
            pv=pv, house=house, grid=800,
        )
        self.assertEqual(command.stage.key, "3_9")
        controller = pc.PVController(PROFILE, settings("step", allowed_grid_import_w=1000))
        _, command = run(controller, wallbox(current=10), pv=pv, house=house, grid=800)
        self.assertIsNone(command)
        self.assertEqual(controller.state, pc.STATE_ACTIVE)

    def test_protection_limit_is_allowance_plus_tolerance(self):
        house = house_with_wallbox(P3["12"])
        controller = pc.PVController(PROFILE, settings("direct", allowed_grid_import_w=1000))
        t, command = run(controller, wallbox(current=12), pv=9000, house=house, grid=1100)
        if command is not None:
            self.assertNotIn("über Grenze", command.reason)
        controller = pc.PVController(PROFILE, settings("direct", allowed_grid_import_w=1000))
        t, command = run(controller, wallbox(current=12), pv=9000, house=house, grid=1500)
        self.assertIsNotNone(command)
        self.assertLess(t, 60)
        self.assertLessEqual(command.stage.power, P3["12"] - 300)


class WaitAndWindowTests(unittest.TestCase):
    def test_wait_after_phase_change_and_after_current_change(self):
        s = settings("direct")
        controller = pc.PVController(PROFILE, s)
        stage6 = controller.current_stage(wallbox(current=6))
        stage10 = next(x for x in controller.ladder if x.key == "3_10")
        controller.command_finished(0, pc.Command(stage10, "test"), stage6, True)
        self.assertIsNone(controller.update(59, pc.Measurement(pv=1, house=1, soc=60), wallbox(current=10)))
        self.assertEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        controller.update(60, pc.Measurement(pv=1, house=1, soc=60), wallbox(current=10))
        self.assertNotEqual(controller.state, pc.STATE_WAITING_WALLBOX)

        single = next(x for x in controller.ladder if x.phases == 1)
        controller.command_finished(100, pc.Command(single, "test"), stage10, True)
        controller.update(185, pc.Measurement(pv=1, house=1, soc=60), wallbox(phases=1, current=6))
        self.assertEqual(controller.state, pc.STATE_WAITING_WALLBOX)

    def test_unstable_stage_uses_longer_window(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        wb = wallbox(current=7)
        _, command = run(controller, wb, pv=12000, house=house_with_wallbox(P3["7"]), seconds=200)
        self.assertIsNone(command)
        self.assertEqual(controller.window_seconds, 240)
        _, command = run(
            controller, wb, pv=12000, house=house_with_wallbox(P3["7"]), start=205, seconds=60
        )
        self.assertIsNotNone(command)

    def test_schedule_and_missing_vehicle_send_nothing(self):
        controller = pc.PVController(PROFILE, settings("direct"))
        _, command = run(controller, wallbox(schedule_active=True), pv=12000, house=500)
        self.assertIsNone(command)
        self.assertEqual(controller.state, pc.STATE_SCHEDULE)
        _, command = run(controller, wallbox(connected=False), pv=12000, house=500)
        self.assertIsNone(command)
        self.assertEqual(controller.state, pc.STATE_NO_VEHICLE)


class ReactionDetectionTests(unittest.TestCase):
    BASE = 500.0

    def prepare(self, previous_key, target_key, **changes):
        """Feed 20 s at the previous stage, then finish a command at t=20."""
        controller = pc.PVController(PROFILE, settings("direct", **changes))
        phases, current = (int(x) for x in previous_key.split("_"))
        wb = wallbox(phases=phases, current=current)
        previous = controller.current_stage(wb)
        house = self.BASE + previous.power
        for t in range(0, 21, 5):
            controller.update(t, pc.Measurement(pv=20000, house=house, soc=60), wb)
        target = next(x for x in controller.ladder if x.key == target_key)
        controller.command_finished(20, pc.Command(target, "test"), previous, True)
        new_wb = wallbox(phases=target.phases, current=target.current)
        return controller, previous, target, new_wb

    def feed(self, controller, wb, start, end, house):
        for t in range(start, end + 1, 5):
            controller.update(t, pc.Measurement(pv=20000, house=house, soc=60), wb)

    def test_wait_ends_once_house_load_reached_expected_level(self):
        controller, previous, target, wb = self.prepare("3_6", "3_10")
        self.assertAlmostEqual(controller.expected_house_w, self.BASE + target.power)
        self.feed(controller, wb, 25, 45, self.BASE + previous.power)
        self.assertEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        # Wallbox reacts at t=50; confirmed after 10 s at t=60 (40 s after command).
        self.feed(controller, wb, 50, 60, self.BASE + target.power + 150)
        self.assertNotEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        self.assertEqual(controller.reaction_seconds, 40)

    def test_unrelated_consumer_keeps_full_wait(self):
        controller, previous, _, wb = self.prepare("3_6", "3_10")
        # A 2 kW consumer switches on instead of the wallbox reacting.
        self.feed(controller, wb, 25, 75, self.BASE + previous.power + 2000)
        self.assertEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        self.feed(controller, wb, 80, 80, self.BASE + previous.power + 2000)
        self.assertNotEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        self.assertIsNone(controller.reaction_seconds)

    def test_charging_pause_during_phase_change_is_not_a_reaction(self):
        controller, _, target, wb = self.prepare("3_8", "1_6")
        # Charging pauses (wallbox 0 W) for 15 s after the phase change.
        self.feed(controller, wb, 55, 70, self.BASE)
        self.assertEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        self.feed(controller, wb, 75, 85, self.BASE + target.power)
        self.assertNotEqual(controller.state, pc.STATE_WAITING_WALLBOX)
        self.assertEqual(controller.reaction_seconds, 65)

    def test_zero_confirmation_time_disables_detection(self):
        controller, _, target, wb = self.prepare("3_6", "3_10", reaction_confirm_seconds=0)
        self.assertIsNone(controller.expected_house_w)
        self.feed(controller, wb, 25, 75, self.BASE + target.power)
        self.assertEqual(controller.state, pc.STATE_WAITING_WALLBOX)


class ConstantsTests(unittest.TestCase):
    def test_settings_fields_match_option_defaults(self):
        fields = set(pc.ControlSettings.__dataclass_fields__) - {"strategy"}
        self.assertEqual(fields, set(CONSTANTS["CONTROL_NUMBER_SETTINGS"]))
        self.assertEqual(pc.STRATEGY_DIRECT, CONSTANTS["CONTROL_STRATEGY_DIRECT"])
        self.assertEqual(pc.STRATEGY_STEP, CONSTANTS["CONTROL_STRATEGY_STEP"])

    def test_unknown_strategy_falls_back_to_step(self):
        self.assertEqual(settings("bogus").strategy, pc.STRATEGY_STEP)


if __name__ == "__main__":
    unittest.main()
