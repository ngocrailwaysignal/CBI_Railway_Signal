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

            self.vacate_train_current_section(train)
            train.current_section = normalized_section
            train.speed = normalized_speed
            train.assign_route(route, self.simulation.topology, self.simulation.locking_engine)
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


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.runtime.simulation import Simulation

