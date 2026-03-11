"""Read-only runtime state for UI/application consumption."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.domain.model.route import Route
    from core.domain.model.train import Train
    from simulation.session import Simulation


@dataclass(slots=True, frozen=True)
class RuntimeRouteState:
    id: str
    entry_signal_id: str
    exit_signal_id: str
    path: tuple[str, ...]
    overlap_path: tuple[str, ...]
    lifecycle_state: str


@dataclass(slots=True, frozen=True)
class RuntimeTrainState:
    id: str
    current_section: str
    speed: float
    route_id: str | None


@dataclass(slots=True, frozen=True)
class RuntimeOccupancyState:
    id: str
    occupied: bool | None = None
    locked_by: str | None = None
    position: str | None = None


@dataclass(slots=True, frozen=True)
class RuntimeSignalState:
    id: str
    aspect: str
    route_id: str | None


@dataclass(slots=True, frozen=True)
class RuntimeViewState:
    tick: int = 0
    routes: tuple[RuntimeRouteState, ...] = field(default_factory=tuple)
    trains: tuple[RuntimeTrainState, ...] = field(default_factory=tuple)
    occupancy: tuple[RuntimeOccupancyState, ...] = field(default_factory=tuple)
    signal_state: tuple[RuntimeSignalState, ...] = field(default_factory=tuple)

    @property
    def trains_by_id(self) -> dict[str, RuntimeTrainState]:
        return {train.id: train for train in self.trains}


_EMPTY_VIEW_STATE = RuntimeViewState()


def build_runtime_view_state(simulation: "Simulation | None") -> RuntimeViewState:
    if simulation is None:
        return _EMPTY_VIEW_STATE

    topology = simulation.topology
    occupancy: list[RuntimeOccupancyState] = []
    for node_id in topology.graph.nodes:
        element = topology.get_element(node_id)
        if element is None:
            continue
        occupied = bool(getattr(element, "occupied", False)) if hasattr(element, "occupied") else None
        position = getattr(element, "position", None)
        occupancy.append(
            RuntimeOccupancyState(
                id=node_id,
                occupied=occupied,
                locked_by=getattr(element, "locked_by", None),
                position=getattr(position, "value", position),
            )
        )

    routes = tuple(
        RuntimeRouteState(
            id=route.id,
            entry_signal_id=route.entry_signal_id,
            exit_signal_id=route.exit_signal_id,
            path=tuple(route.path),
            overlap_path=tuple(route.overlap_path),
            lifecycle_state=route.lifecycle_state.value,
        )
        for route in simulation.locking_engine.active_routes.values()
    )
    trains = tuple(
        RuntimeTrainState(
            id=train.id,
            current_section=train.current_section,
            speed=float(train.speed),
            route_id=train.route_id,
        )
        for train in simulation.trains.values()
    )
    signal_state = tuple(
        RuntimeSignalState(
            id=signal.id,
            aspect=signal.aspect.value,
            route_id=signal.route_id,
        )
        for signal in topology.signals.values()
    )
    return RuntimeViewState(
        tick=simulation.tick,
        routes=routes,
        trains=trains,
        occupancy=tuple(occupancy),
        signal_state=signal_state,
    )
