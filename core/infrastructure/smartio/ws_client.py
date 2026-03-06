"""Qt WebSocket adapter for Smart IO integration."""

from __future__ import annotations

import json
import time
from typing import Any

from PyQt6.QtCore import QObject, QTimer, QUrl, pyqtSignal
from PyQt6.QtWebSockets import QWebSocket


class SmartIOWebSocketClient(QObject):
    """WebSocket client with event validation and reconnect backoff."""

    event_received = pyqtSignal(dict)
    status_changed = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(
        self,
        ws_url: str,
        *,
        reconnect_enabled: bool = True,
        reconnect_max_seconds: float = 30.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._url = str(ws_url).strip()
        self._reconnect_enabled = bool(reconnect_enabled)
        self._reconnect_max_seconds = max(1.0, float(reconnect_max_seconds))
        self._manual_disconnect = False
        self._connected = False
        self._connecting = False
        self._backoff_seconds = 1.0

        self._socket = QWebSocket()
        self._socket.connected.connect(self._on_connected)
        self._socket.disconnected.connect(self._on_disconnected)
        self._socket.textMessageReceived.connect(self._on_text_message_received)
        self._socket.errorOccurred.connect(self._on_error)

        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._reconnect_tick)

    @property
    def is_connected(self) -> bool:
        """Return True when socket is connected."""
        return self._connected

    def connect(self) -> None:
        """Open WebSocket connection."""
        if not self._url:
            self._emit_error("Smart IO URL is empty")
            return
        if self._connected or self._connecting:
            return
        self._manual_disconnect = False
        self._connecting = True
        self.status_changed.emit("connecting")
        self._socket.open(QUrl(self._url))

    def disconnect(self) -> None:
        """Close connection and stop reconnect attempts."""
        self._manual_disconnect = True
        self._connecting = False
        self._reconnect_timer.stop()
        self._socket.close()
        self._connected = False
        self.status_changed.emit("disconnected")

    def send_event(self, event: dict[str, Any]) -> None:
        """Validate and send one Smart IO envelope."""
        validated = self.validate_envelope(event)
        if not self._connected:
            raise RuntimeError("Smart IO WebSocket is not connected")
        self._socket.sendTextMessage(json.dumps(validated, ensure_ascii=False))

    @staticmethod
    def validate_envelope(event: dict[str, Any]) -> dict[str, Any]:
        """Validate one event envelope and return normalized payload."""
        if not isinstance(event, dict):
            raise ValueError("Smart IO event must be a JSON object")
        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(event_type, str) or not event_type.strip():
            raise ValueError("Smart IO event.type must be a non-empty string")
        if not isinstance(payload, dict):
            raise ValueError("Smart IO event.payload must be an object")
        timestamp = event.get("ts")
        if timestamp is None:
            raise ValueError("Smart IO event.ts is required")
        return {
            "type": event_type.strip(),
            "payload": payload,
            "ts": timestamp,
        }

    @classmethod
    def parse_text_envelope(cls, raw_text: str) -> dict[str, Any]:
        """Parse one incoming text message and validate envelope schema."""
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid Smart IO JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("Smart IO JSON must be an object")
        return cls.validate_envelope(payload)

    def _on_connected(self) -> None:
        self._connected = True
        self._connecting = False
        self._backoff_seconds = 1.0
        self.status_changed.emit("connected")

    def _on_disconnected(self) -> None:
        was_connected = self._connected or self._connecting
        self._connected = False
        self._connecting = False
        if not was_connected:
            return
        self.status_changed.emit("disconnected")
        if self._manual_disconnect:
            return
        if not self._reconnect_enabled:
            return
        self._schedule_reconnect()

    def _on_text_message_received(self, message: str) -> None:
        try:
            envelope = self.parse_text_envelope(message)
        except ValueError as exc:
            self._emit_error(str(exc))
            return
        self.event_received.emit(envelope)

    def _on_error(self, _error: object) -> None:
        message = self._socket.errorString()
        if message:
            self._emit_error(message)

    def _schedule_reconnect(self) -> None:
        if self._reconnect_timer.isActive():
            return
        delay = min(self._backoff_seconds, self._reconnect_max_seconds)
        self._backoff_seconds = min(delay * 2.0, self._reconnect_max_seconds)
        self.status_changed.emit(f"reconnecting_in_{int(delay)}s")
        self._reconnect_timer.start(int(delay * 1000.0))

    def _reconnect_tick(self) -> None:
        if self._manual_disconnect:
            return
        self.connect()

    def _emit_error(self, message: str) -> None:
        self.error_occurred.emit(message)
        self.status_changed.emit("error")

    @staticmethod
    def build_envelope(event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Create one outgoing envelope with Unix timestamp."""
        return {
            "type": str(event_type).strip(),
            "payload": dict(payload),
            "ts": time.time(),
        }
