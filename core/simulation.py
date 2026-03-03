"""Time-stepped simulation driver."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.locking_engine import LockingEngine
from core.route_engine import Route, RouteEngine
from core.safety_rules import SafetyRules
from core.topology import RailwayTopology
from core.train import Train


@dataclass
class Simulation:
    """Coordinates route setup, train movement, logging, and safety supervision."""

    topology: RailwayTopology
    route_engine: RouteEngine = field(init=False)
    locking_engine: LockingEngine = field(init=False)
    trains: dict[str, Train] = field(default_factory=dict)
    tick: int = 0

    def __post_init__(self) -> None:
        self.route_engine = RouteEngine(self.topology)
        self.locking_engine = LockingEngine(self.topology)

    def set_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int = 0,
    ) -> Route:
        """Compute and lock a route."""
        self.locking_engine.update_time_locking()
        route = self.route_engine.find_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            active_routes=self.locking_engine.active_routes,
            overlap_length=overlap_length,
        )
        self.locking_engine.lock_route(route)
        return route

    def add_train(self, train: Train, route: Route) -> None:
        """Add a train and place it on its route start."""
        if train.id in self.trains:
            raise ValueError(f"Train {train.id} already exists")
        train.assign_route(route, self.topology, self.locking_engine)
        self.trains[train.id] = train

    def step(self) -> None:
        """Advance the simulation by one tick."""
        self.tick += 1
        self.locking_engine.update_time_locking()
        for train in list(self.trains.values()):
            if not train.route_id:
                continue
            route = self.locking_engine.active_routes.get(train.route_id)
            if route is None:
                train.route_id = None
                continue
            train.step(route, self.topology, self.locking_engine)

        issues = SafetyRules.detect_unsafe_conditions(self.topology, self.trains.values())
        if issues:
            self.locking_engine.force_all_signals_stop()
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
