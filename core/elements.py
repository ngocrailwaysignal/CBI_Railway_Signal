"""Domain elements for geographical interlocking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional


class PointPosition(str, Enum):
    """Point machine position."""

    NORMAL = "NORMAL"
    REVERSE = "REVERSE"


class PointSymbolOrientation(str, Enum):
    """UI orientation of point symbol."""

    RIGHT = "RIGHT"
    UP = "UP"
    LEFT = "LEFT"
    DOWN = "DOWN"


class SignalAspect(str, Enum):
    """Signal aspect state."""

    STOP = "STOP"
    PROCEED = "PROCEED"


class SignalDirection(str, Enum):
    """Operational running direction represented by a signal."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"


@dataclass(slots=True)
class TrackSection:
    """A physical track circuit / track section."""

    id: str
    occupied: bool = False
    locked_by: Optional[str] = None
    length: float = 100.0


@dataclass(slots=True)
class ApproachSection(TrackSection):
    """Track-circuit section used for approach-locking detection."""


@dataclass(slots=True)
class Point:
    """A turnout (point) with switchable facing connections."""

    id: str
    position: PointPosition = PointPosition.NORMAL
    symbol_orientation: PointSymbolOrientation = PointSymbolOrientation.RIGHT
    locked_by: Optional[str] = None
    facing_connections: Dict[PointPosition, str] = field(default_factory=dict)


@dataclass(slots=True)
class Signal:
    """A lineside signal that protects a section."""

    id: str
    aspect: SignalAspect = SignalAspect.STOP
    direction: SignalDirection = SignalDirection.RIGHT
    protects: str = ""
    approach_section: str = ""
    route_id: Optional[str] = None


RailElement = TrackSection | ApproachSection | Point | Signal
