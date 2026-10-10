"""Track API acknowledgement separately from portal configuration read-back."""
from __future__ import annotations

import copy
import logging
import math
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)
SettingPath = tuple[str | int, ...]


def _values_match(actual: Any, expected: Any) -> bool:
    if type(actual) in (int, float) and type(expected) in (int, float):
        return math.isfinite(actual) and math.isfinite(expected) and actual == expected
    return type(actual) is type(expected) and actual == expected


class SettingsWriteStatus:
    """Keep the latest local settings transaction, without storing credentials."""

    def __init__(self) -> None:
        self.state = "Noch keine Änderung"
        self.attributes: dict[str, Any] = {}
        self.callback: Callable[[], None] | None = None
        self._request_id = 0
        self._expected: dict[SettingPath, Any] = {}
        self._patch_started = False
        self._accepted_mode: tuple[int, float] | None = None
        self._mode_requested = False

    @staticmethod
    def _monotonic() -> float:
        return time.monotonic()

    @property
    def accepted_mode(self) -> tuple[int, float] | None:
        """Temporary UI selection; never replace the reported portal values."""
        if self._accepted_mode is not None and self._monotonic() < self._accepted_mode[1]:
            return self._accepted_mode
        return None

    def _remember_mode(self) -> None:
        if not self._mode_requested:
            return
        for generation in ("g1T", "g2T"):
            mode = self._expected.get((generation, "chargeMode"))
            if type(mode) is int:
                self._accepted_mode = (mode, self._monotonic() + 60)
                return

    def check_mode(
        self, selection: tuple[int, float] | None, wallbox: dict[str, Any]
    ) -> None:
        """A read begun before a newer selection cannot clear that selection."""
        if selection is None or selection != self.accepted_mode:
            return
        for generation in ("g1T", "g2T"):
            settings = wallbox.get(generation)
            if (
                isinstance(settings, dict)
                and _values_match(settings.get("chargeMode"), selection[0])
            ):
                self._accepted_mode = None
                return

    def expire_mode(self, selection: tuple[int, float] | None) -> None:
        if selection == self._accepted_mode:
            self._accepted_mode = None

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
        self._mode_requested = requested.get("charge_mode") is not None
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
        self._remember_mode()
        self.state = "API angenommen – Bestätigung ausstehend"
        self.attributes["HTTP-Status"] = status
        self.attributes["API angenommen um"] = self._now()
        self._notify()

    def unchanged(self) -> None:
        self._remember_mode()
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
        readback: dict[str, Any] = {}
        mismatched: list[str] = []
        for path, expected in self._expected.items():
            actual: Any = wallbox
            present = True
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
                    present = False
                    break
            field = ".".join(str(part) for part in path)
            # Expose only requested scalar fields, never parent configuration.
            scalar = present and (
                actual is None or type(actual) in (str, int, float, bool)
            )
            if type(actual) is float and not math.isfinite(actual):
                scalar = False
            readback[field] = {
                "Wert": actual if scalar else None,
                "Datentyp": type(actual).__name__ if present else "fehlend",
                "Vorhanden": present,
            }
            if not present or not _values_match(actual, expected):
                mismatched.append(field)
        self.attributes["Rückgelesen"] = readback
        self.attributes["Abweichende Felder"] = mismatched
        if wallbox and not mismatched:
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
