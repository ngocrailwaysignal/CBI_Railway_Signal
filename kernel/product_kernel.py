"""Generic Product kernel services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from core.compiler.interlocking_table import InterlockingTableGenerator, InterlockingTableRow
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from kernel.route_dispatcher.route_engine import RouteEngine

if TYPE_CHECKING:
    from runtime.application.runtime_session_port import RuntimeSessionPort


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

    def find_route(
        self,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
        runtime_session: RuntimeSessionPort | None = None,
    ) -> Route:
        """Compute a route candidate using generic route-finding rules."""
        route_engine = RouteEngine(topology)
        active_routes = (
            runtime_session.locking_engine.active_routes if runtime_session is not None else {}
        )
        return route_engine.find_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            active_routes=active_routes,
            overlap_length=(
                self.rules.default_overlap_length if overlap_length is None else overlap_length
            ),
        )

    def set_route(
        self,
        runtime_session: RuntimeSessionPort,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
    ) -> Route:
        """Set and lock a route in one runtime session."""
        return runtime_session.set_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=(
                self.rules.default_overlap_length if overlap_length is None else overlap_length
            ),
        )

    def generate_interlocking_rows(
        self,
        topology: RailwayTopology,
        *,
        overlap_length: int | None = None,
    ) -> list[InterlockingTableRow]:
        """Generate interlocking rows for all signal pairs."""
        overlap = self.rules.default_overlap_length if overlap_length is None else overlap_length
        generator = InterlockingTableGenerator(topology=topology, overlap_length=overlap)
        signals = sorted(topology.signals.keys())
        return generator.generate(entry_signal_ids=signals, exit_signal_ids=signals)
