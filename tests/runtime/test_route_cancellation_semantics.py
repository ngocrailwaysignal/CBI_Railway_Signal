"""Characterization tests for route cancellation lifecycle semantics."""

from __future__ import annotations

import pytest

from core.domain.model.elements import Signal, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.runtime.locking_engine import LockingEngine


def _build_engine_with_route() -> tuple[LockingEngine, Route]:
    topology = RailwayTopology()
    topology.add_section(TrackSection(id="A"))
    topology.add_section(TrackSection(id="B"))
    topology.add_signal(Signal(id="S1", protects="A"))
    topology.add_signal(Signal(id="S2", protects="B"))

    engine = LockingEngine(topology)
    route = Route(
        id="R_CANCEL",
        entry_signal_id="S1",
        exit_signal_id="S2",
        path=["A", "B"],
        overlap_path=[],
        required_point_positions={},
    )
    engine.lock_route(route)
    return engine, route


def test_cancel_route_succeeds_when_route_unoccupied() -> None:
    engine, route = _build_engine_with_route()
    engine.cancel_route(route.id)
    assert route.id not in engine.active_routes


def test_cancel_route_fails_when_route_has_occupied_section() -> None:
    engine, route = _build_engine_with_route()
    engine.set_section_occupied("A", True, route_id_hint=route.id)

    with pytest.raises(RuntimeError, match="occupied by train"):
        engine.cancel_route(route.id)

    assert route.id in engine.active_routes

