from __future__ import annotations

import json
import tempfile
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

import pytest

from webclient import serve
from webclient.dispatcher_layout import build_bindable_catalog, normalize_dispatcher_view


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_LAYOUT_PATH = REPO_ROOT / "data" / "station_layout" / "test.json"


@contextmanager
def running_server(*, layout_path: Path):
    runtime_state_path = Path(tempfile.mkdtemp(prefix="dispatcher-layout-api-")) / "runtime_state.json"
    server = serve.create_server(
        host="127.0.0.1",
        port=0,
        root=REPO_ROOT / "webclient",
        runtime_state_path=runtime_state_path,
        layout_path=layout_path,
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


def test_normalize_dispatcher_view_migrates_legacy_segments() -> None:
    view = normalize_dispatcher_view(
        {
            "segments": [
                {
                    "id": "legacy-main",
                    "kind": "main",
                    "points": [{"x": 0, "y": 0}, {"x": 160, "y": 0}],
                    "state_source_ids": ["S1"],
                }
            ],
            "signal_symbols": [{"signal_id": "ENTRY_RIGHT_A", "x": 40, "y": 0, "direction": "RIGHT"}],
        },
        bindable_catalog={
            "sections": ["S1"],
            "points": [],
            "signals": ["ENTRY_RIGHT_A"],
        },
    )

    assert view["elements"]
    assert any(element["kind"] == "track_section" for element in view["elements"])
    assert any(element["kind"] == "signal" for element in view["elements"])


def test_get_dispatcher_layout_returns_normalized_view_and_bindable_ids(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_document = json.loads(TEST_LAYOUT_PATH.read_text(encoding="utf-8"))
    layout_document["dispatcher_view"] = {
        "canvas": {"width": 1400, "height": 720, "grid_size": 16, "snap_enabled": True},
        "elements": [
            {
                "id": "section-a",
                "kind": "track_section",
                "position": {"x": 100, "y": 120},
                "rotation": 0,
                "geometry": {"points": [{"x": 0, "y": 0}, {"x": 220, "y": 0}]},
                "style": {"variant": "main"},
                "z_index": 0,
                "binding": {"cbi_type": "section", "cbi_id": "S1"},
            }
        ],
    }
    layout_path.write_text(json.dumps(layout_document), encoding="utf-8")

    with running_server(layout_path=layout_path) as base_url:
        with urllib.request.urlopen(f"{base_url}/api/dispatcher-layout") as response:
            payload = json.loads(response.read().decode("utf-8"))

    assert payload["dispatcher_view"]["canvas"]["width"] == 1400
    assert payload["bindable"] == build_bindable_catalog(layout_document)
    assert payload["layout_name"] == "layout"


def test_put_dispatcher_layout_persists_view(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(TEST_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    payload = {
        "dispatcher_view": {
            "canvas": {"width": 1600, "height": 800, "grid_size": 20, "snap_enabled": True},
            "elements": [
                {
                    "id": "sig-a",
                    "kind": "signal",
                    "position": {"x": 300, "y": 180},
                    "rotation": 0,
                    "geometry": {"mast": 18, "arm": 14, "head_radius": 5.5, "label_offset": 20},
                    "style": {},
                    "z_index": 0,
                    "binding": {"cbi_type": "signal", "cbi_id": "ENTRY_RIGHT_A"},
                }
            ],
        }
    }

    with running_server(layout_path=layout_path) as base_url:
        request = urllib.request.Request(
            f"{base_url}/api/dispatcher-layout",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(request) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

    saved_document = json.loads(layout_path.read_text(encoding="utf-8"))
    assert response_payload["dispatcher_view"]["elements"][0]["binding"]["cbi_id"] == "ENTRY_RIGHT_A"
    assert saved_document["dispatcher_view"]["elements"][0]["binding"]["cbi_id"] == "ENTRY_RIGHT_A"


def test_put_dispatcher_layout_accepts_empty_elements_and_persists_clear(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(TEST_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    payload = {
        "dispatcher_view": {
            "canvas": {"width": 1600, "height": 800, "grid_size": 20, "snap_enabled": True},
            "elements": [],
        }
    }

    with running_server(layout_path=layout_path) as base_url:
        request = urllib.request.Request(
            f"{base_url}/api/dispatcher-layout",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(request) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

    saved_document = json.loads(layout_path.read_text(encoding="utf-8"))
    assert response_payload["dispatcher_view"]["elements"] == []
    assert saved_document["dispatcher_view"]["elements"] == []


def test_put_dispatcher_layout_accepts_unbound_bindable_element(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(TEST_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    payload = {
        "dispatcher_view": {
            "canvas": {"width": 1600, "height": 800, "grid_size": 20, "snap_enabled": True},
            "elements": [
                {
                    "id": "sig-a",
                    "kind": "signal",
                    "position": {"x": 300, "y": 180},
                    "rotation": 0,
                    "geometry": {"mast": 18, "arm": 14, "head_radius": 5.5, "label_offset": 20},
                    "style": {},
                    "z_index": 0,
                    "binding": None,
                }
            ],
        }
    }

    with running_server(layout_path=layout_path) as base_url:
        request = urllib.request.Request(
            f"{base_url}/api/dispatcher-layout",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(request) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

    saved_document = json.loads(layout_path.read_text(encoding="utf-8"))
    assert response_payload["dispatcher_view"]["elements"][0]["binding"] is None
    assert saved_document["dispatcher_view"]["elements"][0]["binding"] is None


def test_put_dispatcher_layout_accepts_duplicate_signal_binding(tmp_path: Path) -> None:
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(TEST_LAYOUT_PATH.read_text(encoding="utf-8"), encoding="utf-8")
    payload = {
        "dispatcher_view": {
            "canvas": {"width": 1600, "height": 800, "grid_size": 20, "snap_enabled": True},
            "elements": [
                {
                    "id": "sig-a",
                    "kind": "signal",
                    "position": {"x": 100, "y": 100},
                    "rotation": 0,
                    "geometry": {"mast": 18, "arm": 14, "head_radius": 5.5, "label_offset": 20},
                    "style": {},
                    "z_index": 0,
                    "binding": {"cbi_type": "signal", "cbi_id": "ENTRY_RIGHT_A"},
                },
                {
                    "id": "sig-b",
                    "kind": "signal",
                    "position": {"x": 200, "y": 100},
                    "rotation": 0,
                    "geometry": {"mast": 18, "arm": 14, "head_radius": 5.5, "label_offset": 20},
                    "style": {},
                    "z_index": 1,
                    "binding": {"cbi_type": "signal", "cbi_id": "ENTRY_RIGHT_A"},
                },
            ],
        }
    }

    with running_server(layout_path=layout_path) as base_url:
        request = urllib.request.Request(
            f"{base_url}/api/dispatcher-layout",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="PUT",
        )
        with urllib.request.urlopen(request) as response:
            response_payload = json.loads(response.read().decode("utf-8"))

    saved_document = json.loads(layout_path.read_text(encoding="utf-8"))
    assert response_payload["dispatcher_view"]["elements"][0]["binding"]["cbi_id"] == "ENTRY_RIGHT_A"
    assert response_payload["dispatcher_view"]["elements"][1]["binding"]["cbi_id"] == "ENTRY_RIGHT_A"
    assert saved_document["dispatcher_view"]["elements"][0]["binding"]["cbi_id"] == "ENTRY_RIGHT_A"
    assert saved_document["dispatcher_view"]["elements"][1]["binding"]["cbi_id"] == "ENTRY_RIGHT_A"
