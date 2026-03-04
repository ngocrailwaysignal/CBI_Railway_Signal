"""Route dispatch/runtime orchestration over route + locking engines."""

from __future__ import annotations

from core.domain.model.route import Route
from core.runtime.locking_engine import LockingEngine
from core.runtime.route_engine import RouteEngine


class RouteDispatcher:
    """Route runtime service for set/cancel/release operations."""

    def __init__(self, route_engine: RouteEngine, locking_engine: LockingEngine) -> None:
        self.route_engine = route_engine
        self.locking_engine = locking_engine

    def find_route(
        self,
        *,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
    ) -> Route:
        return self.route_engine.find_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            active_routes=self.locking_engine.active_routes,
            overlap_length=overlap_length,
        )

    def set_route(
        self,
        *,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
    ) -> Route:
        self.locking_engine.update_time_locking()
        route = self.find_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
        )
        self.locking_engine.lock_route(route)
        return route

    def cancel_route(self, route_id: str) -> None:
        self.locking_engine.cancel_route(route_id)

    def cancel_all_routes(self) -> list[str]:
        failures: list[str] = []
        for route_id in list(self.locking_engine.active_routes.keys()):
            try:
                self.locking_engine.cancel_route(route_id)
            except Exception as exc:  # pragma: no cover - passthrough behavior
                failures.append(f"{route_id}: {exc}")
        self.locking_engine.update_time_locking()
        return failures

    def update_time_locking(self) -> None:
        self.locking_engine.update_time_locking()
