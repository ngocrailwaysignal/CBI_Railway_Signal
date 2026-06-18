"""Structured runtime error codes shared by kernel safety checks."""

from __future__ import annotations

from typing import Any


class StructuredError(str):
    """String-compatible error with a stable translation key and parameters."""

    code: str
    params: dict[str, Any]

    def __new__(cls, code: str, **params: Any) -> "StructuredError":
        normalized_params = {key: value for key, value in params.items()}
        details = ", ".join(
            f"{key}={value}" for key, value in sorted(normalized_params.items())
        )
        message = f"{code}: {details}" if details else code
        instance = str.__new__(cls, message)
        instance.code = code
        instance.params = normalized_params
        return instance

    def as_dict(self) -> dict[str, Any]:
        """Return a transport-friendly structured error payload."""
        return {"code": self.code, "params": dict(self.params)}


def structured_error(code: str, **params: Any) -> StructuredError:
    """Build a stable, string-compatible error for exceptions and issue lists."""
    return StructuredError(code, **params)
