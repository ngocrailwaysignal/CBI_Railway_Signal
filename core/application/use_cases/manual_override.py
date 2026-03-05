"""Use case for manual occupancy override in Simulation workspace."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.model.elements import TrackSection
from core.runtime.simulation import Simulation


@dataclass(slots=True)
class ManualOverrideResult:
    """Result of one manual state override request."""

    section_id: str
    occupied_before: bool
    occupied_after: bool
    removed_trains: list[str] = field(default_factory=list)


class ManualOverrideUseCase:
    """Apply manual section occupancy and reconcile runtime state."""

    def execute_set_section_occupied(
        self,
        *,
        simulation: Simulation | None,
        section_id: str,
        occupied: bool,
    ) -> ManualOverrideResult:
        if simulation is None:
            raise RuntimeError("Simulation is required for manual runtime override")
        section = simulation.topology.get_element(section_id)
        if not isinstance(section, TrackSection):
            raise KeyError(f"Unknown section {section_id}")

        occupied_before = bool(section.occupied)
        section.occupied = bool(occupied)
        removed_trains: list[str] = []
        # Reconcile whenever final state is FREE to handle cases where
        # occupancy was already changed externally before this use-case runs.
        if not section.occupied:
            removed_trains = simulation.reconcile_manual_free_section(section_id)
        return ManualOverrideResult(
            section_id=section_id,
            occupied_before=occupied_before,
            occupied_after=bool(section.occupied),
            removed_trains=removed_trains,
        )


