"""Domain elements for geographical interlocking."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class PointPosition(StrEnum):
    """Point machine position."""

    NORMAL = "NORMAL"
    REVERSE = "REVERSE"


class PointSymbolOrientation(StrEnum):
    """UI orientation of point symbol."""

    RIGHT = "RIGHT"
    UP = "UP"
    LEFT = "LEFT"
    DOWN = "DOWN"


class SignalAspect(StrEnum):
    """Signal aspect state."""

    RED = "RED"
    YELLOW = "YELLOW"
    GREEN = "GREEN"
    BLUE = "BLUE"
    YELLOW_BLUE = "YELLOW_BLUE"
    GREEN_BLUE = "GREEN_BLUE"
    STOP = "RED"
    PROCEED = "GREEN"

    @classmethod
    def _missing_(cls, value: object) -> SignalAspect | None:
        token = str(value or "").strip().upper().replace("-", "_").replace(" ", "_")
        legacy = {
            "STOP": cls.RED,
            "PROCEED": cls.GREEN,
            "BLUE_YELLOW": cls.YELLOW_BLUE,
            "BLUE_GREEN": cls.GREEN_BLUE,
        }
        return legacy.get(token)


def normalize_signal_aspect(value: object, default: SignalAspect = SignalAspect.RED) -> SignalAspect:
    """Normalize persisted/user aspect values, including legacy STOP/PROCEED tokens."""
    try:
        return SignalAspect(value)
    except ValueError:
        return default


class SignalDirection(StrEnum):
    """Operational running direction represented by a signal."""

    LEFT = "LEFT"
    RIGHT = "RIGHT"


@dataclass(slots=True)
class TrackSection:
    """A physical track circuit / track section."""

    id: str
    occupied: bool = False
    locked_by: str | None = None
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
    locked_by: str | None = None
    facing_connections: dict[PointPosition, str] = field(default_factory=dict)


@dataclass(slots=True)
class Signal:
    """A lineside signal that protects a section or configured route."""

    id: str
    aspect: SignalAspect = SignalAspect.RED
    direction: SignalDirection = SignalDirection.RIGHT
    protects: str = ""
    approach_section: str = ""
    route_id: str | None = None
    is_blocking: bool = False


@dataclass(slots=True)
class DisplayLabel:
    """A visual text label placed on the design layout."""

    id: str
    text: str = "LABEL"
    font_size: float = 18.0
    color: str = "#111111"
    width: float = 120.0
    height: float = 48.0


@dataclass(slots=True)
class DisplayLine:
    """A visual one-way arrow line placed on the design layout."""

    id: str
    start: tuple[float, float] = (0.0, 0.0)
    end: tuple[float, float] = (120.0, 0.0)
    color: str = "#111111"
    width: float = 2.0


RailElement = TrackSection | ApproachSection | Point | Signal
LayoutElement = RailElement | DisplayLabel | DisplayLine
