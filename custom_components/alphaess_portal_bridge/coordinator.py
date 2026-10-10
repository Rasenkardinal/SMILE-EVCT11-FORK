"""Data coordinator for AlphaESS Wallbox Bridge."""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------
from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import AlphaESSPortalApi, AuthenticationError, PortalConnectionError
from .const import DEFAULT_UPDATE_INTERVAL_SECONDS, DOMAIN, UPDATE_INTERVAL_OPTIONS

_LOGGER = logging.getLogger(__name__)
_POST_WRITE_READBACK_SECONDS = 3


class AlphaESSWallboxCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch the current wallbox state from the AlphaESS customer portal."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: AlphaESSPortalApi,
        update_interval_seconds: int = DEFAULT_UPDATE_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=(
                    update_interval_seconds
                    if update_interval_seconds in UPDATE_INTERVAL_OPTIONS
                    else DEFAULT_UPDATE_INTERVAL_SECONDS
                )
            ),
        )
        self.api = api
        self._cancel_followup_refresh: Callable[[], None] | None = None
        self._stopped = False
        self._cancel_mode_expiry: Callable[[], None] | None = None
        self._mode_selection: tuple[int, float] | None = None
        self.api.set_settings_written_callback(self._schedule_followup_refresh)
        self.api.write_status.callback = self._write_status_changed

    def _write_status_changed(self) -> None:
        if self._stopped:
            return
        selection = self.api.write_status.accepted_mode
        if selection != self._mode_selection:
            if self._cancel_mode_expiry is not None:
                self._cancel_mode_expiry()
                self._cancel_mode_expiry = None
            self._mode_selection = selection
            if selection is not None:
                self._cancel_mode_expiry = async_call_later(
                    self.hass, max(0, selection[1] - time.monotonic()),
                    self._mode_expired,
                )
        self.async_update_listeners()

    def _mode_expired(self, _now: Any) -> None:
        self.api.write_status.expire_mode(self._mode_selection)
        self._cancel_mode_expiry = None
        self._mode_selection = None
        if not self._stopped:
            self.async_update_listeners()

    def _schedule_followup_refresh(self) -> None:
        """Read back accepted settings after portal propagation, without waiting.

        Multiple rapid PATCH responses reset a single timer, so an update burst
        triggers only one additional refresh. This is a portal read-back, not
        confirmation of a physical current or phase change.
        """
        if self._stopped:
            return
        if self._cancel_followup_refresh is not None:
            self._cancel_followup_refresh()
        self._cancel_followup_refresh = async_call_later(
            self.hass, _POST_WRITE_READBACK_SECONDS, self._async_followup_refresh
        )

    async def _async_followup_refresh(self, _now: Any) -> None:
        self._cancel_followup_refresh = None
        if not self._stopped:
            await self.async_request_refresh()

    def stop_followup_refresh(self) -> None:
        """Prevent scheduled API traffic after the config entry is unloaded."""
        self._stopped = True
        self.api.set_settings_written_callback(None)
        self.api.write_status.callback = None
        if self._cancel_mode_expiry is not None:
            self._cancel_mode_expiry()
            self._cancel_mode_expiry = None
        if self._cancel_followup_refresh is not None:
            self._cancel_followup_refresh()
            self._cancel_followup_refresh = None

    async def _async_update_data(self) -> dict[str, Any]:
        readback_id = self.api.write_status.readback_id
        mode_selection = self.api.write_status.accepted_mode
        try:
            data = await self.api.async_get_wallbox_data()
            # Retire the bridge only when this complete snapshot is about to
            # replace coordinator.data, not during the earlier config GET.
            self.api.write_status.check_mode(
                mode_selection,
                self.api._find_wallbox_data(
                    data["configuration"], data["wallbox_serial"]
                ),
            )
            return data
        except (AuthenticationError, PortalConnectionError) as err:
            self.api.write_status.read_failed(readback_id, str(err))
            _LOGGER.warning(
                "AlphaESS wallbox refresh failed during %s with status %s",
                err.step,
                getattr(err, "status", "authorization"),
            )
            raise UpdateFailed(f"AlphaESS wallbox refresh failed during {err.step}") from err
