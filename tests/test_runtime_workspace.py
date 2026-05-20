from __future__ import annotations

import tempfile
from pathlib import Path

from PyQt6.QtCore import QObject

from core.domain.model.elements import PointPosition, TrackSection
from integration.smartio_adapter.runtime_bridge import SmartIORuntimeBridge
from runtime import (
    GenericApplicationProfile,
    GenericApplicationService,
    RuntimeSession,
    RuntimeWorkspaceService,
)
from runtime.application import AppMode
from runtime.application.runtime_session_port import RuntimeSessionPort
from runtime.application.serialization import build_runtime_snapshot
from ui.controllers.runtime_workspace_controller import SmartIORuntimeCoordinator

REPO_ROOT = Path(__file__).resolve().parents[1]
LAYOUT_PATH = REPO_ROOT / "data" / "station_layout" / "main_layout.json"
TEST_LAYOUT_PATH = REPO_ROOT / "data" / "station_layout" / "test.json"


def build_services() -> tuple[GenericApplicationService, RuntimeWorkspaceService]:
    profile = GenericApplicationProfile(
        runtime_journal_dir=tempfile.mkdtemp(prefix="cbi-runtime-journal-")
    )
    application_service = GenericApplicationService(profile=profile)
    runtime_workspace = RuntimeWorkspaceService(
        profile=profile,
        kernel=application_service.kernel,
    )
    return application_service, runtime_workspace


def load_topology(application_service: GenericApplicationService):
    return application_service.load_topology(
        LAYOUT_PATH,
        load_runtime_state=False,
        load_occupancy=True,
    )


def load_test_topology(application_service: GenericApplicationService):
    return application_service.load_topology(
        TEST_LAYOUT_PATH,
        load_runtime_state=False,
        load_occupancy=True,
    )


def first_route_pair(application_service: GenericApplicationService, topology):
    signals = sorted(topology.signals.keys())
    for entry_signal_id in signals:
        for exit_signal_id in signals:
            if entry_signal_id == exit_signal_id:
                continue
            if application_service.validate_signal_pair(topology, entry_signal_id, exit_signal_id):
                continue
            try:
                route = application_service.find_route(
                    topology,
                    entry_signal_id,
                    exit_signal_id,
                    overlap_length=1,
                )
            except Exception:
                continue
            return entry_signal_id, exit_signal_id, route
    raise AssertionError("No valid route pair found in sample topology")


def test_route_point_isolates_occupied_flank_branch_for_a_to_g2() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)

    s14 = topology.get_element("S14")
    assert isinstance(s14, TrackSection)
    s14.occupied = True

    route = application_service.find_route(
        topology,
        "A",
        "G2",
        overlap_length=1,
    )

    assert route.required_point_positions["P2"] == PointPosition.REVERSE
    assert "S14" not in route.monitored_flank_sections

    result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id="A",
        exit_signal_id="G2",
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )

    assert result.created is True
    assert result.route.entry_signal_id == "A"
    assert result.route.exit_signal_id == "G2"


def test_runtime_workspace_route_lifecycle_and_view_state() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    first_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )
    second_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )

    assert first_result.created is True
    assert second_result.created is False
    assert first_result.view_state is not None
    assert len(first_result.view_state.routes) == 1
    assert isinstance(runtime_workspace.ensure_session(topology), RuntimeSession)
    assert runtime_workspace.get_active_route_for_pair(entry_signal_id, exit_signal_id) is not None


def test_runtime_workspace_uses_runtime_session_port_implementation() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)

    session = runtime_workspace.ensure_session(topology)

    assert isinstance(session, RuntimeSession)
    assert isinstance(session, RuntimeSessionPort)


def test_runtime_workspace_start_manual_override_and_snapshot_roundtrip() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    start_result = runtime_workspace.start_route_simulation(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
        train_speed=1.0,
    )
    assert start_result.view_state is not None
    assert len(start_result.view_state.trains) == 1

    snapshot = runtime_workspace.build_runtime_snapshot()
    assert "routes" in snapshot
    assert "trains" in snapshot
    assert "occupancy" in snapshot
    assert "signal_state" in snapshot

    topology_copy = load_topology(application_service)
    _, runtime_workspace_copy = build_services()
    session_copy = runtime_workspace_copy.ensure_session(topology_copy)
    bridge = SmartIORuntimeBridge(runtime_session=session_copy, default_overlap_length=1)
    bridge.apply_runtime_snapshot(snapshot)

    copied_view_state = runtime_workspace_copy.runtime_view_state()
    assert copied_view_state.tick == snapshot.get("tick", 0)
    assert len(copied_view_state.routes) == len(snapshot["routes"])
    assert len(copied_view_state.trains) == len(snapshot["trains"])

    override_result = runtime_workspace.manual_set_section_occupied(
        topology=topology,
        section_id=start_result.simulation_start_section,
        occupied=False,
    )
    assert start_result.train.id in override_result.removed_trains

    step_view = runtime_workspace.step()
    assert step_view.tick >= 1


def test_empty_runtime_snapshot_includes_required_tick_field() -> None:
    snapshot = build_runtime_snapshot(None)

    assert snapshot["snapshot_version"] == 2
    assert snapshot["stream_seq"] == 0
    assert snapshot["tick"] == 0
    assert snapshot["topology_revision"] is None
    assert snapshot["routes"] == []
    assert snapshot["trains"] == []
    assert snapshot["occupancy"] == []
    assert snapshot["signal_state"] == []


def test_smartio_state_update_applies_to_runtime_session() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, route = first_route_pair(application_service, topology)

    runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )
    session = runtime_workspace.ensure_session(topology)
    bridge = SmartIORuntimeBridge(runtime_session=session, default_overlap_length=1)

    payload = {
        "trains": [
            {
                "id": "WEB-1",
                "current_section": route.path[0],
                "route_id": route.id,
                "speed": 1.0,
            }
        ],
        "sections": [{"id": route.path[0], "occupied": True}],
        "points": [],
        "signals": [],
    }
    bridge.apply_state_update(payload)

    view_state = runtime_workspace.runtime_view_state()
    assert view_state.trains_by_id["WEB-1"].current_section == route.path[0]


def test_smartio_train_updates_are_incremental_and_do_not_remove_other_trains() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    set_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )
    session = runtime_workspace.ensure_session(topology)
    bridge = SmartIORuntimeBridge(runtime_session=session, default_overlap_length=1)
    start_section = set_result.route.path[0]

    bridge.apply_state_update(
        {
            "trains": [
                {
                    "id": "WEB-1",
                    "current_section": start_section,
                    "route_id": set_result.route.id,
                    "speed": 1.0,
                }
            ]
        }
    )
    bridge.apply_state_update(
        {
            "trains": [
                {
                    "id": "WEB-2",
                    "current_section": start_section,
                    "route_id": set_result.route.id,
                    "speed": 1.0,
                }
            ]
        }
    )

    assert sorted(session.trains.keys()) == ["WEB-1", "WEB-2"]


def test_smartio_removed_train_ids_remove_only_targeted_train_records() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    set_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )
    session = runtime_workspace.ensure_session(topology)
    bridge = SmartIORuntimeBridge(runtime_session=session, default_overlap_length=1)
    start_section = set_result.route.path[0]

    bridge.apply_state_update(
        {
            "trains": [
                {
                    "id": "WEB-1",
                    "current_section": start_section,
                    "route_id": set_result.route.id,
                    "speed": 1.0,
                }
            ]
        }
    )
    bridge.apply_state_update(
        {
            "removed_train_ids": ["WEB-1"],
        }
    )

    assert "WEB-1" not in session.trains
    start_element = session.topology.get_element(start_section)
    assert getattr(start_element, "occupied", None) is True


def test_runtime_snapshot_routes_include_full_path_and_active_status() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )
    snapshot = runtime_workspace.build_runtime_snapshot()

    assert snapshot["routes"]
    assert isinstance(snapshot["topology_revision"], str)
    assert snapshot["stream_seq"] >= 1
    route_snapshot = snapshot["routes"][0]
    assert route_snapshot["status"] == "ACTIVE"
    assert route_snapshot["full_path"] == [*route_snapshot["path"], *route_snapshot["overlap_path"]]


def test_state_update_outside_runtime_mode_returns_failed_command_result() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    sent_messages: list[dict] = []

    class StubSocketClient:
        def __init__(self) -> None:
            self.is_connected = True

        @staticmethod
        def build_envelope(event_type: str, payload: dict) -> dict:
            return {"type": event_type, "payload": payload, "ts": 0.0}

        def send_event(self, event: dict) -> None:
            sent_messages.append(event)

    coordinator = SmartIORuntimeCoordinator(
        profile=GenericApplicationProfile(smart_io_ws_url="ws://example.test/smartio"),
        application_service=application_service,
        runtime_workspace_service=runtime_workspace,
        topology_provider=lambda: topology,
        operating_mode_provider=lambda: AppMode.SIMULATION,
        parent=QObject(),
    )
    coordinator._smartio_client = StubSocketClient()

    coordinator._on_event_received(
        {
            "type": "state_update",
            "payload": {
                "msg_id": "su-test-1",
                "sections": [{"id": "S1", "occupied": True}],
            },
            "ts": 0.0,
        }
    )

    assert sent_messages
    assert sent_messages[0]["type"] == "command_result"
    result_payload = sent_messages[0]["payload"]
    assert result_payload["command_id"] == "su-test-1"
    assert result_payload["status"] == "rejected"


def test_local_smartio_in_simulation_mode_publishes_snapshot() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_test_topology(application_service)
    runtime_workspace.ensure_session(topology)
    sent_messages: list[dict] = []

    class StubSocketClient:
        def __init__(self) -> None:
            self.is_connected = True

        @staticmethod
        def build_envelope(event_type: str, payload: dict) -> dict:
            return {"type": event_type, "payload": payload, "ts": 0.0}

        def send_event(self, event: dict) -> None:
            sent_messages.append(event)

    coordinator = SmartIORuntimeCoordinator(
        profile=GenericApplicationProfile(smart_io_ws_url="ws://127.0.0.1:8088/smartio"),
        application_service=application_service,
        runtime_workspace_service=runtime_workspace,
        topology_provider=lambda: topology,
        operating_mode_provider=lambda: AppMode.SIMULATION,
        parent=None,
    )
    coordinator._smartio_client = StubSocketClient()

    published = coordinator.publish_runtime_snapshot()

    assert published is True
    assert sent_messages
    assert sent_messages[-1]["type"] == "runtime_snapshot"
    assert sent_messages[-1]["payload"]["layout"]["signals"]


def test_local_smartio_in_simulation_mode_accepts_state_update() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_test_topology(application_service)
    sent_messages: list[dict] = []

    class StubSocketClient:
        def __init__(self) -> None:
            self.is_connected = True

        @staticmethod
        def build_envelope(event_type: str, payload: dict) -> dict:
            return {"type": event_type, "payload": payload, "ts": 0.0}

        def send_event(self, event: dict) -> None:
            sent_messages.append(event)

    coordinator = SmartIORuntimeCoordinator(
        profile=GenericApplicationProfile(smart_io_ws_url="ws://127.0.0.1:8088/smartio"),
        application_service=application_service,
        runtime_workspace_service=runtime_workspace,
        topology_provider=lambda: topology,
        operating_mode_provider=lambda: AppMode.SIMULATION,
        parent=None,
    )
    coordinator._smartio_client = StubSocketClient()

    coordinator._on_event_received(
        {
            "type": "state_update",
            "payload": {
                "msg_id": "su-local-1",
                "sections": [{"id": "S2", "occupied": True}],
            },
            "ts": 0.0,
        }
    )

    assert sent_messages
    result_payload = sent_messages[0]["payload"]
    assert sent_messages[0]["type"] == "command_result"
    assert result_payload["command_id"] == "su-local-1"
    assert result_payload["status"] == "applied"


def test_duplicate_command_id_returns_stale_without_reapplying() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    first_result = runtime_workspace.submit_command(
        topology=topology,
        kind="set_route",
        payload={
            "entry_signal_id": entry_signal_id,
            "exit_signal_id": exit_signal_id,
            "overlap_length": 1,
            "approach_time_lock_seconds": 1.0,
            "overlap_release_seconds": 1.0,
        },
        source_id="smartio-web-1",
        command_id="cmd-1",
    )
    second_result = runtime_workspace.submit_command(
        topology=topology,
        kind="set_route",
        payload={
            "entry_signal_id": entry_signal_id,
            "exit_signal_id": exit_signal_id,
            "overlap_length": 1,
            "approach_time_lock_seconds": 1.0,
            "overlap_release_seconds": 1.0,
        },
        source_id="smartio-web-1",
        command_id="cmd-1",
    )

    assert first_result.status == "applied"
    assert second_result.status == "stale"
    assert len(runtime_workspace.runtime_view_state().routes) == 1


def test_reverse_route_handoff_keeps_train_visible_on_test_layout() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_test_topology(application_service)

    forward_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id="ENTRY_RIGHT_A",
        exit_signal_id="EXTI_RIGHT_B",
        overlap_length=0,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=0.0,
    )

    start_forward = runtime_workspace.submit_command(
        topology=topology,
        kind="apply_state_update",
        payload={
            "trains": [
                {
                    "id": "WEB-1",
                    "current_section": "S2",
                    "route_id": forward_result.route.id,
                    "speed": 1.0,
                }
            ],
            "sections": [{"id": "S2", "occupied": True}],
        },
        source_id="smartio-web",
        command_id="forward-1",
    )
    assert start_forward.status == "applied"

    finish_forward = runtime_workspace.submit_command(
        topology=topology,
        kind="apply_state_update",
        payload={
            "trains": [
                {
                    "id": "WEB-1",
                    "current_section": "S3",
                    "route_id": forward_result.route.id,
                    "speed": 1.0,
                }
            ],
            "sections": [{"id": "S3", "occupied": True}],
        },
        source_id="smartio-web",
        command_id="forward-2",
    )
    assert finish_forward.status == "applied"

    reverse_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id="ENTRY_LEFT_B",
        exit_signal_id="EXIT_LEFT_A",
        overlap_length=0,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=0.0,
    )

    handoff_result = runtime_workspace.submit_command(
        topology=topology,
        kind="apply_state_update",
        payload={
            "trains": [
                {
                    "id": "WEB-1",
                    "current_section": "S2",
                    "route_id": forward_result.route.id,
                    "speed": 1.0,
                }
            ],
            "sections": [{"id": "S2", "occupied": True}],
        },
        source_id="smartio-web",
        command_id="reverse-1",
    )
    assert handoff_result.status == "applied"

    destination_result = runtime_workspace.submit_command(
        topology=topology,
        kind="apply_state_update",
        payload={
            "trains": [
                {
                    "id": "WEB-1",
                    "current_section": "S1",
                    "route_id": reverse_result.route.id,
                    "speed": 1.0,
                }
            ],
            "sections": [
                {"id": "S1", "occupied": True},
                {"id": "S3", "occupied": False},
            ],
        },
        source_id="smartio-web",
        command_id="reverse-2",
    )
    assert destination_result.status == "applied"

    session = runtime_workspace.ensure_session(topology)
    train = session.trains.get("WEB-1")
    assert train is not None
    assert train.current_section == "S1"
    assert topology.get_element("S1").occupied is True


def test_active_route_train_move_still_applies_when_web_route_id_is_missing() -> None:
    application_service, runtime_workspace = build_services()
    topology = load_test_topology(application_service)

    forward_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id="ENTRY_RIGHT_A",
        exit_signal_id="EXTI_RIGHT_B",
        overlap_length=0,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=0.0,
    )

    start_result = runtime_workspace.submit_command(
        topology=topology,
        kind="apply_state_update",
        payload={
            "trains": [
                {
                    "id": "WEB-ROUTELESS",
                    "current_section": "S2",
                    "route_id": forward_result.route.id,
                    "speed": 1.0,
                }
            ],
            "sections": [{"id": "S2", "occupied": True}],
        },
        source_id="smartio-web",
        command_id="routeless-start",
    )
    assert start_result.status == "applied"

    move_result = runtime_workspace.submit_command(
        topology=topology,
        kind="apply_state_update",
        payload={
            "trains": [
                {
                    "id": "WEB-ROUTELESS",
                    "current_section": "S3",
                    "route_id": None,
                    "speed": 1.0,
                }
            ],
            "sections": [{"id": "S3", "occupied": True}],
        },
        source_id="smartio-web",
        command_id="routeless-move",
    )
    assert move_result.status == "applied"

    session = runtime_workspace.ensure_session(topology)
    train = session.trains.get("WEB-ROUTELESS")
    assert train is not None
    assert train.current_section == "S3"


def test_runtime_workspace_recovers_from_checkpoint_journal() -> None:
    profile = GenericApplicationProfile(
        runtime_journal_dir=tempfile.mkdtemp(prefix="cbi-runtime-journal-")
    )
    application_service = GenericApplicationService(profile=profile)
    runtime_workspace = RuntimeWorkspaceService(profile=profile, kernel=application_service.kernel)
    topology = load_topology(application_service)
    entry_signal_id, exit_signal_id, _route = first_route_pair(application_service, topology)

    set_result = runtime_workspace.set_or_reuse_route(
        topology=topology,
        entry_signal_id=entry_signal_id,
        exit_signal_id=exit_signal_id,
        overlap_length=1,
        approach_time_lock_seconds=1.0,
        overlap_release_seconds=1.0,
    )
    runtime_workspace.manual_set_section_occupied(
        topology=topology,
        section_id=set_result.route.path[0],
        occupied=True,
    )
    snapshot_before = runtime_workspace.build_runtime_snapshot()

    runtime_workspace_recovered = RuntimeWorkspaceService(
        profile=profile,
        kernel=application_service.kernel,
    )
    topology_recovered = load_topology(application_service)
    runtime_workspace_recovered.ensure_session(topology_recovered)
    snapshot_after = runtime_workspace_recovered.build_runtime_snapshot()

    assert snapshot_after["topology_revision"] == snapshot_before["topology_revision"]
    assert snapshot_after["stream_seq"] >= snapshot_before["stream_seq"]
    assert len(snapshot_after["routes"]) == len(snapshot_before["routes"])


def test_architecture_boundaries_do_not_regress() -> None:
    main_window_text = (REPO_ROOT / "ui" / "views" / "main_window_view.py").read_text()
    assert "simulation.session" not in main_window_text
    assert "core.runtime" not in main_window_text
    assert "from runtime.runtime_controller import RuntimeSession" not in main_window_text
    assert "RuntimeSession(" not in main_window_text

    for path in (REPO_ROOT / "core").rglob("*.py"):
        text = path.read_text()
        assert "PyQt6" not in text, f"Qt import leaked into core: {path}"
        assert "integration.smartio_adapter" not in text, (
            f"SmartIO integration leaked into core: {path}"
        )
        assert "simulation.session" not in text, f"Simulation session leaked back into core: {path}"
