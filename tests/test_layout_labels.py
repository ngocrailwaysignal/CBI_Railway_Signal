from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from core.domain.model import DisplayLabel, DisplayLine, TrackSection
from core.domain.model.elements import SignalAspect
from core.domain.model.topology import RailwayTopology
from runtime.application.serialization.layout_payload_serializer import build_layout_payload
from ui.i18n import UITranslator
from ui.views.canvas_editor_view import ANNOTATION_LABEL_NODE_TYPE, ANNOTATION_LINE_TYPE, CanvasEditor
from ui.views.components_palette_view import PaletteListWidget, PropertiesPanel


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_display_label_round_trips_with_layout_json(tmp_path: Path) -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"), position=(10.0, 20.0))
    topology.add_label(
        DisplayLabel("LBL1", text="Platform A", font_size=24.0), position=(30.0, 40.0)
    )

    path = tmp_path / "layout.json"
    topology.export_to_json(path)

    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    assert raw_payload["labels"] == [
        {
            "id": "LBL1",
            "text": "Platform A",
            "font_size": 24.0,
            "color": "#111111",
            "width": 120.0,
            "height": 48.0,
        }
    ]
    assert raw_payload["ui_positions"]["LBL1"] == [30.0, 40.0]

    loaded = RailwayTopology.load_from_json(path)
    assert loaded.labels["LBL1"].text == "Platform A"
    assert loaded.labels["LBL1"].font_size == 24.0
    assert loaded.labels["LBL1"].color == "#111111"
    assert loaded.labels["LBL1"].width == 120.0
    assert loaded.labels["LBL1"].height == 48.0
    assert loaded.ui_positions["LBL1"] == (30.0, 40.0)
    assert "LBL1" not in loaded.graph.nodes


def test_display_label_missing_color_loads_with_default(tmp_path: Path) -> None:
    payload = {
        "sections": [],
        "points": [],
        "signals": [],
        "labels": [{"id": "LBL1", "text": "Legacy", "font_size": 18.0}],
        "edges": [],
        "signal_links": [],
        "ui_positions": {"LBL1": [10.0, 20.0]},
    }
    path = tmp_path / "legacy_layout.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = RailwayTopology.load_from_json(path)

    assert loaded.labels["LBL1"].color == "#111111"
    assert loaded.labels["LBL1"].width == 120.0
    assert loaded.labels["LBL1"].height == 48.0


def test_display_label_is_in_layout_payload_but_not_routing_graph() -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"), position=(0.0, 0.0))
    topology.add_label(DisplayLabel("LBL1", text="Yard", font_size=18.0), position=(80.0, 0.0))

    payload = build_layout_payload(topology)

    assert payload["labels"] == [
        {
            "id": "LBL1",
            "text": "Yard",
            "font_size": 18.0,
            "color": "#111111",
            "width": 120.0,
            "height": 48.0,
        }
    ]
    assert payload["ui_positions"]["LBL1"] == [80.0, 0.0]
    assert "LBL1" not in topology.routing_graph().nodes


def test_annotation_line_round_trips_with_layout_json(tmp_path: Path) -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"), position=(10.0, 20.0))
    topology.add_annotation_line(
        DisplayLine(
            "LINE1",
            start=(30.0, 40.0),
            end=(150.0, 40.0),
            color="#111111",
            width=2.0,
        )
    )

    path = tmp_path / "layout.json"
    topology.export_to_json(path)

    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    assert raw_payload["annotation_lines"] == [
        {
            "id": "LINE1",
            "start": [30.0, 40.0],
            "end": [150.0, 40.0],
            "color": "#111111",
            "width": 2.0,
        }
    ]

    loaded = RailwayTopology.load_from_json(path)
    assert loaded.annotation_lines["LINE1"].start == (30.0, 40.0)
    assert loaded.annotation_lines["LINE1"].end == (150.0, 40.0)
    assert loaded.annotation_lines["LINE1"].color == "#111111"
    assert loaded.annotation_lines["LINE1"].width == 2.0
    assert "LINE1" not in loaded.graph.nodes


def test_annotation_line_is_in_layout_payload_but_not_routing_graph() -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"), position=(0.0, 0.0))
    topology.add_annotation_line(DisplayLine("LINE1", start=(0.0, 0.0), end=(120.0, 0.0)))

    payload = build_layout_payload(topology)

    assert payload["annotation_lines"] == [
        {
            "id": "LINE1",
            "start": [0.0, 0.0],
            "end": [120.0, 0.0],
            "color": "#111111",
            "width": 2.0,
        }
    ]
    assert "LINE1" not in topology.routing_graph().nodes


def test_display_label_cannot_be_connected() -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"))
    topology.add_label(DisplayLabel("LBL1"))

    with pytest.raises(ValueError, match="Display labels cannot be connected"):
        topology.connect("LBL1", "S1")


def test_annotation_line_cannot_be_connected() -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"))
    topology.add_annotation_line(DisplayLine("LINE1"))

    with pytest.raises(ValueError, match="Display annotation lines cannot be connected"):
        topology.connect("LINE1", "S1")


def test_display_label_is_not_a_palette_component() -> None:
    component_types = {component_type for _, component_type in PaletteListWidget.COMPONENTS}

    assert "Label" not in component_types


def test_canvas_label_creation_uses_annotation_api(qapp: QApplication) -> None:
    _ = qapp
    editor = CanvasEditor()
    try:
        with pytest.raises(ValueError, match="Unsupported element type"):
            editor.add_component("Label", QPointF(0.0, 0.0))

        node = editor.add_text_label(QPointF(30.0, 40.0))

        assert node.element_type == ANNOTATION_LABEL_NODE_TYPE
        assert node.element_id in editor.topology.labels
        assert node.element_id not in editor.topology.graph.nodes
        assert editor.topology.labels[node.element_id].width == 120.0
        assert editor.topology.labels[node.element_id].height == 48.0
    finally:
        editor.deleteLater()


def test_canvas_annotation_tools_create_by_click_and_cancel(qapp: QApplication) -> None:
    _ = qapp
    editor = CanvasEditor()
    try:
        editor.begin_text_label_placement()
        editor._begin_text_label_drag(QPointF(30.0, 40.0))
        assert editor._annotation_text_preview_rect is not None
        editor._finish_text_label_drag(QPointF(180.0, 95.0))

        assert "LBL1" in editor.topology.labels
        assert editor.topology.ui_positions["LBL1"] == (25.0, 50.0)
        assert editor.topology.labels["LBL1"].width == 150.0
        assert editor.topology.labels["LBL1"].height == 50.0
        assert editor.nodes["LBL1"].isSelected()
        assert editor._inline_label_proxy is not None
        widget = editor._inline_label_proxy.widget()
        assert widget is not None
        widget.setText("Route note")
        editor._finish_inline_label_edit(commit=True)
        assert editor.topology.labels["LBL1"].text == "Route note"

        editor.begin_annotation_line_drawing()
        editor._handle_annotation_tool_click(QPointF(5.0, 5.0))
        assert editor._annotation_preview_line is not None
        editor.cancel_annotation_tool()
        assert not editor.topology.annotation_lines

        editor.begin_annotation_line_drawing()
        editor._handle_annotation_tool_click(QPointF(0.0, 0.0))
        editor._handle_annotation_tool_click(QPointF(120.0, 25.0))

        assert editor.topology.annotation_lines["LINE1"].start == (0.0, 0.0)
        assert editor.topology.annotation_lines["LINE1"].end == (125.0, 25.0)
        assert editor.annotation_line_items["LINE1"].isSelected()
    finally:
        editor.deleteLater()


def test_canvas_new_label_inherits_selected_label_style(qapp: QApplication) -> None:
    _ = qapp
    editor = CanvasEditor()
    try:
        first = editor.add_text_label(QPointF(30.0, 40.0))
        editor.update_node_properties(
            first.element_id,
            {
                "font_size": 26.0,
                "color": "#d71920",
            },
        )
        first.setSelected(True)

        second = editor.add_text_label(QPointF(80.0, 40.0))

        assert editor.topology.labels[second.element_id].font_size == 26.0
        assert editor.topology.labels[second.element_id].color == "#d71920"
        assert editor.topology.labels[second.element_id].text == "LABEL"
    finally:
        editor.deleteLater()


def test_canvas_inline_label_edit_commits_and_cancels(qapp: QApplication) -> None:
    _ = qapp
    editor = CanvasEditor()
    try:
        node = editor.add_text_label(QPointF(30.0, 40.0))

        editor.start_inline_label_edit(node)
        assert editor._inline_label_proxy is not None
        widget = editor._inline_label_proxy.widget()
        widget.setText("Edited")
        editor._finish_inline_label_edit(commit=True)
        assert editor.topology.labels["LBL1"].text == "Edited"

        editor.start_inline_label_edit(node)
        assert editor._inline_label_proxy is not None
        widget = editor._inline_label_proxy.widget()
        widget.setText("Canceled")
        editor._finish_inline_label_edit(commit=False)
        assert editor.topology.labels["LBL1"].text == "Edited"
    finally:
        editor.deleteLater()


def test_inline_label_commit_refreshes_selected_properties(qapp: QApplication) -> None:
    _ = qapp
    editor = CanvasEditor()
    emitted: list[dict | None] = []
    editor.node_selected.connect(emitted.append)
    try:
        node = editor.add_text_label(QPointF(30.0, 40.0))
        node.setSelected(True)

        editor.start_inline_label_edit(node)
        assert editor._inline_label_proxy is not None
        widget = editor._inline_label_proxy.widget()
        assert widget is not None
        widget.setText("Do not overwrite")
        committed_id = editor.commit_inline_label_edit()

        assert committed_id == "LBL1"
        assert editor.topology.labels["LBL1"].text == "Do not overwrite"
        assert emitted[-1] is not None
        assert emitted[-1]["properties"]["text"] == "Do not overwrite"
    finally:
        editor.deleteLater()


def test_canvas_line_creation_and_properties_use_annotation_api(qapp: QApplication) -> None:
    _ = qapp
    editor = CanvasEditor()
    try:
        line_item = editor.add_annotation_line(QPointF(30.0, 40.0))

        assert line_item.line.id == "LINE1"
        assert line_item.line.id in editor.topology.annotation_lines
        assert line_item.line.id not in editor.topology.graph.nodes
        assert line_item.line.start == (25.0, 50.0)
        assert line_item.line.end == (145.0, 50.0)

        editor.update_node_properties(
            "LINE1",
            {
                "color": "#d71920",
                "width": 3.0,
                "start_x": 0.0,
                "start_y": 0.0,
                "end_x": 100.0,
                "end_y": 25.0,
            },
        )

        updated = editor.topology.annotation_lines["LINE1"]
        assert updated.color == "#d71920"
        assert updated.width == 3.0
        assert updated.start == (0.0, 0.0)
        assert updated.end == (100.0, 25.0)

        editor.rename_node("LINE1", "LINE2")
        assert "LINE1" not in editor.topology.annotation_lines
        assert "LINE2" in editor.topology.annotation_lines

        editor.delete_annotation_line(editor.annotation_line_items["LINE2"])
        assert "LINE2" not in editor.topology.annotation_lines
    finally:
        editor.deleteLater()


def test_properties_panel_emits_annotation_line_updates(qapp: QApplication) -> None:
    _ = qapp
    panel = PropertiesPanel(UITranslator())
    captured: list[tuple[str, dict]] = []
    panel.properties_applied.connect(lambda element_id, updates: captured.append((element_id, updates)))
    try:
        panel.set_element(
            {
                "id": "LINE1",
                "type": ANNOTATION_LINE_TYPE,
                "properties": {
                    "color": "#111111",
                    "width": 2.0,
                    "start_x": 0.0,
                    "start_y": 0.0,
                    "end_x": 120.0,
                    "end_y": 0.0,
                },
            }
        )

        panel._inputs["color"].setCurrentText("#d71920")
        panel._inputs["width"].setValue(4.0)
        panel._inputs["end_y"].setValue(25.0)
        panel._apply()

        assert captured[-1][0] == "LINE1"
        assert captured[-1][1]["color"] == "#d71920"
        assert captured[-1][1]["width"] == 4.0
        assert captured[-1][1]["end_y"] == 25.0
    finally:
        panel.deleteLater()


def test_properties_panel_emits_label_color_updates(qapp: QApplication) -> None:
    _ = qapp
    panel = PropertiesPanel(UITranslator())
    captured: list[tuple[str, dict]] = []
    panel.properties_applied.connect(lambda element_id, updates: captured.append((element_id, updates)))
    try:
        panel.set_element(
            {
                "id": "LBL1",
                "type": ANNOTATION_LABEL_NODE_TYPE,
                "properties": {
                    "text": "Old",
                    "font_size": 18.0,
                    "color": "#111111",
                    "width": 120.0,
                    "height": 48.0,
                },
            }
        )

        panel._inputs["text"].setText("New")
        panel._inputs["color"].setCurrentText("#2563eb")
        panel._inputs["width"].setValue(180.0)
        panel._inputs["height"].setValue(70.0)
        panel._apply()

        assert captured[-1][0] == "LBL1"
        assert captured[-1][1]["text"] == "New"
        assert captured[-1][1]["color"] == "#2563eb"
        assert captured[-1][1]["width"] == 180.0
        assert captured[-1][1]["height"] == 70.0
    finally:
        panel.deleteLater()


def test_signal_blocking_property_forces_stop_and_hides_route_type_controls(qapp: QApplication) -> None:
    _ = qapp
    panel = PropertiesPanel(UITranslator())
    captured: list[tuple[str, dict]] = []
    panel.properties_applied.connect(lambda element_id, updates: captured.append((element_id, updates)))
    try:
        panel.set_element(
            {
                "id": "S1",
                "type": "SignalRight",
                "properties": {
                    "aspect": SignalAspect.PROCEED.value,
                    "direction": "RIGHT",
                    "is_blocking": False,
                },
            }
        )

        assert "calling_on_entry_signal" not in panel._inputs
        assert "is_reverse_signal" not in panel._inputs
        assert "reverse_role" not in panel._inputs
        assert "reverse_pair_signal" not in panel._inputs

        panel._inputs["is_blocking"].setChecked(True)
        assert panel._inputs["aspect"].currentData() == SignalAspect.RED.value
        assert not panel._inputs["aspect"].isEnabled()

        panel._apply()
        assert captured[-1][0] == "S1"
        assert captured[-1][1]["aspect"] == SignalAspect.RED.value

        panel._inputs["is_blocking"].setChecked(False)
        panel._apply()
        assert captured[-1][1]["is_blocking"] is False
    finally:
        panel.deleteLater()
