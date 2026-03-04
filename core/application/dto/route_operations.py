"""DTOs for route/simulation use-case responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.domain.model.route import Route
    from core.runtime.simulation import Simulation
    from core.domain.model.train import Train


@dataclass(slots=True)
class SetRouteResult:
    simulation: "Simulation"
    route: "Route"
    created: bool


@dataclass(slots=True)
class CancelRoutesResult:
    attempted_routes: int = 0
    cancelled_routes: int = 0
    failures: list[str] = field(default_factory=list)

    @property
    def has_failures(self) -> bool:
        return bool(self.failures)


@dataclass(slots=True)
class StartSimulationResult:
    simulation: "Simulation"
    route: "Route"
    train: "Train"
    created_route: bool
    created_train: bool
    simulation_start_section: str
    visual_route_path: list[str]
    suggested_ticks: int


