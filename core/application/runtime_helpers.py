"""Shared runtime helper utilities used by application services/use cases."""

from __future__ import annotations

from core.domain.model.route import Route
from core.domain.model.train import Train
from core.runtime.simulation import Simulation


def get_active_route_for_pair(
    simulation: Simulation,
    entry_signal_id: str,
    exit_signal_id: str,
) -> Route | None:
    """Return active route for one entry/exit pair, if present."""
    for active_route in simulation.locking_engine.active_routes.values():
        if (
            active_route.entry_signal_id == entry_signal_id
            and active_route.exit_signal_id == exit_signal_id
        ):
            return active_route
    return None


def has_active_routes(simulation: Simulation) -> bool:
    """Check whether simulation currently has active locked routes."""
    return bool(simulation.locking_engine.active_routes)


def cancel_all_active_routes(simulation: Simulation) -> list[str]:
    """Try to cancel all active routes; return per-route failures."""
    failures: list[str] = []
    for route_id in list(simulation.locking_engine.active_routes.keys()):
        try:
            simulation.locking_engine.cancel_route(route_id)
        except Exception as exc:
            failures.append(f"{route_id}: {exc}")
    simulation.locking_engine.update_time_locking()
    return failures


def find_train_for_route(simulation: Simulation, route_id: str) -> Train | None:
    """Return train assigned to one route id, if present."""
    for train in simulation.trains.values():
        if train.route_id == route_id:
            return train
    return None


def next_train_id(simulation: Simulation, prefix: str = "T") -> str:
    """Generate the next free train id for one simulation."""
    index = 1
    while f"{prefix}{index}" in simulation.trains:
        index += 1
    return f"{prefix}{index}"

