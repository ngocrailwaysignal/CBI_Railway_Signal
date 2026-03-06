"""Lightweight architectural dependency-direction checks."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _python_files(base: Path) -> list[Path]:
    return [p for p in base.rglob("*.py") if "__pycache__" not in p.parts]


def _violates_import_rule(path: Path, forbidden_prefixes: tuple[str, ...]) -> bool:
    text = path.read_text(encoding="utf-8")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("import ", "from ")):
            continue
        for prefix in forbidden_prefixes:
            if stripped.startswith(f"import {prefix}") or stripped.startswith(f"from {prefix}"):
                return True
    return False


def test_domain_does_not_import_ui_or_specific_application() -> None:
    domain_files = _python_files(ROOT / "core" / "domain")
    violations = [
        str(path.relative_to(ROOT))
        for path in domain_files
        if _violates_import_rule(path, ("ui", "specific_application"))
    ]
    assert violations == []


def test_infrastructure_does_not_import_ui() -> None:
    infra_files = _python_files(ROOT / "core" / "infrastructure")
    violations = [
        str(path.relative_to(ROOT))
        for path in infra_files
        if _violates_import_rule(path, ("ui",))
    ]
    assert violations == []

