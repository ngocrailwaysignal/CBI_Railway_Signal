"""Main application window for the geographical interlocking simulator."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
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
from core.domain.model.elements import PointPosition
from core.compiler.interlocking_table import InterlockingTableRow
from core.domain.model.route import Route
from core.runtime.simulation import Simulation
from generic_application import GenericApplicationProfile, GenericApplicationService
from specific_application import SpecificLayoutEditorService, StationLayout
from ui.controllers import MainWindowController
from ui.views.canvas_editor_view import CanvasEditor
from ui.views.components_palette_view import ComponentsPalette
from ui.presenters import RoutePresenter


OperatingMode = AppMode


class MainWindow(QMainWindow):
    """Top-level editor + simulator window."""

    def __init__(self, application_profile: GenericApplicationProfile | None = None) -> None:
        super().__init__()
        self.setWindowTitle("Geographical Interlocking Simulator")
        self.resize(1700, 900)

        self.application_profile = application_profile or GenericApplicationProfile()
        self.application_service = GenericApplicationService(profile=self.application_profile)
        self.controller = MainWindowController(self.application_service)
        self.route_presenter = RoutePresenter()
        self.mode_policy = self.application_service.mode_policy
        self.layout_editor_service = SpecificLayoutEditorService(self.application_service)
        self.current_layout = self.layout_editor_service.new_layout(station_id="UNNAMED")
        self._operating_mode = OperatingMode.DESIGN_LAYOUT

        self.palette = ComponentsPalette(self)
        self.canvas = CanvasEditor(self)
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
            self.status.showMessage(f"Loaded sample layout: {sample_path}")
        else:
            self.canvas.load_topology(self.current_layout.topology)
        self._set_operating_mode(OperatingMode.DESIGN_LAYOUT, announce=False)
        self._sync_ui_state()

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
        toolbar = QToolBar("Main", self)
        self.addToolBar(toolbar)

        new_action = toolbar.addAction("New Layout")
        new_action.triggered.connect(self._new_layout)

        save_action = toolbar.addAction("Save Layout")
        save_action.triggered.connect(self._save_layout)

        load_action = toolbar.addAction("Load Layout")
        load_action.triggered.connect(self._load_layout)

        self.connect_mode_action = toolbar.addAction("Connect Mode")
        self.connect_mode_action.setCheckable(True)
        self.connect_mode_action.toggled.connect(self._toggle_connect_mode)

        self.set_route_action = toolbar.addAction("Set Route")
        self.set_route_action.triggered.connect(self._set_selected_route)

        self.cancel_route_action = toolbar.addAction("Cancel Active Route")
        self.cancel_route_action.triggered.connect(lambda: self._cancel_active_routes())

        self.simulation_action = toolbar.addAction("Start Simulation")
        self.simulation_action.triggered.connect(self._start_simulation)

    def _new_layout(self) -> None:
        confirm = QMessageBox.question(
            self,
            "New layout",
            "Clear current layout and start a new one?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self._load_layout_into_canvas(self.layout_editor_service.new_layout(station_id="UNNAMED"))
        self.status.showMessage("Started a new empty layout")

    def _toggle_connect_mode(self, enabled: bool) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_edit_layout and enabled:
            self.connect_mode_action.blockSignals(True)
            self.connect_mode_action.setChecked(False)
            self.connect_mode_action.blockSignals(False)
            QMessageBox.information(
                self,
                "Connect mode",
                "Connect mode is available only in Design Layout workspace.",
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
            self.status.showMessage(f"Added {element_type}")
        except Exception as exc:
            QMessageBox.warning(self, "Cannot add component", str(exc))

    def _build_right_panel(self) -> QWidget:
        panel = QWidget(self)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(6, 6, 6, 6)

        mode_group = QGroupBox("Workspace")
        mode_layout = QVBoxLayout(mode_group)
        self.mode_tabs = QTabWidget(mode_group)
        self.mode_tabs.setDocumentMode(True)
        self.mode_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.mode_tabs.addTab(
            self._build_mode_tab_body(
                "Build topology and interlocking assets.",
                "Enable: add/move/connect/rename/delete elements and edit static attributes.",
            ),
            "Design Layout",
        )
        self.mode_tabs.addTab(
            self._build_mode_tab_body(
                "Train movement sandbox with manual state override.",
                "Enable: set/cancel route + start simulation + edit occupied/locked_by states.",
            ),
            "Simulation",
        )
        self.mode_tabs.addTab(
            self._build_mode_tab_body(
                "Operational mode with strict manual state safety.",
                "Enable: route operations only. Manual occupied/locked_by editing is blocked.",
            ),
            "Runtime",
        )
        self.mode_tabs.currentChanged.connect(self._on_mode_tab_changed)
        mode_layout.addWidget(self.mode_tabs)

        route_group = QGroupBox("Route Finder")
        route_layout = QVBoxLayout(route_group)
        route_layout.addWidget(QLabel("Select Entry and Exit signals, then run route search."))

        combo_row = QHBoxLayout()
        self.entry_combo = QComboBox(route_group)
        self.exit_combo = QComboBox(route_group)
        self.entry_combo.currentTextChanged.connect(lambda _text: self._sync_ui_state())
        self.exit_combo.currentTextChanged.connect(lambda _text: self._sync_ui_state())
        self.overlap_spin = QSpinBox(route_group)
        self.overlap_spin.setRange(0, 5)
        self.overlap_spin.setValue(int(self.application_profile.default_overlap_length))
        self.overlap_spin.valueChanged.connect(self._refresh_interlocking_table)
        combo_row.addWidget(QLabel("Entry"))
        combo_row.addWidget(self.entry_combo)
        combo_row.addWidget(QLabel("Exit"))
        combo_row.addWidget(self.exit_combo)
        combo_row.addWidget(QLabel("Overlap"))
        combo_row.addWidget(self.overlap_spin)
        route_layout.addLayout(combo_row)

        timing_row = QHBoxLayout()
        self.approach_time_spin = QDoubleSpinBox(route_group)
        self.approach_time_spin.setRange(0.0, 600.0)
        self.approach_time_spin.setDecimals(1)
        self.approach_time_spin.setSingleStep(1.0)
        self.approach_time_spin.setSuffix(" s")
        self.approach_time_spin.setValue(float(self.application_profile.time_lock_seconds))
        self.approach_time_spin.valueChanged.connect(self._on_timing_controls_changed)
        self.overlap_release_spin = QDoubleSpinBox(route_group)
        self.overlap_release_spin.setRange(0.0, 600.0)
        self.overlap_release_spin.setDecimals(1)
        self.overlap_release_spin.setSingleStep(1.0)
        self.overlap_release_spin.setSuffix(" s")
        self.overlap_release_spin.setValue(float(self.application_profile.overlap_release_seconds))
        self.overlap_release_spin.valueChanged.connect(self._on_timing_controls_changed)
        timing_row.addWidget(QLabel("Approach release"))
        timing_row.addWidget(self.approach_time_spin)
        timing_row.addWidget(QLabel("Overlap release"))
        timing_row.addWidget(self.overlap_release_spin)
        route_layout.addLayout(timing_row)

        button_row = QHBoxLayout()
        self.find_route_button = QPushButton("Find Route")
        self.find_route_button.clicked.connect(self._preview_selected_route)
        self.set_route_button = QPushButton("Set Route")
        self.set_route_button.clicked.connect(self._set_selected_route)
        self.cancel_route_button = QPushButton("Cancel Active")
        self.cancel_route_button.clicked.connect(lambda: self._cancel_active_routes())
        self.simulate_button = QPushButton("Start Sim")
        self.simulate_button.clicked.connect(self._start_simulation)
        button_row.addWidget(self.find_route_button)
        button_row.addWidget(self.set_route_button)
        button_row.addWidget(self.cancel_route_button)
        button_row.addWidget(self.simulate_button)
        route_layout.addLayout(button_row)

        self.search_log = QPlainTextEdit(route_group)
        self.search_log.setReadOnly(True)
        self.search_log.setPlaceholderText("Route search steps will appear here.")
        route_layout.addWidget(self.search_log)

        table_group = QGroupBox("Interlocking Table")
        table_layout = QVBoxLayout(table_group)
        self.table_widget = QTableWidget(0, 7, table_group)
        self.table_widget.setHorizontalHeaderLabels(
            ["Route", "Entry", "Exit", "Point locks", "Track locks", "Overlap", "Conflicts"]
        )
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table_widget.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table_widget.verticalHeader().setVisible(False)
        header = self.table_widget.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.table_widget.cellClicked.connect(self._on_table_row_clicked)
        table_layout.addWidget(self.table_widget)

        panel_layout.addWidget(mode_group)
        panel_layout.addWidget(route_group)
        panel_layout.addWidget(table_group, stretch=1)
        return panel

    @staticmethod
    def _build_mode_tab_body(summary: str, policy: str) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        summary_label = QLabel(summary, container)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet("font-weight: 600; color: #12384d;")
        policy_label = QLabel(policy, container)
        policy_label.setWordWrap(True)
        policy_label.setStyleSheet("color: #32576e;")
        layout.addWidget(summary_label)
        layout.addWidget(policy_label)
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

    def _set_operating_mode(self, mode: OperatingMode, *, announce: bool = True) -> None:
        previous_mode = self._operating_mode
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
            self.status.showMessage("Simulation stopped after leaving Simulation workspace.")

        if self.connect_mode_action.isChecked() and not design_mode:
            self.connect_mode_action.blockSignals(True)
            self.connect_mode_action.setChecked(False)
            self.connect_mode_action.blockSignals(False)
            self.canvas.set_connect_mode(False)

        self.canvas.set_layout_edit_lock(
            self.mode_policy.layout_edit_locked(mode),
            "Switch to Design Layout workspace to modify topology and static properties.",
        )
        self.palette.component_list.setEnabled(design_mode)
        if design_mode:
            self.palette.component_list.setToolTip("")
        else:
            self.palette.component_list.setToolTip(
                "Component insertion is available only in Design Layout workspace."
            )

        self._sync_ui_state()
        if announce and previous_mode is not mode:
            self.status.showMessage(f"Workspace mode: {mode.title}")

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

            self.status.showMessage(f"Updated {current_id}")
        except Exception as exc:
            QMessageBox.warning(self, "Property update failed", str(exc))

    def _manual_override_from_canvas(
        self,
        section_id: str,
        _occupied_before: bool,
        occupied_after: bool,
    ) -> list[str]:
        if self.simulation is None:
            return []
        result = self.application_service.manual_set_section_occupied(
            simulation=self.simulation,
            section_id=section_id,
            occupied=occupied_after,
        )
        return list(result.removed_trains)

    def _save_layout(self) -> None:
        default_target = "data/layout.json"
        if self.current_layout.source_path is not None:
            default_target = str(self.current_layout.source_path)
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Layout", default_target, "JSON Files (*.json)"
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
            self.status.showMessage(f"Saved layout to {saved_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _load_layout(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Layout", "data", "JSON Files (*.json)")
        if not path:
            return
        keep_occupancy = (
            QMessageBox.question(
                self,
                "Load occupancy state",
                "Restore OCCUPIED/FREE states from file?\n"
                "Route locks and signal route states are always reset on load.",
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
            self.status.showMessage(f"Loaded layout from {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def _load_layout_into_canvas(self, layout: StationLayout) -> None:
        self.current_layout = layout
        self.canvas.load_topology(layout.topology)

    def _on_timing_controls_changed(self, _value: float) -> None:
        if self.simulation is None:
            return
        self.application_service.configure_simulation_timing(
            self.simulation,
            approach_time_lock_seconds=float(self.approach_time_spin.value()),
            overlap_release_seconds=float(self.overlap_release_spin.value()),
        )
        self._sync_ui_state()

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
            values = [
                row.route_name,
                f"{row.entry_signal} ({row.entry_element})",
                f"{row.exit_signal} ({row.exit_element})",
                self._format_point_locks(row.required_point_positions),
                " -> ".join(row.locked_sections) if row.locked_sections else "-",
                " -> ".join(row.overlap) if row.overlap else "-",
                ", ".join(sorted(set(row.conflicting_routes))) if row.conflicting_routes else "-",
            ]
            for col_index, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
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
            QMessageBox.warning(self, "Find Route", "Please select both Entry and Exit signals.")
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(self, "Find Route", "Entry and Exit must be different signals.")
            return
        if (entry_signal_id, exit_signal_id) not in self.valid_route_pairs:
            QMessageBox.warning(
                self,
                "Find Route",
                f"No valid route is defined for {entry_signal_id} -> {exit_signal_id} in the current interlocking table.",
            )
            self._clear_preview_state(clear_visualization=True, sync_ui=True)
            return
        if not self._validate_signal_pair_request(entry_signal_id, exit_signal_id, "Find Route"):
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
            QMessageBox.warning(self, "Route unavailable", str(exc))
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
        self.status.showMessage(f"Preview route: {entry_signal_id} -> {exit_signal_id}")

    def _set_selected_route(self) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_set_route:
            QMessageBox.information(
                self,
                "Set Route",
                "Switch to Simulation or Runtime workspace to set routes.",
            )
            return
        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(self, "Set Route", "Please select both Entry and Exit signals.")
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(self, "Set Route", "Entry and Exit must be different signals.")
            return
        if (entry_signal_id, exit_signal_id) not in self.valid_route_pairs:
            QMessageBox.warning(
                self,
                "Set Route",
                f"No valid route is defined for {entry_signal_id} -> {exit_signal_id} in the current interlocking table.",
            )
            self._clear_preview_state(clear_visualization=True, sync_ui=True)
            return
        if not self._validate_signal_pair_request(entry_signal_id, exit_signal_id, "Set Route"):
            return

        try:
            route, created = self._get_or_create_locked_route(entry_signal_id, exit_signal_id)
        except Exception as exc:
            QMessageBox.warning(self, "Set Route failed", str(exc))
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
        if created:
            self.status.showMessage(f"Route set: {entry_signal_id} -> {exit_signal_id}")
        else:
            self.status.showMessage(f"Route already active: {entry_signal_id} -> {exit_signal_id}")

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

        point_locks = self.route_presenter.format_point_locks(row.required_point_positions)
        self.search_log.setPlainText(
            "\n".join(
                [
                    f"Route: {row.route_name}",
                    f"Entry: {row.entry_signal} protects {row.entry_element}",
                    f"Exit: {row.exit_signal} protects {row.exit_element}",
                    f"Search order: {' -> '.join(search_order)}",
                    f"Locked path: {' -> '.join(row.path)}",
                    f"Overlap: {' -> '.join(row.overlap) if row.overlap else '-'}",
                    f"Point locks: {point_locks}",
                ]
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
        self.search_log.setPlainText(self.route_presenter.build_route_search_log(route, search_order))

    @staticmethod
    def _format_point_locks(required_points: dict[str, PointPosition]) -> str:
        return RoutePresenter.format_point_locks(required_points)

    def _validate_signal_pair_request(
        self,
        entry_signal_id: str,
        exit_signal_id: str,
        title: str,
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
            title,
            "Invalid signal/topology configuration:\n" + issue_lines,
        )
        return False

    def _start_simulation(self) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_start_simulation:
            QMessageBox.information(
                self,
                "Simulation",
                "Switch to Simulation workspace to start or stop train simulation.",
            )
            return
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
            self._sync_ui_state()
            self.status.showMessage("Simulation stopped")
            return

        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(self, "Simulation", "Please choose both Entry and Exit signals.")
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(self, "Simulation", "Entry and Exit must be different signals.")
            return
        if len(self.canvas.topology.signals) < 2:
            QMessageBox.warning(self, "Simulation", "At least two signals are required.")
            return
        if not self._validate_signal_pair_request(entry_signal_id, exit_signal_id, "Simulation"):
            return

        route = self._get_active_route_for_pair(entry_signal_id, exit_signal_id)
        if route is None:
            QMessageBox.warning(
                self,
                "Simulation",
                "Please Set Route first for the selected Entry/Exit before starting simulation.",
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
            QMessageBox.critical(self, "Simulation failed", str(exc))
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
            f"Simulation running: {entry_signal_id} -> {exit_signal_id}, route={route.id}, train={train.id}, start={simulation_start_section}"
        )
        self._simulation_timer.start(700)
        self._sync_ui_state()

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
        except Exception as exc:
            self._simulation_timer.stop()
            self.canvas.refresh_visual_state()
            QMessageBox.critical(self, "Fail-safe STOP", str(exc))
            self._sync_ui_state()
            self.status.showMessage("Simulation halted by fail-safe")
            return

        self._simulation_ticks_remaining -= 1
        if self._simulation_ticks_remaining <= 0:
            self._simulation_timer.stop()
            self._sync_ui_state()
            self.status.showMessage("Simulation complete")

    def _cancel_active_routes(self, show_message: bool = True) -> None:
        if not self.mode_policy.capabilities(self._operating_mode).can_cancel_route:
            if show_message:
                self.status.showMessage("Cancel route is disabled in Design Layout workspace")
            return
        if self.simulation is None:
            if show_message:
                self.status.showMessage("No active simulation routes to cancel")
            return

        if not self.application_service.has_active_routes(self.simulation):
            if show_message:
                self.status.showMessage("No active routes to cancel")
            return

        cancel_result = self.controller.cancel_active_routes(self.simulation)
        self.canvas.clear_route_visualization()
        self.canvas.refresh_visual_state()
        self._sync_ui_state()

        if cancel_result.failures:
            QMessageBox.warning(
                self,
                "Cancel route",
                "Some routes remain locked:\n" + "\n".join(cancel_result.failures),
            )
        elif show_message:
            self.status.showMessage("Cancelled all active routes")

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
        runtime_edit_lock_reason = "Manual occupied/locked_by editing is blocked in Runtime workspace."
        self.canvas.set_runtime_edit_lock(
            self.mode_policy.runtime_edit_locked(self._operating_mode),
            runtime_edit_lock_reason,
        )
        self.mode_status_label.setText(f"Mode: {self._operating_mode.title}")
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

        self.simulation_action.setText("Stop Simulation" if simulation_running else "Start Simulation")
        self.simulation_action.setEnabled(
            capabilities.can_start_simulation and (simulation_running or selected_pair_ready)
        )
        self.simulate_button.setText("Stop Sim" if simulation_running else "Start Sim")
        self.simulate_button.setEnabled(
            capabilities.can_start_simulation and (simulation_running or selected_pair_ready)
        )

