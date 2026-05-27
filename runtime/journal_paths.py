"""Path helpers for generated runtime journal artifacts."""

from __future__ import annotations

from pathlib import Path

from config import DEFAULT_APP_CONFIG
from infrastructure.snapshot_store import (
    WEBCLIENT_RUNTIME_COMMAND_RESULTS_FILENAME,
    WEBCLIENT_RUNTIME_COMMANDS_FILENAME,
    WEBCLIENT_RUNTIME_STATE_FILENAME,
)

DEFAULT_RUNTIME_JOURNAL_DIR = DEFAULT_APP_CONFIG.paths.runtime_journal_dir


def runtime_journal_dir(
    repo_root: Path, journal_dir: str | Path = DEFAULT_RUNTIME_JOURNAL_DIR
) -> Path:
    """Resolve a runtime journal directory relative to the repository root."""
    resolved = Path(journal_dir)
    if resolved.is_absolute():
        return resolved
    return repo_root / resolved


def webclient_runtime_state_path(
    repo_root: Path, journal_dir: str | Path = DEFAULT_RUNTIME_JOURNAL_DIR
) -> Path:
    return runtime_journal_dir(repo_root, journal_dir) / WEBCLIENT_RUNTIME_STATE_FILENAME


def webclient_runtime_command_path(
    repo_root: Path, journal_dir: str | Path = DEFAULT_RUNTIME_JOURNAL_DIR
) -> Path:
    return runtime_journal_dir(repo_root, journal_dir) / WEBCLIENT_RUNTIME_COMMANDS_FILENAME


def webclient_runtime_command_result_path(
    repo_root: Path, journal_dir: str | Path = DEFAULT_RUNTIME_JOURNAL_DIR
) -> Path:
    return runtime_journal_dir(repo_root, journal_dir) / WEBCLIENT_RUNTIME_COMMAND_RESULTS_FILENAME
