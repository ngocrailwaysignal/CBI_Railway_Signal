"""Flank-protection derivation for geographical routes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import networkx as nx

from core.domain.model.elements import Point, PointPosition, TrackSection
from core.domain.model.topology import RailwayTopology


class FlankProtectionError(ValueError):
    """Raised when mandatory flank protection cannot be guaranteed."""


@dataclass(slots=True)
class FlankProtectionResult:
    """Computed flank constraints for one route footprint."""

    required_point_positions: dict[str, PointPosition] = field(default_factory=dict)
    monitored_flank_sections: list[str] = field(default_factory=list)


class FlankProtectionEngine:
    """Computes additional point locks to protect a route from converging moves."""

    def __init__(self, topology: RailwayTopology) -> None:
        self.topology = topology

    def compute_requirements(
        self,
        route_nodes: Iterable[str],
        route_point_positions: dict[str, PointPosition],
    ) -> FlankProtectionResult:
        """Return flank-point locks plus monitored flank sections."""
        route_node_set = set(route_nodes)
        graph = self._physical_undirected_graph()
        flank_positions: dict[str, PointPosition] = {}
        monitored_sections: set[str] = set()
        visited_edges: set[tuple[str, str]] = set()

        for protected_node in sorted(route_node_set):
            if protected_node not in graph.nodes:
                continue
            for branch_node in sorted(graph.neighbors(protected_node)):
                if branch_node in route_node_set:
                    continue
                self._scan_flank_branch(
                    protected_node=protected_node,
                    branch_start=branch_node,
                    route_nodes=route_node_set,
                    route_point_positions=route_point_positions,
                    flank_positions=flank_positions,
                    monitored_sections=monitored_sections,
                    visited_edges=visited_edges,
                )

        return FlankProtectionResult(
            required_point_positions=flank_positions,
            monitored_flank_sections=sorted(monitored_sections),
        )

    def compute_required_positions(
        self,
        route_nodes: Iterable[str],
        route_point_positions: dict[str, PointPosition],
    ) -> dict[str, PointPosition]:
        """Backward-compatible helper returning only flank-point positions."""
        result = self.compute_requirements(
            route_nodes=route_nodes,
            route_point_positions=route_point_positions,
        )
        return result.required_point_positions

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

    def _scan_flank_branch(
        self,
        *,
        protected_node: str,
        branch_start: str,
        route_nodes: set[str],
        route_point_positions: dict[str, PointPosition],
        flank_positions: dict[str, PointPosition],
        monitored_sections: set[str],
        visited_edges: set[tuple[str, str]],
    ) -> None:
        graph = self._physical_undirected_graph()
        stack: list[tuple[str, str, list[str]]] = [(protected_node, branch_start, [])]

        while stack:
            previous, current, traversed_sections = stack.pop()
            edge_key = (previous, current) if previous <= current else (current, previous)
            if edge_key in visited_edges:
                continue
            visited_edges.add(edge_key)

            if current in route_nodes:
                continue

            current_sections = list(traversed_sections)
            element = self.topology.get_element(current)
            if isinstance(element, TrackSection):
                current_sections.append(element.id)

            if isinstance(element, Point):
                toward_route = next(
                    (
                        position
                        for position, target in element.facing_connections.items()
                        if target == previous
                    ),
                    None,
                )
                if toward_route is not None:
                    route_position = route_point_positions.get(element.id)
                    if route_position is not None:
                        if route_position == toward_route:
                            raise FlankProtectionError(
                                f"Point {element.id} cannot protect route at node {protected_node}"
                            )
                    else:
                        protective_position = self._protective_position(element, toward_route)
                        if protective_position is None:
                            raise FlankProtectionError(
                                f"No protective flank position available at point {element.id}"
                            )
                        existing = flank_positions.get(element.id)
                        if existing is not None and existing != protective_position:
                            raise FlankProtectionError(
                                f"Point {element.id} receives conflicting flank calls"
                            )
                        flank_positions[element.id] = protective_position
                    monitored_sections.update(current_sections)
                    continue

            next_nodes = sorted(
                neighbor
                for neighbor in graph.neighbors(current)
                if neighbor != previous and neighbor not in route_nodes
            )
            if not next_nodes:
                monitored_sections.update(current_sections)
                continue
            for next_node in next_nodes:
                stack.append((current, next_node, current_sections))

    def _physical_undirected_graph(self) -> nx.Graph:
        """Return topology graph excluding synthesized signal virtual edges."""
        graph = nx.Graph()
        graph.add_nodes_from(self.topology.graph.nodes)
        for source_id, target_id in self.topology.graph.edges:
            if (source_id, target_id) in self.topology._signal_virtual_edges:
                continue
            graph.add_edge(source_id, target_id)
        return graph


# Backward-compatible semantic alias.
FlankPolicy = FlankProtectionEngine
