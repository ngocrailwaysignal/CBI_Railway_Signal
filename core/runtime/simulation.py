"""Time-stepped simulation driver."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from core.runtime.locking_engine import LockingEngine
from core.runtime.occupancy_reconciler import OccupancyReconciler
from core.runtime.route_dispatcher import RouteDispatcher
from core.runtime.route_engine import RouteEngine
from core.runtime.safety_monitor import SafetyMonitor


@dataclass
class Simulation:
    """Coordinates route setup, train movement, logging, and safety supervision."""

    topology: RailwayTopology
    route_engine: RouteEngine = field(init=False)
    locking_engine: LockingEngine = field(init=False)
    route_dispatcher: RouteDispatcher = field(init=False)
    occupancy_reconciler: OccupancyReconciler = field(init=False)
    safety_monitor: SafetyMonitor = field(init=False)
    trains: dict[str, Train] = field(default_factory=dict)
    tick: int = 0

    def __post_init__(self) -> None:
        self.route_engine = RouteEngine(self.topology)
        self.locking_engine = LockingEngine(self.topology)
        self.route_dispatcher = RouteDispatcher(self.route_engine, self.locking_engine)
        self.occupancy_reconciler = OccupancyReconciler()
        self.safety_monitor = SafetyMonitor()

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

    def add_train(self, train: Train, route: Route) -> None:
        """Add a train and place it on its route start."""
        if train.id in self.trains:
            raise ValueError(f"Train {train.id} already exists")
        train.assign_route(route, self.topology, self.locking_engine)
        self.trains[train.id] = train

    def reconcile_manual_free_section(self, section_id: str) -> list[str]:
        """Remove trains that still claim a section manually forced to FREE."""
        return self.occupancy_reconciler.reconcile_manual_free_section(
            topology=self.topology,
            trains=self.trains,
            section_id=section_id,
        )

    def step(self) -> None:
        """Advance the simulation by one tick."""
        self.tick += 1
        self.route_dispatcher.update_time_locking()
        for train in list(self.trains.values()):
            if not train.route_id:
                continue
            route = self.locking_engine.active_routes.get(train.route_id)
            if route is None:
                train.route_id = None
                continue
            train.step(route, self.topology, self.locking_engine)

        issues = self.safety_monitor.detect_unsafe_conditions(self.topology, self.trains.values())
        if issues:
            self.safety_monitor.enforce_fail_safe_stop(self.topology)
            issue_text = "; ".join(issues)
            raise RuntimeError(f"Fail-safe STOP triggered: {issue_text}")

        self.log_state()

    def run(self, steps: int) -> None:
        """Run N ticks."""
        for _ in range(max(0, steps)):
            self.step()

    def log_state(self) -> None:
        """Emit concise state logs."""
        signal_state = ", ".join(
            f"{s.id}:{s.aspect.value}(route={s.route_id})" for s in self.topology.signals.values()
        )
        section_state: list[str] = []
        for node_id in self.topology.graph.nodes:
            element = self.topology.graph.nodes[node_id]["element"]
            if hasattr(element, "occupied"):
                section_state.append(
                    f"{element.id}(occ={element.occupied},lock={element.locked_by})"
                )
        train_state = ", ".join(f"{t.id}@{t.current_section}" for t in self.trains.values())
        print(f"[tick={self.tick}] signals[{signal_state}] tracks[{'; '.join(section_state)}] trains[{train_state}]")
