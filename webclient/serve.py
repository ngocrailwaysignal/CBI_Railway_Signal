from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
repo_root_text = str(REPO_ROOT)
if repo_root_text not in sys.path:
    sys.path.insert(0, repo_root_text)

from infrastructure.snapshot_store import WEBCLIENT_RUNTIME_STATE_FILENAME
from webclient.dispatcher_layout import (
    build_bindable_catalog,
    create_empty_dispatcher_view,
    normalize_dispatcher_view,
)


def _default_runtime_state_path(root: Path) -> Path:
    return root.parent / "data" / "runtime_journal" / WEBCLIENT_RUNTIME_STATE_FILENAME


def _default_layout_path(root: Path) -> Path:
    return root.parent / "data" / "station_layout" / "main_layout.json"


def _load_json_object(path: Path, *, object_name: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{object_name} payload must be a JSON object")
    return payload


def _load_runtime_state(path: Path) -> dict:
    return _load_json_object(path, object_name="Runtime state")


def _load_layout_document(path: Path) -> dict:
    return _load_json_object(path, object_name="Layout")


def _save_layout_document(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f"{path.stem}-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _dispatcher_layout_payload(layout_document: dict) -> dict:
    bindable_catalog = build_bindable_catalog(layout_document)
    normalized_view = normalize_dispatcher_view(
        layout_document.get("dispatcher_view", {}),
        bindable_catalog=bindable_catalog,
    )
    return {
        "dispatcher_view": normalized_view,
        "bindable": bindable_catalog,
    }


def create_handler(*, root: Path, runtime_state_path: Path, layout_path: Path):
    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *handler_args, **handler_kwargs):
            super().__init__(*handler_args, directory=str(root), **handler_kwargs)

        def end_headers(self) -> None:
            if self.path.endswith((".html", ".js", ".css")) or self.path in {
                "/dispatcher",
                "/dispatcher/",
                "/dispatcher/editor",
                "/dispatcher/editor/",
                "/",
            }:
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/runtime-state":
                self._serve_runtime_state()
                return
            if parsed.path == "/api/dispatcher-layout":
                self._serve_dispatcher_layout()
                return
            if parsed.path in {"", "/", "/dispatcher", "/dispatcher/"}:
                self.path = "/dispatcher.html"
                super().do_GET()
                return
            if parsed.path in {"/dispatcher/editor", "/dispatcher/editor/"}:
                self.path = "/dispatcher-editor.html"
                super().do_GET()
                return
            super().do_GET()

        def do_PUT(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/dispatcher-layout":
                self._update_dispatcher_layout()
                return
            self.send_error(405, "Method Not Allowed")

        def _serve_runtime_state(self) -> None:
            if not runtime_state_path.exists():
                self.send_response(204)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            try:
                payload = _load_runtime_state(runtime_state_path)
            except Exception as exc:
                self._send_json(
                    503,
                    {"error": "runtime_state_unavailable", "detail": str(exc)},
                )
                return
            self._send_json(200, payload)

        def _serve_dispatcher_layout(self) -> None:
            if not layout_path.exists():
                self._send_json(
                    200,
                    {
                        "dispatcher_view": create_empty_dispatcher_view(),
                        "bindable": {"sections": [], "points": [], "signals": []},
                        "layout_path": str(layout_path),
                    },
                )
                return
            try:
                layout_document = _load_layout_document(layout_path)
                payload = _dispatcher_layout_payload(layout_document)
                payload["layout_path"] = str(layout_path)
                payload["layout_name"] = layout_path.stem
            except Exception as exc:
                self._send_json(
                    503,
                    {"error": "dispatcher_layout_unavailable", "detail": str(exc)},
                )
                return
            self._send_json(200, payload)

        def _update_dispatcher_layout(self) -> None:
            if not layout_path.exists():
                self._send_json(404, {"error": "layout_not_found", "detail": str(layout_path)})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
            except ValueError:
                content_length = 0
            if content_length <= 0:
                self._send_json(400, {"error": "invalid_request", "detail": "Missing request body"})
                return
            try:
                raw_body = self.rfile.read(content_length)
                payload = json.loads(raw_body.decode("utf-8"))
            except Exception as exc:
                self._send_json(400, {"error": "invalid_request", "detail": str(exc)})
                return
            dispatcher_view_payload = payload.get("dispatcher_view") if isinstance(payload, dict) else None
            if dispatcher_view_payload is None:
                dispatcher_view_payload = payload
            try:
                layout_document = _load_layout_document(layout_path)
                bindable_catalog = build_bindable_catalog(layout_document)
                normalized_view = normalize_dispatcher_view(
                    dispatcher_view_payload,
                    bindable_catalog=bindable_catalog,
                )
                layout_document["dispatcher_view"] = normalized_view
                _save_layout_document(layout_path, layout_document)
            except ValueError as exc:
                self._send_json(400, {"error": "validation_error", "detail": str(exc)})
                return
            except Exception as exc:
                self._send_json(500, {"error": "dispatcher_layout_save_failed", "detail": str(exc)})
                return
            self._send_json(
                200,
                {
                    "dispatcher_view": normalized_view,
                    "bindable": bindable_catalog,
                    "layout_path": str(layout_path),
                    "layout_name": layout_path.stem,
                },
            )

        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def create_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8091,
    root: Path | None = None,
    runtime_state_path: Path | None = None,
    layout_path: Path | None = None,
) -> ThreadingHTTPServer:
    root_path = (root or Path(__file__).resolve().parent).resolve()
    runtime_state = (runtime_state_path or _default_runtime_state_path(root_path)).resolve()
    layout = (layout_path or _default_layout_path(root_path)).resolve()
    handler = create_handler(root=root_path, runtime_state_path=runtime_state, layout_path=layout)
    return ThreadingHTTPServer((host, port), handler)


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the dispatcher webclient.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8091)
    parser.add_argument("--runtime-state-file", default="")
    parser.add_argument("--layout-file", default="")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    runtime_state_path = (
        Path(args.runtime_state_file).resolve()
        if str(args.runtime_state_file).strip()
        else _default_runtime_state_path(root)
    )
    layout_path = (
        Path(args.layout_file).resolve()
        if str(args.layout_file).strip()
        else _default_layout_path(root)
    )
    server = create_server(
        host=args.host,
        port=args.port,
        root=root,
        runtime_state_path=runtime_state_path,
        layout_path=layout_path,
    )
    print(f"Serving dispatcher webclient at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
