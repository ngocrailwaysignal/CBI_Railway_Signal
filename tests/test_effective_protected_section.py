from __future__ import annotations

import csv

from core.compiler.interlocking_table import InterlockingTableGenerator, InterlockingTableRow
from core.compiler.route_compiler import RouteCompiler
from core.compiler.spec_models import InterlockingRouteSpec
from core.domain.model.elements import Point, PointPosition, Signal, SignalAspect, TrackSection
from core.domain.model.topology import ROUTE_TYPE_REVERSE, RailwayTopology
from kernel.route_dispatcher.route_engine import RouteEngine
from runtime.application import AppMode
from runtime.application.serialization import build_webclient_runtime_state


def build_branching_topology() -> RailwayTopology:
    topology = RailwayTopology()
    for section_id in ("N1", "N2", "R1", "R2"):
        topology.add_section(TrackSection(section_id))
    topology.add_point(Point("P1"))
    topology.add_signal(Signal("ENTRY", protects="P1"))
    topology.add_signal(Signal("EXIT_N", protects="N2"))
    topology.add_signal(Signal("EXIT_R", protects="R2"))
    topology.add_signal(Signal("SECTION_ENTRY", protects="N1"))

    topology.connect("P1", "N1")
    topology.connect("P1", "R1")
    topology.connect("N1", "N2")
    topology.connect("R1", "R2")
    topology.connect("N1", "EXIT_N")
    topology.connect("R1", "EXIT_R")
    topology.connect("N2", "EXIT_R")
    topology.connect("SECTION_ENTRY", "N1")
    topology.sync_signal_virtual_routes()
    return topology


def build_linear_multi_exit_topology() -> RailwayTopology:
    topology = RailwayTopology()
    for section_id in ("S1", "S2", "S3", "S4", "S5"):
        topology.add_section(TrackSection(section_id))
    topology.add_signal(Signal("ENTRY", protects="S1"))
    topology.add_signal(Signal("EXIT_NEAR", protects="S3"))
    topology.add_signal(Signal("EXIT_FAR", protects="S5"))

    topology.connect("ENTRY", "S1")
    topology.connect("S1", "S2")
    topology.connect("S2", "S3")
    topology.connect("S3", "S4")
    topology.connect("S4", "S5")
    topology.connect("S2", "EXIT_NEAR")
    topology.connect("EXIT_NEAR", "S3")
    topology.connect("S4", "EXIT_FAR")
    topology.connect("EXIT_FAR", "S5")
    topology.sync_signal_virtual_routes()
    return topology


def build_equal_distance_exit_topology() -> RailwayTopology:
    topology = RailwayTopology()
    for section_id in ("S0", "A1", "A2", "B1", "B2"):
        topology.add_section(TrackSection(section_id))
    topology.add_signal(Signal("ENTRY", protects="S0"))
    topology.add_signal(Signal("EXIT_A", protects="A2"))
    topology.add_signal(Signal("EXIT_B", protects="B2"))

    topology.connect("ENTRY", "S0")
    topology.connect("S0", "A1")
    topology.connect("S0", "B1")
    topology.connect("A1", "EXIT_A")
    topology.connect("EXIT_A", "A2")
    topology.connect("B1", "EXIT_B")
    topology.connect("EXIT_B", "B2")
    topology.sync_signal_virtual_routes()
    return topology


def test_signal_protecting_point_resolves_first_downstream_section_per_route() -> None:
    topology = build_branching_topology()
    route_engine = RouteEngine(topology)

    normal_route = route_engine.find_route("ENTRY", "EXIT_N")
    reverse_route = route_engine.find_route("ENTRY", "EXIT_R")

    assert normal_route.path == ["P1", "N1"]
    assert normal_route.required_point_positions["P1"] == PointPosition.NORMAL
    assert route_engine.resolve_effective_protected_section("ENTRY", normal_route.path) == "N1"

    assert reverse_route.path == ["P1", "R1"]
    assert reverse_route.required_point_positions["P1"] == PointPosition.REVERSE
    assert route_engine.resolve_effective_protected_section("ENTRY", reverse_route.path) == "R1"


def test_signal_protecting_track_section_resolves_that_section() -> None:
    topology = build_branching_topology()
    route_engine = RouteEngine(topology)

    assert route_engine.resolve_effective_protected_section("SECTION_ENTRY", ["N1", "N2"]) == "N1"


def test_interlocking_outputs_raw_protected_node_and_effective_section() -> None:
    topology = build_branching_topology()
    topology.set_route_type("ENTRY", "EXIT_R", ROUTE_TYPE_REVERSE)
    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_N", "EXIT_R"],
    )

    by_exit = {row.exit_signal: row for row in rows}
    assert by_exit["EXIT_N"].entry_element == "P1"
    assert by_exit["EXIT_N"].entry_protected_section == "N1"
    assert by_exit["EXIT_R"].entry_element == "P1"
    assert by_exit["EXIT_R"].entry_protected_section == "R1"

    spec = RouteCompiler().compile(topology, overlap_length=0, station_id="TEST")
    spec_rows = {
        route.exit_signal: route
        for route in spec.routes
        if route.entry_signal == "ENTRY" and route.exit_signal in {"EXIT_N", "EXIT_R"}
    }
    assert spec_rows["EXIT_N"].to_dict()["entry_element"] == "P1"
    assert spec_rows["EXIT_N"].to_dict()["entry_protected_section"] == "N1"
    assert spec_rows["EXIT_R"].to_dict()["entry_protected_section"] == "R1"

    restored = InterlockingRouteSpec.from_dict(spec_rows["EXIT_N"].to_dict())
    assert restored.entry_element == "P1"
    assert restored.entry_protected_section == "N1"


def test_interlocking_generates_only_nearest_exit_for_each_entry() -> None:
    topology = build_linear_multi_exit_topology()

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_NEAR", "EXIT_FAR"],
    )

    assert [row.exit_signal for row in rows] == ["EXIT_NEAR"]


def test_interlocking_tie_breaks_nearest_exit_by_signal_id() -> None:
    topology = build_equal_distance_exit_topology()

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_B", "EXIT_A"],
    )

    assert [row.exit_signal for row in rows] == ["EXIT_A"]


def test_interlocking_keeps_manual_reverse_route_beyond_nearest_exit() -> None:
    topology = build_linear_multi_exit_topology()
    topology.set_route_type("ENTRY", "EXIT_FAR", ROUTE_TYPE_REVERSE)

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_NEAR", "EXIT_FAR"],
    )

    by_exit = {row.exit_signal: row for row in rows}
    assert set(by_exit) == {"EXIT_NEAR", "EXIT_FAR"}
    assert by_exit["EXIT_NEAR"].is_reverse is False
    assert by_exit["EXIT_FAR"].is_reverse is True
    assert by_exit["EXIT_FAR"].signal_aspect == SignalAspect.YELLOW_BLUE


def test_interlocking_does_not_add_far_reverse_route_from_reverse_entry_only() -> None:
    topology = build_linear_multi_exit_topology()
    topology.signals["ENTRY"].is_reverse_signal = True

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_NEAR", "EXIT_FAR"],
    )

    assert [row.exit_signal for row in rows] == ["EXIT_NEAR"]
    assert rows[0].is_reverse is False


def test_interlocking_does_not_add_far_reverse_route_to_reverse_exit_only() -> None:
    topology = build_linear_multi_exit_topology()
    topology.signals["EXIT_FAR"].is_reverse_signal = True

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_NEAR", "EXIT_FAR"],
    )

    assert [row.exit_signal for row in rows] == ["EXIT_NEAR"]
    assert rows[0].is_reverse is False


def test_interlocking_adds_far_reverse_route_when_entry_and_exit_are_reverse_signals() -> None:
    topology = build_linear_multi_exit_topology()
    topology.signals["ENTRY"].is_reverse_signal = True
    topology.signals["EXIT_FAR"].is_reverse_signal = True

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_NEAR", "EXIT_FAR"],
    )

    by_exit = {row.exit_signal: row for row in rows}
    assert set(by_exit) == {"EXIT_NEAR", "EXIT_FAR"}
    assert by_exit["EXIT_NEAR"].is_reverse is False
    assert by_exit["EXIT_FAR"].is_reverse is True
    assert by_exit["EXIT_FAR"].signal_aspect == SignalAspect.YELLOW_BLUE


def test_interlocking_keeps_reverse_signal_nearest_route_normal() -> None:
    topology = build_linear_multi_exit_topology()
    topology.signals["EXIT_NEAR"].is_reverse_signal = True

    rows = InterlockingTableGenerator(topology).generate(
        entry_signal_ids=["ENTRY"],
        exit_signal_ids=["EXIT_NEAR", "EXIT_FAR"],
    )

    assert [row.exit_signal for row in rows] == ["EXIT_NEAR"]
    assert rows[0].is_reverse is False


def test_interlocking_export_splits_normal_and_reverse_point_columns(tmp_path) -> None:
    row = InterlockingTableRow(
        route_name="ENTRY->EXIT",
        entry_signal="ENTRY",
        exit_signal="EXIT",
        entry_element="P1",
        exit_element="S2",
        entry_protected_section="N1",
        exit_protected_section="S2",
        path=["P1", "N1", "P2", "S2"],
        overlap=[],
        required_point_positions={
            "P1": PointPosition.NORMAL,
            "P2": PointPosition.REVERSE,
        },
        flank_point_positions={},
        locked_sections=["N1", "S2"],
        conflicting_routes=[],
    )
    generator = InterlockingTableGenerator(RailwayTopology())

    markdown = generator.to_markdown([row])

    assert (
        "| Route | Entry | Exit | Signal Aspect | Entry protected section | "
        "Exit protected section | Normal | Reverse |"
    ) in markdown
    assert "| ENTRY->EXIT | ENTRY (P1) | EXIT (S2) | GREEN | N1 | S2 | P1 | P2 |" in markdown

    csv_path = tmp_path / "interlocking.csv"
    generator.export_csv([row], csv_path)
    csv_rows = list(csv.reader(csv_path.open(newline="", encoding="utf-8")))

    assert "normal_points" in csv_rows[0]
    assert "reverse_points" in csv_rows[0]
    assert "signal_aspect" in csv_rows[0]
    assert csv_rows[1][csv_rows[0].index("normal_points")] == "P1"
    assert csv_rows[1][csv_rows[0].index("reverse_points")] == "P2"
    assert csv_rows[1][csv_rows[0].index("signal_aspect")] == "GREEN"


def test_webclient_interlocking_payload_includes_split_point_columns() -> None:
    topology = build_branching_topology()
    topology.set_route_type("ENTRY", "EXIT_R", ROUTE_TYPE_REVERSE)

    payload = build_webclient_runtime_state(
        topology=topology,
        workspace_mode=AppMode.RUNTIME,
        generated_at=1.0,
    )

    entry_rows = [
        row
        for row in payload["interlocking_rows"]
        if row["entry_signal"] == "ENTRY" and row["exit_signal"] in {"EXIT_N", "EXIT_R"}
    ]
    assert entry_rows
    assert all("required_points" in row for row in entry_rows)
    assert any(row["normal_points"] == ["P1"] for row in entry_rows)
    assert any(row["reverse_points"] == ["P1"] for row in entry_rows)
