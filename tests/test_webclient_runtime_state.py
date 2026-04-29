from __future__ import annotations

import json
import os
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from infrastructure.snapshot_store import WEBCLIENT_RUNTIME_STATE_FILENAME
from runtime import GenericApplicationProfile, GenericApplicationService, RuntimeWorkspaceService
from runtime.application import AppMode
from webclient import serve


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_LAYOUT_PATH = REPO_ROOT / "data" / "station_layout" / "test.json"


def build_services() -> tuple[GenericApplicationService, RuntimeWorkspaceService]:
    profile = GenericApplicationProfile(runtime_journal_dir=tempfile.mkdtemp(prefix="cbi-webclient-"))
    application_service = GenericApplicationService(profile=profile)
    runtime_workspace = RuntimeWorkspaceService(profile=profile, kernel=application_service.kernel)
    return application_service, runtime_workspace


@contextmanager
def running_server(*, runtime_state_path: Path, layout_path: Path | None = None):
    server = serve.create_server(
        host="127.0.0.1",
        port=0,
        root=REPO_ROOT / "webclient",
        runtime_state_path=runtime_state_path,
        layout_path=layout_path or TEST_LAYOUT_PATH,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_build_webclient_runtime_state_contains_layout_and_runtime_snapshot() -> None:
    application_service, runtime_workspace = build_services()
    topology = application_service.load_topology(TEST_LAYOUT_PATH, load_runtime_state=False, load_occupancy=True)
    runtime_workspace.ensure_session(topology)

    payload = application_service.build_webclient_runtime_state(
        topology=topology,
        workspace_mode=AppMode.RUNTIME,
        runtime_snapshot=runtime_workspace.build_runtime_snapshot(),
        generated_at=123.0,
    )

    assert payload["workspace_mode"] == "runtime"
    assert payload["generated_at"] == 123.0
    assert payload["layout"]["signals"]
    assert payload["signal_state"]
    assert isinstance(payload["topology_revision"], str)
    assert payload["tick"] == 0


def test_build_webclient_runtime_state_supports_layout_without_runtime_session() -> None:
    application_service, _runtime_workspace = build_services()
    topology = application_service.load_topology(TEST_LAYOUT_PATH, load_runtime_state=False, load_occupancy=True)

    payload = application_service.build_webclient_runtime_state(
        topology=topology,
        workspace_mode=AppMode.RUNTIME,
        runtime_snapshot=None,
        generated_at=456.0,
    )

    assert payload["workspace_mode"] == "runtime"
    assert payload["generated_at"] == 456.0
    assert payload["layout"]["sections"]
    assert payload["routes"] == []
    assert payload["trains"] == []
    assert isinstance(payload["topology_revision"], str)


def test_save_webclient_runtime_state_uses_atomic_replace(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    application_service, _runtime_workspace = build_services()
    topology = application_service.load_topology(TEST_LAYOUT_PATH, load_runtime_state=False, load_occupancy=True)
    payload = application_service.build_webclient_runtime_state(
        topology=topology,
        workspace_mode=AppMode.RUNTIME,
        generated_at=789.0,
    )
    target = tmp_path / WEBCLIENT_RUNTIME_STATE_FILENAME
    replace_calls: list[tuple[Path, Path]] = []
    original_replace = os.replace

    def replace_spy(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        replace_calls.append((Path(src), Path(dst)))
        original_replace(src, dst)

    monkeypatch.setattr(os, "replace", replace_spy)

    application_service.save_webclient_runtime_state(payload, target)

    assert replace_calls
    assert replace_calls[0][1] == target
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8")) == payload
    assert not list(tmp_path.glob("*.tmp"))


def test_runtime_state_endpoint_returns_200_with_json(tmp_path: Path) -> None:
    payload = {"workspace_mode": "runtime", "stream_seq": 7, "layout": {"signals": []}}
    runtime_state_path = tmp_path / WEBCLIENT_RUNTIME_STATE_FILENAME
    runtime_state_path.write_text(json.dumps(payload), encoding="utf-8")

    with running_server(runtime_state_path=runtime_state_path) as base_url:
        with urllib.request.urlopen(f"{base_url}/api/runtime-state") as response:
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
            assert json.loads(response.read().decode("utf-8")) == payload


def test_runtime_state_endpoint_returns_204_when_file_missing(tmp_path: Path) -> None:
    runtime_state_path = tmp_path / WEBCLIENT_RUNTIME_STATE_FILENAME

    with running_server(runtime_state_path=runtime_state_path) as base_url:
        with urllib.request.urlopen(f"{base_url}/api/runtime-state") as response:
            assert response.status == 204
            assert response.headers["Cache-Control"] == "no-store"
            assert response.read() == b""


def test_runtime_state_endpoint_returns_503_for_invalid_json(tmp_path: Path) -> None:
    runtime_state_path = tmp_path / WEBCLIENT_RUNTIME_STATE_FILENAME
    runtime_state_path.write_text("{invalid json", encoding="utf-8")

    with running_server(runtime_state_path=runtime_state_path) as base_url:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(f"{base_url}/api/runtime-state")

    assert excinfo.value.code == 503
    assert excinfo.value.headers["Cache-Control"] == "no-store"
    error_payload = json.loads(excinfo.value.read().decode("utf-8"))
    assert error_payload["error"] == "runtime_state_unavailable"


def test_dispatcher_pretty_routes_return_html(tmp_path: Path) -> None:
    runtime_state_path = tmp_path / WEBCLIENT_RUNTIME_STATE_FILENAME
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(TEST_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    with running_server(runtime_state_path=runtime_state_path, layout_path=layout_path) as base_url:
        with urllib.request.urlopen(f"{base_url}/dispatcher") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "Dispatcher Viewer" in body

        with urllib.request.urlopen(f"{base_url}/dispatcher/editor") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "Dispatcher Editor" in body


def test_dispatcher_static_assets_are_served_with_no_store(tmp_path: Path) -> None:
    runtime_state_path = tmp_path / WEBCLIENT_RUNTIME_STATE_FILENAME
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(TEST_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    with running_server(runtime_state_path=runtime_state_path, layout_path=layout_path) as base_url:
        with urllib.request.urlopen(f"{base_url}/dispatcher") as response:
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"

        with urllib.request.urlopen(f"{base_url}/viewer.js") as response:
            assert response.status == 200
            assert response.headers["Cache-Control"] == "no-store"
