"""Persistence adapter for webclient runtime-state payloads."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


WEBCLIENT_RUNTIME_STATE_FILENAME = "webclient_runtime_state.json"
WEBCLIENT_RUNTIME_COMMANDS_FILENAME = "webclient_commands.jsonl"
WEBCLIENT_RUNTIME_COMMAND_RESULTS_FILENAME = "webclient_command_results.jsonl"


class WebclientRuntimeStateRepository:
    """Save/load the aggregated runtime-state file consumed by the webclient."""

    def save(self, payload: dict[str, Any], path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(prefix=f"{target.stem}-", suffix=".tmp", dir=str(target.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, target)
        except Exception:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def load(self, path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid webclient runtime-state payload")
        return payload
