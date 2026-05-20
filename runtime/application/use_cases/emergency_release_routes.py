"""Use case for emergency releasing all active routes in one simulation."""

from __future__ import annotations

from runtime.application.dto import CancelRoutesResult
from runtime.application.runtime_session_port import RuntimeSessionPort


class EmergencyReleaseRoutesUseCase:
    """Force-release all active routes while preserving per-route error details."""

    def execute(self, simulation: RuntimeSessionPort | None) -> CancelRoutesResult:
        if simulation is None:
            return CancelRoutesResult()

        route_ids = list(simulation.locking_engine.active_routes.keys())
        if not route_ids:
            return CancelRoutesResult()

        failures: list[str] = []
        for route_id in route_ids:
            try:
                simulation.locking_engine.emergency_release_route(route_id)
            except Exception as exc:
                failures.append(f"{route_id}: {exc}")

        active_after = set(simulation.locking_engine.active_routes.keys())
        for train in simulation.trains.values():
            train_route_id = str(train.route_id or "").strip()
            if train_route_id and train_route_id not in active_after:
                train.route_id = None

        cancelled_routes = len([route_id for route_id in route_ids if route_id not in active_after])
        return CancelRoutesResult(
            attempted_routes=len(route_ids),
            cancelled_routes=cancelled_routes,
            failures=failures,
        )
