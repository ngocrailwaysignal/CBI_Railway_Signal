"""Interlocking table generation from geographical topology."""

from __future__ import annotations

import csv
import heapq
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import networkx as nx

from core.domain.model.elements import PointPosition, SignalAspect, SignalDirection, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import ROUTE_TYPE_REVERSE, RailwayTopology
from kernel.route_dispatcher.route_engine import RouteEngine


@dataclass(slots=True)
class InterlockingTableRow:
    """One interlocking-table entry for an entry->exit route."""

    route_name: str
    entry_signal: str
    exit_signal: str
    entry_element: str
    exit_element: str
    entry_protected_section: str | None
    exit_protected_section: str | None
    path: list[str]
    overlap: list[str]
    required_point_positions: dict[str, PointPosition]
    flank_point_positions: dict[str, PointPosition]
    locked_sections: list[str]
    conflicting_routes: list[str]
    is_calling_on: bool = False
    is_reverse: bool = False
    signal_aspect: SignalAspect = SignalAspect.GREEN


class InterlockingTableGenerator:
    """Builds a route locking table from graph connectivity."""

    def __init__(self, topology: RailwayTopology, overlap_length: int = 0) -> None:
        self.topology = topology
        self.overlap_length = max(0, overlap_length)
        self.route_engine = RouteEngine(topology)
        self._route_graph_cache: dict[SignalDirection, nx.DiGraph] = {}
        self._pair_route_cache: dict[tuple[str, str, int, bool, bool], Route | None] = {}

    def generate(
        self,
        entry_signal_ids: Iterable[str],
        exit_signal_ids: Iterable[str],
        max_depth: int = 24,
    ) -> list[InterlockingTableRow]:
        """Generate nearest automatic route per entry plus manually marked routes."""
        self._route_graph_cache.clear()
        self._pair_route_cache.clear()
        self.topology.sync_signal_virtual_routes()
        entry_set = {str(signal_id) for signal_id in entry_signal_ids}
        exit_set = {str(signal_id) for signal_id in exit_signal_ids}
        calling_on_pairs = self.topology.configured_calling_on_pairs()
        reverse_pairs = self.topology.configured_reverse_route_pairs()
        special_pairs = calling_on_pairs
        pair_flags: dict[tuple[str, str], tuple[bool, bool]] = {}

        def add_pair(
            entry_signal_id: str, exit_signal_id: str, *, calling_on: bool, reverse: bool
        ) -> None:
            if entry_signal_id == exit_signal_id:
                return
            if entry_signal_id not in entry_set or exit_signal_id not in exit_set:
                return
            existing_calling_on, existing_reverse = pair_flags.get(
                (entry_signal_id, exit_signal_id),
                (False, False),
            )
            pair_flags[(entry_signal_id, exit_signal_id)] = (
                existing_calling_on or calling_on,
                existing_reverse or reverse,
            )

        for entry_signal_id in sorted(entry_set):
            entry_signal = self.topology.signals.get(entry_signal_id)
            if entry_signal is None or entry_signal.is_blocking:
                continue
            nearest_exit_signal_id: str | None = None
            nearest_path_length: int | None = None
            for exit_signal_id in sorted(exit_set):
                exit_signal = self.topology.signals.get(exit_signal_id)
                if exit_signal is None or exit_signal.is_blocking:
                    continue
                if entry_signal_id == exit_signal_id:
                    continue
                if (entry_signal_id, exit_signal_id) in special_pairs:
                    continue
                if entry_signal.direction != exit_signal.direction:
                    continue
                route = self._find_shortest_pair_route(
                    entry_signal_id,
                    exit_signal_id,
                    max_depth=max_depth,
                    is_calling_on=False,
                    is_reverse=(entry_signal_id, exit_signal_id) in reverse_pairs,
                )
                if route is None:
                    continue
                path_length = len(route.path)
                if (
                    nearest_path_length is None
                    or path_length < nearest_path_length
                    or (
                        path_length == nearest_path_length
                        and exit_signal_id < (nearest_exit_signal_id or "")
                    )
                ):
                    nearest_exit_signal_id = exit_signal_id
                    nearest_path_length = path_length
            if nearest_exit_signal_id is not None:
                add_pair(
                    entry_signal_id,
                    nearest_exit_signal_id,
                    calling_on=False,
                    reverse=(entry_signal_id, nearest_exit_signal_id) in reverse_pairs,
                )

        configured_pairs = calling_on_pairs | reverse_pairs
        for entry_signal_id in sorted(entry_set):
            entry_signal = self.topology.signals.get(entry_signal_id)
            if entry_signal is None or entry_signal.is_blocking:
                continue
            for exit_signal_id in sorted(exit_set):
                exit_signal = self.topology.signals.get(exit_signal_id)
                if exit_signal is None or exit_signal.is_blocking:
                    continue
                if entry_signal_id == exit_signal_id:
                    continue
                if (entry_signal_id, exit_signal_id) in configured_pairs:
                    continue
                if (entry_signal_id, exit_signal_id) in pair_flags:
                    continue
                if entry_signal.direction != exit_signal.direction:
                    continue
                if not (
                    bool(getattr(entry_signal, "is_reverse_signal", False))
                    and bool(getattr(exit_signal, "is_reverse_signal", False))
                ):
                    continue
                if (
                    self._find_shortest_pair_route(
                        entry_signal_id=entry_signal_id,
                        exit_signal_id=exit_signal_id,
                        max_depth=max_depth,
                        is_reverse=True,
                    )
                    is None
                ):
                    continue
                add_pair(
                    entry_signal_id,
                    exit_signal_id,
                    calling_on=False,
                    reverse=True,
                )

        for entry_signal_id, exit_signal_id in sorted(calling_on_pairs):
            add_pair(
                entry_signal_id,
                exit_signal_id,
                calling_on=True,
                reverse=False,
            )
        for entry_signal_id, exit_signal_id in sorted(reverse_pairs):
            add_pair(
                entry_signal_id,
                exit_signal_id,
                calling_on=False,
                reverse=True,
            )

        routes: list[Route] = []
        for (entry_signal_id, exit_signal_id), (is_calling_on, is_reverse) in sorted(
            pair_flags.items()
        ):
            best_route = self._find_shortest_pair_route(
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                max_depth=max_depth,
                is_calling_on=is_calling_on,
                is_reverse=is_reverse,
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
            entry_protected_section = self.route_engine.resolve_effective_protected_section(
                route.entry_signal_id,
                route.path,
            )
            exit_protected_section = self.route_engine.resolve_effective_protected_section(
                route.exit_signal_id,
                route.path,
            )
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
                    entry_protected_section=entry_protected_section,
                    exit_protected_section=exit_protected_section,
                    path=route.path,
                    overlap=route.overlap_path,
                    required_point_positions=all_points,
                    flank_point_positions=dict(route.flank_point_positions),
                    locked_sections=locked_sections,
                    conflicting_routes=[],
                    is_calling_on=route.is_calling_on,
                    is_reverse=route.is_reverse,
                    signal_aspect=route.signal_aspect,
                )
            )

        self._compute_conflicts(rows)
        return rows

    def to_markdown(self, rows: list[InterlockingTableRow]) -> str:
        """Render rows as a markdown interlocking table."""
        lines = [
            (
                "| Route | Entry | Exit | Signal Aspect | Entry protected section | "
                "Exit protected section | Normal | Reverse | Reverse Route | "
                "Calling-on Route | Track locks | Overlap | Conflicts |"
            ),
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for row in rows:
            normal_points = self._format_points_for_position(
                row.required_point_positions,
                PointPosition.NORMAL,
            )
            reverse_points = self._format_points_for_position(
                row.required_point_positions,
                PointPosition.REVERSE,
            )
            tracks = " -> ".join(row.locked_sections) if row.locked_sections else "-"
            overlap = " -> ".join(row.overlap) if row.overlap else "-"
            entry_protected_section = row.entry_protected_section or "-"
            exit_protected_section = row.exit_protected_section or "-"
            conflicts = (
                ", ".join(sorted(set(row.conflicting_routes))) if row.conflicting_routes else "-"
            )
            lines.append(
                f"| {row.route_name} | {row.entry_signal} ({row.entry_element}) | "
                f"{row.exit_signal} ({row.exit_element}) | {row.signal_aspect.value} | "
                f"{entry_protected_section} | "
                f"{exit_protected_section} | {normal_points} | {reverse_points} | "
                f"{self._format_mark(row.is_reverse)} | {self._format_mark(row.is_calling_on)} | "
                f"{tracks} | {overlap} | {conflicts} |"
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
                    "signal_aspect",
                    "entry_protected_section",
                    "exit_protected_section",
                    "normal_points",
                    "reverse_points",
                    "reverse_route",
                    "calling_on_route",
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
                        row.signal_aspect.value,
                        row.entry_protected_section or "",
                        row.exit_protected_section or "",
                        self._format_points_for_position(
                            row.required_point_positions,
                            PointPosition.NORMAL,
                            empty="",
                        ),
                        self._format_points_for_position(
                            row.required_point_positions,
                            PointPosition.REVERSE,
                            empty="",
                        ),
                        self._format_mark(row.is_reverse),
                        self._format_mark(row.is_calling_on),
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
        is_calling_on: bool = False,
        is_reverse: bool = False,
    ) -> list[Route]:
        """Compatibility wrapper that returns at most one shortest route."""
        best = self._find_shortest_pair_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            max_depth=max_depth,
            is_calling_on=is_calling_on,
            is_reverse=is_reverse,
        )
        return [best] if best is not None else []

    def _find_shortest_pair_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        max_depth: int,
        is_calling_on: bool = False,
        is_reverse: bool = False,
    ) -> Route | None:
        """Return the shortest valid route for a signal pair, if any."""
        cache_key = (
            entry_signal_id,
            exit_signal_id,
            int(max_depth),
            bool(is_calling_on),
            bool(is_reverse),
        )
        if cache_key in self._pair_route_cache:
            return self._pair_route_cache[cache_key]

        entry_signal = self.topology.signals.get(entry_signal_id)
        exit_signal = self.topology.signals.get(exit_signal_id)
        if entry_signal is None or exit_signal is None:
            self._pair_route_cache[cache_key] = None
            return None
        if entry_signal.is_blocking:
            self._pair_route_cache[cache_key] = None
            return None
        if exit_signal.is_blocking and not is_calling_on:
            self._pair_route_cache[cache_key] = None
            return None
        if entry_signal.direction != exit_signal.direction:
            self._pair_route_cache[cache_key] = None
            return None
        if not entry_signal.protects or not exit_signal.protects:
            self._pair_route_cache[cache_key] = None
            return None
        entry_protected = self.topology.signal_protected_node(entry_signal_id)
        exit_protected = self.topology.signal_protected_node(exit_signal_id)
        if entry_protected is None or exit_protected is None:
            self._pair_route_cache[cache_key] = None
            return None
        if entry_protected == exit_protected:
            self._pair_route_cache[cache_key] = None
            return None
        exit_target_nodes = self.route_engine.route_exit_target_nodes(exit_signal_id)
        if not exit_target_nodes:
            self._pair_route_cache[cache_key] = None
            return None

        route_graph = self._routing_graph_for_direction(entry_signal.direction)
        if entry_protected not in route_graph:
            self._pair_route_cache[cache_key] = None
            return None

        for index, path in enumerate(
            self._iter_bounded_simple_paths(
                route_graph,
                source=entry_protected,
                targets=exit_target_nodes,
                max_depth=max_depth,
            ),
            start=1,
        ):
            overlap_path = self.route_engine.compute_overlap_for_path(
                path,
                overlap_length=self.overlap_length,
                preferred_first_node=exit_protected,
            )
            try:
                signal_aspect = self.topology.route_signal_aspect(
                    entry_signal_id,
                    exit_signal_id,
                )
                if is_reverse and not self.topology.is_reverse_route_pair(
                    entry_signal_id,
                    exit_signal_id,
                ):
                    signal_aspect = RailwayTopology.default_route_signal_aspect(
                        ROUTE_TYPE_REVERSE
                    )
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
                is_calling_on=is_calling_on,
                is_reverse=is_reverse,
                signal_aspect=signal_aspect,
            )
            self._pair_route_cache[cache_key] = route
            return route
        self._pair_route_cache[cache_key] = None
        return None

    def _routing_graph_for_direction(self, direction: SignalDirection) -> nx.DiGraph:
        graph = self._route_graph_cache.get(direction)
        if graph is None:
            graph = self.route_engine.routing_graph_for_direction(direction)
            self._route_graph_cache[direction] = graph
        return graph

    @staticmethod
    def _iter_bounded_simple_paths(
        graph: nx.DiGraph,
        *,
        source: str,
        targets: Iterable[str],
        max_depth: int,
    ) -> Iterable[list[str]]:
        """Yield simple paths by hop count, then lexicographic node order."""
        target_set = {target for target in targets if target in graph}
        if not target_set or source not in graph:
            return

        max_edges = max(0, int(max_depth))
        sequence = 0
        heap: list[tuple[int, tuple[str, ...], int, list[str]]] = [
            (1, (source,), sequence, [source])
        ]
        while heap:
            _path_length, _path_key, _sequence, path = heapq.heappop(heap)
            current = path[-1]
            if current in target_set:
                yield path
                continue
            if len(path) - 1 >= max_edges:
                continue
            for successor in sorted(graph.successors(current)):
                if successor in path:
                    continue
                next_path = [*path, successor]
                sequence += 1
                heapq.heappush(
                    heap,
                    (len(next_path), tuple(next_path), sequence, next_path),
                )

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

    @staticmethod
    def point_ids_for_position(
        required: dict[str, PointPosition],
        position: PointPosition,
    ) -> list[str]:
        return sorted(
            point_id
            for point_id, required_position in required.items()
            if required_position == position
        )

    @classmethod
    def _format_points_for_position(
        cls,
        required: dict[str, PointPosition],
        position: PointPosition,
        *,
        empty: str = "-",
    ) -> str:
        points = cls.point_ids_for_position(required, position)
        return ", ".join(points) if points else empty

    @staticmethod
    def _format_mark(value: bool) -> str:
        return "\u221a" if value else ""
