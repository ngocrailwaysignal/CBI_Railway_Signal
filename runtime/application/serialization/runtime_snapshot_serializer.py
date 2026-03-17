"""Runtime snapshot serialization utilities."""

from __future__ import annotations

from runtime.application.runtime_session_port import RuntimeSessionPort
from runtime.application.serialization.layout_payload_serializer import build_topology_revision


def build_runtime_snapshot(simulation: RuntimeSessionPort | None) -> dict:
    """Serialize runtime-only state for snapshot persistence."""
    if simulation is None:
        return {
            "snapshot_version": 2,
            "stream_seq": 0,
            "topology_revision": None,
            "tick": 0,
            "routes": [],
            "trains": [],
            "occupancy": [],
            "signal_state": [],
        }

    topology = simulation.topology
    occupancy: list[dict] = []
    for node_id in topology.graph.nodes:
        element = topology.get_element(node_id)
        if element is None:
            continue
        record = {"id": node_id, "locked_by": getattr(element, "locked_by", None)}
        if hasattr(element, "occupied"):
            record["occupied"] = bool(getattr(element, "occupied", False))
        if hasattr(element, "position"):
            position = getattr(element, "position", None)
            record["position"] = getattr(position, "value", position)
        occupancy.append(record)

    routes = [
        {
            "id": route.id,
            "entry_signal_id": route.entry_signal_id,
            "exit_signal_id": route.exit_signal_id,
            "path": list(route.path),
            "overlap_path": list(route.overlap_path),
            "full_path": list(route.full_path),
            "lifecycle_state": route.lifecycle_state.value,
            "status": "ACTIVE",
        }
        for route in simulation.locking_engine.active_routes.values()
    ]
    trains = [
        {
            "id": train.id,
            "current_section": train.current_section,
            "speed": float(train.speed),
            "route_id": train.route_id,
        }
        for train in simulation.trains.values()
    ]
    signal_state = [
        {
            "id": signal.id,
            "aspect": signal.aspect.value,
            "route_id": signal.route_id,
        }
        for signal in topology.signals.values()
    ]
    return {
        "snapshot_version": 2,
        "stream_seq": 0,
        "topology_revision": build_topology_revision(topology),
        "tick": simulation.tick,
        "routes": routes,
        "trains": trains,
        "occupancy": occupancy,
        "signal_state": signal_state,
    }
