"""Internal runtime snapshot hydration/replay logic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.model.elements import Point, PointPosition, TrackSection


@dataclass(slots=True)
class RuntimeSnapshotHydrator:
    """Replays runtime snapshot artifacts through simulation commands."""

    simulation: "Simulation"

    def hydrate_snapshot(
        self,
        *,
        snapshot: dict[str, Any],
        strict_route_ids: bool = True,
    ) -> None:
        """Reset runtime state and replay one runtime snapshot through engine commands."""
        if not isinstance(snapshot, dict):
            raise ValueError("runtime snapshot payload must be an object")

        self.simulation.locking_engine.reset_runtime_state(keep_occupancy=False)
        self.simulation.trains.clear()
        try:
            self.simulation.tick = max(0, int(snapshot.get("tick", 0)))
        except (TypeError, ValueError):
            self.simulation.tick = 0

        routes = snapshot.get("routes", [])
        if not isinstance(routes, list):
            raise ValueError("runtime snapshot routes must be a list")

        incoming_to_actual_route_id: dict[str, str] = {}
        section_route_hints: dict[str, str] = {}
        for route_item in routes:
            if not isinstance(route_item, dict):
                continue
            entry_signal_id = str(route_item.get("entry_signal_id", "")).strip()
            exit_signal_id = str(route_item.get("exit_signal_id", "")).strip()
            incoming_route_id = str(route_item.get("id", "")).strip()
            if not entry_signal_id or not exit_signal_id:
                raise RuntimeError("Route snapshot item requires entry_signal_id/exit_signal_id")

            overlap_path = self._normalize_node_list(route_item.get("overlap_path"))
            expected_path = self._normalize_node_list(route_item.get("path"))
            route = self.simulation.set_route(
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                overlap_length=len(overlap_path),
            )
            if expected_path and list(route.path) != expected_path:
                raise RuntimeError(
                    f"Route path mismatch for {entry_signal_id}->{exit_signal_id}"
                )
            if overlap_path and list(route.overlap_path) != overlap_path:
                raise RuntimeError(
                    f"Route overlap mismatch for {entry_signal_id}->{exit_signal_id}"
                )
            if strict_route_ids and incoming_route_id and route.id != incoming_route_id:
                raise RuntimeError(
                    f"Route ID mismatch for {entry_signal_id}->{exit_signal_id}: "
                    f"{incoming_route_id} != {route.id}"
                )

            route_key = incoming_route_id or route.id
            incoming_to_actual_route_id[route_key] = route.id
            for section_id in route.full_path:
                existing_hint = section_route_hints.get(section_id)
                if existing_hint is None:
                    section_route_hints[section_id] = route.id
                elif existing_hint != route.id:
                    section_route_hints.pop(section_id, None)

        occupancy = snapshot.get("occupancy", [])
        if not isinstance(occupancy, list):
            raise ValueError("runtime snapshot occupancy must be a list")

        desired_occupancy: dict[str, bool] = {}
        for occupancy_item in occupancy:
            if not isinstance(occupancy_item, dict):
                continue
            node_id = str(occupancy_item.get("id", "")).strip()
            if not node_id:
                continue
            if "position" in occupancy_item:
                raw_position = str(occupancy_item.get("position", "")).strip().upper()
                if raw_position:
                    point = self.simulation.topology.get_element(node_id)
                    if not isinstance(point, Point):
                        raise RuntimeError(f"Unknown point {node_id}")
                    incoming_position = PointPosition(raw_position)
                    if point.position != incoming_position:
                        self.simulation.set_point_position(node_id, incoming_position)
            if "occupied" in occupancy_item:
                desired_occupancy[node_id] = bool(occupancy_item.get("occupied", False))

        trains = snapshot.get("trains", [])
        if not isinstance(trains, list):
            raise ValueError("runtime snapshot trains must be a list")
        expected_train_ids: set[str] = set()
        for train_item in trains:
            if not isinstance(train_item, dict):
                continue
            train_id = str(train_item.get("id", "")).strip()
            current_section = str(train_item.get("current_section", "")).strip()
            if not train_id or not current_section:
                raise RuntimeError("Train snapshot item requires id/current_section")
            expected_train_ids.add(train_id)
            incoming_route_id = self._optional_token(train_item.get("route_id"))
            actual_route_id = (
                incoming_to_actual_route_id.get(incoming_route_id or "")
                if incoming_route_id
                else None
            )
            if incoming_route_id and actual_route_id is None:
                actual_route_id = incoming_route_id
            self.simulation.upsert_train(
                train_id=train_id,
                current_section=current_section,
                route_id=actual_route_id,
                speed=float(train_item.get("speed", 0.0)),
            )

        for train_id in list(self.simulation.trains.keys()):
            if train_id in expected_train_ids:
                continue
            self.simulation.remove_train(train_id)

        for section_id, occupied in sorted(desired_occupancy.items(), key=lambda item: item[1]):
            route_hint = section_route_hints.get(section_id)
            self.simulation.locking_engine.set_section_occupied(
                section_id,
                occupied,
                route_id_hint=route_hint,
            )

        self.assert_snapshot_consistent(
            snapshot=snapshot,
            route_id_map=incoming_to_actual_route_id,
        )

    def assert_snapshot_consistent(
        self,
        *,
        snapshot: dict[str, Any],
        route_id_map: dict[str, str],
    ) -> None:
        """Validate runtime state after hydrate against snapshot payload."""
        for route_item in snapshot.get("routes", []):
            if not isinstance(route_item, dict):
                continue
            incoming_route_id = str(route_item.get("id", "")).strip()
            actual_route_id = route_id_map.get(incoming_route_id, incoming_route_id)
            route = self.simulation.locking_engine.active_routes.get(actual_route_id)
            if route is None:
                raise RuntimeError(f"Missing route after hydrate: {incoming_route_id or actual_route_id}")
            if list(route.path) != self._normalize_node_list(route_item.get("path")):
                raise RuntimeError(f"Path mismatch after hydrate for route {actual_route_id}")
            if list(route.overlap_path) != self._normalize_node_list(route_item.get("overlap_path")):
                raise RuntimeError(f"Overlap mismatch after hydrate for route {actual_route_id}")

        for occupancy_item in snapshot.get("occupancy", []):
            if not isinstance(occupancy_item, dict):
                continue
            node_id = str(occupancy_item.get("id", "")).strip()
            if not node_id:
                continue
            element = self.simulation.topology.get_element(node_id)
            if "occupied" in occupancy_item:
                if not isinstance(element, TrackSection):
                    raise RuntimeError(f"Unknown section in occupancy check: {node_id}")
                if bool(element.occupied) != bool(occupancy_item.get("occupied", False)):
                    raise RuntimeError(f"Section occupancy mismatch after hydrate: {node_id}")
            if "position" in occupancy_item:
                if not isinstance(element, Point):
                    raise RuntimeError(f"Unknown point in occupancy check: {node_id}")
                expected = str(occupancy_item.get("position", "")).strip().upper()
                if expected and element.position.value != expected:
                    raise RuntimeError(f"Point position mismatch after hydrate: {node_id}")

        for train_item in snapshot.get("trains", []):
            if not isinstance(train_item, dict):
                continue
            train_id = str(train_item.get("id", "")).strip()
            if not train_id:
                continue
            train = self.simulation.trains.get(train_id)
            if train is None:
                raise RuntimeError(f"Missing train after hydrate: {train_id}")
            expected_section = str(train_item.get("current_section", "")).strip()
            if expected_section != train.current_section:
                raise RuntimeError(f"Train section mismatch after hydrate: {train_id}")
            incoming_route_id = self._optional_token(train_item.get("route_id"))
            expected_route_id = (
                route_id_map.get(incoming_route_id or "", incoming_route_id)
                if incoming_route_id
                else None
            )
            if expected_route_id != train.route_id:
                raise RuntimeError(f"Train route mismatch after hydrate: {train_id}")

        for signal_item in snapshot.get("signal_state", []):
            if not isinstance(signal_item, dict):
                continue
            signal_id = str(signal_item.get("id", "")).strip()
            signal = self.simulation.topology.signals.get(signal_id)
            if signal is None:
                raise RuntimeError(f"Unknown signal in snapshot validation: {signal_id}")
            incoming_aspect = str(signal_item.get("aspect", "")).strip().upper()
            if incoming_aspect and signal.aspect.value != incoming_aspect:
                raise RuntimeError(f"Signal aspect mismatch after hydrate: {signal_id}")
            incoming_route_id = self._optional_token(signal_item.get("route_id"))
            expected_route_id = (
                route_id_map.get(incoming_route_id or "", incoming_route_id)
                if incoming_route_id
                else None
            )
            if signal.route_id != expected_route_id:
                raise RuntimeError(f"Signal route mismatch after hydrate: {signal_id}")

    @staticmethod
    def _normalize_node_list(raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            return []
        return [str(item).strip() for item in raw_value if str(item).strip()]

    @staticmethod
    def _optional_token(raw_value: Any) -> str | None:
        if raw_value is None:
            return None
        token = str(raw_value).strip()
        if not token or token.upper() == "NONE":
            return None
        return token


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.runtime.simulation import Simulation

