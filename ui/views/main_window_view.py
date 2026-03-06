"""Main application window for the geographical interlocking simulator."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.application import AppMode
from core.domain.model.elements import PointPosition, TrackSection
from core.compiler.interlocking_table import InterlockingTableRow
from core.domain.model.route import Route
from core.infrastructure.smartio import (
    SmartIOProtocolError,
    SmartIORuntimeAdapter,
    SmartIOWebSocketClient,
)
from core.runtime.simulation import Simulation
from generic_application import GenericApplicationProfile, GenericApplicationService
from specific_application import SpecificLayoutEditorService, StationLayout
from ui.controllers import MainWindowController
from ui.i18n import SUPPORTED_LANGUAGES, UITranslator, normalize_language
from ui.presenters import RoutePresenter
from ui.views.canvas_editor_view import CanvasEditor
from ui.views.components_palette_view import ComponentsPalette


OperatingMode = AppMode


class MainWindow(QMainWindow):
    """Top-level editor + simulator window."""

    def __init__(self, application_profile: GenericApplicationProfile | None = None) -> None:
        super().__init__()
        self.resize(1700, 900)

        self.application_profile = application_profile or GenericApplicationProfile()
        self._translator = UITranslator(getattr(self.application_profile, "ui_language", "en"))
        self.application_service = GenericApplicationService(profile=self.application_profile)
        self.controller = MainWindowController(self.application_service)
        self.route_presenter = RoutePresenter(self._translator)
        self.mode_policy = self.application_service.mode_policy
        self.layout_editor_service = SpecificLayoutEditorService(self.application_service)
        self.current_layout = self.layout_editor_service.new_layout(station_id="UNNAMED")
        self._operating_mode = OperatingMode.DESIGN_LAYOUT
        self._smartio_client: SmartIOWebSocketClient | None = None
        self._smartio_status_token = "disconnected"

        self.palette = ComponentsPalette(self._translator, self)
        self.canvas = CanvasEditor(self, translator=self._translator)
        self.canvas.set_manual_override_handler(self._manual_override_from_canvas)
        self.right_panel = self._build_right_panel()
        self.palette.properties_applied.connect(self._on_properties_applied)
        self.palette.component_insert_requested.connect(self._insert_component_from_palette)
        self.canvas.node_selected.connect(self.palette.set_selected_element)
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

        self.simulation: Optional[Simulation] = None
        self.canvas.set_simulation(None)
        self.preview_route: Optional[Route] = None
        self.interlocking_rows: list[InterlockingTableRow] = []
        self.valid_route_pairs: set[tuple[str, str]] = set()
        self._simulation_timer = QTimer(self)
        self._simulation_timer.timeout.connect(self._simulation_tick)
        self._simulation_ticks_remaining = 0
        self._initialize_smartio_client()

        sample_path = Path("data/sample_layout.json")
        if sample_path.exists():
            self._load_layout_into_canvas(
                self.layout_editor_service.load_layout(
                    sample_path,
                    station_id=sample_path.stem,
                    load_runtime_state=False,
                    load_occupancy=True,
                )
            )
            self.status.showMessage(
                self._t("status.loaded_sample_layout", path=sample_path)
            )
        else:
            self.canvas.load_topology(self.current_layout.topology)
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

    def _populate_language_selector(self) -> None:
        current_language = self._translator.language
        options = [code for code in SUPPORTED_LANGUAGES if code in {"en", "vi"}] or ["en", "vi"]
        self.language_combo.blockSignals(True)
        self.language_combo.clear()
        for language_code in options:
            option_key = (
                "language.option.vi"
                if language_code == "vi"
                else "language.option.en"
            )
            self.language_combo.addItem(self._t(option_key), language_code)
        selected_index = self.language_combo.findData(current_language)
        self.language_combo.setCurrentIndex(selected_index if selected_index >= 0 else 0)
        self.language_combo.blockSignals(False)

    def _set_table_headers(self) -> None:
        self.table_widget.setHorizontalHeaderLabels(
            [
                self._t("interlocking_table.header.no"),
                self._t("interlocking_table.header.route"),
                self._t("interlocking_table.header.signal"),
                self._t("interlocking_table.header.point"),
                self._t("interlocking_table.header.opposing_signal"),
                self._t("interlocking_table.header.track"),
                self._t("interlocking_table.header.approach_lock_track"),
                self._t("interlocking_table.header.approach_lock_release"),
                self._t("interlocking_table.header.destination_track"),
                self._t("interlocking_table.header.flank_point"),
                self._t("interlocking_table.header.overlap"),
                self._t("interlocking_table.header.overlap_release"),
            ]
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
        self.entry_label.setText(self._t("field.entry"))
        self.exit_label.setText(self._t("field.exit"))
        self.overlap_label.setText(self._t("field.overlap"))
        self.approach_release_label.setText(self._t("field.approach_release"))
        self.overlap_release_label.setText(self._t("field.overlap_release"))

        self.find_route_button.setText(self._t("button.find_route"))
        self.set_route_button.setText(self._t("button.set_route"))
        self.cancel_route_button.setText(self._t("button.cancel_route"))
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

        self.connect_mode_action = self.toolbar.addAction(self._t("toolbar.connect_mode"))
        self.connect_mode_action.setCheckable(True)
        self.connect_mode_action.toggled.connect(self._toggle_connect_mode)

        self.set_route_action = self.toolbar.addAction(self._t("toolbar.set_route"))
        self.set_route_action.triggered.connect(self._set_selected_route)

        self.cancel_route_action = self.toolbar.addAction(self._t("toolbar.cancel_route"))
        self.cancel_route_action.triggered.connect(lambda: self._cancel_active_routes())

        self.simulation_action = self.toolbar.addAction(self._t("toolbar.start_simulation"))
        self.simulation_action.triggered.connect(self._start_simulation)

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

        self.table_group = QGroupBox(self._t("interlocking_table.group"))
        table_layout = QVBoxLayout(self.table_group)
        self.table_widget = QTableWidget(0, 12, self.table_group)
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
        ws_url = str(getattr(self.application_profile, "smart_io_ws_url", "")).strip()
        if not ws_url:
            self._smartio_status_token = "disabled"
            return
        self._smartio_client = SmartIOWebSocketClient(
            ws_url=ws_url,
            reconnect_enabled=bool(
                getattr(self.application_profile, "smart_io_reconnect_enabled", True)
            ),
            reconnect_max_seconds=float(
                getattr(self.application_profile, "smart_io_reconnect_max_seconds", 30.0)
            ),
            parent=self,
        )
        self._smartio_client.status_changed.connect(self._on_smartio_status_changed)
        self._smartio_client.error_occurred.connect(self._on_smartio_error)
        self._smartio_client.event_received.connect(self._on_smartio_event_received)
        self._ensure_smartio_connection()

    def _on_smartio_status_changed(self, status: str) -> None:
        self._smartio_status_token = str(status).strip() or "disconnected"
        if self._smartio_status_token == "connected":
            self._send_smartio_hello()
            self._send_smartio_runtime_snapshot()
        self._update_runtime_connection_label()

    def _on_smartio_error(self, message: str) -> None:
        text = str(message).strip()
        if text:
            self.status.showMessage(self._t("status.smartio_error", message=text), 5000)
        self._update_runtime_connection_label()

    def _on_smartio_event_received(self, event: dict) -> None:
        event_type = str(event.get("type", "")).strip().lower()
        payload = event.get("payload", {})
        if event_type == "state_update" and isinstance(payload, dict):
            self._apply_smartio_state_update(payload)
        self._update_runtime_connection_label()

    def _apply_smartio_state_update(self, payload: dict) -> None:
        if self.simulation is None:
            self.simulation = self.application_service.create_simulation(self.canvas.topology)
            self.canvas.set_simulation(self.simulation)
        try:
            adapter = SmartIORuntimeAdapter(
                self.simulation,
                default_overlap_length=int(self.application_profile.default_overlap_length),
            )
            adapter.apply_state_update(payload)
        except SmartIOProtocolError as exc:
            self.status.showMessage(
                self._t("status.smartio_error", message=f"{exc.code}: {exc}"),
                5000,
            )
            return
        except Exception as exc:
            message = str(exc)
            self.status.showMessage(self._t("status.smartio_error", message=message), 5000)
            if "Sequence locking violation" in message:
                QMessageBox.warning(
                    self,
                    self._t("dialog.property_update_failed.title"),
                    message,
                )
            return

        for section_item in payload.get("sections", []):
            if not isinstance(section_item, dict):
                continue
            section_id = str(section_item.get("id", "")).strip()
            if section_id:
                self._refresh_route_log_for_section(section_id)
        self.canvas.refresh_visual_state()
        self._sync_ui_state()
        self._refresh_interlocking_table()
        self._send_smartio_runtime_snapshot()

    def _send_smartio_hello(self) -> None:
        if self._smartio_client is None or not self._smartio_client.is_connected:
            return
        try:
            envelope = self._smartio_client.build_envelope("hello", {"role": "cbi"})
            self._smartio_client.send_event(envelope)
        except Exception:
            return

    def _send_smartio_runtime_snapshot(self) -> None:
        if self._smartio_client is None or not self._smartio_client.is_connected:
            return
        try:
            snapshot = self.application_service.build_runtime_snapshot(self.simulation)
            snapshot["layout"] = self.application_service.build_layout_payload(self.canvas.topology)
            envelope = self._smartio_client.build_envelope("runtime_snapshot", snapshot)
            self._smartio_client.send_event(envelope)
        except Exception:
            return

    def _smartio_state_text(self) -> str:
        token = str(self._smartio_status_token or "").strip().lower()
        if token.startswith("reconnecting_in_") and token.endswith("s"):
            delay = token.removeprefix("reconnecting_in_").removesuffix("s")
            if delay.isdigit():
                return self._t("smartio.state.reconnecting", seconds=int(delay))
        if token == "connected":
            return self._t("smartio.state.connected")
        if token == "connecting":
            return self._t("smartio.state.connecting")
        if token == "error":
            return self._t("smartio.state.error")
        if token == "disabled":
            return self._t("smartio.state.disabled")
        return self._t("smartio.state.disconnected")

    def _update_runtime_connection_label(self) -> None:
        if not hasattr(self, "runtime_connection_label") or not hasattr(
            self,
            "runtime_connection_badge",
        ):
            return
        show_runtime_status = self._operating_mode is OperatingMode.RUNTIME
        self.runtime_connection_badge.setVisible(show_runtime_status)
        self.runtime_connection_label.setVisible(show_runtime_status)
        if not show_runtime_status:
            return
        raw_token = str(self._smartio_status_token or "").strip().lower()
        normalized_token = raw_token
        if raw_token.startswith("reconnecting_in_"):
            normalized_token = "reconnecting"
        badge_style = {
            "connected": "background:#23a55a; border:1px solid #1b7f46;",
            "connecting": "background:#2f6feb; border:1px solid #2456b7;",
            "reconnecting": "background:#d29922; border:1px solid #9f7218;",
            "error": "background:#da3633; border:1px solid #a92c2a;",
            "disabled": "background:#8b949e; border:1px solid #6e7781;",
            "disconnected": "background:#8b949e; border:1px solid #6e7781;",
        }.get(normalized_token, "background:#8b949e; border:1px solid #6e7781;")
        self.runtime_connection_badge.setToolTip(self._smartio_state_text())
        self.runtime_connection_badge.setStyleSheet(
            f"border-radius: 6px; min-width: 12px; max-width: 12px; "
            f"min-height: 12px; max-height: 12px; {badge_style}"
        )
        self.runtime_connection_label.setText(
            self._t(
                "runtime.smartio.status",
                state=self._smartio_state_text(),
                url=str(getattr(self.application_profile, "smart_io_ws_url", "")).strip()
                or "-",
            )
        )

    def _sync_smartio_connection_for_mode(self, mode: OperatingMode) -> None:
        _ = mode
        self._ensure_smartio_connection()

    def _ensure_smartio_connection(self) -> None:
        if self._smartio_client is None:
            return
        if not self._smartio_client.is_connected:
            self._smartio_client.connect()

    def _allow_runtime_workspace(self) -> bool:
        if self._smartio_client is None:
            return False
        self._ensure_smartio_connection()
        return bool(self._smartio_client.is_connected)

    def _set_operating_mode(self, mode: OperatingMode, *, announce: bool = True) -> None:
        previous_mode = self._operating_mode
        if mode is OperatingMode.RUNTIME and not self._allow_runtime_workspace():
            if hasattr(self, "mode_tabs"):
                self.mode_tabs.blockSignals(True)
                self.mode_tabs.setCurrentIndex(self._tab_index_for_mode(previous_mode))
                self.mode_tabs.blockSignals(False)
            QMessageBox.warning(
                self,
                self._t("dialog.runtime_requires_smartio.title"),
                self._t(
                    "dialog.runtime_requires_smartio.message",
                    url=str(getattr(self.application_profile, "smart_io_ws_url", "")).strip() or "-",
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
        self.palette.component_list.setEnabled(design_mode)
        if design_mode:
            self.palette.component_list.setToolTip("")
        else:
            self.palette.component_list.setToolTip(
                self._t("main.tooltip.component_insertion_disabled")
            )

        self._sync_ui_state()
        self._sync_smartio_connection_for_mode(mode)
        self._update_runtime_connection_label()
        if announce and previous_mode is not mode:
            self.status.showMessage(
                self._t("status.workspace_mode", mode=self._mode_text(mode))
            )

    def _on_properties_applied(self, element_id: str, updates: dict) -> None:
        try:
            current_id = element_id
            new_id = str(updates.pop("id", "")).strip()
            if new_id and new_id != element_id:
                self.canvas.rename_node(element_id, new_id)
                current_id = new_id

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
        if not self.canvas.is_layout_edit_locked():
            return []
        if self.simulation is None:
            self.simulation = self.application_service.create_simulation(self.canvas.topology)
            self.canvas.set_simulation(self.simulation)
        result = self.application_service.manual_set_section_occupied(
            simulation=self.simulation,
            section_id=section_id,
            occupied=occupied_after,
        )
        self._refresh_route_log_for_section(section_id)
        self._send_smartio_runtime_snapshot()
        return list(result.removed_trains)

    def _refresh_route_log_for_section(self, section_id: str) -> None:
        """Refresh route log so lifecycle text tracks manual occupancy clicks."""
        route_for_log: Route | None = None
        normalized_section = str(section_id).strip()

        if self.simulation is not None:
            for active_route in self.simulation.locking_engine.active_routes.values():
                if normalized_section in active_route.full_path:
                    route_for_log = active_route
                    break
                approach_section = (active_route.approach_locking_section or "").strip()
                if approach_section and approach_section == normalized_section:
                    route_for_log = active_route
                    break

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
        keep_occupancy = (
            QMessageBox.question(
                self,
                self._t("dialog.load_occupancy.title"),
                self._t("dialog.load_occupancy.message"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            == QMessageBox.StandardButton.Yes
        )
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

    def _load_layout_into_canvas(self, layout: StationLayout) -> None:
        self.current_layout = layout
        self.canvas.load_topology(layout.topology)
        self._send_smartio_runtime_snapshot()

    def _on_timing_controls_changed(self, _value: float) -> None:
        if self.simulation is not None:
            self.application_service.configure_simulation_timing(
                self.simulation,
                approach_time_lock_seconds=float(self.approach_time_spin.value()),
                overlap_release_seconds=float(self.overlap_release_spin.value()),
            )
            self._sync_ui_state()
        self._refresh_interlocking_table()

    def _on_topology_changed(self) -> None:
        if self.current_layout is not None:
            self.current_layout.topology = self.canvas.topology
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
        self.simulation = None
        self.canvas.set_simulation(None)
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
        if self.entry_combo.count() > 1 and self.entry_combo.currentIndex() == self.exit_combo.currentIndex():
            self.exit_combo.setCurrentIndex((self.entry_combo.currentIndex() + 1) % self.exit_combo.count())

    def _refresh_interlocking_table(self) -> None:
        signals = sorted(self.canvas.topology.signals.keys())
        if len(signals) < 2:
            self.interlocking_rows = []
            self.valid_route_pairs = set()
            self.table_widget.setRowCount(0)
            return

        rows = self.application_service.generate_interlocking_rows(
            topology=self.canvas.topology,
            overlap_length=self.overlap_spin.value(),
        )
        rows.sort(key=lambda item: item.route_name)
        self.interlocking_rows = rows
        self.valid_route_pairs = {
            (row.entry_signal, row.exit_signal) for row in rows
        }

        self.table_widget.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            entry_signal = self.canvas.topology.signals.get(row.entry_signal)
            approach_section = (
                entry_signal.approach_section.strip()
                if entry_signal is not None and entry_signal.approach_section.strip()
                else "-"
            )
            values = [
                str(row_index + 1),
                self._format_route_label(row),
                row.entry_signal,
                self._format_point_locks(row.required_point_positions),
                self._format_opposing_signals(row),
                " -> ".join(row.locked_sections) if row.locked_sections else "-",
                approach_section,
                self._format_seconds(float(self.approach_time_spin.value())),
                self._format_destination_track(row),
                self._format_flank_points(row),
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
            route = self.application_service.find_route(
                topology=self.canvas.topology,
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                overlap_length=self.overlap_spin.value(),
                simulation=self.simulation,
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

    def _on_table_row_clicked(self, row_index: int, _column_index: int) -> None:
        if row_index < 0 or row_index >= len(self.interlocking_rows):
            return
        row = self.interlocking_rows[row_index]
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
                point_locks=row.required_point_positions,
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

        approach_lock_state: str | None = None
        approach_lock_remaining: float | None = None
        if self.simulation is not None:
            locking_engine = self.simulation.locking_engine
            state = locking_engine.approach_lock_state(route.id)
            if state is not None:
                approach_lock_state = state.value
                approach_lock_remaining = locking_engine.approach_locking.remaining_time_lock(route.id)

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
    def _format_route_label(row: InterlockingTableRow) -> str:
        return f"{row.entry_element} -> {row.exit_signal}"

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
            path=list(route.path),
            overlap=list(route.overlap_path),
            required_point_positions=dict(route.required_point_positions),
            flank_point_positions=dict(route.flank_point_positions),
            locked_sections=[],
            conflicting_routes=[],
        )
        return self._opposing_signals_for_row(row_like)

    def _conflicting_routes_for_pair(self, entry_signal_id: str, exit_signal_id: str) -> list[str]:
        for row in self.interlocking_rows:
            if row.entry_signal == entry_signal_id and row.exit_signal == exit_signal_id:
                return sorted(set(row.conflicting_routes))
        return []


    def _format_seconds(self, value_seconds: float) -> str:
        return f"{value_seconds:.1f}{self._t('unit.seconds_suffix')}"

    def _format_flank_points(self, row: InterlockingTableRow) -> str:
        return self.route_presenter.format_point_locks(row.flank_point_positions)

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
                simulation=self.simulation,
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

        self.simulation = start_result.simulation
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
        if self.simulation is None:
            return None
        return self.application_service.get_active_route_for_pair(
            self.simulation,
            entry_signal_id,
            exit_signal_id,
        )

    def _get_or_create_locked_route(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
    ) -> tuple[Route, bool]:
        result = self.controller.set_or_reuse_route(
            topology=self.canvas.topology,
            simulation=self.simulation,
            entry_signal_id=entry_signal_id,
            exit_signal_id=exit_signal_id,
            overlap_length=self.overlap_spin.value(),
            approach_time_lock_seconds=float(self.approach_time_spin.value()),
            overlap_release_seconds=float(self.overlap_release_spin.value()),
        )
        self.simulation = result.simulation
        self.canvas.set_simulation(self.simulation)
        return result.route, result.created

    def _simulation_tick(self) -> None:
        if self.simulation is None:
            self._simulation_timer.stop()
            self._sync_ui_state()
            return
        try:
            self.simulation.step()
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

    def _cancel_active_routes(self, show_message: bool = True) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_cancel_route:
            if show_message:
                self.status.showMessage(self._t("status.cancel_route_disabled"))
            return
        if self.simulation is None:
            if show_message:
                self.status.showMessage(self._t("status.no_active_simulation_routes"))
            return

        if not self.application_service.has_active_routes(self.simulation):
            if show_message:
                self.status.showMessage(self._t("status.no_active_routes"))
            return

        cancel_result = self.controller.cancel_active_routes(self.simulation)
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
        self.canvas.set_simulation(self.simulation)
        has_signals = self.entry_combo.count() > 1 and self.exit_combo.count() > 1
        if self.simulation is not None:
            self.application_service.update_time_locking(self.simulation)
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

        has_active_routes = (
            self.application_service.has_active_routes(self.simulation)
            if self.simulation is not None
            else False
        )
        capabilities = self.mode_policy.capabilities(self._operating_mode)
        simulation_running = self._simulation_timer.isActive()
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
        self.new_layout_action.setEnabled(capabilities.can_edit_layout)
        self.save_layout_action.setEnabled(capabilities.can_edit_layout)
        self.load_layout_action.setEnabled(capabilities.can_edit_layout)
        self.connect_mode_action.setEnabled(capabilities.can_edit_layout)

        self.find_route_button.setEnabled(has_signals and selected_pair_defined)
        self.set_route_button.setEnabled(
            capabilities.can_set_route
            and has_signals
            and selected_pair_defined
            and not simulation_running
        )
        self.set_route_action.setEnabled(
            capabilities.can_set_route
            and has_signals
            and selected_pair_defined
            and not simulation_running
        )
        self.cancel_route_button.setEnabled(capabilities.can_cancel_route and has_active_routes)
        self.cancel_route_action.setEnabled(capabilities.can_cancel_route and has_active_routes)
        self.approach_time_spin.setEnabled(capabilities.can_set_route)
        self.overlap_release_spin.setEnabled(capabilities.can_set_route)

        self.simulation_action.setText(
            self._t("toolbar.stop_simulation")
            if simulation_running
            else self._t("toolbar.start_simulation")
        )
        self.simulation_action.setEnabled(
            capabilities.can_start_simulation and (simulation_running or selected_pair_ready)
        )
        self.simulate_button.setText(
            self._t("button.stop_sim_short")
            if simulation_running
            else self._t("button.start_simulation")
        )
        self.simulate_button.setEnabled(
            capabilities.can_start_simulation and (simulation_running or selected_pair_ready)
        )
        self._update_runtime_connection_label()

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._smartio_client is not None:
            self._smartio_client.disconnect()
        super().closeEvent(event)

