"""Pure simulation engine for train movement and time-stepped behavior."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from runtime.runtime_controller import RuntimeSession


@dataclass(slots=True)
class SimulationEngine:
    """Advance a runtime session through time without owning runtime orchestration."""

    runtime_session: RuntimeSession

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
        self._reconcile_train_occupancy()
        self._mark_calling_on_shared_sections()

        issues = self.runtime_session.safety_monitor.detect_unsafe_conditions(
            self.runtime_session.topology,
            self.runtime_session.trains.values(),
            active_routes=self.runtime_session.locking_engine.active_routes,
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

    def _reconcile_train_occupancy(self) -> None:
        for train in self.runtime_session.trains.values():
            element = self.runtime_session.topology.get_element(train.current_section)
            if hasattr(element, "occupied"):
                element.occupied = True

    def _mark_calling_on_shared_sections(self) -> None:
        active_routes = self.runtime_session.locking_engine.active_routes
        trains_by_section: dict[str, list[object]] = {}
        for train in self.runtime_session.trains.values():
            trains_by_section.setdefault(train.current_section, []).append(train)

        for section_id, trains in trains_by_section.items():
            if len(trains) < 2:
                continue
            has_calling_on_authority = any(
                (route := active_routes.get(str(train.route_id or "").strip()))
                is not None
                and route.is_calling_on
                and section_id in route.full_path
                for train in trains
            )
            if not has_calling_on_authority:
                continue
            for train in trains:
                train.calling_on_shared_sections.add(section_id)
