"""Train movement model over a locked route."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.domain.model.elements import TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology

if TYPE_CHECKING:
    from core.runtime.locking_engine import LockingEngine


@dataclass(slots=True)
class Train:
    """A train that advances section-by-section along a route."""

    id: str
    current_section: str
    speed: float = 1.0
    route_id: str | None = None
    traverse_overlap: bool = True
    _cursor: int = field(default=0, init=False, repr=False)
    _movement_credit: float = field(default=0.0, init=False, repr=False)
    _active_path: list[str] = field(default_factory=list, init=False, repr=False)
    _occupied_track_section: str = field(default="", init=False, repr=False)

    def _rebuild_active_path(self, route: Route) -> list[str]:
        approach_section = route.approach_locking_section.strip() if route.approach_locking_section else ""
        route_path = list(route.full_path if self.traverse_overlap else route.path)
        if approach_section and self.current_section == approach_section and approach_section not in route_path:
            return [approach_section, *route_path]
        return route_path

    def assign_route(
        self, route: Route, topology: RailwayTopology, locking_engine: "LockingEngine"
    ) -> None:
        """Bind this train to a route and initialize occupancy."""
        self.route_id = route.id
        approach_section = route.approach_locking_section.strip() if route.approach_locking_section else ""
        self._active_path = self._rebuild_active_path(route)

        if self.current_section not in self._active_path:
            self.current_section = route.path[0]
        self._cursor = self._active_path.index(self.current_section)
        locking_engine.enter_train_section(
            route.id,
            self.current_section,
            allow_preoccupied=bool(approach_section and self.current_section == approach_section),
        )
        current_element = topology.get_element(self.current_section)
        self._occupied_track_section = (
            self.current_section if isinstance(current_element, TrackSection) else ""
        )

    def relocate_on_route(
        self,
        route: Route,
        topology: RailwayTopology,
        locking_engine: "LockingEngine",
        *,
        new_section: str,
        speed: float | None = None,
    ) -> None:
        """Move train to another node on the same route with safe OCCUPIED-before-FREE ordering."""
        old_track = self._occupied_track_section.strip()
        self.current_section = new_section
        active_path = self._rebuild_active_path(route)
        if self.current_section not in active_path:
            self.current_section = route.path[0]
            active_path = self._rebuild_active_path(route)

        locking_engine.enter_train_section(route.id, self.current_section, allow_preoccupied=True)
        current_element = topology.get_element(self.current_section)
        if isinstance(current_element, TrackSection):
            if old_track and old_track != self.current_section:
                locking_engine.vacate_train_section(route.id, old_track)
            self._occupied_track_section = self.current_section

        self.route_id = route.id
        self._active_path = active_path
        self._cursor = self._active_path.index(self.current_section)
        if speed is not None:
            self.speed = max(0.0, float(speed))

    def step(self, route: Route, topology: RailwayTopology, locking_engine: LockingEngine) -> bool:
        """Advance according to speed; return True if movement occurred."""
        if self.route_id != route.id:
            return False
        active_path = self._active_path or list(route.full_path if self.traverse_overlap else route.path)
        if self._cursor >= len(active_path) - 1:
            # Route complete: keep destination occupancy, release route locking if eligible.
            completion_section = self._occupied_track_section or self.current_section
            locking_engine.sectional_release(route.id, completion_section)
            self.route_id = None
            return False

        moved = False
        self._movement_credit += max(0.0, self.speed)
        while self._movement_credit >= 1.0 and self._cursor < len(active_path) - 1:
            prev_node = active_path[self._cursor]
            next_node = active_path[self._cursor + 1]

            locking_engine.enter_train_section(route.id, next_node)
            next_element = topology.get_element(next_node)
            if isinstance(next_element, TrackSection):
                previous_track = self._occupied_track_section.strip()
                if previous_track and previous_track != next_node:
                    locking_engine.vacate_train_section(route.id, previous_track)
                self._occupied_track_section = next_node

            self.current_section = next_node
            self._cursor += 1
            self._movement_credit -= 1.0
            moved = True

        return moved

