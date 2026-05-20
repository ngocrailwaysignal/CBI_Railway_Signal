"""Serialization helpers for the webclient runtime-state feed."""

from __future__ import annotations

import time
from typing import Any

from core.compiler.interlocking_table import InterlockingTableGenerator
from core.domain.model.topology import RailwayTopology
from runtime.application.mode_policy.policy import AppMode

from .layout_payload_serializer import build_layout_payload, build_topology_revision
from .runtime_snapshot_serializer import build_runtime_snapshot


def build_webclient_runtime_state(
    *,
    topology: RailwayTopology,
    workspace_mode: AppMode | str,
    runtime_snapshot: dict[str, Any] | None = None,
    generated_at: float | None = None,
) -> dict[str, Any]:
    """Build one webclient-friendly runtime payload from layout + runtime snapshot."""
    snapshot = (
        dict(runtime_snapshot)
        if isinstance(runtime_snapshot, dict)
        else build_runtime_snapshot(None)
    )
    payload = dict(snapshot)
    payload["layout"] = build_layout_payload(topology)
    payload["interlocking_rows"] = _build_interlocking_rows(topology)
    payload["workspace_mode"] = _workspace_mode_token(workspace_mode)
    payload["generated_at"] = float(time.time() if generated_at is None else generated_at)
    if not payload.get("topology_revision"):
        payload["topology_revision"] = build_topology_revision(topology)
    return payload


def _build_interlocking_rows(topology: RailwayTopology) -> list[dict[str, Any]]:
    signal_ids = sorted(str(signal_id) for signal_id in topology.signals)
    if len(signal_ids) < 2:
        return []
    try:
        rows = InterlockingTableGenerator(topology, overlap_length=0).generate(
            entry_signal_ids=signal_ids,
            exit_signal_ids=signal_ids,
        )
    except Exception:
        return []
    rows.sort(key=lambda item: item.route_name)
    return [
        {
            "route_name": row.route_name,
            "entry_signal": row.entry_signal,
            "exit_signal": row.exit_signal,
            "locked_sections": list(row.locked_sections),
            "required_points": {
                point_id: str(getattr(position, "value", position))
                for point_id, position in row.required_point_positions.items()
            },
            "conflicting_routes": list(row.conflicting_routes),
        }
        for row in rows
    ]


def _workspace_mode_token(workspace_mode: AppMode | str) -> str:
    if isinstance(workspace_mode, AppMode):
        return workspace_mode.value
    token = str(workspace_mode).strip().lower()
    return token or AppMode.DESIGN_LAYOUT.value
