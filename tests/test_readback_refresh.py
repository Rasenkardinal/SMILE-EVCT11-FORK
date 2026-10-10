"""Tests for the coordinator's debounced post-PATCH configuration read-back.

The real coordinator methods are loaded from the source AST, allowing these
tests to run without an installed Home Assistant instance.
"""
from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
import typing
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_settings_write_lock import (
    AuthenticationError,
    FakePortal,
    PortalConnectionError,
    SettingsWriteStatus,
)


COORDINATOR_FILE = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "alphaess_portal_bridge"
    / "coordinator.py"
)


class FakeScheduledCall:
    def __init__(self, callback):
        self.callback = callback
        self.cancelled = False

    def cancel(self):
        self.cancelled = True

    async def run(self):
        if not self.cancelled:
            await self.callback(None)


scheduled_calls = []


def fake_async_call_later(hass, seconds, callback):
    assert seconds in (3, 60)
    call = FakeScheduledCall(callback)
    scheduled_calls.append(call)
    return call.cancel


def load_coordinator_methods():
    module = ast.parse(COORDINATOR_FILE.read_text(encoding="utf-8"))
    original = next(
        node for node in module.body
        if isinstance(node, ast.ClassDef)
        and node.name == "AlphaESSWallboxCoordinator"
    )
    names = {
        "_schedule_followup_refresh",
        "_async_followup_refresh",
        "stop_followup_refresh",
        "_write_status_changed",
        "_mode_expired",
        "_async_update_data",
    }
    methods = [
        node for node in original.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in names
    ]
    assert len(methods) == len(names)
    extracted = ast.ClassDef(
        name="ExtractedCoordinator",
        bases=[],
        keywords=[],
        body=methods,
        decorator_list=[],
    )
    script = ast.fix_missing_locations(
        ast.Module(body=[extracted], type_ignores=[])
    )
    namespace = {
        "Any": typing.Any,
        "async_call_later": fake_async_call_later,
        "_POST_WRITE_READBACK_SECONDS": 3,
        "time": SimpleNamespace(monotonic=lambda: 100),
        "AuthenticationError": AuthenticationError,
        "PortalConnectionError": PortalConnectionError,
        "UpdateFailed": RuntimeError,
        "_LOGGER": logging.getLogger(__name__),
    }
    exec(compile(script, str(COORDINATOR_FILE), "exec"), namespace)
    return namespace["ExtractedCoordinator"]


Methods = load_coordinator_methods()


class FakeApi:
    def __init__(self):
        self.callback = "registered"
        self.write_status = SimpleNamespace(
            callback="registered",
            accepted_mode=None,
            expire_mode=self.expire_mode,
        )

    def expire_mode(self, selection):
        if selection == self.write_status.accepted_mode:
            self.write_status.accepted_mode = None

    def set_settings_written_callback(self, callback):
        self.callback = callback


class FakeCoordinator(Methods):
    def __init__(self):
        self.hass = object()
        self.api = FakeApi()
        self._cancel_followup_refresh = None
        self._stopped = False
        self._cancel_mode_expiry = None
        self._mode_selection = None
        self.refresh_count = 0
        self.notifications = 0

    def async_update_listeners(self):
        self.notifications += 1

    async def async_request_refresh(self):
        self.refresh_count += 1


class FollowupReadbackTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        scheduled_calls.clear()

    async def test_mode_acceptance_notifies_immediately_and_expiry_notifies_again(self):
        coordinator = FakeCoordinator()
        coordinator.api.write_status.accepted_mode = (4, 160)
        coordinator._write_status_changed()
        self.assertEqual(coordinator.notifications, 1)
        self.assertEqual(len(scheduled_calls), 1)
        coordinator._write_status_changed()
        self.assertEqual(len(scheduled_calls), 1)
        coordinator._mode_expired(None)
        self.assertIsNone(coordinator.api.write_status.accepted_mode)
        self.assertEqual(coordinator.notifications, 3)
        self.assertIsNone(coordinator._cancel_mode_expiry)

    async def test_unload_cancels_mode_expiry_and_suppresses_notifications(self):
        coordinator = FakeCoordinator()
        coordinator.api.write_status.accepted_mode = (4, 160)
        coordinator._write_status_changed()
        coordinator.stop_followup_refresh()
        self.assertTrue(scheduled_calls[-1].cancelled)
        coordinator._mode_expired(None)
        coordinator._write_status_changed()
        self.assertEqual(coordinator.notifications, 1)

    async def test_mode_bridge_survives_config_confirmation_until_snapshot_finishes(self):
        coordinator = FakeCoordinator()
        portal = FakePortal()
        coordinator.api = portal
        with patch.object(SettingsWriteStatus, "_monotonic", return_value=100):
            await portal.async_update_wallbox_settings(charge_mode=4)
            selection = portal.write_status.accepted_mode
            config_read = asyncio.Event()
            finish_snapshot = asyncio.Event()

            async def get_data():
                portal.write_status.check(portal.write_status.readback_id, portal.wallbox)
                config_read.set()
                await finish_snapshot.wait()
                return {
                    "configuration": portal.configuration,
                    "wallbox_serial": portal._wallbox_serial,
                }

            portal.async_get_wallbox_data = get_data
            task = asyncio.create_task(coordinator._async_update_data())
            await config_read.wait()
            self.assertEqual(portal.write_status.state, "Im Portal bestätigt")
            self.assertEqual(portal.write_status.accepted_mode, selection)
            finish_snapshot.set()
            data = await task
            self.assertEqual(data["configuration"], portal.configuration)
            self.assertIsNone(portal.write_status.accepted_mode)

    async def test_api_acknowledgement_notifies_before_any_coordinator_refresh(self):
        coordinator = FakeCoordinator()
        portal = FakePortal()
        portal.settings["chargeMode"] = 1
        coordinator.api = portal
        portal.write_status.callback = coordinator._write_status_changed
        portal.patch_started = asyncio.Event()
        portal.release_patch = asyncio.Event()
        with patch.object(SettingsWriteStatus, "_monotonic", return_value=100):
            task = asyncio.create_task(
                portal.async_update_wallbox_settings(charge_mode=4)
            )
            await portal.patch_started.wait()
            self.assertIsNone(portal.write_status.accepted_mode)
            self.assertEqual(scheduled_calls, [])
            previous_notifications = coordinator.notifications
            portal.release_patch.set()
            await task
            self.assertEqual(portal.write_status.accepted_mode, (4, 160))
            self.assertEqual(coordinator.notifications, previous_notifications + 1)
            self.assertEqual(len(scheduled_calls), 1)
            self.assertEqual(coordinator.refresh_count, 0)

    async def test_rapid_writes_schedule_only_one_readback(self):
        coordinator = FakeCoordinator()
        coordinator._schedule_followup_refresh()
        coordinator._schedule_followup_refresh()
        coordinator._schedule_followup_refresh()
        self.assertEqual(len(scheduled_calls), 3)
        self.assertTrue(scheduled_calls[0].cancelled)
        self.assertTrue(scheduled_calls[1].cancelled)
        self.assertFalse(scheduled_calls[2].cancelled)
        for call in scheduled_calls:
            await call.run()
        self.assertEqual(coordinator.refresh_count, 1)
        self.assertIsNone(coordinator._cancel_followup_refresh)

    async def test_unload_cancels_pending_network_refresh(self):
        coordinator = FakeCoordinator()
        coordinator._schedule_followup_refresh()
        coordinator.stop_followup_refresh()
        self.assertTrue(scheduled_calls[-1].cancelled)
        self.assertIsNone(coordinator.api.callback)
        self.assertIsNone(coordinator.api.write_status.callback)
        await scheduled_calls[-1].run()
        self.assertEqual(coordinator.refresh_count, 0)

    async def test_unloaded_coordinator_ignores_new_notifications(self):
        coordinator = FakeCoordinator()
        coordinator.stop_followup_refresh()
        coordinator._schedule_followup_refresh()
        self.assertEqual(scheduled_calls, [])


if __name__ == "__main__":
    unittest.main()
