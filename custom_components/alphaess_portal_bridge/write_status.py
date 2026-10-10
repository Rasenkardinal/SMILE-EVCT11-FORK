"""Track API acknowledgement separately from portal configuration read-back."""
from __future__ import annotations

import copy
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)
SettingPath = tuple[str | int, ...]


class SettingsWriteStatus:
    """Keep the latest local settings transaction, without storing credentials."""

    def __init__(self) -> None:
        self.state = "Noch keine Änderung"
        self.attributes: dict[str, Any] = {}
        self.callback: Callable[[], None] | None = None
        self._request_id = 0
        self._expected: dict[SettingPath, Any] = {}
        self._patch_started = False

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _notify(self) -> None:
        if self.callback is not None:
            try:
                self.callback()
            except Exception:
                _LOGGER.exception("Unable to notify AlphaESS write-status listeners")

    def begin(self, requested: dict[str, Any]) -> None:
        self._request_id += 1
        self._expected = {}
        self._patch_started = False
        self.state = "Wird gesendet"
        self.attributes = {
            "Auftrag": self._request_id,
            "Gestartet um": self._now(),
            "Angefordert": copy.deepcopy(requested),
        }
        self._notify()

    def prepare(self, expected: dict[SettingPath, Any]) -> None:
        self._expected = copy.deepcopy(expected)
        self.attributes["Angefordert"] = {
            ".".join(str(part) for part in path): value
            for path, value in self._expected.items()
        }

    def transmitting(self) -> None:
        self._patch_started = True
        self.attributes["Gesendet um"] = self._now()
        self._notify()

    def accepted(self, status: int) -> None:
        self.state = "API angenommen – Bestätigung ausstehend"
        self.attributes["HTTP-Status"] = status
        self.attributes["API angenommen um"] = self._now()
        self._notify()

    def unchanged(self) -> None:
        self.state = "Im Portal bestätigt"
        self.attributes["Portal bestätigt um"] = self._now()
        self.attributes["Hinweis zum Auftrag"] = "Werte bereits vorhanden; kein PATCH gesendet"
        self._notify()

    def failed(self, message: str, status: int | None = None, *, rejected: bool = False) -> None:
        if rejected or (status is not None and 400 <= status < 500):
            self.state = "Abgelehnt" if self._patch_started else "Nicht übermittelt"
        elif self._patch_started:
            self.state = "Übermittlung unklar"
        else:
            self.state = "Nicht übermittelt"
        self.attributes["Fehler"] = message
        if status is not None:
            self.attributes["HTTP-Status"] = status
        self._notify()

    @property
    def readback_id(self) -> int | None:
        """Only reads started after this transaction may confirm its values."""
        if self._expected and self.state in {
            "API angenommen – Bestätigung ausstehend",
            "Noch nicht im Portal bestätigt",
            "Übermittlung unklar",
        }:
            return self._request_id
        return None

    def check(self, request_id: int | None, wallbox: dict[str, Any]) -> None:
        if request_id is None or request_id != self.readback_id:
            return
        self.attributes["Letzte Prüfung um"] = self._now()
        self.attributes.pop("Rücklesefehler", None)
        matches = bool(wallbox)
        for path, expected in self._expected.items():
            actual: Any = wallbox
            for part in path:
                if isinstance(actual, dict) and isinstance(part, str) and part in actual:
                    actual = actual[part]
                elif (
                    isinstance(actual, list)
                    and isinstance(part, int)
                    and 0 <= part < len(actual)
                ):
                    actual = actual[part]
                else:
                    matches = False
                    break
            if type(actual) is not type(expected) or actual != expected:
                matches = False
        if matches:
            self.state = "Im Portal bestätigt"
            self.attributes["Portal bestätigt um"] = self._now()
        elif self.state != "Übermittlung unklar":
            self.state = "Noch nicht im Portal bestätigt"
        self._notify()

    def read_failed(self, request_id: int | None, message: str) -> None:
        if request_id is None or request_id != self.readback_id:
            return
        self.attributes["Letzte Prüfung um"] = self._now()
        self.attributes["Rücklesefehler"] = message
        self._notify()
