"""Serializable models for compiled interlocking specifications."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class InterlockingRouteSpec:
    """Compiled route definition used by runtime and audits."""

    route_name: str
    entry_signal: str
    exit_signal: str
    entry_element: str
    exit_element: str
    path: list[str]
    entry_protected_section: str | None = None
    exit_protected_section: str | None = None
    overlap: list[str] = field(default_factory=list)
    required_point_positions: dict[str, str] = field(default_factory=dict)
    locked_sections: list[str] = field(default_factory=list)
    conflicting_routes: list[str] = field(default_factory=list)
    calling_on_route: bool = False
    reverse_route: bool = False
    signal_aspect: str = "GREEN"

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_name": self.route_name,
            "entry_signal": self.entry_signal,
            "exit_signal": self.exit_signal,
            "entry_element": self.entry_element,
            "exit_element": self.exit_element,
            "entry_protected_section": self.entry_protected_section,
            "exit_protected_section": self.exit_protected_section,
            "path": list(self.path),
            "overlap": list(self.overlap),
            "required_point_positions": dict(self.required_point_positions),
            "locked_sections": list(self.locked_sections),
            "conflicting_routes": list(self.conflicting_routes),
            "calling_on_route": bool(self.calling_on_route),
            "reverse_route": bool(self.reverse_route),
            "signal_aspect": self.signal_aspect,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterlockingRouteSpec:
        return cls(
            route_name=str(data.get("route_name", "")).strip(),
            entry_signal=str(data.get("entry_signal", "")).strip(),
            exit_signal=str(data.get("exit_signal", "")).strip(),
            entry_element=str(data.get("entry_element", "")).strip(),
            exit_element=str(data.get("exit_element", "")).strip(),
            entry_protected_section=_optional_token(data.get("entry_protected_section")),
            exit_protected_section=_optional_token(data.get("exit_protected_section")),
            path=[str(node_id) for node_id in data.get("path", [])],
            overlap=[str(node_id) for node_id in data.get("overlap", [])],
            required_point_positions={
                str(point_id): str(position)
                for point_id, position in dict(data.get("required_point_positions", {})).items()
                if str(point_id).strip()
            },
            locked_sections=[str(node_id) for node_id in data.get("locked_sections", [])],
            conflicting_routes=[str(name) for name in data.get("conflicting_routes", [])],
            calling_on_route=bool(data.get("calling_on_route", False)),
            reverse_route=bool(data.get("reverse_route", False)),
            signal_aspect=str(data.get("signal_aspect", "GREEN")).strip() or "GREEN",
        )


def _optional_token(value: Any) -> str | None:
    token = str(value or "").strip()
    return token or None


@dataclass(slots=True)
class InterlockingSpec:
    """Compiled interlocking package for one topology snapshot."""

    schema_version: int
    generated_at: str
    overlap_length: int
    clearance_conflict_groups: list[list[str]]
    routes: list[InterlockingRouteSpec]
    station_id: str = "UNNAMED"

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": int(self.schema_version),
            "generated_at": self.generated_at,
            "station_id": self.station_id,
            "overlap_length": int(self.overlap_length),
            "clearance_conflict_groups": [list(group) for group in self.clearance_conflict_groups],
            "routes": [route.to_dict() for route in self.routes],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InterlockingSpec:
        raw_routes = data.get("routes", [])
        routes = [
            InterlockingRouteSpec.from_dict(route_data)
            for route_data in raw_routes
            if isinstance(route_data, dict)
        ]
        raw_groups = data.get("clearance_conflict_groups", [])
        groups = [
            [str(node_id) for node_id in group] for group in raw_groups if isinstance(group, list)
        ]
        return cls(
            schema_version=int(data.get("schema_version", 1)),
            generated_at=str(data.get("generated_at", "")).strip(),
            station_id=str(data.get("station_id", "UNNAMED")).strip() or "UNNAMED",
            overlap_length=max(0, int(data.get("overlap_length", 0))),
            clearance_conflict_groups=groups,
            routes=routes,
        )
