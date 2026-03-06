"""Application-level orchestration for reusable interlocking simulation."""

from __future__ import annotations

from pathlib import Path

from core.application import ModePolicy
from core.application.runtime_helpers import (
    cancel_all_active_routes,
    find_train_for_route,
    get_active_route_for_pair,
    has_active_routes,
    next_train_id,
)
from core.application.serialization import build_layout_payload, build_runtime_snapshot
from core.application.use_cases import (
    CancelActiveRoutesUseCase,
    CancelRoutesResult,
    ManualOverrideResult,
    ManualOverrideUseCase,
    SetOrReuseRouteUseCase,
    SetRouteResult,
    StartRouteSimulationUseCase,
    StartSimulationResult,
)
from core.compiler import InterlockingSpec, RouteCompiler
from core.compiler.interlocking_table import InterlockingTableRow
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from core.infrastructure.persistence import (
    InterlockingSpecRepository,
    RuntimeSnapshotRepository,
)
from core.runtime.simulation import Simulation
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
        self.mode_policy = ModePolicy()
        self._set_route_use_case = SetOrReuseRouteUseCase(self.kernel)
        self._cancel_routes_use_case = CancelActiveRoutesUseCase()
        self._manual_override_use_case = ManualOverrideUseCase()
        self._start_simulation_use_case = StartRouteSimulationUseCase(self.kernel)
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
        return get_active_route_for_pair(simulation, entry_signal_id, exit_signal_id)

    @staticmethod
    def has_active_routes(simulation: Simulation) -> bool:
        """Check whether simulation currently has active locked routes."""
        return has_active_routes(simulation)

    @staticmethod
    def update_time_locking(simulation: Simulation) -> None:
        """Advance time-lock release checks for active routes."""
        simulation.locking_engine.update_time_locking()

    @staticmethod
    def cancel_all_active_routes(simulation: Simulation) -> list[str]:
        """Try to cancel all active routes; return per-route failures."""
        return cancel_all_active_routes(simulation)

    @staticmethod
    def find_train_for_route(simulation: Simulation, route_id: str) -> Train | None:
        """Return train assigned to one route id, if present."""
        return find_train_for_route(simulation, route_id)

    @staticmethod
    def next_train_id(simulation: Simulation, prefix: str = "T") -> str:
        """Generate the next free train id for one simulation."""
        return next_train_id(simulation, prefix=prefix)

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

    def set_or_reuse_route(
        self,
        *,
        topology: RailwayTopology,
        simulation: Simulation | None,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
        approach_time_lock_seconds: float,
        overlap_release_seconds: float,
    ) -> SetRouteResult:
        """Set route or return already-active route for one signal pair."""
        return self._set_route_use_case.execute(
            topology=topology,
            simulation=simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
            approach_time_lock_seconds=approach_time_lock_seconds,
            overlap_release_seconds=overlap_release_seconds,
        )

    def cancel_active_routes(self, simulation: Simulation | None) -> CancelRoutesResult:
        """Cancel all active routes and return detailed result."""
        return self._cancel_routes_use_case.execute(simulation)

    def start_route_simulation(
        self,
        *,
        topology: RailwayTopology,
        simulation: Simulation | None,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
        approach_time_lock_seconds: float,
        overlap_release_seconds: float,
        train_speed: float = 1.0,
    ) -> StartSimulationResult:
        """Prepare route/train for simulation and return run metadata."""
        return self._start_simulation_use_case.execute(
            topology=topology,
            simulation=simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
            approach_time_lock_seconds=approach_time_lock_seconds,
            overlap_release_seconds=overlap_release_seconds,
            train_speed=train_speed,
        )

    def manual_set_section_occupied(
        self,
        *,
        simulation: Simulation | None,
        section_id: str,
        occupied: bool,
    ) -> ManualOverrideResult:
        """Apply manual occupancy override and reconcile train occupancy state."""
        return self._manual_override_use_case.execute_set_section_occupied(
            simulation=simulation,
            section_id=section_id,
            occupied=occupied,
        )

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
    def build_runtime_snapshot(simulation: Simulation | None) -> dict:
        """Serialize runtime-only state for snapshot persistence."""
        return build_runtime_snapshot(simulation)

    @staticmethod
    def build_layout_payload(topology: RailwayTopology) -> dict:
        """Serialize current topology to one web/runtime-compatible layout payload."""
        return build_layout_payload(topology)
