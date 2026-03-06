"""Time-stepped simulation driver."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from core.domain.model.elements import Point, PointPosition, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from core.domain.model.train import Train
from core.runtime.locking_engine import LockingEngine
from core.runtime.occupancy_reconciler import OccupancyReconciler
from core.runtime.route_dispatcher import RouteDispatcher
from core.runtime.route_engine import RouteEngine
from core.runtime.safety_monitor import SafetyMonitor


@dataclass
class Simulation:
    """Coordinates route setup, train movement, logging, and safety supervision."""

    topology: RailwayTopology
    route_engine: RouteEngine = field(init=False)
    locking_engine: LockingEngine = field(init=False)
    route_dispatcher: RouteDispatcher = field(init=False)
    occupancy_reconciler: OccupancyReconciler = field(init=False)
    safety_monitor: SafetyMonitor = field(init=False)
    trains: dict[str, Train] = field(default_factory=dict)
    tick: int = 0

    def __post_init__(self) -> None:
        self.route_engine = RouteEngine(self.topology)
        self.locking_engine = LockingEngine(self.topology)
        self.route_dispatcher = RouteDispatcher(self.route_engine, self.locking_engine)
        self.occupancy_reconciler = OccupancyReconciler()
        self.safety_monitor = SafetyMonitor()

    def apply_runtime_command(self, op: str, payload: dict[str, Any] | None = None) -> Any:
        """Single runtime command gateway for external/manual integrations."""
        command = str(op).strip().lower()
        body = dict(payload or {})

        if command == "set_route":
            return self.set_route(
                entry_signal_id=str(body.get("entry_signal_id", "")).strip(),
                exit_signal_id=str(body.get("exit_signal_id", "")).strip(),
                overlap_length=int(body.get("overlap_length", 0)),
            )
        if command == "cancel_route":
            self.cancel_route(self._optional_token(body.get("route_id")) or "")
            return None
        if command == "set_section_occupied":
            return self.set_section_occupied(
                section_id=str(body.get("section_id", "")).strip(),
                occupied=bool(body.get("occupied", False)),
                route_id_hint=self._optional_token(body.get("route_id_hint")),
            )
        if command == "set_point_position":
            self.set_point_position(
                point_id=str(body.get("point_id", "")).strip(),
                position=body.get("position", PointPosition.NORMAL.value),
            )
            return None
        if command == "upsert_train":
            return self.upsert_train(
                train_id=str(body.get("train_id", "")).strip(),
                current_section=str(body.get("current_section", "")).strip(),
                route_id=self._optional_token(body.get("route_id")),
                speed=float(body.get("speed", 0.0)),
            )
        if command == "remove_train":
            return self.remove_train(str(body.get("train_id", "")).strip())
        if command == "hydrate_snapshot":
            self.hydrate_snapshot(
                snapshot=body.get("snapshot", {}),
                strict_route_ids=bool(body.get("strict_route_ids", True)),
            )
            return None
        raise ValueError(f"Unsupported runtime command: {op}")

    def set_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int = 0,
    ) -> Route:
        """Compute and lock a route."""
        return self.route_dispatcher.set_route(
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
        )

    def cancel_route(self, route_id: str) -> None:
        """Cancel one active route."""
        self.route_dispatcher.cancel_route(route_id)
        self.route_dispatcher.update_time_locking()

    def set_section_occupied(
        self,
        section_id: str,
        occupied: bool,
        *,
        route_id_hint: str | None = None,
    ) -> dict[str, Any]:
        """Apply one occupancy mutation through locking engine and reconcile trains."""
        resolved_route_id = self.locking_engine.set_section_occupied(
            section_id,
            occupied=occupied,
            route_id_hint=route_id_hint,
        )
        removed_trains: list[str] = []
        if not bool(occupied):
            removed_trains = self.reconcile_manual_free_section(section_id)
        return {
            "route_id": resolved_route_id,
            "removed_trains": removed_trains,
        }

    def set_point_position(self, point_id: str, position: PointPosition | str) -> None:
        """Apply one point movement via locking engine."""
        if isinstance(position, PointPosition):
            target = position
        else:
            target = PointPosition(str(position).strip().upper())
        self.locking_engine.set_point_position(point_id, target)

    def add_train(self, train: Train, route: Route) -> None:
        """Add a train and place it on its route start."""
        if train.id in self.trains:
            raise ValueError(f"Train {train.id} already exists")
        train.assign_route(route, self.topology, self.locking_engine)
        self.trains[train.id] = train

    def upsert_train(
        self,
        *,
        train_id: str,
        current_section: str,
        route_id: str | None = None,
        speed: float = 0.0,
    ) -> Train:
        """Create/update one train while enforcing runtime mutations via engine."""
        normalized_train_id = str(train_id).strip()
        if not normalized_train_id:
            raise ValueError("Train id is required")
        normalized_section = str(current_section).strip()
        if not normalized_section:
            raise ValueError("current_section is required")
        section = self.topology.get_element(normalized_section)
        if not isinstance(section, TrackSection):
            raise KeyError(f"Unknown section {normalized_section}")
        normalized_speed = max(0.0, float(speed))
        normalized_route_id = str(route_id or "").strip() or None

        train = self.trains.get(normalized_train_id)
        if normalized_route_id:
            route = self.locking_engine.active_routes.get(normalized_route_id)
            if route is None:
                raise RuntimeError(f"Route {normalized_route_id} is not active")
            if train is None:
                train = Train(
                    id=normalized_train_id,
                    current_section=normalized_section,
                    speed=normalized_speed,
                )
                self.add_train(train, route)
                return train

            if (
                train.route_id == normalized_route_id
                and train.current_section == normalized_section
            ):
                train.speed = normalized_speed
                return train

            if train.route_id == normalized_route_id:
                train.relocate_on_route(
                    route,
                    self.topology,
                    self.locking_engine,
                    new_section=normalized_section,
                    speed=normalized_speed,
                )
                return train

            self._vacate_train_current_section(train)
            train.current_section = normalized_section
            train.speed = normalized_speed
            train.assign_route(route, self.topology, self.locking_engine)
            return train

        if train is None:
            train = Train(
                id=normalized_train_id,
                current_section=normalized_section,
                speed=normalized_speed,
                route_id=None,
            )
            self.trains[normalized_train_id] = train
        else:
            if train.current_section != normalized_section or train.route_id:
                self._vacate_train_current_section(train)
            train.current_section = normalized_section
            train.speed = normalized_speed
            train.route_id = None

        self.locking_engine.set_section_occupied(normalized_section, True)
        return train

    def remove_train(self, train_id: str) -> bool:
        """Remove one train and vacate its section occupancy."""
        normalized_train_id = str(train_id).strip()
        train = self.trains.pop(normalized_train_id, None)
        if train is None:
            return False
        self._vacate_train_current_section(train)
        train.route_id = None
        return True

    def hydrate_snapshot(
        self,
        *,
        snapshot: dict[str, Any],
        strict_route_ids: bool = True,
    ) -> None:
        """Reset runtime state and replay one runtime snapshot through engine commands."""
        if not isinstance(snapshot, dict):
            raise ValueError("runtime snapshot payload must be an object")

        self.locking_engine.reset_runtime_state(keep_occupancy=False)
        self.trains.clear()
        try:
            self.tick = max(0, int(snapshot.get("tick", 0)))
        except (TypeError, ValueError):
            self.tick = 0

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
            route = self.set_route(
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
                    point = self.topology.get_element(node_id)
                    if not isinstance(point, Point):
                        raise RuntimeError(f"Unknown point {node_id}")
                    incoming_position = PointPosition(raw_position)
                    if point.position != incoming_position:
                        self.set_point_position(node_id, incoming_position)
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
            self.upsert_train(
                train_id=train_id,
                current_section=current_section,
                route_id=actual_route_id,
                speed=float(train_item.get("speed", 0.0)),
            )

        for train_id in list(self.trains.keys()):
            if train_id in expected_train_ids:
                continue
            self.remove_train(train_id)

        for section_id, occupied in sorted(desired_occupancy.items(), key=lambda item: item[1]):
            route_hint = section_route_hints.get(section_id)
            self.locking_engine.set_section_occupied(
                section_id,
                occupied,
                route_id_hint=route_hint,
            )

        self._assert_snapshot_consistent(
            snapshot=snapshot,
            route_id_map=incoming_to_actual_route_id,
        )

    def reconcile_manual_free_section(self, section_id: str) -> list[str]:
        """Remove trains that still claim a section manually forced to FREE."""
        return self.occupancy_reconciler.reconcile_manual_free_section(
            topology=self.topology,
            trains=self.trains,
            section_id=section_id,
        )

    def step(self) -> None:
        """Advance the simulation by one tick."""
        self.tick += 1
        self.route_dispatcher.update_time_locking()
        for train in list(self.trains.values()):
            if not train.route_id:
                continue
            route = self.locking_engine.active_routes.get(train.route_id)
            if route is None:
                train.route_id = None
                continue
            train.step(route, self.topology, self.locking_engine)

        issues = self.safety_monitor.detect_unsafe_conditions(self.topology, self.trains.values())
        if issues:
            self.locking_engine.force_all_signals_stop()
            issue_text = "; ".join(issues)
            raise RuntimeError(f"Fail-safe STOP triggered: {issue_text}")

        self.log_state()

    def run(self, steps: int) -> None:
        """Run N ticks."""
        for _ in range(max(0, steps)):
            self.step()

    def log_state(self) -> None:
        """Emit concise state logs."""
        signal_state = ", ".join(
            f"{s.id}:{s.aspect.value}(route={s.route_id})" for s in self.topology.signals.values()
        )
        section_state: list[str] = []
        for node_id in self.topology.graph.nodes:
            element = self.topology.graph.nodes[node_id]["element"]
            if hasattr(element, "occupied"):
                section_state.append(
                    f"{element.id}(occ={element.occupied},lock={element.locked_by})"
                )
        train_state = ", ".join(f"{t.id}@{t.current_section}" for t in self.trains.values())
        print(
            f"[tick={self.tick}] signals[{signal_state}] tracks[{'; '.join(section_state)}] "
            f"trains[{train_state}]"
        )

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

    def _vacate_train_current_section(self, train: Train) -> None:
        section_id = str(getattr(train, "current_section", "")).strip()
        if not section_id:
            return
        try:
            self.locking_engine.set_section_occupied(
                section_id,
                False,
                route_id_hint=str(getattr(train, "route_id", "")).strip() or None,
            )
        except KeyError:
            return

    def _assert_snapshot_consistent(
        self,
        *,
        snapshot: dict[str, Any],
        route_id_map: dict[str, str],
    ) -> None:
        for route_item in snapshot.get("routes", []):
            if not isinstance(route_item, dict):
                continue
            incoming_route_id = str(route_item.get("id", "")).strip()
            actual_route_id = route_id_map.get(incoming_route_id, incoming_route_id)
            route = self.locking_engine.active_routes.get(actual_route_id)
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
            element = self.topology.get_element(node_id)
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
            train = self.trains.get(train_id)
            if train is None:
                raise RuntimeError(f"Missing train after hydrate: {train_id}")
            expected_section = str(train_item.get("current_section", "")).strip()
            if expected_section != train.current_section:
                raise RuntimeError(f"Train section mismatch after hydrate: {train_id}")
            incoming_route_id = self._optional_token(train_item.get("route_id"))
            expected_route_id = route_id_map.get(incoming_route_id or "", incoming_route_id) if incoming_route_id else None
            if expected_route_id != train.route_id:
                raise RuntimeError(f"Train route mismatch after hydrate: {train_id}")

        for signal_item in snapshot.get("signal_state", []):
            if not isinstance(signal_item, dict):
                continue
            signal_id = str(signal_item.get("id", "")).strip()
            signal = self.topology.signals.get(signal_id)
            if signal is None:
                raise RuntimeError(f"Unknown signal in snapshot validation: {signal_id}")
            incoming_aspect = str(signal_item.get("aspect", "")).strip().upper()
            if incoming_aspect and signal.aspect.value != incoming_aspect:
                raise RuntimeError(f"Signal aspect mismatch after hydrate: {signal_id}")
            incoming_route_id = self._optional_token(signal_item.get("route_id"))
            expected_route_id = route_id_map.get(incoming_route_id or "", incoming_route_id) if incoming_route_id else None
            if signal.route_id != expected_route_id:
                raise RuntimeError(f"Signal route mismatch after hydrate: {signal_id}")
