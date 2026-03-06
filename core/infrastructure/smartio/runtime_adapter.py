"""Smart IO envelope adapter that mutates runtime state via simulation commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.runtime.simulation import Simulation


class SmartIOProtocolError(RuntimeError):
    """Protocol-level Smart IO error with machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = str(code).strip() or "SMARTIO_ERROR"
        super().__init__(message)


@dataclass(slots=True)
class SmartIORuntimeAdapter:
    """Translate Smart IO payloads into runtime commands."""

    simulation: Simulation
    default_overlap_length: int = 0

    def apply_command(self, payload: dict[str, Any]) -> Any:
        target = str(payload.get("target", "")).strip().lower()
        target_id = str(payload.get("id", "")).strip()
        action = str(payload.get("action", "")).strip().lower()
        value = str(payload.get("value", "")).strip().upper()
        context = payload.get("context", {}) if isinstance(payload.get("context"), dict) else {}

        if target == "point" and action == "set_position" and target_id:
            self.simulation.apply_runtime_command(
                "set_point_position",
                {
                    "point_id": target_id,
                    "position": value,
                },
            )
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
                route = self.simulation.apply_runtime_command(
                    "set_route",
                    {
                        "entry_signal_id": entry_signal,
                        "exit_signal_id": exit_signal,
                        "overlap_length": overlap_length,
                    },
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
                    self.simulation.apply_runtime_command(
                        "cancel_route",
                        {"route_id": route_id},
                    )
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
            self.simulation.apply_runtime_command(
                "set_point_position",
                {"point_id": point_id, "position": position},
            )

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
            expected_train_ids: set[str] = set()
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
                expected_train_ids.add(train_id)
                try:
                    speed = float(train_item.get("speed", 0.0))
                except (TypeError, ValueError) as exc:
                    raise SmartIOProtocolError(
                        "INVALID_PAYLOAD",
                        f"Train {train_id} has invalid speed",
                    ) from exc
                try:
                    self.simulation.apply_runtime_command(
                        "upsert_train",
                        {
                            "train_id": train_id,
                            "current_section": current_section,
                            "route_id": self._optional_token(train_item.get("route_id")),
                            "speed": speed,
                        },
                    )
                except RuntimeError as exc:
                    raw_route_id = self._optional_token(train_item.get("route_id"))
                    if raw_route_id and "is not active" in str(exc):
                        # Web clients can carry stale route_id when a route auto-releases in CBI.
                        self.simulation.apply_runtime_command(
                            "upsert_train",
                            {
                                "train_id": train_id,
                                "current_section": current_section,
                                "route_id": None,
                                "speed": speed,
                            },
                        )
                    else:
                        raise

            for existing_train_id in list(self.simulation.trains.keys()):
                if existing_train_id in expected_train_ids:
                    continue
                self.simulation.apply_runtime_command(
                    "remove_train",
                    {"train_id": existing_train_id},
                )

        for section_id, occupied in sorted(section_updates, key=lambda item: item[1]):
            self.simulation.apply_runtime_command(
                "set_section_occupied",
                {
                    "section_id": section_id,
                    "occupied": occupied,
                },
            )

    def apply_runtime_snapshot(self, payload: dict[str, Any]) -> None:
        try:
            self.simulation.apply_runtime_command(
                "hydrate_snapshot",
                {
                    "snapshot": payload,
                    "strict_route_ids": True,
                },
            )
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
            for active_route in self.simulation.locking_engine.active_routes.values():
                if (
                    active_route.entry_signal_id == entry_signal
                    and active_route.exit_signal_id == exit_signal
                ):
                    return active_route.id

        signal = self.simulation.topology.signals.get(target_id)
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
