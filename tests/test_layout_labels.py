from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QApplication

from core.domain.model import DisplayLabel, TrackSection
from core.domain.model.topology import RailwayTopology
from runtime.application.serialization.layout_payload_serializer import build_layout_payload
from ui.views.canvas_editor_view import ANNOTATION_LABEL_NODE_TYPE, CanvasEditor
from ui.views.components_palette_view import PaletteListWidget


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
    assert raw_payload["labels"] == [{"id": "LBL1", "text": "Platform A", "font_size": 24.0}]
    assert raw_payload["ui_positions"]["LBL1"] == [30.0, 40.0]

    loaded = RailwayTopology.load_from_json(path)
    assert loaded.labels["LBL1"].text == "Platform A"
    assert loaded.labels["LBL1"].font_size == 24.0
    assert loaded.ui_positions["LBL1"] == (30.0, 40.0)
    assert "LBL1" not in loaded.graph.nodes


def test_display_label_is_in_layout_payload_but_not_routing_graph() -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"), position=(0.0, 0.0))
    topology.add_label(DisplayLabel("LBL1", text="Yard", font_size=18.0), position=(80.0, 0.0))

    payload = build_layout_payload(topology)

    assert payload["labels"] == [{"id": "LBL1", "text": "Yard", "font_size": 18.0}]
    assert payload["ui_positions"]["LBL1"] == [80.0, 0.0]
    assert "LBL1" not in topology.routing_graph().nodes


def test_display_label_cannot_be_connected() -> None:
    topology = RailwayTopology()
    topology.add_section(TrackSection("S1"))
    topology.add_label(DisplayLabel("LBL1"))

    with pytest.raises(ValueError, match="Display labels cannot be connected"):
        topology.connect("LBL1", "S1")


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
    finally:
        editor.deleteLater()
