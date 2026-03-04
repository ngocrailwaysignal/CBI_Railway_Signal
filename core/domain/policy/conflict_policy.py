"""Conflict and element-availability policy."""

from __future__ import annotations

from typing import Iterable

from core.domain.model.elements import Point, PointPosition, TrackSection
from core.domain.model.topology import RailwayTopology


class ConflictPolicy:
    """Route conflict and element-availability checks."""

    @staticmethod
    def route_elements_available(
        topology: RailwayTopology,
        node_path: Iterable[str],
        required_points: dict[str, PointPosition],
        monitored_flank_sections: Iterable[str] | None = None,
        requesting_route_id: str | None = None,
    ) -> tuple[bool, str]:
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

        for section_id in monitored_flank_sections or []:
            section = topology.get_element(section_id)
            if not isinstance(section, TrackSection):
                continue
            if section.occupied:
                return False, f"Flank section {section.id} is occupied"
            if section.locked_by and section.locked_by != requesting_route_id:
                return False, f"Flank section {section.id} is locked by {section.locked_by}"

        return True, "OK"

    @staticmethod
    def has_conflict(
        topology: RailwayTopology,
        candidate_route: object,
        active_routes: Iterable[object],
    ) -> bool:
        candidate_nodes = set(candidate_route.full_path).union(candidate_route.monitored_flank_sections)
        candidate_points = set(candidate_route.all_required_point_positions)
        for active_route in active_routes:
            active_nodes = set(active_route.full_path).union(active_route.monitored_flank_sections)
            active_points = set(active_route.all_required_point_positions)
            if candidate_nodes.intersection(active_nodes):
                return True
            if topology.sets_conflict_by_clearance(candidate_nodes, active_nodes):
                return True
            if candidate_points.intersection(active_points):
                return True
        return False

