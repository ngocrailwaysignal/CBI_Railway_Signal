"""Tests for shared runtime helper utilities."""

from __future__ import annotations

from core.application.runtime_helpers import (
    find_train_for_route,
    get_active_route_for_pair,
    next_train_id,
)
from core.domain.model.elements import Signal, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from core.runtime.simulation import Simulation


def _build_locked_simulation() -> tuple[Simulation, Route]:
    topology = RailwayTopology()
    topology.add_section(TrackSection(id="A"))
    topology.add_section(TrackSection(id="B"))
    topology.add_signal(Signal(id="S1", protects="A"))
    topology.add_signal(Signal(id="S2", protects="B"))
    simulation = Simulation(topology)
    route = Route(
        id="R_HELP",
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=["A", "B"],
        overlap_path=[],
        required_point_positions={},
    )
    simulation.locking_engine.lock_route(route)
    return simulation, route


def test_get_active_route_for_pair_returns_matching_route() -> None:
    simulation, route = _build_locked_simulation()
    found = get_active_route_for_pair(simulation, "S1", "S2")
    assert found is not None
    assert found.id == route.id


def test_find_train_for_route_and_next_train_id() -> None:
    simulation, route = _build_locked_simulation()
    simulation.add_train(Train(id="T1", current_section="A", speed=1.0), route)
    simulation.trains["T2"] = Train(id="T2", current_section="B", speed=0.5, route_id=None)

    found = find_train_for_route(simulation, route.id)
    assert found is not None
    assert found.id == "T1"
    assert next_train_id(simulation) == "T3"

