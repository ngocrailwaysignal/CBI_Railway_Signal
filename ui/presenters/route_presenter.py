"""Formatting helpers for route-related UI output."""

from __future__ import annotations

from core.domain.model.elements import PointPosition
from core.domain.model.route import Route


class RoutePresenter:
    """Formats route/interlocking details for logs and labels."""

    @staticmethod
    def format_point_locks(required_points: dict[str, PointPosition]) -> str:
        if not required_points:
            return "-"
        return ", ".join(
            f"{point_id}:{position.value}"
            for point_id, position in sorted(required_points.items())
        )

    @classmethod
    def build_route_search_log(cls, route: Route, search_order: list[str]) -> str:
        point_locks = cls.format_point_locks(route.all_required_point_positions)
        return "\n".join(
            [
                f"Route id: {route.id}",
                f"Entry signal: {route.entry_signal_id}",
                f"Exit signal: {route.exit_signal_id}",
                f"Approach section: {route.approach_locking_section or '-'}",
                f"Search order: {' -> '.join(search_order)}",
                f"Route path: {' -> '.join(route.path)}",
                f"Overlap: {' -> '.join(route.overlap_path) if route.overlap_path else '-'}",
                f"Required points: {point_locks}",
            ]
        )


