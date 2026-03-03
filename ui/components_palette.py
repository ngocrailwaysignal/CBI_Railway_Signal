"""Palette of draggable railway components and properties panel."""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QMimeData, pyqtSignal, Qt
from PyQt6.QtGui import QColor, QDrag, QIcon, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.elements import PointPosition, PointSymbolOrientation, SignalAspect, SignalDirection

POINT_SYMBOL_CHOICES: tuple[tuple[str, PointSymbolOrientation], ...] = (
    ("1", PointSymbolOrientation.RIGHT),
    ("2", PointSymbolOrientation.DOWN),
    ("3", PointSymbolOrientation.LEFT),
    ("4", PointSymbolOrientation.UP),
)


class PaletteListWidget(QListWidget):
    """List widget that starts drag operations for component types."""

    COMPONENT_MIME = "application/x-rail-component"

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self._add_component("Section", "TrackSection")
        self._add_component("Approach", "ApproachSection")
        self._add_component("Point", "Point")
        self._add_component("Signal", "Signal")

    def _add_component(self, label: str, element_type: str) -> None:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, element_type)
        item.setIcon(QIcon(self._create_icon(element_type)))
        self.addItem(item)

    def _create_icon(self, element_type: str) -> QPixmap:
        pix = QPixmap(44, 28)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#141414"), 1.2))
        painter.setBrush(Qt.GlobalColor.white)
        painter.drawRect(3, 3, 38, 22)

        if element_type in {"TrackSection", "ApproachSection"}:
            painter.drawText(0, 0, 44, 28, int(Qt.AlignmentFlag.AlignCenter), "S")
            if element_type == "ApproachSection":
                painter.drawText(2, 17, 40, 10, int(Qt.AlignmentFlag.AlignCenter), "A")
        elif element_type == "Point":
            panel_left, panel_top, panel_w, panel_h = 10, 4, 24, 20
            panel_mid_y = panel_top + panel_h / 2
            painter.drawRect(panel_left, panel_top, panel_w, panel_h)
            painter.drawLine(int(panel_left + 1), int(panel_mid_y), int(panel_left + panel_w - 1), int(panel_mid_y))
            painter.drawLine(
                int(panel_left + 1),
                int(panel_mid_y),
                int(panel_left + panel_w - 1),
                int(panel_top + panel_h - 1),
            )
            label_y = panel_top + 1
            painter.drawText(
                panel_left + 2,
                label_y,
                panel_w - 4,
                int(panel_h / 2) - 2,
                int(Qt.AlignmentFlag.AlignCenter),
                "3",
            )
        else:
            is_left = element_type in {"SignalLeft", "SignalDown"}
            head_x = 30 if is_left else 10
            line_start_x = head_x - 4 if is_left else head_x + 4
            line_end_x = 10 if is_left else 30
            stop_bar_x = 8 if is_left else 32
            painter.setBrush(Qt.GlobalColor.white)
            painter.drawEllipse(head_x - 4, 6, 8, 8)
            painter.drawLine(line_start_x, 10, line_end_x, 10)
            painter.drawLine(stop_bar_x, 6, stop_bar_x, 14)
        painter.end()
        return pix

    def startDrag(self, _supported_actions: Qt.DropAction) -> None:
        selected = self.selectedItems()
        item = selected[0] if selected else self.currentItem()
        if item is None:
            return
        component_name = str(item.data(Qt.ItemDataRole.UserRole))
        mime_data = QMimeData()
        mime_data.setData(self.COMPONENT_MIME, component_name.encode("utf-8"))
        mime_data.setText(component_name)
        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.CopyAction)


class PropertiesPanel(QWidget):
    """Dynamic properties panel for selected canvas node."""

    properties_applied = pyqtSignal(str, dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._selected_id: Optional[str] = None
        self._selected_type: Optional[str] = None
        self._inputs: dict[str, Any] = {}

        self.title = QLabel("Properties")
        self.title.setStyleSheet("font-weight: 600;")
        self.form_container = QFrame()
        self.form_layout = QFormLayout(self.form_container)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.placeholder = QLabel("Select a block to edit its properties.")
        self.placeholder.setWordWrap(True)
        self.form_layout.addRow(self.placeholder)

        self.apply_button = QPushButton("Apply")
        self.apply_button.clicked.connect(self._apply)
        self.apply_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.form_container)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)

    @staticmethod
    def _is_signal_type(element_type: str | None) -> bool:
        return element_type in {"Signal", "SignalLeft", "SignalRight", "SignalUp", "SignalDown"}

    def set_element(self, payload: Optional[dict[str, Any]]) -> None:
        """Populate panel from selected node payload."""
        self._clear_form()
        self._inputs.clear()
        self._selected_id = None
        self._selected_type = None
        self.apply_button.setEnabled(False)

        if not payload:
            self.form_layout.addRow(QLabel("Select a block to edit its properties."))
            return

        self._selected_id = str(payload["id"])
        self._selected_type = str(payload["type"])
        id_input = QLineEdit(self._selected_id)
        id_input.setPlaceholderText("Element ID")
        self._inputs["id"] = id_input
        self.form_layout.addRow("ID", id_input)
        properties = dict(payload.get("properties", {}))

        if self._selected_type in {"TrackSection", "ApproachSection"}:
            length_input = QDoubleSpinBox()
            length_input.setRange(1.0, 10000.0)
            length_input.setValue(float(properties.get("length", 100.0)))
            state_input = QComboBox()
            state_input.addItems(["FREE", "OCCUPIED"])
            state_input.setCurrentText("OCCUPIED" if properties.get("occupied", False) else "FREE")
            locked_by_input = QLineEdit(str(properties.get("locked_by") or ""))
            self._inputs["length"] = length_input
            self._inputs["state"] = state_input
            self._inputs["locked_by"] = locked_by_input
            self.form_layout.addRow("Length", length_input)
            self.form_layout.addRow("State", state_input)
            self.form_layout.addRow("Locked by", locked_by_input)

        elif self._selected_type == "Point":
            position_input = QComboBox()
            position_input.addItems([PointPosition.NORMAL.value, PointPosition.REVERSE.value])
            position_input.setCurrentText(str(properties.get("position", PointPosition.NORMAL.value)))
            symbol_orientation_input = QComboBox()
            for label, orientation in POINT_SYMBOL_CHOICES:
                symbol_orientation_input.addItem(label, orientation.value)
            current_orientation = str(
                properties.get("symbol_orientation", PointSymbolOrientation.RIGHT.value)
            )
            symbol_index = symbol_orientation_input.findData(current_orientation)
            symbol_orientation_input.setCurrentIndex(symbol_index if symbol_index >= 0 else 0)
            normal_target = QLineEdit(str(properties.get("normal_target", "")))
            reverse_target = QLineEdit(str(properties.get("reverse_target", "")))
            locked_by_input = QLineEdit(str(properties.get("locked_by") or ""))
            self._inputs["position"] = position_input
            self._inputs["symbol_orientation"] = symbol_orientation_input
            self._inputs["normal_target"] = normal_target
            self._inputs["reverse_target"] = reverse_target
            self._inputs["locked_by"] = locked_by_input
            self.form_layout.addRow("Position", position_input)
            self.form_layout.addRow("Symbol", symbol_orientation_input)
            self.form_layout.addRow("Normal ->", normal_target)
            self.form_layout.addRow("Reverse ->", reverse_target)
            self.form_layout.addRow("Locked by", locked_by_input)

        elif self._is_signal_type(self._selected_type):
            protects_input = QLineEdit(str(properties.get("protects", "")))
            approach_section_input = QLineEdit(str(properties.get("approach_section", "")))
            aspect_input = QComboBox()
            aspect_input.addItems([SignalAspect.STOP.value, SignalAspect.PROCEED.value])
            aspect_input.setCurrentText(str(properties.get("aspect", SignalAspect.STOP.value)))
            direction_input = QComboBox()
            direction_input.addItems([SignalDirection.LEFT.value, SignalDirection.RIGHT.value])
            default_direction = (
                SignalDirection.LEFT.value
                if self._selected_type in {"SignalLeft", "SignalDown"}
                else SignalDirection.RIGHT.value
            )
            direction_input.setCurrentText(
                str(properties.get("direction", default_direction))
            )
            self._inputs["protects"] = protects_input
            self._inputs["approach_section"] = approach_section_input
            self._inputs["aspect"] = aspect_input
            self._inputs["direction"] = direction_input
            self.form_layout.addRow("Protects", protects_input)
            self.form_layout.addRow("Approach section", approach_section_input)
            self.form_layout.addRow("Direction", direction_input)
            self.form_layout.addRow("Aspect", aspect_input)

        self.apply_button.setEnabled(True)

    def _clear_form(self) -> None:
        while self.form_layout.count():
            item = self.form_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _apply(self) -> None:
        if not self._selected_id or not self._selected_type:
            return
        updated: dict[str, Any] = {}
        if self._selected_type in {"TrackSection", "ApproachSection"}:
            updated["length"] = float(self._inputs["length"].value())
            updated["occupied"] = self._inputs["state"].currentText() == "OCCUPIED"
            updated["locked_by"] = str(self._inputs["locked_by"].text()).strip()
        elif self._selected_type == "Point":
            updated["position"] = str(self._inputs["position"].currentText())
            symbol_orientation = self._inputs["symbol_orientation"].currentData()
            updated["symbol_orientation"] = str(
                symbol_orientation or self._inputs["symbol_orientation"].currentText()
            )
            updated["normal_target"] = str(self._inputs["normal_target"].text()).strip()
            updated["reverse_target"] = str(self._inputs["reverse_target"].text()).strip()
            updated["locked_by"] = str(self._inputs["locked_by"].text()).strip()
        elif self._is_signal_type(self._selected_type):
            updated["protects"] = str(self._inputs["protects"].text()).strip()
            updated["approach_section"] = str(self._inputs["approach_section"].text()).strip()
            updated["direction"] = str(self._inputs["direction"].currentText())
            updated["aspect"] = str(self._inputs["aspect"].currentText())
        updated["id"] = str(self._inputs["id"].text()).strip()
        self.properties_applied.emit(self._selected_id, updated)


class ComponentsPalette(QWidget):
    """Combined component palette and selected component properties."""

    component_insert_requested = pyqtSignal(str)
    properties_applied = pyqtSignal(str, dict)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        title = QLabel("Components")
        title.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.component_list = PaletteListWidget()
        self.component_list.itemDoubleClicked.connect(self._on_component_double_clicked)
        hint = QLabel(
            "Drag modules to canvas (or double-click to add). Use Connect Mode (2 clicks) or Connect Selected. Right-click or use Delete/F2 to edit."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #4b5563; font-size: 11px;")
        self.properties_panel = PropertiesPanel()
        self.properties_panel.properties_applied.connect(self.properties_applied.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(title)
        layout.addWidget(self.component_list)
        layout.addWidget(hint)
        layout.addWidget(self.properties_panel)

    def set_selected_element(self, payload: Optional[dict[str, Any]]) -> None:
        """Update properties pane for selected node."""
        self.properties_panel.set_element(payload)

    def _on_component_double_clicked(self, item: QListWidgetItem) -> None:
        component_name = str(item.data(Qt.ItemDataRole.UserRole))
        self.component_insert_requested.emit(component_name)
