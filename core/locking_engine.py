"""Route locking, sectional release, and signal control."""

from __future__ import annotations

from time import monotonic
from typing import Dict

from core.approach_locking import ApproachLockState, ApproachLockingStateMachine
from core.elements import ApproachSection, Point, PointPosition, SignalAspect, TrackSection
from core.route_engine import Route
from core.safety_rules import SafetyRules
from core.topology import RailwayTopology


class LockingEngine:
    """Applies and releases interlocking locks for active routes."""

    def __init__(
        self,
        topology: RailwayTopology,
        time_lock_seconds: float = 30.0,
        overlap_release_seconds: float = 0.0,
    ) -> None:
        self.topology = topology
        self.active_routes: Dict[str, Route] = {}
        self.approach_locking = ApproachLockingStateMachine(time_lock_seconds=time_lock_seconds)
        self.overlap_release_seconds = max(0.0, float(overlap_release_seconds))
        self._pending_overlap_releases: dict[str, float] = {}

    def configure_release_timing(
        self,
        *,
        approach_time_lock_seconds: float | None = None,
        overlap_release_seconds: float | None = None,
    ) -> None:
        """Update runtime timing values used by locking release logic."""
        if approach_time_lock_seconds is not None:
            self.approach_locking.time_lock_seconds = max(0.0, float(approach_time_lock_seconds))
        if overlap_release_seconds is not None:
            self.overlap_release_seconds = max(0.0, float(overlap_release_seconds))

    def lock_route(self, route: Route) -> None:
        """Lock sections, points, and clear entry signal only when fully secured."""
        if route.id in self.active_routes:
            raise ValueError(f"Route {route.id} is already active")
        try:
            all_points = route.all_required_point_positions
        except ValueError as exc:
            raise ValueError(f"Cannot lock route: {exc}") from exc

        ok, reason = SafetyRules.route_elements_available(
            self.topology,
            route.full_path,
            all_points,
        )
        if not ok:
            raise ValueError(f"Cannot lock route: {reason}")

        for point_id, required_position in all_points.items():
            point = self.topology.get_element(point_id)
            if not isinstance(point, Point):
                raise ValueError(f"Route refers to unknown point {point_id}")
            if point.locked_by and point.locked_by != route.id:
                raise ValueError(f"Point {point_id} locked by {point.locked_by}")
            point.position = required_position
            point.locked_by = route.id

        for node_id in route.full_path:
            element = self.topology.get_element(node_id)
            if isinstance(element, TrackSection):
                if element.locked_by and element.locked_by != route.id:
                    raise ValueError(f"Section {node_id} already locked by {element.locked_by}")
                element.locked_by = route.id
            elif isinstance(element, Point):
                if element.locked_by and element.locked_by != route.id:
                    raise ValueError(f"Point {node_id} already locked by {element.locked_by}")
                element.locked_by = route.id

        entry_signal = self.topology.signals[route.entry_signal_id]
        entry_signal.route_id = route.id
        entry_signal.aspect = SignalAspect.PROCEED
        self.active_routes[route.id] = route
        route.approach_locking_section = self._resolve_route_approach_section(route)
        self.approach_locking.register_route(
            route_id=route.id,
            entry_signal_id=route.entry_signal_id,
            approach_section_id=route.approach_locking_section,
        )
        self._pending_overlap_releases.pop(route.id, None)

    def set_point_position(self, point_id: str, new_position: PointPosition) -> None:
        """Move a point only if not locked."""
        point = self.topology.get_element(point_id)
        if not isinstance(point, Point):
            raise KeyError(f"Unknown point: {point_id}")
        if point.locked_by:
            raise RuntimeError(f"Point {point.id} is locked by {point.locked_by}")
        point.position = new_position

    def cancel_route(self, route_id: str) -> None:
        """Cancel a route unless blocked by approach locking."""
        route = self.active_routes.get(route_id)
        if route is None:
            return

        approach_occupied = self._is_approach_occupied(route)
        can_cancel, reason = self.approach_locking.request_cancellation(
            route_id=route_id,
            approach_occupied=approach_occupied,
        )
        if not can_cancel:
            raise RuntimeError(reason)
        occupied_sections = self._occupied_route_sections(route)
        if occupied_sections:
            joined = ", ".join(occupied_sections)
            raise RuntimeError(
                f"Route {route_id} is occupied by train on sections: {joined}"
            )
        self._unlock_route(route_id)

    def notify_train_entered(self, route_id: str, node_id: str) -> None:
        """React to train progression for approach locking behavior."""
        route = self.active_routes.get(route_id)
        if route is None:
            return
        if route.approach_locking_section and node_id == route.approach_locking_section:
            self.approach_locking.mark_approach_locked(route_id)
        if node_id == route.path[0]:
            entry_signal = self.topology.signals[route.entry_signal_id]
            entry_signal.aspect = SignalAspect.STOP
            self.approach_locking.mark_approach_locked(route_id)

    def sectional_release(self, route_id: str, section_id: str) -> None:
        """Release a section once a train has vacated it."""
        route = self.active_routes.get(route_id)
        if route is None:
            return
        section = self.topology.get_element(section_id)
        if isinstance(section, TrackSection) and section.locked_by == route_id and not section.occupied:
            section.locked_by = None
        self._cleanup_route_if_complete(route_id)

    def force_all_signals_stop(self) -> None:
        """Force fail-safe STOP on every signal."""
        SafetyRules.enforce_fail_safe_stop(self.topology)

    def update_time_locking(self) -> None:
        """Release routes whose time locking has elapsed."""
        current_time = monotonic()
        for route_id in self.approach_locking.releasable_routes(now=current_time):
            route = self.active_routes.get(route_id)
            if route is None:
                continue
            if self._is_approach_occupied(route):
                continue
            if self._occupied_route_sections(route):
                continue
            self._unlock_route(route_id)

        for route_id, due_time in list(self._pending_overlap_releases.items()):
            if current_time < due_time:
                continue
            route = self.active_routes.get(route_id)
            if route is None:
                self._pending_overlap_releases.pop(route_id, None)
                continue
            self._unlock_route(
                route_id,
                force_unlock_sections=self._destination_force_unlock_sections(route),
            )

    def approach_lock_state(self, route_id: str) -> ApproachLockState | None:
        """Expose current approach-lock state for UI/logging."""
        return self.approach_locking.state(route_id)

    def _cleanup_route_if_complete(self, route_id: str) -> None:
        route = self.active_routes.get(route_id)
        if route is None:
            return

        track_sections = [
            node_id
            for node_id in route.full_path
            if isinstance(self.topology.get_element(node_id), TrackSection)
        ]
        if not track_sections:
            self._unlock_route(route_id)
            return

        destination_section = track_sections[-1]
        destination_occupied = False
        for section_id in track_sections:
            section = self.topology.get_element(section_id)
            if not isinstance(section, TrackSection):
                continue
            if section_id == destination_section:
                destination_occupied = section.occupied
                if section.locked_by == route_id and not section.occupied:
                    # Train has not yet reached destination section.
                    return
                continue
            if section.occupied:
                return
            if section.locked_by == route_id:
                return

        force_unlock = {destination_section} if destination_occupied else None
        if self.overlap_release_seconds <= 0.0:
            self._unlock_route(route_id, force_unlock_sections=force_unlock)
            return
        if route_id not in self._pending_overlap_releases:
            self._pending_overlap_releases[route_id] = monotonic() + self.overlap_release_seconds

    def _unlock_route(
        self,
        route_id: str,
        force_unlock_sections: set[str] | None = None,
    ) -> None:
        route = self.active_routes.get(route_id)
        if route is None:
            return

        for node_id in route.full_path:
            element = self.topology.get_element(node_id)
            if isinstance(element, TrackSection):
                force_unlock = force_unlock_sections is not None and node_id in force_unlock_sections
                if element.locked_by == route_id and (force_unlock or not element.occupied):
                    element.locked_by = None
            elif isinstance(element, Point):
                if element.locked_by == route_id:
                    element.locked_by = None

        for point_id in route.flank_point_positions:
            point = self.topology.get_element(point_id)
            if isinstance(point, Point) and point.locked_by == route_id:
                point.locked_by = None

        for signal in self.topology.signals.values():
            if signal.route_id == route_id:
                signal.aspect = SignalAspect.STOP
                signal.route_id = None

        self._pending_overlap_releases.pop(route_id, None)
        self.approach_locking.clear(route_id)
        self.active_routes.pop(route_id, None)

    def _destination_force_unlock_sections(self, route: Route) -> set[str] | None:
        """Return destination section to force-unlock if still occupied."""
        track_sections = [
            node_id
            for node_id in route.full_path
            if isinstance(self.topology.get_element(node_id), TrackSection)
        ]
        if not track_sections:
            return None
        destination_section = track_sections[-1]
        destination = self.topology.get_element(destination_section)
        if isinstance(destination, TrackSection) and destination.occupied:
            return {destination_section}
        return None

    def _is_approach_occupied(self, route: Route) -> bool:
        approach_candidates = self._approach_candidates(route)
        if approach_candidates:
            # Keep route snapshot aligned with the latest topology-based resolution.
            route.approach_locking_section = approach_candidates[0]
            for approach_id in approach_candidates:
                approach = self.topology.get_element(approach_id)
                if isinstance(approach, ApproachSection) and approach.occupied:
                    return True

        if not route.path:
            # Fail-safe: unresolved approach mapping + occupied approach section anywhere.
            return self._any_occupied_approach_section()

        # Fail-safe: if no route-specific approach could be resolved, do not allow cancellation
        # while any approach section is occupied.
        if not approach_candidates:
            return self._any_occupied_approach_section()

        return False

    def _resolve_route_approach_section(self, route: Route) -> str | None:
        candidates = self._approach_candidates(route)
        return candidates[0] if candidates else None

    def _approach_candidates(self, route: Route) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add_if_section(node_id: str) -> None:
            node = node_id.strip()
            if not node or node in seen:
                return
            element = self.topology.get_element(node)
            if isinstance(element, ApproachSection):
                candidates.append(node)
                seen.add(node)

        if route.approach_locking_section:
            add_if_section(route.approach_locking_section)

        entry_signal = self.topology.signals.get(route.entry_signal_id)
        if entry_signal is not None:
            if entry_signal.approach_section:
                add_if_section(entry_signal.approach_section)
            for node_id in self.topology.signal_approach_nodes(route.entry_signal_id):
                add_if_section(node_id)
            candidates = [
                node_id
                for node_id in candidates
                if self.topology.is_signal_back_side_node(route.entry_signal_id, node_id)
            ]

        return candidates

    def _any_occupied_approach_section(self) -> bool:
        for node_id in self.topology.graph.nodes:
            element = self.topology.get_element(node_id)
            if isinstance(element, ApproachSection) and element.occupied:
                return True
        return False

    def _occupied_route_sections(self, route: Route) -> list[str]:
        occupied: list[str] = []
        for node_id in route.full_path:
            section = self.topology.get_element(node_id)
            if isinstance(section, TrackSection) and section.occupied:
                occupied.append(section.id)
        return occupied
