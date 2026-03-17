"""SmartIO/runtime coordination for MainWindow."""

from __future__ import annotations

import time
from collections.abc import Callable
from urllib.parse import urlparse
from typing import Any

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from runtime.application import AppMode
from core.domain.model.topology import RailwayTopology
from runtime import GenericApplicationProfile, GenericApplicationService, RuntimeWorkspaceService
from integration.smartio_adapter import (
    SmartIOProtocolError,
    SmartIORuntimeBridge,
    SmartIOWebSocketClient,
)


class SmartIORuntimeCoordinator(QObject):
    """Own SmartIO lifecycle and translate events into runtime workspace mutations."""

    smartio_status_changed = pyqtSignal(str)
    smartio_error = pyqtSignal(str)
    runtime_state_changed = pyqtSignal(object)
    runtime_health_changed = pyqtSignal(object)

    def __init__(
        self,
        *,
        profile: GenericApplicationProfile,
        application_service: GenericApplicationService,
        runtime_workspace_service: RuntimeWorkspaceService,
        topology_provider: Callable[[], RailwayTopology],
        operating_mode_provider: Callable[[], AppMode],
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._application_service = application_service
        self._runtime_workspace_service = runtime_workspace_service
        self._topology_provider = topology_provider
        self._operating_mode_provider = operating_mode_provider
        self._ws_url = str(getattr(self._profile, "smart_io_ws_url", "")).strip()
        self._smartio_status_token = "disabled"
        self._smartio_client: SmartIOWebSocketClient | None = None
        self._last_snapshot_published_at: float | None = None
        self._last_transport_message_at: float | None = None
        self._last_command_result_at: float | None = None
        self._last_runtime_event_seq: int = 0
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(1000)
        self._health_timer.timeout.connect(self._emit_runtime_health)
        self._heartbeat_timer = QTimer(self)
        self._heartbeat_timer.setInterval(
            max(1000, int(float(self._profile.smart_io_snapshot_heartbeat_seconds) * 1000.0))
        )
        self._heartbeat_timer.timeout.connect(self.publish_runtime_snapshot)
        self._initialize_client(parent)
        self._health_timer.start()

    @property
    def smartio_status_token(self) -> str:
        return self._smartio_status_token

    @property
    def is_connected(self) -> bool:
        return self._smartio_client is not None and self._smartio_client.is_connected

    @property
    def current_ws_url(self) -> str:
        return self._ws_url

    @property
    def runtime_health(self) -> dict[str, Any]:
        health = self._runtime_workspace_service.runtime_health()
        now = time.time()
        stale_after = max(1.0, float(getattr(self._profile, "smart_io_runtime_stale_seconds", 15.0)))
        snapshot_age = (
            max(0.0, now - self._last_snapshot_published_at)
            if self._last_snapshot_published_at is not None
            else None
        )
        command_age = (
            max(0.0, now - self._last_command_result_at)
            if self._last_command_result_at is not None
            else None
        )
        degraded_reason = health.degraded_reason
        if (
            self._operating_mode_provider() is AppMode.RUNTIME
            and self.is_connected
            and snapshot_age is not None
            and snapshot_age > stale_after
        ):
            degraded_reason = (
                degraded_reason or f"TRANSPORT_UNAVAILABLE: snapshot stale for {snapshot_age:.1f}s"
            )
        return {
            "topology_revision": health.topology_revision,
            "stream_seq": health.stream_seq,
            "last_applied_command_at": health.last_applied_command_at,
            "last_snapshot_at": self._last_snapshot_published_at,
            "last_command_result_at": self._last_command_result_at,
            "last_transport_message_at": self._last_transport_message_at,
            "last_runtime_event_seq": self._last_runtime_event_seq,
            "last_command_id": health.last_command_id,
            "last_command_status": health.last_command_status,
            "snapshot_age_seconds": snapshot_age,
            "command_age_seconds": command_age,
            "degraded": bool(degraded_reason),
            "degraded_reason": degraded_reason,
        }

    def _is_local_endpoint(self) -> bool:
        ws_url = str(self._ws_url or "").strip()
        if not ws_url:
            return False
        parsed = urlparse(ws_url)
        host = str(parsed.hostname or "").strip().lower()
        return host in {"127.0.0.1", "localhost"}

    def _should_keep_connection_for_mode(self, mode: AppMode) -> bool:
        return bool(str(self._ws_url or "").strip())

    def _can_publish_snapshot_for_mode(self, mode: AppMode) -> bool:
        return self._should_keep_connection_for_mode(mode)

    def _can_accept_transport_commands_for_mode(self, mode: AppMode) -> bool:
        if mode is AppMode.RUNTIME:
            return True
        return mode is AppMode.SIMULATION and self._is_local_endpoint()

    def _initialize_client(self, parent: QObject | None) -> None:
        ws_url = str(self._ws_url).strip()
        if not ws_url:
            self._set_status("disabled")
            return
        self._smartio_client = SmartIOWebSocketClient(
            ws_url=ws_url,
            reconnect_enabled=bool(getattr(self._profile, "smart_io_reconnect_enabled", True)),
            reconnect_max_seconds=float(
                getattr(self._profile, "smart_io_reconnect_max_seconds", 30.0)
            ),
            parent=parent,
        )
        self._smartio_client.status_changed.connect(self._on_status_changed)
        self._smartio_client.error_occurred.connect(self._on_error)
        self._smartio_client.event_received.connect(self._on_event_received)
        self._set_status("disconnected")

    def set_ws_url(self, ws_url: str) -> None:
        normalized_url = str(ws_url).strip()
        if normalized_url == self._ws_url:
            return
        next_is_local = False
        if normalized_url:
            parsed = urlparse(normalized_url)
            next_is_local = str(parsed.hostname or "").strip().lower() in {"127.0.0.1", "localhost"}
        current_mode = self._operating_mode_provider()
        should_reconnect = bool(normalized_url)
        self.disconnect()
        if self._smartio_client is not None:
            self._smartio_client.deleteLater()
        self._smartio_client = None
        self._ws_url = normalized_url
        self._last_transport_message_at = None
        self._last_command_result_at = None
        self._last_snapshot_published_at = None
        self._last_runtime_event_seq = 0
        self._initialize_client(self)
        self._emit_runtime_health()
        if should_reconnect:
            self.ensure_connection(force=True)

    def sync_connection_for_mode(self, mode: AppMode) -> None:
        if self._smartio_client is None:
            return
        if self._should_keep_connection_for_mode(mode):
            self.ensure_connection()
            return
        self._heartbeat_timer.stop()
        self._smartio_client.disconnect()

    def ensure_connection(self, *, force: bool = False) -> None:
        if self._smartio_client is None:
            return
        if not force and not self._should_keep_connection_for_mode(self._operating_mode_provider()):
            return
        if not self._smartio_client.is_connected:
            self._smartio_client.connect()

    def disconnect(self) -> None:
        self._heartbeat_timer.stop()
        if self._smartio_client is not None:
            self._smartio_client.disconnect()

    def publish_runtime_snapshot(self) -> bool:
        if self._smartio_client is None or not self._smartio_client.is_connected:
            return False
        if not self._can_publish_snapshot_for_mode(self._operating_mode_provider()):
            return False
        try:
            for event in self._runtime_workspace_service.drain_pending_runtime_events():
                self._last_runtime_event_seq = max(
                    self._last_runtime_event_seq,
                    int(event.get("stream_seq", 0) or 0),
                )
                envelope = self._smartio_client.build_envelope("runtime_event", event)
                self._smartio_client.send_event(envelope)
            snapshot = self._runtime_workspace_service.checkpoint_runtime_snapshot()
            snapshot["layout"] = self._application_service.build_layout_payload(
                self._topology_provider()
            )
            envelope = self._smartio_client.build_envelope("runtime_snapshot", snapshot)
            self._smartio_client.send_event(envelope)
            self._last_snapshot_published_at = time.time()
            self._emit_runtime_health()
            return True
        except Exception as exc:
            self.smartio_error.emit(f"runtime_snapshot send failed: {exc}")
            return False

    def _on_status_changed(self, status: str) -> None:
        self._set_status(status)
        if self._smartio_status_token == "connected":
            self._send_hello()
            self.publish_runtime_snapshot()
            self._heartbeat_timer.start()
        elif self._smartio_status_token in {"disconnected", "error", "disabled"}:
            self._heartbeat_timer.stop()
        self._emit_runtime_health()

    def _on_error(self, message: str) -> None:
        self.smartio_error.emit(str(message).strip())
        self._emit_runtime_health()

    def _on_event_received(self, event: dict) -> None:
        self._last_transport_message_at = time.time()
        event_type = str(event.get("type", "")).strip().lower()
        payload = event.get("payload", {})
        if event_type == "error" and isinstance(payload, dict):
            code = str(payload.get("code", "")).strip()
            message = str(payload.get("message", "")).strip() or "Unknown SmartIO error"
            self.smartio_error.emit(f"{code}: {message}" if code else message)
            self._emit_runtime_health()
            return
        if event_type in {"ack", "command_result"} and isinstance(payload, dict):
            self._last_command_result_at = time.time()
            self._emit_runtime_health()
            return
        if event_type == "runtime_event" and isinstance(payload, dict):
            self._last_runtime_event_seq = max(
                self._last_runtime_event_seq,
                int(payload.get("stream_seq", 0) or 0),
            )
            self._emit_runtime_health()
            return
        current_mode = self._operating_mode_provider()
        if not self._can_accept_transport_commands_for_mode(current_mode):
            command_id = (
                str(payload.get("command_id", payload.get("msg_id", ""))).strip()
                if isinstance(payload, dict)
                else ""
            )
            source_id = (
                str(payload.get("source_id", "")).strip()
                if isinstance(payload, dict)
                else ""
            ) or "smartio-web"
            if event_type in {"command", "state_update"} and command_id:
                self._send_command_result(
                    {
                        "command_id": command_id,
                        "source_id": source_id,
                        "status": "rejected",
                        "message": "CBI is not in Runtime mode",
                        "stream_seq": self._runtime_workspace_service.runtime_health().stream_seq,
                    }
                )
            return
        if event_type not in {"command", "state_update"} or not isinstance(payload, dict):
            return

        topology = self._topology_provider()
        bridge = SmartIORuntimeBridge(
            runtime_session=self._runtime_workspace_service.ensure_session(topology),
            default_overlap_length=int(self._profile.default_overlap_length),
        )
        try:
            command = bridge.command_from_envelope(event_type, payload)
            command_result = self._runtime_workspace_service.submit_command(
                topology=topology,
                kind=str(command.get("kind", "")).strip(),
                payload=dict(command.get("payload", {})),
                source_id=str(command.get("source_id", "")).strip() or "smartio-web",
                command_id=str(command.get("command_id", "")).strip() or None,
                command_ts=float(event.get("ts", command.get("ts", 0.0)) or 0.0),
            )
        except SmartIOProtocolError as exc:
            self._send_command_result(
                {
                    "command_id": str(payload.get("command_id", payload.get("msg_id", ""))).strip(),
                    "source_id": str(payload.get("source_id", "")).strip() or "smartio-web",
                    "status": "rejected",
                    "message": f"{exc.code}: {exc}",
                    "stream_seq": self._runtime_workspace_service.runtime_health().stream_seq,
                }
            )
            self.smartio_error.emit(f"{exc.code}: {exc}")
            return
        except Exception as exc:
            self._send_command_result(
                {
                    "command_id": str(payload.get("command_id", payload.get("msg_id", ""))).strip(),
                    "source_id": str(payload.get("source_id", "")).strip() or "smartio-web",
                    "status": "rejected",
                    "message": str(exc),
                    "stream_seq": self._runtime_workspace_service.runtime_health().stream_seq,
                }
            )
            self.smartio_error.emit(str(exc))
            return

        self._last_command_result_at = time.time()
        self._send_command_result(command_result.to_transport_payload())
        if command_result.status == "applied":
            changed_sections = []
            if command_result.event is not None:
                changed_sections = list(
                    command_result.event.payload.get("result", {}).get("changed_sections", [])
                )
            self.runtime_state_changed.emit(
                {
                    "sections": changed_sections,
                    "view_state": self._runtime_workspace_service.runtime_view_state(),
                }
            )
            self.publish_runtime_snapshot()
        self._emit_runtime_health()

    def _send_hello(self) -> None:
        if self._smartio_client is None or not self._smartio_client.is_connected:
            return
        try:
            envelope = self._smartio_client.build_envelope("hello", {"role": "cbi"})
            self._smartio_client.send_event(envelope)
        except Exception as exc:
            self.smartio_error.emit(f"hello send failed: {exc}")

    def _send_command_result(self, payload: dict[str, Any]) -> None:
        if self._smartio_client is None or not self._smartio_client.is_connected:
            return
        try:
            envelope = self._smartio_client.build_envelope("command_result", payload)
            self._smartio_client.send_event(envelope)
        except Exception as exc:
            self.smartio_error.emit(f"command_result send failed: {exc}")

    def _emit_runtime_health(self) -> None:
        self.runtime_health_changed.emit(dict(self.runtime_health))

    def _set_status(self, status: str) -> None:
        self._smartio_status_token = str(status).strip() or "disconnected"
        self.smartio_status_changed.emit(self._smartio_status_token)
