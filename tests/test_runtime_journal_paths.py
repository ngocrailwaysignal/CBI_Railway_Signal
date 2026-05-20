from __future__ import annotations

from pathlib import Path

from runtime.journal_paths import (
    runtime_journal_dir,
    webclient_runtime_command_path,
    webclient_runtime_command_result_path,
    webclient_runtime_state_path,
)


def test_runtime_journal_dir_resolves_relative_to_repo_root() -> None:
    repo_root = Path("repo")

    assert runtime_journal_dir(repo_root) == repo_root / "data" / "runtime_journal"
    assert runtime_journal_dir(repo_root, "var/journal") == repo_root / "var" / "journal"


def test_runtime_journal_dir_preserves_absolute_path(tmp_path: Path) -> None:
    journal_dir = tmp_path / "journal"

    assert runtime_journal_dir(Path("repo"), journal_dir) == journal_dir


def test_webclient_runtime_paths_share_resolved_journal_dir() -> None:
    repo_root = Path("repo")

    assert (
        webclient_runtime_state_path(repo_root)
        .as_posix()
        .endswith("data/runtime_journal/webclient_runtime_state.json")
    )
    assert (
        webclient_runtime_command_path(repo_root)
        .as_posix()
        .endswith("data/runtime_journal/webclient_commands.jsonl")
    )
    assert (
        webclient_runtime_command_result_path(repo_root)
        .as_posix()
        .endswith("data/runtime_journal/webclient_command_results.jsonl")
    )
