"""Domain elements for geographical interlocking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class PointPosition(str, Enum):
    """Point machine position."""

    NORMAL = "NORMAL"
    REVERSE = "REVERSE"


class SignalAspect(str, Enum):
    """Signal aspect state."""

    STOP = "STOP"
    PROCEED = "PROCEED"


class SignalRole(str, Enum):
    """Operational role of a signal in route setting."""

    AUTO = "AUTO"
    ENTRY = "ENTRY"
    EXIT = "EXIT"
    BOTH = "BOTH"


@dataclass(slots=True)
class TrackSection:
    """A physical track circuit / track section."""

    id: str
    occupied: bool = False
    locked_by: Optional[str] = None
    length: float = 100.0


@dataclass(slots=True)
class Point:
    """A turnout (point) with switchable facing connections."""

    id: str
    position: PointPosition = PointPosition.NORMAL
    locked_by: Optional[str] = None
    facing_connections: Dict[PointPosition, str] = field(default_factory=dict)


@dataclass(slots=True)
class Signal:
    """A lineside signal that protects a section."""

    id: str
    aspect: SignalAspect = SignalAspect.STOP
    role: SignalRole = SignalRole.AUTO
    protects: str = ""
    route_id: Optional[str] = None


RailElement = TrackSection | Point | Signal
