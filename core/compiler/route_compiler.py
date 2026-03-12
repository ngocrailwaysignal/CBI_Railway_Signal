"""Compile topology into a deterministic interlocking specification."""

from __future__ import annotations

from datetime import UTC, datetime

from core.compiler.spec_models import InterlockingRouteSpec, InterlockingSpec
from core.domain.model.topology import RailwayTopology
from products.generic_product import GenericProductKernel


class RouteCompiler:
    """Build a route/conflict spec from one topology snapshot."""

    SCHEMA_VERSION = 1

    def __init__(self, kernel: GenericProductKernel | None = None) -> None:
        self.kernel = kernel or GenericProductKernel()

    def compile(
        self,
        topology: RailwayTopology,
        *,
        overlap_length: int,
        station_id: str = "UNNAMED",
    ) -> InterlockingSpec:
        rows = self.kernel.generate_interlocking_rows(
            topology=topology,
            overlap_length=max(0, int(overlap_length)),
        )
        routes = [
            InterlockingRouteSpec(
                route_name=row.route_name,
                entry_signal=row.entry_signal,
                exit_signal=row.exit_signal,
                entry_element=row.entry_element,
                exit_element=row.exit_element,
                path=list(row.path),
                overlap=list(row.overlap),
                required_point_positions={
                    point_id: position.value
                    for point_id, position in sorted(row.required_point_positions.items())
                },
                locked_sections=list(row.locked_sections),
                conflicting_routes=sorted(set(row.conflicting_routes)),
            )
            for row in rows
        ]
        clearance_groups = [
            sorted(group)
            for group in sorted(
                (set(group) for group in topology.clearance_conflict_groups if len(group) >= 2),
                key=lambda item: tuple(sorted(item)),
            )
        ]
        generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        return InterlockingSpec(
            schema_version=self.SCHEMA_VERSION,
            generated_at=generated_at,
            station_id=station_id.strip() or "UNNAMED",
            overlap_length=max(0, int(overlap_length)),
            clearance_conflict_groups=clearance_groups,
            routes=routes,
        )
