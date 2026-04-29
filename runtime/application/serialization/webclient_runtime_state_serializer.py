"""Serialization helpers for the webclient runtime-state feed."""

from __future__ import annotations

import time
from typing import Any

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
    snapshot = dict(runtime_snapshot) if isinstance(runtime_snapshot, dict) else build_runtime_snapshot(None)
    payload = dict(snapshot)
    payload["layout"] = build_layout_payload(topology)
    payload["workspace_mode"] = _workspace_mode_token(workspace_mode)
    payload["generated_at"] = float(time.time() if generated_at is None else generated_at)
    if not payload.get("topology_revision"):
        payload["topology_revision"] = build_topology_revision(topology)
    return payload


def _workspace_mode_token(workspace_mode: AppMode | str) -> str:
    if isinstance(workspace_mode, AppMode):
        return workspace_mode.value
    token = str(workspace_mode).strip().lower()
    return token or AppMode.DESIGN_LAYOUT.value
