"""Layout payload serialization for web/runtime interoperability."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json

from core.domain.model.topology import RailwayTopology


def build_layout_payload(topology: RailwayTopology) -> dict:
    """Serialize current topology to one web/runtime-compatible layout payload."""
    payload: dict = {
        "sections": [],
        "points": [],
        "signals": [],
        "edges": [],
        "signal_links": [],
        "clearance_conflict_groups": [],
        "ui_positions": {},
        "dispatcher_view": deepcopy(getattr(topology, "dispatcher_view", {})),
    }

    for node_id in topology.graph.nodes:
        element = topology.get_element(node_id)
        if element is None:
            continue
        if hasattr(element, "length") and hasattr(element, "occupied"):
            payload["sections"].append(
                {
                    "id": str(getattr(element, "id", node_id)),
                    "kind": (
                        "approach"
                        if element.__class__.__name__.lower() == "approachsection"
                        else "track"
                    ),
                    "occupied": bool(getattr(element, "occupied", False)),
                    "locked_by": getattr(element, "locked_by", None),
                    "length": float(getattr(element, "length", 100.0)),
                }
            )
            continue
        if hasattr(element, "position") and hasattr(element, "facing_connections"):
            facing_connections = {}
            for key, value in dict(getattr(element, "facing_connections", {})).items():
                key_token = getattr(key, "value", key)
                if value:
                    facing_connections[str(key_token)] = str(value)
            payload["points"].append(
                {
                    "id": str(getattr(element, "id", node_id)),
                    "position": str(getattr(getattr(element, "position", None), "value", "NORMAL")),
                    "symbol_orientation": str(
                        getattr(getattr(element, "symbol_orientation", None), "value", "RIGHT")
                    ),
                    "locked_by": getattr(element, "locked_by", None),
                    "facing_connections": facing_connections,
                }
            )

    for signal in topology.signals.values():
        payload["signals"].append(
            {
                "id": signal.id,
                "aspect": signal.aspect.value,
                "direction": signal.direction.value,
                "protects": signal.protects,
                "approach_section": signal.approach_section,
                "route_id": signal.route_id,
            }
        )

    virtual_edges = set(getattr(topology, "_signal_virtual_edges", set()))
    payload["edges"] = [
        [src, dst]
        for src, dst in topology.graph.edges
        if (src, dst) not in virtual_edges
    ]
    payload["signal_links"] = [
        [src, dst]
        for src, dst in sorted(topology.signal_links)
        if src in topology.graph.nodes and dst in topology.signals
    ]
    payload["clearance_conflict_groups"] = [
        sorted(group)
        for group in sorted(
            (set(group) for group in topology.clearance_conflict_groups if len(group) >= 2),
            key=lambda item: tuple(sorted(item)),
        )
    ]
    payload["ui_positions"] = {
        key: [float(value[0]), float(value[1])]
        for key, value in topology.ui_positions.items()
    }
    return payload


def build_topology_revision(topology: RailwayTopology) -> str:
    """Build one stable topology revision token from canonical layout payload."""
    payload = build_layout_payload(topology)
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

