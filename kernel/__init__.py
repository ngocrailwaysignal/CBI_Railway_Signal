"""Kernel runtime engines and product rules."""

from __future__ import annotations

__all__ = [
    "GenericProductKernel",
    "LockingEngine",
    "OccupancyReconciler",
    "ProductRules",
    "ReleaseUpdateScheduler",
    "RouteDispatcher",
    "RouteEngine",
    "SafetyMonitor",
    "ThreadedReleaseUpdateScheduler",
]


def __getattr__(name: str) -> object:
    if name == "GenericProductKernel" or name == "ProductRules":
        from kernel.product_kernel import GenericProductKernel, ProductRules

        return {
            "GenericProductKernel": GenericProductKernel,
            "ProductRules": ProductRules,
        }[name]
    if name == "LockingEngine":
        from kernel.locking_engine.locking_engine import LockingEngine

        return LockingEngine
    if name == "OccupancyReconciler":
        from kernel.occupancy_engine.occupancy_reconciler import OccupancyReconciler

        return OccupancyReconciler
    if name == "ReleaseUpdateScheduler" or name == "ThreadedReleaseUpdateScheduler":
        from kernel.locking_engine.release_update_scheduler import (
            ReleaseUpdateScheduler,
            ThreadedReleaseUpdateScheduler,
        )

        return {
            "ReleaseUpdateScheduler": ReleaseUpdateScheduler,
            "ThreadedReleaseUpdateScheduler": ThreadedReleaseUpdateScheduler,
        }[name]
    if name == "RouteDispatcher":
        from kernel.route_dispatcher.route_dispatcher import RouteDispatcher

        return RouteDispatcher
    if name == "RouteEngine":
        from kernel.route_dispatcher.route_engine import RouteEngine

        return RouteEngine
    if name == "SafetyMonitor":
        from kernel.safety_engine.safety_monitor import SafetyMonitor

        return SafetyMonitor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
