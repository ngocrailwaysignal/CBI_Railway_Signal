"""Runtime occupancy reconciliation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.domain.model.elements import TrackSection
from core.domain.model.topology import RailwayTopology

if TYPE_CHECKING:
    from core.domain.model.train import Train


class OccupancyReconciler:
    """Reconcile train registry with manual occupancy overrides."""

    @staticmethod
    def reconcile_manual_free_section(
        *,
        topology: RailwayTopology,
        trains: dict[str, "Train"],
        section_id: str,
    ) -> list[str]:
        section = topology.get_element(section_id)
        if not isinstance(section, TrackSection) or section.occupied:
            return []

        removed: list[str] = []
        for train_id, train in list(trains.items()):
            if train.current_section != section_id:
                continue
            train.route_id = None
            trains.pop(train_id, None)
            removed.append(train_id)
        return removed
