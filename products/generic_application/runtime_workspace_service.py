"""Workspace-scoped runtime orchestration facade."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from core.application.runtime_helpers import get_active_route_for_pair, has_active_routes
from core.application.serialization import build_runtime_snapshot, build_topology_revision
from core.application.use_cases import (
    CancelActiveRoutesUseCase,
    CancelRoutesResult,
    EmergencyReleaseRoutesUseCase,
    SimulationManualOverrideResult,
    SimulationManualOverrideUseCase,
    SetOrReuseRouteUseCase,
    SetRouteResult,
    StartRouteSimulationUseCase,
    StartSimulationResult,
)
from core.domain.model.route import Route
from core.domain.model.topology import RailwayTopology
from products.generic_product import GenericProductKernel
from runtime_session import RuntimeSession, RuntimeViewState, build_runtime_view_state

from .profile import GenericApplicationProfile
from .runtime_realtime import (
    RuntimeCommand,
    RuntimeCommandResult,
    RuntimeEvent,
    RuntimeHealth,
    RuntimeJournal,
    RuntimeRecoveryService,
)


class RuntimeWorkspaceService:
    """Manage one runtime session for the active workspace topology."""

    def __init__(
        self,
        profile: GenericApplicationProfile | None = None,
        kernel: GenericProductKernel | None = None,
    ) -> None:
        self.profile = profile or GenericApplicationProfile()
        self.kernel = kernel or GenericProductKernel(self.profile.to_product_rules())
        self._set_route_use_case = SetOrReuseRouteUseCase(self.kernel)
        self._cancel_routes_use_case = CancelActiveRoutesUseCase()
        self._emergency_release_use_case = EmergencyReleaseRoutesUseCase()
        self._manual_override_use_case = SimulationManualOverrideUseCase()
        self._start_simulation_use_case = StartRouteSimulationUseCase(self.kernel)
        self._session: RuntimeSession | None = None
        self._journal = RuntimeJournal(self.profile.runtime_journal_dir)
        self._recovery = RuntimeRecoveryService(self._journal)
        self._stream_seq = 0
        self._pending_runtime_events: list[RuntimeEvent] = []
        self._command_counter = 0
        self._topology_revision: str | None = None
        self._last_applied_command_at: float | None = None
        self._last_snapshot_at: float | None = None
        self._last_command_id: str | None = None
        self._last_command_status: str | None = None
        self._degraded_reason: str | None = None
        self._command_cache: dict[tuple[str, str], RuntimeCommandResult] = {}
        for cached_result in self._journal.load_processed_command_results():
            self._command_cache[(cached_result.source_id, cached_result.command_id)] = cached_result
            self._stream_seq = max(self._stream_seq, int(cached_result.stream_seq))

    @property
    def has_session(self) -> bool:
        return self._session is not None

    def clear_session(self) -> None:
        self._session = None

    def invalidate_runtime_journal(self) -> None:
        self._journal.reset()
        self._stream_seq = 0
        self._pending_runtime_events.clear()
        self._command_cache.clear()
        self._topology_revision = None
        self._last_applied_command_at = None
        self._last_snapshot_at = None
        self._last_command_id = None
        self._last_command_status = None
        self._degraded_reason = None

    def ensure_session(self, topology: RailwayTopology) -> RuntimeSession:
        if self._session is None or self._session.topology is not topology:
            self._session = RuntimeSession(topology)
            self.configure_timing(
                approach_time_lock_seconds=float(self.profile.time_lock_seconds),
                overlap_release_seconds=float(self.profile.overlap_release_seconds),
            )
            self._topology_revision = build_topology_revision(topology)
            restore_report = self._recovery.restore(
                simulation=self._session,
                topology_revision=self._topology_revision,
                replay_command=self._replay_command,
            )
            self._stream_seq = max(self._stream_seq, int(restore_report.last_stream_seq))
            self._degraded_reason = restore_report.degraded_reason
            if self._degraded_reason:
                self._session.locking_engine.force_all_signals_stop()
        return self._session

    def runtime_view_state(self) -> RuntimeViewState:
        return build_runtime_view_state(self._session)

    def runtime_health(self) -> RuntimeHealth:
        return RuntimeHealth(
            topology_revision=self._topology_revision,
            stream_seq=self._stream_seq,
            last_applied_command_at=self._last_applied_command_at,
            last_snapshot_at=self._last_snapshot_at,
            last_command_id=self._last_command_id,
            last_command_status=self._last_command_status,
            degraded_reason=self._degraded_reason,
        )

    def build_runtime_snapshot(self) -> dict[str, Any]:
        snapshot = build_runtime_snapshot(self._session)
        snapshot["stream_seq"] = int(self._stream_seq)
        snapshot["topology_revision"] = self._topology_revision
        snapshot["snapshot_version"] = 2
        return snapshot

    def checkpoint_runtime_snapshot(self) -> dict[str, Any]:
        snapshot = self.build_runtime_snapshot()
        self._journal.append_snapshot(snapshot)
        self._last_snapshot_at = time.time()
        return snapshot

    def drain_pending_runtime_events(self) -> list[dict[str, Any]]:
        pending = [event.to_dict() for event in self._pending_runtime_events]
        self._pending_runtime_events.clear()
        return pending

    def find_route(
        self,
        *,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int | None = None,
    ) -> Route:
        session = self._session if self._session is not None and self._session.topology is topology else None
        return self.kernel.find_route(
            topology=topology,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=overlap_length,
            runtime_session=session,
        )

    def configure_timing(
        self,
        *,
        approach_time_lock_seconds: float | None = None,
        overlap_release_seconds: float | None = None,
    ) -> None:
        if self._session is None:
            return
        self._session.locking_engine.configure_release_timing(
            approach_time_lock_seconds=approach_time_lock_seconds,
            overlap_release_seconds=overlap_release_seconds,
        )

    def update_time_locking(self) -> None:
        if self._session is None:
            return
        self._session.locking_engine.update_time_locking()

    def get_active_route_for_pair(self, entry_signal_id: str, exit_signal_id: str) -> Route | None:
        if self._session is None:
            return None
        return get_active_route_for_pair(self._session, entry_signal_id, exit_signal_id)

    def has_active_routes(self) -> bool:
        return self._session is not None and has_active_routes(self._session)

    def active_route_for_section(self, section_id: str) -> Route | None:
        if self._session is None:
            return None
        normalized_section = str(section_id).strip()
        for active_route in self._session.locking_engine.active_routes.values():
            if normalized_section in active_route.full_path:
                return active_route
            approach_section = (active_route.approach_locking_section or "").strip()
            if approach_section and approach_section == normalized_section:
                return active_route
        return None

    def approach_lock_details(self, route_id: str) -> tuple[str | None, float | None]:
        if self._session is None:
            return None, None
        state = self._session.locking_engine.approach_lock_state(route_id)
        if state is None:
            return None, None
        remaining = self._session.locking_engine.approach_locking.remaining_time_lock(route_id)
        return state.value, remaining

    def submit_command(
        self,
        *,
        topology: RailwayTopology,
        kind: str,
        payload: dict[str, Any],
        source_id: str = "local",
        command_id: str | None = None,
        command_ts: float | None = None,
    ) -> RuntimeCommandResult:
        session = self.ensure_session(topology)
        provided_command_id = str(command_id).strip() if command_id is not None else ""
        actual_command = RuntimeCommand(
            command_id=provided_command_id or self._next_command_id(source_id),
            source_id=str(source_id).strip() or "local",
            kind=str(kind).strip(),
            payload=dict(payload),
            ts=float(command_ts if command_ts is not None else time.time()),
        )
        cache_key = (actual_command.source_id, actual_command.command_id)
        cached_result = self._command_cache.get(cache_key)
        if cached_result is not None:
            return RuntimeCommandResult(
                command_id=cached_result.command_id,
                source_id=cached_result.source_id,
                status="stale",
                message=f"Duplicate command ignored; previous status={cached_result.status}",
                payload=dict(cached_result.payload),
                stream_seq=cached_result.stream_seq,
                ts=time.time(),
                event=cached_result.event,
            )

        self._journal.append_command(actual_command)
        status = "applied"
        message = ""
        result_payload: dict[str, Any] = {}
        try:
            result_payload = self._execute_command(session, topology, actual_command)
        except Exception as exc:
            status = "rejected"
            message = str(exc)

        self._stream_seq += 1
        event = RuntimeEvent(
            event_id=f"evt-{self._stream_seq}",
            stream_seq=self._stream_seq,
            kind=actual_command.kind,
            payload={
                "command": actual_command.to_dict(),
                "result": self._event_summary(actual_command.kind, result_payload),
            },
            caused_by_command_id=actual_command.command_id,
            source_id=actual_command.source_id,
            command_status=status,
            message=message,
            topology_revision=self._topology_revision,
            ts=time.time(),
        )
        self._journal.append_event(event)
        command_result = RuntimeCommandResult(
            command_id=actual_command.command_id,
            source_id=actual_command.source_id,
            status=status,
            message=message,
            payload=result_payload,
            stream_seq=self._stream_seq,
            ts=event.ts,
            event=(event if status == "applied" else None),
        )
        self._command_cache[cache_key] = command_result
        self._last_command_id = actual_command.command_id
        self._last_command_status = status
        if status == "applied":
            self._last_applied_command_at = event.ts
            self._degraded_reason = None
            self._pending_runtime_events.append(event)
            self._maybe_checkpoint_snapshot()
        return command_result

    def set_or_reuse_route(
        self,
        *,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
        approach_time_lock_seconds: float,
        overlap_release_seconds: float,
    ) -> SetRouteResult:
        command_result = self.submit_command(
            topology=topology,
            kind="set_route",
            payload={
                "entry_signal_id": entry_signal_id,
                "exit_signal_id": exit_signal_id,
                "overlap_length": overlap_length,
                "approach_time_lock_seconds": approach_time_lock_seconds,
                "overlap_release_seconds": overlap_release_seconds,
            },
        )
        if command_result.status != "applied":
            raise RuntimeError(command_result.message or "Route command rejected")
        route_result = command_result.payload.get("set_route_result")
        if not isinstance(route_result, SetRouteResult):
            raise RuntimeError("Route result payload missing")
        return replace(route_result, view_state=self.runtime_view_state())

    def cancel_active_routes(self) -> CancelRoutesResult:
        if self._session is None:
            return CancelRoutesResult()
        command_result = self.submit_command(
            topology=self._session.topology,
            kind="cancel_active_routes",
            payload={},
        )
        result = command_result.payload.get("cancel_routes_result")
        return result if isinstance(result, CancelRoutesResult) else CancelRoutesResult()

    def emergency_release_active_routes(self) -> CancelRoutesResult:
        if self._session is None:
            return CancelRoutesResult()
        command_result = self.submit_command(
            topology=self._session.topology,
            kind="emergency_release_active_routes",
            payload={},
        )
        result = command_result.payload.get("cancel_routes_result")
        return result if isinstance(result, CancelRoutesResult) else CancelRoutesResult()

    def start_route_simulation(
        self,
        *,
        topology: RailwayTopology,
        entry_signal_id: str,
        exit_signal_id: str,
        overlap_length: int,
        approach_time_lock_seconds: float,
        overlap_release_seconds: float,
        train_speed: float = 1.0,
    ) -> StartSimulationResult:
        command_result = self.submit_command(
            topology=topology,
            kind="start_route_simulation",
            payload={
                "entry_signal_id": entry_signal_id,
                "exit_signal_id": exit_signal_id,
                "overlap_length": overlap_length,
                "approach_time_lock_seconds": approach_time_lock_seconds,
                "overlap_release_seconds": overlap_release_seconds,
                "train_speed": train_speed,
            },
        )
        if command_result.status != "applied":
            raise RuntimeError(command_result.message or "Simulation start rejected")
        result = command_result.payload.get("start_simulation_result")
        if not isinstance(result, StartSimulationResult):
            raise RuntimeError("Simulation result payload missing")
        return replace(result, view_state=self.runtime_view_state())

    def manual_set_section_occupied(
        self,
        *,
        topology: RailwayTopology,
        section_id: str,
        occupied: bool,
    ) -> SimulationManualOverrideResult:
        command_result = self.submit_command(
            topology=topology,
            kind="set_section_occupied",
            payload={"section_id": section_id, "occupied": bool(occupied)},
        )
        if command_result.status != "applied":
            raise RuntimeError(command_result.message or "Manual override rejected")
        result = command_result.payload.get("manual_override_result")
        if not isinstance(result, SimulationManualOverrideResult):
            raise RuntimeError("Manual override result payload missing")
        return result

    def step(self) -> RuntimeViewState:
        if self._session is None:
            return self.runtime_view_state()
        command_result = self.submit_command(
            topology=self._session.topology,
            kind="step_runtime",
            payload={},
        )
        if command_result.status != "applied":
            raise RuntimeError(command_result.message or "Runtime step rejected")
        view_state = command_result.payload.get("view_state")
        return view_state if isinstance(view_state, RuntimeViewState) else self.runtime_view_state()

    def apply_smartio_state_update(self, bridge: Any, payload: dict[str, Any]) -> RuntimeViewState:
        session = self._session
        if session is None:
            raise RuntimeError("Runtime session is not initialized")
        bridge.apply_state_update(payload)
        return self.runtime_view_state()

    def hydrate_runtime_snapshot(self, bridge: Any, payload: dict[str, Any]) -> RuntimeViewState:
        session = self._session
        if session is None:
            raise RuntimeError("Runtime session is not initialized")
        bridge.apply_runtime_snapshot(payload)
        return self.runtime_view_state()

    def _next_command_id(self, source_id: str) -> str:
        self._command_counter += 1
        return f"{source_id}-{self._command_counter}"

    def _maybe_checkpoint_snapshot(self) -> None:
        interval = max(1, int(getattr(self.profile, "runtime_snapshot_checkpoint_interval", 1)))
        if self._stream_seq % interval == 0:
            self.checkpoint_runtime_snapshot()

    def _replay_command(self, command: RuntimeCommand) -> None:
        if self._session is None:
            return
        self._execute_command(self._session, self._session.topology, command)

    def _execute_command(
        self,
        session: RuntimeSession,
        topology: RailwayTopology,
        command: RuntimeCommand,
    ) -> dict[str, Any]:
        kind = command.kind
        payload = command.payload
        if kind == "set_route":
            result = self._set_route_use_case.execute(
                simulation=session,
                topology=topology,
                entry_signal_id=str(payload.get("entry_signal_id", "")).strip(),
                exit_signal_id=str(payload.get("exit_signal_id", "")).strip(),
                overlap_length=int(payload.get("overlap_length", 0) or 0),
                approach_time_lock_seconds=float(
                    payload.get("approach_time_lock_seconds", self.profile.time_lock_seconds)
                ),
                overlap_release_seconds=float(
                    payload.get("overlap_release_seconds", self.profile.overlap_release_seconds)
                ),
            )
            self._session = session
            return {"set_route_result": replace(result, view_state=self.runtime_view_state())}

        if kind == "cancel_active_routes":
            result = self._cancel_routes_use_case.execute(session)
            return {"cancel_routes_result": result}

        if kind == "emergency_release_active_routes":
            result = self._emergency_release_use_case.execute(session)
            return {"cancel_routes_result": result}

        if kind == "start_route_simulation":
            result = self._start_simulation_use_case.execute(
                topology=topology,
                simulation=session,
                entry_signal_id=str(payload.get("entry_signal_id", "")).strip(),
                exit_signal_id=str(payload.get("exit_signal_id", "")).strip(),
                overlap_length=int(payload.get("overlap_length", 0) or 0),
                approach_time_lock_seconds=float(
                    payload.get("approach_time_lock_seconds", self.profile.time_lock_seconds)
                ),
                overlap_release_seconds=float(
                    payload.get("overlap_release_seconds", self.profile.overlap_release_seconds)
                ),
                train_speed=float(payload.get("train_speed", 1.0) or 1.0),
            )
            self._session = session
            return {"start_simulation_result": replace(result, view_state=self.runtime_view_state())}

        if kind == "set_section_occupied":
            section_id = str(payload.get("section_id", "")).strip()
            occupied = bool(payload.get("occupied", False))
            result = self._manual_override_use_case.execute_set_section_occupied(
                simulation=session,
                section_id=section_id,
                occupied=occupied,
            )
            return {"manual_override_result": result}

        if kind == "set_point_position":
            point_id = str(payload.get("point_id", "")).strip()
            position = payload.get("position", "")
            session.set_point_position(point_id, position)
            return {"point_id": point_id, "position": str(position)}

        if kind == "upsert_train":
            train = session.upsert_train(
                train_id=str(payload.get("train_id", "")).strip(),
                current_section=str(payload.get("current_section", "")).strip(),
                route_id=(str(payload.get("route_id", "")).strip() or None),
                speed=float(payload.get("speed", 0.0) or 0.0),
            )
            return {"train_id": train.id, "current_section": train.current_section, "route_id": train.route_id}

        if kind == "remove_train":
            train_id = str(payload.get("train_id", "")).strip()
            return {"train_id": train_id, "removed": bool(session.remove_train(train_id))}

        if kind == "step_runtime":
            session.step()
            return {"view_state": self.runtime_view_state(), "tick": session.tick}

        if kind == "hydrate_snapshot":
            snapshot = payload.get("snapshot", {})
            if not isinstance(snapshot, dict):
                raise ValueError("hydrate_snapshot requires snapshot object")
            session.hydrate_snapshot(snapshot=snapshot, strict_route_ids=bool(payload.get("strict_route_ids", True)))
            return {"tick": session.tick}

        if kind == "apply_state_update":
            return self._apply_state_update_command(session, payload)

        raise RuntimeError(f"INVALID_COMMAND: Unsupported runtime command {kind}")

    def _apply_state_update_command(self, session: RuntimeSession, payload: dict[str, Any]) -> dict[str, Any]:
        changed_sections: list[str] = []
        for point_item in payload.get("points", []):
            if not isinstance(point_item, dict):
                continue
            if "locked_by" in point_item:
                raise RuntimeError("SAFETY_REJECTED: Direct locked_by point update is blocked")
            point_id = str(point_item.get("id", "")).strip()
            position = str(point_item.get("position", "")).strip().upper()
            if point_id and position:
                session.set_point_position(point_id, position)

        trains_payload = payload.get("trains")
        if isinstance(trains_payload, list):
            for train_item in trains_payload:
                if not isinstance(train_item, dict):
                    continue
                train_id = str(train_item.get("id", "")).strip()
                current_section = str(train_item.get("current_section", "")).strip()
                if not train_id or not current_section:
                    raise RuntimeError("INVALID_COMMAND: Each train requires id/current_section")
                try:
                    session.upsert_train(
                        train_id=train_id,
                        current_section=current_section,
                        route_id=(str(train_item.get("route_id", "")).strip() or None),
                        speed=float(train_item.get("speed", 0.0) or 0.0),
                    )
                except RuntimeError as exc:
                    route_id = str(train_item.get("route_id", "")).strip()
                    if route_id and "is not active" in str(exc):
                        session.upsert_train(
                            train_id=train_id,
                            current_section=current_section,
                            route_id=None,
                            speed=float(train_item.get("speed", 0.0) or 0.0),
                        )
                    else:
                        raise

        removed_train_ids = payload.get("removed_train_ids")
        if isinstance(removed_train_ids, list):
            for raw_train_id in removed_train_ids:
                train_id = str(raw_train_id).strip()
                if train_id:
                    session.trains.pop(train_id, None)

        for section_item in payload.get("sections", []):
            if not isinstance(section_item, dict):
                continue
            if "locked_by" in section_item:
                raise RuntimeError("SAFETY_REJECTED: Direct locked_by section update is blocked")
            section_id = str(section_item.get("id", "")).strip()
            if not section_id or "occupied" not in section_item:
                continue
            session.set_section_occupied(section_id, bool(section_item.get("occupied", False)))
            changed_sections.append(section_id)

        for signal_item in payload.get("signals", []):
            if not isinstance(signal_item, dict):
                continue
            if "aspect" in signal_item or "route_id" in signal_item:
                raise RuntimeError("SAFETY_REJECTED: Direct signal aspect/route_id updates are blocked")

        normalized_removed_train_ids = []
        if isinstance(removed_train_ids, list):
            normalized_removed_train_ids = [
                str(item).strip() for item in removed_train_ids if str(item).strip()
            ]

        return {
            "changed_sections": changed_sections,
            "removed_train_ids": normalized_removed_train_ids,
            "train_ids": sorted(session.trains.keys()),
        }

    @staticmethod
    def _event_summary(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        if kind == "set_route":
            result = payload.get("set_route_result")
            if isinstance(result, SetRouteResult):
                return {
                    "route_id": result.route.id,
                    "entry_signal_id": result.route.entry_signal_id,
                    "exit_signal_id": result.route.exit_signal_id,
                    "created": result.created,
                }
        if kind == "start_route_simulation":
            result = payload.get("start_simulation_result")
            if isinstance(result, StartSimulationResult):
                return {
                    "route_id": result.route.id,
                    "train_id": result.train.id,
                    "simulation_start_section": result.simulation_start_section,
                    "created_route": result.created_route,
                    "created_train": result.created_train,
                }
        if kind == "set_section_occupied":
            result = payload.get("manual_override_result")
            if isinstance(result, SimulationManualOverrideResult):
                return {
                    "section_id": result.section_id,
                    "occupied_before": result.occupied_before,
                    "occupied_after": result.occupied_after,
                    "removed_trains": list(result.removed_trains),
                }
        if kind in {"cancel_active_routes", "emergency_release_active_routes"}:
            result = payload.get("cancel_routes_result")
            if isinstance(result, CancelRoutesResult):
                return {
                    "attempted_routes": result.attempted_routes,
                    "cancelled_routes": result.cancelled_routes,
                    "failures": list(result.failures),
                }
        if kind == "step_runtime":
            return {"tick": payload.get("tick", 0)}
        if kind == "apply_state_update":
            return {
                "changed_sections": list(payload.get("changed_sections", [])),
                "removed_train_ids": list(payload.get("removed_train_ids", [])),
                "train_ids": list(payload.get("train_ids", [])),
            }
        return {}
