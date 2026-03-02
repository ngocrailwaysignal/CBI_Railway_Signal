"""Safety rules for route validation and fail-safe checks."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, TYPE_CHECKING

from core.elements import Point, PointPosition, SignalAspect, TrackSection
from core.topology import RailwayTopology

if TYPE_CHECKING:
    from core.route_engine import Route
    from core.train import Train


class SafetyRules:
    """Static safety checks used by route and simulation engines."""

    @staticmethod
    def route_elements_available(
        topology: RailwayTopology,
        node_path: Iterable[str],
        required_points: dict[str, PointPosition],
        requesting_route_id: str | None = None,
    ) -> tuple[bool, str]:
        """Check occupancy and lock availability for a prospective route."""
        for node_id in node_path:
            element = topology.get_element(node_id)
            if isinstance(element, TrackSection):
                if element.occupied:
                    return False, f"Section {element.id} is occupied"
                if element.locked_by and element.locked_by != requesting_route_id:
                    return False, f"Section {element.id} is locked by {element.locked_by}"
            elif isinstance(element, Point):
                if element.locked_by and element.locked_by != requesting_route_id:
                    return False, f"Point {element.id} is locked by {element.locked_by}"

        for point_id, required_position in required_points.items():
            point = topology.get_element(point_id)
            if not isinstance(point, Point):
                return False, f"Required point {point_id} is missing"
            if point.locked_by and point.locked_by != requesting_route_id:
                return False, f"Point {point.id} is locked by {point.locked_by}"
            if point.position != required_position and point.locked_by:
                return False, f"Point {point.id} cannot move while locked"

        return True, "OK"

    @staticmethod
    def has_conflict(candidate: "Route", active_routes: Iterable["Route"]) -> bool:
        """Return True if a route conflicts with any active route footprint."""
        candidate_nodes = set(candidate.full_path)
        candidate_points = set(candidate.required_point_positions)
        for active in active_routes:
            active_nodes = set(active.full_path)
            active_points = set(active.required_point_positions)
            if candidate_nodes.intersection(active_nodes):
                return True
            if candidate_points.intersection(active_points):
                return True
        return False

    @staticmethod
    def flank_protection_placeholder(_route: "Route", _topology: RailwayTopology) -> bool:
        """Placeholder hook for flank protection extension."""
        return True

    @staticmethod
    def detect_unsafe_conditions(topology: RailwayTopology, trains: Iterable["Train"]) -> list[str]:
        """Collect unsafe conditions that should trigger fail-safe STOP."""
        issues: list[str] = []

        section_counter: Counter[str] = Counter()
        for train in trains:
            section_counter[train.current_section] += 1
            current = topology.get_element(train.current_section)
            if isinstance(current, TrackSection) and not current.occupied:
                issues.append(
                    f"Train {train.id} reports section {train.current_section} but section not occupied"
                )

        for section_id, count in section_counter.items():
            if count > 1:
                issues.append(f"Collision risk: {count} trains on {section_id}")

        for signal in topology.signals.values():
            if signal.aspect == SignalAspect.PROCEED and not signal.route_id:
                issues.append(f"Signal {signal.id} is PROCEED without a locked route")

        for node_id in topology.graph.nodes:
            element = topology.graph.nodes[node_id]["element"]
            if isinstance(element, Point) and element.locked_by and element.position not in (
                PointPosition.NORMAL,
                PointPosition.REVERSE,
            ):
                issues.append(f"Point {element.id} has invalid position while locked")

        return issues

    @staticmethod
    def enforce_fail_safe_stop(topology: RailwayTopology) -> None:
        """Force all signals to STOP."""
        for signal in topology.signals.values():
            signal.aspect = SignalAspect.STOP
            signal.route_id = None

