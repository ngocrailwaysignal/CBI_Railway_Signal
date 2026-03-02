"""Main application window for the geographical interlocking simulator."""

from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (
    QComboBox,
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
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from core.elements import PointPosition
from core.interlocking_table import InterlockingTableGenerator, InterlockingTableRow
from core.route_engine import Route, RouteEngine
from core.simulation import Simulation
from core.train import Train
from ui.canvas_editor import CanvasEditor
from ui.components_palette import ComponentsPalette


class MainWindow(QMainWindow):
    """Top-level editor + simulator window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Geographical Interlocking Simulator")
        self.resize(1700, 900)

        self.palette = ComponentsPalette(self)
        self.canvas = CanvasEditor(self)
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
        self.canvas.editor_message.connect(self.status.showMessage)
        self._build_toolbar()

        self.simulation: Optional[Simulation] = None
        self.preview_route: Optional[Route] = None
        self.interlocking_rows: list[InterlockingTableRow] = []
        self._simulation_timer = QTimer(self)
        self._simulation_timer.timeout.connect(self._simulation_tick)
        self._simulation_ticks_remaining = 0

        sample_path = Path("data/sample_layout.json")
        if sample_path.exists():
            self.canvas.load_from_json(sample_path)
            self.status.showMessage(f"Loaded sample layout: {sample_path}")
        self._on_topology_changed()

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

        set_route_action = toolbar.addAction("Set Route")
        set_route_action.triggered.connect(self._set_selected_route)

        clear_route_action = toolbar.addAction("Clear Route")
        clear_route_action.triggered.connect(self._clear_route)

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
        self.canvas.clear_layout()
        self.status.showMessage("Started a new empty layout")

    def _rename_selected(self) -> None:
        try:
            self.canvas.rename_selected_node_dialog()
        except Exception as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))

    def _delete_selected(self) -> None:
        self.canvas.delete_selected_items()
        self.status.showMessage("Deleted selected item(s)")

    def _connect_selected(self) -> None:
        try:
            self.canvas.connect_selected_nodes()
            self.status.showMessage("Connected selected modules")
        except Exception as exc:
            QMessageBox.warning(self, "Connect failed", str(exc))

    def _toggle_connect_mode(self, enabled: bool) -> None:
        self.canvas.set_connect_mode(enabled)

    def _clear_route(self) -> None:
        self.preview_route = None
        self.canvas.clear_route_visualization()
        self.search_log.clear()
        self.status.showMessage("Cleared route visualization")

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

        route_group = QGroupBox("Route Finder")
        route_layout = QVBoxLayout(route_group)
        route_layout.addWidget(QLabel("Select Entry and Exit signals, then run route search (always 2-way)."))

        combo_row = QHBoxLayout()
        self.entry_combo = QComboBox(route_group)
        self.exit_combo = QComboBox(route_group)
        self.overlap_spin = QSpinBox(route_group)
        self.overlap_spin.setRange(0, 5)
        self.overlap_spin.setValue(0)
        self.overlap_spin.valueChanged.connect(self._refresh_interlocking_table)
        combo_row.addWidget(QLabel("Entry"))
        combo_row.addWidget(self.entry_combo)
        combo_row.addWidget(QLabel("Exit"))
        combo_row.addWidget(self.exit_combo)
        combo_row.addWidget(QLabel("Overlap"))
        combo_row.addWidget(self.overlap_spin)
        route_layout.addLayout(combo_row)

        button_row = QHBoxLayout()
        self.find_route_button = QPushButton("Find Route")
        self.find_route_button.clicked.connect(self._preview_selected_route)
        self.set_route_button = QPushButton("Set Route")
        self.set_route_button.clicked.connect(self._set_selected_route)
        self.clear_visual_button = QPushButton("Clear View")
        self.clear_visual_button.clicked.connect(self.canvas.clear_route_visualization)
        self.refresh_table_button = QPushButton("Refresh Table")
        self.refresh_table_button.clicked.connect(self._refresh_interlocking_table)
        button_row.addWidget(self.find_route_button)
        button_row.addWidget(self.set_route_button)
        button_row.addWidget(self.clear_visual_button)
        button_row.addWidget(self.refresh_table_button)
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

        panel_layout.addWidget(route_group)
        panel_layout.addWidget(table_group, stretch=1)
        return panel

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

    def _save_layout(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Layout", "data/layout.json", "JSON Files (*.json)"
        )
        if not path:
            return
        try:
            self.canvas.save_to_json(path)
            self.status.showMessage(f"Saved layout to {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _load_layout(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load Layout", "data", "JSON Files (*.json)")
        if not path:
            return
        try:
            self.canvas.load_from_json(path)
            self.status.showMessage(f"Loaded layout from {path}")
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))

    def _load_sample(self) -> None:
        sample_path = Path("data/sample_layout.json")
        if not sample_path.exists():
            QMessageBox.warning(self, "Missing sample", f"Sample file not found: {sample_path}")
            return
        self.canvas.load_from_json(sample_path)
        self.status.showMessage(f"Loaded sample layout: {sample_path}")

    def _load_rsp30(self) -> None:
        rsp_path = Path("data/rsp30_layout.json")
        if not rsp_path.exists():
            QMessageBox.warning(self, "Missing layout", f"Layout file not found: {rsp_path}")
            return
        self.canvas.load_from_json(rsp_path)
        self.status.showMessage(f"Loaded RSP30 layout: {rsp_path}")

    def _on_topology_changed(self) -> None:
        self.simulation = None
        self.preview_route = None
        self.canvas.clear_route_visualization()
        self._refresh_signal_selectors()
        self._refresh_interlocking_table()
        self.canvas.refresh_visual_state()

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
            self.table_widget.setRowCount(0)
            return

        generator = InterlockingTableGenerator(
            topology=self.canvas.topology,
            overlap_length=self.overlap_spin.value(),
        )
        rows = generator.generate(
            entry_signal_ids=signals,
            exit_signal_ids=signals,
        )
        rows.sort(key=lambda item: item.route_name)
        self.interlocking_rows = rows

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

    def _preview_selected_route(self) -> None:
        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(self, "Find Route", "Please select both Entry and Exit signals.")
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(self, "Find Route", "Entry and Exit must be different signals.")
            return

        route_engine = RouteEngine(self.canvas.topology)
        try:
            route = route_engine.find_route(
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                active_routes={},
                overlap_length=self.overlap_spin.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Route unavailable", str(exc))
            self.canvas.clear_route_visualization()
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
        self.status.showMessage(f"Preview route: {entry_signal_id} -> {exit_signal_id}")

    def _set_selected_route(self) -> None:
        entry_signal_id = self.entry_combo.currentText().strip()
        exit_signal_id = self.exit_combo.currentText().strip()
        if not entry_signal_id or not exit_signal_id:
            QMessageBox.warning(self, "Set Route", "Please select both Entry and Exit signals.")
            return
        if entry_signal_id == exit_signal_id:
            QMessageBox.warning(self, "Set Route", "Entry and Exit must be different signals.")
            return

        if self.simulation is None:
            self.simulation = Simulation(self.canvas.topology)

        try:
            route = self.simulation.set_route(
                entry_signal_id=entry_signal_id,
                exit_signal_id=exit_signal_id,
                overlap_length=self.overlap_spin.value(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "Set Route failed", str(exc))
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
        self.status.showMessage(f"Route set: {entry_signal_id} -> {exit_signal_id}")

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

        point_locks = self._format_point_locks(row.required_point_positions)
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
        graph = self.canvas.topology.graph
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
        point_locks = self._format_point_locks(route.required_point_positions)
        self.search_log.setPlainText(
            "\n".join(
                [
                    f"Route id: {route.id}",
                    f"Entry signal: {route.entry_signal_id}",
                    f"Exit signal: {route.exit_signal_id}",
                    f"Search order: {' -> '.join(search_order)}",
                    f"Route path: {' -> '.join(route.path)}",
                    f"Overlap: {' -> '.join(route.overlap_path) if route.overlap_path else '-'}",
                    f"Required points: {point_locks}",
                ]
            )
        )

    @staticmethod
    def _format_point_locks(required_points: dict[str, PointPosition]) -> str:
        if not required_points:
            return "-"
        return ", ".join(f"{point_id}:{position.value}" for point_id, position in sorted(required_points.items()))

    def _start_simulation(self) -> None:
        if self._simulation_timer.isActive():
            self._simulation_timer.stop()
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

        self.simulation = Simulation(self.canvas.topology)
        try:
            route = self.simulation.set_route(
                entry_signal_id,
                exit_signal_id,
                overlap_length=self.overlap_spin.value(),
            )
            train = Train(id="T1", current_section=route.path[0], speed=1.0)
            self.simulation.add_train(train, route)
        except Exception as exc:
            QMessageBox.critical(self, "Simulation failed", str(exc))
            self.canvas.refresh_visual_state()
            return

        search_order, _ = self._build_search_trace(route.path[0], route.path[-1])
        self.canvas.animate_route_search(
            search_sequence=search_order,
            route_path=route.path,
            overlap_path=route.overlap_path,
            interval_ms=160,
        )
        self._write_search_log(route, search_order)
        self._simulation_ticks_remaining = max(3, len(route.full_path) + 2)
        self.canvas.refresh_visual_state()
        self.status.showMessage(
            f"Simulation running: {entry_signal_id} -> {exit_signal_id}, route={route.id}"
        )
        self._simulation_timer.start(700)

    def _simulation_tick(self) -> None:
        if self.simulation is None:
            self._simulation_timer.stop()
            return
        try:
            self.simulation.step()
            self.canvas.refresh_visual_state()
        except Exception as exc:
            self._simulation_timer.stop()
            self.canvas.refresh_visual_state()
            QMessageBox.critical(self, "Fail-safe STOP", str(exc))
            self.status.showMessage("Simulation halted by fail-safe")
            return

        self._simulation_ticks_remaining -= 1
        if self._simulation_ticks_remaining <= 0:
            self._simulation_timer.stop()
            self.status.showMessage("Simulation complete")
