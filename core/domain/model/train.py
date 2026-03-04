"""Train movement model over a locked route."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.model.elements import TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.runtime.locking_engine import LockingEngine


@dataclass(slots=True)
class Train:
    """A train that advances section-by-section along a route."""

    id: str
    current_section: str
    speed: float = 1.0
    route_id: str | None = None
    _cursor: int = field(default=0, init=False, repr=False)
    _movement_credit: float = field(default=0.0, init=False, repr=False)
    _active_path: list[str] = field(default_factory=list, init=False, repr=False)

    def assign_route(
        self, route: Route, topology: RailwayTopology, locking_engine: LockingEngine
    ) -> None:
        """Bind this train to a route and initialize occupancy."""
        self.route_id = route.id
        approach_section = route.approach_locking_section.strip() if route.approach_locking_section else ""
        full_path = list(route.full_path)
        if approach_section and self.current_section == approach_section and approach_section not in full_path:
            self._active_path = [approach_section, *full_path]
        else:
            self._active_path = full_path

        if self.current_section not in self._active_path:
            self.current_section = route.path[0]
        self._cursor = self._active_path.index(self.current_section)

        section = topology.get_element(self.current_section)
        if isinstance(section, TrackSection):
            if section.occupied:
                if not (approach_section and self.current_section == approach_section):
                    raise RuntimeError(
                        f"Train {self.id} cannot enter occupied section {self.current_section}"
                    )
            else:
                section.occupied = True
        locking_engine.notify_train_entered(route.id, self.current_section)

    def step(self, route: Route, topology: RailwayTopology, locking_engine: LockingEngine) -> bool:
        """Advance according to speed; return True if movement occurred."""
        if self.route_id != route.id:
            return False
        active_path = self._active_path or list(route.full_path)
        if self._cursor >= len(active_path) - 1:
            # Route complete: keep destination occupancy, release route locking if eligible.
            locking_engine.sectional_release(route.id, self.current_section)
            self.route_id = None
            return False

        moved = False
        self._movement_credit += max(0.0, self.speed)
        while self._movement_credit >= 1.0 and self._cursor < len(active_path) - 1:
            prev_node = active_path[self._cursor]
            next_node = active_path[self._cursor + 1]

            next_element = topology.get_element(next_node)
            if isinstance(next_element, TrackSection):
                if next_element.occupied:
                    raise RuntimeError(f"Unsafe move: section {next_element.id} already occupied")
                next_element.occupied = True

            locking_engine.notify_train_entered(route.id, next_node)

            prev_element = topology.get_element(prev_node)
            if isinstance(prev_element, TrackSection):
                prev_element.occupied = False
                locking_engine.sectional_release(route.id, prev_node)

            self.current_section = next_node
            self._cursor += 1
            self._movement_credit -= 1.0
            moved = True

        return moved

