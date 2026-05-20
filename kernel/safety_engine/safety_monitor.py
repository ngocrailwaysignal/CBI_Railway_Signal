"""Runtime fail-safe monitor."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from core.domain.model.elements import Point, PointPosition, SignalAspect, TrackSection
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train


class SafetyMonitor:
    """Evaluates and enforces runtime fail-safe conditions."""

    @staticmethod
    def detect_unsafe_conditions(
        topology: RailwayTopology,
        trains: Iterable[Train],
    ) -> list[str]:
        issues: list[str] = []

        section_counter: Counter[str] = Counter()
        for train in trains:
            section_counter[train.current_section] += 1
            current = topology.get_element(train.current_section)
            if isinstance(current, TrackSection) and not current.occupied:
                issues.append(
                    f"Train {train.id} reports section {train.current_section} "
                    "but section not occupied"
                )

        for section_id, count in section_counter.items():
            if count > 1:
                issues.append(f"Collision risk: {count} trains on {section_id}")

        for signal in topology.signals.values():
            if signal.aspect == SignalAspect.PROCEED and not signal.route_id:
                issues.append(f"Signal {signal.id} is PROCEED without a locked route")

        for node_id in topology.graph.nodes:
            element = topology.graph.nodes[node_id]["element"]
            if (
                isinstance(element, Point)
                and element.locked_by
                and element.position
                not in (
                    PointPosition.NORMAL,
                    PointPosition.REVERSE,
                )
            ):
                issues.append(f"Point {element.id} has invalid position while locked")

        return issues

    @staticmethod
    def enforce_fail_safe_stop(topology: RailwayTopology) -> None:
        for signal in topology.signals.values():
            signal.aspect = SignalAspect.STOP
            signal.route_id = None
