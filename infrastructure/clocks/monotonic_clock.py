"""Monotonic time provider."""

from __future__ import annotations

from time import monotonic
from typing import Protocol


class Clock(Protocol):
    """Abstract clock interface used by runtime locks/timers."""

    def now(self) -> float:
        """Return current monotonic time in seconds."""


class MonotonicClock:
    """Default production clock using time.monotonic()."""

    def now(self) -> float:
        return monotonic()
