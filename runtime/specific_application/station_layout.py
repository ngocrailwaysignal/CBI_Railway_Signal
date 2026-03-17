"""Specific station layout model."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.domain.model.topology import RailwayTopology


@dataclass(slots=True)
class StationLayout:
    """One concrete station configuration (specific application)."""

    station_id: str
    topology: RailwayTopology
    source_path: Path | None = None
