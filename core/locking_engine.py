"""Route locking, sectional release, and signal control."""

from __future__ import annotations

from typing import Dict

from core.elements import Point, PointPosition, SignalAspect, TrackSection
from core.route_engine import Route
from core.safety_rules import SafetyRules
from core.topology import RailwayTopology


class LockingEngine:
    """Applies and releases interlocking locks for active routes."""

    def __init__(self, topology: RailwayTopology) -> None:
        self.topology = topology
        self.active_routes: Dict[str, Route] = {}
        self.approach_locked: Dict[str, bool] = {}

    def lock_route(self, route: Route) -> None:
        """Lock sections, points, and clear entry signal only when fully secured."""
        if route.id in self.active_routes:
            raise ValueError(f"Route {route.id} is already active")

        ok, reason = SafetyRules.route_elements_available(
            self.topology, route.full_path, route.required_point_positions
        )
        if not ok:
            raise ValueError(f"Cannot lock route: {reason}")

        for point_id, required_position in route.required_point_positions.items():
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
        self.approach_locked[route.id] = True

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
        approach_node = route.path[0]
        approach_element = self.topology.get_element(approach_node)
        if isinstance(approach_element, TrackSection) and approach_element.occupied:
            raise RuntimeError("Approach locking active: train in approach section")
        self._unlock_route(route_id)

    def notify_train_entered(self, route_id: str, node_id: str) -> None:
        """React to train progression for approach locking behavior."""
        route = self.active_routes.get(route_id)
        if route is None:
            return
        if node_id == route.path[0]:
            entry_signal = self.topology.signals[route.entry_signal_id]
            entry_signal.aspect = SignalAspect.STOP

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

    def _cleanup_route_if_complete(self, route_id: str) -> None:
        route = self.active_routes.get(route_id)
        if route is None:
            return

        for node_id in route.full_path:
            element = self.topology.get_element(node_id)
            if isinstance(element, TrackSection):
                if element.occupied:
                    return
                if element.locked_by == route_id:
                    return

        self._unlock_route(route_id)

    def _unlock_route(self, route_id: str) -> None:
        route = self.active_routes.get(route_id)
        if route is None:
            return

        for node_id in route.full_path:
            element = self.topology.get_element(node_id)
            if isinstance(element, TrackSection):
                if element.locked_by == route_id and not element.occupied:
                    element.locked_by = None
            elif isinstance(element, Point):
                if element.locked_by == route_id:
                    element.locked_by = None

        for signal in self.topology.signals.values():
            if signal.route_id == route_id:
                signal.aspect = SignalAspect.STOP
                signal.route_id = None

        self.approach_locked.pop(route_id, None)
        self.active_routes.pop(route_id, None)
