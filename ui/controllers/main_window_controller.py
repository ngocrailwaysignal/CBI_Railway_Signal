"""Controller that adapts MainWindow intents to application/runtime workspace services."""

from __future__ import annotations

from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from runtime import GenericApplicationService, RuntimeViewState, RuntimeWorkspaceService


class MainWindowController:
    """Facade around application and runtime workspace services."""

    def __init__(
        self,
        application_service: GenericApplicationService,
        runtime_workspace_service: RuntimeWorkspaceService,
    ) -> None:
        self.application_service = application_service
        self.runtime_workspace_service = runtime_workspace_service

    @property
    def has_runtime_session(self) -> bool:
        return self.runtime_workspace_service.has_session

    def clear_runtime_session(self) -> None:
        self.runtime_workspace_service.clear_session()

    def runtime_view_state(self) -> RuntimeViewState:
        return self.runtime_workspace_service.runtime_view_state()

    def find_route(self, **kwargs):
        return self.runtime_workspace_service.find_route(**kwargs)

    def set_or_reuse_route(self, **kwargs):
        return self.runtime_workspace_service.set_or_reuse_route(**kwargs)

    def start_route_simulation(self, **kwargs):
        return self.runtime_workspace_service.start_route_simulation(**kwargs)

    def cancel_active_routes(self):
        return self.runtime_workspace_service.cancel_active_routes()

    def emergency_release_active_routes(self):
        return self.runtime_workspace_service.emergency_release_active_routes()

    def manual_set_section_occupied(self, **kwargs):
        return self.runtime_workspace_service.manual_set_section_occupied(**kwargs)

    def update_time_locking(self) -> None:
        self.runtime_workspace_service.update_time_locking()

    def configure_timing(self, **kwargs) -> None:
        self.runtime_workspace_service.configure_timing(**kwargs)

    def get_active_route_for_pair(self, entry_signal_id: str, exit_signal_id: str) -> Route | None:
        return self.runtime_workspace_service.get_active_route_for_pair(
            entry_signal_id, exit_signal_id
        )

    def has_active_routes(self) -> bool:
        return self.runtime_workspace_service.has_active_routes()

    def active_route_for_section(self, section_id: str) -> Route | None:
        return self.runtime_workspace_service.active_route_for_section(section_id)

    def approach_lock_details(self, route_id: str) -> tuple[str | None, float | None]:
        return self.runtime_workspace_service.approach_lock_details(route_id)

    def ensure_runtime_session(self, topology: RailwayTopology):
        return self.runtime_workspace_service.ensure_session(topology)

    def step_runtime(self) -> RuntimeViewState:
        return self.runtime_workspace_service.step()

    def build_runtime_snapshot(self) -> dict:
        return self.runtime_workspace_service.build_runtime_snapshot()
