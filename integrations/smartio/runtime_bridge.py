"""Smart IO envelope adapter that mutates runtime state via typed session calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.application.runtime_session_port import RuntimeSessionPort
from integrations.smartio.protocol import SmartIOProtocolError


@dataclass(slots=True)
class SmartIORuntimeBridge:
    """Translate Smart IO payloads into runtime commands."""

    runtime_session: RuntimeSessionPort
    default_overlap_length: int = 0

    def command_from_envelope(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized_type = str(event_type).strip().lower()
        if normalized_type == "command":
            command_id = str(payload.get("command_id", "")).strip()
            source_id = str(payload.get("source_id", "")).strip()
            kind = str(payload.get("kind", "")).strip()
            command_payload = payload.get("payload", {})
            if not command_id or not source_id or not kind or not isinstance(command_payload, dict):
                raise SmartIOProtocolError(
                    "INVALID_PAYLOAD",
                    "Command envelope requires command_id/source_id/kind/payload",
                )
            return {
                "command_id": command_id,
                "source_id": source_id,
                "kind": kind,
                "payload": dict(command_payload),
                "ts": float(payload.get("ts", 0.0) or 0.0),
            }
        if normalized_type == "state_update":
            return self.command_from_state_update(payload)
        raise SmartIOProtocolError("UNSUPPORTED_COMMAND", f"Unsupported envelope type {event_type}")

    def command_from_state_update(
        self,
        payload: dict[str, Any],
        *,
        command_id: str | None = None,
        source_id: str | None = None,
        ts: float | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise SmartIOProtocolError("INVALID_PAYLOAD", "state_update payload must be an object")
        actual_command_id = str(command_id or payload.get("msg_id", "")).strip()
        if not actual_command_id:
            raise SmartIOProtocolError("INVALID_PAYLOAD", "state_update requires msg_id/command_id")
        actual_source_id = str(source_id or payload.get("source_id", "")).strip() or "smartio-web"
        command_payload = dict(payload)
        command_payload.pop("msg_id", None)
        command_payload.pop("source_id", None)
        return {
            "command_id": actual_command_id,
            "source_id": actual_source_id,
            "kind": "apply_state_update",
            "payload": command_payload,
            "ts": float(ts if ts is not None else payload.get("ts", 0.0) or 0.0),
        }

    def apply_command(self, payload: dict[str, Any]) -> Any:
        target = str(payload.get("target", "")).strip().lower()
        target_id = str(payload.get("id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()
        value = str(payload.get("value", "")).strip().upper()
        context = payload.get("context", {}) if isinstance(payload.get("context"), dict) else {}

        if target == "point" and action == "set_position" and target_id:
            self.runtime_session.set_point_position(target_id, value)
            return {"target": target, "id": target_id, "action": action, "value": value}

        if target == "signal" and action == "set_aspect" and target_id:
            if value == "PROCEED":
                entry_signal = str(context.get("entry_signal", "")).strip() or target_id
                exit_signal = str(context.get("exit_signal", "")).strip()
                if not entry_signal or not exit_signal:
                    raise SmartIOProtocolError(
                        "INVALID_PAYLOAD",
                        "Signal PROCEED command requires context.entry_signal/context.exit_signal",
                    )
                overlap_path = self._normalize_node_list(context.get("overlap_path"))
                try:
                    overlap_length = (
                        len(overlap_path)
                        if overlap_path
                        else int(context.get("overlap_length", self.default_overlap_length))
                    )
                except (TypeError, ValueError) as exc:
                    raise SmartIOProtocolError(
                        "INVALID_PAYLOAD",
                        "context.overlap_length must be a number",
                    ) from exc
                route = self.runtime_session.set_route(
                    entry_signal_id=entry_signal,
                    exit_signal_id=exit_signal,
                    overlap_length=overlap_length,
                )
                expected_route_id = self._optional_token(context.get("route_id"))
                if expected_route_id and expected_route_id != getattr(route, "id", ""):
                    raise SmartIOProtocolError(
                        "SNAPSHOT_INCONSISTENT",
                        f"Route ID mismatch for {entry_signal}->{exit_signal}: "
                        f"{expected_route_id} != {getattr(route, 'id', '')}",
                    )
                return route

            if value == "STOP":
                route_id = self._resolve_route_to_cancel(
                    target_id=target_id,
                    context=context,
                )
                if route_id:
                    self.runtime_session.cancel_route(route_id)
                return {"target": target, "id": target_id, "action": action, "value": value}

            raise SmartIOProtocolError(
                "INVALID_PAYLOAD",
                f"Unsupported signal aspect command value: {value}",
            )

        raise SmartIOProtocolError(
            "UNSUPPORTED_COMMAND",
            f"Unsupported command target/action: {target}/{action}",
        )

    def apply_state_update(self, payload: dict[str, Any]) -> None:
        section_updates: list[tuple[str, bool]] = []
        for section_item in payload.get("sections", []):
            if not isinstance(section_item, dict):
                continue
            if "locked_by" in section_item:
                raise SmartIOProtocolError(
                    "DIRECT_STATE_WRITE_BLOCKED",
                    "Direct locked_by updates are blocked; use interlocking commands",
                )
            section_id = str(section_item.get("id", "")).strip()
            if not section_id or "occupied" not in section_item:
                continue
            section_updates.append((section_id, bool(section_item.get("occupied", False))))

        for point_item in payload.get("points", []):
            if not isinstance(point_item, dict):
                continue
            if "locked_by" in point_item:
                raise SmartIOProtocolError(
                    "DIRECT_STATE_WRITE_BLOCKED",
                    "Direct locked_by updates are blocked; use interlocking commands",
                )
            point_id = str(point_item.get("id", "")).strip()
            position = str(point_item.get("position", "")).strip().upper()
            if not point_id or not position:
                continue
            self.runtime_session.set_point_position(point_id, position)

        for signal_item in payload.get("signals", []):
            if not isinstance(signal_item, dict):
                continue
            if "aspect" in signal_item or "route_id" in signal_item:
                raise SmartIOProtocolError(
                    "DIRECT_STATE_WRITE_BLOCKED",
                    "Direct signal aspect/route_id updates are blocked; use signal commands",
                )

        trains_payload = payload.get("trains")
        if isinstance(trains_payload, list):
            for train_item in trains_payload:
                if not isinstance(train_item, dict):
                    continue
                train_id = str(train_item.get("id", "")).strip()
                current_section = str(train_item.get("current_section", "")).strip()
                if not train_id or not current_section:
                    raise SmartIOProtocolError(
                        "INVALID_PAYLOAD",
                        "Each train requires id/current_section",
                    )
                try:
                    speed = float(train_item.get("speed", 0.0))
                except (TypeError, ValueError) as exc:
                    raise SmartIOProtocolError(
                        "INVALID_PAYLOAD",
                        f"Train {train_id} has invalid speed",
                    ) from exc
                try:
                    self.runtime_session.upsert_train(
                        train_id=train_id,
                        current_section=current_section,
                        route_id=self._optional_token(train_item.get("route_id")),
                        speed=speed,
                    )
                except RuntimeError as exc:
                    raw_route_id = self._optional_token(train_item.get("route_id"))
                    if raw_route_id and "is not active" in str(exc):
                        # Web clients can carry stale route_id when a route auto-releases in CBI.
                        self.runtime_session.upsert_train(
                            train_id=train_id,
                            current_section=current_section,
                            route_id=None,
                            speed=speed,
                        )
                    else:
                        raise

        removed_train_ids = payload.get("removed_train_ids")
        if isinstance(removed_train_ids, list):
            for raw_train_id in removed_train_ids:
                train_id = str(raw_train_id).strip()
                if not train_id:
                    continue
                self.runtime_session.trains.pop(train_id, None)

        for section_id, occupied in section_updates:
            self.runtime_session.set_section_occupied(section_id, occupied)

    def apply_runtime_snapshot(self, payload: dict[str, Any]) -> None:
        try:
            self.runtime_session.hydrate_snapshot(snapshot=payload, strict_route_ids=True)
        except SmartIOProtocolError:
            raise
        except Exception as exc:  # pragma: no cover - defensive mapping
            raise SmartIOProtocolError("SNAPSHOT_INCONSISTENT", str(exc)) from exc

    def _resolve_route_to_cancel(self, *, target_id: str, context: dict[str, Any]) -> str | None:
        route_id = self._optional_token(context.get("route_id"))
        if route_id:
            return route_id

        entry_signal = str(context.get("entry_signal", "")).strip() or target_id
        exit_signal = str(context.get("exit_signal", "")).strip()
        if entry_signal and exit_signal:
            for active_route in self.runtime_session.locking_engine.active_routes.values():
                if (
                    active_route.entry_signal_id == entry_signal
                    and active_route.exit_signal_id == exit_signal
                ):
                    return active_route.id

        signal = self.runtime_session.topology.signals.get(target_id)
        if signal is not None and signal.route_id:
            return signal.route_id
        return None

    @staticmethod
    def _normalize_node_list(raw_value: Any) -> list[str]:
        if not isinstance(raw_value, list):
            return []
        return [str(item).strip() for item in raw_value if str(item).strip()]

    @staticmethod
    def _optional_token(raw_value: Any) -> str | None:
        if raw_value is None:
            return None
        token = str(raw_value).strip()
        if not token or token.upper() == "NONE":
            return None
        return token


SmartIORuntimeAdapter = SmartIORuntimeBridge
