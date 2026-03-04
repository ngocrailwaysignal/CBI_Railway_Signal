"""Use case for preparing and starting train simulation on a selected route."""

from __future__ import annotations

from core.domain.model.elements import ApproachSection
from core.domain.model.route import Route
from core.runtime.simulation import Simulation
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from generic_product import GenericProductKernel

from core.application.dto import StartSimulationResult
from .set_route import SetOrReuseRouteUseCase


class StartRouteSimulationUseCase:
    """Ensure route/train are ready, then return animation/runtime metadata."""

    def __init__(self, kernel: GenericProductKernel) -> None:
        self._set_route = SetOrReuseRouteUseCase(kernel)

    @staticmethod
    def _resolve_simulation_start_section(topology: RailwayTopology, route: Route) -> str:
        approach_section = route.approach_locking_section.strip() if route.approach_locking_section else ""
        if approach_section:
            approach_element = topology.get_element(approach_section)
            if isinstance(approach_element, ApproachSection) and approach_element.occupied:
                return approach_section
        return route.path[0]

    @staticmethod
    def _find_train_for_route(simulation: Simulation, route_id: str) -> Train | None:
        for train in simulation.trains.values():
            if train.route_id == route_id:
                return train
        return None

    @staticmethod
    def _next_train_id(simulation: Simulation, prefix: str = "T") -> str:
        index = 1
        while f"{prefix}{index}" in simulation.trains:
            index += 1
        return f"{prefix}{index}"

    def execute(
        self,
        *,
        topology: RailwayTopology,
        simulation: Simulation | None,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
        approach_time_lock_seconds: float,
        overlap_release_seconds: float,
        train_speed: float = 1.0,
    ) -> StartSimulationResult:
        route_result = self._set_route.execute(
            topology=topology,
            simulation=simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
            approach_time_lock_seconds=approach_time_lock_seconds,
            overlap_release_seconds=overlap_release_seconds,
        )
        active_simulation = route_result.simulation
        route = route_result.route

        train = self._find_train_for_route(active_simulation, route.id)
        simulation_start_section = self._resolve_simulation_start_section(topology, route)
        created_train = False
        if train is None:
            train = Train(
                id=self._next_train_id(active_simulation),
                current_section=simulation_start_section,
                speed=float(train_speed),
            )
            active_simulation.add_train(train, route)
            created_train = True
        else:
            simulation_start_section = train.current_section

        visual_route_path = list(route.path)
        if simulation_start_section not in visual_route_path:
            visual_route_path = [simulation_start_section, *visual_route_path]
        extra_steps = 1 if simulation_start_section not in route.full_path else 0
        suggested_ticks = max(3, len(route.full_path) + extra_steps + 2)

        return StartSimulationResult(
            simulation=active_simulation,
            route=route,
            train=train,
            created_route=route_result.created,
            created_train=created_train,
            simulation_start_section=simulation_start_section,
            visual_route_path=visual_route_path,
            suggested_ticks=suggested_ticks,
        )

