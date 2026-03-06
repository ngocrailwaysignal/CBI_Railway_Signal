"""Unit tests for UI workspace state coordinator."""

from __future__ import annotations

from core.application import AppMode, ModePolicy
from ui.controllers import SmartIOSessionAdapter, WorkspaceStateCoordinator


def test_workspace_state_simulation_mode_enables_route_actions_when_ready() -> None:
    policy = ModePolicy()
    capabilities = policy.capabilities(AppMode.SIMULATION)

    state = WorkspaceStateCoordinator.evaluate(
        capabilities=capabilities,
        has_signals=True,
        selected_pair_defined=True,
        selected_pair_ready=True,
        has_active_routes=True,
        simulation_running=False,
    )

    assert state.find_route_enabled is True
    assert state.set_route_enabled is True
    assert state.cancel_route_enabled is True
    assert state.simulation_enabled is True
    assert state.layout_edit_enabled is False


def test_workspace_state_runtime_mode_blocks_manual_override() -> None:
    policy = ModePolicy()
    capabilities = policy.capabilities(AppMode.RUNTIME)

    state = WorkspaceStateCoordinator.evaluate(
        capabilities=capabilities,
        has_signals=True,
        selected_pair_defined=True,
        selected_pair_ready=False,
        has_active_routes=False,
        simulation_running=False,
    )

    assert state.runtime_override_enabled is False
    assert state.set_route_enabled is True
    assert state.simulation_enabled is False


def test_smartio_session_adapter_normalizes_reconnecting_status() -> None:
    presentation = SmartIOSessionAdapter.presentation(
        operating_mode=AppMode.RUNTIME,
        status_token="reconnecting_in_5s",
    )
    assert presentation.visible is True
    assert presentation.normalized_status == "reconnecting"
    assert presentation.state_key == "smartio.state.reconnecting"

