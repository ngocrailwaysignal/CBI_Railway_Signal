"""Workspace state coordinator for MainWindow UI enablement decisions."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.application import ModeCapabilities


@dataclass(slots=True, frozen=True)
class WorkspaceState:
    """Computed control state for one UI synchronization cycle."""

    find_route_enabled: bool
    set_route_enabled: bool
    cancel_route_enabled: bool
    simulation_enabled: bool
    simulation_running: bool
    layout_edit_enabled: bool
    connect_mode_enabled: bool
    runtime_override_enabled: bool
    route_timing_enabled: bool


class WorkspaceStateCoordinator:
    """Computes UI state from mode capabilities and runtime conditions."""

    @staticmethod
    def evaluate(
        *,
        capabilities: ModeCapabilities,
        has_signals: bool,
        selected_pair_defined: bool,
        selected_pair_ready: bool,
        has_active_routes: bool,
        simulation_running: bool,
    ) -> WorkspaceState:
        set_route_enabled = (
            capabilities.can_set_route
            and has_signals
            and selected_pair_defined
            and not simulation_running
        )
        simulation_enabled = capabilities.can_start_simulation and (
            simulation_running or selected_pair_ready
        )
        return WorkspaceState(
            find_route_enabled=has_signals and selected_pair_defined,
            set_route_enabled=set_route_enabled,
            cancel_route_enabled=capabilities.can_cancel_route and has_active_routes,
            simulation_enabled=simulation_enabled,
            simulation_running=simulation_running,
            layout_edit_enabled=capabilities.can_edit_layout,
            connect_mode_enabled=capabilities.can_edit_layout,
            runtime_override_enabled=capabilities.can_manual_state_override,
            route_timing_enabled=capabilities.can_set_route,
        )

