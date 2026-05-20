"""Runtime realtime journal, command, and recovery primitives."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path
from typing import Any


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "value"):
        token = value.value
        if isinstance(token, (str, int, float, bool)) or token is None:
            return token
    if isinstance(value, Path):
        return str(value)
    return value


@dataclass(slots=True, frozen=True)
class RuntimeCommand:
    command_id: str
    source_id: str
    kind: str
    payload: dict[str, Any]
    ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "source_id": self.source_id,
            "kind": self.kind,
            "payload": _jsonable(self.payload),
            "ts": float(self.ts),
        }


@dataclass(slots=True, frozen=True)
class RuntimeEvent:
    event_id: str
    stream_seq: int
    kind: str
    payload: dict[str, Any]
    caused_by_command_id: str | None
    source_id: str
    command_status: str
    message: str
    topology_revision: str | None
    ts: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "stream_seq": int(self.stream_seq),
            "kind": self.kind,
            "payload": _jsonable(self.payload),
            "caused_by_command_id": self.caused_by_command_id,
            "source_id": self.source_id,
            "command_status": self.command_status,
            "message": self.message,
            "topology_revision": self.topology_revision,
            "ts": float(self.ts),
        }


@dataclass(slots=True)
class RuntimeCommandResult:
    command_id: str
    source_id: str
    status: str
    message: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    stream_seq: int = 0
    ts: float = field(default_factory=time.time)
    event: RuntimeEvent | None = None

    def to_transport_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "source_id": self.source_id,
            "status": self.status,
            "message": self.message,
            "stream_seq": int(self.stream_seq),
            "ts": float(self.ts),
        }


@dataclass(slots=True, frozen=True)
class RuntimeRestoreReport:
    restored: bool
    topology_revision: str | None
    last_stream_seq: int = 0
    replayed_events: int = 0
    degraded_reason: str | None = None


@dataclass(slots=True, frozen=True)
class RuntimeHealth:
    topology_revision: str | None
    stream_seq: int
    last_applied_command_at: float | None
    last_snapshot_at: float | None
    last_command_id: str | None
    last_command_status: str | None
    degraded_reason: str | None

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_reason)


class RuntimeJournal:
    """Append-only JSONL journal for commands, events, and snapshots."""

    def __init__(self, root_dir: str | Path) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.commands_path = self.root_dir / "runtime_commands.jsonl"
        self.events_path = self.root_dir / "runtime_events.jsonl"
        self.snapshots_path = self.root_dir / "runtime_snapshots.jsonl"

    def reset(self) -> None:
        self.root_dir.mkdir(parents=True, exist_ok=True)
        for path in (self.commands_path, self.events_path, self.snapshots_path):
            if path.exists():
                path.unlink()

    def append_command(self, command: RuntimeCommand) -> None:
        self._append_jsonl(self.commands_path, command.to_dict())

    def append_event(self, event: RuntimeEvent) -> None:
        self._append_jsonl(self.events_path, event.to_dict())

    def append_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._append_jsonl(self.snapshots_path, _jsonable(snapshot))

    def load_latest_snapshot(self, *, truncate_invalid_tail: bool = True) -> dict[str, Any] | None:
        records = self._read_jsonl(self.snapshots_path, truncate_invalid_tail=truncate_invalid_tail)
        return records[-1] if records else None

    def load_events_after(
        self,
        stream_seq: int,
        *,
        truncate_invalid_tail: bool = True,
    ) -> list[dict[str, Any]]:
        records = self._read_jsonl(self.events_path, truncate_invalid_tail=truncate_invalid_tail)
        return [item for item in records if int(item.get("stream_seq", 0) or 0) > int(stream_seq)]

    def load_processed_command_results(
        self,
        *,
        limit: int = 512,
        truncate_invalid_tail: bool = True,
    ) -> list[RuntimeCommandResult]:
        records = self._read_jsonl(self.events_path, truncate_invalid_tail=truncate_invalid_tail)
        results: list[RuntimeCommandResult] = []
        for item in reversed(records):
            command_id = str(item.get("caused_by_command_id", "")).strip()
            source_id = str(item.get("source_id", "")).strip()
            status = str(item.get("command_status", "")).strip()
            if not command_id or not source_id or not status:
                continue
            results.append(
                RuntimeCommandResult(
                    command_id=command_id,
                    source_id=source_id,
                    status=status,
                    message=str(item.get("message", "")).strip(),
                    payload={},
                    stream_seq=int(item.get("stream_seq", 0) or 0),
                    ts=float(item.get("ts", 0.0) or 0.0),
                )
            )
            if len(results) >= max(1, int(limit)):
                break
        results.reverse()
        return results

    def _append_jsonl(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False))
            handle.write("\n")

    def _read_jsonl(self, path: Path, *, truncate_invalid_tail: bool) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        valid_records: list[dict[str, Any]] = []
        valid_lines: list[str] = []
        invalid_tail = False
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError:
                    invalid_tail = True
                    break
                if not isinstance(payload, dict):
                    invalid_tail = True
                    break
                valid_records.append(payload)
                valid_lines.append(stripped)
        if invalid_tail and truncate_invalid_tail:
            with path.open("w", encoding="utf-8") as handle:
                for line in valid_lines:
                    handle.write(line)
                    handle.write("\n")
        return valid_records


class RuntimeRecoveryService:
    """Restore runtime state from latest checkpoint plus event replay."""

    def __init__(self, journal: RuntimeJournal) -> None:
        self._journal = journal

    def restore(
        self,
        *,
        simulation: Any,
        topology_revision: str,
        replay_command: Callable[[RuntimeCommand], None],
    ) -> RuntimeRestoreReport:
        latest_snapshot = self._journal.load_latest_snapshot(truncate_invalid_tail=True)
        if latest_snapshot is None:
            return RuntimeRestoreReport(restored=False, topology_revision=topology_revision)

        snapshot_revision = str(latest_snapshot.get("topology_revision") or "").strip() or None
        if snapshot_revision and snapshot_revision != topology_revision:
            return RuntimeRestoreReport(
                restored=False,
                topology_revision=topology_revision,
                last_stream_seq=int(latest_snapshot.get("stream_seq", 0) or 0),
                degraded_reason=(
                    "REVISION_MISMATCH: "
                    f"checkpoint {snapshot_revision} != current {topology_revision}"
                ),
            )

        try:
            simulation.hydrate_snapshot(snapshot=latest_snapshot, strict_route_ids=True)
            replayed_events = 0
            last_stream_seq = int(latest_snapshot.get("stream_seq", 0) or 0)
            for event_item in self._journal.load_events_after(
                last_stream_seq, truncate_invalid_tail=True
            ):
                last_stream_seq = max(last_stream_seq, int(event_item.get("stream_seq", 0) or 0))
                if str(event_item.get("command_status", "")).strip().lower() != "applied":
                    continue
                command_payload = event_item.get("payload", {}).get("command")
                if not isinstance(command_payload, dict):
                    continue
                replay_command(
                    RuntimeCommand(
                        command_id=str(command_payload.get("command_id", "")).strip(),
                        source_id=str(command_payload.get("source_id", "")).strip() or "replay",
                        kind=str(command_payload.get("kind", "")).strip(),
                        payload=dict(command_payload.get("payload", {}))
                        if isinstance(command_payload.get("payload", {}), dict)
                        else {},
                        ts=float(command_payload.get("ts", event_item.get("ts", 0.0)) or 0.0),
                    )
                )
                replayed_events += 1
        except Exception as exc:
            return RuntimeRestoreReport(
                restored=False,
                topology_revision=topology_revision,
                last_stream_seq=int(latest_snapshot.get("stream_seq", 0) or 0),
                degraded_reason=f"RECOVERY_FAILED: {exc}",
            )

        return RuntimeRestoreReport(
            restored=True,
            topology_revision=topology_revision,
            last_stream_seq=last_stream_seq,
            replayed_events=replayed_events,
            degraded_reason=None,
        )
