"""Persistence adapter for runtime snapshot state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RuntimeSnapshotRepository:
    """Save/load runtime state snapshots independently from layout/spec artifacts."""

    def save(self, snapshot: dict[str, Any], path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")

    def load(self, path: str | Path) -> dict[str, Any]:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid runtime snapshot payload")
        return payload

