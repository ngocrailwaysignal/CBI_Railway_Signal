"""Characterization tests for Simulation runtime command gateway."""

from __future__ import annotations

import types

from core.domain.model.elements import Signal, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.runtime.simulation import Simulation


def _build_simulation() -> Simulation:
    topology = RailwayTopology()
    topology.add_section(TrackSection(id="A"))
    topology.add_section(TrackSection(id="B"))
    topology.add_signal(Signal(id="S1", protects="A"))
    topology.add_signal(Signal(id="S2", protects="B"))
    return Simulation(topology)


def test_apply_runtime_command_upsert_and_remove_train() -> None:
    simulation = _build_simulation()

    train = simulation.apply_runtime_command(
        "upsert_train",
        {
            "train_id": "T1",
            "current_section": "A",
            "route_id": None,
            "speed": 1.5,
        },
    )
    section = simulation.topology.get_element("A")

    assert train.id == "T1"
    assert "T1" in simulation.trains
    assert getattr(section, "occupied", False) is True

    removed = simulation.apply_runtime_command("remove_train", {"train_id": "T1"})
    assert removed is True
    assert "T1" not in simulation.trains


def test_apply_runtime_command_cancel_route() -> None:
    simulation = _build_simulation()
    route = Route(
        id="R_CANCEL",
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=["A", "B"],
        overlap_path=[],
        required_point_positions={},
    )
    simulation.locking_engine.lock_route(route)

    simulation.apply_runtime_command("cancel_route", {"route_id": route.id})

    assert route.id not in simulation.locking_engine.active_routes


def test_apply_runtime_command_set_route_delegates_to_simulation_set_route() -> None:
    simulation = _build_simulation()

    expected_route = Route(
        id="R_STUB",
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=["A", "B"],
        overlap_path=[],
        required_point_positions={},
    )

    def _stub_set_route(self: Simulation, entry_signal_id: str, exit_signal_id: str, overlap_length: int = 0) -> Route:
        assert entry_signal_id == "S1"
        assert exit_signal_id == "S2"
        assert overlap_length == 1
        return expected_route

    simulation.set_route = types.MethodType(_stub_set_route, simulation)
    result = simulation.apply_runtime_command(
        "set_route",
        {"entry_signal_id": "S1", "exit_signal_id": "S2", "overlap_length": 1},
    )
    assert result is expected_route


def test_apply_runtime_command_hydrate_snapshot_delegates_to_hydrator() -> None:
    simulation = _build_simulation()
    captured: list[tuple[dict, bool]] = []

    def _stub_hydrate(
        self: Simulation,
        *,
        snapshot: dict,
        strict_route_ids: bool = True,
    ) -> None:
        captured.append((snapshot, strict_route_ids))

    simulation.hydrate_snapshot = types.MethodType(_stub_hydrate, simulation)
    payload = {"tick": 7, "routes": [], "trains": [], "occupancy": [], "signal_state": []}
    simulation.apply_runtime_command(
        "hydrate_snapshot",
        {"snapshot": payload, "strict_route_ids": False},
    )

    assert captured == [(payload, False)]

