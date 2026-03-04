"""Interlocking compiler components."""

from __future__ import annotations

from typing import Any

__all__ = ["RouteCompiler", "InterlockingRouteSpec", "InterlockingSpec"]


def __getattr__(name: str) -> Any:
    """Lazily expose compiler symbols to avoid import cycles."""
    if name == "RouteCompiler":
        from .route_compiler import RouteCompiler

        return RouteCompiler
    if name in {"InterlockingRouteSpec", "InterlockingSpec"}:
        from .spec_models import InterlockingRouteSpec, InterlockingSpec

        return {"InterlockingRouteSpec": InterlockingRouteSpec, "InterlockingSpec": InterlockingSpec}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
