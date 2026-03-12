"""Pure simulation engine for train movement and time-stepped behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime_session.session import RuntimeSession


@dataclass(slots=True)
class SimulationEngine:
    """Advance a runtime session through time without owning runtime orchestration."""

    runtime_session: "RuntimeSession"

    def step(self) -> None:
        """Advance the simulation by one tick."""
        self.runtime_session.tick += 1
        self.runtime_session.route_dispatcher.update_time_locking()
        for train in list(self.runtime_session.trains.values()):
            if not train.route_id:
                continue
            route = self.runtime_session.locking_engine.active_routes.get(train.route_id)
            if route is None:
                train.route_id = None
                continue
            train.step(route, self.runtime_session.topology, self.runtime_session.locking_engine)
        self.runtime_session.route_dispatcher.update_time_locking()

        issues = self.runtime_session.safety_monitor.detect_unsafe_conditions(
            self.runtime_session.topology,
            self.runtime_session.trains.values(),
        )
        if issues:
            self.runtime_session.locking_engine.force_all_signals_stop()
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
            f"{s.id}:{s.aspect.value}(route={s.route_id})"
            for s in self.runtime_session.topology.signals.values()
        )
        section_state: list[str] = []
        for node_id in self.runtime_session.topology.graph.nodes:
            element = self.runtime_session.topology.graph.nodes[node_id]["element"]
            if hasattr(element, "occupied"):
                section_state.append(
                    f"{element.id}(occ={element.occupied},lock={element.locked_by})"
                )
        train_state = ", ".join(
            f"{t.id}@{t.current_section}" for t in self.runtime_session.trains.values()
        )
        print(
            f"[tick={self.runtime_session.tick}] signals[{signal_state}] "
            f"tracks[{'; '.join(section_state)}] trains[{train_state}]"
        )
