"""Railway topology graph and persistence."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import networkx as nx

from core.domain.model.elements import (
    ApproachSection,
    Point,
    PointPosition,
    PointSymbolOrientation,
    RailElement,
    Signal,
    SignalAspect,
    SignalDirection,
    TrackSection,
)


class RailwayTopology:
    """Geographical topology represented by a directed graph."""

    def __init__(self) -> None:
        self.graph: nx.DiGraph = nx.DiGraph()
        self.signals: Dict[str, Signal] = {}
        # Only Node->Signal approach links are persisted in this set.
        self.signal_links: set[tuple[str, str]] = set()
        # Graph edges synthesized from Node->Signal + Signal.protects.
        self._signal_virtual_edges: set[tuple[str, str]] = set()
        # Metadata for special (profile/clearance) route conflicts.
        self.clearance_conflict_groups: list[set[str]] = []
        self.ui_positions: Dict[str, tuple[float, float]] = {}

    def add_section(self, section: TrackSection, position: tuple[float, float] | None = None) -> None:
        """Add a track section node."""
        self.graph.add_node(section.id, element=section)
        if position is not None:
            self.ui_positions[section.id] = position

    def add_approach_section(
        self,
        section: ApproachSection,
        position: tuple[float, float] | None = None,
    ) -> None:
        """Add an approach-locking track section node."""
        self.add_section(section, position=position)

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
            source.protects = target_id
            self.sync_signal_virtual_routes()
            return

        if isinstance(target, Signal):
            self.signal_links.add((source_id, target_id))
            if (
                isinstance(source, ApproachSection)
                and not target.approach_section
                and self.is_signal_back_side_node(target_id, source_id)
            ):
                target.approach_section = source_id
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
            if source.protects == target_id:
                source.protects = ""
            self.sync_signal_virtual_routes()
            return

        if isinstance(target, Signal):
            self.signal_links.discard((source_id, target_id))
            if target.approach_section == source_id:
                target.approach_section = ""
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

    def routing_graph(self) -> nx.DiGraph:
        """Return directed routing graph.

        Track/point physical links are treated bidirectionally, while signal
        virtual links keep their operational direction (approach -> protected).
        """
        self.sync_signal_virtual_routes()

        route_graph = nx.DiGraph()
        route_graph.add_nodes_from(self.graph.nodes)

        for source_id, target_id in self.graph.edges:
            if (source_id, target_id) in self._signal_virtual_edges:
                route_graph.add_edge(source_id, target_id)
            else:
                route_graph.add_edge(source_id, target_id)
                route_graph.add_edge(target_id, source_id)
        return route_graph

    def graph_node_ids(self) -> Iterable[str]:
        """Return ids of graph-contained nodes."""
        return self.graph.nodes

    def signal_approach_nodes(self, signal_id: str) -> list[str]:
        """Return graph nodes that connect into the given signal from its rear side."""
        candidates = sorted(
            source_id
            for source_id, target_id in self.signal_links
            if target_id == signal_id and source_id in self.graph.nodes
        )
        return [node_id for node_id in candidates if self._is_node_on_signal_back_side(signal_id, node_id)]

    def signal_protected_node(self, signal_id: str) -> str | None:
        """Return protected node only when it is on the signal front side."""
        signal = self.signals.get(signal_id)
        if signal is None:
            return None
        node_id = signal.protects.strip()
        if node_id not in self.graph.nodes:
            return None
        if not self._is_node_on_signal_front_side(signal_id, node_id):
            return None
        return node_id

    def is_signal_front_side_node(self, signal_id: str, node_id: str) -> bool:
        """Public wrapper for front-side checks."""
        return self._is_node_on_signal_front_side(signal_id, node_id)

    def is_signal_back_side_node(self, signal_id: str, node_id: str) -> bool:
        """Public wrapper for rear-side checks."""
        return self._is_node_on_signal_back_side(signal_id, node_id)

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

    def _is_node_on_signal_front_side(self, signal_id: str, node_id: str) -> bool:
        relative_side = self._signal_relative_side(signal_id, node_id)
        if relative_side is None:
            return True
        signal = self.signals.get(signal_id)
        if signal is None:
            return True
        if signal.direction == SignalDirection.RIGHT:
            return relative_side == "RIGHT"
        return relative_side == "LEFT"

    def _is_node_on_signal_back_side(self, signal_id: str, node_id: str) -> bool:
        relative_side = self._signal_relative_side(signal_id, node_id)
        if relative_side is None:
            return True
        signal = self.signals.get(signal_id)
        if signal is None:
            return True
        if signal.direction == SignalDirection.RIGHT:
            return relative_side == "LEFT"
        return relative_side == "RIGHT"

    def _signal_relative_side(self, signal_id: str, node_id: str) -> str | None:
        signal_pos = self.ui_positions.get(signal_id)
        node_pos = self.ui_positions.get(node_id)
        if signal_pos is None or node_pos is None:
            return None
        dx = float(node_pos[0]) - float(signal_pos[0])
        if abs(dx) <= 1e-6:
            return None
        return "RIGHT" if dx > 0 else "LEFT"

    def clear_runtime_state(self, keep_occupancy: bool = True) -> None:
        """Reset transient runtime state while preserving static topology."""
        for node_id in self.graph.nodes:
            element = self.graph.nodes[node_id]["element"]
            if isinstance(element, TrackSection):
                if not keep_occupancy:
                    element.occupied = False
                element.locked_by = None
            elif isinstance(element, Point):
                element.locked_by = None

        for signal in self.signals.values():
            signal.aspect = SignalAspect.STOP
            signal.route_id = None

    def add_clearance_conflict_group(self, nodes: set[str]) -> None:
        """Register a special clearance/profile conflict group."""
        normalized = {str(node_id).strip() for node_id in nodes if str(node_id).strip()}
        if len(normalized) < 2:
            return
        if any(existing == normalized for existing in self.clearance_conflict_groups):
            return
        self.clearance_conflict_groups.append(normalized)

    def node_conflicts_with(self, node_id: str, other_nodes: set[str]) -> bool:
        """Return True if one node conflicts with any node in the other set by metadata."""
        target = str(node_id).strip()
        if not target or not other_nodes:
            return False
        normalized_other = {str(other).strip() for other in other_nodes if str(other).strip()}
        if target in normalized_other:
            return True
        for group in self.clearance_conflict_groups:
            if target not in group:
                continue
            if group.intersection(normalized_other):
                return True
        return False

    def sets_conflict_by_clearance(self, node_set_a: set[str], node_set_b: set[str]) -> bool:
        """Return True if any node pair across sets conflicts via clearance metadata."""
        normalized_a = {str(node_id).strip() for node_id in node_set_a if str(node_id).strip()}
        normalized_b = {str(node_id).strip() for node_id in node_set_b if str(node_id).strip()}
        if not normalized_a or not normalized_b:
            return False
        for group in self.clearance_conflict_groups:
            if group.intersection(normalized_a) and group.intersection(normalized_b):
                return True
        return False

    def clearance_conflicting_nodes(self, node_id: str) -> set[str]:
        """Return nodes that have special clearance conflict with one node."""
        target = str(node_id).strip()
        if not target:
            return set()
        conflicts: set[str] = set()
        for group in self.clearance_conflict_groups:
            if target in group:
                conflicts.update(group)
        conflicts.discard(target)
        return conflicts

    def validate_signal_configuration(self) -> list[str]:
        """Validate signal direction/protect mappings and conflicting protects."""
        issues: list[str] = []
        protected_to_signals: dict[str, list[Signal]] = defaultdict(list)

        for signal in sorted(self.signals.values(), key=lambda item: item.id):
            protected = signal.protects.strip()
            if not protected:
                issues.append(f"Signal {signal.id} has no protected section/point")
                continue
            if protected not in self.graph.nodes:
                issues.append(
                    f"Signal {signal.id} protects unknown element {protected}"
                )
                continue
            if self.signal_protected_node(signal.id) is None:
                issues.append(
                    f"Signal {signal.id} protects {protected} on wrong side for direction {signal.direction.value}"
                )
                continue
            protected_to_signals[protected].append(signal)

        for protected, signals in sorted(protected_to_signals.items()):
            by_direction: dict[SignalDirection, list[str]] = defaultdict(list)
            for signal in signals:
                by_direction[signal.direction].append(signal.id)
            for direction, signal_ids in sorted(
                by_direction.items(), key=lambda item: item[0].value
            ):
                if len(signal_ids) > 1:
                    joined = ", ".join(sorted(signal_ids))
                    issues.append(
                        f"Protected node {protected} is assigned to multiple {direction.value} signals: {joined}"
                    )
        return issues

    def validate_signal_pair(self, entry_signal_id: str, exit_signal_id: str) -> list[str]:
        """Validate one route request pair before route finding."""
        issues: list[str] = []
        entry_signal = self.signals.get(entry_signal_id)
        exit_signal = self.signals.get(exit_signal_id)
        if entry_signal is None:
            return [f"Unknown entry signal {entry_signal_id}"]
        if exit_signal is None:
            return [f"Unknown exit signal {exit_signal_id}"]
        if entry_signal.direction != exit_signal.direction:
            issues.append(
                f"Entry {entry_signal_id} and exit {exit_signal_id} have opposite directions "
                f"({entry_signal.direction.value}/{exit_signal.direction.value})"
            )

        entry_protected = self.signal_protected_node(entry_signal_id)
        exit_protected = self.signal_protected_node(exit_signal_id)
        if entry_protected is None:
            issues.append(
                f"Entry signal {entry_signal_id} has invalid protects for direction {entry_signal.direction.value}"
            )
        if exit_protected is None:
            issues.append(
                f"Exit signal {exit_signal_id} has invalid protects for direction {exit_signal.direction.value}"
            )
        if entry_protected and exit_protected and entry_protected == exit_protected:
            issues.append(
                f"Entry {entry_signal_id} and exit {exit_signal_id} protect the same node {entry_protected}"
            )

        exit_approach_nodes = self.signal_approach_nodes(exit_signal_id)
        if not exit_approach_nodes:
            issues.append(
                f"Exit signal {exit_signal_id} has no rear-side approach link (node -> signal)"
            )

        protected_nodes = {node for node in (entry_protected, exit_protected) if node}
        for protected in sorted(protected_nodes):
            signals = [
                signal
                for signal in self.signals.values()
                if signal.protects.strip() == protected
            ]
            by_direction: dict[SignalDirection, list[str]] = defaultdict(list)
            for signal in signals:
                by_direction[signal.direction].append(signal.id)
            for direction, signal_ids in sorted(
                by_direction.items(), key=lambda item: item[0].value
            ):
                if len(signal_ids) > 1:
                    joined = ", ".join(sorted(signal_ids))
                    issues.append(
                        f"Protected node {protected} is assigned to multiple {direction.value} signals: {joined}"
                    )
        return issues

    def export_to_json(
        self,
        path: str | Path,
        *,
        include_runtime_state: bool = False,
        include_occupancy: bool = True,
    ) -> None:
        """Serialize layout to JSON with optional runtime state."""
        payload: Dict[str, Any] = {
            "sections": [],
            "points": [],
            "signals": [],
            "edges": [],
            "signal_links": [],
            "clearance_conflict_groups": [],
            "ui_positions": {},
        }

        for node_id in self.graph.nodes:
            element = self.graph.nodes[node_id]["element"]
            if isinstance(element, TrackSection):
                payload["sections"].append(
                    {
                        "id": element.id,
                        "kind": "approach" if isinstance(element, ApproachSection) else "track",
                        "occupied": element.occupied if include_occupancy else False,
                        "locked_by": element.locked_by if include_runtime_state else None,
                        "length": element.length,
                    }
                )
            elif isinstance(element, Point):
                payload["points"].append(
                    {
                        "id": element.id,
                        "position": element.position.value,
                        "symbol_orientation": element.symbol_orientation.value,
                        "locked_by": element.locked_by if include_runtime_state else None,
                        "facing_connections": {
                            key.value: value for key, value in element.facing_connections.items()
                        },
                    }
                )

        for signal in self.signals.values():
            payload["signals"].append(
                {
                    "id": signal.id,
                    "aspect": (
                        signal.aspect.value
                        if include_runtime_state
                        else SignalAspect.STOP.value
                    ),
                    "direction": signal.direction.value,
                    "protects": signal.protects,
                    "approach_section": signal.approach_section,
                    "route_id": signal.route_id if include_runtime_state else None,
                }
            )

        payload["edges"] = [
            [src, dst] for src, dst in self.graph.edges if (src, dst) not in self._signal_virtual_edges
        ]
        payload["signal_links"] = [
            [src, dst]
            for src, dst in sorted(self.signal_links)
            if src in self.graph.nodes and dst in self.signals
        ]
        payload["clearance_conflict_groups"] = [
            sorted(group)
            for group in sorted(
                (set(group) for group in self.clearance_conflict_groups if len(group) >= 2),
                key=lambda item: tuple(sorted(item)),
            )
        ]
        payload["ui_positions"] = {
            key: [float(value[0]), float(value[1])] for key, value in self.ui_positions.items()
        }

        path_obj = Path(path)
        path_obj.parent.mkdir(parents=True, exist_ok=True)
        path_obj.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    @classmethod
    def load_from_json(
        cls,
        path: str | Path,
        *,
        load_runtime_state: bool = False,
        load_occupancy: bool = True,
    ) -> "RailwayTopology":
        """Load topology from JSON with optional runtime-state restoration."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        topology = cls()

        positions = data.get("ui_positions", {})

        for section_data in data.get("sections", []):
            section_kind = str(section_data.get("kind", "track")).strip().lower()
            section_cls = ApproachSection if section_kind == "approach" else TrackSection
            section = section_cls(
                id=section_data["id"],
                occupied=(
                    bool(section_data.get("occupied", False))
                    if load_occupancy
                    else False
                ),
                locked_by=(
                    section_data.get("locked_by")
                    if load_runtime_state
                    else None
                ),
                length=float(section_data.get("length", 100.0)),
            )
            section_pos = positions.get(section.id)
            topology.add_section(
                section,
                position=(float(section_pos[0]), float(section_pos[1])) if section_pos else None,
            )

        for point_data in data.get("points", []):
            facing = point_data.get("facing_connections", {})
            raw_orientation = str(
                point_data.get("symbol_orientation", PointSymbolOrientation.RIGHT.value)
            ).strip().upper()
            try:
                symbol_orientation = PointSymbolOrientation(raw_orientation)
            except ValueError:
                symbol_orientation = PointSymbolOrientation.RIGHT
            point = Point(
                id=point_data["id"],
                position=PointPosition(point_data.get("position", PointPosition.NORMAL.value)),
                symbol_orientation=symbol_orientation,
                locked_by=point_data.get("locked_by") if load_runtime_state else None,
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
            raw_direction = str(
                signal_data.get("direction", SignalDirection.RIGHT.value)
            ).strip().upper()
            if raw_direction == "UP":
                raw_direction = SignalDirection.RIGHT.value
            elif raw_direction == "DOWN":
                raw_direction = SignalDirection.LEFT.value
            try:
                direction = SignalDirection(raw_direction)
            except ValueError:
                direction = SignalDirection.RIGHT
            signal = Signal(
                id=signal_data["id"],
                aspect=(
                    SignalAspect(signal_data.get("aspect", SignalAspect.STOP.value))
                    if load_runtime_state
                    else SignalAspect.STOP
                ),
                direction=direction,
                protects=signal_data.get("protects", ""),
                approach_section=str(signal_data.get("approach_section", "")).strip(),
                route_id=signal_data.get("route_id") if load_runtime_state else None,
            )
            signal_pos = positions.get(signal.id)
            topology.add_signal(
                signal,
                position=(float(signal_pos[0]), float(signal_pos[1])) if signal_pos else None,
            )

        for source_id, target_id in data.get("edges", []):
            if source_id in topology.graph.nodes and target_id in topology.graph.nodes:
                topology.graph.add_edge(source_id, target_id)

        legacy_signal_to_protected: dict[str, str] = {}
        raw_signal_links = data.get("signal_links", [])
        if isinstance(raw_signal_links, list):
            for link in raw_signal_links:
                if not isinstance(link, list | tuple) or len(link) != 2:
                    continue
                source_id, target_id = str(link[0]), str(link[1])
                if topology.get_element(source_id) is None or topology.get_element(target_id) is None:
                    continue
                if source_id in topology.graph.nodes and target_id in topology.signals:
                    topology.signal_links.add((source_id, target_id))
                elif source_id in topology.signals and target_id in topology.graph.nodes:
                    legacy_signal_to_protected[source_id] = target_id

        # Backward compatibility for files that encoded protects via signal_links.
        for signal in topology.signals.values():
            if not signal.protects and signal.id in legacy_signal_to_protected:
                signal.protects = legacy_signal_to_protected[signal.id]
            if signal.approach_section:
                approach_element = topology.get_element(signal.approach_section)
                if not isinstance(approach_element, ApproachSection):
                    signal.approach_section = ""

        raw_clearance_groups = data.get("clearance_conflict_groups", [])
        if isinstance(raw_clearance_groups, list):
            known_nodes = set(topology.graph.nodes).union(topology.signals.keys())
            for raw_group in raw_clearance_groups:
                if not isinstance(raw_group, list | tuple):
                    continue
                group = {str(node_id).strip() for node_id in raw_group if str(node_id).strip()}
                group = {node_id for node_id in group if node_id in known_nodes}
                topology.add_clearance_conflict_group(group)

        topology.sync_signal_virtual_routes()
        if not load_runtime_state:
            topology.clear_runtime_state(keep_occupancy=load_occupancy)

        return topology

