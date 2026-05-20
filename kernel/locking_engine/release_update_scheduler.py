"""Background scheduler for deferred overlap-release checks."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock, Timer
from typing import Protocol


class ReleaseUpdateScheduler(Protocol):
    """Schedules one callback per route for deferred release checks."""

    def schedule(
        self, route_id: str, delay_seconds: float, callback: Callable[[], None]
    ) -> None: ...

    def cancel(self, route_id: str) -> None: ...

    def clear_all(self) -> None: ...


@dataclass(slots=True)
class ThreadedReleaseUpdateScheduler:
    """Coalesced timer scheduler keyed by route id."""

    _timers: dict[str, Timer] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def schedule(self, route_id: str, delay_seconds: float, callback: Callable[[], None]) -> None:
        route_key = str(route_id).strip()
        if not route_key:
            return
        with self._lock:
            if route_key in self._timers:
                return

            def _fire() -> None:
                with self._lock:
                    self._timers.pop(route_key, None)
                callback()

            timer = Timer(max(0.0, float(delay_seconds)), _fire)
            timer.daemon = True
            self._timers[route_key] = timer
            timer.start()

    def cancel(self, route_id: str) -> None:
        route_key = str(route_id).strip()
        if not route_key:
            return
        with self._lock:
            timer = self._timers.pop(route_key, None)
        if timer is not None:
            timer.cancel()

    def clear_all(self) -> None:
        with self._lock:
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            timer.cancel()
