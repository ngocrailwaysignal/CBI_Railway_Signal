"""Safety tests for route cancellation while a train is on the route."""

from __future__ import annotations

import unittest
from pathlib import Path

from core.elements import TrackSection
from core.simulation import Simulation
from core.topology import RailwayTopology
from core.train import Train


def _load_topology() -> RailwayTopology:
    repo_root = Path(__file__).resolve().parents[1]
    return RailwayTopology.load_from_json(
        repo_root / "data" / "test2.json",
        load_runtime_state=False,
        load_occupancy=True,
    )


class CancelRouteSafetyTests(unittest.TestCase):
    def test_time_lock_update_does_not_unlock_occupied_route(self) -> None:
        topology = _load_topology()
        simulation = Simulation(topology)
        simulation.locking_engine.configure_release_timing(approach_time_lock_seconds=0.0)

        route = simulation.set_route("A", "G2", overlap_length=0)
        train = Train(id="T1", current_section=route.path[0], speed=1.0)
        simulation.add_train(train, route)

        with self.assertRaisesRegex(RuntimeError, "Approach locking active"):
            simulation.locking_engine.cancel_route(route.id)

        simulation.locking_engine.update_time_locking()
        self.assertIn(route.id, simulation.locking_engine.active_routes)

        first_section = topology.get_element(route.path[0])
        self.assertIsInstance(first_section, TrackSection)
        assert isinstance(first_section, TrackSection)
        self.assertTrue(first_section.occupied)
        self.assertEqual(first_section.locked_by, route.id)
        self.assertEqual(topology.signals["A"].route_id, route.id)

    def test_cancel_route_rejected_when_train_is_on_route(self) -> None:
        topology = _load_topology()
        simulation = Simulation(topology)
        simulation.locking_engine.configure_release_timing(approach_time_lock_seconds=0.0)

        route = simulation.set_route("A", "G2", overlap_length=0)
        train = Train(id="T1", current_section=route.path[0], speed=1.0)
        simulation.add_train(train, route)

        with self.assertRaisesRegex(RuntimeError, "Approach locking active"):
            simulation.locking_engine.cancel_route(route.id)
        with self.assertRaisesRegex(RuntimeError, "occupied by train on sections"):
            simulation.locking_engine.cancel_route(route.id)

        self.assertIn(route.id, simulation.locking_engine.active_routes)

    def test_time_locked_route_can_still_release_when_clear(self) -> None:
        topology = _load_topology()
        simulation = Simulation(topology)
        simulation.locking_engine.configure_release_timing(approach_time_lock_seconds=0.0)

        route = simulation.set_route("A", "G2", overlap_length=0)
        simulation.locking_engine.approach_locking.mark_approach_locked(route.id)

        with self.assertRaisesRegex(RuntimeError, "Approach locking active"):
            simulation.locking_engine.cancel_route(route.id)

        simulation.locking_engine.update_time_locking()
        self.assertNotIn(route.id, simulation.locking_engine.active_routes)
        self.assertIsNone(topology.signals["A"].route_id)


if __name__ == "__main__":
    unittest.main()
