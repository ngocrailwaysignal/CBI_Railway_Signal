"""Flank-protection derivation for geographical routes."""

from __future__ import annotations

from typing import Iterable

from core.elements import Point, PointPosition
from core.topology import RailwayTopology


class FlankProtectionError(ValueError):
    """Raised when mandatory flank protection cannot be guaranteed."""


class FlankProtectionEngine:
    """Computes additional point locks to protect a route from converging moves."""

    def __init__(self, topology: RailwayTopology) -> None:
        self.topology = topology

    def compute_required_positions(
        self,
        route_nodes: Iterable[str],
        route_point_positions: dict[str, PointPosition],
    ) -> dict[str, PointPosition]:
        """Return flank-point positions required for the given route footprint."""
        route_node_set = set(route_nodes)
        graph = self.topology.graph
        flank_positions: dict[str, PointPosition] = {}

        for protected_node in sorted(route_node_set):
            if protected_node not in graph.nodes:
                continue
            for predecessor in sorted(graph.predecessors(protected_node)):
                if predecessor in route_node_set:
                    continue
                point = self.topology.get_element(predecessor)
                if not isinstance(point, Point):
                    continue

                toward_route = next(
                    (
                        position
                        for position, target in point.facing_connections.items()
                        if target == protected_node
                    ),
                    None,
                )
                if toward_route is None:
                    continue

                route_position = route_point_positions.get(point.id)
                if route_position is not None:
                    if route_position == toward_route:
                        raise FlankProtectionError(
                            f"Point {point.id} cannot protect route at node {protected_node}"
                        )
                    continue

                protective_position = self._protective_position(point, toward_route)
                if protective_position is None:
                    raise FlankProtectionError(
                        f"No protective flank position available at point {point.id}"
                    )

                existing = flank_positions.get(point.id)
                if existing is not None and existing != protective_position:
                    raise FlankProtectionError(
                        f"Point {point.id} receives conflicting flank calls"
                    )
                flank_positions[point.id] = protective_position

        return flank_positions

    @staticmethod
    def _protective_position(
        point: Point,
        toward_route: PointPosition,
    ) -> PointPosition | None:
        opposite = (
            PointPosition.REVERSE
            if toward_route == PointPosition.NORMAL
            else PointPosition.NORMAL
        )
        if opposite in point.facing_connections:
            return opposite
        return None
