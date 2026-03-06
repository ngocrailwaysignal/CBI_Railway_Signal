"""Interactive drag-and-drop canvas for topology editing."""

from __future__ import annotations

from copy import deepcopy
from math import hypot
from dataclasses import asdict
from typing import Any, Callable, Optional

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QBrush,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
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

from core.domain.model.elements import (
    ApproachSection,
    Point,
    PointPosition,
    PointSymbolOrientation,
    Signal,
    SignalAspect,
    SignalDirection,
    TrackSection,
)
from core.domain.model.topology import RailwayTopology
from ui.i18n import UITranslator
from ui.views.components_palette_view import PaletteListWidget

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
        return QRectF(0.0, 0.0, self.WIDTH, self.HEIGHT)

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
            (rect.bottom() - split_y - 4.0) * 0.58,
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.element_id)

        is_occupied = bool(self.payload.get("occupied"))
        if self.editor is not None:
            state_text = self.editor.state_label(is_occupied)
        else:
            state_text = "OCCUPIED" if is_occupied else "FREE"
        state_color = QColor("#c62828") if is_occupied else QColor("#2e7d32")
        state_rect = QRectF(
            rect.left() + 4.0,
            label_rect.bottom() - 1.0,
            rect.width() - 8.0,
            rect.bottom() - label_rect.bottom() - 3.0,
        )
        painter.setPen(QPen(state_color, 1.0))
        painter.drawText(state_rect, Qt.AlignmentFlag.AlignCenter, state_text)

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

        symbol_orientation = str(
            self.payload.get("symbol_orientation", PointSymbolOrientation.RIGHT.value)
        )
        branch_offset = max(6.0, panel.height() * 0.30)
        rail_half = panel.width() / 2.0 - 2.0

        # Point UI is controlled only by symbol orientation.
        # NORMAL/REVERSE position remains a runtime logic state and does not flip symbol drawing.
        # RIGHT  -> toe left, branch to upper-right
        # DOWN   -> toe left, branch to lower-right
        # LEFT   -> toe right, branch to lower-left
        # UP     -> toe right, branch to upper-left
        if symbol_orientation == PointSymbolOrientation.LEFT.value:
            toe_x, toe_y = rail_half, 0.0
            straight_x, straight_y = -rail_half, 0.0
            branch_x = -rail_half
            branch_y = branch_offset
        elif symbol_orientation == PointSymbolOrientation.UP.value:
            toe_x, toe_y = rail_half, 0.0
            straight_x, straight_y = -rail_half, 0.0
            branch_x = -rail_half
            branch_y = -branch_offset
        elif symbol_orientation == PointSymbolOrientation.DOWN.value:
            toe_x, toe_y = -rail_half, 0.0
            straight_x, straight_y = rail_half, 0.0
            branch_x = rail_half
            branch_y = branch_offset
        else:
            toe_x, toe_y = -rail_half, 0.0
            straight_x, straight_y = rail_half, 0.0
            branch_x = rail_half
            branch_y = -branch_offset

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


class TrainSpriteItem(QGraphicsObject):
    """Animated train icon inspired by the provided reference style."""

    BASE_WIDTH = 84.0
    BASE_HEIGHT = 44.0
    WIDTH = 56.0
    HEIGHT = 28.0

    def __init__(self, train_id: str) -> None:
        super().__init__()
        self.train_id = train_id
        self._facing_left = False
        self.setZValue(16.0)

    def boundingRect(self) -> QRectF:
        return QRectF(0.0, 0.0, self.WIDTH, self.HEIGHT)

    def set_facing_left(self, enabled: bool) -> None:
        facing_left = bool(enabled)
        if self._facing_left == facing_left:
            return
        self._facing_left = facing_left
        self.update()

    def paint(self, painter: QPainter, _option: Any, _widget: Any = None) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._facing_left:
            painter.translate(self.WIDTH, 0.0)
            painter.scale(-1.0, 1.0)
        painter.scale(self.WIDTH / self.BASE_WIDTH, self.HEIGHT / self.BASE_HEIGHT)

        body_outline = QPen(QColor("#111111"), 2.8)
        body_fill = QBrush(QColor("#eceff2"))
        body_path = QPainterPath()
        body_path.moveTo(8.0, 7.0)
        body_path.lineTo(56.0, 7.0)
        body_path.quadTo(65.0, 7.0, 70.0, 14.0)
        body_path.lineTo(78.0, 25.0)
        body_path.quadTo(82.0, 30.0, 80.0, 35.0)
        body_path.quadTo(78.0, 39.0, 72.0, 39.0)
        body_path.lineTo(8.0, 39.0)
        body_path.quadTo(4.0, 39.0, 4.0, 35.0)
        body_path.lineTo(4.0, 12.0)
        body_path.quadTo(4.0, 7.0, 8.0, 7.0)
        body_path.closeSubpath()
        painter.setPen(body_outline)
        painter.setBrush(body_fill)
        painter.drawPath(body_path)

        painter.setPen(body_outline)
        painter.setBrush(QBrush(QColor("#ff4338")))
        painter.drawRoundedRect(QRectF(4.6, 26.0, 74.0, 11.0), 5.0, 5.0)

        painter.setBrush(QBrush(QColor("#1aa2e0")))
        painter.drawRoundedRect(QRectF(12.0, 11.0, 14.0, 18.0), 2.5, 2.5)
        painter.drawRoundedRect(QRectF(31.5, 12.5, 13.5, 10.5), 2.0, 2.0)

        front_window = QPolygonF(
            [
                QPointF(49.0, 12.0),
                QPointF(61.0, 12.0),
                QPointF(67.5, 22.0),
                QPointF(49.0, 22.0),
            ]
        )
        painter.drawPolygon(front_window)

        painter.setBrush(QBrush(QColor("#7ea0b5")))
        painter.drawEllipse(QRectF(38.0, 34.0, 8.6, 8.6))
        painter.drawEllipse(QRectF(53.0, 34.0, 8.6, 8.6))

        painter.setPen(QPen(QColor("#0f1012"), 1.7))
        painter.drawLine(QPointF(12.0, 17.5), QPointF(20.0, 17.5))
        painter.drawLine(QPointF(12.0, 22.0), QPointF(20.0, 22.0))

        painter.setPen(QPen(QColor("#0f1012"), 3.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(6.0, 24.4), QPointF(55.0, 24.4))
        painter.drawLine(QPointF(60.0, 24.4), QPointF(78.0, 24.4))
        painter.restore()


class CanvasEditor(QGraphicsView):
    """Grid canvas supporting block drag-drop and edge connection."""

    GRID_STEP = 25.0
    ZOOM_FACTOR = 1.15
    MIN_ZOOM = 0.3
    MAX_ZOOM = 4.0
    editor_message = pyqtSignal(str)
    node_selected = pyqtSignal(object)
    topology_changed = pyqtSignal()

    def __init__(
        self,
        parent: Optional[Any] = None,
        translator: UITranslator | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator or UITranslator()
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
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
        self._runtime_edit_locked = False
        self._runtime_edit_lock_reason = ""
        self._layout_edit_locked = False
        self._layout_edit_lock_reason = ""
        self._simulation: Any | None = None
        self._manual_override_handler: Callable[[str, bool, bool], list[str]] | None = None
        self._train_items: dict[str, TrainSpriteItem] = {}
        self._train_animations: dict[str, QPropertyAnimation] = {}
        self._train_last_sections: dict[str, str] = {}
        self._train_animation_duration_ms = 420
        self._is_panning = False
        self._pan_last_pos: Any = None
        self._pan_has_moved = False
        self._suppress_context_menu_once = False

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    def set_translator(self, translator: UITranslator) -> None:
        self._translator = translator
        self.refresh_visual_state()

    def state_label(self, occupied: bool) -> str:
        return self._t("state.occupied" if occupied else "state.free")

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
            QMessageBox.warning(
                self,
                self._t("canvas.dialog.cannot_add_component.title"),
                str(exc),
            )
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
        if event.button() == Qt.MouseButton.RightButton:
            self._is_panning = True
            self._pan_last_pos = event.position().toPoint()
            self._pan_has_moved = False
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

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
                    self._t(
                        "canvas.message.connect_start_select_target",
                        node_id=node.element_id,
                    )
                )
                self.refresh_visual_state()
                event.accept()
                return

            source = self._connect_source
            if node.element_id == source.element_id:
                self.editor_message.emit(
                    self._t(
                        "canvas.message.connect_start_select_another",
                        node_id=node.element_id,
                    )
                )
                event.accept()
                return

            try:
                self.create_connection(source.element_id, node.element_id)
                self.editor_message.emit(
                    self._t(
                        "canvas.message.connected_pair",
                        source=source.element_id,
                        target=node.element_id,
                    )
                )
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    self._t("canvas.dialog.connection_rejected.title"),
                    str(exc),
                )
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
        if self._is_panning and self._pan_last_pos is not None:
            current_pos = event.position().toPoint()
            delta = current_pos - self._pan_last_pos
            self._pan_last_pos = current_pos
            if delta.manhattanLength() > 0:
                self._pan_has_moved = True
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        if self._temporary_edge is not None and self._connection_start is not None:
            start = self._connection_start.sceneBoundingRect().center()
            end = self.mapToScene(event.position().toPoint())
            self._temporary_edge.setLine(start.x(), start.y(), end.x(), end.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MouseButton.RightButton and self._is_panning:
            self._is_panning = False
            self._pan_last_pos = None
            self._suppress_context_menu_once = self._pan_has_moved
            self._pan_has_moved = False
            if self._connect_mode:
                self.viewport().setCursor(Qt.CursorShape.CrossCursor)
            else:
                self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

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
                    QMessageBox.warning(
                        self,
                        self._t("canvas.dialog.connection_rejected.title"),
                        str(exc),
                    )
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event: Any) -> None:
        if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            super().wheelEvent(event)
            return

        delta_y = event.angleDelta().y()
        if delta_y == 0:
            super().wheelEvent(event)
            return

        current_zoom = self.transform().m11()
        zoom_in = delta_y > 0
        next_zoom = current_zoom * (self.ZOOM_FACTOR if zoom_in else 1.0 / self.ZOOM_FACTOR)

        if not (self.MIN_ZOOM <= next_zoom <= self.MAX_ZOOM):
            event.accept()
            return

        factor = self.ZOOM_FACTOR if zoom_in else 1.0 / self.ZOOM_FACTOR
        self.scale(factor, factor)
        event.accept()

    def connect_selected_nodes(self) -> None:
        selected_nodes = [
            item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)
        ]
        if len(selected_nodes) != 2:
            raise ValueError(self._t("canvas.error.select_exactly_two_modules"))
        first, second = selected_nodes
        if self._is_signal_type_name(first.element_type) and not self._is_signal_type_name(second.element_type):
            self.create_connection(first.element_id, second.element_id)
            return
        if self._is_signal_type_name(second.element_type) and not self._is_signal_type_name(first.element_type):
            self.create_connection(second.element_id, first.element_id)
            return
        self.create_connection(first.element_id, second.element_id)

    def contextMenuEvent(self, event: Any) -> None:
        if self._suppress_context_menu_once:
            self._suppress_context_menu_once = False
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        item = self.scene_ref.itemAt(scene_pos, self.transform())
        node = self._extract_node_item(item)
        edge = item if isinstance(item, EdgeItem) else None

        menu = QMenu(self)
        if node is not None:
            edit_action = menu.addAction(self._t("canvas.menu.edit_properties"))
            rename_action = menu.addAction(self._t("canvas.menu.rename"))
            delete_action = menu.addAction(self._t("canvas.menu.delete"))
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
                    self._t(
                        "canvas.menu.connect_pair",
                        source=other.element_id,
                        target=node.element_id,
                    )
                )
                connect_to_selected_action = menu.addAction(
                    self._t(
                        "canvas.menu.connect_pair",
                        source=node.element_id,
                        target=other.element_id,
                    )
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
                    QMessageBox.warning(
                        self,
                        self._t("canvas.dialog.connection_rejected.title"),
                        str(exc),
                    )
            elif chosen == connect_to_selected_action and len(other_nodes) == 1:
                try:
                    self.create_connection(node.element_id, other_nodes[0].element_id)
                except Exception as exc:
                    QMessageBox.warning(
                        self,
                        self._t("canvas.dialog.connection_rejected.title"),
                        str(exc),
                    )
            return

        if edge is not None:
            delete_edge_action = menu.addAction(self._t("canvas.menu.delete_connection"))
            chosen = menu.exec(event.globalPos())
            if chosen == delete_edge_action:
                self.delete_edge(edge)
            return

        super().contextMenuEvent(event)

    def keyPressEvent(self, event: Any) -> None:
        if event.matches(QKeySequence.StandardKey.Undo):
            if self.undo():
                self.editor_message.emit(self._t("canvas.message.undo_completed"))
            else:
                self.editor_message.emit(self._t("canvas.message.nothing_to_undo"))
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            if self.redo():
                self.editor_message.emit(self._t("canvas.message.redo_completed"))
            else:
                self.editor_message.emit(self._t("canvas.message.nothing_to_redo"))
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            if self._connect_source is not None:
                self._connect_source = None
                self.refresh_visual_state()
                self.editor_message.emit(self._t("canvas.message.connect_mode_canceled_source"))
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
            self.editor_message.emit(self._t("canvas.message.connect_mode_on"))
        else:
            self.editor_message.emit(self._t("canvas.message.connect_mode_off"))

    def set_runtime_edit_lock(self, enabled: bool, reason: str = "") -> None:
        """Enable/disable runtime protection for unsafe manual state edits."""
        self._runtime_edit_locked = bool(enabled)
        self._runtime_edit_lock_reason = str(reason).strip()

    def set_layout_edit_lock(self, enabled: bool, reason: str = "") -> None:
        """Enable/disable topology/layout editing operations."""
        self._layout_edit_locked = bool(enabled)
        self._layout_edit_lock_reason = str(reason).strip()
        if self._layout_edit_locked and self._connect_mode:
            self.set_connect_mode(False)
        accepts_drop = not self._layout_edit_locked
        self.setAcceptDrops(accepts_drop)
        self.viewport().setAcceptDrops(accepts_drop)
        self._apply_layout_edit_flags()

    def is_layout_edit_locked(self) -> bool:
        return self._layout_edit_locked

    def _apply_layout_edit_flags(self) -> None:
        movable = not self._layout_edit_locked
        for node in self.nodes.values():
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)

    def _ensure_layout_edit_allowed(self, action_key: str) -> None:
        if not self._layout_edit_locked:
            return
        reason = self._layout_edit_lock_reason or self._t("main.lock.layout_edit_reason")
        raise RuntimeError(
            self._t(
                "canvas.error.layout_edit_locked",
                action=self._t(action_key),
                reason=reason,
            )
        )

    def set_simulation(self, simulation: Any | None) -> None:
        """Attach simulation state to render animated train sprites."""
        self._simulation = simulation
        if simulation is None:
            self._clear_train_visuals()
            return
        self._sync_train_visuals()

    def set_manual_override_handler(
        self,
        handler: Callable[[str, bool, bool], list[str]] | None,
    ) -> None:
        """Inject application-level manual override use-case handler."""
        self._manual_override_handler = handler

    def set_train_animation_duration(self, duration_ms: int) -> None:
        self._train_animation_duration_ms = max(0, int(duration_ms))

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
        self._ensure_layout_edit_allowed("canvas.action.add_components")
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
            raise ValueError(
                self._t(
                    "canvas.error.unsupported_element_type",
                    element_type=element_type,
                )
            )
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
            raise ValueError(
                self._t(
                    "canvas.error.element_id_exists",
                    element_id=element_id,
                )
            )

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
        self._ensure_layout_edit_allowed("canvas.action.create_connections")
        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if source is None or target is None:
            raise KeyError(self._t("canvas.error.connection_requires_existing_nodes"))
        if source_id == target_id:
            raise ValueError(self._t("canvas.error.cannot_self_connect"))

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
            self._t("canvas.dialog.rename_element.title"),
            self._t("canvas.dialog.rename_element.prompt"),
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
            QMessageBox.warning(
                self,
                self._t("canvas.dialog.rename_failed.title"),
                str(exc),
            )

    def rename_node(self, old_id: str, new_id: str) -> None:
        self._ensure_layout_edit_allowed("canvas.action.rename_elements")
        if old_id not in self.nodes:
            raise KeyError(self._t("canvas.error.unknown_element", element_id=old_id))
        if new_id in self.nodes or self.topology.get_element(new_id):
            raise ValueError(
                self._t(
                    "canvas.error.element_id_exists",
                    element_id=new_id,
                )
            )
        self._push_undo_state()

        node = self.nodes[old_id]
        element = self.topology.get_element(old_id)
        if element is None:
            raise KeyError(self._t("canvas.error.unknown_element", element_id=old_id))
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

        remapped_groups: list[set[str]] = []
        for group in self.topology.clearance_conflict_groups:
            remapped = {new_id if node_id == old_id else node_id for node_id in group}
            if len(remapped) >= 2 and remapped not in remapped_groups:
                remapped_groups.append(remapped)
        self.topology.clearance_conflict_groups = remapped_groups

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
        self._ensure_layout_edit_allowed("canvas.action.delete_elements_or_connections")
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
        self._ensure_layout_edit_allowed("canvas.action.delete_elements")
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
        filtered_groups: list[set[str]] = []
        for group in self.topology.clearance_conflict_groups:
            updated = {member for member in group if member != node_id}
            if len(updated) >= 2 and updated not in filtered_groups:
                filtered_groups.append(updated)
        self.topology.clearance_conflict_groups = filtered_groups
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
        self._ensure_layout_edit_allowed("canvas.action.delete_connections")
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
        dialog.setWindowTitle(
            self._t("canvas.dialog.edit_element.title", element_id=node.element_id)
        )
        form = QFormLayout(dialog)
        layout_lock_hint = self._layout_edit_lock_reason or self._t("canvas.lock.layout_editing_locked")

        id_input = QLineEdit(node.element_id, dialog)
        form.addRow(self._t("field.id"), id_input)
        if self._layout_edit_locked:
            id_input.setEnabled(False)
            id_input.setToolTip(layout_lock_hint)
        controls: dict[str, Any] = {}
        if node.element_type in {"TrackSection", "ApproachSection"}:
            length = QDoubleSpinBox(dialog)
            length.setRange(1.0, 10000.0)
            length.setValue(float(node.payload.get("length", 100.0)))
            occupied = QComboBox(dialog)
            occupied.addItem(self._t("state.free"), False)
            occupied.addItem(self._t("state.occupied"), True)
            occupied.setCurrentIndex(1 if node.payload.get("occupied", False) else 0)
            locked_by = QLineEdit(str(node.payload.get("locked_by") or ""), dialog)
            controls["length"] = length
            controls["occupied"] = occupied
            controls["locked_by"] = locked_by
            form.addRow(self._t("field.length"), length)
            form.addRow(self._t("field.state"), occupied)
            form.addRow(self._t("field.locked_by"), locked_by)
            if self._layout_edit_locked:
                length.setEnabled(False)
                length.setToolTip(layout_lock_hint)
                locked_by.setEnabled(False)
                locked_by.setToolTip(layout_lock_hint)
            if self._runtime_edit_locked:
                occupied.setEnabled(False)
                locked_by.setEnabled(False)
                hint = self._runtime_edit_lock_reason or self._t("canvas.lock.runtime_lock_active")
                occupied.setToolTip(hint)
                locked_by.setToolTip(hint)
        elif node.element_type == "Point":
            position = QComboBox(dialog)
            position.addItem(self._t("point_position.normal"), PointPosition.NORMAL.value)
            position.addItem(self._t("point_position.reverse"), PointPosition.REVERSE.value)
            current_position = str(node.payload.get("position", PointPosition.NORMAL.value))
            position_index = position.findData(current_position)
            position.setCurrentIndex(position_index if position_index >= 0 else 0)
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
            form.addRow(self._t("field.position"), position)
            form.addRow(self._t("field.symbol"), symbol_orientation)
            form.addRow(self._t("field.normal_to"), normal)
            form.addRow(self._t("field.reverse_to"), reverse)
            form.addRow(self._t("field.locked_by"), locked_by)
            if self._layout_edit_locked:
                symbol_orientation.setEnabled(False)
                normal.setEnabled(False)
                reverse.setEnabled(False)
                locked_by.setEnabled(False)
                symbol_orientation.setToolTip(layout_lock_hint)
                normal.setToolTip(layout_lock_hint)
                reverse.setToolTip(layout_lock_hint)
                locked_by.setToolTip(layout_lock_hint)
            if self._runtime_edit_locked:
                locked_by.setEnabled(False)
                locked_by.setToolTip(
                    self._runtime_edit_lock_reason or self._t("canvas.lock.runtime_lock_active")
                )
        else:
            protects = QLineEdit(str(node.payload.get("protects", "")), dialog)
            approach_section = QLineEdit(str(node.payload.get("approach_section", "")), dialog)
            direction = QComboBox(dialog)
            direction.addItem(self._t("signal_direction.left"), SignalDirection.LEFT.value)
            direction.addItem(self._t("signal_direction.right"), SignalDirection.RIGHT.value)
            current_direction = str(node.payload.get("direction", SignalDirection.RIGHT.value))
            direction_index = direction.findData(current_direction)
            direction.setCurrentIndex(direction_index if direction_index >= 0 else 0)
            aspect = QComboBox(dialog)
            aspect.addItem(self._t("signal_aspect.stop"), SignalAspect.STOP.value)
            aspect.addItem(self._t("signal_aspect.proceed"), SignalAspect.PROCEED.value)
            current_aspect = str(node.payload.get("aspect", SignalAspect.STOP.value))
            aspect_index = aspect.findData(current_aspect)
            aspect.setCurrentIndex(aspect_index if aspect_index >= 0 else 0)
            controls["protects"] = protects
            controls["approach_section"] = approach_section
            controls["direction"] = direction
            controls["aspect"] = aspect
            form.addRow(self._t("field.protects"), protects)
            form.addRow(self._t("field.approach_section"), approach_section)
            form.addRow(self._t("field.direction"), direction)
            form.addRow(self._t("field.aspect"), aspect)
            if self._layout_edit_locked:
                protects.setEnabled(False)
                approach_section.setEnabled(False)
                direction.setEnabled(False)
                aspect.setEnabled(False)
                protects.setToolTip(layout_lock_hint)
                approach_section.setToolTip(layout_lock_hint)
                direction.setToolTip(layout_lock_hint)
                aspect.setToolTip(layout_lock_hint)

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
                        elif key == "occupied":
                            updates[key] = bool(widget.currentData())
                        else:
                            updates[key] = str(widget.currentData() or widget.currentText())
                    elif isinstance(widget, QLineEdit):
                        updates[key] = str(widget.text()).strip()
                if updates:
                    self.update_node_properties(node.element_id, updates)
            except Exception as exc:
                QMessageBox.warning(
                    self,
                    self._t("canvas.dialog.property_update_failed.title"),
                    str(exc),
                )

    def update_node_properties(self, element_id: str, updates: dict[str, Any]) -> None:
        """Apply updated properties to domain model and refresh visuals."""
        element = self.topology.get_element(element_id)
        if element is None:
            raise KeyError(self._t("canvas.error.unknown_element", element_id=element_id))
        track_occupied_before = bool(element.occupied) if isinstance(element, TrackSection) else None
        self._validate_layout_property_updates(element, updates)
        self._validate_runtime_state_updates(element, updates)
        if updates:
            self._push_undo_state()
        emit_topology_change = False

        if isinstance(element, TrackSection):
            if "length" in updates:
                element.length = float(updates["length"])
            next_occupied = bool(element.occupied)
            if "occupied" in updates:
                occupied_value = updates["occupied"]
                if isinstance(occupied_value, str):
                    occupied_token = occupied_value.strip().upper()
                    localized_occupied = self._t("state.occupied").strip().upper()
                    next_occupied = occupied_token in {"OCCUPIED", localized_occupied}
                else:
                    next_occupied = bool(occupied_value)

                if self._layout_edit_locked:
                    self._reconcile_manual_free_section(
                        section_id=element.id,
                        occupied_before=bool(track_occupied_before),
                        occupied_after=next_occupied,
                    )
                else:
                    element.occupied = next_occupied
            if "locked_by" in updates and not self._layout_edit_locked:
                locked_by_text = str(updates["locked_by"]).strip()
                element.locked_by = locked_by_text or None
            if (not self._layout_edit_locked) and ("occupied" in updates):
                self._reconcile_manual_free_section(
                    section_id=element.id,
                    occupied_before=bool(track_occupied_before),
                    occupied_after=bool(element.occupied),
                )

        elif isinstance(element, Point):
            target_locked_by = element.locked_by
            if "locked_by" in updates:
                locked_by_text = str(updates["locked_by"]).strip()
                target_locked_by = locked_by_text or None
            if "position" in updates:
                requested_position = PointPosition(str(updates["position"]))
                if target_locked_by and requested_position != element.position:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.point_locked_by",
                            point_id=element.id,
                            locked_by=target_locked_by,
                        )
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
            if "locked_by" in updates and not self._layout_edit_locked:
                element.locked_by = target_locked_by

        elif isinstance(element, Signal):
            if "protects" in updates:
                new_protects = str(updates["protects"]).strip()
                if new_protects and new_protects not in self.topology.graph.nodes:
                    raise ValueError(
                        self._t("canvas.error.protects_invalid")
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
                            self._t("canvas.error.approach_section_invalid")
                        )
                    if not self.topology.is_signal_back_side_node(element_id, approach_section):
                        raise ValueError(
                            self._t("canvas.error.approach_section_rear_side")
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

    def _reconcile_manual_free_section(
        self,
        section_id: str,
        occupied_before: bool,
        occupied_after: bool,
    ) -> None:
        if occupied_before == occupied_after:
            return

        removed_train_ids: list[str] = []
        if callable(self._manual_override_handler):
            try:
                removed_train_ids = list(
                    self._manual_override_handler(section_id, occupied_before, occupied_after)
                )
            except Exception as exc:
                message = str(exc)
                if "Sequence locking violation" in message:
                    QMessageBox.warning(
                        self,
                        self._t("dialog.property_update_failed.title"),
                        message,
                    )
                removed_train_ids = []
        elif self._simulation is not None:
            command_fn = getattr(self._simulation, "apply_runtime_command", None)
            if callable(command_fn):
                try:
                    command_result = command_fn(
                        "set_section_occupied",
                        {
                            "section_id": section_id,
                            "occupied": occupied_after,
                        },
                    )
                    if isinstance(command_result, dict):
                        removed_train_ids = list(command_result.get("removed_trains", []))
                except Exception as exc:
                    message = str(exc)
                    if "Sequence locking violation" in message:
                        QMessageBox.warning(
                            self,
                            self._t("dialog.property_update_failed.title"),
                            message,
                        )
                    removed_train_ids = []
            else:
                reconcile_fn = getattr(self._simulation, "reconcile_manual_free_section", None)
                if callable(reconcile_fn) and not occupied_after:
                    try:
                        removed_train_ids = list(reconcile_fn(section_id))
                    except Exception:
                        removed_train_ids = []

        if removed_train_ids and not occupied_after:
            joined = ", ".join(sorted(removed_train_ids))
            self.editor_message.emit(
                self._t(
                    "canvas.message.manual_free_removed_trains",
                    section_id=section_id,
                    train_ids=joined,
                )
            )

    def _validate_layout_property_updates(self, element: Any, updates: dict[str, Any]) -> None:
        if not self._layout_edit_locked or not updates:
            return
        reason = self._layout_edit_lock_reason or self._t("main.lock.layout_edit_reason")

        if isinstance(element, TrackSection) and "length" in updates:
            if float(updates["length"]) != float(element.length):
                raise RuntimeError(
                    self._t(
                        "canvas.error.cannot_edit_length_locked",
                        reason=reason,
                    )
                )

        if isinstance(element, Point):
            if "symbol_orientation" in updates:
                incoming_orientation = PointSymbolOrientation(str(updates["symbol_orientation"]))
                if incoming_orientation != element.symbol_orientation:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_point_symbol_locked",
                            reason=reason,
                        )
                    )
            if "normal_target" in updates:
                incoming_normal = str(updates["normal_target"]).strip()
                current_normal = element.facing_connections.get(PointPosition.NORMAL, "")
                if incoming_normal != current_normal:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_point_targets_locked",
                            reason=reason,
                        )
                    )
            if "reverse_target" in updates:
                incoming_reverse = str(updates["reverse_target"]).strip()
                current_reverse = element.facing_connections.get(PointPosition.REVERSE, "")
                if incoming_reverse != current_reverse:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_point_targets_locked",
                            reason=reason,
                        )
                    )

        if isinstance(element, Signal):
            if "protects" in updates:
                incoming_protects = str(updates["protects"]).strip()
                if incoming_protects != element.protects:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_signal_protection_locked",
                            reason=reason,
                        )
                    )
            if "approach_section" in updates:
                incoming_approach = str(updates["approach_section"]).strip()
                if incoming_approach != element.approach_section:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_signal_approach_locked",
                            reason=reason,
                        )
                    )
            if "direction" in updates:
                incoming_direction = SignalDirection(str(updates["direction"]))
                if incoming_direction != element.direction:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_signal_direction_locked",
                            reason=reason,
                        )
                    )

    def _validate_runtime_state_updates(self, element: Any, updates: dict[str, Any]) -> None:
        if not updates:
            return
        runtime_reason = self._runtime_edit_lock_reason or self._t("canvas.lock.runtime_lock_active")
        layout_reason = self._layout_edit_lock_reason or self._t("main.lock.layout_edit_reason")

        if isinstance(element, TrackSection):
            if "occupied" in updates and self._runtime_edit_locked:
                incoming = updates["occupied"]
                if isinstance(incoming, str):
                    incoming_token = incoming.strip().upper()
                    localized_occupied = self._t("state.occupied").strip().upper()
                    next_occupied = incoming_token in {"OCCUPIED", localized_occupied}
                else:
                    next_occupied = bool(incoming)
                if next_occupied != bool(element.occupied):
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_occupied_runtime",
                            reason=runtime_reason,
                        )
                    )
            if "locked_by" in updates:
                next_locked_by = str(updates["locked_by"]).strip() or None
                if next_locked_by != element.locked_by and (
                    self._runtime_edit_locked or self._layout_edit_locked
                ):
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_locked_by_runtime",
                            reason=(runtime_reason if self._runtime_edit_locked else layout_reason),
                        )
                    )

        if isinstance(element, Point) and "locked_by" in updates:
            next_locked_by = str(updates["locked_by"]).strip() or None
            if next_locked_by != element.locked_by and (
                self._runtime_edit_locked or self._layout_edit_locked
            ):
                raise RuntimeError(
                    self._t(
                        "canvas.error.cannot_edit_locked_by_runtime",
                        reason=(runtime_reason if self._runtime_edit_locked else layout_reason),
                    )
                )

        if isinstance(element, Signal) and self._layout_edit_locked:
            if "aspect" in updates:
                next_aspect = SignalAspect(str(updates["aspect"]))
                if next_aspect != element.aspect:
                    raise RuntimeError(
                        f"Manual signal aspect editing is blocked outside Design Layout workspace ({layout_reason})."
                    )
            if "route_id" in updates:
                next_route_id = str(updates["route_id"]).strip() or None
                if next_route_id != element.route_id:
                    raise RuntimeError(
                        f"Manual signal route editing is blocked outside Design Layout workspace ({layout_reason})."
                    )

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

    def _node_scene_anchor(self, node_id: str) -> QPointF | None:
        node = self.nodes.get(node_id)
        if node is None:
            return None
        center = node.sceneBoundingRect().center()
        return QPointF(
            center.x() - (TrainSpriteItem.WIDTH / 2.0),
            center.y() - (TrainSpriteItem.HEIGHT / 2.0) - 3.0,
        )

    def _clear_train_visuals(self) -> None:
        for train_id in list(self._train_items):
            self._remove_train_sprite(train_id)
        for animation in self._train_animations.values():
            animation.stop()
        self._train_animations.clear()
        self._train_last_sections.clear()

    def _remove_train_sprite(self, train_id: str) -> None:
        animation = self._train_animations.pop(train_id, None)
        if animation is not None:
            animation.stop()
        sprite = self._train_items.pop(train_id, None)
        if sprite is not None:
            self.scene_ref.removeItem(sprite)
        self._train_last_sections.pop(train_id, None)

    def _animate_train_item(self, train_id: str, sprite: TrainSpriteItem, target_pos: QPointF) -> None:
        duration_ms = max(0, int(self._train_animation_duration_ms))
        if duration_ms <= 0:
            sprite.setPos(target_pos)
            self._train_animations.pop(train_id, None)
            return

        active_animation = self._train_animations.pop(train_id, None)
        if active_animation is not None:
            active_animation.stop()

        animation = QPropertyAnimation(sprite, b"pos", self)
        animation.setDuration(duration_ms)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.setStartValue(QPointF(sprite.pos()))
        animation.setEndValue(target_pos)
        self._train_animations[train_id] = animation
        animation.finished.connect(lambda tid=train_id: self._train_animations.pop(tid, None))
        animation.start()

    def _is_train_renderable(self, train: Any) -> bool:
        current_section = str(getattr(train, "current_section", "")).strip()
        if not current_section or current_section not in self.nodes:
            return False
        section_element = self.topology.get_element(current_section)
        if isinstance(section_element, TrackSection):
            # If a section is no longer occupied, hide the train sprite as requested.
            return bool(section_element.occupied)
        return True

    def _sync_train_visuals(self) -> None:
        if self._simulation is None:
            self._clear_train_visuals()
            return
        trains = getattr(self._simulation, "trains", {}) or {}
        visible_trains = {
            train_id: train
            for train_id, train in trains.items()
            if self._is_train_renderable(train)
        }
        active_ids = set(visible_trains.keys())

        for train_id in list(self._train_items):
            if train_id in active_ids:
                continue
            self._remove_train_sprite(train_id)

        for train_id, train in visible_trains.items():
            current_section = getattr(train, "current_section", "")
            anchor = self._node_scene_anchor(current_section)
            if anchor is None:
                continue

            sprite = self._train_items.get(train_id)
            if sprite is None:
                sprite = TrainSpriteItem(train_id)
                self.scene_ref.addItem(sprite)
                sprite.setPos(anchor)
                self._train_items[train_id] = sprite

            previous_section = self._train_last_sections.get(train_id)
            previous_anchor = self._node_scene_anchor(previous_section) if previous_section else None
            if previous_anchor is not None and abs(anchor.x() - previous_anchor.x()) > 1.0:
                sprite.set_facing_left(anchor.x() < previous_anchor.x())

            if previous_section != current_section:
                self._animate_train_item(train_id, sprite, anchor)
            elif sprite.pos() != anchor and train_id not in self._train_animations:
                sprite.setPos(anchor)

            self._train_last_sections[train_id] = current_section

    def refresh_visual_state(self) -> None:
        """Refresh node colors and labels from topology state."""
        for element_id, node in self.nodes.items():
            node.payload = self._element_payload(element_id)
            node.update()
        for edge in self.edges:
            edge.update_geometry()
        self._sync_train_visuals()

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
        self._clear_train_visuals()
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
        self._apply_layout_edit_flags()

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

