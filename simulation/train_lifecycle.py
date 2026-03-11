"""Internal train lifecycle operations for runtime simulation."""

from __future__ import annotations

from dataclasses import dataclass

from core.domain.model.elements import TrackSection
from core.domain.model.train import Train


@dataclass(slots=True)
class RuntimeTrainLifecycle:
    """Handles train upsert/remove operations via locking-aware mutations."""

    simulation: "Simulation"

    def upsert_train(
        self,
        *,
        train_id: str,
        current_section: str,
        route_id: str | None = None,
        speed: float = 0.0,
    ) -> Train:
        normalized_train_id = str(train_id).strip()
        if not normalized_train_id:
            raise ValueError("Train id is required")
        normalized_section = str(current_section).strip()
        if not normalized_section:
            raise ValueError("current_section is required")
        section = self.simulation.topology.get_element(normalized_section)
        if not isinstance(section, TrackSection):
            raise KeyError(f"Unknown section {normalized_section}")
        normalized_speed = max(0.0, float(speed))
        normalized_route_id = str(route_id or "").strip() or None

        train = self.simulation.trains.get(normalized_train_id)
        normalized_route_id = self._resolve_route_id(
            train=train,
            requested_route_id=normalized_route_id,
            current_section=normalized_section,
        )
        if normalized_route_id:
            route = self.simulation.locking_engine.active_routes.get(normalized_route_id)
            if route is None:
                raise RuntimeError(f"Route {normalized_route_id} is not active")
            if train is None:
                train = Train(
                    id=normalized_train_id,
                    current_section=normalized_section,
                    speed=normalized_speed,
                )
                self.simulation.add_train(train, route)
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
                    self.simulation.topology,
                    self.simulation.locking_engine,
                    new_section=normalized_section,
                    speed=normalized_speed,
                )
                return train

            previous_section = str(getattr(train, "current_section", "")).strip()
            previous_route_id = str(getattr(train, "route_id", "")).strip() or None
            train.current_section = normalized_section
            train.speed = normalized_speed
            train.assign_route(route, self.simulation.topology, self.simulation.locking_engine)
            self._release_previous_section_after_reassignment(
                previous_section=previous_section,
                previous_route_id=previous_route_id,
                new_route_id=route.id,
                new_section=normalized_section,
            )
            return train

        if train is None:
            train = Train(
                id=normalized_train_id,
                current_section=normalized_section,
                speed=normalized_speed,
                route_id=None,
            )
            self.simulation.trains[normalized_train_id] = train
        else:
            if train.current_section != normalized_section or train.route_id:
                self.vacate_train_current_section(train)
            train.current_section = normalized_section
            train.speed = normalized_speed
            train.route_id = None

        self.simulation.locking_engine.set_section_occupied(normalized_section, True)
        return train

    def remove_train(self, train_id: str) -> bool:
        """Remove one train and vacate its section occupancy."""
        normalized_train_id = str(train_id).strip()
        train = self.simulation.trains.pop(normalized_train_id, None)
        if train is None:
            return False
        self.vacate_train_current_section(train)
        train.route_id = None
        return True

    def vacate_train_current_section(self, train: Train) -> None:
        """Vacate a train's current section using locking-engine semantics."""
        section_id = str(getattr(train, "current_section", "")).strip()
        if not section_id:
            return
        try:
            self.simulation.locking_engine.set_section_occupied(
                section_id,
                False,
                route_id_hint=str(getattr(train, "route_id", "")).strip() or None,
            )
        except KeyError:
            return

    def _resolve_route_id(
        self,
        *,
        train: Train | None,
        requested_route_id: str | None,
        current_section: str,
    ) -> str | None:
        active_routes = self.simulation.locking_engine.active_routes
        requested_token = str(requested_route_id or "").strip() or None
        if requested_token and requested_token in active_routes:
            return requested_token

        existing_route_id = str(getattr(train, "route_id", "")).strip() or None
        if existing_route_id and existing_route_id in active_routes:
            existing_route = active_routes[existing_route_id]
            if self._section_belongs_to_route(current_section, existing_route):
                return existing_route_id

        candidate_route_ids = [
            route_id
            for route_id, route in active_routes.items()
            if self._section_belongs_to_route(current_section, route)
        ]
        if len(candidate_route_ids) == 1:
            return candidate_route_ids[0]
        return None

    @staticmethod
    def _section_belongs_to_route(section_id: str, route: object) -> bool:
        section_token = str(section_id).strip()
        if not section_token:
            return False
        full_path = list(getattr(route, "full_path", []) or [])
        if section_token in full_path:
            return True
        approach_section = str(getattr(route, "approach_locking_section", "") or "").strip()
        return bool(approach_section and approach_section == section_token)

    def _release_previous_section_after_reassignment(
        self,
        *,
        previous_section: str,
        previous_route_id: str | None,
        new_route_id: str,
        new_section: str,
    ) -> None:
        previous_token = str(previous_section).strip()
        if not previous_token or previous_token == str(new_section).strip():
            return

        release_route_id = previous_route_id
        new_route = self.simulation.locking_engine.active_routes.get(str(new_route_id).strip())
        if new_route is not None:
            if previous_token in new_route.full_path:
                release_route_id = new_route.id
            elif new_route.approach_locking_section and previous_token == new_route.approach_locking_section:
                release_route_id = new_route.id

        try:
            self.simulation.locking_engine.set_section_occupied(
                previous_token,
                False,
                route_id_hint=release_route_id,
            )
        except KeyError:
            return


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.session import Simulation

