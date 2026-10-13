"""Decision logic for HA charging mode 5 (PV self-consumption).

This module has no Home Assistant imports so it can be tested in isolation.
The caller supplies averaged-free raw samples every few seconds; the
controller averages them, applies waits after commands and returns at most
one wallbox command per decision.

A command with ``stage=None`` means "AlphaESS mode 1" (classic surplus
charging). It is used for pauses, SOC protection and sensor faults instead of
a START/STOP event.
"""
# ---------------------------------------------------------------------------
# Community-Build fuer https://www.storion4you.de/
# G2T-Erweiterung fuer SMILE-G3-EVCT11/S: Kavino
# Basierend auf dem Ausgangsprojekt wfa001/SMILE-EVCT11.
# Details und Attribution: siehe NOTICE.md im Paket.
# ---------------------------------------------------------------------------
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping

STRATEGY_STEP = "step"
STRATEGY_DIRECT = "direct"

MODE_SURPLUS = 1
MODE_CUSTOM = 4

SAMPLE_INTERVAL_SECONDS = 5
REACTION_TOLERANCE_SHARE = 0.35

STATE_AVERAGING = "Mittelwert wird gebildet"
STATE_ACTIVE = "Regelung aktiv"
STATE_WAITING_SURPLUS = "Warten auf Überschuss"
STATE_WAITING_WALLBOX = "Warten auf Wallbox-Reaktion"
STATE_SOC_PROTECTION = "SOC-Schutz"
STATE_FALLBACK = "Fallback Sensorfehler"
STATE_RECOVERY = "Sensoren wieder gültig, Rückkehr wird abgewartet"
STATE_NO_VEHICLE = "Kein Fahrzeug angeschlossen"
STATE_SCHEDULE = "Zeitgesteuertes Aufladen aktiv"


@dataclass(frozen=True)
class Stage:
    """One phase/current combination with its stable charging power."""

    phases: int
    current: int
    power: float
    unstable: bool = False

    @property
    def key(self) -> str:
        return f"{self.phases}_{self.current}"

    @property
    def label(self) -> str:
        return f"{self.phases}-phasig {self.current} A"


def _profile_power(profile: Mapping[str, Any], phases: int, current: int) -> float | None:
    values = profile.get(f"power_{phases}p") or {}
    value = values.get(str(current))
    return float(value) if isinstance(value, (int, float)) else None


def build_ladder(profile: Mapping[str, Any]) -> list[Stage]:
    """Return usable stages ordered by power, preferring three phases.

    Single-phase charging has higher losses. A single-phase stage is only
    used below the smallest usable three-phase stage, so whenever the
    budget reaches that stage the ladder continues with three phases only.
    """
    unstable = set(profile.get("unstable_stages") or [])
    excluded = set(profile.get("excluded_stages") or [])
    stages: dict[int, list[Stage]] = {1: [], 3: []}
    for phases in (1, 3):
        for current in range(6, 16):
            key = f"{phases}_{current}"
            power = _profile_power(profile, phases, current)
            if key in excluded or power is None or power <= 0:
                continue
            stages[phases].append(Stage(phases, current, power, key in unstable))
    three = sorted(stages[3], key=lambda s: s.power)
    lowest_three = three[0].power if three else float("inf")
    one = sorted((s for s in stages[1] if s.power < lowest_three), key=lambda s: s.power)
    return one + three


@dataclass
class ControlSettings:
    strategy: str = STRATEGY_STEP
    average_window_seconds: float = 120
    unstable_average_window_seconds: float = 240
    current_change_wait_seconds: float = 40
    phase_change_wait_seconds: float = 90
    allowed_grid_import_w: float = 200
    grid_import_limit_w: float = 500
    grid_import_protection_seconds: float = 50
    reaction_confirm_seconds: float = 10
    surplus_reserve_w: float = 50
    min_battery_soc: float = 20
    battery_soc_hysteresis: float = 5
    sensor_stale_seconds: float = 10
    sensor_recovery_seconds: float = 30

    @classmethod
    def from_options(
        cls, options: Mapping[str, Any], defaults: Mapping[str, Any], strategy_key: str
    ) -> "ControlSettings":
        values: dict[str, Any] = {}
        for name in cls.__dataclass_fields__:
            if name == "strategy":
                continue
            default = defaults[name][0] if name in defaults else getattr(cls, name)
            value = options.get(name, default)
            values[name] = float(value) if isinstance(value, (int, float)) else float(default)
        strategy = options.get(strategy_key, STRATEGY_STEP)
        values["strategy"] = strategy if strategy in (STRATEGY_STEP, STRATEGY_DIRECT) else STRATEGY_STEP
        return cls(**values)


@dataclass
class Measurement:
    """Latest local sensor values in W and %; ``problem`` set when invalid."""

    pv: float = 0.0
    house: float = 0.0
    grid: float = 0.0
    soc: float = 0.0
    problem: str | None = None

    @property
    def valid(self) -> bool:
        return self.problem is None


@dataclass
class WallboxState:
    """Portal view of the wallbox as currently known by the coordinator."""

    connected: bool
    charging: bool
    schedule_active: bool
    mode: int | None
    phases: int | None
    current: int | None
    cloud_power: float | None = None


@dataclass(frozen=True)
class Command:
    """Requested wallbox change. ``stage=None`` selects AlphaESS mode 1."""

    stage: Stage | None
    reason: str


class PVController:
    """Stateful decision maker for one config entry."""

    def __init__(self, profile: Mapping[str, Any], settings: ControlSettings) -> None:
        self.settings = settings
        self.ladder = build_ladder(profile)
        self._profile = profile
        self._samples: deque[tuple[float, float, float, float, float]] = deque()
        self._wait_until = 0.0
        self._command_at = 0.0
        # (expected house load, tolerance) after the last command.
        self._reaction: tuple[float, float] | None = None
        self._reaction_since: float | None = None
        self.expected_house_w: float | None = None
        self.reaction_seconds: float | None = None
        self._valid_since: float | None = None
        self.fallback = False
        self.soc_lock = False
        self.state = STATE_AVERAGING
        self.reason = ""
        self.available_w: float | None = None
        self.target: Stage | None = None
        self.averages: dict[str, float] = {}
        self.window_seconds = settings.average_window_seconds

    # -- helpers ---------------------------------------------------------
    def _set(self, state: str, reason: str = "") -> None:
        self.state = state
        self.reason = reason

    def reset_samples(self) -> None:
        self._samples.clear()
        self.averages = {}

    def current_stage(self, wallbox: WallboxState) -> Stage | None:
        """Return the stage the portal reports, or None outside mode 4."""
        if wallbox.mode != MODE_CUSTOM or wallbox.phases is None or wallbox.current is None:
            return None
        for stage in self.ladder:
            if stage.phases == wallbox.phases and stage.current == wallbox.current:
                return stage
        power = _profile_power(self._profile, wallbox.phases, wallbox.current)
        if power is None:
            power = wallbox.cloud_power or 0.0
        key = f"{wallbox.phases}_{wallbox.current}"
        unstable = key in set(self._profile.get("unstable_stages") or [])
        return Stage(wallbox.phases, wallbox.current, power, unstable)

    def _ladder_index(self, stage: Stage) -> int:
        """Index of the stage, or of the highest ladder stage below it."""
        index = -1
        for position, candidate in enumerate(self.ladder):
            if candidate == stage:
                return position
            if candidate.power <= stage.power:
                index = position
        return index

    def _highest_at_most(self, budget: float) -> Stage | None:
        fitting = [stage for stage in self.ladder if stage.power <= budget]
        return fitting[-1] if fitting else None

    def _step_down(self, current: Stage) -> Stage | None:
        index = self._ladder_index(current)
        if current in self.ladder:
            index -= 1
        return self.ladder[index] if index >= 0 else None

    def _target(self, current: Stage | None, available: float) -> Stage | None:
        reserve = self.settings.surplus_reserve_w
        if self.settings.strategy == STRATEGY_DIRECT:
            best_up = self._highest_at_most(available - reserve)
            if current is None:
                return best_up
            if best_up is not None and best_up.power > current.power:
                return best_up
            if current.power > available or current not in self.ladder:
                return self._highest_at_most(available)
            return current

        if current is None:
            first = self.ladder[0] if self.ladder else None
            return first if first is not None and first.power <= available - reserve else None
        index = self._ladder_index(current)
        following = self.ladder[index + 1] if index + 1 < len(self.ladder) else None
        if following is not None and following.power <= available - reserve:
            return following
        if current.power > available:
            return self._step_down(current)
        if current not in self.ladder:
            return self.ladder[index] if index >= 0 else None
        return current

    # -- early end of the settle time -----------------------------------
    def _clear_reaction(self) -> None:
        self._reaction = None
        self._reaction_since = None
        self.expected_house_w = None

    def _expect_reaction(self, target: Stage) -> None:
        """Derive the house load expected once the wallbox runs ``target``.

        The band is 35 % of the smaller of power change and target power, so
        neither the old load nor the charging pause during a phase change
        (wallbox at 0 W) falls into it. Other consumers that shift the load
        out of the band simply keep the full settle time.
        """
        recent = list(self._samples)[-3:]
        if not recent:
            return
        baseline = sum(sample[2] for sample in recent) / len(recent)
        delta = target.power - recent[-1][4]
        tolerance = REACTION_TOLERANCE_SHARE * min(abs(delta), target.power)
        if tolerance <= 0:
            return
        self._reaction = (baseline + delta, tolerance)
        self.expected_house_w = baseline + delta

    def _reaction_confirmed(self, now: float, house: float) -> bool:
        if self._reaction is None:
            return False
        expected, tolerance = self._reaction
        if abs(house - expected) > tolerance:
            self._reaction_since = None
            return False
        if self._reaction_since is None:
            self._reaction_since = now
        return now - self._reaction_since >= self.settings.reaction_confirm_seconds

    def _command_if_changed(
        self, target: Stage | None, current: Stage | None, wallbox: WallboxState, reason: str
    ) -> Command | None:
        self.target = target
        if target is None:
            if wallbox.mode == MODE_SURPLUS:
                return None
            return Command(None, reason)
        if current is not None and current.key == target.key:
            return None
        return Command(target, reason)

    # -- main entry ------------------------------------------------------
    def update(self, now: float, measurement: Measurement, wallbox: WallboxState) -> Command | None:
        """Process one sample and return a command if a decision is due."""
        s = self.settings
        if wallbox.schedule_active:
            self.reset_samples()
            self._set(STATE_SCHEDULE, "Modus 5 sendet keine Befehle")
            return None

        if not measurement.valid:
            self._valid_since = None
            self._reaction_since = None
            self.reset_samples()
            self._set(STATE_FALLBACK, measurement.problem or "")
            self.fallback = True
            self.target = None
            if wallbox.mode != MODE_SURPLUS and now >= self._wait_until:
                return Command(None, f"Sensorfehler: {measurement.problem}")
            return None

        if self.fallback:
            if self._valid_since is None:
                self._valid_since = now
            if now - self._valid_since < s.sensor_recovery_seconds:
                self._set(STATE_RECOVERY)
                return None
            self.fallback = False
            self._valid_since = None

        if not wallbox.connected:
            self.reset_samples()
            self._set(STATE_NO_VEHICLE)
            return None

        if now < self._wait_until:
            if self._reaction_confirmed(now, measurement.house):
                self.reaction_seconds = now - self._command_at
                self._wait_until = now
                self._clear_reaction()
            else:
                reason = f"noch {int(self._wait_until - now)} s"
                if self._reaction is not None:
                    reason += f", erwartete Hauslast ca. {self._reaction[0]:.0f} W"
                self._set(STATE_WAITING_WALLBOX, reason)
                return None
        elif self._reaction is not None:
            self._clear_reaction()

        current = self.current_stage(wallbox)
        if current is not None:
            wallbox_power = current.power if wallbox.charging else 0.0
        else:
            wallbox_power = (wallbox.cloud_power or 0.0) if wallbox.charging else 0.0

        self._samples.append(
            (now, measurement.pv, measurement.house, measurement.grid, wallbox_power)
        )
        window = (
            s.unstable_average_window_seconds
            if current is not None and current.unstable
            else s.average_window_seconds
        )
        self.window_seconds = window
        while self._samples and self._samples[0][0] < now - window:
            self._samples.popleft()

        count = len(self._samples)
        pv = sum(sample[1] for sample in self._samples) / count
        house = sum(sample[2] for sample in self._samples) / count
        grid = sum(sample[3] for sample in self._samples) / count
        wb = sum(sample[4] for sample in self._samples) / count
        available = pv - (house - wb)
        self.averages = {"pv": pv, "house": house, "grid": grid, "wallbox": wb}
        self.available_w = available
        span = now - self._samples[0][0]

        if measurement.soc < s.min_battery_soc:
            self.soc_lock = True
        elif self.soc_lock and measurement.soc >= s.min_battery_soc + s.battery_soc_hysteresis:
            self.soc_lock = False
        if self.soc_lock:
            self._set(
                STATE_SOC_PROTECTION,
                f"SOC {measurement.soc:.0f} %, Rückkehr ab "
                f"{s.min_battery_soc + s.battery_soc_hysteresis:.0f} %",
            )
            return self._command_if_changed(None, current, wallbox, "SOC unter Mindestwert")

        # The permitted deficit while charging raises the protection limit as
        # well, otherwise the protection would undo the allowance.
        grid_limit = s.allowed_grid_import_w + s.grid_import_limit_w
        # Never wait longer than a full window; the span cannot exceed it.
        protection_span = min(s.grid_import_protection_seconds, window - SAMPLE_INTERVAL_SECONDS)
        if (
            current is not None
            and span >= protection_span
            and grid > grid_limit
        ):
            if s.strategy == STRATEGY_DIRECT:
                target = self._highest_at_most(current.power - (grid - grid_limit))
            else:
                target = self._step_down(current)
            self._set(STATE_ACTIVE, f"Netzbezug Ø {grid:.0f} W über Grenze")
            return self._command_if_changed(
                target, current, wallbox, f"Netzbezug Ø {grid:.0f} W über Grenze"
            )

        if span < window - SAMPLE_INTERVAL_SECONDS:
            self._set(STATE_AVERAGING, f"{int(span)} von {int(window)} s")
            return None

        budget = available + s.allowed_grid_import_w
        reason = f"verfügbar Ø {available:.0f} W"
        if s.allowed_grid_import_w > 0:
            reason += f" + Defizit {s.allowed_grid_import_w:.0f} W"
        target = self._target(current, budget)
        self._set(STATE_WAITING_SURPLUS if target is None else STATE_ACTIVE, reason)
        return self._command_if_changed(target, current, wallbox, reason)

    def command_finished(
        self, now: float, command: Command, previous: Stage | None, success: bool
    ) -> None:
        """Start the settle time after a command and discard old samples."""
        s = self.settings
        self._command_at = now
        self.reaction_seconds = None
        self._clear_reaction()
        if success and command.stage is not None and s.reaction_confirm_seconds > 0:
            self._expect_reaction(command.stage)
        self.reset_samples()
        if not success:
            self._wait_until = now + s.current_change_wait_seconds
            return
        stage = command.stage
        phase_change = (
            stage is None
            or previous is None
            or stage.phases != previous.phases
        )
        self._wait_until = now + (
            s.phase_change_wait_seconds if phase_change else s.current_change_wait_seconds
        )
