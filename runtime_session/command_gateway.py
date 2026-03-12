"""Internal runtime command dispatch handler."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from core.domain.model.elements import PointPosition

if TYPE_CHECKING:
    from runtime_session.session import RuntimeSession


@dataclass(slots=True)
class RuntimeCommandHandler:
    """Dispatch runtime operations to the stateful runtime session."""

    runtime_session: "RuntimeSession"

    def execute(self, op: str, payload: dict[str, Any] | None = None) -> Any:
        command = str(op).strip().lower()
        body = dict(payload or {})

        if command == "set_route":
            return self.runtime_session.set_route(
                entry_signal_id=str(body.get("entry_signal_id", "")).strip(),
                exit_signal_id=str(body.get("exit_signal_id", "")).strip(),
                overlap_length=int(body.get("overlap_length", 0)),
            )
        if command == "cancel_route":
            self.runtime_session.cancel_route(self._optional_token(body.get("route_id")) or "")
            return None
        if command == "set_section_occupied":
            return self.runtime_session.set_section_occupied(
                section_id=str(body.get("section_id", "")).strip(),
                occupied=bool(body.get("occupied", False)),
                route_id_hint=self._optional_token(body.get("route_id_hint")),
            )
        if command == "set_point_position":
            self.runtime_session.set_point_position(
                point_id=str(body.get("point_id", "")).strip(),
                position=body.get("position", PointPosition.NORMAL.value),
            )
            return None
        if command == "upsert_train":
            return self.runtime_session.upsert_train(
                train_id=str(body.get("train_id", "")).strip(),
                current_section=str(body.get("current_section", "")).strip(),
                route_id=self._optional_token(body.get("route_id")),
                speed=float(body.get("speed", 0.0)),
            )
        if command == "remove_train":
            return self.runtime_session.remove_train(str(body.get("train_id", "")).strip())
        if command == "hydrate_snapshot":
            self.runtime_session.hydrate_snapshot(
                snapshot=body.get("snapshot", {}),
                strict_route_ids=bool(body.get("strict_route_ids", True)),
            )
            return None
        raise ValueError(f"Unsupported runtime command: {op}")

    @staticmethod
    def _optional_token(raw_value: Any) -> str | None:
        if raw_value is None:
            return None
        token = str(raw_value).strip()
        if not token or token.upper() == "NONE":
            return None
        return token
