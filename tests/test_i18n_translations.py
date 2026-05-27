from __future__ import annotations

import ast
import re
from pathlib import Path

from core.domain.model.elements import SignalAspect
from ui.i18n import TRANSLATIONS

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = REPO_ROOT / "ui"
WEBCLIENT_I18N_PATH = REPO_ROOT / "webclient" / "i18n.js"

VI_EQUALS_EN_ALLOWLIST = {
    "field.id",
    "runtime.smartio.status",
    "unit.seconds_suffix",
}

CORRUPTION_MARKERS = (
    "\ufffd",
    "??",
    "kh?ng",
    "Kh?ng",
    "l?i",
    "L?i",
)


def _literal_translation_keys(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    keys: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        if not isinstance(node.args[0], ast.Constant) or not isinstance(node.args[0].value, str):
            continue
        func = node.func
        if (
            isinstance(func, ast.Name)
            and func.id == "_t"
            or isinstance(func, ast.Attribute)
            and func.attr == "_t"
        ):
            keys.add(node.args[0].value)
    return keys


def _webclient_language_block(language: str) -> str:
    text = WEBCLIENT_I18N_PATH.read_text(encoding="utf-8")
    match = re.search(rf"\n  {language}: \{{(?P<body>.*?)\n  \}},", text, flags=re.DOTALL)
    assert match is not None
    return match.group("body")


def _webclient_keys(language: str) -> set[str]:
    block = _webclient_language_block(language)
    return set(re.findall(r'^\s+"([^"]+)":', block, flags=re.MULTILINE))


def test_vietnamese_translations_are_not_left_as_english() -> None:
    untranslated = {
        key
        for key, translations in TRANSLATIONS.items()
        if translations.get("vi") == translations.get("en") and key not in VI_EQUALS_EN_ALLOWLIST
    }

    assert untranslated == set()


def test_vietnamese_translations_have_no_known_corruption_markers() -> None:
    corrupted = {
        key: translations["vi"]
        for key, translations in TRANSLATIONS.items()
        if any(marker in translations.get("vi", "") for marker in CORRUPTION_MARKERS)
    }

    assert corrupted == {}


def test_literal_pyqt_translation_keys_exist() -> None:
    used_keys: set[str] = set()
    for path in UI_ROOT.rglob("*.py"):
        used_keys.update(_literal_translation_keys(path))

    missing = used_keys - set(TRANSLATIONS)

    assert missing == set()


def test_all_signal_aspects_have_vietnamese_display_labels() -> None:
    missing_or_raw = {
        aspect.value: TRANSLATIONS.get(f"signal_aspect.{aspect.value.lower()}", {})
        for aspect in set(SignalAspect)
        if TRANSLATIONS.get(f"signal_aspect.{aspect.value.lower()}", {}).get("vi")
        == aspect.value
        or f"signal_aspect.{aspect.value.lower()}" not in TRANSLATIONS
    }

    assert missing_or_raw == {}


def test_webclient_translation_tables_are_complete() -> None:
    assert _webclient_keys("vi") == _webclient_keys("en")


def test_webclient_vietnamese_translations_have_no_known_corruption_markers() -> None:
    vi_block = _webclient_language_block("vi")
    found_markers = [marker for marker in CORRUPTION_MARKERS if marker in vi_block]

    assert found_markers == []
