"""Stateful runtime session for one active topology workspace."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domain.model.elements import PointPosition
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from kernel.locking_engine.locking_engine import LockingEngine
from kernel.occupancy_engine.occupancy_reconciler import OccupancyReconciler
from kernel.route_dispatcher.route_dispatcher import RouteDispatcher
from kernel.route_dispatcher.route_engine import RouteEngine
from kernel.safety_engine.safety_monitor import SafetyMonitor
from runtime.command_bus import RuntimeCommandHandler
from runtime.runtime_cycle import SimulationEngine
from simulation.environment_simulator import RuntimeSnapshotHydrator
from simulation.train_simulator import RuntimeTrainLifecycle


@dataclass
class RuntimeSession:
    """Own the mutable runtime state and delegate simulation behavior."""

    topology: RailwayTopology
    route_engine: RouteEngine = field(init=False)
    locking_engine: LockingEngine = field(init=False)
    route_dispatcher: RouteDispatcher = field(init=False)
    occupancy_reconciler: OccupancyReconciler = field(init=False)
    safety_monitor: SafetyMonitor = field(init=False)
    command_handler: RuntimeCommandHandler = field(init=False)
    train_lifecycle: RuntimeTrainLifecycle = field(init=False)
    snapshot_hydrator: RuntimeSnapshotHydrator = field(init=False)
    simulation_engine: SimulationEngine = field(init=False)
    trains: dict[str, Train] = field(default_factory=dict)
    tick: int = 0

    def __post_init__(self) -> None:
        self.route_engine = RouteEngine(self.topology)
        self.locking_engine = LockingEngine(self.topology)
        self.route_dispatcher = RouteDispatcher(self.route_engine, self.locking_engine)
        self.occupancy_reconciler = OccupancyReconciler()
        self.safety_monitor = SafetyMonitor()
        self.command_handler = RuntimeCommandHandler(self)
        self.train_lifecycle = RuntimeTrainLifecycle(self)
        self.snapshot_hydrator = RuntimeSnapshotHydrator(self)
        self.simulation_engine = SimulationEngine(self)

    def apply_runtime_command(self, op: str, payload: dict[str, Any] | None = None) -> Any:
        """Single runtime command gateway for external/manual integrations."""
        return self.command_handler.execute(op, payload)

    def set_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int = 0,
    ) -> Route:
        """Compute and lock a route."""
        return self.route_dispatcher.set_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
        )

    def cancel_route(self, route_id: str) -> None:
        """Cancel one active route."""
        self.route_dispatcher.cancel_route(route_id)
        self.route_dispatcher.update_time_locking()

    def set_section_occupied(
        self,
        section_id: str,
        occupied: bool,
        *,
        route_id_hint: str | None = None,
    ) -> dict[str, Any]:
        """Apply one occupancy mutation through locking engine and reconcile trains."""
        resolved_route_id = self.locking_engine.set_section_occupied(
            section_id,
            occupied=occupied,
            route_id_hint=route_id_hint,
        )
        removed_trains: list[str] = []
        if not bool(occupied):
            removed_trains = self.reconcile_manual_free_section(section_id)
        return {
            "route_id": resolved_route_id,
            "removed_trains": removed_trains,
        }

    def set_point_position(self, point_id: str, position: PointPosition | str) -> None:
        """Apply one point movement via locking engine."""
        if isinstance(position, PointPosition):
            target = position
        else:
            target = PointPosition(str(position).strip().upper())
        self.locking_engine.set_point_position(point_id, target)

    def add_train(self, train: Train, route: Route) -> None:
        """Add a train and place it on its route start."""
        if train.id in self.trains:
            raise ValueError(f"Train {train.id} already exists")
        train.assign_route(route, self.topology, self.locking_engine)
        self.trains[train.id] = train

    def upsert_train(
        self,
        *,
        train_id: str,
        current_section: str,
        route_id: str | None = None,
        speed: float = 0.0,
    ) -> Train:
        """Create/update one train while enforcing runtime mutations via engine."""
        return self.train_lifecycle.upsert_train(
            train_id=train_id,
            current_section=current_section,
            route_id=route_id,
            speed=speed,
        )

    def remove_train(self, train_id: str) -> bool:
        """Remove one train and vacate its section occupancy."""
        return self.train_lifecycle.remove_train(train_id)

    def hydrate_snapshot(
        self,
        *,
        snapshot: dict[str, Any],
        strict_route_ids: bool = True,
    ) -> None:
        """Reset runtime state and replay one runtime snapshot through engine commands."""
        self.snapshot_hydrator.hydrate_snapshot(
            snapshot=snapshot,
            strict_route_ids=strict_route_ids,
        )

    def reconcile_manual_free_section(self, section_id: str) -> list[str]:
        """Remove trains that still claim a section manually forced to FREE."""
        return self.occupancy_reconciler.reconcile_manual_free_section(
            topology=self.topology,
            trains=self.trains,
            section_id=section_id,
        )

    def step(self) -> None:
        """Advance simulation behavior for the current runtime state."""
        self.simulation_engine.step()

    def run(self, steps: int) -> None:
        """Run N simulation ticks."""
        self.simulation_engine.run(steps)

    def log_state(self) -> None:
        """Emit concise state logs."""
        self.simulation_engine.log_state()
