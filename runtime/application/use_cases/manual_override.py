"""Use case for manual occupancy override inside the runtime session."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.model.elements import TrackSection
from runtime.application.runtime_session_port import RuntimeSessionPort


@dataclass(slots=True)
class SimulationManualOverrideResult:
    """Result of one manual simulation state override request."""

    section_id: str
    occupied_before: bool
    occupied_after: bool
    removed_trains: list[str] = field(default_factory=list)


class SimulationManualOverrideUseCase:
    """Apply one manual occupancy override inside the runtime session."""

    def execute_set_section_occupied(
        self,
        *,
        simulation: RuntimeSessionPort | None,
        section_id: str,
        occupied: bool,
    ) -> SimulationManualOverrideResult:
        if simulation is None:
            raise RuntimeError("Runtime session is required for manual runtime override")
        section = simulation.topology.get_element(section_id)
        if not isinstance(section, TrackSection):
            raise KeyError(f"Unknown section {section_id}")

        occupied_before = bool(section.occupied)
        command_result = simulation.set_section_occupied(
            section_id=section_id,
            occupied=bool(occupied),
        )
        removed_trains = (
            list(command_result.get("removed_trains", []))
            if isinstance(command_result, dict)
            else []
        )
        return SimulationManualOverrideResult(
            section_id=section_id,
            occupied_before=occupied_before,
            occupied_after=bool(section.occupied),
            removed_trains=removed_trains,
        )


# Backward-compatible aliases while callers migrate to simulation-focused naming.
ManualOverrideResult = SimulationManualOverrideResult
ManualOverrideUseCase = SimulationManualOverrideUseCase
