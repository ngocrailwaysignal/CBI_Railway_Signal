"""Overlap selection policy."""

from __future__ import annotations

from enum import Enum

from core.domain.model.elements import TrackSection
from core.domain.model.topology import RailwayTopology


class OverlapSelectionPolicy(str, Enum):
    """Supported overlap policies for route compilation/dispatching."""

    STANDARD = "STANDARD"


class OverlapPolicy:
    """Computes overlap nodes according to configured selection policy."""

    def __init__(self, policy: OverlapSelectionPolicy = OverlapSelectionPolicy.STANDARD) -> None:
        self.policy = policy

    def compute_overlap(
        self,
        *,
        topology: RailwayTopology,
        route_path: list[str],
        overlap_length: int,
        preferred_first_node: str | None = None,
    ) -> list[str]:
        if not route_path:
            return []

        route_graph = topology.routing_graph()
        overlap: list[str] = []
        route_nodes = set(route_path)
        previous = route_path[-2] if len(route_path) > 1 else None
        current = route_path[-1]
        counted_sections = 0
        max_steps = max(1, route_graph.number_of_nodes() * 2)

        for _ in range(max_steps):
            if counted_sections >= max(0, overlap_length):
                break
            neighbors = sorted(node for node in route_graph.successors(current) if node != previous)
            preferred = [node for node in neighbors if node not in route_nodes and node not in overlap]
            candidates = preferred if preferred else [node for node in neighbors if node not in overlap]
            if not candidates:
                break

            next_node = candidates[0]
            if not overlap and preferred_first_node:
                normalized = preferred_first_node.strip()
                if normalized in candidates:
                    next_node = normalized
            overlap.append(next_node)

            next_element = topology.get_element(next_node)
            if isinstance(next_element, TrackSection):
                counted_sections += 1
            previous, current = current, next_node

        return overlap


__all__ = ["OverlapSelectionPolicy", "OverlapPolicy"]
