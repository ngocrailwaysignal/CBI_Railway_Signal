"""Runtime fail-safe monitor."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

from core.domain.model.elements import Point, PointPosition, SignalAspect, TrackSection
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train

if TYPE_CHECKING:
    from core.domain.model.route import Route


class SafetyMonitor:
    """Evaluates and enforces runtime fail-safe conditions."""

    @staticmethod
    def detect_unsafe_conditions(
        topology: RailwayTopology,
        trains: Iterable[Train],
        active_routes: dict[str, Route] | None = None,
    ) -> list[str]:
        issues: list[str] = []
        train_list = list(trains)

        section_counter: Counter[str] = Counter()
        for train in train_list:
            section_counter[train.current_section] += 1
            current = topology.get_element(train.current_section)
            if isinstance(current, TrackSection) and not current.occupied:
                issues.append(
                    f"Train {train.id} reports section {train.current_section} "
                    "but section not occupied"
                )

        for section_id, count in section_counter.items():
            if count > 1:
                section_trains = [
                    train for train in train_list if train.current_section == section_id
                ]
                if SafetyMonitor._is_allowed_calling_on_shared_section(
                    section_id,
                    section_trains,
                    active_routes or {},
                ):
                    continue
                issues.append(f"Collision risk: {count} trains on {section_id}")

        for signal in topology.signals.values():
            if signal.is_blocking and signal.aspect != SignalAspect.RED:
                issues.append(f"Blocking signal {signal.id} must remain RED")
            if signal.aspect != SignalAspect.RED and not signal.route_id:
                issues.append(f"Signal {signal.id} is {signal.aspect.value} without a locked route")

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
    def _is_allowed_calling_on_shared_section(
        section_id: str,
        trains: list[Train],
        active_routes: dict[str, Route],
    ) -> bool:
        if not trains:
            return False
        has_calling_on_train = False
        has_active_calling_on_train = False
        has_unauthorized_idle_train = False
        for train in trains:
            route_id = str(train.route_id or "").strip()
            if not route_id:
                if section_id in train.calling_on_shared_sections:
                    has_calling_on_train = True
                    continue
                has_unauthorized_idle_train = True
                continue
            route = active_routes.get(route_id)
            if route is None:
                if section_id in train.calling_on_shared_sections:
                    has_calling_on_train = True
                    continue
                return False
            if not route.is_calling_on or section_id not in route.full_path:
                return False
            has_calling_on_train = True
            has_active_calling_on_train = True
        return has_calling_on_train and (
            has_active_calling_on_train or not has_unauthorized_idle_train
        )

    @staticmethod
    def enforce_fail_safe_stop(topology: RailwayTopology) -> None:
        for signal in topology.signals.values():
            signal.aspect = SignalAspect.RED
            signal.route_id = None
