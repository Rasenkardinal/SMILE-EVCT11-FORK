"""Regression tests for AlphaESS wallbox settings write transactions.

Run without Home Assistant:
    python -m unittest discover -s tests -v

Only production methods are extracted from api.py via ast. No portal credentials,
network requests or hardware access are used in these tests.
"""
from __future__ import annotations

import ast
import asyncio
import copy
import functools
from pathlib import Path
import re
import runpy
import typing
import unittest
from types import SimpleNamespace


API_FILE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "alphaess_portal_bridge"
    / "api.py"
)
SettingsWriteStatus = runpy.run_path(
    str(API_FILE.with_name("write_status.py"))
)["SettingsWriteStatus"]


class AuthenticationError(Exception):
    pass


class PortalConnectionError(Exception):
    def __init__(self, status=None, step="connection"):
        self.status = status
        self.step = step
        super().__init__(step)


class PVControlSuspended(Exception):
    pass


def load_production_methods():
    """Compile the actual decorator and update methods without HA imports."""
    source = ast.parse(API_FILE.read_text(encoding="utf-8"))
    decorator = next(
        node for node in source.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "_serialize_settings_write"
    )
    original_class = next(
        node for node in source.body
        if isinstance(node, ast.ClassDef) and node.name == "AlphaESSPortalApi"
    )
    selected = {
        "async_update_wallbox_settings",
        "async_save_current_mode_settings",
        "async_update_time_period",
        "_settings_from_wallbox",
        "_find_wallbox_data",
        "_validate_hhmm",
        "_async_write_settings",
        "async_get_wallbox_data",
        "_find_wallbox_serial",
    }
    methods = [
        node for node in original_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in selected
    ]
    assert len(methods) == len(selected), "An API method was renamed/removed"
    extracted_class = ast.ClassDef(
        name="ExtractedPortalMethods",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    module = ast.fix_missing_locations(
        ast.Module(body=[decorator, extracted_class], type_ignores=[])
    )
    namespace = {
        "asyncio": asyncio,
        "wraps": functools.wraps,
        "copy": copy,
        "re": re,
        "Any": typing.Any,
        "PortalConnectionError": PortalConnectionError,
        "AuthenticationError": AuthenticationError,
        "PVControlSuspended": PVControlSuspended,
        "SettingPath": tuple[str | int, ...],
    }
    exec(compile(module, str(API_FILE), "exec"), namespace)
    cls = namespace["ExtractedPortalMethods"]
    # The recursive static helper uses the production class name explicitly.
    namespace["AlphaESSPortalApi"] = cls
    return cls


ProductionMethods = load_production_methods()


def sample_configuration():
    return {
        "evCharger": [{
            "sn": "ALP_TEST",
            "model": "SMILE-G3-EVCT11/S",
            "houseHoldCurrent": 25,
            "allowInstallersControl": False,
            "g2T": {
                "chargeMode": 4,
                "chargeCurrent": 6,
                "chargeStrategy": 0,
                "obcPhase": 1,
                "smartMode": False,
                "gunLineSelfLockEnable": False,
                "isSupportGunLineSelfLock": True,
                "timePeriods": [
                    {"isEnable": True, "startTime": "08:00", "endTime": "17:00",
                     "chargeMode": 1, "chargeCurrent": 6},
                    {"isEnable": True, "startTime": "17:00", "endTime": "21:00",
                     "chargeMode": 1, "chargeCurrent": 6},
                    {"isEnable": True, "startTime": "00:15", "endTime": "04:45",
                     "chargeMode": 4, "chargeCurrent": 16},
                ],
            },
        }]
    }


class FakePortal(ProductionMethods):
    def __init__(self):
        self._settings_write_lock = asyncio.Lock()
        self.mode_settings = None
        self._pv_mode_active = lambda: False
        self._pv_control_allowed = lambda: self._pv_mode_active()
        self._mode_write_pending = False
        self.write_status = SettingsWriteStatus()
        self._charge_current_request_id = 0
        self._wallbox_serial = "ALP_TEST"
        self._system_serial = "ALA_TEST"
        self.configuration = sample_configuration()
        self.patches = []
        self.active_patches = 0
        self.max_active_patches = 0
        self.fail_next_patch = False
        self.patch_started = None
        self.release_patch = None

    async def _async_get(self, path, *, step):
        return copy.deepcopy(self.configuration)

    async def _async_authenticated_patch(self, path, payload, *, step):
        self.write_status.transmitting()
        self.active_patches += 1
        self.max_active_patches = max(self.max_active_patches, self.active_patches)
        try:
            if self.patch_started is not None:
                self.patch_started.set()
            if self.release_patch is not None:
                await self.release_patch.wait()
            if self.fail_next_patch:
                self.fail_next_patch = False
                raise PortalConnectionError(503, step)
            self.configuration = copy.deepcopy(payload)
            self.patches.append((step, copy.deepcopy(payload)))
            await asyncio.sleep(0)
            return 204
        finally:
            self.active_patches -= 1

    @property
    def wallbox(self):
        return self.configuration["evCharger"][0]

    @property
    def settings(self):
        return self.wallbox["g2T"]


def make_mode_memory(entry):
    source = ast.parse(API_FILE.with_name("mode_settings.py").read_text(encoding="utf-8"))
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef))
    module = ast.fix_missing_locations(ast.Module(
        body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cls],
        type_ignores=[],
    ))
    namespace = {"CONF_MODE_SETTINGS": "mode_settings"}
    exec(compile(module, "mode_settings.py", "exec"), namespace)

    def update_entry(target, *, options):
        target.options = options

    hass = SimpleNamespace(config_entries=SimpleNamespace(async_update_entry=update_entry))
    return namespace["ModeSettings"](hass, entry, "ALP_TEST")


class ModeSettingsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.entry = SimpleNamespace(options={})
        self.portal = FakePortal()
        self.portal.mode_settings = make_mode_memory(self.entry)
        self.active = False
        self.portal._pv_mode_active = lambda: self.active

    async def test_pv_control_preserves_custom_settings_across_restart_and_fallback(self):
        portal = self.portal
        portal.settings.update(chargeCurrent=14, obcPhase=2, smartMode=True)
        await portal.async_save_current_mode_settings()
        self.active = True
        await portal.async_update_wallbox_settings(
            charge_mode=4, charge_current=6, obc_phase=1, pv_control=True
        )
        await portal.async_update_wallbox_settings(charge_mode=1, pv_control=True)
        self.assertEqual(self.entry.options["mode_settings"]["ALP_TEST:g2T:4"], {
            "chargeCurrent": 14, "obcPhase": 2, "smartMode": True,
        })
        portal.mode_settings = make_mode_memory(self.entry)
        self.active = False
        await portal.async_update_wallbox_settings(
            charge_mode=4, restore_mode_settings=True, preserve_current_mode=False
        )
        self.assertEqual(
            {key: portal.settings[key] for key in ("chargeMode", "chargeCurrent", "obcPhase", "smartMode")},
            {"chargeMode": 4, "chargeCurrent": 14, "obcPhase": 2, "smartMode": True},
        )

    async def test_return_from_pv_when_portal_is_still_in_custom_mode(self):
        portal = self.portal
        portal.settings.update(chargeCurrent=14, obcPhase=3)
        await portal.async_save_current_mode_settings()
        self.active = True
        await portal.async_update_wallbox_settings(
            charge_mode=4, charge_current=6, obc_phase=1, pv_control=True
        )
        portal._pv_control_allowed = lambda: False
        await portal.async_update_wallbox_settings(
            charge_mode=4, restore_mode_settings=True, preserve_current_mode=False
        )
        self.assertEqual((portal.settings["chargeCurrent"], portal.settings["obcPhase"]), (14, 3))
        self.assertEqual(self.entry.options["mode_settings"]["ALP_TEST:g2T:4"]["chargeCurrent"], 14)

    async def test_each_original_mode_restores_its_own_latest_values(self):
        portal = self.portal
        await portal.async_update_wallbox_settings(charge_current=12, obc_phase=2)
        await portal.async_update_wallbox_settings(charge_mode=1, restore_mode_settings=True)
        await portal.async_update_wallbox_settings(charge_current=8, obc_phase=3, smart_mode=True)
        await portal.async_update_wallbox_settings(charge_mode=4, restore_mode_settings=True)
        self.assertEqual(
            (portal.settings["chargeCurrent"], portal.settings["obcPhase"], portal.settings["smartMode"]),
            (12, 2, False),
        )
        await portal.async_update_wallbox_settings(charge_mode=1, restore_mode_settings=True)
        self.assertEqual(
            (portal.settings["chargeCurrent"], portal.settings["obcPhase"], portal.settings["smartMode"]),
            (8, 3, True),
        )

    async def test_stale_read_does_not_replace_an_accepted_current(self):
        portal = self.portal
        stale = copy.deepcopy(portal.configuration)
        await portal.async_update_wallbox_settings(charge_current=13)

        async def stale_get(path, *, step):
            return copy.deepcopy(stale)

        portal._async_get = stale_get
        await portal.async_update_wallbox_settings(obc_phase=2)
        self.assertEqual(portal.settings["chargeCurrent"], 13)
        self.assertEqual(self.entry.options["mode_settings"]["ALP_TEST:g2T:4"]["chargeCurrent"], 13)
        await portal.async_update_wallbox_settings(charge_mode=1, restore_mode_settings=True)
        self.assertEqual(self.entry.options["mode_settings"]["ALP_TEST:g2T:4"]["chargeCurrent"], 13)

    async def test_failed_write_does_not_save_rejected_values(self):
        portal = self.portal
        await portal.async_save_current_mode_settings()
        portal.fail_next_patch = True
        with self.assertRaises(PortalConnectionError):
            await portal.async_update_wallbox_settings(charge_current=15)
        self.assertEqual(self.entry.options["mode_settings"]["ALP_TEST:g2T:4"]["chargeCurrent"], 6)

    async def test_missing_portal_fields_do_not_erase_valid_saved_values(self):
        portal = self.portal
        portal.settings.update(chargeCurrent=12.0, obcPhase=2.0, chargeMode=4.0)
        await portal.async_save_current_mode_settings()
        del portal.settings["chargeCurrent"]
        del portal.settings["obcPhase"]
        await portal.async_save_current_mode_settings()
        self.assertEqual(self.entry.options["mode_settings"]["ALP_TEST:g2T:4"], {
            "chargeCurrent": 12, "obcPhase": 2, "smartMode": False,
        })

    async def test_saved_settings_are_isolated_by_wallbox_serial(self):
        portal = self.portal
        await portal.async_save_current_mode_settings()
        other = make_mode_memory(self.entry)
        other.serial = "ALP_OTHER"
        self.assertEqual(other.get("g2T", 4), {})
        other.save("g2T", 4, {"chargeCurrent": 15})
        self.assertEqual(portal.mode_settings.get("g2T", 4)["chargeCurrent"], 6)

    async def test_queued_pv_write_is_discarded_after_deactivation(self):
        portal = self.portal
        self.active = True
        async with portal._settings_write_lock:
            task = asyncio.create_task(portal.async_update_wallbox_settings(
                charge_current=8, pv_control=True
            ))
            await asyncio.sleep(0)
            self.active = False
        with self.assertRaises(PVControlSuspended):
            await task
        self.assertEqual(portal.patches, [])

    async def test_g1_modes_store_current_without_g2_fields(self):
        portal = self.portal
        portal.wallbox["g1T"] = {"chargeMode": 0, "chargeCurrent": 10}
        del portal.wallbox["g2T"]
        await portal.async_update_wallbox_settings(charge_mode=4, restore_mode_settings=True)
        await portal.async_update_wallbox_settings(charge_current=15)
        await portal.async_update_wallbox_settings(charge_mode=0, restore_mode_settings=True)
        self.assertEqual(portal.wallbox["g1T"]["chargeCurrent"], 10)
        await portal.async_update_wallbox_settings(charge_mode=4, restore_mode_settings=True)
        self.assertEqual(portal.wallbox["g1T"]["chargeCurrent"], 15)


class ModeSelectTests(unittest.IsolatedAsyncioTestCase):
    async def test_pv_is_suspended_until_selection_succeeds_or_fails(self):
        source = ast.parse(API_FILE.with_name("select.py").read_text(encoding="utf-8"))
        cls = next(node for node in source.body if isinstance(node, ast.ClassDef)
                   and node.name == "AlphaESSWallboxModeSelect")
        module = ast.fix_missing_locations(ast.Module(
            body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), cls],
            type_ignores=[],
        ))
        namespace = {
            "AlphaESSWallboxEntity": type("Entity", (), {}),
            "SelectEntity": type("Select", (), {}),
            "EntityCategory": SimpleNamespace(CONFIG="config"),
            "G1_MODES": {"Benutzerdefiniert": 4},
            "G2_MODES": {"Benutzerdefiniert": 4},
            "PV_MODE_OPTION": "PV-Eigenverbrauch",
            "settings_object": lambda coordinator: ("g2T", {}),
            "HomeAssistantError": RuntimeError,
            "AuthenticationError": AuthenticationError,
            "PortalConnectionError": PortalConnectionError,
        }
        exec(compile(module, "select.py", "exec"), namespace)

        class Manager:
            def __init__(self):
                self.active = True
                self.suspended = False
                self.mode_change_lock = asyncio.Lock()

            def suspend(self):
                self.suspended = True

            def resume(self):
                self.suspended = False

            async def async_deactivate(self):
                self.active = False
                self.suspended = False

        manager = Manager()
        fail = True

        async def update(**kwargs):
            self.assertTrue(manager.active)
            self.assertTrue(manager.suspended)
            self.assertFalse(kwargs["preserve_current_mode"])
            if fail:
                raise PortalConnectionError(503)

        entity = namespace["AlphaESSWallboxModeSelect"].__new__(
            namespace["AlphaESSWallboxModeSelect"]
        )
        entity.coordinator = SimpleNamespace(
            pv_mode=manager,
            api=SimpleNamespace(async_update_wallbox_settings=update),
            async_request_refresh=lambda: asyncio.sleep(0),
        )
        entity.async_write_ha_state = lambda: None
        with self.assertRaises(RuntimeError):
            await entity.async_select_option("Benutzerdefiniert")
        self.assertTrue(manager.active)
        self.assertFalse(manager.suspended)
        fail = False
        await entity.async_select_option("Benutzerdefiniert")
        self.assertFalse(manager.active)
        self.assertFalse(manager.suspended)


class SettingsWriteTests(unittest.IsolatedAsyncioTestCase):
    async def test_leaving_custom_mode_with_smart_mode_sets_three_phases(self):
        for mode in (1, 2, 3):
            for phase in (1, 2, 3):
                with self.subTest(mode=mode, phase=phase):
                    portal = FakePortal()
                    portal.settings.update(chargeMode=4, smartMode=True, obcPhase=phase)
                    expected = copy.deepcopy(portal.configuration)
                    expected["evCharger"][0]["g2T"].update(chargeMode=mode, obcPhase=3)
                    await portal.async_update_wallbox_settings(charge_mode=mode)
                    self.assertEqual(portal.configuration, expected)
                    self.assertEqual(len(portal.patches), 1)
                    self.assertEqual(portal.patches[0][1], expected)

    async def test_mode_changes_without_smart_mode_preserve_phase(self):
        for mode in (1, 2, 3):
            portal = FakePortal()
            portal.settings.update(chargeMode=4, smartMode=False, obcPhase=1)
            await portal.async_update_wallbox_settings(charge_mode=mode)
            self.assertEqual(portal.settings["obcPhase"], 1)
            self.assertFalse(portal.settings["smartMode"])

    async def test_disabling_smart_mode_with_mode_change_preserves_phase(self):
        portal = FakePortal()
        portal.settings.update(chargeMode=4, smartMode=True, obcPhase=2)
        await portal.async_update_wallbox_settings(charge_mode=1, smart_mode=False)
        self.assertEqual(portal.settings["obcPhase"], 2)
        self.assertFalse(portal.settings["smartMode"])

    async def test_conflicting_explicit_phase_is_rejected_without_write(self):
        portal = FakePortal()
        portal.settings.update(chargeMode=4, smartMode=True, obcPhase=1)
        original = copy.deepcopy(portal.configuration)
        with self.assertRaises(ValueError):
            await portal.async_update_wallbox_settings(charge_mode=1, obc_phase=2)
        self.assertEqual(portal.configuration, original)
        self.assertEqual(portal.patches, [])

    async def test_mode_changes_preserve_enabled_smart_mode(self):
        portal = FakePortal()
        portal.settings.update(chargeMode=1, smartMode=True, obcPhase=3)
        original = copy.deepcopy(portal.configuration)
        for mode in (4, 1):
            await portal.async_update_wallbox_settings(charge_mode=mode)
            expected = copy.deepcopy(original)
            expected["evCharger"][0]["g2T"]["chargeMode"] = mode
            self.assertEqual(portal.configuration, expected)
        self.assertEqual(len(portal.patches), 2)

    async def test_smart_mode_can_be_enabled_in_custom_mode(self):
        portal = FakePortal()
        portal.settings["obcPhase"] = 3
        original = copy.deepcopy(portal.configuration)
        await portal.async_update_wallbox_settings(smart_mode=True)
        original["evCharger"][0]["g2T"]["smartMode"] = True
        self.assertEqual(portal.configuration, original)
        await portal.async_update_wallbox_settings(smart_mode=False)
        self.assertFalse(portal.settings["smartMode"])
        self.assertEqual(portal.settings["chargeMode"], 4)

    async def test_smart_mode_still_rejects_invalid_or_missing_modes(self):
        for mode in (0, 5, None):
            with self.subTest(mode=mode):
                portal = FakePortal()
                portal.settings.update(chargeMode=mode, obcPhase=3)
                with self.assertRaises(ValueError):
                    await portal.async_update_wallbox_settings(smart_mode=True)
                self.assertEqual(portal.patches, [])

    async def test_g1t_mode_changes_and_smart_mode_rejection_remain(self):
        portal = FakePortal()
        settings = portal.wallbox.pop("g2T")
        portal.wallbox["g1T"] = settings
        for mode in (0, 4):
            await portal.async_update_wallbox_settings(charge_mode=mode)
            self.assertEqual(portal.wallbox["g1T"]["chargeMode"], mode)
        with self.assertRaises(ValueError):
            await portal.async_update_wallbox_settings(smart_mode=True)
        self.assertEqual(len(portal.patches), 2)

    async def test_smart_mode_schedule_and_phase_guards_remain(self):
        for settings, update in (
            ({"chargeStrategy": 1, "obcPhase": 3}, {"smart_mode": True}),
            ({"obcPhase": 1}, {"smart_mode": True}),
            ({"smartMode": True, "obcPhase": 3}, {"charge_strategy": 1}),
            ({"chargeMode": 1, "smartMode": True, "obcPhase": 3}, {"obc_phase": 1}),
        ):
            with self.subTest(settings=settings, update=update):
                portal = FakePortal()
                portal.settings.update(settings)
                original = copy.deepcopy(portal.configuration)
                with self.assertRaises(ValueError):
                    await portal.async_update_wallbox_settings(**update)
                self.assertEqual(portal.configuration, original)
                self.assertEqual(portal.patches, [])

    async def test_custom_mode_allows_all_phases_with_smart_mode_enabled(self):
        for phase in (1, 2, 3):
            with self.subTest(phase=phase):
                portal = FakePortal()
                portal.settings.update(chargeMode=4, smartMode=True, obcPhase=3)
                expected = copy.deepcopy(portal.configuration)
                expected["evCharger"][0]["g2T"]["obcPhase"] = phase
                await portal.async_update_wallbox_settings(obc_phase=phase)
                self.assertEqual(portal.configuration, expected)
                self.assertEqual(len(portal.patches), 0 if phase == 3 else 1)

    async def test_non_custom_modes_keep_smart_mode_phase_guard(self):
        for mode in (1, 2, 3, None):
            for phase in (1, 2, 3):
                with self.subTest(mode=mode, phase=phase):
                    portal = FakePortal()
                    portal.settings.update(chargeMode=mode, smartMode=True, obcPhase=3)
                    original = copy.deepcopy(portal.configuration)
                    if phase == 3:
                        await portal.async_update_wallbox_settings(obc_phase=phase)
                    else:
                        with self.assertRaises(ValueError):
                            await portal.async_update_wallbox_settings(obc_phase=phase)
                    self.assertEqual(portal.configuration, original)
                    self.assertEqual(portal.patches, [])

    async def test_different_fields_are_serialized_and_preserved(self):
        portal = FakePortal()
        original_periods = copy.deepcopy(portal.settings["timePeriods"])
        await asyncio.gather(
            portal.async_update_wallbox_settings(charge_current=10),
            portal.async_update_wallbox_settings(household_current=32),
            portal.async_update_time_period(0, start_time="09:00"),
        )
        self.assertEqual(portal.max_active_patches, 1)
        self.assertEqual(len(portal.patches), 3)
        self.assertEqual(portal.settings["chargeCurrent"], 10)
        self.assertEqual(portal.wallbox["houseHoldCurrent"], 32)
        self.assertEqual(portal.settings["timePeriods"][0]["startTime"], "09:00")
        self.assertEqual(
            portal.settings["timePeriods"][1:], original_periods[1:]
        )
        self.assertFalse(portal.settings["smartMode"])
        self.assertEqual(portal.settings["chargeStrategy"], 0)

    async def test_queued_current_changes_use_latest_value(self):
        portal = FakePortal()
        async with portal._settings_write_lock:
            first = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=8)
            )
            await asyncio.sleep(0)
            second = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=9)
            )
            await asyncio.sleep(0)
            last = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=10)
            )
            await asyncio.sleep(0)
        await asyncio.gather(first, second, last)
        self.assertEqual(portal.settings["chargeCurrent"], 10)
        self.assertEqual(len(portal.patches), 1)
        self.assertEqual(portal.write_status.attributes["Auftrag"], 1)

    async def test_other_settings_are_not_coalesced(self):
        portal = FakePortal()
        async with portal._settings_write_lock:
            first = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=8)
            )
            await asyncio.sleep(0)
            other = asyncio.create_task(
                portal.async_update_wallbox_settings(household_current=40)
            )
            await asyncio.sleep(0)
            last = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=10)
            )
            await asyncio.sleep(0)
        await asyncio.gather(first, other, last)
        self.assertEqual(portal.wallbox["houseHoldCurrent"], 40)
        self.assertEqual(portal.settings["chargeCurrent"], 10)
        self.assertEqual(len(portal.patches), 2)

    async def test_inflight_patch_is_not_cancelled(self):
        portal = FakePortal()
        portal.patch_started = asyncio.Event()
        portal.release_patch = asyncio.Event()
        first = asyncio.create_task(
            portal.async_update_wallbox_settings(charge_current=10)
        )
        await portal.patch_started.wait()
        second = asyncio.create_task(
            portal.async_update_wallbox_settings(charge_current=6)
        )
        await asyncio.sleep(0)
        portal.release_patch.set()
        await asyncio.gather(first, second)
        self.assertEqual(len(portal.patches), 2)
        self.assertEqual(portal.settings["chargeCurrent"], 6)

    async def test_identical_values_do_not_send_another_patch(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(charge_current=6)
        await portal.async_update_time_period(0, start_time="08:00")
        self.assertEqual(portal.patches, [])

    async def test_failed_patch_releases_lock_without_fake_success(self):
        portal = FakePortal()
        portal.fail_next_patch = True
        with self.assertRaises(PortalConnectionError):
            await portal.async_update_wallbox_settings(charge_current=10)
        self.assertEqual(portal.settings["chargeCurrent"], 6)
        await portal.async_update_wallbox_settings(charge_current=9)
        self.assertEqual(portal.settings["chargeCurrent"], 9)
        self.assertFalse(portal._settings_write_lock.locked())

    async def test_invalid_current_does_not_discard_valid_request(self):
        portal = FakePortal()
        async with portal._settings_write_lock:
            valid = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=10)
            )
            await asyncio.sleep(0)
            invalid = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_current=17)
            )
            await asyncio.sleep(0)
        results = await asyncio.gather(valid, invalid, return_exceptions=True)
        self.assertIsNone(results[0])
        self.assertIsInstance(results[1], ValueError)
        self.assertEqual(portal.settings["chargeCurrent"], 10)

    async def test_configuration_missing_current_is_patched_not_skipped(self):
        portal = FakePortal()
        del portal.settings["chargeCurrent"]
        await portal.async_update_wallbox_settings(charge_current=6)
        self.assertEqual(len(portal.patches), 1)
        self.assertEqual(portal.settings["chargeCurrent"], 6)


if __name__ == "__main__":
    unittest.main()
