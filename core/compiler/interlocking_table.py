"""Interlocking table generation from geographical topology."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import networkx as nx

from core.domain.model.elements import PointPosition, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from kernel.route_dispatcher.route_engine import RouteEngine


@dataclass(slots=True)
class InterlockingTableRow:
    """One interlocking-table entry for an entry->exit route."""

    route_name: str
    entry_signal: str
    exit_signal: str
    entry_element: str
    exit_element: str
    path: list[str]
    overlap: list[str]
    required_point_positions: dict[str, PointPosition]
    flank_point_positions: dict[str, PointPosition]
    locked_sections: list[str]
    conflicting_routes: list[str]


class InterlockingTableGenerator:
    """Builds a route locking table from graph connectivity."""

    def __init__(self, topology: RailwayTopology, overlap_length: int = 0) -> None:
        self.topology = topology
        self.overlap_length = max(0, overlap_length)
        self.route_engine = RouteEngine(topology)

    def generate(
        self,
        entry_signal_ids: Iterable[str],
        exit_signal_ids: Iterable[str],
        max_depth: int = 24,
    ) -> list[InterlockingTableRow]:
        """Generate one shortest valid interlocking row per entry/exit pair."""
        self.topology.sync_signal_virtual_routes()
        routes: list[Route] = []
        for entry_signal_id in entry_signal_ids:
            for exit_signal_id in exit_signal_ids:
                if entry_signal_id == exit_signal_id:
                    continue
                best_route = self._find_shortest_pair_route(
                    entry_signal_id=entry_signal_id,
                    exit_signal_id=exit_signal_id,
                    max_depth=max_depth,
                )
                if best_route is not None:
                    routes.append(best_route)

        rows: list[InterlockingTableRow] = []
        for route in routes:
            try:
                all_points = route.all_required_point_positions
            except ValueError:
                continue
            entry_signal = self.topology.signals[route.entry_signal_id]
            exit_signal = self.topology.signals[route.exit_signal_id]
            entry_element = entry_signal.protects
            exit_element = exit_signal.protects
            route_name = f"{route.entry_signal_id}->{route.exit_signal_id}"

            locked_sections = [
                node_id
                for node_id in route.full_path
                if isinstance(self.topology.get_element(node_id), TrackSection)
            ]

            rows.append(
                InterlockingTableRow(
                    route_name=route_name,
                    entry_signal=route.entry_signal_id,
                    exit_signal=route.exit_signal_id,
                    entry_element=entry_element,
                    exit_element=exit_element,
                    path=route.path,
                    overlap=route.overlap_path,
                    required_point_positions=all_points,
                    flank_point_positions=dict(route.flank_point_positions),
                    locked_sections=locked_sections,
                    conflicting_routes=[],
                )
            )

        self._compute_conflicts(rows)
        return rows

    def to_markdown(self, rows: list[InterlockingTableRow]) -> str:
        """Render rows as a markdown interlocking table."""
        lines = [
            "| Route | Entry | Exit | Point locks | Track locks | Overlap | Conflicts |",
            "|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            point_text = self._format_points(row.required_point_positions)
            tracks = " -> ".join(row.locked_sections) if row.locked_sections else "-"
            overlap = " -> ".join(row.overlap) if row.overlap else "-"
            conflicts = ", ".join(sorted(set(row.conflicting_routes))) if row.conflicting_routes else "-"
            lines.append(
                f"| {row.route_name} | {row.entry_signal} ({row.entry_element}) | "
                f"{row.exit_signal} ({row.exit_element}) | {point_text} | {tracks} | {overlap} | {conflicts} |"
            )
        return "\n".join(lines)

    def export_markdown(self, rows: list[InterlockingTableRow], path: str | Path) -> None:
        """Write markdown interlocking table."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(self.to_markdown(rows), encoding="utf-8")

    def export_csv(self, rows: list[InterlockingTableRow], path: str | Path) -> None:
        """Write CSV interlocking table."""
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(
                [
                    "route",
                    "entry_signal",
                    "entry_element",
                    "exit_signal",
                    "exit_element",
                    "point_locks",
                    "track_locks",
                    "overlap",
                    "conflicts",
                ]
            )
            for row in rows:
                writer.writerow(
                    [
                        row.route_name,
                        row.entry_signal,
                        row.entry_element,
                        row.exit_signal,
                        row.exit_element,
                        self._format_points(row.required_point_positions),
                        " -> ".join(row.locked_sections),
                        " -> ".join(row.overlap),
                        ", ".join(sorted(set(row.conflicting_routes))),
                    ]
                )

    def _enumerate_pair_routes(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        max_depth: int,
    ) -> list[Route]:
        """Compatibility wrapper that returns at most one shortest route."""
        best = self._find_shortest_pair_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            max_depth=max_depth,
        )
        return [best] if best is not None else []

    def _find_shortest_pair_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        max_depth: int,
    ) -> Route | None:
        """Return the shortest valid route for a signal pair, if any."""
        entry_signal = self.topology.signals.get(entry_signal_id)
        exit_signal = self.topology.signals.get(exit_signal_id)
        if entry_signal is None or exit_signal is None:
            return None
        if entry_signal.direction != exit_signal.direction:
            return None
        if not entry_signal.protects or not exit_signal.protects:
            return None
        entry_protected = self.topology.signal_protected_node(entry_signal_id)
        exit_protected = self.topology.signal_protected_node(exit_signal_id)
        if entry_protected is None or exit_protected is None:
            return None
        if entry_protected == exit_protected:
            return None
        exit_approach_nodes = self.topology.signal_approach_nodes(exit_signal_id)
        if not exit_approach_nodes:
            return None

        try:
            route_graph = self.route_engine.routing_graph_for_direction(entry_signal.direction)
            path_list: list[list[str]] = []
            for target_node in exit_approach_nodes:
                try:
                    all_paths = nx.all_simple_paths(
                        route_graph,
                        source=entry_protected,
                        target=target_node,
                        cutoff=max_depth,
                    )
                    path_list.extend(list(all_paths))
                except nx.NetworkXNoPath:
                    continue
            # Sort shortest first by hop count, then lexicographically for deterministic tie-break.
            path_list = sorted(path_list, key=lambda p: (len(p), p))
        except nx.NetworkXNoPath:
            return None

        if not path_list:
            return None

        for index, path in enumerate(path_list, start=1):
            overlap_path = self.route_engine.compute_overlap_for_path(
                path,
                overlap_length=self.overlap_length,
                preferred_first_node=exit_protected,
            )
            try:
                required_points = self.route_engine.compute_required_point_positions(
                    [*path, *overlap_path]
                )
                flank_result = self.route_engine.compute_flank_requirements(
                    [*path, *overlap_path],
                    required_points,
                    entry_signal_id=entry_signal_id,
                    route_start_node=(path[0] if path else None),
                )
            except ValueError:
                continue
            route = Route(
                id=f"R_{entry_signal_id}_{exit_signal_id}_{index:02d}",
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                path=path,
                overlap_path=overlap_path,
                required_point_positions=required_points,
                flank_point_positions=flank_result.required_point_positions,
                monitored_flank_sections=flank_result.monitored_flank_sections,
                approach_locking_section=self.route_engine.resolve_approach_locking_section(
                    entry_signal_id
                ),
            )
            return route
        return None

    def _compute_conflicts(self, rows: list[InterlockingTableRow]) -> None:
        for i, row_i in enumerate(rows):
            nodes_i = set(row_i.path + row_i.overlap)
            points_i = set(row_i.required_point_positions)
            for j, row_j in enumerate(rows):
                if i == j:
                    continue
                nodes_j = set(row_j.path + row_j.overlap)
                points_j = set(row_j.required_point_positions)
                if (
                    nodes_i.intersection(nodes_j)
                    or self.topology.sets_conflict_by_clearance(nodes_i, nodes_j)
                    or points_i.intersection(points_j)
                ):
                    row_i.conflicting_routes.append(row_j.route_name)

    @staticmethod
    def _format_points(required: dict[str, PointPosition]) -> str:
        if not required:
            return "-"
        tokens = [f"{point}:{position.value}" for point, position in sorted(required.items())]
        return ", ".join(tokens)
