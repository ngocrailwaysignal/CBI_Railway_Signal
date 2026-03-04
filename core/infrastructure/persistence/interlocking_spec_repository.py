"""File-based repository for compiled interlocking specifications."""

from __future__ import annotations

import json
from pathlib import Path

from core.compiler.spec_models import InterlockingSpec


class InterlockingSpecRepository:
    """Persist and restore InterlockingSpec to/from JSON files."""

    def save(self, spec: InterlockingSpec, path: str | Path) -> None:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(spec.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def load(self, path: str | Path) -> InterlockingSpec:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid interlocking spec payload")
        return InterlockingSpec.from_dict(payload)

