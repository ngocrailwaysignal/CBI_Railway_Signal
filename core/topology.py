"""Railway topology graph and persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import networkx as nx

from core.elements import (
    Point,
    PointPosition,
    RailElement,
    Signal,
    SignalAspect,
    SignalRole,
    TrackSection,
)


class RailwayTopology:
    """Geographical topology represented by a directed graph."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self.signals: Dict[str, Signal] = {}
        # Includes both Signal->Node protect links and Node->Signal approach links.
        self.signal_links: set[tuple[str, str]] = set()
        # Graph edges synthesized from Node->Signal + Signal.protects.
        self._signal_virtual_edges: set[tuple[str, str]] = set()
        self.ui_positions: Dict[str, tuple[float, float]] = {}

    def add_section(self, section: TrackSection, position: tuple[float, float] | None = None) -> None:
        """Add a track section node."""
        self.graph.add_node(section.id, element=section)
        if position is not None:
            self.ui_positions[section.id] = position

    def add_point(self, point: Point, position: tuple[float, float] | None = None) -> None:
        """Add a point node."""
        self.graph.add_node(point.id, element=point)
        if position is not None:
            self.ui_positions[point.id] = position

    def add_signal(self, signal: Signal, position: tuple[float, float] | None = None) -> None:
        """Add a signal (stored outside the graph)."""
        self.signals[signal.id] = signal
        if position is not None:
            self.ui_positions[signal.id] = position

    def connect(self, source_id: str, target_id: str) -> None:
        """Connect two elements with directed adjacency."""
        source = self.get_element(source_id)
        target = self.get_element(target_id)
        if source is None or target is None:
            raise KeyError(f"Unknown element in connection: {source_id} -> {target_id}")

        if isinstance(source, Signal):
            if target_id not in self.graph.nodes:
                raise ValueError("Signals must protect a track section or point node")
            if source.protects:
                self.signal_links.discard((source.id, source.protects))
            source.protects = target_id
            self.signal_links.add((source.id, target_id))
            self.sync_signal_virtual_routes()
            return

        if isinstance(target, Signal):
            self.signal_links.add((source_id, target_id))
            self.sync_signal_virtual_routes()
            return

        # If callers explicitly reconnect an existing virtual edge, treat it as explicit.
        self._signal_virtual_edges.discard((source_id, target_id))
        self.graph.add_edge(source_id, target_id)
        if isinstance(source, Point):
            self._sync_point_facing_connections(source)

    def disconnect(self, source_id: str, target_id: str) -> None:
        """Disconnect two elements and refresh derived signal-route edges."""
        source = self.get_element(source_id)
        target = self.get_element(target_id)
        if source is None or target is None:
            return

        if isinstance(source, Signal):
            self.signal_links.discard((source_id, target_id))
            if source.protects == target_id:
                source.protects = ""
            self.sync_signal_virtual_routes()
            return

        if isinstance(target, Signal):
            self.signal_links.discard((source_id, target_id))
            self.sync_signal_virtual_routes()
            return

        if self.graph.has_edge(source_id, target_id):
            self.graph.remove_edge(source_id, target_id)
        self._signal_virtual_edges.discard((source_id, target_id))
        if isinstance(source, Point):
            self._sync_point_facing_connections(source)

    def sync_signal_virtual_routes(self) -> None:
        """Rebuild virtual graph edges implied by Node->Signal->ProtectedNode chains."""
        for src, dst in list(self._signal_virtual_edges):
            if self.graph.has_edge(src, dst):
                self.graph.remove_edge(src, dst)
        self._signal_virtual_edges.clear()

        for source_id, signal_id in sorted(self.signal_links):
            if source_id not in self.graph.nodes:
                continue
            signal = self.signals.get(signal_id)
            if signal is None:
                continue
            protected = signal.protects
            if protected not in self.graph.nodes:
                continue
            if source_id == protected:
                continue
            edge = (source_id, protected)
            if self.graph.has_edge(*edge):
                continue
            self.graph.add_edge(*edge)
            self._signal_virtual_edges.add(edge)

        self.normalize_point_facing_connections()

    def get_element(self, element_id: str) -> Optional[RailElement]:
        """Get any element by id."""
        if element_id in self.signals:
            return self.signals[element_id]
        if element_id in self.graph.nodes:
            node_data = self.graph.nodes[element_id]
            return node_data["element"]
        return None

    def update_position(self, element_id: str, position: tuple[float, float]) -> None:
        """Store canvas position for an element."""
        self.ui_positions[element_id] = position

    def successors(self, node_id: str) -> list[str]:
        """Return outgoing neighbors for a graph node."""
        if node_id not in self.graph.nodes:
            return []
        return list(self.graph.successors(node_id))

    def graph_node_ids(self) -> Iterable[str]:
        """Return ids of graph-contained nodes."""
        return self.graph.nodes

    def signal_approach_nodes(self, signal_id: str) -> list[str]:
        """Return graph nodes that connect into the given signal."""
        return sorted(
            source_id
            for source_id, target_id in self.signal_links
            if target_id == signal_id and source_id in self.graph.nodes
        )

    def normalize_point_facing_connections(self) -> None:
        """Normalize point branch mapping from current graph topology."""
        for node_id in self.graph.nodes:
            element = self.graph.nodes[node_id]["element"]
            if isinstance(element, Point):
                self._sync_point_facing_connections(element)

    def _sync_point_facing_connections(self, point: Point) -> None:
        """Keep point branch mapping consistent with outgoing graph edges."""
        incident = sorted(self.graph.to_undirected(as_view=True).neighbors(point.id))
        if len(incident) > 3:
            raise ValueError(
                f"Point {point.id} has {len(incident)} connected tracks; expected at most 3"
            )
        outgoing = sorted(self.graph.successors(point.id))

        cleaned: dict[PointPosition, str] = {}
        used_targets: set[str] = set()
        for position in (PointPosition.NORMAL, PointPosition.REVERSE):
            target = point.facing_connections.get(position)
            if target in incident and target not in used_targets:
                cleaned[position] = target
                used_targets.add(target)

        remaining = [node for node in outgoing if node not in used_targets]
        for position in (PointPosition.NORMAL, PointPosition.REVERSE):
            if position not in cleaned and remaining:
                cleaned[position] = remaining.pop(0)

        point.facing_connections = cleaned

    def export_to_json(self, path: str | Path) -> None:
        """Serialize layout and runtime state to JSON."""
        payload: Dict[str, Any] = {
            "sections": [],
            "points": [],
            "signals": [],
            "edges": [],
            "signal_links": [],
            "ui_positions": {},
        }

        for node_id in self.graph.nodes:
            element = self.graph.nodes[node_id]["element"]
            if isinstance(element, TrackSection):
                payload["sections"].append(
                    {
                        "id": element.id,
                        "occupied": element.occupied,
                        "locked_by": element.locked_by,
                        "length": element.length,
                    }
                )
            elif isinstance(element, Point):
                payload["points"].append(
                    {
                        "id": element.id,
                        "position": element.position.value,
                        "locked_by": element.locked_by,
                        "facing_connections": {
                            key.value: value for key, value in element.facing_connections.items()
                        },
                    }
                )

        for signal in self.signals.values():
            payload["signals"].append(
                {
                    "id": signal.id,
                    "aspect": signal.aspect.value,
                    "role": signal.role.value,
                    "protects": signal.protects,
                    "route_id": signal.route_id,
                }
            )

        payload["edges"] = [
            [src, dst] for src, dst in self.graph.edges if (src, dst) not in self._signal_virtual_edges
        ]
        payload["signal_links"] = [list(link) for link in sorted(self.signal_links)]
        payload["ui_positions"] = {
            key: [float(value[0]), float(value[1])] for key, value in self.ui_positions.items()
        }

        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load_from_json(cls, path: str | Path) -> "RailwayTopology":
        """Load topology from JSON."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        topology = cls()

        positions = data.get("ui_positions", {})

        for section_data in data.get("sections", []):
            section = TrackSection(
                id=section_data["id"],
                occupied=bool(section_data.get("occupied", False)),
                locked_by=section_data.get("locked_by"),
                length=float(section_data.get("length", 100.0)),
            )
            section_pos = positions.get(section.id)
            topology.add_section(
                section,
                position=(float(section_pos[0]), float(section_pos[1])) if section_pos else None,
            )

        for point_data in data.get("points", []):
            facing = point_data.get("facing_connections", {})
            point = Point(
                id=point_data["id"],
                position=PointPosition(point_data.get("position", PointPosition.NORMAL.value)),
                locked_by=point_data.get("locked_by"),
                facing_connections={
                    PointPosition(key): value for key, value in facing.items() if value
                },
            )
            point_pos = positions.get(point.id)
            topology.add_point(
                point,
                position=(float(point_pos[0]), float(point_pos[1])) if point_pos else None,
            )

        for signal_data in data.get("signals", []):
            signal = Signal(
                id=signal_data["id"],
                aspect=SignalAspect(signal_data.get("aspect", SignalAspect.STOP.value)),
                role=SignalRole(signal_data.get("role", SignalRole.AUTO.value)),
                protects=signal_data.get("protects", ""),
                route_id=signal_data.get("route_id"),
            )
            signal_pos = positions.get(signal.id)
            topology.add_signal(
                signal,
                position=(float(signal_pos[0]), float(signal_pos[1])) if signal_pos else None,
            )

        for source_id, target_id in data.get("edges", []):
            if source_id in topology.graph.nodes and target_id in topology.graph.nodes:
                topology.graph.add_edge(source_id, target_id)

        raw_signal_links = data.get("signal_links", [])
        if isinstance(raw_signal_links, list):
            for link in raw_signal_links:
                if not isinstance(link, list | tuple) or len(link) != 2:
                    continue
                source_id, target_id = str(link[0]), str(link[1])
                if topology.get_element(source_id) is None or topology.get_element(target_id) is None:
                    continue
                topology.signal_links.add((source_id, target_id))

        # Backward compatibility for files without signal_links.
        for signal in topology.signals.values():
            if signal.protects and signal.protects in topology.graph.nodes:
                topology.signal_links.add((signal.id, signal.protects))

        topology.sync_signal_virtual_routes()

        return topology

    def resolve_signal_role(self, signal_id: str) -> SignalRole:
        """Resolve signal role using explicit setting or topology heuristics."""
        signal = self.signals.get(signal_id)
        if signal is None:
            raise KeyError(f"Unknown signal: {signal_id}")
        if signal.role != SignalRole.AUTO:
            return signal.role

        x_position = self.ui_positions.get(signal_id, (None, None))[0]
        known_x = [
            self.ui_positions[sid][0]
            for sid in self.signals
            if sid in self.ui_positions and self.ui_positions[sid][0] is not None
        ]
        if x_position is not None and len(known_x) >= 2:
            left, right = min(known_x), max(known_x)
            midpoint = (left + right) / 2.0
            if x_position <= midpoint:
                return SignalRole.ENTRY
            return SignalRole.EXIT

        protected = signal.protects
        if protected in self.graph.nodes:
            in_degree = self.graph.in_degree(protected)
            out_degree = self.graph.out_degree(protected)
            if in_degree == 0 and out_degree > 0:
                return SignalRole.ENTRY
            if out_degree == 0 and in_degree > 0:
                return SignalRole.EXIT

        prefix = "".join(ch for ch in signal.id if ch.isalpha()).upper()
        if prefix.startswith("A"):
            return SignalRole.ENTRY
        if prefix.startswith(("B", "C", "D", "X")):
            return SignalRole.EXIT

        return SignalRole.BOTH
