"""Smart IO protocol primitives."""

from __future__ import annotations


class SmartIOProtocolError(RuntimeError):
    """Protocol-level Smart IO error with machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code).strip() or "SMARTIO_ERROR"
        super().__init__(message)
