"""Train movement model over a locked route."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.elements import TrackSection
from core.locking_engine import LockingEngine
from core.route_engine import Route
from core.topology import RailwayTopology


@dataclass(slots=True)
class Train:
    """A train that advances section-by-section along a route."""

    id: str
    current_section: str
    speed: float = 1.0
    route_id: str | None = None
    _cursor: int = field(default=0, init=False, repr=False)
    _movement_credit: float = field(default=0.0, init=False, repr=False)

    def assign_route(
        self, route: Route, topology: RailwayTopology, locking_engine: LockingEngine
    ) -> None:
        """Bind this train to a route and initialize occupancy."""
        self.route_id = route.id
        if self.current_section not in route.full_path:
            self.current_section = route.path[0]
        self._cursor = route.full_path.index(self.current_section)

        section = topology.get_element(self.current_section)
        if isinstance(section, TrackSection):
            if section.occupied:
                raise RuntimeError(
                    f"Train {self.id} cannot enter occupied section {self.current_section}"
                )
            section.occupied = True
        locking_engine.notify_train_entered(route.id, self.current_section)

    def step(self, route: Route, topology: RailwayTopology, locking_engine: LockingEngine) -> bool:
        """Advance according to speed; return True if movement occurred."""
        if self.route_id != route.id:
            return False
        if self._cursor >= len(route.full_path) - 1:
            return False

        moved = False
        self._movement_credit += max(0.0, self.speed)
        while self._movement_credit >= 1.0 and self._cursor < len(route.full_path) - 1:
            prev_node = route.full_path[self._cursor]
            next_node = route.full_path[self._cursor + 1]

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

