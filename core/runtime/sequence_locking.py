"""Sequence-locking state tracker for sectional release safety."""

from __future__ import annotations

from dataclasses import dataclass, field

from core.domain.model.elements import ApproachSection, TrackSection
from core.domain.model.topology import RailwayTopology


@dataclass(slots=True)
class SequenceLockingTracker:
    """Tracks occupied evidence and enforces in-order sectional release."""

    topology: RailwayTopology
    route_track_sections: dict[str, list[str]] = field(default_factory=dict)
    seen_occupied_sections: dict[str, set[str]] = field(default_factory=dict)

    def clear_all(self) -> None:
        self.route_track_sections.clear()
        self.seen_occupied_sections.clear()

    def initialize_route(self, route_id: str, route_path: list[str]) -> None:
        track_sections = [
            node_id
            for node_id in route_path
            if self.is_sequence_track_section(self.topology.get_element(node_id))
        ]
        self.route_track_sections[route_id] = track_sections
        self.seen_occupied_sections[route_id] = set()

    def clear_route(self, route_id: str) -> None:
        self.route_track_sections.pop(route_id, None)
        self.seen_occupied_sections.pop(route_id, None)

    def mark_section_occupied(self, route_id: str, node_id: str) -> None:
        track_sections = self.route_track_sections.get(route_id)
        if not track_sections or node_id not in track_sections:
            return
        self.seen_occupied_sections.setdefault(route_id, set()).add(node_id)

    def try_section_release(self, route_id: str, section_id: str) -> bool:
        section = self.topology.get_element(section_id)
        if not self.is_sequence_track_section(section):
            return False
        if section.locked_by != route_id or section.occupied:
            return False

        track_sections = self.route_track_sections.get(route_id, [])
        if not track_sections:
            section.locked_by = None
            return True
        if section_id not in track_sections:
            section.locked_by = None
            return True

        seen_occupied = self.seen_occupied_sections.setdefault(route_id, set())
        section_index = track_sections.index(section_id)

        if len(track_sections) == 1:
            if section_id not in seen_occupied:
                raise RuntimeError(
                    f"Sequence locking violation on {section_id}: "
                    "section has no prior occupied evidence"
                )
            section.locked_by = None
            return True

        if section_index == len(track_sections) - 1:
            return False

        if section_id not in seen_occupied:
            raise RuntimeError(
                f"Sequence locking violation on {section_id}: "
                "section occupancy was never confirmed"
            )

        next_section_id = track_sections[section_index + 1]
        if next_section_id not in seen_occupied:
            raise RuntimeError(
                f"Sequence locking violation on {section_id}: "
                f"next section {next_section_id} has not been confirmed occupied"
            )

        if section_index > 0:
            previous_section_id = track_sections[section_index - 1]
            previous = self.topology.get_element(previous_section_id)
            if self.is_sequence_track_section(previous) and previous.locked_by == route_id:
                raise RuntimeError(
                    f"Sequence locking violation on {section_id}: "
                    f"previous section {previous_section_id} is still locked"
                )

        section.locked_by = None
        return True

    @staticmethod
    def is_sequence_track_section(element: object) -> bool:
        return isinstance(element, TrackSection) and not isinstance(element, ApproachSection)

