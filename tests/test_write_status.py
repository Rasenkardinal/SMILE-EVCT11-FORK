"""Exercise actual write-status tracking without Home Assistant or a portal."""
from __future__ import annotations

import asyncio
import ast
import copy
import logging
from types import MethodType, SimpleNamespace
import unittest
from unittest.mock import patch

from test_settings_write_lock import (
    API_FILE,
    AuthenticationError,
    FakePortal,
    PortalConnectionError,
    SettingsWriteStatus,
)


def load_patch_method():
    source = ast.parse(API_FILE.read_text(encoding="utf-8"))
    cls = next(node for node in source.body if isinstance(node, ast.ClassDef)
               and node.name == "AlphaESSPortalApi")
    method = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "_async_authenticated_patch")
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    namespace = {
        "Any": object,
        "asyncio": asyncio,
        "aiohttp": SimpleNamespace(
            ClientTimeout=lambda **kwargs: kwargs,
            ClientError=ConnectionError,
        ),
        "PORTAL_HEADERS": {},
        "AuthenticationError": AuthenticationError,
        "PortalConnectionError": PortalConnectionError,
        "_LOGGER": logging.getLogger(__name__),
    }
    exec(compile(module, str(API_FILE), "exec"), namespace)
    return namespace["_async_authenticated_patch"]


class FakeResponse:
    def __init__(self, status=204, error=None):
        self.status = status
        self.error = error

    async def __aenter__(self):
        if self.error is not None:
            raise self.error
        return self

    async def __aexit__(self, *args):
        return False


class WriteStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_mode_acceptance_expires_exactly_after_sixty_seconds(self):
        portal = FakePortal()
        clock = patch.object(SettingsWriteStatus, "_monotonic", return_value=100)
        with clock as now:
            await portal.async_update_wallbox_settings(charge_mode=4)
            self.assertEqual(portal.write_status.accepted_mode, (4, 160))
            now.return_value = 159.99
            self.assertIsNotNone(portal.write_status.accepted_mode)
            now.return_value = 160
            self.assertIsNone(portal.write_status.accepted_mode)

    async def test_stale_mode_is_not_reintroduced_by_immediate_current_write(self):
        portal = FakePortal()
        portal.settings["chargeMode"] = 1
        with patch.object(SettingsWriteStatus, "_monotonic", return_value=100) as now:
            await portal.async_update_wallbox_settings(charge_mode=4)
            selection = portal.write_status.accepted_mode
            now.return_value = 120
            portal.settings["chargeMode"] = 1  # Simulate stale portal read.
            await portal.async_update_wallbox_settings(charge_current=10)
            self.assertEqual(portal.settings["chargeMode"], 4)
            self.assertEqual(portal.settings["chargeCurrent"], 10)
            self.assertEqual(portal.write_status.accepted_mode, selection)
            self.assertEqual(len(portal.patches), 2)
            self.assertIn("g2T.chargeMode", portal.write_status.attributes["Angefordert"])
            now.return_value = 160
            self.assertIsNone(portal.write_status.accepted_mode)

    async def test_matching_mode_read_retires_override_even_after_current_write(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(charge_mode=4)
        old_selection = portal.write_status.accepted_mode
        await portal.async_update_wallbox_settings(charge_current=10)
        portal.write_status.check_mode(old_selection, portal.wallbox)
        self.assertIsNone(portal.write_status.accepted_mode)
        await portal.async_update_wallbox_settings(charge_mode=1)
        new_selection = portal.write_status.accepted_mode
        portal.write_status.check_mode(old_selection, portal.wallbox)
        self.assertEqual(portal.write_status.accepted_mode, new_selection)

    async def test_failed_mode_switch_does_not_enable_override(self):
        portal = FakePortal()
        portal.settings["chargeMode"] = 1
        portal.fail_next_patch = True
        with self.assertRaises(PortalConnectionError):
            await portal.async_update_wallbox_settings(charge_mode=4)
        self.assertIsNone(portal.write_status.accepted_mode)

    async def test_unconfirmed_mode_four_to_one_restores_three_phases(self):
        portal = FakePortal()
        portal.settings.update(chargeMode=1, smartMode=True, obcPhase=1)
        await portal.async_update_wallbox_settings(charge_mode=4)
        portal.settings["chargeMode"] = 1
        await portal.async_update_wallbox_settings(charge_mode=1)
        self.assertEqual(portal.settings["obcPhase"], 3)
        self.assertEqual(portal.write_status.accepted_mode[0], 1)

    async def test_mode_bridge_requires_acceptance_not_transmission_or_failure(self):
        for status_code in (400, 500, None):
            with self.subTest(status_code=status_code):
                status = SettingsWriteStatus()
                status.begin({"charge_mode": 4})
                status.prepare({("g2T", "chargeMode"): 4})
                self.assertIsNone(status.accepted_mode)
                status.transmitting()
                self.assertIsNone(status.accepted_mode)
                status.failed("Failed", status_code)
                self.assertIsNone(status.accepted_mode)

    async def test_g1t_and_top_level_settings_are_confirmed_without_device_data(self):
        portal = FakePortal()
        portal.wallbox["g1T"] = portal.wallbox.pop("g2T")
        await portal.async_update_wallbox_settings(
            charge_current=10, household_current=32, installer_control_allowed=True
        )
        status = portal.write_status
        self.assertEqual(status.attributes["Angefordert"], {
            "g1T.chargeCurrent": 10,
            "houseHoldCurrent": 32,
            "allowInstallersControl": True,
        })
        status.check(status.readback_id, portal.wallbox)
        self.assertEqual(status.state, "Im Portal bestätigt")
        self.assertNotIn("ALP_TEST", str(status.attributes))
        self.assertNotIn("model", str(status.attributes))

    async def test_cancelled_inflight_write_is_uncertain_and_not_retried(self):
        portal = FakePortal()
        portal.patch_started = asyncio.Event()
        portal.release_patch = asyncio.Event()
        task = asyncio.create_task(portal.async_update_wallbox_settings(charge_current=10))
        await portal.patch_started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(portal.write_status.state, "Übermittlung unklar")
        self.assertEqual(portal.patches, [])
        self.assertFalse(portal._settings_write_lock.locked())

    async def test_sensor_reports_failures_even_when_polling_is_unavailable(self):
        source = ast.parse(API_FILE.with_name("sensor.py").read_text(encoding="utf-8"))
        cls = next(node for node in source.body if isinstance(node, ast.ClassDef)
                   and node.name == "AlphaESSSettingsWriteStatusSensor")

        class BaseEntity:
            def __init__(self, coordinator, entry, key):
                self.coordinator = coordinator
                self.unique_key = key

        namespace = {
            "AlphaESSWallboxEntity": BaseEntity,
            "SensorEntity": type("SensorEntity", (), {}),
            "AlphaESSWallboxCoordinator": object,
            "ConfigEntry": object,
            "EntityCategory": SimpleNamespace(DIAGNOSTIC="diagnostic"),
            "Any": object,
        }
        module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
        exec(compile(module, str(API_FILE.with_name("sensor.py")), "exec"), namespace)
        portal = FakePortal()
        entity = namespace["AlphaESSSettingsWriteStatusSensor"](
            SimpleNamespace(api=portal, last_update_success=False), object()
        )
        self.assertEqual(entity.unique_key, "last_settings_write")
        self.assertEqual(entity.native_value, "Noch keine Änderung")
        self.assertTrue(entity.available)
        with self.assertRaises(ValueError):
            await portal.async_update_wallbox_settings(charge_current=17)
        self.assertEqual(entity.native_value, "Nicht übermittelt")
        self.assertIn("Fehler", entity.extra_state_attributes)
        self.assertIn("nicht der physischen", entity.extra_state_attributes["Hinweis"])
        for state, icon in (
            ("Noch keine Änderung", "mdi:information-outline"),
            ("Wird gesendet", "mdi:cloud-upload-outline"),
            ("API angenommen – Bestätigung ausstehend", "mdi:timer-sand"),
            ("Im Portal bestätigt", "mdi:check-circle-outline"),
            ("Noch nicht im Portal bestätigt", "mdi:clock-alert-outline"),
            ("Übermittlung unklar", "mdi:help-circle-outline"),
            ("Abgelehnt", "mdi:close-circle-outline"),
            ("Nicht übermittelt", "mdi:cloud-off-outline"),
            ("Unbekannter Zustand", "mdi:help-circle-outline"),
        ):
            with self.subTest(state=state):
                portal.write_status.state = state
                self.assertEqual(entity.icon, icon)

    async def test_real_patch_method_tracks_http_success_rejection_and_timeout(self):
        for code, error, state in (
            (200, None, "API angenommen – Bestätigung ausstehend"),
            (201, None, "API angenommen – Bestätigung ausstehend"),
            (204, None, "API angenommen – Bestätigung ausstehend"),
            (400, None, "Abgelehnt"),
            (401, None, "Abgelehnt"),
            (503, None, "Übermittlung unklar"),
            (None, asyncio.TimeoutError(), "Übermittlung unklar"),
        ):
            with self.subTest(code=code):
                portal = FakePortal()
                portal._async_authenticated_patch = MethodType(load_patch_method(), portal)
                portal._async_token = lambda: asyncio.sleep(0)
                portal._token = "TEST"
                portal._api_url = "https://example.invalid"
                portal._session = SimpleNamespace(
                    patch=lambda *args, **kwargs: FakeResponse(code, error)
                )
                notifications = []
                portal._settings_written_callback = lambda: notifications.append(True)
                if code in (200, 201, 204):
                    await portal.async_update_wallbox_settings(charge_current=10)
                    self.assertEqual(notifications, [True])
                else:
                    with self.assertRaises((AuthenticationError, PortalConnectionError)):
                        await portal.async_update_wallbox_settings(charge_current=10)
                    self.assertEqual(notifications, [])
                self.assertEqual(portal.write_status.state, state)
                if code is not None:
                    self.assertEqual(portal.write_status.attributes["HTTP-Status"], code)

    async def test_configuration_poll_wires_confirmation_and_failure(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(charge_current=10)

        async def fetch(path, *, step, params=None):
            if step == "wallbox status":
                return {"status": "Charging"}
            return copy.deepcopy(portal.configuration)

        portal._async_get = fetch
        portal.async_get_charge_report_items = lambda serial: asyncio.sleep(0, result=[])
        portal._today_energy_from_report = lambda items: 0
        await portal.async_get_wallbox_data()
        self.assertEqual(portal.write_status.state, "Im Portal bestätigt")
        await portal.async_update_wallbox_settings(charge_current=12)

        async def failing_config(path, *, step, params=None):
            if step == "wallbox configuration":
                raise PortalConnectionError(503, step)
            return await fetch(path, step=step, params=params)

        portal._async_get = failing_config
        data = await portal.async_get_wallbox_data()
        self.assertEqual(data["configuration"], {})
        self.assertIn("Rücklesefehler", portal.write_status.attributes)
        self.assertEqual(portal.write_status.state, "API angenommen – Bestätigung ausstehend")

    async def test_api_acceptance_and_matching_portal_values_are_separate(self):
        portal = FakePortal()
        states = []
        portal.write_status.callback = lambda: states.append(portal.write_status.state)
        await portal.async_update_wallbox_settings(charge_current=10)
        status = portal.write_status
        self.assertEqual(status.state, "API angenommen – Bestätigung ausstehend")
        self.assertEqual(status.attributes["HTTP-Status"], 204)
        self.assertIn("API angenommen um", status.attributes)
        self.assertNotIn("Portal bestätigt um", status.attributes)
        self.assertEqual(status.attributes["Angefordert"], {"g2T.chargeCurrent": 10})
        status.check(status.readback_id, portal.wallbox)
        self.assertEqual(status.state, "Im Portal bestätigt")
        self.assertIn("Portal bestätigt um", status.attributes)
        self.assertEqual(states[0], "Wird gesendet")
        self.assertEqual(states[-1], "Im Portal bestätigt")

    async def test_only_requested_and_automatic_fields_are_compared(self):
        portal = FakePortal()
        portal.settings.update(chargeMode=4, smartMode=True, obcPhase=1)
        await portal.async_update_wallbox_settings(charge_mode=1)
        status = portal.write_status
        self.assertEqual(status.attributes["Angefordert"], {
            "g2T.chargeMode": 1, "g2T.obcPhase": 3,
        })
        wallbox = copy.deepcopy(portal.wallbox)
        wallbox["g2T"]["obcPhase"] = 1
        status.check(status.readback_id, wallbox)
        self.assertEqual(status.state, "Noch nicht im Portal bestätigt")
        wallbox["g2T"]["obcPhase"] = 3
        wallbox["houseHoldCurrent"] = 40
        wallbox["g2T"]["chargeCurrent"] = 12
        status.check(status.readback_id, wallbox)
        self.assertEqual(status.state, "Im Portal bestätigt")

    async def test_time_period_confirmation_uses_exact_index_and_preserves_minutes(self):
        portal = FakePortal()
        await portal.async_update_time_period(2, enabled=False, start_time="08:15")
        status = portal.write_status
        self.assertEqual(status.attributes["Angefordert"], {
            "g2T.timePeriods.2.isEnable": False,
            "g2T.timePeriods.2.startTime": "08:15",
        })
        wallbox = copy.deepcopy(portal.wallbox)
        wallbox["g2T"]["timePeriods"][2]["startTime"] = "08:16"
        status.check(status.readback_id, wallbox)
        self.assertEqual(status.state, "Noch nicht im Portal bestätigt")
        status.check(status.readback_id, portal.wallbox)
        self.assertEqual(status.state, "Im Portal bestätigt")

    async def test_no_op_confirms_without_fake_http_acknowledgement(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(charge_current=6)
        status = portal.write_status
        self.assertEqual(status.state, "Im Portal bestätigt")
        self.assertNotIn("HTTP-Status", status.attributes)
        self.assertNotIn("API angenommen um", status.attributes)
        self.assertEqual(portal.patches, [])

    async def test_new_transaction_cannot_be_confirmed_by_old_readback(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(charge_current=10)
        old_id = portal.write_status.readback_id
        await portal.async_update_wallbox_settings(charge_current=12)
        portal.write_status.check(old_id, portal.wallbox)
        self.assertEqual(portal.write_status.state, "API angenommen – Bestätigung ausstehend")
        self.assertNotIn("Portal bestätigt um", portal.write_status.attributes)
        portal.write_status.check(portal.write_status.readback_id, portal.wallbox)
        self.assertEqual(portal.write_status.state, "Im Portal bestätigt")

    async def test_read_started_before_acknowledgement_cannot_confirm(self):
        portal = FakePortal()
        portal.patch_started = asyncio.Event()
        portal.release_patch = asyncio.Event()
        task = asyncio.create_task(portal.async_update_wallbox_settings(charge_current=10))
        await portal.patch_started.wait()
        read_id = portal.write_status.readback_id
        self.assertIsNone(read_id)
        portal.release_patch.set()
        await task
        portal.write_status.check(read_id, portal.wallbox)
        self.assertEqual(portal.write_status.state, "API angenommen – Bestätigung ausstehend")

    async def test_invalid_input_and_failed_get_are_not_reported_as_sent(self):
        portal = FakePortal()
        with self.assertRaises(ValueError):
            await portal.async_update_wallbox_settings(charge_current=17)
        self.assertEqual(portal.write_status.state, "Nicht übermittelt")
        self.assertNotIn("Gesendet um", portal.write_status.attributes)

        async def failing_get(*args, **kwargs):
            raise PortalConnectionError(None, "wallbox settings")

        portal._async_get = failing_get
        with self.assertRaises(PortalConnectionError):
            await portal.async_update_wallbox_settings(charge_current=10)
        self.assertEqual(portal.write_status.state, "Nicht übermittelt")
        self.assertNotIn("Gesendet um", portal.write_status.attributes)

    async def test_server_error_is_uncertain_and_readback_can_still_confirm(self):
        portal = FakePortal()
        portal.fail_next_patch = True
        with self.assertRaises(PortalConnectionError):
            await portal.async_update_wallbox_settings(charge_current=10)
        status = portal.write_status
        self.assertEqual(status.state, "Übermittlung unklar")
        self.assertEqual(status.attributes["HTTP-Status"], 503)
        status.check(status.readback_id, portal.wallbox)
        self.assertEqual(status.state, "Übermittlung unklar")
        portal.settings["chargeCurrent"] = 10
        status.check(status.readback_id, portal.wallbox)
        self.assertEqual(status.state, "Im Portal bestätigt")
        self.assertNotIn("API angenommen um", status.attributes)
        self.assertEqual(portal.patches, [])

    async def test_readback_failure_does_not_erase_acknowledgement(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(charge_current=10)
        status = portal.write_status
        status.read_failed(status.readback_id, "Portal nicht erreichbar")
        self.assertEqual(status.state, "API angenommen – Bestätigung ausstehend")
        self.assertEqual(status.attributes["HTTP-Status"], 204)
        self.assertIn("Rücklesefehler", status.attributes)
        status.check(status.readback_id, portal.wallbox)
        self.assertNotIn("Rücklesefehler", status.attributes)

    async def test_missing_fields_and_wrong_types_do_not_confirm(self):
        portal = FakePortal()
        await portal.async_update_wallbox_settings(smart_mode=True, obc_phase=3)
        status = portal.write_status
        for wallbox in ({}, {"g2T": {"smartMode": 1, "obcPhase": 3}}):
            status.check(status.readback_id, wallbox)
            self.assertEqual(status.state, "Noch nicht im Portal bestätigt")

    async def test_numeric_readback_accepts_equal_integer_and_float_values(self):
        for actual in (10, 10.0):
            with self.subTest(actual=actual):
                status = SettingsWriteStatus()
                status.begin({"charge_current": 10})
                status.prepare({("g2T", "chargeCurrent"): 10})
                status.accepted(204)
                status.check(status.readback_id, {"g2T": {"chargeCurrent": actual}})
                self.assertEqual(status.state, "Im Portal bestätigt")
                self.assertEqual(status.attributes["Abweichende Felder"], [])
                self.assertEqual(status.attributes["Rückgelesen"]["g2T.chargeCurrent"], {
                    "Wert": actual, "Datentyp": type(actual).__name__, "Vorhanden": True,
                })

    async def test_invalid_numeric_readback_does_not_confirm(self):
        for actual in (True, False, "10", "10.0", None, 9, 10.01, float("nan"), float("inf")):
            with self.subTest(actual=actual):
                status = SettingsWriteStatus()
                status.begin({"charge_current": 10})
                status.prepare({("g2T", "chargeCurrent"): 10})
                status.accepted(204)
                status.check(status.readback_id, {"g2T": {"chargeCurrent": actual}})
                self.assertEqual(status.state, "Noch nicht im Portal bestätigt")
                self.assertEqual(status.attributes["Abweichende Felder"], ["g2T.chargeCurrent"])

    async def test_readback_diagnostics_distinguish_missing_and_null_without_leaking_data(self):
        status = SettingsWriteStatus()
        status.begin({"charge_current": 10})
        status.prepare({("g2T", "chargeCurrent"): 10, ("g2T", "chargeMode"): 4})
        status.accepted(204)
        for actual, present, name in (
            ({}, False, "fehlend"),
            ({"chargeCurrent": None}, True, "NoneType"),
            ({"chargeCurrent": {"token": "SECRET"}}, True, "dict"),
        ):
            status.check(status.readback_id, {"g2T": actual})
            read = status.attributes["Rückgelesen"]["g2T.chargeCurrent"]
            self.assertEqual(read, {"Wert": None, "Datentyp": name, "Vorhanden": present})
            self.assertNotIn("SECRET", str(status.attributes))
        status.check(status.readback_id, {"g2T": {"chargeCurrent": 10.0, "chargeMode": 1}})
        self.assertEqual(status.attributes["Abweichende Felder"], ["g2T.chargeMode"])
        status.check(status.readback_id, {"g2T": {"chargeCurrent": 10.0, "chargeMode": 4.0}})
        self.assertEqual(status.state, "Im Portal bestätigt")
        self.assertEqual(status.attributes["Abweichende Felder"], [])
        status.begin({"charge_current": 12})
        self.assertNotIn("Rückgelesen", status.attributes)
        self.assertNotIn("Abweichende Felder", status.attributes)

    async def test_decimal_mode_confirmation_retires_bridge(self):
        status = SettingsWriteStatus()
        status.begin({"charge_mode": 4})
        status.prepare({("g2T", "chargeMode"): 4})
        status.accepted(204)
        selection = status.accepted_mode
        status.check_mode(selection, {"g2T": {"chargeMode": 4.0}})
        self.assertIsNone(status.accepted_mode)

    async def test_http_rejection_and_timeout_are_distinct(self):
        status = SettingsWriteStatus()
        for code, expected in ((400, "Abgelehnt"), (403, "Abgelehnt"), (None, "Übermittlung unklar")):
            with self.subTest(code=code):
                status.begin({"charge_current": 10})
                status.prepare({("g2T", "chargeCurrent"): 10})
                status.transmitting()
                status.failed("Schreibfehler", code)
                self.assertEqual(status.state, expected)
                self.assertNotIn("API angenommen um", status.attributes)


if __name__ == "__main__":
    unittest.main()
