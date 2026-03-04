"""Generic Product kernel services."""

from __future__ import annotations

from dataclasses import dataclass

from core.compiler.interlocking_table import InterlockingTableGenerator, InterlockingTableRow
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.runtime.route_engine import RouteEngine
from core.runtime.simulation import Simulation


@dataclass(slots=True, frozen=True)
class ProductRules:
    """Generic product defaults shared by all deployments."""

    time_lock_seconds: float = 30.0
    default_overlap_length: int = 0
    overlap_release_seconds: float = 0.0


class GenericProductKernel:
    """Reusable interlocking kernel with no station-specific assumptions."""

    def __init__(self, rules: ProductRules | None = None) -> None:
        self.rules = rules or ProductRules()

    def create_simulation(self, topology: RailwayTopology) -> Simulation:
        """Create a simulation engine configured with product defaults."""
        simulation = Simulation(topology)
        simulation.locking_engine.configure_release_timing(
            approach_time_lock_seconds=float(self.rules.time_lock_seconds),
            overlap_release_seconds=float(self.rules.overlap_release_seconds),
        )
        return simulation

    def find_route(
        self,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
        simulation: Simulation | None = None,
    ) -> Route:
        """Compute a route candidate using generic route-finding rules."""
        route_engine = RouteEngine(topology)
        active_routes = (
            simulation.locking_engine.active_routes if simulation is not None else {}
        )
        return route_engine.find_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            active_routes=active_routes,
            overlap_length=(
                self.rules.default_overlap_length
                if overlap_length is None
                else overlap_length
            ),
        )

    def set_route(
        self,
        simulation: Simulation,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
    ) -> Route:
        """Set and lock a route in one simulation instance."""
        return simulation.set_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=(
                self.rules.default_overlap_length
                if overlap_length is None
                else overlap_length
            ),
        )

    def generate_interlocking_rows(
        self,
        topology: RailwayTopology,
        *,
        overlap_length: int | None = None,
    ) -> list[InterlockingTableRow]:
        """Generate interlocking rows for all signal pairs."""
        overlap = (
            self.rules.default_overlap_length
            if overlap_length is None
            else overlap_length
        )
        generator = InterlockingTableGenerator(topology=topology, overlap_length=overlap)
        signals = sorted(topology.signals.keys())
        return generator.generate(entry_signal_ids=signals, exit_signal_ids=signals)
