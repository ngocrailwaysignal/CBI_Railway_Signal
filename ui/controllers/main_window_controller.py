"""Controller that adapts MainWindow intents to application use-cases."""

from __future__ import annotations

from generic_application import GenericApplicationService


class MainWindowController:
    """Thin controller facade around GenericApplicationService."""

    def __init__(self, application_service: GenericApplicationService) -> None:
        self.application_service = application_service

    def set_or_reuse_route(self, **kwargs):
        return self.application_service.set_or_reuse_route(**kwargs)

    def start_route_simulation(self, **kwargs):
        return self.application_service.start_route_simulation(**kwargs)

    def cancel_active_routes(self, simulation):
        return self.application_service.cancel_active_routes(simulation)

