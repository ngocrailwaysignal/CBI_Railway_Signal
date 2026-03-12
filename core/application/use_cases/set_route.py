"""Use case for setting a route while preserving existing active route when possible."""

from __future__ import annotations

from core.application.runtime_session_port import RuntimeSessionPort
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from products.generic_product import GenericProductKernel

from core.application.dto import SetRouteResult


class SetOrReuseRouteUseCase:
    """Set route for one entry/exit pair, reusing existing active route if available."""

    def __init__(self, kernel: GenericProductKernel) -> None:
        self.kernel = kernel

    @staticmethod
    def _get_active_route_for_pair(
        simulation: RuntimeSessionPort,
        entry_signal_id: str,
        exit_signal_id: str,
    ) -> Route | None:
        for route in simulation.locking_engine.active_routes.values():
            if (
                route.entry_signal_id == entry_signal_id
                and route.exit_signal_id == exit_signal_id
            ):
                return route
        return None

    def execute(
        self,
        *,
        topology: RailwayTopology,
        simulation: RuntimeSessionPort,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
        approach_time_lock_seconds: float,
        overlap_release_seconds: float,
    ) -> SetRouteResult:
        simulation.locking_engine.configure_release_timing(
            approach_time_lock_seconds=approach_time_lock_seconds,
            overlap_release_seconds=overlap_release_seconds,
        )

        existing = self._get_active_route_for_pair(
            simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
        )
        if existing is not None:
            return SetRouteResult(route=existing, created=False)

        route = self.kernel.set_route(
            runtime_session=simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
        )
        return SetRouteResult(route=route, created=True)
