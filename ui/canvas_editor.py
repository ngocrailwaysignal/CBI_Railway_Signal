"""Interactive drag-and-drop canvas for topology editing."""

from __future__ import annotations

from copy import deepcopy
from math import hypot
from dataclasses import asdict
from typing import Any, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QBrush,
    QKeySequence,
    QPainter,
    QPen,
)
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QInputDialog,
    QLineEdit,
    QMenu,
    QMessageBox,
)

from core.elements import (
    ApproachSection,
    Point,
    PointPosition,
    PointSymbolOrientation,
    Signal,
    SignalAspect,
    SignalDirection,
    TrackSection,
)
from core.topology import RailwayTopology
from ui.components_palette import PaletteListWidget

POINT_SYMBOL_CHOICES: tuple[tuple[str, PointSymbolOrientation], ...] = (
    ("1", PointSymbolOrientation.RIGHT),
    ("2", PointSymbolOrientation.DOWN),
    ("3", PointSymbolOrientation.LEFT),
    ("4", PointSymbolOrientation.UP),
)


class NodeItem(QGraphicsObject):
    """Visual node for a track section, point, or signal."""

    WIDTH = 96.0
    HEIGHT = 56.0
    SIGNAL_WIDTH = 110.0
    SIGNAL_HEIGHT = 90.0

    def __init__(self, element_id: str, element_type: str, payload: dict[str, Any]) -> None:
        super().__init__()
        self.element_id = element_id
        self.element_type = element_type
        self.payload = payload
        self.editor: Optional["CanvasEditor"] = None
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def boundingRect(self) -> QRectF:
        width, height = self._dimensions_for_type(self.element_type)
        return QRectF(0.0, 0.0, width, height)

    def paint(self, painter: QPainter, _option: Any, _widget: Any = None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5)
        if self.element_type != "Point":
            border_pen = QPen(QColor("#111111"), 2.0 if self.isSelected() else 1.2)
            painter.setPen(border_pen)
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawRect(rect)

        if self.element_type in {"TrackSection", "ApproachSection"}:
            self._paint_section(painter, rect)
        elif self.element_type == "Point":
            self._paint_point(painter, rect)
        else:
            self._paint_signal(painter, rect)

        self._paint_state_marker(painter, rect)
        self._paint_route_highlight(painter)

    def _paint_section(self, painter: QPainter, rect: QRectF) -> None:
        if self.element_type == "ApproachSection":
            painter.setPen(QPen(QColor("#9c6b00"), 1.2, Qt.PenStyle.DashLine))
            painter.drawRect(rect.adjusted(2.5, 2.5, -2.5, -2.5))

        painter.setPen(QPen(QColor("#111111"), 1.1))
        split_y = rect.top() + rect.height() * 0.46
        top_line_y = rect.top() + rect.height() * 0.20
        left_x = rect.left() + 8.0
        right_x = rect.right() - 8.0
        painter.drawLine(QPointF(left_x, top_line_y), QPointF(right_x, top_line_y))
        tick_height = rect.height() * 0.14
        tick_offset = rect.width() * 0.12
        for x in (rect.left() + tick_offset, rect.right() - tick_offset):
            painter.drawLine(
                QPointF(x, top_line_y),
                QPointF(x, top_line_y + tick_height),
            )
        painter.drawLine(
            QPointF(rect.left() + 2.0, split_y),
            QPointF(rect.right() - 2.0, split_y),
        )
        label_rect = QRectF(
            rect.left() + 4.0,
            split_y + 2.0,
            rect.width() - 8.0,
            rect.bottom() - split_y - 4.0,
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.element_id)

    def _paint_point(self, painter: QPainter, rect: QRectF) -> None:
        panel_side = max(26.0, min(rect.width(), rect.height()) - 8.0)
        panel = QRectF(
            rect.center().x() - panel_side / 2.0,
            rect.center().y() - panel_side / 2.0,
            panel_side,
            panel_side,
        )
        painter.setPen(QPen(QColor("#111111"), 2.0 if self.isSelected() else 1.3))
        painter.setBrush(QBrush(QColor("#f3f3f3")))
        painter.drawRect(panel)

        position = str(self.payload.get("position", PointPosition.NORMAL.value))
        symbol_orientation = str(
            self.payload.get("symbol_orientation", PointSymbolOrientation.RIGHT.value)
        )
        branch_offset = max(6.0, panel.height() * 0.30)
        rail_half = panel.width() / 2.0 - 2.0

        # 4 UI orientations are rendered as horizontal point symbols:
        # RIGHT  -> toe left, branch to upper-right (NORMAL) / lower-right (REVERSE)
        # DOWN   -> toe left, branch to lower-right (NORMAL) / upper-right (REVERSE)
        # LEFT   -> toe right, branch to lower-left (NORMAL) / upper-left (REVERSE)
        # UP     -> toe right, branch to upper-left (NORMAL) / lower-left (REVERSE)
        if symbol_orientation == PointSymbolOrientation.LEFT.value:
            toe_x, toe_y = rail_half, 0.0
            straight_x, straight_y = -rail_half, 0.0
            branch_x = -rail_half
            branch_y = branch_offset if position == PointPosition.NORMAL.value else -branch_offset
        elif symbol_orientation == PointSymbolOrientation.UP.value:
            toe_x, toe_y = rail_half, 0.0
            straight_x, straight_y = -rail_half, 0.0
            branch_x = -rail_half
            branch_y = -branch_offset if position == PointPosition.NORMAL.value else branch_offset
        elif symbol_orientation == PointSymbolOrientation.DOWN.value:
            toe_x, toe_y = -rail_half, 0.0
            straight_x, straight_y = rail_half, 0.0
            branch_x = rail_half
            branch_y = branch_offset if position == PointPosition.NORMAL.value else -branch_offset
        else:
            toe_x, toe_y = -rail_half, 0.0
            straight_x, straight_y = rail_half, 0.0
            branch_x = rail_half
            branch_y = -branch_offset if position == PointPosition.NORMAL.value else branch_offset

        def _to_scene(x: float, y: float) -> QPointF:
            return QPointF(panel.center().x() + x, panel.center().y() + y)

        toe = _to_scene(toe_x, toe_y)
        straight = _to_scene(straight_x, straight_y)
        branch = _to_scene(branch_x, branch_y)
        painter.drawLine(toe, straight)
        painter.drawLine(toe, branch)

        label = self.element_id
        text_left = panel.left() + 1.0 if branch_x > 0 else panel.center().x() + 1.0
        text_top = panel.center().y() + 1.0 if branch_y < 0 else panel.top() + 1.0
        text_rect = QRectF(
            text_left,
            text_top,
            panel.width() / 2.0 - 3.0,
            panel.height() / 2.0 - 3.0,
        )
        painter.setPen(QPen(QColor("#111111"), 1.1))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label)

    def _paint_signal(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#111111"), 1.2))
        outer = rect.adjusted(0.8, 0.8, -0.8, -0.8)
        painter.drawRect(outer)

        split_y = outer.bottom() - max(24.0, outer.height() * 0.28)
        painter.drawLine(QPointF(outer.left() + 1.5, split_y), QPointF(outer.right() - 1.5, split_y))

        top_rect = QRectF(
            outer.left() + 5.0,
            outer.top() + 4.0,
            outer.width() - 10.0,
            split_y - outer.top() - 8.0,
        )
        mast_x = top_rect.center().x()
        mast_top = top_rect.top() + 6.0
        mast_bottom = top_rect.bottom() - 4.0
        painter.drawLine(QPointF(mast_x, mast_top), QPointF(mast_x, mast_bottom))

        direction = str(self.payload.get("direction", SignalDirection.RIGHT.value))
        # Render LEFT/RIGHT directly by direction value.
        face_left = direction == SignalDirection.LEFT.value
        aspect = self.payload.get("aspect", SignalAspect.STOP.value)
        lamp_color = QColor("#1f8f48") if aspect == SignalAspect.PROCEED.value else QColor("#c62828")

        arm_y = top_rect.top() + top_rect.height() * 0.35
        arm_length = max(16.0, top_rect.width() * 0.32)
        head_radius = 6.0
        if face_left:
            head_center_x = mast_x - arm_length
            stop_bar_x = head_center_x - 8.0
        else:
            head_center_x = mast_x + arm_length
            stop_bar_x = head_center_x + 8.0

        painter.drawLine(QPointF(mast_x, arm_y), QPointF(head_center_x, arm_y))
        painter.setBrush(QBrush(lamp_color))
        painter.drawEllipse(
            QRectF(
                head_center_x - head_radius,
                arm_y - head_radius,
                head_radius * 2.0,
                head_radius * 2.0,
            )
        )
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(QPointF(stop_bar_x, arm_y - 6.0), QPointF(stop_bar_x, arm_y + 6.0))

        label_rect = QRectF(outer.left() + 3.0, split_y + 2.0, outer.width() - 6.0, outer.bottom() - split_y - 3.0)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.element_id)
        painter.restore()

    @classmethod
    def _dimensions_for_type(cls, element_type: str) -> tuple[float, float]:
        if element_type.startswith("Signal"):
            return cls.WIDTH, cls.HEIGHT
        return cls.WIDTH, cls.HEIGHT

    def _paint_state_marker(self, painter: QPainter, rect: QRectF) -> None:
        color: QColor | None = None
        if self.payload.get("occupied"):
            color = QColor("#c62828")
        elif self.payload.get("locked_by"):
            color = QColor("#15c020")
        if color is None:
            return
        marker_rect = QRectF(rect.right() - 10.0, rect.top() + 4.0, 6.0, 6.0)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawEllipse(marker_rect)
        painter.restore()

    def _paint_route_highlight(self, painter: QPainter) -> None:
        if self.editor is None:
            return
        if self.editor._connect_source is self:
            pen = QPen(QColor("#7c3aed"), 3.0)
        elif self.element_id in self.editor._route_highlight_nodes:
            pen = QPen(QColor("#cf1322"), 3.0)
        elif self.element_id in self.editor._overlap_highlight_nodes:
            pen = QPen(QColor("#0b7285"), 2.6, Qt.PenStyle.DashLine)
        ##elif self.element_id in self.editor._search_highlight_nodes:
            ##pen = QPen(QColor("#d97706"), 2.2, Qt.PenStyle.DashLine)
        else:
            return

        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.boundingRect().adjusted(2.0, 2.0, -2.0, -2.0))
        painter.restore()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionChange
            and self.editor is not None
            and isinstance(value, QPointF)
        ):
            return self.editor.snap_to_grid(value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and self.editor is not None:
            self.editor.handle_node_moved(self)
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.editor is not None:
            self.editor.edit_node_properties_dialog(self)
        super().mouseDoubleClickEvent(event)


class EdgeItem(QGraphicsLineItem):
    """Connection line between two nodes."""

    def __init__(self, source: NodeItem, target: NodeItem) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.setPen(QPen(QColor("#222222"), 1.6))
        self.setZValue(-1.0)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.update_geometry()

    def update_geometry(self) -> None:
        source_center = self.source.sceneBoundingRect().center()
        target_center = self.target.sceneBoundingRect().center()
        start = self._edge_anchor(self.source, target_center)
        end = self._edge_anchor(self.target, source_center)
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        distance = hypot(dx, dy)
        if distance > 18.0:
            inset = min(10.0, distance * 0.35)
            end = QPointF(end.x() - (dx / distance) * inset, end.y() - (dy / distance) * inset)
        self.setLine(start.x(), start.y(), end.x(), end.y())

    @staticmethod
    def _edge_anchor(node: NodeItem, toward: QPointF) -> QPointF:
        rect = node.sceneBoundingRect()
        center = rect.center()
        dx = toward.x() - center.x()
        dy = toward.y() - center.y()
        if abs(dx) >= abs(dy):
            return QPointF(rect.right() if dx >= 0 else rect.left(), center.y())
        return QPointF(center.x(), rect.bottom() if dy >= 0 else rect.top())

    def paint(self, painter: QPainter, option: Any, widget: Any = None) -> None:
        line = self.line()
        if line.length() <= 0.0:
            return

        color = QColor("#0b7285") if self.isSelected() else QColor("#222222")
        width = 2.3 if self.isSelected() else 1.6

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, width))
        painter.drawLine(line)
        painter.restore()


class CanvasEditor(QGraphicsView):
    """Grid canvas supporting block drag-drop and edge connection."""

    GRID_STEP = 25.0
    editor_message = pyqtSignal(str)
    node_selected = pyqtSignal(object)
    topology_changed = pyqtSignal()

    def __init__(self, parent: Optional[Any] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.scene_ref = QGraphicsScene(self)
        self.setScene(self.scene_ref)
        self.scene_ref.setSceneRect(-1000.0, -1000.0, 2200.0, 2200.0)
        self.scene_ref.selectionChanged.connect(self._on_selection_changed)

        self.topology = RailwayTopology()
        self.nodes: dict[str, NodeItem] = {}
        self.edges: list[EdgeItem] = []
        self.signal_links: set[tuple[str, str]] = self.topology.signal_links
        self._counter = {"TrackSection": 0, "ApproachSection": 0, "Point": 0, "Signal": 0}

        self._connection_start: Optional[NodeItem] = None
        self._connect_mode = False
        self._connect_source: Optional[NodeItem] = None
        self._temporary_edge: Optional[QGraphicsLineItem] = None
        self._search_highlight_nodes: set[str] = set()
        self._route_highlight_nodes: set[str] = set()
        self._overlap_highlight_nodes: set[str] = set()
        self._search_sequence: list[str] = []
        self._search_index = 0
        self._search_timer = QTimer(self)
        self._search_timer.timeout.connect(self._advance_search_animation)
        self._undo_stack: list[RailwayTopology] = []
        self._redo_stack: list[RailwayTopology] = []
        self._max_undo_depth = 50

    def dragEnterEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat(PaletteListWidget.COMPONENT_MIME):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: Any) -> None:
        if event.mimeData().hasFormat(PaletteListWidget.COMPONENT_MIME):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: Any) -> None:
        if not event.mimeData().hasFormat(PaletteListWidget.COMPONENT_MIME):
            event.ignore()
            return
        payload = event.mimeData().data(PaletteListWidget.COMPONENT_MIME)
        element_type = bytes(payload).decode("utf-8")
        scene_pos = self.snap_to_grid(self.mapToScene(event.position().toPoint()))
        try:
            self.add_component(element_type, scene_pos)
        except Exception as exc:
            QMessageBox.warning(self, "Cannot add component", str(exc))
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.acceptProposedAction()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:
        super().drawBackground(painter, rect)
        painter.setPen(QPen(QColor("#e5e9ef"), 1.0))
        step = int(self.GRID_STEP)
        x_start = int(rect.left()) - (int(rect.left()) % step)
        y_start = int(rect.top()) - (int(rect.top()) % step)
        for x in range(x_start, int(rect.right()) + step, step):
            painter.drawLine(x, int(rect.top()), x, int(rect.bottom()))
        for y in range(y_start, int(rect.bottom()) + step, step):
            painter.drawLine(int(rect.left()), y, int(rect.right()), y)

    def snap_to_grid(self, scene_pos: QPointF) -> QPointF:
        step = self.GRID_STEP
        return QPointF(
            round(scene_pos.x() / step) * step,
            round(scene_pos.y() / step) * step,
        )

    def mousePressEvent(self, event: Any) -> None:
        if (
            self._connect_mode
            and event.button() == Qt.MouseButton.LeftButton
            and not (
                event.modifiers()
                & (
                    Qt.KeyboardModifier.ShiftModifier
                    | Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.AltModifier
                )
            )
        ):
            node = self._node_at_view_pos(event.position().toPoint())
            if node is None:
                super().mousePressEvent(event)
                return

            if self._connect_source is None:
                self._connect_source = node
                self.editor_message.emit(
                    f"Connect mode: start {node.element_id}. Click target node to create connection."
                )
                self.refresh_visual_state()
                event.accept()
                return

            source = self._connect_source
            if node.element_id == source.element_id:
                self.editor_message.emit(
                    f"Connect mode: start {node.element_id}. Click another node as target."
                )
                event.accept()
                return

            try:
                self.create_connection(source.element_id, node.element_id)
                self.editor_message.emit(f"Connected {source.element_id} to {node.element_id}")
            except Exception as exc:
                QMessageBox.warning(self, "Connection rejected", str(exc))
            finally:
                self._connect_source = None
                self.refresh_visual_state()
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton and (
            not self._connect_mode
            and (
            event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
            )
        ):
            node = self._node_at_view_pos(event.position().toPoint())
            if node is not None:
                self._connection_start = node
                start = node.sceneBoundingRect().center()
                self._temporary_edge = QGraphicsLineItem(start.x(), start.y(), start.x(), start.y())
                self._temporary_edge.setPen(QPen(QColor("#7a8692"), 1.5, Qt.PenStyle.DashLine))
                self.scene_ref.addItem(self._temporary_edge)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self._temporary_edge is not None and self._connection_start is not None:
            start = self._connection_start.sceneBoundingRect().center()
            end = self.mapToScene(event.position().toPoint())
            self._temporary_edge.setLine(start.x(), start.y(), end.x(), end.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if self._temporary_edge is not None and self._connection_start is not None:
            target = self._node_at_view_pos(event.position().toPoint())
            self.scene_ref.removeItem(self._temporary_edge)
            self._temporary_edge = None
            source = self._connection_start
            self._connection_start = None
            if target is not None and target.element_id != source.element_id:
                try:
                    self.create_connection(source.element_id, target.element_id)
                except Exception as exc:  # UI path
                    QMessageBox.warning(self, "Connection rejected", str(exc))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def connect_selected_nodes(self) -> None:
        selected_nodes = [
            item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)
        ]
        if len(selected_nodes) != 2:
            raise ValueError("Select exactly 2 modules to connect")
        first, second = selected_nodes
        if self._is_signal_type_name(first.element_type) and not self._is_signal_type_name(second.element_type):
            self.create_connection(first.element_id, second.element_id)
            return
        if self._is_signal_type_name(second.element_type) and not self._is_signal_type_name(first.element_type):
            self.create_connection(second.element_id, first.element_id)
            return
        self.create_connection(first.element_id, second.element_id)

    def contextMenuEvent(self, event: Any) -> None:
        scene_pos = self.mapToScene(event.pos())
        item = self.scene_ref.itemAt(scene_pos, self.transform())
        node = self._extract_node_item(item)
        edge = item if isinstance(item, EdgeItem) else None

        menu = QMenu(self)
        if node is not None:
            edit_action = menu.addAction("Edit properties")
            rename_action = menu.addAction("Rename")
            delete_action = menu.addAction("Delete")
            connect_from_selected_action = None
            connect_to_selected_action = None
            selected_nodes = [
                item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)
            ]
            other_nodes = [item for item in selected_nodes if item.element_id != node.element_id]
            if len(other_nodes) == 1:
                other = other_nodes[0]
                menu.addSeparator()
                connect_from_selected_action = menu.addAction(
                    f"Connect {other.element_id} to {node.element_id}"
                )
                connect_to_selected_action = menu.addAction(
                    f"Connect {node.element_id} to {other.element_id}"
                )
            chosen = menu.exec(event.globalPos())
            if chosen == edit_action:
                self.edit_node_properties_dialog(node)
            elif chosen == rename_action:
                self.rename_node_dialog(node)
            elif chosen == delete_action:
                self.delete_node(node)
            elif chosen == connect_from_selected_action and len(other_nodes) == 1:
                try:
                    self.create_connection(other_nodes[0].element_id, node.element_id)
                except Exception as exc:
                    QMessageBox.warning(self, "Connection rejected", str(exc))
            elif chosen == connect_to_selected_action and len(other_nodes) == 1:
                try:
                    self.create_connection(node.element_id, other_nodes[0].element_id)
                except Exception as exc:
                    QMessageBox.warning(self, "Connection rejected", str(exc))
            return

        if edge is not None:
            delete_edge_action = menu.addAction("Delete connection")
            chosen = menu.exec(event.globalPos())
            if chosen == delete_edge_action:
                self.delete_edge(edge)
            return

        super().contextMenuEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.StandardKey.Undo):
            if self.undo():
                self.editor_message.emit("Undo completed")
            else:
                self.editor_message.emit("Nothing to undo")
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            if self.redo():
                self.editor_message.emit("Redo completed")
            else:
                self.editor_message.emit("Nothing to redo")
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._connect_source is not None:
                self._connect_source = None
                self.refresh_visual_state()
                self.editor_message.emit("Connect mode: canceled source selection")
                event.accept()
                return
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selected_items()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F2:
            self.rename_selected_node_dialog()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_connect_mode(self, enabled: bool) -> None:
        self._connect_mode = bool(enabled)
        self._connect_source = None
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if self._connect_mode else QGraphicsView.DragMode.RubberBandDrag
        )
        self.viewport().setCursor(
            Qt.CursorShape.CrossCursor if self._connect_mode else Qt.CursorShape.ArrowCursor
        )
        self.refresh_visual_state()
        if self._connect_mode:
            self.editor_message.emit("Connect mode ON: click source node, then target node")
        else:
            self.editor_message.emit("Connect mode OFF")

    def is_connect_mode(self) -> bool:
        return self._connect_mode

    def _snapshot_topology(self) -> RailwayTopology:
        """Capture a deep-copy snapshot for undo/redo."""
        return deepcopy(self.topology)

    def _push_undo_state(self) -> None:
        """Push current state to undo stack and clear redo stack."""
        self._undo_stack.append(self._snapshot_topology())
        if len(self._undo_stack) > self._max_undo_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Restore previous topology snapshot."""
        if not self._undo_stack:
            return False
        previous = self._undo_stack.pop()
        self._redo_stack.append(self._snapshot_topology())
        self._rebuild_from_topology(previous)
        return True

    def redo(self) -> bool:
        """Restore topology snapshot undone by the last undo action."""
        if not self._redo_stack:
            return False
        upcoming = self._redo_stack.pop()
        self._undo_stack.append(self._snapshot_topology())
        if len(self._undo_stack) > self._max_undo_depth:
            self._undo_stack.pop(0)
        self._rebuild_from_topology(upcoming)
        return True

    def add_component(
        self, element_type: str, scene_pos: QPointF, element_id: str | None = None
    ) -> NodeItem:
        """Create topology element and visual node."""
        self._push_undo_state()
        aliases = {
            "Section": "TrackSection",
            "TrackSection": "TrackSection",
            "Approach": "ApproachSection",
            "ApproachSection": "ApproachSection",
            "Point": "Point",
            "PointUp": "Point",
            "Signal": "Signal",
            "SignalRight": "SignalRight",
            "SignalLeft": "SignalLeft",
            # Backward-compatibility aliases from previous version.
            "SignalUp": "SignalRight",
            "SignalDown": "SignalLeft",
        }
        element_type = aliases.get(element_type, element_type)
        if element_type not in {
            "TrackSection",
            "ApproachSection",
            "Point",
            "Signal",
            "SignalLeft",
            "SignalRight",
        }:
            raise ValueError(f"Unsupported element type: {element_type}")
        scene_pos = self.snap_to_grid(scene_pos)

        if self._is_signal_type_name(element_type):
            counter_key = "Signal"
        elif element_type == "Point":
            counter_key = "Point"
        else:
            counter_key = element_type
        if element_id is None:
            self._counter[counter_key] += 1
            prefix = {
                "TrackSection": "S",
                "ApproachSection": "AS",
                "Point": "P",
                "Signal": "SIG",
            }[counter_key]
            element_id = f"{prefix}{self._counter[counter_key]}"

        if element_id in self.nodes or self.topology.get_element(element_id):
            raise ValueError(f"Element id already exists: {element_id}")

        if element_type == "TrackSection":
            element = TrackSection(id=element_id)
            self.topology.add_section(element, position=(scene_pos.x(), scene_pos.y()))
        elif element_type == "ApproachSection":
            element = ApproachSection(id=element_id)
            self.topology.add_approach_section(element, position=(scene_pos.x(), scene_pos.y()))
        elif element_type == "Point":
            element = Point(id=element_id, symbol_orientation=PointSymbolOrientation.RIGHT)
            self.topology.add_point(element, position=(scene_pos.x(), scene_pos.y()))
        else:
            direction = (
                SignalDirection.LEFT if element_type == "SignalLeft" else SignalDirection.RIGHT
            )
            element = Signal(id=element_id, direction=direction)
            self.topology.add_signal(element, position=(scene_pos.x(), scene_pos.y()))

        if isinstance(element, Signal):
            node_type = (
                "SignalLeft" if element.direction == SignalDirection.LEFT else "SignalRight"
            )
        elif isinstance(element, Point):
            node_type = "Point"
        else:
            node_type = element_type
        node = NodeItem(element_id, node_type, self._element_payload(element_id))
        node.setPos(scene_pos)
        self.scene_ref.addItem(node)
        node.editor = self
        self.nodes[element_id] = node
        self.topology_changed.emit()
        return node

    def create_connection(self, source_id: str, target_id: str) -> None:
        """Create directed connection between blocks."""
        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if source is None or target is None:
            raise KeyError("Connection requires existing source and target nodes")
        if source_id == target_id:
            raise ValueError("Cannot self-connect")

        if self._is_signal_type_name(source.element_type):
            signal = self.topology.signals.get(source_id)
            if signal is not None and signal.protects == target_id:
                return
        elif self._is_signal_type_name(target.element_type):
            if (source_id, target_id) in self.signal_links:
                return
        elif (
            (source_id, target_id) in self.topology.graph.edges
            or (target_id, source_id) in self.topology.graph.edges
        ):
            return

        self._push_undo_state()
        self.topology.connect(source_id, target_id)
        self._rebuild_edge_items()
        self.topology_changed.emit()

    def rename_selected_node_dialog(self) -> None:
        selected_nodes = [
            item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)
        ]
        if len(selected_nodes) != 1:
            return
        self.rename_node_dialog(selected_nodes[0])

    def rename_node_dialog(self, node: NodeItem) -> None:
        new_id, ok = QInputDialog.getText(
            self,
            "Rename element",
            "New ID:",
            text=node.element_id,
        )
        if not ok:
            return
        new_id = str(new_id).strip()
        if not new_id or new_id == node.element_id:
            return
        try:
            self.rename_node(node.element_id, new_id)
        except Exception as exc:
            QMessageBox.warning(self, "Rename failed", str(exc))

    def rename_node(self, old_id: str, new_id: str) -> None:
        if old_id not in self.nodes:
            raise KeyError(f"Unknown element {old_id}")
        if new_id in self.nodes or self.topology.get_element(new_id):
            raise ValueError(f"Element id already exists: {new_id}")
        self._push_undo_state()

        node = self.nodes[old_id]
        element = self.topology.get_element(old_id)
        if element is None:
            raise KeyError(f"Unknown element {old_id}")
        element.id = new_id

        if old_id in self.topology.graph.nodes:
            import networkx as nx

            nx.relabel_nodes(self.topology.graph, {old_id: new_id}, copy=False)
        else:
            signal = self.topology.signals.pop(old_id)
            signal.id = new_id
            self.topology.signals[new_id] = signal

        if old_id in self.topology.ui_positions:
            self.topology.ui_positions[new_id] = self.topology.ui_positions.pop(old_id)

        for point_id in list(self.topology.graph.nodes):
            point_element = self.topology.graph.nodes[point_id]["element"]
            if not isinstance(point_element, Point):
                continue
            for pos, target in list(point_element.facing_connections.items()):
                if target == old_id:
                    point_element.facing_connections[pos] = new_id

        for signal in self.topology.signals.values():
            if signal.protects == old_id:
                signal.protects = new_id
            if signal.approach_section == old_id:
                signal.approach_section = new_id

        updated_links: set[tuple[str, str]] = set()
        for src, dst in self.signal_links:
            updated_links.add(
                (
                    new_id if src == old_id else src,
                    new_id if dst == old_id else dst,
                )
            )
        self.signal_links.clear()
        self.signal_links.update(updated_links)
        self.topology.sync_signal_virtual_routes()
        self._rebuild_edge_items()

        self.nodes[new_id] = self.nodes.pop(old_id)
        node.element_id = new_id
        self.refresh_visual_state()
        self.topology_changed.emit()

    def delete_selected_items(self) -> None:
        selected = list(self.scene_ref.selectedItems())
        edges = [item for item in selected if isinstance(item, EdgeItem)]
        nodes = [item for item in selected if isinstance(item, NodeItem)]

        if not edges and not nodes:
            return
        self._push_undo_state()

        changed = False
        for edge in edges:
            self.delete_edge(edge, emit_change=False, record_undo=False)
            changed = True

        for node in nodes:
            self.delete_node(node, emit_change=False, record_undo=False)
            changed = True

        if changed:
            self.refresh_visual_state()
            self.topology_changed.emit()

    def delete_node(
        self,
        node: NodeItem,
        emit_change: bool = True,
        record_undo: bool = True,
    ) -> None:
        node_id = node.element_id
        if node_id not in self.nodes:
            return
        if record_undo:
            self._push_undo_state()

        if self._connect_source is node:
            self._connect_source = None

        connected_edges = [
            edge
            for edge in list(self.edges)
            if edge.source.element_id == node_id or edge.target.element_id == node_id
        ]
        for edge in connected_edges:
            self.delete_edge(edge, emit_change=False, record_undo=False)

        self.scene_ref.removeItem(node)
        self.nodes.pop(node_id, None)
        self.topology.ui_positions.pop(node_id, None)

        if node_id in self.topology.graph.nodes:
            self.topology.graph.remove_node(node_id)
        else:
            self.topology.signals.pop(node_id, None)

        for point_id in list(self.topology.graph.nodes):
            point_element = self.topology.graph.nodes[point_id]["element"]
            if not isinstance(point_element, Point):
                continue
            for pos, target in list(point_element.facing_connections.items()):
                if target == node_id:
                    point_element.facing_connections.pop(pos, None)

        for signal in self.topology.signals.values():
            if signal.protects == node_id:
                signal.protects = ""
            if signal.approach_section == node_id:
                signal.approach_section = ""

        filtered_links = {
            (src, dst) for src, dst in self.signal_links if src != node_id and dst != node_id
        }
        self.signal_links.clear()
        self.signal_links.update(filtered_links)
        self.topology.sync_signal_virtual_routes()
        self._rebuild_edge_items()

        if emit_change:
            self.refresh_visual_state()
            self.topology_changed.emit()

    def delete_edge(
        self,
        edge: EdgeItem,
        emit_change: bool = True,
        record_undo: bool = True,
    ) -> None:
        if record_undo:
            self._push_undo_state()
        source_id = edge.source.element_id
        target_id = edge.target.element_id

        self.topology.disconnect(source_id, target_id)
        self._rebuild_edge_items()

        if emit_change:
            self.refresh_visual_state()
            self.topology_changed.emit()

    def edit_node_properties_dialog(self, node: NodeItem) -> None:
        """Open a double-click edit dialog for a node."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit {node.element_id}")
        form = QFormLayout(dialog)

        id_input = QLineEdit(node.element_id, dialog)
        form.addRow("ID", id_input)
        controls: dict[str, Any] = {}
        if node.element_type in {"TrackSection", "ApproachSection"}:
            length = QDoubleSpinBox(dialog)
            length.setRange(1.0, 10000.0)
            length.setValue(float(node.payload.get("length", 100.0)))
            occupied = QComboBox(dialog)
            occupied.addItems(["FREE", "OCCUPIED"])
            occupied.setCurrentText("OCCUPIED" if node.payload.get("occupied", False) else "FREE")
            locked_by = QLineEdit(str(node.payload.get("locked_by") or ""), dialog)
            controls["length"] = length
            controls["occupied"] = occupied
            controls["locked_by"] = locked_by
            form.addRow("Length", length)
            form.addRow("State", occupied)
            form.addRow("Locked by", locked_by)
        elif node.element_type == "Point":
            position = QComboBox(dialog)
            position.addItems([PointPosition.NORMAL.value, PointPosition.REVERSE.value])
            position.setCurrentText(str(node.payload.get("position", PointPosition.NORMAL.value)))
            symbol_orientation = QComboBox(dialog)
            for label, orientation in POINT_SYMBOL_CHOICES:
                symbol_orientation.addItem(label, orientation.value)
            current_orientation = str(
                node.payload.get("symbol_orientation", PointSymbolOrientation.RIGHT.value)
            )
            symbol_index = symbol_orientation.findData(current_orientation)
            symbol_orientation.setCurrentIndex(symbol_index if symbol_index >= 0 else 0)
            normal = QLineEdit(str(node.payload.get("normal_target", "")), dialog)
            reverse = QLineEdit(str(node.payload.get("reverse_target", "")), dialog)
            locked_by = QLineEdit(str(node.payload.get("locked_by") or ""), dialog)
            controls["position"] = position
            controls["symbol_orientation"] = symbol_orientation
            controls["normal_target"] = normal
            controls["reverse_target"] = reverse
            controls["locked_by"] = locked_by
            form.addRow("Position", position)
            form.addRow("Symbol", symbol_orientation)
            form.addRow("Normal ->", normal)
            form.addRow("Reverse ->", reverse)
            form.addRow("Locked by", locked_by)
        else:
            protects = QLineEdit(str(node.payload.get("protects", "")), dialog)
            approach_section = QLineEdit(str(node.payload.get("approach_section", "")), dialog)
            direction = QComboBox(dialog)
            direction.addItems([SignalDirection.LEFT.value, SignalDirection.RIGHT.value])
            direction.setCurrentText(str(node.payload.get("direction", SignalDirection.RIGHT.value)))
            aspect = QComboBox(dialog)
            aspect.addItems([SignalAspect.STOP.value, SignalAspect.PROCEED.value])
            aspect.setCurrentText(str(node.payload.get("aspect", SignalAspect.STOP.value)))
            controls["protects"] = protects
            controls["approach_section"] = approach_section
            controls["direction"] = direction
            controls["aspect"] = aspect
            form.addRow("Protects", protects)
            form.addRow("Approach section", approach_section)
            form.addRow("Direction", direction)
            form.addRow("Aspect", aspect)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, parent=dialog
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                target_id = str(id_input.text()).strip()
                if target_id and target_id != node.element_id:
                    self.rename_node(node.element_id, target_id)
                    node = self.nodes[target_id]

                updates: dict[str, Any] = {}
                for key, widget in controls.items():
                    if isinstance(widget, QDoubleSpinBox):
                        updates[key] = float(widget.value())
                    elif isinstance(widget, QComboBox):
                        if key == "symbol_orientation":
                            symbol_orientation = widget.currentData()
                            updates[key] = str(symbol_orientation or widget.currentText())
                        else:
                            updates[key] = str(widget.currentText())
                    elif isinstance(widget, QLineEdit):
                        updates[key] = str(widget.text()).strip()
                if updates:
                    self.update_node_properties(node.element_id, updates)
            except Exception as exc:
                QMessageBox.warning(self, "Property update failed", str(exc))

    def update_node_properties(self, element_id: str, updates: dict[str, Any]) -> None:
        """Apply updated properties to domain model and refresh visuals."""
        element = self.topology.get_element(element_id)
        if element is None:
            raise KeyError(f"Unknown element {element_id}")
        if updates:
            self._push_undo_state()
        emit_topology_change = False

        if isinstance(element, TrackSection):
            if "length" in updates:
                element.length = float(updates["length"])
            if "occupied" in updates:
                occupied_value = updates["occupied"]
                if isinstance(occupied_value, str):
                    element.occupied = occupied_value.strip().upper() == "OCCUPIED"
                else:
                    element.occupied = bool(occupied_value)
            if "locked_by" in updates:
                locked_by_text = str(updates["locked_by"]).strip()
                element.locked_by = locked_by_text or None

        elif isinstance(element, Point):
            target_locked_by = element.locked_by
            if "locked_by" in updates:
                locked_by_text = str(updates["locked_by"]).strip()
                target_locked_by = locked_by_text or None
            if "position" in updates:
                requested_position = PointPosition(str(updates["position"]))
                if target_locked_by and requested_position != element.position:
                    raise RuntimeError(
                        f"Point {element.id} is locked by {target_locked_by}. Unlock before moving."
                    )
                element.position = requested_position
            if "symbol_orientation" in updates:
                element.symbol_orientation = PointSymbolOrientation(
                    str(updates["symbol_orientation"])
                )
            normal_target = str(updates.get("normal_target", "")).strip()
            reverse_target = str(updates.get("reverse_target", "")).strip()
            if normal_target:
                element.facing_connections[PointPosition.NORMAL] = normal_target
                emit_topology_change = True
            elif PointPosition.NORMAL in element.facing_connections:
                element.facing_connections.pop(PointPosition.NORMAL, None)
                emit_topology_change = True
            if reverse_target:
                element.facing_connections[PointPosition.REVERSE] = reverse_target
                emit_topology_change = True
            elif PointPosition.REVERSE in element.facing_connections:
                element.facing_connections.pop(PointPosition.REVERSE, None)
                emit_topology_change = True
            if "locked_by" in updates:
                element.locked_by = target_locked_by

        elif isinstance(element, Signal):
            if "protects" in updates:
                new_protects = str(updates["protects"]).strip()
                if new_protects and new_protects not in self.topology.graph.nodes:
                    raise ValueError(
                        "Protects must reference an existing track section or point node"
                    )
                element.protects = new_protects
                self.topology.sync_signal_virtual_routes()
                self._rebuild_edge_items()
                emit_topology_change = True
            if "approach_section" in updates:
                approach_section = str(updates["approach_section"]).strip()
                if approach_section:
                    approach_element = self.topology.get_element(approach_section)
                    if not isinstance(approach_element, ApproachSection):
                        raise ValueError(
                            "Approach section must reference an existing ApproachSection node"
                        )
                    if not self.topology.is_signal_back_side_node(element_id, approach_section):
                        raise ValueError(
                            "Approach section must be on the rear side of the signal direction"
                        )
                element.approach_section = approach_section
            if "direction" in updates:
                element.direction = SignalDirection(str(updates["direction"]))
                node = self.nodes.get(element_id)
                if node is not None:
                    node.element_type = (
                        "SignalLeft" if element.direction == SignalDirection.LEFT else "SignalRight"
                    )
            if "aspect" in updates:
                element.aspect = SignalAspect(str(updates["aspect"]))

        self.refresh_visual_state()
        if emit_topology_change:
            self.topology_changed.emit()

    def handle_node_moved(self, node: NodeItem) -> None:
        """Persist node position and update connected edges."""
        self.topology.update_position(node.element_id, (node.pos().x(), node.pos().y()))
        for edge in self.edges:
            if edge.source is node or edge.target is node:
                edge.update_geometry()

    def _on_selection_changed(self) -> None:
        selected_items = [item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)]
        if not selected_items:
            self.node_selected.emit(None)
            return
        node = selected_items[0]
        self.node_selected.emit(
            {
                "id": node.element_id,
                "type": node.element_type,
                "properties": dict(node.payload),
            }
        )

    def _node_at_view_pos(self, pos: Any) -> Optional[NodeItem]:
        scene_pos = self.mapToScene(pos)
        item = self.scene_ref.itemAt(scene_pos, self.transform())
        return self._extract_node_item(item)

    @staticmethod
    def _extract_node_item(item: Any) -> Optional[NodeItem]:
        while item is not None and not isinstance(item, NodeItem):
            item = item.parentItem()
        return item if isinstance(item, NodeItem) else None

    def _element_payload(self, element_id: str) -> dict[str, Any]:
        element = self.topology.get_element(element_id)
        if isinstance(element, TrackSection):
            return asdict(element)
        if isinstance(element, Point):
            payload = asdict(element)
            payload["position"] = element.position.value
            payload["symbol_orientation"] = element.symbol_orientation.value
            payload["normal_target"] = element.facing_connections.get(PointPosition.NORMAL, "")
            payload["reverse_target"] = element.facing_connections.get(PointPosition.REVERSE, "")
            return payload
        if isinstance(element, Signal):
            payload = asdict(element)
            payload["aspect"] = element.aspect.value
            payload["direction"] = element.direction.value
            return payload
        return {}

    def refresh_visual_state(self) -> None:
        """Refresh node colors and labels from topology state."""
        for element_id, node in self.nodes.items():
            node.payload = self._element_payload(element_id)
            node.update()
        for edge in self.edges:
            edge.update_geometry()

    def _connection_pairs(self) -> list[tuple[str, str]]:
        """Return visualized connections in deterministic order."""
        pairs: list[tuple[str, str]] = []
        for source_id, target_id in sorted(self.topology.graph.edges):
            if (source_id, target_id) in self.topology._signal_virtual_edges:
                continue
            pairs.append((source_id, target_id))

        for signal in sorted(self.topology.signals.values(), key=lambda item: item.id):
            protected = signal.protects.strip()
            if protected and protected in self.nodes:
                pairs.append((signal.id, protected))

        for source_id, target_id in sorted(self.signal_links):
            if source_id in self.nodes and target_id in self.nodes:
                pairs.append((source_id, target_id))
        return pairs

    def _rebuild_edge_items(self) -> None:
        """Recreate all edge graphics from current topology links."""
        for edge in list(self.edges):
            self.scene_ref.removeItem(edge)
        self.edges.clear()

        seen: set[tuple[str, str]] = set()
        for source_id, target_id in self._connection_pairs():
            if (source_id, target_id) in seen:
                continue
            source_node = self.nodes.get(source_id)
            target_node = self.nodes.get(target_id)
            if source_node is None or target_node is None:
                continue
            edge = EdgeItem(source_node, target_node)
            self.scene_ref.addItem(edge)
            self.edges.append(edge)
            seen.add((source_id, target_id))

    def load_topology(self, topology: RailwayTopology) -> None:
        """Load topology object directly."""
        self._rebuild_from_topology(topology)

    def clear_layout(self) -> None:
        """Clear current scene and reset to an empty topology."""
        if self.nodes or self.edges:
            self._push_undo_state()
        self._rebuild_from_topology(RailwayTopology())

    def _rebuild_from_topology(self, topology: RailwayTopology) -> None:
        self.clear_route_visualization()
        self.scene_ref.clear()
        self.nodes.clear()
        self.edges.clear()
        self._connect_source = None
        self.topology = topology
        self.signal_links = self.topology.signal_links
        self.topology.sync_signal_virtual_routes()
        self._counter = {"TrackSection": 0, "ApproachSection": 0, "Point": 0, "Signal": 0}

        for node_id in topology.graph.nodes:
            element = topology.graph.nodes[node_id]["element"]
            if isinstance(element, ApproachSection):
                element_type = "ApproachSection"
                self._counter[element_type] = max(self._counter[element_type], self._extract_suffix(node_id))
            elif isinstance(element, TrackSection):
                element_type = "TrackSection"
                self._counter[element_type] = max(self._counter[element_type], self._extract_suffix(node_id))
            elif isinstance(element, Point):
                element_type = "Point"
                self._counter[element_type] = max(self._counter[element_type], self._extract_suffix(node_id))
            else:
                continue
            position = topology.ui_positions.get(node_id, (0.0, 0.0))
            node = NodeItem(node_id, element_type, self._element_payload(node_id))
            node.setPos(QPointF(position[0], position[1]))
            self.scene_ref.addItem(node)
            node.editor = self
            self.nodes[node_id] = node

        for signal_id in topology.signals:
            self._counter["Signal"] = max(self._counter["Signal"], self._extract_suffix(signal_id))
            position = topology.ui_positions.get(signal_id, (0.0, 0.0))
            signal = topology.signals[signal_id]
            signal_type = "SignalLeft" if signal.direction == SignalDirection.LEFT else "SignalRight"
            node = NodeItem(signal_id, signal_type, self._element_payload(signal_id))
            node.setPos(QPointF(position[0], position[1]))
            self.scene_ref.addItem(node)
            node.editor = self
            self.nodes[signal_id] = node

        self._rebuild_edge_items()

        self.refresh_visual_state()
        self.topology_changed.emit()

    @staticmethod
    def _extract_suffix(element_id: str) -> int:
        digits = "".join(ch for ch in element_id if ch.isdigit())
        return int(digits) if digits else 0

    @staticmethod
    def _is_signal_type_name(element_type: str) -> bool:
        return element_type in {"Signal", "SignalLeft", "SignalRight", "SignalUp", "SignalDown"}

    def animate_route_search(
        self,
        search_sequence: list[str],
        route_path: list[str],
        overlap_path: list[str] | None = None,
        interval_ms: int = 280,
    ) -> None:
        """Animate visited nodes then highlight final route path."""
        self.clear_route_visualization()
        self._search_sequence = [node_id for node_id in search_sequence if node_id in self.nodes]
        self._route_highlight_nodes = {node_id for node_id in route_path if node_id in self.nodes}
        self._overlap_highlight_nodes = {
            node_id for node_id in (overlap_path or []) if node_id in self.nodes
        }
        self._search_index = 0
        if self._search_sequence:
            self._search_timer.start(max(80, interval_ms))
        self.refresh_visual_state()

    def clear_route_visualization(self) -> None:
        """Clear any active route search/path highlight."""
        self._search_timer.stop()
        self._search_sequence.clear()
        self._search_index = 0
        self._search_highlight_nodes.clear()
        self._route_highlight_nodes.clear()
        self._overlap_highlight_nodes.clear()
        self.refresh_visual_state()

    def _advance_search_animation(self) -> None:
        if self._search_index >= len(self._search_sequence):
            self._search_timer.stop()
            self.refresh_visual_state()
            return
        self._search_highlight_nodes.add(self._search_sequence[self._search_index])
        self._search_index += 1
        self.refresh_visual_state()
