"""Approach-locking state machine with time locking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import monotonic


class ApproachLockState(str, Enum):
    """Lifecycle states of approach locking for one active route."""

    ROUTE_SET = "ROUTE_SET"
    APPROACH_LOCKED = "APPROACH_LOCKED"
    TIME_LOCKED = "TIME_LOCKED"


@dataclass(slots=True)
class ApproachLockRecord:
    """Runtime approach-locking state tied to one route."""

    route_id: str
    entry_signal_id: str
    approach_section_id: str | None
    state: ApproachLockState = ApproachLockState.ROUTE_SET
    time_lock_until: float = 0.0


class ApproachLockingStateMachine:
    """Manages approach locking transitions and delayed cancellations."""

    def __init__(self, time_lock_seconds: float = 30.0) -> None:
        self.time_lock_seconds = max(0.0, float(time_lock_seconds))
        self._records: dict[str, ApproachLockRecord] = {}

    def register_route(
        self,
        route_id: str,
        entry_signal_id: str,
        approach_section_id: str | None,
    ) -> None:
        self._records[route_id] = ApproachLockRecord(
            route_id=route_id,
            entry_signal_id=entry_signal_id,
            approach_section_id=approach_section_id,
        )

    def mark_approach_locked(self, route_id: str) -> None:
        record = self._records.get(route_id)
        if record is None:
            return
        if record.state == ApproachLockState.ROUTE_SET:
            record.state = ApproachLockState.APPROACH_LOCKED

    def request_cancellation(
        self,
        route_id: str,
        approach_occupied: bool,
        now: float | None = None,
    ) -> tuple[bool, str]:
        """Request route cancellation, applying approach/time-lock rules."""
        record = self._records.get(route_id)
        if record is None:
            return True, "Route not found"

        if approach_occupied:
            record.state = ApproachLockState.APPROACH_LOCKED
            record.time_lock_until = 0.0
            return False, "Approach section occupied: cancellation inhibited"

        current_time = monotonic() if now is None else now
        if record.state == ApproachLockState.TIME_LOCKED:
            remaining = max(0.0, record.time_lock_until - current_time)
            if remaining <= 0.0:
                return True, "Time locking elapsed"
            return False, f"Time locking active: {remaining:.1f}s remaining"

        if record.state == ApproachLockState.ROUTE_SET:
            return True, "Cancelled before approach locking"

        record.state = ApproachLockState.TIME_LOCKED
        record.time_lock_until = current_time + self.time_lock_seconds
        return False, f"Approach locking active, time lock {self.time_lock_seconds:.1f}s"

    def releasable_routes(self, now: float | None = None) -> list[str]:
        """Return route IDs whose time lock has elapsed."""
        current_time = monotonic() if now is None else now
        return [
            route_id
            for route_id, record in self._records.items()
            if record.state == ApproachLockState.TIME_LOCKED
            and current_time >= record.time_lock_until
        ]

    def state(self, route_id: str) -> ApproachLockState | None:
        """Get current approach-lock state for one route."""
        record = self._records.get(route_id)
        return record.state if record is not None else None

    def remaining_time_lock(self, route_id: str, now: float | None = None) -> float:
        """Get remaining time-lock duration in seconds."""
        record = self._records.get(route_id)
        if record is None or record.state != ApproachLockState.TIME_LOCKED:
            return 0.0
        current_time = monotonic() if now is None else now
        return max(0.0, record.time_lock_until - current_time)

    def clear(self, route_id: str) -> None:
        """Drop any approach-locking state for a released route."""
        self._records.pop(route_id, None)

    def clear_all(self) -> None:
        """Drop approach-locking state for all routes."""
        self._records.clear()
