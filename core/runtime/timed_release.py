"""Timed release schedule for overlap/time locking operations."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TimedReleaseScheduler:
    """Stores pending overlap-release deadlines per active route."""

    overlap_release_seconds: float = 0.0
    pending_overlap_releases: dict[str, float] = field(default_factory=dict)

    def configure_overlap_release(self, overlap_release_seconds: float | None) -> None:
        """Update overlap release delay if provided."""
        if overlap_release_seconds is not None:
            self.overlap_release_seconds = max(0.0, float(overlap_release_seconds))

    def clear_all(self) -> None:
        self.pending_overlap_releases.clear()

    def clear_route(self, route_id: str) -> None:
        self.pending_overlap_releases.pop(route_id, None)

    def schedule_route_release(self, route_id: str, now: float) -> float:
        """Schedule route release and return due timestamp."""
        if route_id not in self.pending_overlap_releases:
            self.pending_overlap_releases[route_id] = now + self.overlap_release_seconds
        return self.pending_overlap_releases[route_id]

    def due_routes(self, now: float) -> list[str]:
        """Return route ids whose overlap-release timer has elapsed."""
        return [
            route_id
            for route_id, due_time in list(self.pending_overlap_releases.items())
            if now >= due_time
        ]

    def pending_due_times(self) -> dict[str, float]:
        """Return a shallow copy of all pending overlap-release deadlines."""
        return dict(self.pending_overlap_releases)

