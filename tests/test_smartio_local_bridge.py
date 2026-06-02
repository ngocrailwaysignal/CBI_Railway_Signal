from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("aiohttp")


def _load_server_module() -> Any:
    module_path = Path(__file__).resolve().parent / "CBI_SmartIO" / "server.py"
    spec = importlib.util.spec_from_file_location("smartio_local_server", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load SmartIO local server module: {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SERVER = _load_server_module()


class FakeSocket:
    closed = False

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_str(self, message: str) -> None:
        self.sent.append(json.loads(message))


def _run(coro: Any) -> None:
    asyncio.run(coro)


def _simulator(tmp_path: Path) -> Any:
    layout_path = tmp_path / "sample_layout.json"
    layout_path.write_text(
        json.dumps({"sections": [], "points": [], "signals": []}),
        encoding="utf-8",
    )
    return SERVER.SmartIOWebSimulator(layout_path=layout_path)


def _state_update_message(msg_id: str) -> str:
    return json.dumps(
        {
            "type": "state_update",
            "msg_id": msg_id,
            "payload": {"sections": [{"id": "S1", "occupied": True}]},
            "ts": 0.0,
        }
    )


def _transport_log_count(tmp_path: Path) -> int:
    log_path = tmp_path / "transport_commands.jsonl"
    if not log_path.exists():
        return 0
    return len([line for line in log_path.read_text(encoding="utf-8").splitlines() if line])


def test_duplicate_state_update_pending_replays_received_without_reforwarding(
    tmp_path: Path,
) -> None:
    simulator = _simulator(tmp_path)
    web_socket = FakeSocket()
    cbi_socket = FakeSocket()
    simulator._cbi_clients.add(cbi_socket)
    simulator._socket_source_ids[web_socket] = "web-test"

    _run(simulator._on_text_message(web_socket, _state_update_message("su-1")))
    _run(simulator._on_text_message(web_socket, _state_update_message("su-1")))

    cbi_commands = [item for item in cbi_socket.sent if item.get("type") == "command"]
    duplicate_results = [
        item
        for item in web_socket.sent
        if item.get("type") == "command_result"
        and item.get("payload", {}).get("command_id") == "su-1"
    ]
    assert len(cbi_commands) == 1
    assert duplicate_results[-1]["payload"]["status"] == "received"
    assert _transport_log_count(tmp_path) == 1


def test_duplicate_state_update_after_cbi_result_replays_cached_terminal_result(
    tmp_path: Path,
) -> None:
    simulator = _simulator(tmp_path)
    web_socket = FakeSocket()
    cbi_socket = FakeSocket()
    simulator._cbi_clients.add(cbi_socket)
    simulator._socket_source_ids[web_socket] = "web-test"

    _run(simulator._on_text_message(web_socket, _state_update_message("su-2")))
    _run(
        simulator._handle_command_result(
            {
                "command_id": "su-2",
                "source_id": "web-test",
                "status": "applied",
                "message": "",
                "stream_seq": 7,
            }
        )
    )
    _run(simulator._on_text_message(web_socket, _state_update_message("su-2")))

    cbi_commands = [item for item in cbi_socket.sent if item.get("type") == "command"]
    applied_results = [
        item
        for item in web_socket.sent
        if item.get("type") == "command_result"
        and item.get("payload", {}).get("command_id") == "su-2"
    ]
    assert len(cbi_commands) == 1
    assert applied_results[-1]["payload"]["status"] == "applied"
    assert applied_results[-1]["payload"]["stream_seq"] == 7
    assert _transport_log_count(tmp_path) == 1
