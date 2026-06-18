"""Runtime fail-safe monitor."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from typing import TYPE_CHECKING

from core.domain.model.elements import Point, PointPosition, SignalAspect, TrackSection
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from kernel.structured_error import StructuredError, structured_error

if TYPE_CHECKING:
    from core.domain.model.route import Route


class SafetyMonitor:
    """Evaluates and enforces runtime fail-safe conditions."""

    @staticmethod
    def detect_unsafe_conditions(
        topology: RailwayTopology,
        trains: Iterable[Train],
        active_routes: dict[str, Route] | None = None,
    ) -> list[StructuredError]:
        issues: list[StructuredError] = []
        train_list = list(trains)

        section_counter: Counter[str] = Counter()
        for train in train_list:
            section_counter[train.current_section] += 1
            current = topology.get_element(train.current_section)
            if isinstance(current, TrackSection) and not current.occupied:
                issues.append(
                    structured_error(
                        "safety.error.train_section_not_occupied",
                        train_id=train.id,
                        section_id=train.current_section,
                    )
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
                issues.append(
                    structured_error(
                        "safety.error.collision_risk",
                        count=count,
                        section_id=section_id,
                    )
                )

        for signal in topology.signals.values():
            if signal.is_blocking and signal.aspect != SignalAspect.RED:
                issues.append(
                    structured_error(
                        "safety.error.blocking_signal_not_red",
                        signal_id=signal.id,
                    )
                )
            if signal.aspect != SignalAspect.RED and not signal.route_id:
                issues.append(
                    structured_error(
                        "safety.error.signal_without_locked_route",
                        signal_id=signal.id,
                        aspect=signal.aspect.value,
                    )
                )

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
                issues.append(
                    structured_error(
                        "safety.error.locked_point_invalid_position",
                        point_id=element.id,
                    )
                )

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
