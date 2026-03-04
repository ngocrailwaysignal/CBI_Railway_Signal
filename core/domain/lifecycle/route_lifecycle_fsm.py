"""Route lifecycle finite state machine."""

from __future__ import annotations

from enum import Enum


class RouteLifecycleState(str, Enum):
    """Lifecycle states for one locked route."""

    RESERVED = "RESERVED"
    CLEARED_REVERSIBLE = "CLEARED_REVERSIBLE"
    APPROACH_LOCKED = "APPROACH_LOCKED"
    TRAIN_IN_ROUTE = "TRAIN_IN_ROUTE"
    RELEASING = "RELEASING"
    RELEASED = "RELEASED"


class RouteLifecycleFSM:
    """State transition guard for route lifecycle."""

    _ALLOWED: dict[RouteLifecycleState, set[RouteLifecycleState]] = {
        RouteLifecycleState.RESERVED: {RouteLifecycleState.CLEARED_REVERSIBLE},
        RouteLifecycleState.CLEARED_REVERSIBLE: {
            RouteLifecycleState.APPROACH_LOCKED,
            RouteLifecycleState.TRAIN_IN_ROUTE,
            RouteLifecycleState.RELEASING,
        },
        RouteLifecycleState.APPROACH_LOCKED: {
            RouteLifecycleState.TRAIN_IN_ROUTE,
            RouteLifecycleState.RELEASING,
        },
        RouteLifecycleState.TRAIN_IN_ROUTE: {RouteLifecycleState.RELEASING},
        RouteLifecycleState.RELEASING: {RouteLifecycleState.RELEASED},
        RouteLifecycleState.RELEASED: set(),
    }

    @classmethod
    def can_transition(cls, current: RouteLifecycleState, target: RouteLifecycleState) -> bool:
        if current == target:
            return True
        return target in cls._ALLOWED.get(current, set())

    @classmethod
    def transition(cls, current: RouteLifecycleState, target: RouteLifecycleState) -> RouteLifecycleState:
        if not cls.can_transition(current, target):
            raise ValueError(f"Invalid lifecycle transition {current.value} -> {target.value}")
        return target

