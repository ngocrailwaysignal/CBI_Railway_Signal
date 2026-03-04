"""Topology-driven route finding and validation."""

from __future__ import annotations

from uuid import uuid4

import networkx as nx

from core.domain.model.elements import (
    ApproachSection,
    Point,
    PointPosition,
    SignalDirection,
)
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.policy import (
    ConflictPolicy,
    FlankPolicy,
    FlankProtectionResult,
    OverlapPolicy,
    OverlapSelectionPolicy,
)


class RouteEngine:
    """Computes geographical routes directly from graph connectivity."""

    def __init__(
        self,
        topology: RailwayTopology,
        overlap_policy: OverlapSelectionPolicy = OverlapSelectionPolicy.STANDARD,
    ) -> None:
        self.topology = topology
        self.flank_engine = FlankPolicy(topology)
        self.overlap_policy = overlap_policy
        self._overlap_policy_engine = OverlapPolicy(overlap_policy)

    def find_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        active_routes: dict[str, Route] | None = None,
        overlap_length: int = 0,
    ) -> Route:
        """Find and validate a route between two signals."""
        entry_signal = self.topology.signals.get(entry_signal_id)
        exit_signal = self.topology.signals.get(exit_signal_id)
        if not entry_signal or not exit_signal:
            missing: list[str] = []
            if not entry_signal:
                missing.append(f"entry {entry_signal_id}")
            if not exit_signal:
                missing.append(f"exit {exit_signal_id}")
            available = ", ".join(sorted(self.topology.signals)) or "<none>"
            raise ValueError(
                f"Unknown signal id for {', '.join(missing)}. Available signals: {available}"
            )
        if entry_signal.direction != exit_signal.direction:
            raise ValueError(
                f"Entry {entry_signal_id} and exit {exit_signal_id} must have the same direction "
                f"({entry_signal.direction.value} != {exit_signal.direction.value})"
            )
        if entry_signal_id == exit_signal_id:
            raise ValueError("Entry and exit signals must be different")
        if not entry_signal.protects or not exit_signal.protects:
            raise ValueError("Signals must protect valid track/point nodes")
        entry_protected = self.topology.signal_protected_node(entry_signal_id)
        if entry_protected is None:
            raise ValueError(
                f"Entry signal {entry_signal.id} protects an invalid node for direction {entry_signal.direction.value}"
            )
        exit_protected = self.topology.signal_protected_node(exit_signal_id)
        if exit_protected is None:
            raise ValueError(
                f"Exit signal {exit_signal.id} protects an invalid node for direction {exit_signal.direction.value}"
            )
        if entry_protected == exit_protected:
            raise ValueError(
                f"Invalid route: entry {entry_signal_id} and exit {exit_signal_id} "
                f"protect the same node {entry_protected}. "
                "Use opposite-direction signal pairing or set exit protects to the downstream node."
            )

        route_graph = self.routing_graph_for_direction(entry_signal.direction)
        source_node = entry_protected
        exit_approach_nodes = self.topology.signal_approach_nodes(exit_signal_id)
        if not exit_approach_nodes:
            raise ValueError(
                f"Exit signal {exit_signal.id} has no incoming track/point link"
            )

        reachable_targets: list[tuple[int, str]] = []
        for target_node in exit_approach_nodes:
            try:
                distance = nx.shortest_path_length(route_graph, source=source_node, target=target_node)
            except nx.NetworkXNoPath:
                continue
            reachable_targets.append((distance, target_node))

        if not reachable_targets:
            raise ValueError(
                f"No route from {source_node} to any approach node of {exit_signal.id}"
            )

        reachable_targets.sort(key=lambda item: (item[0], item[1]))

        last_reason = "no valid candidate path"
        max_candidates = max(20, route_graph.number_of_nodes() * 4)
        for _distance, target_node in reachable_targets:
            try:
                candidate_paths = nx.shortest_simple_paths(
                    route_graph,
                    source=source_node,
                    target=target_node,
                )
            except nx.NetworkXNoPath:
                continue

            try:
                for index, path in enumerate(candidate_paths):
                    if index >= max_candidates:
                        break
                    try:
                        overlap_path = self._compute_overlap(
                            path,
                            overlap_length=overlap_length,
                            preferred_first_node=exit_protected,
                        )
                        if self._has_front_protection_conflict(path, target_node, exit_protected):
                            raise ValueError(
                                f"Front protection conflict at target boundary {target_node}"
                            )
                        required_points = self.compute_required_point_positions([*path, *overlap_path])
                        flank_result = self.compute_flank_requirements(
                            [*path, *overlap_path],
                            required_points,
                        )
                        route = Route(
                            id=f"R_{entry_signal_id}_{exit_signal_id}_{uuid4().hex[:8]}",
                            entry_signal_id=entry_signal_id,
                            exit_signal_id=exit_signal_id,
                            path=path,
                            overlap_path=overlap_path,
                            required_point_positions=required_points,
                            flank_point_positions=flank_result.required_point_positions,
                            monitored_flank_sections=flank_result.monitored_flank_sections,
                            approach_locking_section=self._resolve_approach_locking_section(
                                entry_signal_id
                            ),
                        )
                    except ValueError as exc:
                        last_reason = str(exc)
                        continue

                    try:
                        all_points = route.all_required_point_positions
                    except ValueError as exc:
                        last_reason = str(exc)
                        continue

                    route_ok, reason = ConflictPolicy.route_elements_available(
                        self.topology,
                        route.full_path,
                        all_points,
                        monitored_flank_sections=route.monitored_flank_sections,
                    )
                    if not route_ok:
                        last_reason = f"Route unavailable: {reason}"
                        continue

                    if active_routes and ConflictPolicy.has_conflict(self.topology, route, active_routes.values()):
                        last_reason = "Route conflicts with an already locked route"
                        continue

                    return route
            except nx.NetworkXNoPath:
                continue

        raise ValueError(
            f"No valid route from {source_node} to signal {exit_signal.id}: {last_reason}"
        )

    def routing_graph_for_direction(self, route_direction: SignalDirection) -> nx.DiGraph:
        """Build route-search graph constrained by requested running direction.

        Physical track/point links are always bidirectional via topology.routing_graph().
        For signal virtual links, direction handling is:
        - same-direction signal: keep approach -> protected only
        - opposite-direction signal: also allow protected -> approach
        """
        graph = self.topology.routing_graph().copy()
        for approach_node, signal_id in sorted(self.topology.signal_links):
            signal = self.topology.signals.get(signal_id)
            if signal is None:
                continue
            protected_node = signal.protects.strip()
            if (
                approach_node not in graph.nodes
                or protected_node not in graph.nodes
                or approach_node == protected_node
            ):
                continue
            if signal.direction != route_direction:
                graph.add_edge(protected_node, approach_node)
        return graph

    def compute_required_point_positions(self, node_path: list[str]) -> dict[str, PointPosition]:
        """Public helper to resolve point locks for a full movement path."""
        return self._compute_required_point_positions(node_path)

    def compute_overlap_for_path(
        self,
        route_path: list[str],
        overlap_length: int,
        preferred_first_node: str | None = None,
    ) -> list[str]:
        """Public helper for overlap computation from a computed route path."""
        return self._compute_overlap(
            route_path,
            overlap_length=overlap_length,
            preferred_first_node=preferred_first_node,
        )

    def compute_flank_point_positions(
        self,
        node_path: list[str],
        route_point_positions: dict[str, PointPosition],
    ) -> dict[str, PointPosition]:
        """Public helper for flank-point lock derivation."""
        return self.flank_engine.compute_required_positions(
            route_nodes=node_path,
            route_point_positions=route_point_positions,
        )

    def compute_flank_requirements(
        self,
        node_path: list[str],
        route_point_positions: dict[str, PointPosition],
    ) -> FlankProtectionResult:
        """Public helper for flank-point and flank-section derivation."""
        return self.flank_engine.compute_requirements(
            route_nodes=node_path,
            route_point_positions=route_point_positions,
        )

    def resolve_approach_locking_section(self, entry_signal_id: str) -> str | None:
        """Public helper to resolve approach section for one entry signal."""
        return self._resolve_approach_locking_section(entry_signal_id)

    def _compute_required_point_positions(self, path: list[str]) -> dict[str, PointPosition]:
        """Compute all point positions needed to traverse the path."""
        required: dict[str, PointPosition] = {}
        for index, node_id in enumerate(path):
            element = self.topology.get_element(node_id)
            if not isinstance(element, Point):
                continue

            previous_node = path[index - 1] if index > 0 else None
            next_node = path[index + 1] if index + 1 < len(path) else None

            selected_position = self._resolve_point_position(
                point=element,
                previous_node=previous_node,
                next_node=next_node,
            )

            if selected_position is None:
                raise ValueError(
                    f"Cannot infer required position for point {element.id} in path {path}"
                )

            existing = required.get(element.id)
            if existing is not None and existing != selected_position:
                raise ValueError(
                    f"Point {element.id} requires conflicting positions {existing.value}/{selected_position.value}"
                )
            required[element.id] = selected_position

        return required

    def _resolve_point_position(
        self,
        point: Point,
        previous_node: str | None,
        next_node: str | None,
    ) -> PointPosition | None:
        facing = point.facing_connections
        if not facing:
            return None

        next_position = next(
            (position for position, successor in facing.items() if next_node and successor == next_node),
            None,
        )
        prev_position = next(
            (position for position, successor in facing.items() if previous_node and successor == previous_node),
            None,
        )

        if next_position and prev_position and next_position != prev_position:
            raise ValueError(
                f"Path requests impossible movement through point {point.id}: "
                f"{previous_node} -> {point.id} -> {next_node}"
            )
        return next_position or prev_position

    def _compute_overlap(
        self,
        route_path: list[str],
        overlap_length: int,
        preferred_first_node: str | None = None,
    ) -> list[str]:
        """Compute fixed-length overlap beyond route end along graph connectivity."""
        return self._overlap_policy_engine.compute_overlap(
            topology=self.topology,
            route_path=route_path,
            overlap_length=overlap_length,
            preferred_first_node=preferred_first_node,
        )

    def _has_front_protection_conflict(
        self,
        route_path: list[str],
        target_node: str,
        exit_protected: str,
    ) -> bool:
        if not route_path:
            return False
        boundary_nodes = {target_node, exit_protected}
        conflict_nodes: set[str] = set()
        for node_id in boundary_nodes:
            conflict_nodes.update(self.topology.clearance_conflicting_nodes(node_id))
        if not conflict_nodes:
            return False
        # Ignore final target boundary itself; only check prior route path footprint.
        route_body = set(route_path[:-1])
        return bool(route_body.intersection(conflict_nodes))

    def _resolve_approach_locking_section(self, entry_signal_id: str) -> str | None:
        signal = self.topology.signals.get(entry_signal_id)
        if signal is None:
            return None

        configured = signal.approach_section.strip()
        if configured:
            element = self.topology.get_element(configured)
            if (
                isinstance(element, ApproachSection)
                and self.topology.is_signal_back_side_node(entry_signal_id, configured)
            ):
                return configured

        for node_id in self.topology.signal_approach_nodes(entry_signal_id):
            element = self.topology.get_element(node_id)
            if isinstance(element, ApproachSection):
                return node_id
        return None
