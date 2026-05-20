"""Palette of draggable railway components and properties panel."""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QMimeData, Qt, pyqtSignal
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

from core.domain.model.elements import (
    PointPosition,
    PointSymbolOrientation,
    SignalAspect,
    SignalDirection,
)
from ui.i18n import UITranslator

POINT_SYMBOL_CHOICES: tuple[tuple[str, PointSymbolOrientation], ...] = (
    ("1", PointSymbolOrientation.RIGHT),
    ("2", PointSymbolOrientation.DOWN),
    ("3", PointSymbolOrientation.LEFT),
    ("4", PointSymbolOrientation.UP),
)
ANNOTATION_LABEL_TYPES = {"AnnotationLabel", "Label"}


class PaletteListWidget(QListWidget):
    """List widget that starts drag operations for component types."""

    COMPONENT_MIME = "application/x-rail-component"
    COMPONENTS: tuple[tuple[str, str], ...] = (
        ("palette.component.section", "TrackSection"),
        ("palette.component.approach", "ApproachSection"),
        ("palette.component.point", "Point"),
        ("palette.component.signal", "Signal"),
    )

    def __init__(self, translator: UITranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.setDragEnabled(True)
        self.setDefaultDropAction(Qt.DropAction.CopyAction)
        self.retranslate_ui()

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    def set_translator(self, translator: UITranslator) -> None:
        self._translator = translator
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        current_element_type = ""
        current_item = self.currentItem()
        if current_item is not None:
            current_element_type = str(current_item.data(Qt.ItemDataRole.UserRole))

        self.clear()
        for label_key, element_type in self.COMPONENTS:
            self._add_component(self._t(label_key), element_type)

        if not current_element_type:
            return
        for index in range(self.count()):
            item = self.item(index)
            if str(item.data(Qt.ItemDataRole.UserRole)) != current_element_type:
                continue
            self.setCurrentItem(item)
            break

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
            painter.drawLine(
                int(panel_left + 1),
                int(panel_mid_y),
                int(panel_left + panel_w - 1),
                int(panel_mid_y),
            )
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

    def __init__(self, translator: UITranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator
        self._selected_id: str | None = None
        self._selected_type: str | None = None
        self._inputs: dict[str, Any] = {}
        self._current_payload: dict[str, Any] | None = None

        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600;")
        self.form_container = QFrame()
        self.form_layout = QFormLayout(self.form_container)
        self.form_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.apply_button = QPushButton()
        self.apply_button.clicked.connect(self._apply)
        self.apply_button.setEnabled(False)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title)
        layout.addWidget(self.form_container)
        layout.addWidget(self.apply_button)
        layout.addStretch(1)

        self.retranslate_ui()

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    def retranslate_ui(self) -> None:
        self.title.setText(self._t("properties.title"))
        self.apply_button.setText(self._t("button.apply"))
        self.set_element(self._current_payload)

    def set_translator(self, translator: UITranslator) -> None:
        self._translator = translator
        self.retranslate_ui()

    @staticmethod
    def _is_signal_type(element_type: str | None) -> bool:
        return element_type in {"Signal", "SignalLeft", "SignalRight", "SignalUp", "SignalDown"}

    def _render_placeholder(self) -> None:
        self._clear_form()
        placeholder = QLabel(self._t("properties.placeholder"))
        placeholder.setWordWrap(True)
        self.form_layout.addRow(placeholder)

    def set_element(self, payload: dict[str, Any] | None) -> None:
        """Populate panel from selected node payload."""
        self._current_payload = payload
        self._clear_form()
        self._inputs.clear()
        self._selected_id = None
        self._selected_type = None
        self.apply_button.setEnabled(False)

        if not payload:
            self._render_placeholder()
            return

        self._selected_id = str(payload["id"])
        self._selected_type = str(payload["type"])
        id_input = QLineEdit(self._selected_id)
        id_input.setPlaceholderText(self._t("field.element_id_placeholder"))
        self._inputs["id"] = id_input
        self.form_layout.addRow(self._t("field.id"), id_input)
        properties = dict(payload.get("properties", {}))

        if self._selected_type in {"TrackSection", "ApproachSection"}:
            length_input = QDoubleSpinBox()
            length_input.setRange(1.0, 10000.0)
            length_input.setValue(float(properties.get("length", 100.0)))
            state_input = QComboBox()
            state_input.addItem(self._t("state.free"), False)
            state_input.addItem(self._t("state.occupied"), True)
            state_input.setCurrentIndex(1 if properties.get("occupied", False) else 0)
            self._inputs["length"] = length_input
            self._inputs["state"] = state_input
            self.form_layout.addRow(self._t("field.length"), length_input)
            self.form_layout.addRow(self._t("field.state"), state_input)

        elif self._selected_type == "Point":
            position_input = QComboBox()
            position_input.addItem(self._t("point_position.normal"), PointPosition.NORMAL.value)
            position_input.addItem(self._t("point_position.reverse"), PointPosition.REVERSE.value)
            current_position = str(properties.get("position", PointPosition.NORMAL.value))
            position_index = position_input.findData(current_position)
            position_input.setCurrentIndex(position_index if position_index >= 0 else 0)

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
            self._inputs["position"] = position_input
            self._inputs["symbol_orientation"] = symbol_orientation_input
            self._inputs["normal_target"] = normal_target
            self._inputs["reverse_target"] = reverse_target
            self.form_layout.addRow(self._t("field.position"), position_input)
            self.form_layout.addRow(self._t("field.symbol"), symbol_orientation_input)
            self.form_layout.addRow(self._t("field.normal_to"), normal_target)
            self.form_layout.addRow(self._t("field.reverse_to"), reverse_target)

        elif self._is_signal_type(self._selected_type):
            protects_input = QLineEdit(str(properties.get("protects", "")))
            approach_section_input = QLineEdit(str(properties.get("approach_section", "")))

            aspect_input = QComboBox()
            aspect_input.addItem(self._t("signal_aspect.stop"), SignalAspect.STOP.value)
            aspect_input.addItem(self._t("signal_aspect.proceed"), SignalAspect.PROCEED.value)
            current_aspect = str(properties.get("aspect", SignalAspect.STOP.value))
            aspect_index = aspect_input.findData(current_aspect)
            aspect_input.setCurrentIndex(aspect_index if aspect_index >= 0 else 0)

            direction_input = QComboBox()
            direction_input.addItem(self._t("signal_direction.left"), SignalDirection.LEFT.value)
            direction_input.addItem(self._t("signal_direction.right"), SignalDirection.RIGHT.value)
            default_direction = (
                SignalDirection.LEFT.value
                if self._selected_type in {"SignalLeft", "SignalDown"}
                else SignalDirection.RIGHT.value
            )
            current_direction = str(properties.get("direction", default_direction))
            direction_index = direction_input.findData(current_direction)
            direction_input.setCurrentIndex(direction_index if direction_index >= 0 else 0)

            self._inputs["protects"] = protects_input
            self._inputs["approach_section"] = approach_section_input
            self._inputs["aspect"] = aspect_input
            self._inputs["direction"] = direction_input
            self.form_layout.addRow(self._t("field.protects"), protects_input)
            self.form_layout.addRow(self._t("field.approach_section"), approach_section_input)
            self.form_layout.addRow(self._t("field.direction"), direction_input)
            self.form_layout.addRow(self._t("field.aspect"), aspect_input)

        elif self._selected_type in ANNOTATION_LABEL_TYPES:
            text_input = QLineEdit(str(properties.get("text", "LABEL")))
            font_size_input = QDoubleSpinBox()
            font_size_input.setRange(6.0, 96.0)
            font_size_input.setValue(float(properties.get("font_size", 18.0)))
            self._inputs["text"] = text_input
            self._inputs["font_size"] = font_size_input
            self.form_layout.addRow(self._t("field.text"), text_input)
            self.form_layout.addRow(self._t("field.font_size"), font_size_input)

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
            state_data = self._inputs["state"].currentData()
            updated["occupied"] = bool(state_data) if state_data is not None else False
        elif self._selected_type == "Point":
            updated["position"] = str(
                self._inputs["position"].currentData() or PointPosition.NORMAL.value
            )
            symbol_orientation = self._inputs["symbol_orientation"].currentData()
            updated["symbol_orientation"] = str(
                symbol_orientation or self._inputs["symbol_orientation"].currentText()
            )
            updated["normal_target"] = str(self._inputs["normal_target"].text()).strip()
            updated["reverse_target"] = str(self._inputs["reverse_target"].text()).strip()
        elif self._is_signal_type(self._selected_type):
            updated["protects"] = str(self._inputs["protects"].text()).strip()
            updated["approach_section"] = str(self._inputs["approach_section"].text()).strip()
            updated["direction"] = str(
                self._inputs["direction"].currentData() or SignalDirection.RIGHT.value
            )
            updated["aspect"] = str(self._inputs["aspect"].currentData() or SignalAspect.STOP.value)
        elif self._selected_type in ANNOTATION_LABEL_TYPES:
            updated["text"] = str(self._inputs["text"].text()).strip() or "LABEL"
            updated["font_size"] = float(self._inputs["font_size"].value())
        updated["id"] = str(self._inputs["id"].text()).strip()
        self.properties_applied.emit(self._selected_id, updated)


class ComponentsPalette(QWidget):
    """Combined component palette and selected component properties."""

    component_insert_requested = pyqtSignal(str)
    label_insert_requested = pyqtSignal()
    properties_applied = pyqtSignal(str, dict)

    def __init__(self, translator: UITranslator, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._translator = translator

        self.title_label = QLabel()
        self.title_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        self.component_list = PaletteListWidget(self._translator)
        self.component_list.itemDoubleClicked.connect(self._on_component_double_clicked)

        self.add_label_button = QPushButton()
        self.add_label_button.clicked.connect(self.label_insert_requested.emit)

        self.hint_label = QLabel()
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet("color: #4b5563; font-size: 11px;")

        self.properties_panel = PropertiesPanel(self._translator)
        self.properties_panel.properties_applied.connect(self.properties_applied.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.title_label)
        layout.addWidget(self.component_list)
        layout.addWidget(self.add_label_button)
        layout.addWidget(self.hint_label)
        layout.addWidget(self.properties_panel)

        self.retranslate_ui()

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    def set_translator(self, translator: UITranslator) -> None:
        self._translator = translator
        self.component_list.set_translator(translator)
        self.properties_panel.set_translator(translator)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.title_label.setText(self._t("palette.components"))
        self.add_label_button.setText(self._t("palette.add_label"))
        self.hint_label.setText(self._t("palette.hint"))

    def set_selected_element(self, payload: dict[str, Any] | None) -> None:
        """Update properties pane for selected node."""
        self.properties_panel.set_element(payload)

    def _on_component_double_clicked(self, item: QListWidgetItem) -> None:
        component_name = str(item.data(Qt.ItemDataRole.UserRole))
        self.component_insert_requested.emit(component_name)
