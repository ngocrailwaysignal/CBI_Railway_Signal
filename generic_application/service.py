"""Application-level orchestration for reusable interlocking simulation."""

from __future__ import annotations

from pathlib import Path

from core.interlocking_table import InterlockingTableRow
from core.route_engine import Route
from core.simulation import Simulation
from core.topology import RailwayTopology
from core.train import Train
from generic_product import GenericProductKernel

from .profile import GenericApplicationProfile


class GenericApplicationService:
    """Bridges generic product kernel with an operational profile."""

    def __init__(
        self,
        profile: GenericApplicationProfile | None = None,
        kernel: GenericProductKernel | None = None,
    ) -> None:
        self.profile = profile or GenericApplicationProfile()
        self.kernel = kernel or GenericProductKernel(self.profile.to_product_rules())

    def load_topology(
        self,
        path: str | Path,
        *,
        load_runtime_state: bool | None = None,
        load_occupancy: bool | None = None,
    ) -> RailwayTopology:
        """Load one station layout with application defaults."""
        return RailwayTopology.load_from_json(
            path,
            load_runtime_state=(
                self.profile.load_runtime_state
                if load_runtime_state is None
                else load_runtime_state
            ),
            load_occupancy=(
                self.profile.load_occupancy
                if load_occupancy is None
                else load_occupancy
            ),
        )

    def save_topology(
        self,
        topology: RailwayTopology,
        path: str | Path,
        *,
        include_runtime_state: bool | None = None,
        include_occupancy: bool | None = None,
    ) -> None:
        """Save one station layout with application defaults."""
        topology.export_to_json(
            path,
            include_runtime_state=(
                self.profile.include_runtime_state
                if include_runtime_state is None
                else include_runtime_state
            ),
            include_occupancy=(
                self.profile.include_occupancy
                if include_occupancy is None
                else include_occupancy
            ),
        )

    def create_simulation(self, topology: RailwayTopology) -> Simulation:
        """Create simulation using product rules configured by profile."""
        return self.kernel.create_simulation(topology)

    def find_route(
        self,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
        simulation: Simulation | None = None,
    ) -> Route:
        """Find one route candidate using application defaults."""
        return self.kernel.find_route(
            topology=topology,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
            simulation=simulation,
        )

    def set_route(
        self,
        simulation: Simulation,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
    ) -> Route:
        """Set one route in simulation using application defaults."""
        return self.kernel.set_route(
            simulation=simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
        )

    def generate_interlocking_rows(
        self,
        topology: RailwayTopology,
        *,
        overlap_length: int | None = None,
    ) -> list[InterlockingTableRow]:
        """Generate interlocking rows using application defaults."""
        return self.kernel.generate_interlocking_rows(
            topology=topology,
            overlap_length=overlap_length,
        )

    @staticmethod
    def validate_signal_pair(
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
    ) -> list[str]:
        """Validate route request against topology constraints."""
        return topology.validate_signal_pair(entry_signal_id, exit_signal_id)

    @staticmethod
    def get_active_route_for_pair(
        simulation: Simulation,
        entry_signal_id: str,
        exit_signal_id: str,
    ) -> Route | None:
        """Return active route for one entry/exit pair, if present."""
        for active_route in simulation.locking_engine.active_routes.values():
            if (
                active_route.entry_signal_id == entry_signal_id
                and active_route.exit_signal_id == exit_signal_id
            ):
                return active_route
        return None

    @staticmethod
    def has_active_routes(simulation: Simulation) -> bool:
        """Check whether simulation currently has active locked routes."""
        return bool(simulation.locking_engine.active_routes)

    @staticmethod
    def update_time_locking(simulation: Simulation) -> None:
        """Advance time-lock release checks for active routes."""
        simulation.locking_engine.update_time_locking()

    @staticmethod
    def cancel_all_active_routes(simulation: Simulation) -> list[str]:
        """Try to cancel all active routes; return per-route failures."""
        failures: list[str] = []
        for route_id in list(simulation.locking_engine.active_routes.keys()):
            try:
                simulation.locking_engine.cancel_route(route_id)
            except Exception as exc:
                failures.append(f"{route_id}: {exc}")
        simulation.locking_engine.update_time_locking()
        return failures

    @staticmethod
    def find_train_for_route(simulation: Simulation, route_id: str) -> Train | None:
        """Return train assigned to one route id, if present."""
        for train in simulation.trains.values():
            if train.route_id == route_id:
                return train
        return None

    @staticmethod
    def next_train_id(simulation: Simulation, prefix: str = "T") -> str:
        """Generate the next free train id for one simulation."""
        index = 1
        while f"{prefix}{index}" in simulation.trains:
            index += 1
        return f"{prefix}{index}"

    @staticmethod
    def configure_simulation_timing(
        simulation: Simulation,
        *,
        approach_time_lock_seconds: float | None = None,
        overlap_release_seconds: float | None = None,
    ) -> None:
        """Apply runtime timing parameters to one simulation."""
        simulation.locking_engine.configure_release_timing(
            approach_time_lock_seconds=approach_time_lock_seconds,
            overlap_release_seconds=overlap_release_seconds,
        )
