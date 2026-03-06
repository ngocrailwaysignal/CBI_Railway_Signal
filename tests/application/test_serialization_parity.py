"""Characterization tests for application serializer extraction."""

from __future__ import annotations

from core.application.serialization import build_layout_payload, build_runtime_snapshot
from core.domain.model.elements import Point, Signal, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from core.runtime.simulation import Simulation
from generic_application import GenericApplicationService


def _build_simulation() -> Simulation:
    topology = RailwayTopology()
    topology.add_section(TrackSection(id="A"))
    topology.add_section(TrackSection(id="B"))
    topology.add_point(Point(id="P1"))
    topology.add_signal(Signal(id="S1", protects="A"))
    topology.add_signal(Signal(id="S2", protects="B"))
    topology.connect("A", "B")
    topology.connect("A", "S2")

    simulation = Simulation(topology)
    route = Route(
        id="R1",
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=["A", "B"],
        overlap_path=[],
        required_point_positions={},
    )
    simulation.locking_engine.lock_route(route)
    simulation.add_train(Train(id="T1", current_section="A", speed=1.0), route)
    return simulation


def test_runtime_snapshot_serializer_matches_service_output() -> None:
    simulation = _build_simulation()
    expected = GenericApplicationService.build_runtime_snapshot(simulation)
    actual = build_runtime_snapshot(simulation)
    assert actual == expected


def test_layout_payload_serializer_matches_service_output() -> None:
    simulation = _build_simulation()
    topology = simulation.topology
    expected = GenericApplicationService.build_layout_payload(topology)
    actual = build_layout_payload(topology)
    assert actual == expected

