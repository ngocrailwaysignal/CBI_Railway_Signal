"""SmartIO runtime adapter applies section updates in payload order."""

from __future__ import annotations

import pytest

from core.domain.model.elements import Signal, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.infrastructure.smartio.runtime_adapter import SmartIORuntimeAdapter
from core.runtime.simulation import Simulation


def _build_simulation_with_locked_route() -> tuple[Simulation, Route]:
    topology = RailwayTopology()
    for section_id in ["A", "B", "C"]:
        topology.add_section(TrackSection(id=section_id))
    topology.add_signal(Signal(id="S1", protects="A"))
    topology.add_signal(Signal(id="S2", protects="C"))

    simulation = Simulation(topology)
    route = Route(
        id="R_ADAPTER",
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=["A", "B", "C"],
        overlap_path=[],
        required_point_positions={},
    )
    simulation.locking_engine.lock_route(route)
    return simulation, route


def test_apply_state_update_respects_payload_order_for_sequence_locking() -> None:
    simulation, route = _build_simulation_with_locked_route()
    adapter = SmartIORuntimeAdapter(simulation)

    # Train starts in A first.
    adapter.apply_state_update({"sections": [{"id": "A", "occupied": True}]})

    # Move A -> B must be OCCUPIED(B) before FREE(A).
    adapter.apply_state_update(
        {
            "sections": [
                {"id": "B", "occupied": True},
                {"id": "A", "occupied": False},
            ]
        }
    )

    section_a = simulation.topology.get_element("A")
    section_b = simulation.topology.get_element("B")
    assert isinstance(section_a, TrackSection)
    assert isinstance(section_b, TrackSection)
    assert section_a.locked_by is None
    assert section_b.occupied is True
    assert route.id in simulation.locking_engine.active_routes


def test_apply_state_update_free_before_next_occupied_raises() -> None:
    simulation, route = _build_simulation_with_locked_route()
    adapter = SmartIORuntimeAdapter(simulation)

    adapter.apply_state_update({"sections": [{"id": "A", "occupied": True}]})

    with pytest.raises(RuntimeError, match="Sequence locking violation"):
        adapter.apply_state_update(
            {
                "sections": [
                    {"id": "A", "occupied": False},
                    {"id": "B", "occupied": True},
                ]
            }
        )

    section_a = simulation.topology.get_element("A")
    assert isinstance(section_a, TrackSection)
    assert section_a.locked_by == route.id


def test_apply_state_update_train_relocation_keeps_occupied_before_free() -> None:
    simulation, route = _build_simulation_with_locked_route()
    adapter = SmartIORuntimeAdapter(simulation)

    adapter.apply_state_update(
        {
            "trains": [
                {
                    "id": "T1",
                    "current_section": "A",
                    "route_id": route.id,
                    "speed": 1.0,
                }
            ]
        }
    )

    adapter.apply_state_update(
        {
            "trains": [
                {
                    "id": "T1",
                    "current_section": "B",
                    "route_id": route.id,
                    "speed": 1.0,
                }
            ],
            "sections": [
                {"id": "B", "occupied": True},
                {"id": "A", "occupied": False},
            ],
        }
    )

    section_a = simulation.topology.get_element("A")
    section_b = simulation.topology.get_element("B")
    assert isinstance(section_a, TrackSection)
    assert isinstance(section_b, TrackSection)
    assert section_a.locked_by is None
    assert section_b.occupied is True
