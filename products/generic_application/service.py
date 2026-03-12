"""Application-level orchestration for reusable interlocking simulation."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from core.application import ModePolicy
from core.application.serialization import build_layout_payload
from core.compiler import InterlockingSpec, RouteCompiler
from core.compiler.interlocking_table import InterlockingTableRow
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.infrastructure.persistence import (
    InterlockingSpecRepository,
    RuntimeSnapshotRepository,
)
from products.generic_product import GenericProductKernel

from .profile import GenericApplicationProfile

if TYPE_CHECKING:
    from core.application.runtime_session_port import RuntimeSessionPort


class GenericApplicationService:
    """Bridges generic product kernel with an operational profile."""

    def __init__(
        self,
        profile: GenericApplicationProfile | None = None,
        kernel: GenericProductKernel | None = None,
    ) -> None:
        self.profile = profile or GenericApplicationProfile()
        self.kernel = kernel or GenericProductKernel(self.profile.to_product_rules())
        self.mode_policy = ModePolicy()
        self._route_compiler = RouteCompiler(self.kernel)
        self._spec_repository = InterlockingSpecRepository()
        self._snapshot_repository = RuntimeSnapshotRepository()

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

    def find_route(
        self,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        *,
        overlap_length: int | None = None,
        runtime_session: "RuntimeSessionPort | None" = None,
    ) -> Route:
        """Find one route candidate using application defaults."""
        return self.kernel.find_route(
            topology=topology,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
            runtime_session=runtime_session,
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

    def compile_interlocking_spec(
        self,
        topology: RailwayTopology,
        *,
        station_id: str = "UNNAMED",
        overlap_length: int | None = None,
    ) -> InterlockingSpec:
        """Compile topology into one deterministic interlocking specification."""
        return self._route_compiler.compile(
            topology=topology,
            station_id=station_id,
            overlap_length=(
                self.profile.default_overlap_length
                if overlap_length is None
                else overlap_length
            ),
        )

    def save_interlocking_spec(self, spec: InterlockingSpec, path: str | Path) -> None:
        """Save one compiled interlocking specification to JSON."""
        self._spec_repository.save(spec, path)

    def load_interlocking_spec(self, path: str | Path) -> InterlockingSpec:
        """Load one compiled interlocking specification from JSON."""
        return self._spec_repository.load(path)

    def save_runtime_snapshot(self, snapshot: dict, path: str | Path) -> None:
        """Save runtime snapshot artifact (occupancy/locks/routes/trains)."""
        self._snapshot_repository.save(snapshot, path)

    def load_runtime_snapshot(self, path: str | Path) -> dict:
        """Load runtime snapshot artifact."""
        return self._snapshot_repository.load(path)

    @staticmethod
    def build_layout_payload(topology: RailwayTopology) -> dict:
        """Serialize current topology to one web/runtime-compatible layout payload."""
        return build_layout_payload(topology)
