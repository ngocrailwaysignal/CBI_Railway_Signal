"""Non-visual helper functions used by canvas editor view."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QPointF

from core.domain.model.elements import TrackSection
from core.domain.model.topology import RailwayTopology


def node_scene_anchor(
    *,
    node: Any | None,
    sprite_width: float,
    sprite_height: float,
) -> QPointF | None:
    """Return top-left sprite anchor centered on a node, if node exists."""
    if node is None:
        return None
    center = node.sceneBoundingRect().center()
    return QPointF(
        center.x() - (sprite_width / 2.0),
        center.y() - (sprite_height / 2.0) - 3.0,
    )


def is_train_renderable(train: Any, *, nodes: dict[str, Any], topology: RailwayTopology) -> bool:
    """Return whether a train should have an active sprite on canvas."""
    current_section = str(getattr(train, "current_section", "")).strip()
    if not current_section or current_section not in nodes:
        return False
    section_element = topology.get_element(current_section)
    if isinstance(section_element, TrackSection):
        return bool(section_element.occupied)
    return True


def connection_pairs(
    *,
    topology: RailwayTopology,
    nodes: dict[str, Any],
    signal_links: set[tuple[str, str]],
) -> list[tuple[str, str]]:
    """Return visualized connections in deterministic order."""
    pairs: list[tuple[str, str]] = []
    for source_id, target_id in sorted(topology.graph.edges):
        if (source_id, target_id) in topology._signal_virtual_edges:
            continue
        pairs.append((source_id, target_id))

    for signal in sorted(topology.signals.values(), key=lambda item: item.id):
        protected = signal.protects.strip()
        if protected and protected in nodes:
            pairs.append((signal.id, protected))

    for source_id, target_id in sorted(signal_links):
        if source_id in nodes and target_id in nodes:
            pairs.append((source_id, target_id))
    return pairs


def resolve_connection_direction(
    *,
    topology: RailwayTopology,
    source_id: str,
    target_id: str,
) -> tuple[str, str]:
    """Resolve connection direction for one pair with signal-safe heuristics.

    When one side is a signal and the other is a track/point node:
    - If signal has no protects yet, keep Signal -> Node (set protects).
    - If signal already protects a node, prefer Node -> Signal (add approach link).
    """
    source_is_signal = source_id in topology.signals
    target_is_signal = target_id in topology.signals
    if source_is_signal == target_is_signal:
        return source_id, target_id

    signal_id = source_id if source_is_signal else target_id
    node_id = target_id if source_is_signal else source_id
    signal = topology.signals.get(signal_id)
    if signal is None:
        return source_id, target_id

    protected = signal.protects.strip()
    if not protected:
        return signal_id, node_id
    return node_id, signal_id

