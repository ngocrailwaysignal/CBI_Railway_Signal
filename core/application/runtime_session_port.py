"""Application-facing protocol for stateful runtime sessions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from core.domain.model.elements import PointPosition
from core.domain.model.topology import RailwayTopology


@runtime_checkable
class RuntimeSessionPort(Protocol):
    topology: RailwayTopology
    locking_engine: object
    trains: dict[str, object]
    tick: int

    def set_route(self, entry_signal_id: str, exit_signal_id: str, overlap_length: int = 0): ...
    def cancel_route(self, route_id: str) -> None: ...
    def set_section_occupied(
        self,
        section_id: str,
        occupied: bool,
        *,
        route_id_hint: str | None = None,
    ) -> dict[str, object]: ...
    def set_point_position(self, point_id: str, position: PointPosition | str) -> None: ...
    def upsert_train(
        self,
        *,
        train_id: str,
        current_section: str,
        route_id: str | None = None,
        speed: float = 0.0,
    ): ...
    def remove_train(self, train_id: str) -> bool: ...
    def hydrate_snapshot(self, *, snapshot: dict, strict_route_ids: bool = True) -> None: ...
    def reconcile_manual_free_section(self, section_id: str) -> list[str]: ...
    def step(self) -> None: ...
