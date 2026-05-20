"""Workspace mode policy for Design/Simulation/Runtime."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AppMode(StrEnum):
    """Logical operating modes used across UI and application layer."""

    DESIGN_LAYOUT = "design_layout"
    SIMULATION = "simulation"
    RUNTIME = "runtime"


@dataclass(slots=True, frozen=True)
class ModeCapabilities:
    """Permissions granted by one operating mode."""

    can_edit_layout: bool
    can_manual_state_override: bool
    can_set_route: bool
    can_cancel_route: bool
    can_start_simulation: bool


@dataclass(slots=True, frozen=True)
class ModeSyncContract:
    """Expected source-of-truth contract per workspace mode."""

    smartio_state_update_applied: bool
    runtime_snapshot_emitted: bool
    local_set_route_allowed: bool
    local_cancel_route_allowed: bool
    local_manual_override_allowed: bool
    local_simulation_step_allowed: bool


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
    _SYNC_AUDIT_MATRIX: dict[AppMode, ModeSyncContract] = {
        AppMode.DESIGN_LAYOUT: ModeSyncContract(
            smartio_state_update_applied=False,
            runtime_snapshot_emitted=False,
            local_set_route_allowed=False,
            local_cancel_route_allowed=False,
            local_manual_override_allowed=True,
            local_simulation_step_allowed=False,
        ),
        AppMode.SIMULATION: ModeSyncContract(
            smartio_state_update_applied=False,
            runtime_snapshot_emitted=False,
            local_set_route_allowed=True,
            local_cancel_route_allowed=True,
            local_manual_override_allowed=True,
            local_simulation_step_allowed=True,
        ),
        AppMode.RUNTIME: ModeSyncContract(
            smartio_state_update_applied=True,
            runtime_snapshot_emitted=True,
            local_set_route_allowed=True,
            local_cancel_route_allowed=True,
            local_manual_override_allowed=False,
            local_simulation_step_allowed=False,
        ),
    }

    def capabilities(self, mode: AppMode) -> ModeCapabilities:
        return self._CAPABILITIES.get(mode, self._CAPABILITIES[AppMode.DESIGN_LAYOUT])

    def layout_edit_locked(self, mode: AppMode) -> bool:
        return not self.capabilities(mode).can_edit_layout

    def runtime_edit_locked(self, mode: AppMode) -> bool:
        return not self.capabilities(mode).can_manual_state_override

    def sync_contract(self, mode: AppMode) -> ModeSyncContract:
        return self._SYNC_AUDIT_MATRIX.get(mode, self._SYNC_AUDIT_MATRIX[AppMode.DESIGN_LAYOUT])
