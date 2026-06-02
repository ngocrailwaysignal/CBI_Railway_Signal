"""Main application window for the geographical interlocking simulator."""

from __future__ import annotations

import json
import os
import sys
import time
from collections import deque
from contextlib import suppress
from pathlib import Path

from PyQt6.QtCore import QProcess, QRect, QSize, Qt, QTimer, QUrl
from PyQt6.QtGui import QCloseEvent, QDesktopServices, QPainter, QPaintEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from config import DEFAULT_APP_CONFIG
from core.compiler.interlocking_table import InterlockingTableGenerator, InterlockingTableRow
from core.domain.model.elements import PointPosition, SignalAspect, TrackSection
from core.domain.model.route import Route
from core.domain.model.topology import ROUTE_TYPE_CALLING_ON, ROUTE_TYPE_REVERSE
from kernel.route_dispatcher.route_engine import RouteEngine
from runtime import GenericApplicationProfile, GenericApplicationService, RuntimeWorkspaceService
from runtime.application import AppMode
from runtime.application.serialization import build_topology_revision
from runtime.journal_paths import (
    webclient_runtime_command_path,
    webclient_runtime_command_result_path,
    webclient_runtime_state_path,
)
from runtime.specific_application import SpecificLayoutEditorService, StationLayout
from ui.controllers import (
    MainWindowController,
    SmartIORuntimeCoordinator,
    SmartIOSessionAdapter,
    WorkspaceStateCoordinator,
)
from ui.exporters import write_xlsx_table
from ui.i18n import SUPPORTED_LANGUAGES, UITranslator, normalize_language
from ui.presenters import RoutePresenter
from ui.views.canvas_editor_view import CanvasEditor
from ui.views.components_palette_view import ComponentsPalette

OperatingMode = AppMode


class PointGroupedHeader(QHeaderView):
    """Two-level header for grouped point columns."""

    NORMAL_COLUMN = 4
    REVERSE_COLUMN = 5
    FLANK_NORMAL_COLUMN = 13
    FLANK_REVERSE_COLUMN = 14

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._labels: list[str] = []
        self._groups: list[tuple[str, int, int]] = []

    def set_labels(self, labels: list[str], groups: list[tuple[str, int, int]]) -> None:
        self._labels = labels
        self._groups = groups
        self.viewport().update()

    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        return QSize(hint.width(), max(hint.height(), 52))

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self.viewport())
        try:
            painter.fillRect(event.rect(), self.palette().button())
            painter.setPen(self.palette().mid().color())

            top_height = self.height() // 2
            bottom_height = self.height() - top_height
            grouped_columns: set[int] = set()
            for group_label, first_column, last_column in self._visible_groups():
                grouped_columns.update(range(first_column, last_column + 1))
                self._draw_group(painter, group_label, first_column, last_column, top_height)

            for logical_index in range(self.count()):
                if self.isSectionHidden(logical_index):
                    continue
                section_rect = QRect(
                    self.sectionViewportPosition(logical_index),
                    0,
                    self.sectionSize(logical_index),
                    self.height(),
                )
                if logical_index in grouped_columns:
                    label_rect = QRect(
                        section_rect.left(),
                        top_height,
                        section_rect.width(),
                        bottom_height,
                    )
                else:
                    label_rect = section_rect
                self._draw_header_cell(painter, label_rect, self._label_for(logical_index))
        finally:
            painter.end()

    def _visible_groups(self) -> list[tuple[str, int, int]]:
        groups: list[tuple[str, int, int]] = []
        for label, first_column, last_column in self._groups:
            if last_column >= self.count():
                continue
            if any(self.isSectionHidden(column) for column in range(first_column, last_column + 1)):
                continue
            groups.append((label, first_column, last_column))
        return groups

    def _draw_group(
        self,
        painter: QPainter,
        label: str,
        first_column: int,
        last_column: int,
        height: int,
    ) -> None:
        left = self.sectionViewportPosition(first_column)
        width = sum(self.sectionSize(column) for column in range(first_column, last_column + 1))
        self._draw_header_cell(painter, QRect(left, 0, width, height), label)

    def _draw_header_cell(self, painter: QPainter, rect: QRect, label: str) -> None:
        if not rect.isValid():
            return
        painter.fillRect(rect, self.palette().button())
        painter.setPen(self.palette().mid().color())
        painter.drawRect(rect.adjusted(0, 0, -1, -1))
        painter.setPen(self.palette().buttonText().color())
        painter.drawText(rect.adjusted(4, 0, -4, 0), int(Qt.AlignmentFlag.AlignCenter), label)

    def _label_for(self, logical_index: int) -> str:
        if 0 <= logical_index < len(self._labels):
            return self._labels[logical_index]
        return str(logical_index + 1)


class MainWindow(QMainWindow):
    """Top-level editor + simulator window."""

    SIGNAL_ASPECT_COLUMN = 3
    REVERSE_ROUTE_COLUMN = 6
    CALLING_ON_ROUTE_COLUMN = 7

    def __init__(self, application_profile: GenericApplicationProfile | None = None) -> None:
        super().__init__()
        self.resize(1700, 900)

        self.application_profile = application_profile or GenericApplicationProfile()
        self._translator = UITranslator(getattr(self.application_profile, "ui_language", "en"))
        self.application_service = GenericApplicationService(profile=self.application_profile)
        self.runtime_workspace_service = RuntimeWorkspaceService(
            profile=self.application_profile,
            kernel=self.application_service.kernel,
        )
        self.controller = MainWindowController(
            self.application_service,
            self.runtime_workspace_service,
        )
        self.workspace_state_coordinator = WorkspaceStateCoordinator()
        self.route_presenter = RoutePresenter(self._translator)
        self.mode_policy = self.application_service.mode_policy
        self.layout_editor_service = SpecificLayoutEditorService(self.application_service)
        self.current_layout = self.layout_editor_service.new_layout(station_id="UNNAMED")
        self._operating_mode = OperatingMode.DESIGN_LAYOUT
        self._smartio_status_token = "disabled"
        self._runtime_transport_health: dict[str, object] = {}
        self._smartio_local_process: QProcess | None = None
        self._simulation_uses_local_smartio = False
        self._webclient_process: QProcess | None = None
        self._webclient_browser_opened = False

        self.palette = ComponentsPalette(self._translator, self)
        self.canvas = CanvasEditor(self, translator=self._translator)
        self.canvas.set_manual_override_handler(self._manual_override_from_canvas)
        self.right_panel = self._build_right_panel()
        self.palette.properties_applied.connect(self._on_properties_applied)
        self.palette.component_insert_requested.connect(self._insert_component_from_palette)
        self.palette.label_insert_requested.connect(self._insert_text_label)
        self.palette.line_insert_requested.connect(self._insert_annotation_line)
        self.canvas.node_selected.connect(self.palette.set_selected_element)
        self.canvas.canvas_selection_changed.connect(self._sync_ui_state)
        self.canvas.topology_changed.connect(self._on_topology_changed)

        splitter = QSplitter(self)
        splitter.addWidget(self.palette)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([320, 930, 450])
        self.setCentralWidget(splitter)

        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.mode_status_label = QLabel(self)
        self.status.addPermanentWidget(self.mode_status_label)
        self.canvas.editor_message.connect(self.status.showMessage)
        self._build_toolbar()
        self._apply_visual_theme()

        self.canvas.set_runtime_view_state(None)
        self.preview_route: Route | None = None
        self.interlocking_rows: list[InterlockingTableRow] = []
        self.valid_route_pairs: set[tuple[str, str]] = set()
        self._interlocking_rows_cache: dict[tuple[str, int], list[InterlockingTableRow]] = {}
        self._simulation_timer = QTimer(self)
        self._simulation_timer.timeout.connect(self._simulation_tick)
        self._simulation_ticks_remaining = 0
        self._topology_change_timer = QTimer(self)
        self._topology_change_timer.setSingleShot(True)
        self._topology_change_timer.setInterval(50)
        self._topology_change_timer.timeout.connect(self._flush_topology_changed)
        self._webclient_runtime_timer = QTimer(self)
        self._webclient_runtime_timer.setInterval(
            int(
                getattr(
                    self.application_profile,
                    "webclient_runtime_publish_interval_ms",
                    DEFAULT_APP_CONFIG.webclient.runtime_publish_interval_ms,
                )
            )
        )
        self._webclient_runtime_timer.timeout.connect(self._publish_webclient_runtime_state)
        self._last_webclient_runtime_export_error = ""
        self._initialize_smartio_client()

        sample_path = self._repo_root() / str(
            getattr(
                self.application_profile,
                "default_layout_path",
                DEFAULT_APP_CONFIG.paths.default_layout_path,
            )
        )
        if sample_path.exists():
            self._load_layout_into_canvas(
                self.layout_editor_service.load_layout(
                    sample_path,
                    station_id=sample_path.stem,
                    load_runtime_state=False,
                    load_occupancy=True,
                )
            )
            self.status.showMessage(self._t("status.loaded_sample_layout", path=sample_path))
        else:
            self.canvas.load_topology(self.current_layout.topology, emit_change=False)
        self._set_operating_mode(OperatingMode.DESIGN_LAYOUT, announce=False)
        self._sync_ui_state()
        self._retranslate_ui()

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    @staticmethod
    def _mode_translation_key(mode: OperatingMode) -> str:
        if mode is OperatingMode.DESIGN_LAYOUT:
            return "mode.design_layout"
        if mode is OperatingMode.SIMULATION:
            return "mode.simulation"
        return "mode.runtime"

    def _mode_text(self, mode: OperatingMode) -> str:
        return self._t(self._mode_translation_key(mode))

    def _signal_aspect_text(self, aspect: SignalAspect) -> str:
        return self._t(f"signal_aspect.{aspect.value.lower()}")

    def _populate_language_selector(self) -> None:
        current_language = self._translator.language
        options = [code for code in SUPPORTED_LANGUAGES if code in {"en", "vi"}] or ["en", "vi"]
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for language_code in options:
            option_key = "language.option.vi" if language_code == "vi" else "language.option.en"
            self.language_combo.addItem(self._t(option_key), language_code)
        selected_index = self.language_combo.findData(current_language)
        self.language_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.language_combo.blockSignals(False)

    def _set_table_headers(self) -> None:
        labels = [
            self._t("interlocking_table.header.no"),
            self._t("interlocking_table.header.route"),
            self._t("interlocking_table.header.signal"),
            self._t("interlocking_table.header.signal_aspect"),
            self._t("interlocking_table.header.normal").upper(),
            self._t("interlocking_table.header.reverse").upper(),
            self._t("interlocking_table.header.reverse_route"),
            self._t("interlocking_table.header.calling_on_route"),
            self._t("interlocking_table.header.opposing_signal"),
            self._t("interlocking_table.header.track"),
            self._t("interlocking_table.header.approach_lock_track"),
            self._t("interlocking_table.header.approach_lock_release"),
            self._t("interlocking_table.header.destination_track"),
            self._t("interlocking_table.header.normal").upper(),
            self._t("interlocking_table.header.reverse").upper(),
            self._t("interlocking_table.header.overlap"),
            self._t("interlocking_table.header.overlap_release"),
        ]
        self.table_widget.setHorizontalHeaderLabels(labels)
        header = self.table_widget.horizontalHeader()
        if isinstance(header, PointGroupedHeader):
            point_label = (
                "POINTS"
                if self._translator.language == "en"
                else self._t("interlocking_table.header.point").upper()
            )
            flank_label = self._t("interlocking_table.header.flank_point")
            header.set_labels(
                labels,
                [
                    (
                        point_label,
                        PointGroupedHeader.NORMAL_COLUMN,
                        PointGroupedHeader.REVERSE_COLUMN,
                    ),
                    (
                        flank_label,
                        PointGroupedHeader.FLANK_NORMAL_COLUMN,
                        PointGroupedHeader.FLANK_REVERSE_COLUMN,
                    ),
                ],
            )

    def _retranslate_ui(self) -> None:
        self.setWindowTitle(self._t("app.window_title"))

        self.toolbar.setWindowTitle(self._t("toolbar.main"))
        self.new_layout_action.setText(self._t("toolbar.new_layout"))
        self.save_layout_action.setText(self._t("toolbar.save_layout"))
        self.load_layout_action.setText(self._t("toolbar.load_layout"))
        self.connect_mode_action.setText(self._t("toolbar.connect_mode"))
        self.set_route_action.setText(self._t("toolbar.set_route"))
        self.cancel_route_action.setText(self._t("toolbar.cancel_route"))
        self.emergency_release_action.setText(self._t("toolbar.emergency_release"))
        self.export_interlocking_xlsx_action.setText(self._t("toolbar.export_xlsx"))
        self.open_smartio_local_action.setText(self._t("toolbar.open_smartio_local"))
        self.more_menu.setTitle(self._t("toolbar.more"))
        self.more_tool_button.setText(self._t("toolbar.more"))
        self.language_label.setText(self._t("language.label"))
        self._populate_language_selector()

        self.mode_group.setTitle(self._t("workspace.group"))
        mode_keys = [
            "mode.design_layout",
            "mode.simulation",
            "mode.runtime",
        ]
        summary_keys = [
            "workspace.summary.design_layout",
            "workspace.summary.simulation",
            "workspace.summary.runtime",
        ]
        for tab_index, mode_key in enumerate(mode_keys):
            self.mode_tabs.setTabText(tab_index, self._t(mode_key))
            self.mode_summary_labels[tab_index].setText(self._t(summary_keys[tab_index]))

        self.route_group.setTitle(self._t("route_finder.group"))
        self.route_help_label.setText(self._t("route_finder.instructions"))
        self.open_smartio_local_button.setText(self._t("button.open_smartio_local"))
        self.entry_label.setText(self._t("field.entry"))
        self.exit_label.setText(self._t("field.exit"))
        self.overlap_label.setText(self._t("field.overlap"))
        self.approach_release_label.setText(self._t("field.approach_release"))
        self.overlap_release_label.setText(self._t("field.overlap_release"))

        self.find_route_button.setText(self._t("button.find_route"))
        self.set_route_button.setText(self._t("button.set_route"))
        self.cancel_route_button.setText(self._t("button.cancel_route"))
        self.emergency_release_button.setText(self._t("button.emergency_release"))
        self.search_log.setPlaceholderText(self._t("route_finder.placeholder"))

        self.table_group.setTitle(self._t("interlocking_table.group"))
        self._set_table_headers()
        self._refresh_interlocking_table()

        self.approach_time_spin.setSuffix(self._t("unit.seconds_suffix"))
        self.overlap_release_spin.setSuffix(self._t("unit.seconds_suffix"))

        self.palette.set_translator(self._translator)
        self.canvas.set_translator(self._translator)
        self.route_presenter.set_translator(self._translator)
        self.canvas.set_layout_edit_lock(
            self.mode_policy.layout_edit_locked(self._operating_mode),
            self._t("main.lock.layout_edit_reason"),
        )
        if self.mode_policy.capabilities(self._operating_mode).can_edit_layout:
            self.palette.component_list.setToolTip("")
        else:
            self.palette.component_list.setToolTip(
                self._t("main.tooltip.component_insertion_disabled")
            )
        self.palette.add_label_button.setEnabled(
            self.mode_policy.capabilities(self._operating_mode).can_edit_layout
        )
        self.palette.add_line_button.setEnabled(
            self.mode_policy.capabilities(self._operating_mode).can_edit_layout
        )

        self._sync_ui_state()
        if self.preview_route is not None:
            search_order, _ = self._build_search_trace(
                self.preview_route.path[0],
                self.preview_route.path[-1],
            )
            self._write_search_log(self.preview_route, search_order)
        else:
            selected_row = self.table_widget.currentRow()
            if 0 <= selected_row < len(self.interlocking_rows):
                self._render_interlocking_row_log(self.interlocking_rows[selected_row])

    def _set_language(self, language_code: str) -> None:
        normalized_language = normalize_language(language_code)
        if normalized_language == self._translator.language:
            return
        self._translator.set_language(normalized_language)
        self._retranslate_ui()

    def _on_language_changed(self, index: int) -> None:
        if index < 0:
            return
        selected_language = str(self.language_combo.itemData(index) or "en")
        self._set_language(selected_language)

    def _apply_visual_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow { background: #eef2f6; }
            QToolBar {
                spacing: 6px;
                padding: 6px;
                border-bottom: 1px solid #ccd4dc;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #f7f9fb, stop:1 #edf3f8);
            }
            QToolButton {
                background: #f8fbfd;
                border: 1px solid #c7d2dc;
                border-radius: 6px;
                padding: 5px 10px;
                color: #1d4156;
                font-weight: 600;
            }
            QToolButton:hover { background: #eef5fa; }
            QToolButton:disabled {
                color: #91a0ac;
                background: #eef2f5;
            }
            QGroupBox {
                background: #ffffff;
                border: 1px solid #cfd9e2;
                border-radius: 10px;
                margin-top: 12px;
                font-weight: 600;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: #1d4156;
            }
            QTabWidget::pane {
                border: 1px solid #ccd6e0;
                border-radius: 8px;
                background: #ffffff;
            }
            QTabBar::tab {
                background: #e8eef5;
                border: 1px solid #c8d4df;
                border-bottom: none;
                padding: 7px 11px;
                margin-right: 3px;
                border-top-left-radius: 7px;
                border-top-right-radius: 7px;
                color: #20465b;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #ffffff;
                color: #0f5e8a;
            }
            QPushButton {
                background: #0f5e8a;
                color: #ffffff;
                border: 1px solid #0d4f75;
                border-radius: 7px;
                padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton:hover { background: #126da0; }
            QPushButton:disabled {
                background: #b8c7d4;
                border: 1px solid #afbfcc;
                color: #f4f7fa;
            }
            QPushButton#emergencyReleaseButton {
                background: #c62828;
                border: 1px solid #8e1b1b;
                color: #ffffff;
            }
            QPushButton#emergencyReleaseButton:hover {
                background: #d63a3a;
            }
            QPushButton#emergencyReleaseButton:disabled {
                background: #d9a6a6;
                border: 1px solid #c58e8e;
                color: #fff5f5;
            }
            QPlainTextEdit, QTableWidget, QComboBox, QDoubleSpinBox, QSpinBox {
                background: #fbfdff;
                border: 1px solid #c9d4df;
                border-radius: 6px;
            }
            """
        )

    def _build_toolbar(self) -> None:
        self.toolbar = QToolBar(self._t("toolbar.main"), self)
        self.addToolBar(self.toolbar)

        self.new_layout_action = self.toolbar.addAction(self._t("toolbar.new_layout"))
        self.new_layout_action.triggered.connect(self._new_layout)

        self.save_layout_action = self.toolbar.addAction(self._t("toolbar.save_layout"))
        self.save_layout_action.triggered.connect(self._save_layout)

        self.load_layout_action = self.toolbar.addAction(self._t("toolbar.load_layout"))
        self.load_layout_action.triggered.connect(self._load_layout)

        self.toolbar.addSeparator()

        self.connect_mode_action = self.toolbar.addAction(self._t("toolbar.connect_mode"))
        self.connect_mode_action.setCheckable(True)
        self.connect_mode_action.toggled.connect(self._toggle_connect_mode)

        self.toolbar.addSeparator()

        self.set_route_action = self.toolbar.addAction(self._t("toolbar.set_route"))
        self.set_route_action.triggered.connect(self._set_selected_route)

        self.cancel_route_action = self.toolbar.addAction(self._t("toolbar.cancel_route"))
        self.cancel_route_action.triggered.connect(lambda: self._cancel_active_routes())

        self.simulation_action = self.toolbar.addAction(self._t("toolbar.start_simulation"))
        self.simulation_action.triggered.connect(self._start_simulation)

        self.toolbar.addSeparator()

        self.export_interlocking_xlsx_action = self.toolbar.addAction(
            self._t("toolbar.export_xlsx")
        )
        self.export_interlocking_xlsx_action.triggered.connect(
            self._export_interlocking_table_xlsx
        )

        self.more_menu = QMenu(self._t("toolbar.more"), self.toolbar)
        self.emergency_release_action = self.more_menu.addAction(
            self._t("toolbar.emergency_release")
        )
        self.emergency_release_action.triggered.connect(lambda: self._emergency_release_routes())
        self.open_smartio_local_action = self.more_menu.addAction(
            self._t("toolbar.open_smartio_local")
        )
        self.open_smartio_local_action.triggered.connect(self._open_smartio_local)
        self.more_tool_button = QToolButton(self.toolbar)
        self.more_tool_button.setText(self._t("toolbar.more"))
        self.more_tool_button.setMenu(self.more_menu)
        self.more_tool_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.toolbar.addWidget(self.more_tool_button)

        self.toolbar.addSeparator()
        self.language_label = QLabel(self._t("language.label"), self.toolbar)
        self.language_combo = QComboBox(self.toolbar)
        self._populate_language_selector()
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.toolbar.addWidget(self.language_label)
        self.toolbar.addWidget(self.language_combo)

    def _new_layout(self) -> None:
        confirm = QMessageBox.question(
            self,
            self._t("dialog.new_layout.title"),
            self._t("dialog.new_layout.message"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._load_layout_into_canvas(self.layout_editor_service.new_layout(station_id="UNNAMED"))
        self.status.showMessage(self._t("status.started_new_empty_layout"))

    def _toggle_connect_mode(self, enabled: bool) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_edit_layout and enabled:
            self.connect_mode_action.blockSignals(True)
            self.connect_mode_action.setChecked(False)
            self.connect_mode_action.blockSignals(False)
            QMessageBox.information(
                self,
                self._t("dialog.connect_mode.title"),
                self._t("dialog.connect_mode.only_design_layout"),
            )
            return
        self.canvas.set_connect_mode(enabled)

    def _clear_preview_state(
        self,
        *,
        clear_visualization: bool = True,
        sync_ui: bool = False,
    ) -> None:
        """Clear preview route/log state after invalid/failed route actions."""
        self.preview_route = None
        if clear_visualization:
            self.canvas.clear_route_visualization()
        self.search_log.clear()
        if sync_ui:
            self._sync_ui_state()

    def _insert_component_from_palette(self, element_type: str) -> None:
        try:
            center = self.canvas.mapToScene(self.canvas.viewport().rect().center())
            self.canvas.add_component(element_type, center)
            self.status.showMessage(self._t("status.component_added", element_type=element_type))
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("dialog.cannot_add_component.title"),
                str(exc),
            )

    def _insert_text_label(self) -> None:
        try:
            self.canvas.begin_text_label_placement()
            self.status.showMessage(self._t("status.label_tool_active"))
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("dialog.cannot_add_label.title"),
                str(exc),
            )

    def _insert_annotation_line(self) -> None:
        try:
            self.canvas.begin_annotation_line_drawing()
            self.status.showMessage(self._t("status.line_tool_active"))
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("dialog.cannot_add_line.title"),
                str(exc),
            )

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(6, 6, 6, 6)

        self.mode_group = QGroupBox(self._t("workspace.group"))
        mode_layout = QVBoxLayout(self.mode_group)
        self.mode_tabs = QTabWidget(self.mode_group)
        self.mode_tabs.setDocumentMode(True)
        self.mode_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.mode_summary_labels: list[QLabel] = []
        self.mode_tabs.addTab(
            self._build_mode_tab_body(
                self._t("workspace.summary.design_layout"),
            ),
            self._t("mode.design_layout"),
        )
        self.mode_tabs.addTab(
            self._build_mode_tab_body(
                self._t("workspace.summary.simulation"),
            ),
            self._t("mode.simulation"),
        )
        self.mode_tabs.addTab(
            self._build_mode_tab_body(
                self._t("workspace.summary.runtime"),
            ),
            self._t("mode.runtime"),
        )
        self.mode_tabs.currentChanged.connect(self._on_mode_tab_changed)
        mode_layout.addWidget(self.mode_tabs)
        runtime_status_row = QHBoxLayout()
        self.runtime_connection_badge = QLabel(self.mode_group)
        self.runtime_connection_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.runtime_connection_badge.setFixedSize(12, 12)
        self.runtime_connection_badge.setStyleSheet(
            "border-radius: 6px; background:#cad2db; border:1px solid #aab4bf;"
        )
        self.runtime_connection_badge.setText("")
        runtime_status_row.addWidget(self.runtime_connection_badge)
        self.runtime_connection_label = QLabel(self.mode_group)
        self.runtime_connection_label.setWordWrap(True)
        self.runtime_connection_label.setStyleSheet("font-weight: 600; color: #12415a;")
        runtime_status_row.addWidget(self.runtime_connection_label, stretch=1)
        self.open_smartio_local_button = QPushButton(self._t("button.open_smartio_local"))
        self.open_smartio_local_button.clicked.connect(self._open_smartio_local)
        runtime_status_row.addWidget(self.open_smartio_local_button)
        mode_layout.addLayout(runtime_status_row)

        self.route_group = QGroupBox(self._t("route_finder.group"))
        route_layout = QVBoxLayout(self.route_group)
        self.route_help_label = QLabel(self._t("route_finder.instructions"))
        self.route_help_label.setWordWrap(True)
        route_layout.addWidget(self.route_help_label)

        combo_row = QHBoxLayout()
        self.entry_combo = QComboBox(self.route_group)
        self.exit_combo = QComboBox(self.route_group)
        self.entry_combo.currentTextChanged.connect(lambda _text: self._sync_ui_state())
        self.exit_combo.currentTextChanged.connect(lambda _text: self._sync_ui_state())
        self.overlap_spin = QSpinBox(self.route_group)
        self.overlap_spin.setRange(0, 5)
        self.overlap_spin.setValue(int(self.application_profile.default_overlap_length))
        self.overlap_spin.valueChanged.connect(self._refresh_interlocking_table)
        self.entry_label = QLabel(self._t("field.entry"))
        self.exit_label = QLabel(self._t("field.exit"))
        self.overlap_label = QLabel(self._t("field.overlap"))
        combo_row.addWidget(self.entry_label)
        combo_row.addWidget(self.entry_combo)
        combo_row.addWidget(self.exit_label)
        combo_row.addWidget(self.exit_combo)
        combo_row.addWidget(self.overlap_label)
        combo_row.addWidget(self.overlap_spin)
        route_layout.addLayout(combo_row)

        timing_row = QHBoxLayout()
        self.approach_time_spin = QDoubleSpinBox(self.route_group)
        self.approach_time_spin.setRange(0.0, 600.0)
        self.approach_time_spin.setDecimals(1)
        self.approach_time_spin.setSingleStep(1.0)
        self.approach_time_spin.setSuffix(self._t("unit.seconds_suffix"))
        self.approach_time_spin.setValue(float(self.application_profile.time_lock_seconds))
        self.approach_time_spin.valueChanged.connect(self._on_timing_controls_changed)
        self.overlap_release_spin = QDoubleSpinBox(self.route_group)
        self.overlap_release_spin.setRange(0.0, 600.0)
        self.overlap_release_spin.setDecimals(1)
        self.overlap_release_spin.setSingleStep(1.0)
        self.overlap_release_spin.setSuffix(self._t("unit.seconds_suffix"))
        self.overlap_release_spin.setValue(float(self.application_profile.overlap_release_seconds))
        self.overlap_release_spin.valueChanged.connect(self._on_timing_controls_changed)
        self.approach_release_label = QLabel(self._t("field.approach_release"))
        self.overlap_release_label = QLabel(self._t("field.overlap_release"))
        timing_row.addWidget(self.approach_release_label)
        timing_row.addWidget(self.approach_time_spin)
        timing_row.addWidget(self.overlap_release_label)
        timing_row.addWidget(self.overlap_release_spin)
        route_layout.addLayout(timing_row)

        button_row = QHBoxLayout()
        self.find_route_button = QPushButton(self._t("button.find_route"))
        self.find_route_button.clicked.connect(self._preview_selected_route)
        self.set_route_button = QPushButton(self._t("button.set_route"))
        self.set_route_button.clicked.connect(self._set_selected_route)
        self.cancel_route_button = QPushButton(self._t("button.cancel_route"))
        self.cancel_route_button.clicked.connect(lambda: self._cancel_active_routes())
        self.simulate_button = QPushButton(self._t("button.start_simulation"))
        self.simulate_button.clicked.connect(self._start_simulation)
        button_row.addWidget(self.find_route_button)
        button_row.addWidget(self.set_route_button)
        button_row.addWidget(self.cancel_route_button)
        button_row.addWidget(self.simulate_button)
        route_layout.addLayout(button_row)

        self.search_log = QPlainTextEdit(self.route_group)
        self.search_log.setReadOnly(True)
        self.search_log.setPlaceholderText(self._t("route_finder.placeholder"))
        route_layout.addWidget(self.search_log)

        emergency_row = QHBoxLayout()
        emergency_row.addStretch(1)
        self.emergency_release_button = QPushButton(self._t("button.emergency_release"))
        self.emergency_release_button.setObjectName("emergencyReleaseButton")
        self.emergency_release_button.clicked.connect(lambda: self._emergency_release_routes())
        emergency_row.addWidget(self.emergency_release_button)
        route_layout.addLayout(emergency_row)

        self.table_group = QGroupBox(self._t("interlocking_table.group"))
        table_layout = QVBoxLayout(self.table_group)
        self.table_widget = QTableWidget(0, 17, self.table_group)
        self.table_widget.setHorizontalHeader(PointGroupedHeader(self.table_widget))
        self._set_table_headers()
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_widget.verticalHeader().setVisible(False)
        header = self.table_widget.horizontalHeader()
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFixedHeight(52)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table_widget.cellClicked.connect(self._on_table_row_clicked)
        table_layout.addWidget(self.table_widget)

        panel_layout.addWidget(self.mode_group)
        panel_layout.addWidget(self.route_group)
        panel_layout.addWidget(self.table_group, stretch=1)
        return panel

    def _build_mode_tab_body(self, summary: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        summary_label = QLabel(summary, container)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet("font-weight: 600; color: #12384d;")
        layout.addWidget(summary_label)
        self.mode_summary_labels.append(summary_label)
        return container

    @staticmethod
    def _tab_index_for_mode(mode: OperatingMode) -> int:
        if mode is OperatingMode.DESIGN_LAYOUT:
            return 0
        if mode is OperatingMode.SIMULATION:
            return 1
        return 2

    @staticmethod
    def _mode_for_tab_index(index: int) -> OperatingMode:
        if index == 1:
            return OperatingMode.SIMULATION
        if index == 2:
            return OperatingMode.RUNTIME
        return OperatingMode.DESIGN_LAYOUT

    def _on_mode_tab_changed(self, index: int) -> None:
        self._set_operating_mode(self._mode_for_tab_index(index))

    def _initialize_smartio_client(self) -> None:
        self.smartio_coordinator = SmartIORuntimeCoordinator(
            profile=self.application_profile,
            application_service=self.application_service,
            runtime_workspace_service=self.runtime_workspace_service,
            topology_provider=lambda: self.canvas.topology,
            operating_mode_provider=lambda: self._operating_mode,
            parent=self,
        )
        self.smartio_coordinator.smartio_status_changed.connect(self._on_smartio_status_changed)
        self.smartio_coordinator.smartio_error.connect(self._on_smartio_error)
        self.smartio_coordinator.runtime_state_changed.connect(self._on_runtime_state_changed)
        self.smartio_coordinator.runtime_health_changed.connect(self._on_runtime_health_changed)
        self._smartio_status_token = self.smartio_coordinator.smartio_status_token
        self._runtime_transport_health = dict(self.smartio_coordinator.runtime_health)

    def _on_smartio_status_changed(self, status: str) -> None:
        self._smartio_status_token = str(status).strip() or "disconnected"
        self._update_runtime_connection_label()

    def _on_smartio_error(self, message: str) -> None:
        text = self._localized_smartio_error(str(message).strip())
        if text:
            self.status.showMessage(self._t("status.smartio_error", message=text), 5000)
        self._update_runtime_connection_label()

    def _localized_smartio_error(self, message: str) -> str:
        if not message:
            return ""
        prefix_key_pairs = (
            ("runtime_snapshot send failed: ", "smartio.error.runtime_snapshot_send_failed"),
            ("hello send failed: ", "smartio.error.hello_send_failed"),
            ("command_result send failed: ", "smartio.error.command_result_send_failed"),
        )
        for prefix, key in prefix_key_pairs:
            if message.startswith(prefix):
                return self._t(key, message=message.removeprefix(prefix))
        if message == "Unknown SmartIO error":
            return self._t("smartio.error.unknown")
        if message == "CBI is not in Runtime mode":
            return self._t("smartio.error.cbi_not_runtime")
        return message

    def _on_runtime_state_changed(self, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        for section_id in data.get("sections", []):
            if section_id:
                self._refresh_route_log_for_section(str(section_id))
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._refresh_interlocking_table()
        self._publish_webclient_runtime_state()

    def _on_runtime_health_changed(self, payload: object) -> None:
        self._runtime_transport_health = payload if isinstance(payload, dict) else {}
        self._update_runtime_connection_label()
        self._sync_ui_state()

    def _send_smartio_runtime_snapshot(self) -> None:
        self._publish_webclient_runtime_state()
        self.smartio_coordinator.publish_runtime_snapshot()

    def _webclient_runtime_state_path(self) -> Path:
        return webclient_runtime_state_path(
            self._repo_root(),
            getattr(
                self.application_profile,
                "runtime_journal_dir",
                DEFAULT_APP_CONFIG.paths.runtime_journal_dir,
            ),
        )

    def _webclient_runtime_command_path(self) -> Path:
        return webclient_runtime_command_path(
            self._repo_root(),
            getattr(
                self.application_profile,
                "runtime_journal_dir",
                DEFAULT_APP_CONFIG.paths.runtime_journal_dir,
            ),
        )

    def _webclient_runtime_command_result_path(self) -> Path:
        return webclient_runtime_command_result_path(
            self._repo_root(),
            getattr(
                self.application_profile,
                "runtime_journal_dir",
                DEFAULT_APP_CONFIG.paths.runtime_journal_dir,
            ),
        )

    def _publish_webclient_runtime_state(self) -> None:
        if self._operating_mode not in {OperatingMode.SIMULATION, OperatingMode.RUNTIME}:
            return
        try:
            self._process_webclient_runtime_commands()
            runtime_snapshot = (
                self.controller.build_runtime_snapshot()
                if self.controller.has_runtime_session
                else None
            )
            payload = self.application_service.build_webclient_runtime_state(
                topology=self.canvas.topology,
                workspace_mode=self._operating_mode,
                runtime_snapshot=runtime_snapshot,
            )
            self.application_service.save_webclient_runtime_state(
                payload, self._webclient_runtime_state_path()
            )
            self._last_webclient_runtime_export_error = ""
        except Exception as exc:
            message = str(exc).strip()
            if message and message != self._last_webclient_runtime_export_error:
                self.status.showMessage(
                    self._t("status.webclient_runtime_export_failed", message=message),
                    5000,
                )
                self._last_webclient_runtime_export_error = message

    def _drain_webclient_runtime_commands(self) -> list[dict]:
        command_path = self._webclient_runtime_command_path()
        if not command_path.exists():
            return []
        processing_path = command_path.with_name(f"{command_path.name}.{os.getpid()}.processing")
        try:
            os.replace(command_path, processing_path)
        except FileNotFoundError:
            return []
        except OSError as exc:
            self.status.showMessage(
                self._t("status.webclient_command_inbox_unavailable", message=exc),
                5000,
            )
            return []

        commands: list[dict] = []
        try:
            for line in processing_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    self.status.showMessage(
                        self._t("status.webclient_command_invalid_ignored", message=exc),
                        5000,
                    )
                    continue
                if isinstance(payload, dict):
                    commands.append(payload)
        finally:
            with suppress(OSError):
                processing_path.unlink(missing_ok=True)
        return commands

    def _process_webclient_runtime_commands(self) -> None:
        for command in self._drain_webclient_runtime_commands():
            kind = str(command.get("kind", "")).strip()
            payload = command.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}
            try:
                if kind == "set_route":
                    result_payload = self._set_route_from_webclient(payload)
                elif kind == "cancel_active_routes":
                    result_payload = self._cancel_active_routes_from_webclient()
                else:
                    raise RuntimeError(
                        self._t(
                            "status.webclient_unsupported_command",
                            kind=kind or self._t("status.webclient_missing_command"),
                        )
                    )
            except Exception as exc:
                message = str(exc)
                self._record_webclient_runtime_command_result(
                    command, status="rejected", message=message
                )
                self.status.showMessage(
                    self._t("status.webclient_command_rejected", message=message),
                    5000,
                )
            else:
                self._record_webclient_runtime_command_result(
                    command,
                    status="applied",
                    message="",
                    payload=result_payload,
                )

    def _record_webclient_runtime_command_result(
        self,
        command: dict,
        *,
        status: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        result_path = self._webclient_runtime_command_result_path()
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result = {
            "command_id": str(command.get("command_id", "")),
            "kind": str(command.get("kind", "")),
            "source_id": str(command.get("source_id", "webclient")),
            "status": status,
            "message": message,
            "payload": payload or {},
            "ts": time.time(),
        }
        try:
            with result_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            self.status.showMessage(
                self._t("status.webclient_command_result_write_failed", message=exc),
                5000,
            )

    def _set_route_from_webclient(self, payload: dict) -> dict:
        if not self.mode_policy.capabilities(self._operating_mode).can_set_route:
            raise RuntimeError(self._t("status.set_route_disabled"))
        entry_signal_id = str(payload.get("entry_signal_id", "")).strip()
        exit_signal_id = str(payload.get("exit_signal_id", "")).strip()
        if not entry_signal_id or not exit_signal_id:
            raise RuntimeError(self._t("dialog.find_route.select_both"))
        if entry_signal_id == exit_signal_id:
            raise RuntimeError(self._t("dialog.find_route.same_signal"))
        route_result = self.controller.set_or_reuse_route(
            topology=self.canvas.topology,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=0,
            approach_time_lock_seconds=float(
                getattr(self.application_profile, "time_lock_seconds", 0.0)
            ),
            overlap_release_seconds=float(
                getattr(self.application_profile, "overlap_release_seconds", 0.0)
            ),
        )
        route = route_result.route
        search_order, _ = self._build_search_trace(route.path[0], route.path[-1])
        self.preview_route = route
        self._write_search_log(route, search_order)
        self.canvas.set_runtime_view_state(self.controller.runtime_view_state())
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._refresh_interlocking_table()
        self.status.showMessage(
            self._t(
                "status.route_set" if route_result.created else "status.route_already_active",
                entry=entry_signal_id,
                exit=exit_signal_id,
            ),
            5000,
        )
        return {"route_id": route.id, "created": route_result.created}

    def _cancel_active_routes_from_webclient(self) -> dict:
        if not self.mode_policy.capabilities(self._operating_mode).can_cancel_route:
            raise RuntimeError(self._t("status.cancel_route_disabled"))
        if not self.controller.has_runtime_session or not self.controller.has_active_routes():
            self.status.showMessage(self._t("status.no_active_routes"), 5000)
            return {"attempted_routes": 0, "cancelled_routes": 0, "failures": []}
        cancel_result = self.controller.cancel_active_routes()
        self.canvas.clear_route_visualization()
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._refresh_interlocking_table()
        if cancel_result.failures:
            self.status.showMessage("; ".join(cancel_result.failures), 5000)
        else:
            self.status.showMessage(self._t("status.cancelled_all_active_routes"), 5000)
        return {
            "attempted_routes": cancel_result.attempted_routes,
            "cancelled_routes": cancel_result.cancelled_routes,
            "failures": list(cancel_result.failures),
        }

    def _sync_webclient_runtime_export_for_mode(self, mode: OperatingMode) -> None:
        if mode in {OperatingMode.SIMULATION, OperatingMode.RUNTIME}:
            self._webclient_runtime_timer.start()
            self._publish_webclient_runtime_state()
            return
        self._webclient_runtime_timer.stop()

    def _smartio_state_text(self) -> str:
        token = str(self._smartio_status_token or "").strip().lower()
        presentation = SmartIOSessionAdapter.presentation(
            operating_mode=self._operating_mode,
            status_token=token,
        )
        if presentation.state_key == "smartio.state.reconnecting" and token.endswith("s"):
            delay = token.removeprefix("reconnecting_in_").removesuffix("s")
            if delay.isdigit():
                return self._t("smartio.state.reconnecting", seconds=int(delay))
        return self._t(presentation.state_key)

    def _update_runtime_connection_label(self) -> None:
        if not hasattr(self, "runtime_connection_label") or not hasattr(
            self,
            "runtime_connection_badge",
        ):
            return
        presentation = SmartIOSessionAdapter.presentation(
            operating_mode=self._operating_mode,
            status_token=self._smartio_status_token,
        )
        self.runtime_connection_badge.setVisible(presentation.visible)
        self.runtime_connection_label.setVisible(presentation.visible)
        if not presentation.visible:
            return
        self.runtime_connection_badge.setToolTip(self._smartio_state_text())
        self.runtime_connection_badge.setStyleSheet(
            f"border-radius: 6px; min-width: 12px; max-width: 12px; "
            f"min-height: 12px; max-height: 12px; {presentation.badge_style}"
        )
        self.runtime_connection_label.setText(
            self._t(
                "runtime.smartio.status",
                state=self._smartio_state_text(),
            )
        )

    def _runtime_health_text_suffix(self) -> str:
        health = (
            self._runtime_transport_health
            if isinstance(self._runtime_transport_health, dict)
            else {}
        )
        stream_seq = int(health.get("stream_seq", 0) or 0)
        snapshot_age = health.get("snapshot_age_seconds")
        command_age = health.get("command_age_seconds")
        degraded = bool(health.get("degraded"))
        degraded_reason = str(health.get("degraded_reason", "")).strip()
        details = [f"seq={stream_seq}"]
        if snapshot_age is not None:
            details.append(f"snap={float(snapshot_age):.1f}s")
        if command_age is not None:
            details.append(f"cmd={float(command_age):.1f}s")
        suffix = " | ".join(details)
        if degraded and degraded_reason:
            if degraded_reason.startswith("TRANSPORT_UNAVAILABLE: snapshot stale for "):
                seconds = degraded_reason.removeprefix(
                    "TRANSPORT_UNAVAILABLE: snapshot stale for "
                ).removesuffix("s")
                degraded_reason = self._t("smartio.error.snapshot_stale", seconds=seconds)
            return f"\nDEGRADED: {degraded_reason}\n{suffix}"
        return f"\n{suffix}" if suffix else ""

    def _sync_smartio_connection_for_mode(self, mode: OperatingMode) -> None:
        self._apply_smartio_url_for_mode(mode)
        self.smartio_coordinator.sync_connection_for_mode(mode)

    def _ensure_smartio_connection(self, *, force: bool = False) -> None:
        self.smartio_coordinator.ensure_connection(force=force)

    def _current_smartio_ws_url(self) -> str:
        return str(getattr(self.smartio_coordinator, "current_ws_url", "")).strip()

    def _remote_smartio_ws_url(self) -> str:
        return str(getattr(self.application_profile, "smart_io_ws_url", "")).strip()

    def _preferred_smartio_ws_url_for_mode(self, mode: OperatingMode) -> str:
        if mode is OperatingMode.RUNTIME:
            return self._remote_smartio_ws_url()
        if (
            mode is OperatingMode.SIMULATION
            and self._simulation_uses_local_smartio
            and self._is_smartio_local_running()
        ):
            return self._smartio_local_ws_url()
        return self._remote_smartio_ws_url()

    def _apply_smartio_url_for_mode(self, mode: OperatingMode) -> None:
        desired_ws_url = self._preferred_smartio_ws_url_for_mode(mode)
        if desired_ws_url and desired_ws_url != self._current_smartio_ws_url():
            self.smartio_coordinator.set_ws_url(desired_ws_url)
            self._smartio_status_token = self.smartio_coordinator.smartio_status_token
            self._update_runtime_connection_label()

    def _smartio_local_host(self) -> str:
        return str(
            getattr(
                self.application_profile,
                "smart_io_local_host",
                DEFAULT_APP_CONFIG.smartio.local_host,
            )
        )

    def _smartio_local_port(self) -> int:
        return int(
            getattr(
                self.application_profile,
                "smart_io_local_port",
                DEFAULT_APP_CONFIG.smartio.local_port,
            )
        )

    def _smartio_local_http_url(self) -> str:
        return f"http://{self._smartio_local_host()}:{self._smartio_local_port()}/"

    def _smartio_local_ws_url(self) -> str:
        host = self._smartio_local_host()
        port = self._smartio_local_port()
        path = str(
            getattr(
                self.application_profile,
                "smart_io_local_ws_path",
                DEFAULT_APP_CONFIG.smartio.local_ws_path,
            )
        )
        return f"ws://{host}:{port}{path}"

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[2]

    def _smartio_local_layout_path(self) -> Path:
        target_dir = self._repo_root() / str(
            getattr(
                self.application_profile,
                "smartio_local_layout_dir",
                DEFAULT_APP_CONFIG.paths.smartio_local_layout_dir,
            )
        )
        target_dir.mkdir(parents=True, exist_ok=True)
        layout_name = (
            self.current_layout.source_path.stem
            if self.current_layout is not None and self.current_layout.source_path is not None
            else (self.current_layout.station_id if self.current_layout is not None else "layout")
        )
        return target_dir / f"{layout_name or 'layout'}_smartio_local.json"

    def _export_smartio_local_layout(self) -> Path:
        layout_path = self._smartio_local_layout_path()
        if self.current_layout is not None:
            self.current_layout.topology = self.canvas.topology
        self.application_service.save_topology(
            self.canvas.topology,
            layout_path,
            include_runtime_state=False,
            include_occupancy=True,
        )
        return layout_path

    def _is_smartio_local_running(self) -> bool:
        return (
            self._smartio_local_process is not None
            and self._smartio_local_process.state() is not QProcess.ProcessState.NotRunning
        )

    def _stop_smartio_local_process(self) -> None:
        self._simulation_uses_local_smartio = False
        if self._smartio_local_process is None:
            return
        if self._smartio_local_process.state() is not QProcess.ProcessState.NotRunning:
            self._smartio_local_process.terminate()
            stop_timeout_ms = int(
                getattr(
                    self.application_profile,
                    "process_stop_timeout_ms",
                    DEFAULT_APP_CONFIG.webclient.process_stop_timeout_ms,
                )
            )
            if not self._smartio_local_process.waitForFinished(stop_timeout_ms):
                self._smartio_local_process.kill()
                self._smartio_local_process.waitForFinished(stop_timeout_ms)
        self._smartio_local_process.deleteLater()
        self._smartio_local_process = None

    def _open_smartio_local(self) -> None:
        if self._operating_mode is not OperatingMode.SIMULATION:
            return
        layout_path = self._export_smartio_local_layout()
        http_url = self._smartio_local_http_url()
        ws_url = self._smartio_local_ws_url()

        if not self._is_smartio_local_running():
            process = QProcess(self)
            process.setProgram(sys.executable)
            process.setArguments(
                [
                    str(self._repo_root() / "tools" / "CBI_SmartIO" / "run_local_host.py"),
                    "--layout",
                    str(layout_path),
                    "--host",
                    self._smartio_local_host(),
                    "--port",
                    str(self._smartio_local_port()),
                    "--no-browser",
                ]
            )
            process.setWorkingDirectory(str(self._repo_root()))
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            process.start()
            start_timeout_ms = int(
                getattr(
                    self.application_profile,
                    "process_start_timeout_ms",
                    DEFAULT_APP_CONFIG.webclient.process_start_timeout_ms,
                )
            )
            if not process.waitForStarted(start_timeout_ms):
                error_text = str(process.errorString()).strip() or self._t(
                    "status.smartio_local_failed"
                )
                QMessageBox.critical(
                    self,
                    self._t("dialog.smartio_local_failed.title"),
                    error_text,
                )
                process.deleteLater()
                return
            self._smartio_local_process = process
            self.status.showMessage(
                self._t("status.smartio_local_started", path=layout_path, url=http_url),
                5000,
            )
        else:
            self.status.showMessage(
                self._t("status.smartio_local_opened", url=http_url),
                4000,
            )

        self._simulation_uses_local_smartio = True
        self.smartio_coordinator.set_ws_url(ws_url)
        self._smartio_status_token = self.smartio_coordinator.smartio_status_token
        self._update_runtime_connection_label()
        self._ensure_smartio_connection(force=True)
        QDesktopServices.openUrl(QUrl(http_url))

    def _allow_runtime_workspace(self) -> bool:
        self._apply_smartio_url_for_mode(OperatingMode.RUNTIME)
        self._ensure_smartio_connection(force=True)
        return self.smartio_coordinator.is_connected

    def _webclient_host(self) -> str:
        return str(
            getattr(
                self.application_profile,
                "webclient_host",
                DEFAULT_APP_CONFIG.webclient.host,
            )
        )

    def _webclient_port(self) -> int:
        return int(
            getattr(
                self.application_profile,
                "webclient_port",
                DEFAULT_APP_CONFIG.webclient.port,
            )
        )

    def _webclient_http_url(self) -> str:
        return f"http://{self._webclient_host()}:{self._webclient_port()}/?lang={self._translator.language}"

    def _webclient_layout_path(self) -> Path:
        if self.current_layout is not None and self.current_layout.source_path is not None:
            return self.current_layout.source_path.resolve()
        return (
            self._repo_root()
            / str(
                getattr(
                    self.application_profile,
                    "default_layout_path",
                    DEFAULT_APP_CONFIG.paths.default_layout_path,
                )
            )
        ).resolve()

    def _is_webclient_server_running(self) -> bool:
        return (
            self._webclient_process is not None
            and self._webclient_process.state() is not QProcess.ProcessState.NotRunning
        )

    def _stop_webclient_server_process(self) -> None:
        if self._webclient_process is None:
            return
        if self._webclient_process.state() is not QProcess.ProcessState.NotRunning:
            self._webclient_process.terminate()
            stop_timeout_ms = int(
                getattr(
                    self.application_profile,
                    "process_stop_timeout_ms",
                    DEFAULT_APP_CONFIG.webclient.process_stop_timeout_ms,
                )
            )
            if not self._webclient_process.waitForFinished(stop_timeout_ms):
                self._webclient_process.kill()
                self._webclient_process.waitForFinished(stop_timeout_ms)
        self._webclient_process.deleteLater()
        self._webclient_process = None

    def _ensure_webclient_server_for_runtime(self) -> None:
        self._publish_webclient_runtime_state()
        if not self._is_webclient_server_running():
            process = QProcess(self)
            process.setProgram(sys.executable)
            process.setArguments(
                [
                    str(self._repo_root() / "webclient" / "serve.py"),
                    "--host",
                    self._webclient_host(),
                    "--port",
                    str(self._webclient_port()),
                    "--layout-file",
                    str(self._webclient_layout_path()),
                    "--runtime-command-file",
                    str(self._webclient_runtime_command_path()),
                    "--runtime-command-result-file",
                    str(self._webclient_runtime_command_result_path()),
                ]
            )
            process.setWorkingDirectory(str(self._repo_root()))
            process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
            process.start()
            start_timeout_ms = int(
                getattr(
                    self.application_profile,
                    "process_start_timeout_ms",
                    DEFAULT_APP_CONFIG.webclient.process_start_timeout_ms,
                )
            )
            if process.waitForStarted(start_timeout_ms):
                self._webclient_process = process
                self.status.showMessage(
                    self._t("status.webclient_monitor_started", url=self._webclient_http_url()),
                    5000,
                )
            else:
                error_text = str(process.errorString()).strip()
                process.deleteLater()
                if error_text:
                    self.status.showMessage(
                        self._t("status.webclient_monitor_start_failed", message=error_text),
                        5000,
                    )
        if not self._webclient_browser_opened:
            QDesktopServices.openUrl(QUrl(self._webclient_http_url()))
            self._webclient_browser_opened = True

    def _set_operating_mode(self, mode: OperatingMode, *, announce: bool = True) -> None:
        previous_mode = self._operating_mode
        if mode is OperatingMode.RUNTIME and not self._allow_runtime_workspace():
            if hasattr(self, "mode_tabs"):
                self.mode_tabs.blockSignals(True)
                self.mode_tabs.setCurrentIndex(self._tab_index_for_mode(previous_mode))
                self.mode_tabs.blockSignals(False)
            if announce:
                QMessageBox.warning(
                    self,
                    self._t("dialog.runtime_requires_smartio.title"),
                    self._t(
                        "dialog.runtime_requires_smartio.message",
                        url=self._current_smartio_ws_url() or "-",
                        state=self._smartio_state_text(),
                    ),
                )
            self.status.showMessage(
                self._t(
                    "status.runtime_requires_smartio",
                    state=self._smartio_state_text(),
                ),
                5000,
            )
            self._update_runtime_connection_label()
            return
        self._operating_mode = mode
        capabilities = self.mode_policy.capabilities(mode)

        if hasattr(self, "mode_tabs"):
            target_index = self._tab_index_for_mode(mode)
            if self.mode_tabs.currentIndex() != target_index:
                self.mode_tabs.blockSignals(True)
                self.mode_tabs.setCurrentIndex(target_index)
                self.mode_tabs.blockSignals(False)

        design_mode = capabilities.can_edit_layout
        if not capabilities.can_start_simulation and self._simulation_timer.isActive():
            self._simulation_timer.stop()
            self.status.showMessage(self._t("status.simulation_stopped_workspace"))

        if self.connect_mode_action.isChecked() and not design_mode:
            self.connect_mode_action.blockSignals(True)
            self.connect_mode_action.setChecked(False)
            self.connect_mode_action.blockSignals(False)
            self.canvas.set_connect_mode(False)

        self.canvas.set_layout_edit_lock(
            self.mode_policy.layout_edit_locked(mode),
            self._t("main.lock.layout_edit_reason"),
        )
        self.canvas.set_edit_dialog_enabled(mode is not OperatingMode.RUNTIME)
        self.palette.component_list.setEnabled(design_mode)
        self.palette.add_label_button.setEnabled(design_mode)
        self.palette.add_line_button.setEnabled(design_mode)
        if design_mode:
            self.palette.component_list.setToolTip("")
        else:
            self.palette.component_list.setToolTip(
                self._t("main.tooltip.component_insertion_disabled")
            )

        self._sync_smartio_connection_for_mode(mode)
        self._sync_webclient_runtime_export_for_mode(mode)
        if mode is OperatingMode.RUNTIME:
            self._ensure_webclient_server_for_runtime()
        self._sync_ui_state()
        self._update_runtime_connection_label()
        if announce and previous_mode is not mode:
            self.status.showMessage(self._t("status.workspace_mode", mode=self._mode_text(mode)))

    def _on_properties_applied(self, element_id: str, updates: dict) -> None:
        try:
            committed_label_id = self.canvas.commit_inline_label_edit()
            current_id = element_id
            new_id = str(updates.pop("id", "")).strip()
            if new_id and new_id != element_id:
                self.canvas.rename_node(element_id, new_id)
                current_id = new_id
            if committed_label_id == element_id and "text" in updates:
                label = self.canvas.topology.labels.get(current_id)
                if label is not None:
                    updates["text"] = label.text

            if updates:
                self.canvas.update_node_properties(current_id, updates)
            else:
                self.canvas.refresh_visual_state()
                self.canvas.topology_changed.emit()

            self.status.showMessage(self._t("status.updated_element", element_id=current_id))
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("dialog.property_update_failed.title"),
                str(exc),
            )

    def _manual_override_from_canvas(
        self,
        section_id: str,
        _occupied_before: bool,
        occupied_after: bool,
    ) -> list[str]:
        if self._operating_mode is not OperatingMode.SIMULATION:
            self.status.showMessage(
                self._t("status.workspace_mode", mode=self._mode_text(self._operating_mode)),
                2500,
            )
            return []
        if not self.mode_policy.capabilities(self._operating_mode).can_manual_state_override:
            self.status.showMessage(
                self._t("status.workspace_mode", mode=self._mode_text(self._operating_mode)),
                2500,
            )
            return []
        if not self.canvas.is_layout_edit_locked():
            return []
        result = self.controller.manual_set_section_occupied(
            topology=self.canvas.topology,
            section_id=section_id,
            occupied=occupied_after,
        )
        self.controller.update_time_locking()
        self.canvas.refresh_visual_state()
        self._schedule_manual_followup_refresh()
        self._refresh_route_log_for_section(section_id)
        self._send_smartio_runtime_snapshot()
        return list(result.removed_trains)

    def _schedule_manual_followup_refresh(self) -> None:
        """Refresh UI after overlap-release delay so background unlock is rendered."""
        delay_seconds = max(0.0, float(self.overlap_release_spin.value()))
        if delay_seconds <= 0.0:
            return
        QTimer.singleShot(
            int(delay_seconds * 1000) + 120,
            self._manual_followup_refresh,
        )

    def _manual_followup_refresh(self) -> None:
        if not self.controller.has_runtime_session:
            return
        self.controller.update_time_locking()
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._send_smartio_runtime_snapshot()

    def _refresh_route_log_for_section(self, section_id: str) -> None:
        """Refresh route log so lifecycle text tracks manual occupancy clicks."""
        route_for_log: Route | None = None
        normalized_section = str(section_id).strip()

        route_for_log = self.controller.active_route_for_section(normalized_section)

        if route_for_log is None and self.preview_route is not None:
            preview = self.preview_route
            if normalized_section in preview.full_path:
                route_for_log = preview
            else:
                approach_section = (preview.approach_locking_section or "").strip()
                if approach_section and approach_section == normalized_section:
                    route_for_log = preview

        if route_for_log is None or not route_for_log.path:
            return

        search_order, _ = self._build_search_trace(
            route_for_log.path[0],
            route_for_log.path[-1],
        )
        self._write_search_log(route_for_log, search_order)

    def _save_layout(self) -> None:
        default_target = "data/layout.json"
        if self.current_layout.source_path is not None:
            default_target = str(self.current_layout.source_path)
        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t("dialog.save_layout.title"),
            default_target,
            self._t("dialog.file_filter.json"),
        )
        if not path:
            return
        try:
            self.current_layout.topology = self.canvas.topology
            saved_path = self.layout_editor_service.save_layout(
                self.current_layout,
                path=path,
                include_runtime_state=False,
                include_occupancy=True,
            )
            self.current_layout.station_id = saved_path.stem
            self.status.showMessage(self._t("status.saved_layout", path=saved_path))
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("dialog.save_failed.title"),
                str(exc),
            )

    def _load_layout(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            self._t("dialog.load_layout.title"),
            "data",
            self._t("dialog.file_filter.json"),
        )
        if not path:
            return
        keep_occupancy = True
        try:
            loaded = self.layout_editor_service.load_layout(
                path,
                station_id=Path(path).stem,
                load_runtime_state=False,
                load_occupancy=keep_occupancy,
            )
            self._load_layout_into_canvas(loaded)
            self.status.showMessage(self._t("status.loaded_layout", path=path))
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("dialog.load_failed.title"),
                str(exc),
            )

    def _export_interlocking_table_xlsx(self) -> None:
        self._refresh_interlocking_table()
        if self.table_widget.rowCount() == 0:
            QMessageBox.warning(
                self,
                self._t("dialog.export_interlocking_xlsx.title"),
                self._t("dialog.export_interlocking_xlsx.empty"),
            )
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            self._t("dialog.export_interlocking_xlsx.title"),
            self._default_interlocking_xlsx_path(),
            self._t("dialog.file_filter.xlsx"),
        )
        if not path:
            return
        output_path = Path(path)
        if output_path.suffix.lower() != ".xlsx":
            output_path = output_path.with_suffix(".xlsx")

        try:
            write_xlsx_table(
                output_path,
                self._t("interlocking_table.group"),
                self._interlocking_table_export_headers(),
                self._interlocking_table_export_rows(),
                column_widths=self._interlocking_table_export_widths(),
                merged_headers=self._interlocking_table_export_merged_headers(),
            )
            self.status.showMessage(
                self._t("status.exported_interlocking_xlsx", path=output_path),
                5000,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("dialog.export_interlocking_xlsx.failed_title"),
                str(exc),
            )

    def _default_interlocking_xlsx_path(self) -> str:
        if self.current_layout.source_path is not None:
            stem = self.current_layout.source_path.stem
        else:
            stem = self.current_layout.station_id or "interlocking_table"
        return str(Path("data") / f"{stem}_interlocking_table.xlsx")

    def _interlocking_table_export_headers(self) -> list[str]:
        headers: list[str] = []
        for column in range(self.table_widget.columnCount()):
            item = self.table_widget.horizontalHeaderItem(column)
            headers.append(item.text() if item is not None else "")
        return headers

    def _interlocking_table_export_rows(self) -> list[list[str]]:
        table_rows: list[list[str]] = []
        for row in range(self.table_widget.rowCount()):
            values: list[str] = []
            for column in range(self.table_widget.columnCount()):
                item = self.table_widget.item(row, column)
                values.append(item.text() if item is not None else "")
            table_rows.append(values)
        return table_rows

    def _interlocking_table_export_merged_headers(self) -> list[tuple[str, int, int]]:
        point_label = (
            "POINTS"
            if self._translator.language == "en"
            else self._t("interlocking_table.header.point").upper()
        )
        return [
            (
                point_label,
                PointGroupedHeader.NORMAL_COLUMN,
                PointGroupedHeader.REVERSE_COLUMN,
            ),
            (
                self._t("interlocking_table.header.flank_point"),
                PointGroupedHeader.FLANK_NORMAL_COLUMN,
                PointGroupedHeader.FLANK_REVERSE_COLUMN,
            ),
        ]

    @staticmethod
    def _interlocking_table_export_widths() -> list[float]:
        return [
            7,
            18,
            12,
            16,
            12,
            12,
            14,
            16,
            18,
            22,
            18,
            18,
            18,
            12,
            12,
            20,
            18,
        ]

    def _load_layout_into_canvas(self, layout: StationLayout) -> None:
        self.current_layout = layout
        self.canvas.load_topology(layout.topology, emit_change=False)
        self._topology_change_timer.stop()
        self.runtime_workspace_service.invalidate_runtime_journal()
        self.controller.clear_runtime_session()
        self.canvas.set_runtime_view_state(None)
        self.preview_route = None
        self.canvas.clear_route_visualization()
        self._refresh_signal_selectors()
        self._refresh_interlocking_table()
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._send_smartio_runtime_snapshot()

    def _on_timing_controls_changed(self, _value: float) -> None:
        if self.controller.has_runtime_session:
            self.controller.configure_timing(
                approach_time_lock_seconds=float(self.approach_time_spin.value()),
                overlap_release_seconds=float(self.overlap_release_spin.value()),
            )
            self._sync_ui_state()
        self._refresh_interlocking_table()

    def _on_topology_changed(self) -> None:
        if self.current_layout is not None:
            self.current_layout.topology = self.canvas.topology
        self._topology_change_timer.start()

    def _flush_topology_changed(self) -> None:
        if self.current_layout is not None:
            self.current_layout.topology = self.canvas.topology
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        self.runtime_workspace_service.invalidate_runtime_journal()
        self.controller.clear_runtime_session()
        self.canvas.set_runtime_view_state(None)
        self.preview_route = None
        self.canvas.clear_route_visualization()
        self._refresh_signal_selectors()
        self._refresh_interlocking_table()
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._send_smartio_runtime_snapshot()

    def _refresh_signal_selectors(self) -> None:
        signals = sorted(self.canvas.topology.signals.keys())
        previous_entry = self.entry_combo.currentText()
        previous_exit = self.exit_combo.currentText()
        self.entry_combo.blockSignals(True)
        self.exit_combo.blockSignals(True)
        self.entry_combo.clear()
        self.exit_combo.clear()
        self.entry_combo.addItems(signals)
        self.exit_combo.addItems(signals)
        self.entry_combo.blockSignals(False)
        self.exit_combo.blockSignals(False)

        if previous_entry in signals:
            self.entry_combo.setCurrentText(previous_entry)
        if previous_exit in signals:
            self.exit_combo.setCurrentText(previous_exit)
        if (
            self.entry_combo.count() > 1
            and self.entry_combo.currentIndex() == self.exit_combo.currentIndex()
        ):
            self.exit_combo.setCurrentIndex(
                (self.entry_combo.currentIndex() + 1) % self.exit_combo.count()
            )

    def _refresh_interlocking_table(self) -> None:
        signals = sorted(self.canvas.topology.signals.keys())
        if len(signals) < 2:
            self.interlocking_rows = []
            self.valid_route_pairs = set()
            self.table_widget.setRowCount(0)
            self.export_interlocking_xlsx_action.setEnabled(False)
            return

        overlap_length = int(self.overlap_spin.value())
        cache_key = (build_topology_revision(self.canvas.topology), overlap_length)
        rows = self._interlocking_rows_cache.get(cache_key)
        if rows is None:
            rows = self.application_service.generate_interlocking_rows(
                topology=self.canvas.topology,
                overlap_length=overlap_length,
            )
            rows.sort(key=lambda item: item.route_name)
            self._interlocking_rows_cache[cache_key] = rows
            if len(self._interlocking_rows_cache) > 8:
                self._interlocking_rows_cache.pop(next(iter(self._interlocking_rows_cache)))
        self.interlocking_rows = rows
        self.valid_route_pairs = {(row.entry_signal, row.exit_signal) for row in rows}
        self.export_interlocking_xlsx_action.setEnabled(bool(rows))

        self.table_widget.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            entry_signal = self.canvas.topology.signals.get(row.entry_signal)
            approach_section = (
                entry_signal.approach_section.strip()
                if entry_signal is not None and entry_signal.approach_section.strip()
                else "-"
            )
            main_point_positions = self._main_route_point_positions(row)
            values = [
                str(row_index + 1),
                self._format_route_label(row),
                row.entry_signal,
                self._signal_aspect_text(row.signal_aspect),
                self._format_points_for_position(
                    main_point_positions,
                    PointPosition.NORMAL,
                ),
                self._format_points_for_position(
                    main_point_positions,
                    PointPosition.REVERSE,
                ),
                self._format_route_mark(row.is_reverse),
                self._format_route_mark(row.is_calling_on),
                self._format_opposing_signals(row),
                " -> ".join(row.locked_sections) if row.locked_sections else "-",
                approach_section,
                self._format_seconds(float(self.approach_time_spin.value())),
                self._format_destination_track(row),
                self._format_points_for_position(
                    row.flank_point_positions,
                    PointPosition.NORMAL,
                ),
                self._format_points_for_position(
                    row.flank_point_positions,
                    PointPosition.REVERSE,
                ),
                " -> ".join(row.overlap) if row.overlap else "-",
                self._format_seconds(float(self.overlap_release_spin.value())),
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setTextAlignment(int(Qt.AlignmentFlag.AlignCenter))
                self.table_widget.setItem(row_index, col_index, item)

        current_pair = (
            self.entry_combo.currentText().strip(),
            self.exit_combo.currentText().strip(),
        )
        if self.valid_route_pairs and current_pair not in self.valid_route_pairs:
            first_row = rows[0]
            self.entry_combo.blockSignals(True)
            self.exit_combo.blockSignals(True)
            self.entry_combo.setCurrentText(first_row.entry_signal)
            self.exit_combo.setCurrentText(first_row.exit_signal)
            self.entry_combo.blockSignals(False)
            self.exit_combo.blockSignals(False)

    def _preview_selected_route(self) -> None:
        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(
                self,
                self._t("dialog.find_route.title"),
                self._t("dialog.find_route.select_both"),
            )
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(
                self,
                self._t("dialog.find_route.title"),
                self._t("dialog.find_route.same_signal"),
            )
            return
        if (entry_signal_id, exit_signal_id) not in self.valid_route_pairs:
            QMessageBox.warning(
                self,
                self._t("dialog.find_route.title"),
                self._t(
                    "dialog.find_route.no_valid_route",
                    entry=entry_signal_id,
                    exit=exit_signal_id,
                ),
            )
            self._clear_preview_state(clear_visualization=True, sync_ui=True)
            return
        if not self._validate_signal_pair_request(
            entry_signal_id,
            exit_signal_id,
            "dialog.find_route.title",
        ):
            self._clear_preview_state(clear_visualization=True, sync_ui=False)
            return

        try:
            route = self.controller.find_route(
                topology=self.canvas.topology,
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                overlap_length=self.overlap_spin.value(),
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("dialog.route_unavailable.title"),
                str(exc),
            )
            self._clear_preview_state(clear_visualization=True, sync_ui=False)
            return

        search_order, _ = self._build_search_trace(route.path[0], route.path[-1])
        self.canvas.animate_route_search(
            search_sequence=search_order,
            route_path=route.path,
            overlap_path=route.overlap_path,
            interval_ms=220,
        )
        self.preview_route = route
        self._write_search_log(route, search_order)
        self._sync_ui_state()
        self.status.showMessage(
            self._t(
                "status.preview_route",
                entry=entry_signal_id,
                exit=exit_signal_id,
            )
        )

    def _set_selected_route(self) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_set_route:
            self.status.showMessage(
                self._t("status.workspace_mode", mode=self._mode_text(self._operating_mode)),
                2500,
            )
            QMessageBox.information(
                self,
                self._t("dialog.set_route.title"),
                self._t("dialog.set_route.switch_workspace"),
            )
            return
        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(
                self,
                self._t("dialog.set_route.title"),
                self._t("dialog.find_route.select_both"),
            )
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(
                self,
                self._t("dialog.set_route.title"),
                self._t("dialog.find_route.same_signal"),
            )
            return
        if (entry_signal_id, exit_signal_id) not in self.valid_route_pairs:
            QMessageBox.warning(
                self,
                self._t("dialog.set_route.title"),
                self._t(
                    "dialog.find_route.no_valid_route",
                    entry=entry_signal_id,
                    exit=exit_signal_id,
                ),
            )
            self._clear_preview_state(clear_visualization=True, sync_ui=True)
            return
        if not self._validate_signal_pair_request(
            entry_signal_id,
            exit_signal_id,
            "dialog.set_route.title",
        ):
            return

        try:
            route, created = self._get_or_create_locked_route(entry_signal_id, exit_signal_id)
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("dialog.set_route.failed_title"),
                str(exc),
            )
            self._clear_preview_state(clear_visualization=True, sync_ui=False)
            return

        search_order, _ = self._build_search_trace(route.path[0], route.path[-1])
        self.canvas.animate_route_search(
            search_sequence=search_order,
            route_path=route.path,
            overlap_path=route.overlap_path,
            interval_ms=160,
        )
        self.preview_route = route
        self._write_search_log(route, search_order)
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._refresh_interlocking_table()
        self._send_smartio_runtime_snapshot()
        if created:
            self.status.showMessage(
                self._t(
                    "status.route_set",
                    entry=entry_signal_id,
                    exit=exit_signal_id,
                )
            )
        else:
            self.status.showMessage(
                self._t(
                    "status.route_already_active",
                    entry=entry_signal_id,
                    exit=exit_signal_id,
                )
            )

    def _on_table_row_clicked(self, row_index: int, column_index: int) -> None:
        if row_index < 0 or row_index >= len(self.interlocking_rows):
            return
        row = self.interlocking_rows[row_index]
        if column_index == self.SIGNAL_ASPECT_COLUMN:
            if self._operating_mode is not OperatingMode.DESIGN_LAYOUT:
                self._render_interlocking_row_log(row)
                return
            self._cycle_route_signal_aspect(row)
            route_name = row.route_name
            self.canvas.topology_changed.emit()
            self._refresh_interlocking_table()
            for next_row_index, next_row in enumerate(self.interlocking_rows):
                if next_row.route_name == route_name:
                    self.table_widget.setCurrentCell(next_row_index, column_index)
                    self._render_interlocking_row_log(next_row)
                    break
            return
        if column_index == self.CALLING_ON_ROUTE_COLUMN:
            self._render_interlocking_row_log(row)
            return
        if column_index == self.REVERSE_ROUTE_COLUMN:
            self._render_interlocking_row_log(row)
            return
        self.entry_combo.setCurrentText(row.entry_signal)
        self.exit_combo.setCurrentText(row.exit_signal)
        search_order, _ = self._build_search_trace(row.path[0], row.path[-1])
        self.canvas.animate_route_search(
            search_sequence=search_order,
            route_path=row.path,
            overlap_path=row.overlap,
            interval_ms=180,
        )
        self._render_interlocking_row_log(row, search_order=search_order)

    def _render_interlocking_row_log(
        self,
        row: InterlockingTableRow,
        search_order: list[str] | None = None,
    ) -> None:
        effective_search_order = (
            list(search_order)
            if search_order is not None
            else self._build_search_trace(row.path[0], row.path[-1])[0]
        )
        entry_signal = self.canvas.topology.signals.get(row.entry_signal)
        self.search_log.setPlainText(
            self.route_presenter.build_interlocking_row_search_log(
                route_id=row.route_name,
                route_label=self._format_route_label(row),
                entry_signal=row.entry_signal,
                exit_signal=row.exit_signal,
                entry_protects=row.entry_element or "-",
                exit_protects=row.exit_element or "-",
                direction=entry_signal.direction.value if entry_signal is not None else "-",
                approach_locking_section=(
                    entry_signal.approach_section.strip()
                    if entry_signal is not None and entry_signal.approach_section.strip()
                    else "-"
                ),
                search_order=effective_search_order,
                locked_path=row.path,
                overlap_path=row.overlap,
                destination_track=self._format_destination_track(row),
                point_locks=self._main_route_point_positions(row),
                flank_point_locks=row.flank_point_positions,
                monitored_flank_sections=[],
                opposing_signals=self._opposing_signals_for_row(row),
                conflicting_routes=sorted(set(row.conflicting_routes)),
                overlap_release_seconds=float(self.overlap_release_spin.value()),
            )
        )

    def _build_search_trace(
        self,
        source_node_id: str,
        target_node_id: str,
    ) -> tuple[list[str], list[str]]:
        graph = self.canvas.topology.routing_graph()
        if source_node_id not in graph.nodes or target_node_id not in graph.nodes:
            return [], []

        queue: deque[str] = deque([source_node_id])
        visited: set[str] = {source_node_id}
        parent: dict[str, str] = {}
        search_order: list[str] = []

        while queue:
            current = queue.popleft()
            search_order.append(current)
            if current == target_node_id:
                break
            for successor in sorted(graph.successors(current)):
                if successor in visited:
                    continue
                visited.add(successor)
                parent[successor] = current
                queue.append(successor)

        if target_node_id not in visited:
            return search_order, []

        path = [target_node_id]
        while path[-1] != source_node_id:
            path.append(parent[path[-1]])
        path.reverse()
        return search_order, path

    def _write_search_log(self, route: Route, search_order: list[str]) -> None:
        entry_signal = self.canvas.topology.signals.get(route.entry_signal_id)
        exit_signal = self.canvas.topology.signals.get(route.exit_signal_id)
        lifecycle = route.lifecycle_state.value if getattr(route, "lifecycle_state", None) else "-"

        approach_lock_state, approach_lock_remaining = self.controller.approach_lock_details(
            route.id
        )

        self.search_log.setPlainText(
            self.route_presenter.build_route_search_log(
                route,
                search_order,
                route_label=f"{route.entry_signal_id}->{route.exit_signal_id}",
                entry_protects=(entry_signal.protects if entry_signal is not None else "-"),
                exit_protects=(exit_signal.protects if exit_signal is not None else "-"),
                direction=(entry_signal.direction.value if entry_signal is not None else "-"),
                lifecycle=lifecycle,
                destination_track=self._destination_track_from_path(route.path, fallback="-"),
                opposing_signals=self._opposing_signals_for_route(route),
                conflicting_routes=self._conflicting_routes_for_pair(
                    route.entry_signal_id, route.exit_signal_id
                ),
                approach_lock_state=approach_lock_state,
                approach_lock_remaining_seconds=approach_lock_remaining,
                overlap_release_seconds=float(self.overlap_release_spin.value()),
            )
        )

    def _format_point_locks(self, required_points: dict[str, PointPosition]) -> str:
        return self.route_presenter.format_point_locks(required_points)

    @staticmethod
    def _format_points_for_position(
        required_points: dict[str, PointPosition],
        position: PointPosition,
    ) -> str:
        points = InterlockingTableGenerator.point_ids_for_position(required_points, position)
        return ", ".join(points) if points else "-"

    @staticmethod
    def _format_route_label(row: InterlockingTableRow) -> str:
        return f"{row.entry_signal} -> {row.exit_signal}"

    @staticmethod
    def _format_route_mark(value: bool) -> str:
        return "\u221a" if value else ""

    def _cycle_route_signal_aspect(self, row: InterlockingTableRow) -> None:
        route_type = (
            ROUTE_TYPE_CALLING_ON
            if row.is_calling_on
            else ROUTE_TYPE_REVERSE
            if row.is_reverse
            else self.canvas.topology.route_type(row.entry_signal, row.exit_signal)
        )
        allowed = self.canvas.topology.allowed_route_signal_aspects(route_type)
        current = self.canvas.topology.route_signal_aspect_for_type(
            row.entry_signal,
            row.exit_signal,
            route_type,
        )
        try:
            current_index = allowed.index(current)
        except ValueError:
            current_index = -1
        next_aspect = allowed[(current_index + 1) % len(allowed)]
        self.canvas.topology.set_route_signal_aspect_for_type(
            row.entry_signal,
            row.exit_signal,
            next_aspect,
            route_type,
        )

    def _destination_track_from_path(self, path: list[str], fallback: str = "-") -> str:
        for node_id in reversed(path):
            element = self.canvas.topology.get_element(node_id)
            if isinstance(element, TrackSection):
                return node_id
        return fallback

    def _format_opposing_signals(self, row: InterlockingTableRow) -> str:
        opposing = self._opposing_signals_for_row(row)
        if not opposing:
            return "-"
        return ", ".join(opposing)

    def _format_destination_track(self, row: InterlockingTableRow) -> str:
        return self._destination_track_from_path(row.path, fallback=row.exit_element or "-")

    def _main_route_point_positions(self, row: InterlockingTableRow) -> dict[str, PointPosition]:
        try:
            return RouteEngine(self.canvas.topology).compute_required_point_positions(
                [*row.path, *row.overlap]
            )
        except ValueError:
            main_points = dict(row.required_point_positions)
            for point_id in row.flank_point_positions:
                main_points.pop(point_id, None)
            return main_points

    def _opposing_signals_for_row(self, row: InterlockingTableRow) -> list[str]:
        entry_signal = self.canvas.topology.signals.get(row.entry_signal)
        if entry_signal is None:
            return []
        route_footprint = set(row.path)
        route_footprint.update(row.overlap)
        route_footprint.add(row.entry_element)
        route_footprint.add(row.exit_element)
        return sorted(
            signal.id
            for signal in self.canvas.topology.signals.values()
            if signal.id != row.entry_signal
            and signal.direction != entry_signal.direction
            and signal.protects.strip() in route_footprint
        )

    def _opposing_signals_for_route(self, route: Route) -> list[str]:
        row_like = InterlockingTableRow(
            route_name=route.id,
            entry_signal=route.entry_signal_id,
            exit_signal=route.exit_signal_id,
            entry_element=self.canvas.topology.signals.get(route.entry_signal_id).protects
            if self.canvas.topology.signals.get(route.entry_signal_id) is not None
            else "",
            exit_element=self.canvas.topology.signals.get(route.exit_signal_id).protects
            if self.canvas.topology.signals.get(route.exit_signal_id) is not None
            else "",
            entry_protected_section=None,
            exit_protected_section=None,
            path=list(route.path),
            overlap=list(route.overlap_path),
            required_point_positions=dict(route.required_point_positions),
            flank_point_positions=dict(route.flank_point_positions),
            locked_sections=[],
            conflicting_routes=[],
            is_calling_on=route.is_calling_on,
            is_reverse=route.is_reverse,
            signal_aspect=route.signal_aspect,
        )
        return self._opposing_signals_for_row(row_like)

    def _conflicting_routes_for_pair(self, entry_signal_id: str, exit_signal_id: str) -> list[str]:
        for row in self.interlocking_rows:
            if row.entry_signal == entry_signal_id and row.exit_signal == exit_signal_id:
                return sorted(set(row.conflicting_routes))
        return []

    def _format_seconds(self, value_seconds: float) -> str:
        return f"{value_seconds:.1f}{self._t('unit.seconds_suffix')}"

    def _validate_signal_pair_request(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        title_key: str,
    ) -> bool:
        issues = self.application_service.validate_signal_pair(
            self.canvas.topology,
            entry_signal_id,
            exit_signal_id,
        )
        if not issues:
            return True
        issue_lines = "\n".join(f"- {issue}" for issue in issues)
        QMessageBox.warning(
            self,
            self._t(title_key),
            self._t("dialog.invalid_signal_config.message", issues=issue_lines),
        )
        return False

    def _start_simulation(self) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_start_simulation:
            self.status.showMessage(
                self._t("status.workspace_mode", mode=self._mode_text(self._operating_mode)),
                2500,
            )
            QMessageBox.information(
                self,
                self._t("dialog.simulation.title"),
                self._t("dialog.simulation.switch_workspace"),
            )
            return
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
            self._sync_ui_state()
            self.status.showMessage(self._t("status.simulation_stopped"))
            return

        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(
                self,
                self._t("dialog.simulation.title"),
                self._t("dialog.simulation.select_both"),
            )
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(
                self,
                self._t("dialog.simulation.title"),
                self._t("dialog.simulation.same_signal"),
            )
            return
        if len(self.canvas.topology.signals) < 2:
            QMessageBox.warning(
                self,
                self._t("dialog.simulation.title"),
                self._t("dialog.simulation.at_least_two_signals"),
            )
            return
        if not self._validate_signal_pair_request(
            entry_signal_id,
            exit_signal_id,
            "dialog.simulation.title",
        ):
            return

        route = self._get_active_route_for_pair(entry_signal_id, exit_signal_id)
        if route is None:
            QMessageBox.warning(
                self,
                self._t("dialog.simulation.title"),
                self._t("dialog.simulation.set_route_first"),
            )
            return

        try:
            start_result = self.controller.start_route_simulation(
                topology=self.canvas.topology,
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                overlap_length=self.overlap_spin.value(),
                approach_time_lock_seconds=float(self.approach_time_spin.value()),
                overlap_release_seconds=float(self.overlap_release_spin.value()),
                train_speed=1.0,
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._t("dialog.simulation_failed.title"),
                str(exc),
            )
            self.canvas.refresh_visual_state()
            self._sync_ui_state()
            return

        route = start_result.route
        train = start_result.train
        simulation_start_section = start_result.simulation_start_section
        visual_route_path = start_result.visual_route_path
        search_order, _ = self._build_search_trace(simulation_start_section, route.path[-1])
        self.canvas.animate_route_search(
            search_sequence=search_order,
            route_path=visual_route_path,
            overlap_path=route.overlap_path,
            interval_ms=160,
        )
        self._write_search_log(route, search_order)
        self._simulation_ticks_remaining = start_result.suggested_ticks
        self.canvas.refresh_visual_state()
        self.status.showMessage(
            self._t(
                "status.simulation_running",
                entry=entry_signal_id,
                exit=exit_signal_id,
                route_id=route.id,
                train_id=train.id,
                start=simulation_start_section,
            )
        )
        self._simulation_timer.start(700)
        self._sync_ui_state()
        self._send_smartio_runtime_snapshot()

    def _get_active_route_for_pair(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
    ) -> Route | None:
        return self.controller.get_active_route_for_pair(entry_signal_id, exit_signal_id)

    def _get_or_create_locked_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
    ) -> tuple[Route, bool]:
        result = self.controller.set_or_reuse_route(
            topology=self.canvas.topology,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=self.overlap_spin.value(),
            approach_time_lock_seconds=float(self.approach_time_spin.value()),
            overlap_release_seconds=float(self.overlap_release_spin.value()),
        )
        return result.route, result.created

    def _simulation_tick(self) -> None:
        if not self.controller.has_runtime_session:
            self._simulation_timer.stop()
            self._sync_ui_state()
            return
        try:
            step_view_state = self.controller.step_runtime()
            self.canvas.set_runtime_view_state(step_view_state)
            self.canvas.refresh_visual_state()
            self._send_smartio_runtime_snapshot()
        except Exception as exc:
            self._simulation_timer.stop()
            self.canvas.refresh_visual_state()
            QMessageBox.critical(
                self,
                self._t("dialog.fail_safe_stop.title"),
                str(exc),
            )
            self._sync_ui_state()
            self.status.showMessage(self._t("status.simulation_halted_fail_safe"))
            return

        self._simulation_ticks_remaining -= 1
        if self._simulation_ticks_remaining <= 0:
            self._simulation_timer.stop()
            self._sync_ui_state()
            self.status.showMessage(self._t("status.simulation_complete"))

    def _emergency_release_routes(self, show_message: bool = True) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_cancel_route:
            if show_message:
                self.status.showMessage(self._t("status.emergency_release_disabled"))
            return
        if not self.controller.has_runtime_session:
            if show_message:
                self.status.showMessage(self._t("status.no_active_simulation_routes"))
            return
        if not self.controller.has_active_routes():
            if show_message:
                self.status.showMessage(self._t("status.no_active_routes"))
            return

        password, ok = QInputDialog.getText(
            self,
            self._t("dialog.emergency_release.title"),
            self._t("dialog.emergency_release.password_prompt"),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return

        expected_password = str(getattr(self.application_profile, "emergency_release_password", ""))
        if str(password) != expected_password:
            QMessageBox.warning(
                self,
                self._t("dialog.emergency_release.title"),
                self._t("dialog.emergency_release.password_invalid"),
            )
            return

        emergency_result = self.controller.emergency_release_active_routes()
        self.canvas.clear_route_visualization()
        self.canvas.refresh_visual_state()
        self._refresh_interlocking_table()
        self._send_smartio_runtime_snapshot()
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        self._sync_ui_state()

        if emergency_result.failures:
            QMessageBox.warning(
                self,
                self._t("dialog.emergency_release.title"),
                self._t(
                    "dialog.emergency_release.some_failed",
                    details="\n".join(emergency_result.failures),
                ),
            )
            return
        if show_message:
            self.status.showMessage(self._t("status.emergency_released_all_active_routes"))

    def _cancel_active_routes(self, show_message: bool = True) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_cancel_route:
            if show_message:
                self.status.showMessage(self._t("status.cancel_route_disabled"))
            return
        if not self.controller.has_runtime_session:
            if show_message:
                self.status.showMessage(self._t("status.no_active_simulation_routes"))
            return

        if not self.controller.has_active_routes():
            if show_message:
                self.status.showMessage(self._t("status.no_active_routes"))
            return

        cancel_result = self.controller.cancel_active_routes()
        self.canvas.clear_route_visualization()
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._refresh_interlocking_table()
        self._send_smartio_runtime_snapshot()

        if cancel_result.failures:
            QMessageBox.warning(
                self,
                self._t("dialog.cancel_route.title"),
                self._t(
                    "dialog.cancel_route.some_locked",
                    details="\n".join(cancel_result.failures),
                ),
            )
        elif show_message:
            self.status.showMessage(self._t("status.cancelled_all_active_routes"))

    def _sync_ui_state(self) -> None:
        self.canvas.set_runtime_view_state(self.controller.runtime_view_state())
        has_signals = self.entry_combo.count() > 1 and self.exit_combo.count() > 1
        if self.controller.has_runtime_session:
            self.canvas.refresh_visual_state()

        selected_entry = self.entry_combo.currentText().strip()
        selected_exit = self.exit_combo.currentText().strip()
        selected_pair_defined = (
            bool(selected_entry)
            and bool(selected_exit)
            and (selected_entry, selected_exit) in self.valid_route_pairs
        )
        selected_pair_ready = (
            selected_pair_defined
            and self._get_active_route_for_pair(selected_entry, selected_exit) is not None
        )

        has_active_routes = self.controller.has_active_routes()
        capabilities = self.mode_policy.capabilities(self._operating_mode)
        simulation_running = self._simulation_timer.isActive()
        workspace_state = self.workspace_state_coordinator.evaluate(
            capabilities=capabilities,
            has_signals=has_signals,
            selected_pair_defined=selected_pair_defined,
            selected_pair_ready=selected_pair_ready,
            has_active_routes=has_active_routes,
            simulation_running=simulation_running,
        )
        runtime_degraded = self._operating_mode is OperatingMode.RUNTIME and bool(
            self._runtime_transport_health.get("degraded", False)
        )
        runtime_edit_lock_reason = self._t("main.lock.runtime_edit_reason")
        self.canvas.set_runtime_edit_lock(
            self.mode_policy.runtime_edit_locked(self._operating_mode),
            runtime_edit_lock_reason,
        )
        self.mode_status_label.setText(
            self._t(
                "mode.status",
                mode=self._mode_text(self._operating_mode),
            )
        )
        self.new_layout_action.setEnabled(workspace_state.layout_edit_enabled)
        self.save_layout_action.setEnabled(workspace_state.layout_edit_enabled)
        self.load_layout_action.setEnabled(workspace_state.layout_edit_enabled)
        self.connect_mode_action.setEnabled(workspace_state.connect_mode_enabled)

        self.find_route_button.setEnabled(workspace_state.find_route_enabled)
        simulation_workspace = self._operating_mode is OperatingMode.SIMULATION
        self.open_smartio_local_button.setEnabled(simulation_workspace)
        self.open_smartio_local_action.setEnabled(simulation_workspace)
        self.export_interlocking_xlsx_action.setEnabled(bool(self.interlocking_rows))
        self.set_route_button.setEnabled(workspace_state.set_route_enabled and not runtime_degraded)
        self.set_route_action.setEnabled(workspace_state.set_route_enabled and not runtime_degraded)
        self.cancel_route_button.setEnabled(
            workspace_state.cancel_route_enabled and not runtime_degraded
        )
        self.cancel_route_action.setEnabled(
            workspace_state.cancel_route_enabled and not runtime_degraded
        )
        self.emergency_release_button.setEnabled(
            workspace_state.cancel_route_enabled and not runtime_degraded
        )
        self.emergency_release_action.setEnabled(
            workspace_state.cancel_route_enabled and not runtime_degraded
        )
        self.approach_time_spin.setEnabled(workspace_state.route_timing_enabled)
        self.overlap_release_spin.setEnabled(workspace_state.route_timing_enabled)

        self.simulation_action.setText(
            self._t("toolbar.stop_simulation")
            if workspace_state.simulation_running
            else self._t("toolbar.start_simulation")
        )
        self.simulation_action.setEnabled(
            workspace_state.simulation_enabled and not runtime_degraded
        )
        self.simulate_button.setText(
            self._t("button.stop_sim_short")
            if workspace_state.simulation_running
            else self._t("button.start_simulation")
        )
        self.simulate_button.setEnabled(workspace_state.simulation_enabled and not runtime_degraded)
        self._apply_workspace_visibility_profile()
        self._update_runtime_connection_label()

    def _apply_workspace_visibility_profile(self) -> None:
        """Apply per-workspace visibility profile for toolbar and action buttons."""
        runtime_mode = self._operating_mode is OperatingMode.RUNTIME
        design_mode = self._operating_mode is OperatingMode.DESIGN_LAYOUT
        simulation_mode = self._operating_mode is OperatingMode.SIMULATION
        # Left editor workspace is not used in Runtime operations.
        self.palette.setVisible(not runtime_mode and not simulation_mode)

        # Toolbar profile by workspace.
        self.new_layout_action.setVisible(not runtime_mode and not simulation_mode)
        self.save_layout_action.setVisible(not runtime_mode and not simulation_mode)
        self.load_layout_action.setVisible(not runtime_mode and not simulation_mode)
        self.connect_mode_action.setVisible(not runtime_mode and not simulation_mode)
        self.set_route_action.setVisible(not design_mode)
        self.cancel_route_action.setVisible(not design_mode)
        self.emergency_release_action.setVisible(not design_mode)
        self.simulation_action.setVisible(not runtime_mode and not design_mode)
        self.open_smartio_local_action.setVisible(simulation_mode)
        self.export_interlocking_xlsx_action.setVisible(True)
        self.more_tool_button.setVisible(
            self.emergency_release_action.isVisible()
            or self.open_smartio_local_action.isVisible()
        )
        self.more_tool_button.setEnabled(self.more_tool_button.isVisible())

        # Button/profile in right panel.
        self.open_smartio_local_button.setVisible(simulation_mode)
        self.set_route_button.setVisible(not design_mode)
        self.cancel_route_button.setVisible(not design_mode)
        self.emergency_release_button.setVisible(not design_mode)
        self.find_route_button.setVisible(not runtime_mode and not design_mode)
        self.simulate_button.setVisible(not runtime_mode and not design_mode)

        # Runtime keeps monitoring widgets visible while hiding local search/timing controls.
        self.route_help_label.setVisible(not runtime_mode)
        self.overlap_label.setVisible(not runtime_mode)
        self.overlap_spin.setVisible(not runtime_mode)

        self.approach_release_label.setVisible(not runtime_mode)
        self.approach_time_spin.setVisible(not runtime_mode)
        self.overlap_release_label.setVisible(not runtime_mode)
        self.overlap_release_spin.setVisible(not runtime_mode)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._webclient_runtime_timer.stop()
        self.smartio_coordinator.disconnect()
        self._stop_smartio_local_process()
        self._stop_webclient_server_process()
        super().closeEvent(event)
