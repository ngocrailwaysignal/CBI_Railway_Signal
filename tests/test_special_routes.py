from __future__ import annotations

import json

import pytest

from core.compiler.interlocking_table import InterlockingTableGenerator
from core.domain.lifecycle import RouteLifecycleState
from core.domain.model.elements import Signal, SignalAspect, SignalDirection, TrackSection
from core.domain.model.topology import (
    ROUTE_TYPE_CALLING_ON,
    ROUTE_TYPE_REVERSE,
    RailwayTopology,
)
from core.domain.model.train import Train
from kernel.product_kernel import GenericProductKernel
from runtime import RuntimeSession
from runtime.application import AppMode
from runtime.application.serialization import build_webclient_runtime_state
from runtime.application.use_cases.set_route import SetOrReuseRouteUseCase
from runtime.read_model import build_runtime_view_state


class FakeClock:
    def __init__(self) -> None:
        self.current = 0.0

    def now(self) -> float:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += float(seconds)


def build_two_signal_topology(
    *,
    exit_direction: SignalDirection = SignalDirection.RIGHT,
) -> RailwayTopology:
    topology = RailwayTopology()
    for section_id in ("S1", "S2", "S3"):
        topology.add_section(TrackSection(section_id))
    topology.add_signal(Signal("ENTRY", direction=SignalDirection.RIGHT, protects="S1"))
    topology.add_signal(Signal("EXIT", direction=exit_direction, protects="S3"))
    topology.connect("ENTRY", "S1")
    topology.connect("S1", "S2")
    topology.connect("S2", "EXIT")
    topology.connect("EXIT", "S3")
    topology.sync_signal_virtual_routes()
    return topology


def test_blocking_signal_and_manual_route_type_round_trip(tmp_path) -> None:
    topology = build_two_signal_topology()
    signal = topology.signals["EXIT"]
    signal.aspect = SignalAspect.GREEN
    signal.is_blocking = True
    signal.is_reverse_signal = True
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)

    path = tmp_path / "layout.json"
    topology.export_to_json(path, include_runtime_state=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_signal = next(item for item in raw["signals"] if item["id"] == "EXIT")

    assert raw_signal["aspect"] == SignalAspect.RED.value
    assert raw_signal["is_blocking"] is True
    assert raw_signal["is_reverse_signal"] is True
    assert "calling_on_entry_signal" not in raw_signal
    assert raw["route_types"] == {"ENTRY->EXIT": ROUTE_TYPE_CALLING_ON}
    assert raw["route_signal_aspects"] == {"ENTRY->EXIT": SignalAspect.YELLOW.value}

    loaded = RailwayTopology.load_from_json(path, load_runtime_state=True)
    loaded_signal = loaded.signals["EXIT"]
    assert loaded_signal.aspect == SignalAspect.RED
    assert loaded_signal.is_blocking is True
    assert loaded_signal.is_reverse_signal is True
    assert loaded.route_type("ENTRY", "EXIT") == ROUTE_TYPE_CALLING_ON
    loaded_signal.aspect = SignalAspect.GREEN
    view_state = build_runtime_view_state(RuntimeSession(loaded))
    exit_state = next(item for item in view_state.signal_state if item.id == "EXIT")
    assert exit_state.aspect == SignalAspect.RED.value


def test_missing_reverse_signal_field_loads_as_false(tmp_path) -> None:
    topology = build_two_signal_topology()
    path = tmp_path / "layout.json"
    topology.export_to_json(path, include_runtime_state=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    for signal in raw["signals"]:
        signal.pop("is_reverse_signal", None)
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = RailwayTopology.load_from_json(path, load_runtime_state=True)

    assert loaded.signals["ENTRY"].is_reverse_signal is False
    assert loaded.signals["EXIT"].is_reverse_signal is False


def test_route_type_is_mutually_exclusive_and_can_reset_to_normal() -> None:
    topology = build_two_signal_topology()

    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)
    assert topology.is_calling_on_pair("ENTRY", "EXIT")
    assert not topology.is_reverse_route_pair("ENTRY", "EXIT")
    assert topology.route_signal_aspect("ENTRY", "EXIT") == SignalAspect.YELLOW

    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_REVERSE)
    assert not topology.is_calling_on_pair("ENTRY", "EXIT")
    assert topology.is_reverse_route_pair("ENTRY", "EXIT")
    assert topology.route_signal_aspect("ENTRY", "EXIT") == SignalAspect.YELLOW_BLUE

    topology.set_route_type("ENTRY", "EXIT", "")
    assert topology.route_type("ENTRY", "EXIT") == ""
    assert topology.route_signal_aspect("ENTRY", "EXIT") == SignalAspect.GREEN


def test_calling_on_route_allows_occupied_sections_and_uses_manual_signal_aspect() -> None:
    topology = build_two_signal_topology()
    topology.signals["EXIT"].is_blocking = True
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)
    topology.set_route_signal_aspect("ENTRY", "EXIT", SignalAspect.GREEN)
    section = topology.get_element("S2")
    assert isinstance(section, TrackSection)
    section.occupied = True

    session = RuntimeSession(topology)
    route = session.set_route("ENTRY", "EXIT")

    assert route.is_calling_on is True
    assert route.is_reverse is False
    assert route.signal_aspect == SignalAspect.GREEN
    assert topology.signals["ENTRY"].aspect == SignalAspect.GREEN
    assert topology.signals["ENTRY"].route_id == route.id
    assert section.locked_by == route.id


def test_calling_on_route_still_rejects_locked_sections() -> None:
    topology = build_two_signal_topology()
    topology.signals["EXIT"].is_blocking = True
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)
    section = topology.get_element("S2")
    assert isinstance(section, TrackSection)
    section.locked_by = "OTHER"

    with pytest.raises(ValueError, match="locked by OTHER"):
        RuntimeSession(topology).set_route("ENTRY", "EXIT")


def test_calling_on_train_can_enter_preoccupied_route_section_without_collision() -> None:
    topology = build_two_signal_topology()
    topology.signals["EXIT"].is_blocking = True
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)
    session = RuntimeSession(topology)
    session.locking_engine.configure_release_timing(overlap_release_seconds=2.0)
    route = session.set_route("ENTRY", "EXIT")

    session.locking_engine.enter_train_section(route.id, "S2")
    session.locking_engine.enter_train_section(route.id, "S2")
    issues = session.safety_monitor.detect_unsafe_conditions(
        topology,
        [
            Train("T1", current_section="S2", route_id=route.id),
            Train("T2", current_section="S2", route_id=route.id),
        ],
        active_routes=session.locking_engine.active_routes,
    )

    assert not [issue for issue in issues if "Collision risk" in issue]


def test_calling_on_train_can_share_section_with_idle_train() -> None:
    topology = build_two_signal_topology()
    topology.signals["EXIT"].is_blocking = True
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)
    session = RuntimeSession(topology)
    session.locking_engine.configure_release_timing(overlap_release_seconds=2.0)
    route = session.set_route("ENTRY", "EXIT")

    session.locking_engine.enter_train_section(route.id, "S2")
    issues = session.safety_monitor.detect_unsafe_conditions(
        topology,
        [
            Train("STANDING", current_section="S2", route_id=None),
            Train("CALLING", current_section="S2", route_id=route.id),
        ],
        active_routes=session.locking_engine.active_routes,
    )

    assert not [issue for issue in issues if "Collision risk" in issue]


def test_calling_on_share_survives_destination_release() -> None:
    topology = build_two_signal_topology()
    topology.signals["EXIT"].is_blocking = True
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_CALLING_ON)
    destination = topology.get_element("S2")
    assert isinstance(destination, TrackSection)
    destination.occupied = True

    session = RuntimeSession(topology)
    clock = FakeClock()
    session.locking_engine.clock = clock
    session.locking_engine.configure_release_timing(overlap_release_seconds=1.0)
    session.trains["STANDING"] = Train("STANDING", current_section="S2", speed=0.0)
    route = session.set_route("ENTRY", "EXIT")

    assert route.lifecycle_state == RouteLifecycleState.CLEARED_REVERSIBLE

    session.add_train(Train("CALLING", current_section="S1", speed=1.0), route)
    session.step()

    assert route.lifecycle_state == RouteLifecycleState.RELEASING
    assert topology.signals["ENTRY"].route_id == route.id
    assert topology.signals["ENTRY"].aspect == SignalAspect.RED
    assert session.trains["STANDING"].calling_on_shared_sections == {"S2"}
    assert session.trains["CALLING"].calling_on_shared_sections == {"S2"}

    clock.advance(2.0)
    session.step()

    assert session.locking_engine.active_routes == {}
    assert session.trains["CALLING"].route_id is None
    assert session.trains["STANDING"].calling_on_shared_sections == {"S2"}
    assert session.trains["CALLING"].calling_on_shared_sections == {"S2"}


def test_normal_train_still_rejects_preoccupied_route_section() -> None:
    topology = build_two_signal_topology()
    session = RuntimeSession(topology)
    route = session.set_route("ENTRY", "EXIT")

    session.locking_engine.enter_train_section(route.id, "S2")
    with pytest.raises(RuntimeError, match="already occupied"):
        session.locking_engine.enter_train_section(route.id, "S2")


def test_releasing_route_is_not_reused_for_second_start_or_set() -> None:
    topology = build_two_signal_topology()
    session = RuntimeSession(topology)
    route = session.set_route("ENTRY", "EXIT")
    route.lifecycle_state = RouteLifecycleState.RELEASING

    use_case = SetOrReuseRouteUseCase(GenericProductKernel())

    with pytest.raises(RuntimeError, match="is releasing"):
        use_case.execute(
            topology=topology,
            simulation=session,
            entry_signal_id="ENTRY",
            exit_signal_id="EXIT",
            overlap_length=0,
            approach_time_lock_seconds=0.0,
            overlap_release_seconds=2.0,
        )


def test_manual_reverse_mark_is_display_only_on_normal_valid_route() -> None:
    topology = build_two_signal_topology()
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_REVERSE)

    rows = InterlockingTableGenerator(topology).generate(["ENTRY"], ["EXIT"])

    assert len(rows) == 1
    assert rows[0].is_reverse is True
    assert rows[0].is_calling_on is False
    assert rows[0].signal_aspect == SignalAspect.YELLOW_BLUE

    section = topology.get_element("S2")
    assert isinstance(section, TrackSection)
    section.occupied = True
    with pytest.raises(ValueError, match="occupied"):
        RuntimeSession(topology).set_route("ENTRY", "EXIT")


def test_reverse_signal_pair_sets_blue_route_aspect_without_manual_route_type() -> None:
    topology = build_two_signal_topology()
    topology.signals["ENTRY"].is_reverse_signal = True
    topology.signals["EXIT"].is_reverse_signal = True
    topology.set_route_signal_aspect("ENTRY", "EXIT", SignalAspect.YELLOW)

    rows = InterlockingTableGenerator(topology).generate(["ENTRY"], ["EXIT"])
    route = RuntimeSession(topology).set_route("ENTRY", "EXIT")

    assert rows[0].is_reverse is True
    assert rows[0].signal_aspect == SignalAspect.YELLOW_BLUE
    assert route.is_reverse is True
    assert route.signal_aspect == SignalAspect.YELLOW_BLUE
    assert topology.signals["ENTRY"].aspect == SignalAspect.YELLOW_BLUE


def test_reverse_signal_pair_can_store_green_blue_without_manual_route_type() -> None:
    topology = build_two_signal_topology()
    topology.signals["ENTRY"].is_reverse_signal = True
    topology.signals["EXIT"].is_reverse_signal = True
    topology.set_route_signal_aspect_for_type(
        "ENTRY",
        "EXIT",
        SignalAspect.GREEN_BLUE,
        ROUTE_TYPE_REVERSE,
    )

    rows = InterlockingTableGenerator(topology).generate(["ENTRY"], ["EXIT"])
    route = RuntimeSession(topology).set_route("ENTRY", "EXIT")

    assert rows[0].is_reverse is True
    assert rows[0].signal_aspect == SignalAspect.GREEN_BLUE
    assert route.is_reverse is True
    assert route.signal_aspect == SignalAspect.GREEN_BLUE
    assert topology.signals["ENTRY"].aspect == SignalAspect.GREEN_BLUE


def test_reverse_mark_does_not_enable_opposite_direction_route() -> None:
    topology = build_two_signal_topology(exit_direction=SignalDirection.LEFT)
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_REVERSE)

    rows = InterlockingTableGenerator(topology).generate(["ENTRY"], ["EXIT"])

    assert rows == []
    assert topology.validate_signal_pair("ENTRY", "EXIT")
    with pytest.raises(ValueError, match="opposite directions"):
        RuntimeSession(topology).route_engine.find_route("ENTRY", "EXIT")


def test_reverse_mark_does_not_allow_exit_without_approach_link() -> None:
    topology = RailwayTopology()
    for section_id in ("A", "B", "C"):
        topology.add_section(TrackSection(section_id))
    topology.add_signal(Signal("ENTRY", direction=SignalDirection.RIGHT, protects="A"))
    topology.add_signal(Signal("EXIT", direction=SignalDirection.RIGHT, protects="C"))
    topology.connect("ENTRY", "A")
    topology.connect("A", "B")
    topology.connect("B", "C")
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_REVERSE)
    topology.sync_signal_virtual_routes()

    assert topology.signal_approach_nodes("EXIT") == []
    assert topology.validate_signal_pair("ENTRY", "EXIT")

    rows = InterlockingTableGenerator(topology).generate(["ENTRY"], ["EXIT"])

    assert rows == []
    with pytest.raises(ValueError, match="no incoming track/point link"):
        RuntimeSession(topology).route_engine.find_route("ENTRY", "EXIT")


def test_special_route_columns_are_serialized_to_table_and_webclient_payload() -> None:
    topology = build_two_signal_topology()
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_REVERSE)

    generator = InterlockingTableGenerator(topology)
    rows = generator.generate(["ENTRY"], ["EXIT"])
    markdown = generator.to_markdown(rows)
    payload = build_webclient_runtime_state(
        topology=topology,
        workspace_mode=AppMode.RUNTIME,
        generated_at=1.0,
    )
    payload_row = next(
        item
        for item in payload["interlocking_rows"]
        if item["entry_signal"] == "ENTRY" and item["exit_signal"] == "EXIT"
    )

    assert rows[0].is_calling_on is False
    assert rows[0].is_reverse is True
    assert "Reverse Route" in markdown
    assert "Calling-on Route" in markdown
    assert "Signal Aspect" in markdown
    assert "YELLOW_BLUE" in markdown
    assert "\\u221a" not in markdown
    assert "\u221a" in markdown
    assert payload_row["calling_on_route"] is False
    assert payload_row["reverse_route"] is True
    assert payload_row["is_calling_on"] is False
    assert payload_row["is_reverse"] is True
    assert payload_row["signal_aspect"] == SignalAspect.YELLOW_BLUE.value


def test_route_signal_aspect_round_trip_and_legacy_tokens(tmp_path) -> None:
    topology = build_two_signal_topology()
    topology.set_route_type("ENTRY", "EXIT", ROUTE_TYPE_REVERSE)
    topology.set_route_signal_aspect("ENTRY", "EXIT", "GREEN_BLUE")

    path = tmp_path / "layout.json"
    topology.export_to_json(path, include_runtime_state=True)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["signals"][0]["aspect"] = "STOP"
    raw["route_signal_aspects"]["ENTRY->EXIT"] = "BLUE_GREEN"
    path.write_text(json.dumps(raw), encoding="utf-8")

    loaded = RailwayTopology.load_from_json(path, load_runtime_state=True)

    assert loaded.signals["ENTRY"].aspect == SignalAspect.RED
    assert loaded.route_signal_aspect("ENTRY", "EXIT") == SignalAspect.GREEN_BLUE
