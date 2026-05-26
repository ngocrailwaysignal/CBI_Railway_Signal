"""Use case for preparing and starting train simulation on a selected route."""

from __future__ import annotations

from core.domain.lifecycle import RouteLifecycleState
from core.domain.model.elements import TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from kernel.product_kernel import GenericProductKernel
from runtime.application.dto import StartSimulationResult
from runtime.application.runtime_helpers import (
    find_idle_train_on_section,
    find_train_for_route,
    next_train_id,
)
from runtime.application.runtime_session_port import RuntimeSessionPort

from .set_route import SetOrReuseRouteUseCase


class StartRouteSimulationUseCase:
    """Ensure route/train are ready, then return animation/runtime metadata."""

    def __init__(self, kernel: GenericProductKernel) -> None:
        self._set_route = SetOrReuseRouteUseCase(kernel)

    @staticmethod
    def _resolve_simulation_start_section(topology: RailwayTopology, route: Route) -> str:
        rear_track_sections: list[str] = []
        for node_id in topology.signal_approach_nodes(route.entry_signal_id):
            element = topology.get_element(node_id)
            if isinstance(element, TrackSection) and node_id not in route.full_path:
                rear_track_sections.append(node_id)

        if rear_track_sections:
            occupied_rear = [
                node_id
                for node_id in rear_track_sections
                if isinstance(topology.get_element(node_id), TrackSection)
                and bool(topology.get_element(node_id).occupied)
            ]
            if occupied_rear:
                return sorted(occupied_rear)[0]
            return sorted(rear_track_sections)[0]
        raise ValueError(
            "Entry signal must have a rear-side track section outside route for train start"
        )

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
        active_simulation = simulation
        route = route_result.route
        if route.lifecycle_state == RouteLifecycleState.RELEASING:
            raise RuntimeError(
                f"Route {entry_signal_id}->{exit_signal_id} is releasing; "
                "wait for overlap release to finish before starting simulation again"
            )

        train = find_train_for_route(active_simulation, route.id)
        simulation_start_section = self._resolve_simulation_start_section(topology, route)
        created_train = False
        if train is None:
            idle_train = find_idle_train_on_section(active_simulation, simulation_start_section)
            if idle_train is not None:
                train = idle_train
                train.traverse_overlap = False
                train.speed = float(train_speed)
                train.assign_route(route, topology, active_simulation.locking_engine)
            else:
                train = Train(
                    id=next_train_id(active_simulation),
                    current_section=simulation_start_section,
                    speed=float(train_speed),
                    traverse_overlap=False,
                )
                active_simulation.add_train(train, route)
                created_train = True
        else:
            train.traverse_overlap = False
            train.relocate_on_route(
                route,
                topology,
                active_simulation.locking_engine,
                new_section=train.current_section,
                speed=train.speed,
            )
            simulation_start_section = train.current_section

        visual_route_path = list(route.path)
        if simulation_start_section not in visual_route_path:
            visual_route_path = [simulation_start_section, *visual_route_path]
        extra_steps = 1 if simulation_start_section not in route.path else 0
        suggested_ticks = max(3, len(route.path) + extra_steps + 2)

        return StartSimulationResult(
            route=route,
            train=train,
            created_route=route_result.created,
            created_train=created_train,
            simulation_start_section=simulation_start_section,
            visual_route_path=visual_route_path,
            suggested_ticks=suggested_ticks,
        )
