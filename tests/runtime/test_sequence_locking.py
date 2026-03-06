"""Sequence-locking safety behavior for route sectional release."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from core.domain.model.elements import Signal, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.runtime.locking_engine import LockingEngine
from core.runtime.simulation import Simulation
from core.domain.model.train import Train


@dataclass
class FakeClock:
    """Deterministic clock used for overlap-release tests."""

    current: float = 0.0

    def now(self) -> float:
        return float(self.current)

    def advance(self, delta_seconds: float) -> None:
        self.current += float(delta_seconds)


def _build_topology(section_ids: list[str]) -> RailwayTopology:
    topology = RailwayTopology()
    for section_id in section_ids:
        topology.add_section(TrackSection(id=section_id))
    topology.add_signal(Signal(id="S1", protects=section_ids[0]))
    topology.add_signal(Signal(id="S2", protects=section_ids[-1]))
    return topology


def _build_route(
    section_ids: list[str],
    route_id: str = "R_SEQ",
    *,
    overlap_ids: list[str] | None = None,
) -> Route:
    return Route(
        id=route_id,
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=list(section_ids),
        overlap_path=list(overlap_ids or []),
        required_point_positions={},
    )


def _section(topology: RailwayTopology, section_id: str) -> TrackSection:
    element = topology.get_element(section_id)
    assert isinstance(element, TrackSection)
    return element


def test_sequence_release_requires_next_section_occupied_evidence() -> None:
    topology = _build_topology(["A", "B", "C"])
    route = _build_route(["A", "B", "C"], route_id="R_SEQ_3")
    engine = LockingEngine(topology)
    engine.lock_route(route)

    engine.set_section_occupied("A", True, route_id_hint=route.id)
    engine.set_section_occupied("B", True, route_id_hint=route.id)
    engine.set_section_occupied("A", False, route_id_hint=route.id)
    assert _section(topology, "A").locked_by is None

    engine.set_section_occupied("C", True, route_id_hint=route.id)
    engine.set_section_occupied("B", False, route_id_hint=route.id)
    assert _section(topology, "B").locked_by is None


def test_lost_shunt_free_event_raises_immediately_and_keeps_lock() -> None:
    topology = _build_topology(["A", "B", "C"])
    route = _build_route(["A", "B", "C"], route_id="R_SHUNT")
    engine = LockingEngine(topology)
    engine.lock_route(route)

    engine.set_section_occupied("A", True, route_id_hint=route.id)
    with pytest.raises(RuntimeError, match="Sequence locking violation"):
        engine.set_section_occupied("A", False, route_id_hint=route.id)
    assert _section(topology, "A").locked_by == route.id

    # No auto-retry: after evidence appears, caller must request release again.
    engine.set_section_occupied("B", True, route_id_hint=route.id)
    assert _section(topology, "A").locked_by == route.id
    engine.set_section_occupied("A", False, route_id_hint=route.id)
    assert _section(topology, "A").locked_by is None


def test_single_section_route_free_without_prior_occupied_raises() -> None:
    topology = _build_topology(["A"])
    route = _build_route(["A"], route_id="R_SINGLE")
    engine = LockingEngine(topology)
    engine.lock_route(route)

    with pytest.raises(RuntimeError, match="Sequence locking violation"):
        engine.set_section_occupied("A", False, route_id_hint=route.id)
    assert _section(topology, "A").locked_by == route.id

    engine.set_section_occupied("A", True, route_id_hint=route.id)
    engine.set_section_occupied("A", False, route_id_hint=route.id)
    assert route.id not in engine.active_routes
    assert _section(topology, "A").locked_by is None


def test_overlap_release_timer_starts_after_main_path_complete() -> None:
    topology = _build_topology(["A", "B", "C"])
    route = _build_route(["A", "B"], route_id="R_OVERLAP", overlap_ids=["C"])
    clock = FakeClock(current=100.0)
    engine = LockingEngine(topology, overlap_release_seconds=5.0, clock=clock)
    engine.lock_route(route)

    engine.set_section_occupied("A", True, route_id_hint=route.id)
    engine.set_section_occupied("B", True, route_id_hint=route.id)
    engine.set_section_occupied("A", False, route_id_hint=route.id)

    assert route.id in engine.active_routes
    assert _section(topology, "B").locked_by == route.id
    assert _section(topology, "C").locked_by == route.id

    clock.advance(4.0)
    engine.update_time_locking()
    assert route.id in engine.active_routes

    clock.advance(1.1)
    engine.update_time_locking()
    assert route.id not in engine.active_routes
    assert _section(topology, "B").locked_by is None
    assert _section(topology, "C").locked_by is None


def test_overlap_route_releases_without_any_overlap_occupied_event() -> None:
    topology = _build_topology(["A", "B", "C"])
    route = _build_route(["A", "B"], route_id="R_OVERLAP_NO_OCC", overlap_ids=["C"])
    clock = FakeClock(current=50.0)
    engine = LockingEngine(topology, overlap_release_seconds=2.0, clock=clock)
    engine.lock_route(route)

    engine.set_section_occupied("A", True, route_id_hint=route.id)
    engine.set_section_occupied("B", True, route_id_hint=route.id)
    engine.set_section_occupied("A", False, route_id_hint=route.id)

    # Overlap section C never receives occupied=True.
    assert _section(topology, "C").occupied is False
    assert route.id in engine.active_routes

    clock.advance(2.1)
    engine.update_time_locking()

    assert route.id not in engine.active_routes
    assert _section(topology, "C").locked_by is None


def test_simulation_set_section_occupied_propagates_sequence_error() -> None:
    topology = _build_topology(["A", "B", "C"])
    route = _build_route(["A", "B", "C"], route_id="R_SIM")
    simulation = Simulation(topology)
    simulation.locking_engine.lock_route(route)

    simulation.set_section_occupied("A", True, route_id_hint=route.id)
    with pytest.raises(RuntimeError, match="Sequence locking violation"):
        simulation.set_section_occupied("A", False, route_id_hint=route.id)


def test_train_can_stop_at_main_path_without_entering_overlap() -> None:
    topology = _build_topology(["A", "B", "C"])
    route = _build_route(["A", "B"], route_id="R_MAIN_ONLY", overlap_ids=["C"])
    simulation = Simulation(topology)
    simulation.locking_engine.lock_route(route)
    train = Train(id="T_MAIN_ONLY", current_section="A", speed=1.0, traverse_overlap=False)
    simulation.add_train(train, route)

    simulation.step()
    assert train.current_section == "B"
    assert train.route_id == route.id

    simulation.step()
    assert train.current_section == "B"
    assert train.route_id is None
