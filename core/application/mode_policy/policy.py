"""Workspace mode policy for Design/Simulation/Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AppMode(str, Enum):
    """Logical operating modes used across UI and application layer."""

    DESIGN_LAYOUT = "design_layout"
    SIMULATION = "simulation"
    RUNTIME = "runtime"

    @property
    def title(self) -> str:
        if self is AppMode.DESIGN_LAYOUT:
            return "Design Layout"
        if self is AppMode.SIMULATION:
            return "Simulation"
        return "Runtime"


@dataclass(slots=True, frozen=True)
class ModeCapabilities:
    """Permissions granted by one operating mode."""

    can_edit_layout: bool
    can_manual_state_override: bool
    can_set_route: bool
    can_cancel_route: bool
    can_start_simulation: bool


class ModePolicy:
    """Single source of truth for workspace permissions."""

    _CAPABILITIES: dict[AppMode, ModeCapabilities] = {
        AppMode.DESIGN_LAYOUT: ModeCapabilities(
            can_edit_layout=True,
            can_manual_state_override=True,
            can_set_route=False,
            can_cancel_route=False,
            can_start_simulation=False,
        ),
        AppMode.SIMULATION: ModeCapabilities(
            can_edit_layout=False,
            can_manual_state_override=True,
            can_set_route=True,
            can_cancel_route=True,
            can_start_simulation=True,
        ),
        AppMode.RUNTIME: ModeCapabilities(
            can_edit_layout=False,
            can_manual_state_override=False,
            can_set_route=True,
            can_cancel_route=True,
            can_start_simulation=False,
        ),
    }

    def capabilities(self, mode: AppMode) -> ModeCapabilities:
        return self._CAPABILITIES.get(mode, self._CAPABILITIES[AppMode.DESIGN_LAYOUT])

    def layout_edit_locked(self, mode: AppMode) -> bool:
        return not self.capabilities(mode).can_edit_layout

    def runtime_edit_locked(self, mode: AppMode) -> bool:
        return not self.capabilities(mode).can_manual_state_override

