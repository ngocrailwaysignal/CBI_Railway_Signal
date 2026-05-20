"""Domain route model."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.lifecycle import RouteLifecycleState
from core.domain.model.elements import PointPosition


@dataclass(slots=True)
class Route:
    """A computed route with required point states and overlap."""

    id: str
    entry_signal_id: str
    exit_signal_id: str
    path: list[str]
    overlap_path: list[str]
    required_point_positions: dict[str, PointPosition]
    flank_point_positions: dict[str, PointPosition] = field(default_factory=dict)
    monitored_flank_sections: list[str] = field(default_factory=list)
    approach_locking_section: str | None = None
    lifecycle_state: RouteLifecycleState = RouteLifecycleState.RESERVED

    @property
    def full_path(self) -> list[str]:
        """Route path including overlap footprint."""
        return [*self.path, *self.overlap_path]

    @property
    def all_required_point_positions(self) -> dict[str, PointPosition]:
        """All point locks required by route path and flank protection."""
        merged = dict(self.required_point_positions)
        for point_id, position in self.flank_point_positions.items():
            existing = merged.get(point_id)
            if existing is not None and existing != position:
                raise ValueError(
                    f"Point {point_id} has conflicting route/flank locks "
                    f"{existing.value}/{position.value}"
                )
            merged[point_id] = position
        return merged


__all__ = ["Route"]
