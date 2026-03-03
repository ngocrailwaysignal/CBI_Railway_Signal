"""Editor-facing service for one specific station layout."""

from __future__ import annotations

from pathlib import Path

from core.topology import RailwayTopology
from generic_application import GenericApplicationService

from .station_layout import StationLayout


class SpecificLayoutEditorService:
    """Station editor service bound to one generic application profile."""

    def __init__(self, application_service: GenericApplicationService) -> None:
        self.application_service = application_service

    def new_layout(self, station_id: str = "UNNAMED") -> StationLayout:
        """Create a blank specific station layout."""
        return StationLayout(station_id=station_id, topology=RailwayTopology())

    def load_layout(
        self,
        path: str | Path,
        *,
        station_id: str | None = None,
        load_runtime_state: bool | None = None,
        load_occupancy: bool | None = None,
    ) -> StationLayout:
        """Load one specific station layout from disk."""
        layout_path = Path(path)
        topology = self.application_service.load_topology(
            layout_path,
            load_runtime_state=load_runtime_state,
            load_occupancy=load_occupancy,
        )
        return StationLayout(
            station_id=station_id or layout_path.stem,
            topology=topology,
            source_path=layout_path,
        )

    def save_layout(
        self,
        layout: StationLayout,
        path: str | Path | None = None,
        *,
        include_runtime_state: bool | None = None,
        include_occupancy: bool | None = None,
    ) -> Path:
        """Save one specific station layout to disk."""
        target = Path(path) if path is not None else layout.source_path
        if target is None:
            raise ValueError("Missing output path for station layout save")
        self.application_service.save_topology(
            layout.topology,
            target,
            include_runtime_state=include_runtime_state,
            include_occupancy=include_occupancy,
        )
        layout.source_path = target
        return target
