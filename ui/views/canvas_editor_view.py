"""Interactive drag-and-drop canvas for topology editing."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict
from math import atan2, cos, hypot, sin
from typing import Any

from PyQt6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
)
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsObject,
    QGraphicsProxyWidget,
    QGraphicsRectItem,
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
    DisplayLabel,
    DisplayLine,
    Point,
    PointPosition,
    PointSymbolOrientation,
    Signal,
    SignalAspect,
    SignalDirection,
    TrackSection,
    normalize_signal_aspect,
)
from core.domain.model.topology import RailwayTopology
from ui.i18n import UITranslator
from ui.views.canvas_view_helpers import (
    connection_pairs,
    is_train_renderable,
    node_scene_anchor,
    resolve_connection_direction,
)
from ui.views.components_palette_view import (
    PaletteListWidget,
    combo_color_value,
    create_color_combo,
)

POINT_SYMBOL_CHOICES: tuple[tuple[str, PointSymbolOrientation], ...] = (
    ("1", PointSymbolOrientation.RIGHT),
    ("2", PointSymbolOrientation.DOWN),
    ("3", PointSymbolOrientation.LEFT),
    ("4", PointSymbolOrientation.UP),
)
ANNOTATION_LABEL_NODE_TYPE = "AnnotationLabel"
ANNOTATION_LINE_TYPE = "AnnotationLine"
ANNOTATION_TOOL_TEXT = "TEXT"
ANNOTATION_TOOL_LINE = "LINE"


class NodeItem(QGraphicsObject):
    """Visual node for a track section, point, or signal."""

    WIDTH = 96.0
    HEIGHT = 56.0

    def __init__(self, element_id: str, element_type: str, payload: dict[str, Any]) -> None:
        super().__init__()
        self.element_id = element_id
        self.element_type = element_type
        self.payload = payload
        self.editor: CanvasEditor | None = None
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def boundingRect(self) -> QRectF:
        if self.element_type == ANNOTATION_LABEL_NODE_TYPE:
            return QRectF(
                0.0,
                0.0,
                max(40.0, float(self.payload.get("width", self.WIDTH))),
                max(24.0, float(self.payload.get("height", self.HEIGHT))),
            )
        return QRectF(0.0, 0.0, self.WIDTH, self.HEIGHT)

    def paint(self, painter: QPainter, _option: Any, _widget: Any = None) -> None:
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            rect = self.boundingRect().adjusted(0.5, 0.5, -0.5, -0.5)
            if self.element_type not in {"Point", ANNOTATION_LABEL_NODE_TYPE}:
                border_pen = QPen(QColor("#111111"), 2.0 if self.isSelected() else 1.2)
                painter.setPen(border_pen)
                painter.setBrush(QBrush(QColor("#ffffff")))
                painter.drawRect(rect)

            if self.element_type == ANNOTATION_LABEL_NODE_TYPE:
                self._paint_label(painter, rect)
            elif self.element_type in {"TrackSection", "ApproachSection"}:
                self._paint_section(painter, rect)
            elif self.element_type == "Point":
                self._paint_point(painter, rect)
            else:
                self._paint_signal(painter, rect)

            self._paint_state_marker(painter, rect)
            self._paint_route_highlight(painter)
        finally:
            painter.restore()

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
        text_top = panel.center().y() + 1.0 if branch_y < 0 else panel.top() + 1.0
        text_rect = QRectF(
            panel.left() + 2.0,
            text_top,
            panel.width() - 4.0,
            panel.height() / 2.0 - 3.0,
        )
        painter.setPen(QPen(QColor("#111111"), 1.1))
        painter.save()
        font = painter.font()
        font.setPointSizeF(self._fit_text_point_size(font, label, text_rect))
        painter.setFont(font)
        painter.drawText(
            text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter, label
        )
        painter.restore()

    @staticmethod
    def _fit_text_point_size(font: QFont, text: str, rect: QRectF) -> float:
        point_size = max(5.5, font.pointSizeF() if font.pointSizeF() > 0 else 8.0)
        while point_size > 5.5:
            font.setPointSizeF(point_size)
            metrics = QFontMetricsF(font)
            if metrics.horizontalAdvance(text) <= rect.width() - 2.0:
                return point_size
            point_size -= 0.5
        return point_size

    def _paint_signal(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setPen(QPen(QColor("#111111"), 1.2))
        outer = rect.adjusted(0.8, 0.8, -0.8, -0.8)
        painter.drawRect(outer)

        split_y = outer.bottom() - max(24.0, outer.height() * 0.28)
        painter.drawLine(
            QPointF(outer.left() + 1.5, split_y), QPointF(outer.right() - 1.5, split_y)
        )

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
        aspect = normalize_signal_aspect(self.payload.get("aspect", SignalAspect.RED.value))

        arm_y = top_rect.top() + top_rect.height() * 0.35
        arm_length = max(16.0, top_rect.width() * 0.32)
        head_radius = 4.6
        if face_left:
            head_center_x = mast_x - arm_length
            stop_bar_x = head_center_x - 24.0
        else:
            head_center_x = mast_x + arm_length
            stop_bar_x = head_center_x + 24.0

        painter.drawLine(QPointF(mast_x, arm_y), QPointF(head_center_x, arm_y))
        lamp_spacing = 10.5
        lamp_centers = [
            head_center_x - lamp_spacing,
            head_center_x,
            head_center_x + lamp_spacing,
        ]
        lamp_colors = [QColor("#151b20"), QColor("#151b20"), QColor("#151b20")]
        if aspect == SignalAspect.RED:
            lamp_colors[0] = QColor("#d71920")
        elif aspect == SignalAspect.YELLOW:
            lamp_colors[1] = QColor("#f0c419")
        elif aspect == SignalAspect.GREEN:
            lamp_colors[1] = QColor("#16a34a")
        elif aspect == SignalAspect.BLUE:
            lamp_colors[2] = QColor("#2f80ed")
        elif aspect == SignalAspect.YELLOW_BLUE:
            lamp_colors[1] = QColor("#f0c419")
            lamp_colors[2] = QColor("#2f80ed")
        elif aspect == SignalAspect.GREEN_BLUE:
            lamp_colors[1] = QColor("#16a34a")
            lamp_colors[2] = QColor("#2f80ed")

        painter.setPen(QPen(QColor("#111111"), 1.0))
        for center_x, color in zip(lamp_centers, lamp_colors, strict=True):
            painter.setBrush(QBrush(color))
            painter.drawEllipse(
                QRectF(
                    center_x - head_radius,
                    arm_y - head_radius,
                    head_radius * 2.0,
                    head_radius * 2.0,
                )
            )
        painter.setPen(QPen(QColor("#111111"), 1.2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(
            QPointF(stop_bar_x, arm_y - 6.0),
            QPointF(stop_bar_x, arm_y + 6.0),
        )

        label_rect = QRectF(
            outer.left() + 3.0, split_y + 2.0, outer.width() - 6.0, outer.bottom() - split_y - 3.0
        )
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, self.element_id)
        painter.restore()

    def _paint_label(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        text = str(self.payload.get("text", "LABEL")) or "LABEL"
        font = painter.font()
        font.setPointSizeF(max(6.0, float(self.payload.get("font_size", 18.0))))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QPen(QColor(str(self.payload.get("color", "#111111"))), 1.0))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
        if self.isSelected():
            painter.setPen(QPen(QColor("#2563eb"), 1.2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect.adjusted(1.0, 1.0, -1.0, -1.0))
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
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and self.editor is not None
        ):
            self.editor.handle_node_moved(self)
        return super().itemChange(change, value)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.editor is not None:
            self.editor.begin_node_drag(self)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        if self.editor is not None:
            self.editor.finish_node_drag()

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.editor is not None:
            if self.element_type == ANNOTATION_LABEL_NODE_TYPE:
                self.editor.start_inline_label_edit(self)
            else:
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
        if distance > 12.0:
            inset = min(4.0, distance * 0.2)
            end = QPointF(end.x() - (dx / distance) * inset, end.y() - (dy / distance) * inset)
        self.setLine(start.x(), start.y(), end.x(), end.y())

    @staticmethod
    def _edge_anchor(node: NodeItem, toward: QPointF) -> QPointF:
        rect = node.sceneBoundingRect()
        if node.element_type == "Point":
            panel_side = max(26.0, min(rect.width(), rect.height()) - 8.0)
            rect = QRectF(
                rect.center().x() - panel_side / 2.0,
                rect.center().y() - panel_side / 2.0,
                panel_side,
                panel_side,
            )
        center = rect.center()
        dx = toward.x() - center.x()
        dy = toward.y() - center.y()
        inset = 2.5
        if abs(dx) >= abs(dy):
            return QPointF(
                (rect.right() - inset) if dx >= 0 else (rect.left() + inset),
                center.y(),
            )
        return QPointF(
            center.x(),
            (rect.bottom() - inset) if dy >= 0 else (rect.top() + inset),
        )

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


class AnnotationLineItem(QGraphicsObject):
    """Visual-only arrow line annotation for running-direction notes."""

    HANDLE_RADIUS = 5.5

    def __init__(self, line: DisplayLine) -> None:
        super().__init__()
        self.line = line
        self.editor: CanvasEditor | None = None
        self._drag_handle: str | None = None
        self._drag_line = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setZValue(2.0)

    def boundingRect(self) -> QRectF:
        start = QPointF(*self.line.start)
        end = QPointF(*self.line.end)
        rect = QRectF(start, end).normalized()
        pad = max(self.HANDLE_RADIUS + 4.0, float(self.line.width) + 12.0)
        return rect.adjusted(-pad, -pad, pad, pad)

    def paint(self, painter: QPainter, _option: Any, _widget: Any = None) -> None:
        start = QPointF(*self.line.start)
        end = QPointF(*self.line.end)
        if start == end:
            end = QPointF(start.x() + 1.0, start.y())
        color = QColor(self.line.color or "#111111")
        width = max(0.5, float(self.line.width))

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(color, width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(start, end)

        angle = atan2(end.y() - start.y(), end.x() - start.x())
        arrow_len = max(12.0, width * 5.0)
        arrow_angle = 0.55
        arrow_points = QPolygonF(
            [
                end,
                QPointF(
                    end.x() - arrow_len * cos(angle - arrow_angle),
                    end.y() - arrow_len * sin(angle - arrow_angle),
                ),
                QPointF(
                    end.x() - arrow_len * cos(angle + arrow_angle),
                    end.y() - arrow_len * sin(angle + arrow_angle),
                ),
            ]
        )
        painter.setBrush(QBrush(color))
        painter.drawPolygon(arrow_points)

        if self.isSelected():
            handle_pen = QPen(QColor("#2563eb"), 1.3)
            painter.setPen(handle_pen)
            painter.setBrush(QBrush(QColor("#ffffff")))
            for point in (start, end):
                painter.drawEllipse(
                    QRectF(
                        point.x() - self.HANDLE_RADIUS,
                        point.y() - self.HANDLE_RADIUS,
                        self.HANDLE_RADIUS * 2.0,
                        self.HANDLE_RADIUS * 2.0,
                    )
                )
        painter.restore()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.setSelected(True)
        pos = event.scenePos()
        self._drag_handle = self._hit_handle(pos)
        self._drag_line = self._drag_handle is None
        if self.editor is not None:
            self.editor.begin_annotation_line_drag(self.line.id)
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.editor is None:
            event.ignore()
            return
        if self._drag_handle:
            snapped = self.editor.snap_to_grid(event.scenePos())
            if self._drag_handle == "start":
                self.editor.update_annotation_line_geometry(
                    self.line.id,
                    start=snapped,
                    emit_change=False,
                )
            else:
                self.editor.update_annotation_line_geometry(
                    self.line.id,
                    end=snapped,
                    emit_change=False,
                )
            event.accept()
            return
        if self._drag_line:
            delta = event.scenePos() - event.lastScenePos()
            self.editor.move_annotation_line(self.line.id, delta, emit_change=False)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.editor is not None:
            self.editor.finish_annotation_line_drag(self.line.id)
        self._drag_handle = None
        self._drag_line = False
        event.accept()

    def mouseDoubleClickEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.editor is not None:
            self.editor.edit_annotation_line_properties_dialog(self)
        event.accept()

    def _hit_handle(self, scene_pos: QPointF) -> str | None:
        start = QPointF(*self.line.start)
        end = QPointF(*self.line.end)
        if hypot(scene_pos.x() - start.x(), scene_pos.y() - start.y()) <= self.HANDLE_RADIUS * 1.8:
            return "start"
        if hypot(scene_pos.x() - end.x(), scene_pos.y() - end.y()) <= self.HANDLE_RADIUS * 1.8:
            return "end"
        return None

    def refresh_geometry(self) -> None:
        self.prepareGeometryChange()
        self.update()


class InlineLabelEdit(QLineEdit):
    """Small inline editor used for fast label text editing."""

    canceled = pyqtSignal()

    def keyPressEvent(self, event: Any) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.canceled.emit()
            event.accept()
            return
        super().keyPressEvent(event)


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
    canvas_selection_changed = pyqtSignal()
    topology_changed = pyqtSignal()

    def __init__(
        self,
        parent: Any | None = None,
        translator: UITranslator | None = None,
    ) -> None:
        super().__init__(parent)
        self._translator = translator or UITranslator()
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setCacheMode(QGraphicsView.CacheModeFlag.CacheBackground)
        self.setOptimizationFlag(QGraphicsView.OptimizationFlag.DontSavePainterState, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setRubberBandSelectionMode(Qt.ItemSelectionMode.IntersectsItemShape)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.scene_ref = QGraphicsScene(self)
        self.setScene(self.scene_ref)
        self.scene_ref.setItemIndexMethod(QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.scene_ref.setSceneRect(-3000.0, -1800.0, 6000.0, 3600.0)
        self.scene_ref.selectionChanged.connect(self._on_selection_changed)

        self.topology = RailwayTopology()
        self.nodes: dict[str, NodeItem] = {}
        self.annotation_line_items: dict[str, AnnotationLineItem] = {}
        self.edges: list[EdgeItem] = []
        self._edges_by_node: dict[str, set[EdgeItem]] = {}
        self.signal_links: set[tuple[str, str]] = self.topology.signal_links
        self._counter = {
            "TrackSection": 0,
            "ApproachSection": 0,
            "Point": 0,
            "Signal": 0,
            "Label": 0,
            "Line": 0,
        }

        self._connection_start: NodeItem | None = None
        self._connect_mode = False
        self._connect_source: NodeItem | None = None
        self._temporary_edge: QGraphicsLineItem | None = None
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
        self._pending_node_drag_snapshot: RailwayTopology | None = None
        self._pending_node_drag_positions: dict[str, tuple[float, float]] = {}
        self._pending_annotation_line_snapshot: RailwayTopology | None = None
        self._pending_annotation_line_state: (
            tuple[str, tuple[float, float], tuple[float, float]] | None
        ) = None
        self._runtime_edit_locked = False
        self._runtime_edit_lock_reason = ""
        self._layout_edit_locked = False
        self._layout_edit_lock_reason = ""
        self._runtime_view_state: Any | None = None
        self._manual_override_handler: Callable[[str, bool, bool], list[str]] | None = None
        self._train_items: dict[str, TrainSpriteItem] = {}
        self._train_animations: dict[str, QPropertyAnimation] = {}
        self._train_last_sections: dict[str, str] = {}
        self._train_animation_duration_ms = 420
        self._is_panning = False
        self._pan_last_pos: Any = None
        self._pan_has_moved = False
        self._suppress_context_menu_once = False
        self._edit_dialog_enabled = True
        self._annotation_tool: str = ""
        self._annotation_line_start: QPointF | None = None
        self._annotation_preview_line: QGraphicsLineItem | None = None
        self._annotation_text_start: QPointF | None = None
        self._annotation_text_preview_rect: QGraphicsRectItem | None = None
        self._inline_label_proxy: QGraphicsProxyWidget | None = None
        self._inline_label_editor: InlineLabelEdit | None = None
        self._inline_label_node: NodeItem | None = None
        self._inline_label_original_text = ""

    def _t(self, key: str, **kwargs: object) -> str:
        return self._translator.t(key, **kwargs)

    @staticmethod
    def _is_canvas_pan_request(button: Qt.MouseButton, modifiers: Qt.KeyboardModifier) -> bool:
        return button in {Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton} or (
            button == Qt.MouseButton.LeftButton
            and bool(modifiers & Qt.KeyboardModifier.AltModifier)
        )

    def _begin_canvas_pan(self, view_pos: Any) -> None:
        self._is_panning = True
        self._pan_last_pos = view_pos
        self._pan_has_moved = False
        self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

    def set_translator(self, translator: UITranslator) -> None:
        self._translator = translator
        self.refresh_visual_state()

    def set_edit_dialog_enabled(self, enabled: bool) -> None:
        self._edit_dialog_enabled = bool(enabled)

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
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._annotation_tool
            and not self._layout_edit_locked
        ):
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._annotation_tool == ANNOTATION_TOOL_TEXT:
                self._begin_text_label_drag(scene_pos)
            else:
                self._handle_annotation_tool_click(scene_pos)
            event.accept()
            return

        if (
            self._is_canvas_pan_request(event.button(), event.modifiers())
            and not self._connect_mode
        ):
            scene_pos = self.mapToScene(event.position().toPoint())
            item = self.scene_ref.itemAt(scene_pos, self.transform())
            if (
                self._extract_node_item(item) is None
                and self._extract_annotation_line_item(item) is None
                and not isinstance(item, EdgeItem)
            ):
                self._begin_canvas_pan(event.position().toPoint())
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
                event.modifiers()
                & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
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
        if self._annotation_preview_line is not None and self._annotation_line_start is not None:
            start = self._annotation_line_start
            end = self.snap_to_grid(self.mapToScene(event.position().toPoint()))
            self._annotation_preview_line.setLine(start.x(), start.y(), end.x(), end.y())
            event.accept()
            return
        if (
            self._annotation_text_preview_rect is not None
            and self._annotation_text_start is not None
        ):
            rect = QRectF(
                self._annotation_text_start,
                self.snap_to_grid(self.mapToScene(event.position().toPoint())),
            ).normalized()
            self._annotation_text_preview_rect.setRect(rect)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if self._is_panning and event.button() in {
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.MiddleButton,
            Qt.MouseButton.RightButton,
        }:
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
        if (
            event.button() == Qt.MouseButton.LeftButton
            and self._annotation_tool == ANNOTATION_TOOL_TEXT
            and self._annotation_text_start is not None
        ):
            self._finish_text_label_drag(self.mapToScene(event.position().toPoint()))
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
        source_id, target_id = resolve_connection_direction(
            topology=self.topology,
            source_id=first.element_id,
            target_id=second.element_id,
        )
        self.create_connection(source_id, target_id)

    def contextMenuEvent(self, event: Any) -> None:
        if self._suppress_context_menu_once:
            self._suppress_context_menu_once = False
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        item = self.scene_ref.itemAt(scene_pos, self.transform())
        node = self._extract_node_item(item)
        line = self._extract_annotation_line_item(item)
        edge = item if isinstance(item, EdgeItem) else None

        menu = QMenu(self)
        if node is not None:
            event.accept()
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
                    source_id, target_id = resolve_connection_direction(
                        topology=self.topology,
                        source_id=other_nodes[0].element_id,
                        target_id=node.element_id,
                    )
                    self.create_connection(source_id, target_id)
                except Exception as exc:
                    QMessageBox.warning(
                        self,
                        self._t("canvas.dialog.connection_rejected.title"),
                        str(exc),
                    )
            elif chosen == connect_to_selected_action and len(other_nodes) == 1:
                try:
                    source_id, target_id = resolve_connection_direction(
                        topology=self.topology,
                        source_id=node.element_id,
                        target_id=other_nodes[0].element_id,
                    )
                    self.create_connection(source_id, target_id)
                except Exception as exc:
                    QMessageBox.warning(
                        self,
                        self._t("canvas.dialog.connection_rejected.title"),
                        str(exc),
                    )
            return

        if line is not None:
            event.accept()
            edit_action = menu.addAction(self._t("canvas.menu.edit_properties"))
            delete_action = menu.addAction(self._t("canvas.menu.delete"))
            chosen = menu.exec(event.globalPos())
            if chosen == edit_action:
                self.edit_annotation_line_properties_dialog(line)
            elif chosen == delete_action:
                self.delete_annotation_line(line)
            return

        if edge is not None:
            event.accept()
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
        if event.key() == Qt.Key.Key_Escape and self._annotation_tool:
            self.cancel_annotation_tool()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape and self._connect_source is not None:
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
        if enabled:
            self.cancel_annotation_tool()
        self._connect_mode = bool(enabled)
        self._connect_source = None
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag
            if self._connect_mode
            else QGraphicsView.DragMode.RubberBandDrag
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
        if self._layout_edit_locked:
            self.cancel_annotation_tool()
        if self._layout_edit_locked and self._connect_mode:
            self.set_connect_mode(False)
        accepts_drop = not self._layout_edit_locked
        self.setAcceptDrops(accepts_drop)
        self.viewport().setAcceptDrops(accepts_drop)
        self._apply_layout_edit_flags()

    def begin_text_label_placement(self) -> None:
        """Enter click-to-place mode for text annotation labels."""
        self._ensure_layout_edit_allowed("canvas.action.add_components")
        self.set_connect_mode(False)
        self._set_annotation_tool(ANNOTATION_TOOL_TEXT)
        self.editor_message.emit(self._t("canvas.message.annotation_text_mode"))

    def begin_annotation_line_drawing(self) -> None:
        """Enter click-click drawing mode for direction arrow annotations."""
        self._ensure_layout_edit_allowed("canvas.action.add_components")
        self.set_connect_mode(False)
        self._set_annotation_tool(ANNOTATION_TOOL_LINE)
        self.editor_message.emit(self._t("canvas.message.annotation_line_mode_start"))

    def cancel_annotation_tool(self) -> None:
        if self._annotation_preview_line is not None:
            self.scene_ref.removeItem(self._annotation_preview_line)
            self._annotation_preview_line = None
        if self._annotation_text_preview_rect is not None:
            self.scene_ref.removeItem(self._annotation_text_preview_rect)
            self._annotation_text_preview_rect = None
        self._annotation_tool = ""
        self._annotation_line_start = None
        self._annotation_text_start = None
        if not self._connect_mode:
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def start_inline_label_edit(self, node: NodeItem) -> None:
        """Edit one label directly on the canvas."""
        if self._layout_edit_locked:
            reason = self._layout_edit_lock_reason or self._t("main.lock.layout_edit_reason")
            self.editor_message.emit(
                self._t(
                    "canvas.error.layout_edit_locked",
                    action=self._t("canvas.action.rename_elements"),
                    reason=reason,
                )
            )
            return
        self._finish_inline_label_edit(commit=True)
        if node.element_type != ANNOTATION_LABEL_NODE_TYPE:
            return
        self.scene_ref.clearSelection()
        node.setSelected(True)
        editor = InlineLabelEdit(str(node.payload.get("text", "LABEL")))
        editor.selectAll()
        rect = node.sceneBoundingRect().adjusted(4.0, 10.0, -4.0, -10.0)
        editor.setMinimumWidth(max(80, int(rect.width())))
        editor.setStyleSheet("background: white; border: 1px solid #2563eb; padding: 2px;")
        proxy = self.scene_ref.addWidget(editor)
        proxy.setZValue(20.0)
        proxy.setPos(rect.topLeft())
        proxy.resize(rect.width(), max(24.0, rect.height()))
        self._inline_label_proxy = proxy
        self._inline_label_editor = editor
        self._inline_label_node = node
        self._inline_label_original_text = str(node.payload.get("text", "LABEL"))
        editor.returnPressed.connect(lambda: self._finish_inline_label_edit(commit=True))
        editor.editingFinished.connect(lambda: self._finish_inline_label_edit(commit=True))
        editor.canceled.connect(lambda: self._finish_inline_label_edit(commit=False))
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

    def commit_inline_label_edit(self) -> str | None:
        """Commit any active inline label editor and return its label id."""
        node = self._inline_label_node
        label_id = node.element_id if node is not None else None
        self._finish_inline_label_edit(commit=True)
        return label_id

    def _finish_inline_label_edit(self, *, commit: bool) -> None:
        proxy = self._inline_label_proxy
        node = self._inline_label_node
        if proxy is None:
            return
        editor = self._inline_label_editor or proxy.widget()
        text = str(editor.text()).strip() if isinstance(editor, QLineEdit) else ""
        self._inline_label_proxy = None
        self._inline_label_editor = None
        self._inline_label_node = None
        self.scene_ref.removeItem(proxy)
        if not commit or node is None:
            return
        new_text = text or "LABEL"
        old_text = self._inline_label_original_text or "LABEL"
        if new_text != old_text:
            self.update_node_properties(node.element_id, {"text": new_text})

    def _set_annotation_tool(self, tool: str) -> None:
        self._finish_inline_label_edit(commit=True)
        self.cancel_annotation_tool()
        self._annotation_tool = tool
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def _handle_annotation_tool_click(self, scene_pos: QPointF) -> None:
        scene_pos = self.snap_to_grid(scene_pos)
        if self._annotation_tool != ANNOTATION_TOOL_LINE:
            return
        if self._annotation_line_start is None:
            self._annotation_line_start = scene_pos
            self._annotation_preview_line = QGraphicsLineItem(
                scene_pos.x(),
                scene_pos.y(),
                scene_pos.x(),
                scene_pos.y(),
            )
            self._annotation_preview_line.setPen(
                QPen(QColor("#2563eb"), 1.5, Qt.PenStyle.DashLine)
            )
            self._annotation_preview_line.setZValue(3.0)
            self.scene_ref.addItem(self._annotation_preview_line)
            self.editor_message.emit(self._t("canvas.message.annotation_line_mode_end"))
            return
        start = self._annotation_line_start
        if self._annotation_preview_line is not None:
            self.scene_ref.removeItem(self._annotation_preview_line)
            self._annotation_preview_line = None
        item = self.add_annotation_line(start, end_pos=scene_pos)
        self._select_graphics_item(item)
        self.cancel_annotation_tool()

    def _begin_text_label_drag(self, scene_pos: QPointF) -> None:
        start = self.snap_to_grid(scene_pos)
        self._annotation_text_start = start
        if self._annotation_text_preview_rect is not None:
            self.scene_ref.removeItem(self._annotation_text_preview_rect)
        preview = QGraphicsRectItem(QRectF(start, start))
        preview.setPen(QPen(QColor("#2563eb"), 1.2, Qt.PenStyle.DashLine))
        preview.setBrush(QBrush(QColor(37, 99, 235, 18)))
        preview.setZValue(3.0)
        self.scene_ref.addItem(preview)
        self._annotation_text_preview_rect = preview

    def _finish_text_label_drag(self, scene_pos: QPointF) -> None:
        start = self._annotation_text_start
        if start is None:
            return
        end = self.snap_to_grid(scene_pos)
        rect = QRectF(start, end).normalized()
        if rect.width() < 40.0:
            rect.setWidth(120.0)
        if rect.height() < 24.0:
            rect.setHeight(48.0)
        if self._annotation_text_preview_rect is not None:
            self.scene_ref.removeItem(self._annotation_text_preview_rect)
            self._annotation_text_preview_rect = None
        self._annotation_text_start = None
        node = self.add_text_label(
            rect.topLeft(),
            width=rect.width(),
            height=rect.height(),
        )
        self._select_graphics_item(node)
        self.cancel_annotation_tool()
        self.start_inline_label_edit(node)

    def _select_graphics_item(self, item: QGraphicsItem) -> None:
        self.scene_ref.clearSelection()
        item.setSelected(True)

    def _selected_label_style(self) -> dict[str, Any]:
        for item in self.scene_ref.selectedItems():
            if not isinstance(item, NodeItem) or item.element_type != ANNOTATION_LABEL_NODE_TYPE:
                continue
            label = self.topology.labels.get(item.element_id)
            if label is None:
                continue
            return {
                "font_size": label.font_size,
                "color": label.color,
            }
        return {"font_size": 18.0, "color": "#111111"}

    def is_layout_edit_locked(self) -> bool:
        return self._layout_edit_locked

    def _apply_layout_edit_flags(self) -> None:
        movable = not self._layout_edit_locked
        for node in self.nodes.values():
            node.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, movable)
        for line in self.annotation_line_items.values():
            line.setAcceptedMouseButtons(
                Qt.MouseButton.NoButton if self._layout_edit_locked else Qt.MouseButton.LeftButton
            )

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

    def set_runtime_view_state(self, runtime_view_state: Any | None) -> None:
        """Attach read-only runtime state to render animated train sprites."""
        self._runtime_view_state = runtime_view_state
        if runtime_view_state is None:
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

    def _push_undo_snapshot(self, snapshot: RailwayTopology) -> None:
        """Push a pre-mutation snapshot captured before an interactive drag."""
        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > self._max_undo_depth:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _push_undo_state(self) -> None:
        """Push current state to undo stack and clear redo stack."""
        self._push_undo_snapshot(self._snapshot_topology())

    def begin_node_drag(self, node: NodeItem) -> None:
        """Capture one pre-drag snapshot without committing an undo entry yet."""
        if self._pending_node_drag_snapshot is not None:
            return
        selected_nodes = [
            item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)
        ]
        if node not in selected_nodes:
            selected_nodes.append(node)
        self._pending_node_drag_snapshot = self._snapshot_topology()
        self._pending_node_drag_positions = {
            item.element_id: (item.pos().x(), item.pos().y()) for item in selected_nodes
        }

    def finish_node_drag(self) -> None:
        """Commit one undo entry only if an interactive node drag changed positions."""
        snapshot = self._pending_node_drag_snapshot
        start_positions = self._pending_node_drag_positions
        self._pending_node_drag_snapshot = None
        self._pending_node_drag_positions = {}
        if snapshot is None or not start_positions:
            return
        for element_id, start_position in start_positions.items():
            node = self.nodes.get(element_id)
            if node is None:
                continue
            if (node.pos().x(), node.pos().y()) != start_position:
                self._push_undo_snapshot(snapshot)
                return

    def begin_annotation_line_drag(self, line_id: str) -> None:
        """Capture one pre-drag snapshot for annotation line movement."""
        if self._pending_annotation_line_snapshot is not None:
            return
        line = self.topology.annotation_lines.get(line_id)
        if line is None:
            return
        self._pending_annotation_line_snapshot = self._snapshot_topology()
        self._pending_annotation_line_state = (line_id, tuple(line.start), tuple(line.end))

    def finish_annotation_line_drag(self, line_id: str) -> None:
        """Commit annotation drag once and emit one topology change after release."""
        snapshot = self._pending_annotation_line_snapshot
        state = self._pending_annotation_line_state
        self._pending_annotation_line_snapshot = None
        self._pending_annotation_line_state = None
        if snapshot is None or state is None or state[0] != line_id:
            return
        line = self.topology.annotation_lines.get(line_id)
        if line is None:
            return
        if tuple(line.start) == state[1] and tuple(line.end) == state[2]:
            return
        self._push_undo_snapshot(snapshot)
        self._on_selection_changed()
        self.topology_changed.emit()

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

        self._push_undo_state()
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
            node_type = "SignalLeft" if element.direction == SignalDirection.LEFT else "SignalRight"
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

    def add_text_label(
        self,
        scene_pos: QPointF,
        element_id: str | None = None,
        *,
        width: float = 120.0,
        height: float = 48.0,
    ) -> NodeItem:
        """Create a drawing-only text annotation."""
        self._ensure_layout_edit_allowed("canvas.action.add_components")
        scene_pos = self.snap_to_grid(scene_pos)
        if element_id is None:
            self._counter["Label"] += 1
            element_id = f"LBL{self._counter['Label']}"
        if element_id in self.nodes or self.topology.get_element(element_id):
            raise ValueError(
                self._t(
                    "canvas.error.element_id_exists",
                    element_id=element_id,
                )
            )

        self._push_undo_state()
        style = self._selected_label_style()
        element = DisplayLabel(
            id=element_id,
            font_size=float(style["font_size"]),
            color=str(style["color"]),
            width=max(40.0, float(width)),
            height=max(24.0, float(height)),
        )
        self.topology.add_label(element, position=(scene_pos.x(), scene_pos.y()))
        node = NodeItem(
            element_id,
            ANNOTATION_LABEL_NODE_TYPE,
            self._element_payload(element_id),
        )
        node.setPos(scene_pos)
        self.scene_ref.addItem(node)
        node.editor = self
        self.nodes[element_id] = node
        self.topology_changed.emit()
        return node

    def add_annotation_line(
        self,
        scene_pos: QPointF,
        element_id: str | None = None,
        end_pos: QPointF | None = None,
    ) -> AnnotationLineItem:
        """Create a drawing-only direction arrow annotation."""
        self._ensure_layout_edit_allowed("canvas.action.add_components")
        scene_pos = self.snap_to_grid(scene_pos)
        resolved_end = (
            self.snap_to_grid(end_pos)
            if end_pos is not None
            else QPointF(scene_pos.x() + 120.0, scene_pos.y())
        )
        if element_id is None:
            self._counter["Line"] += 1
            element_id = f"LINE{self._counter['Line']}"
        if (
            element_id in self.nodes
            or element_id in self.annotation_line_items
            or self.topology.get_element(element_id)
        ):
            raise ValueError(
                self._t(
                    "canvas.error.element_id_exists",
                    element_id=element_id,
                )
            )

        self._push_undo_state()
        line = DisplayLine(
            id=element_id,
            start=(scene_pos.x(), scene_pos.y()),
            end=(resolved_end.x(), resolved_end.y()),
        )
        self.topology.add_annotation_line(line)
        item = AnnotationLineItem(line)
        item.editor = self
        self.scene_ref.addItem(item)
        self.annotation_line_items[element_id] = item
        self.topology_changed.emit()
        return item

    def create_connection(self, source_id: str, target_id: str) -> None:
        """Create directed connection between blocks."""
        self._ensure_layout_edit_allowed("canvas.action.create_connections")
        if source_id not in self.nodes or target_id not in self.nodes:
            raise KeyError(self._t("canvas.error.connection_requires_existing_nodes"))
        if source_id == target_id:
            raise ValueError(self._t("canvas.error.cannot_self_connect"))
        if ANNOTATION_LABEL_NODE_TYPE in {
            self.nodes[source_id].element_type,
            self.nodes[target_id].element_type,
        }:
            raise ValueError(self._t("canvas.error.cannot_connect_label"))

        # Guard UI connect flows from accidentally overwriting protects:
        # when user starts from a signal that already protects another node,
        # treat the action as adding an approach link (node -> signal).
        source_signal = self.topology.signals.get(source_id)
        if source_signal is not None and target_id in self.topology.graph.nodes:
            protected = source_signal.protects.strip()
            if protected and protected != target_id:
                source_id, target_id = target_id, source_id

        source = self.nodes.get(source_id)
        target = self.nodes.get(target_id)
        if source is None or target is None:
            raise KeyError(self._t("canvas.error.connection_requires_existing_nodes"))

        if self._is_signal_type_name(source.element_type):
            signal = self.topology.signals.get(source_id)
            if signal is not None and signal.protects == target_id:
                return
        elif self._is_signal_type_name(target.element_type):
            if (source_id, target_id) in self.signal_links:
                return
        elif (source_id, target_id) in self.topology.graph.edges or (
            target_id,
            source_id,
        ) in self.topology.graph.edges:
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
        if old_id in self.annotation_line_items:
            self.rename_annotation_line(old_id, new_id)
            return
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
        elif old_id in self.topology.labels:
            label = self.topology.labels.pop(old_id)
            label.id = new_id
            self.topology.labels[new_id] = label
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
        updated_route_types: dict[str, str] = {}
        for route_key, route_type in self.topology.route_types.items():
            entry_signal_id, separator, exit_signal_id = route_key.partition("->")
            if not separator:
                continue
            if entry_signal_id == old_id:
                entry_signal_id = new_id
            if exit_signal_id == old_id:
                exit_signal_id = new_id
            updated_route_types[f"{entry_signal_id}->{exit_signal_id}"] = route_type
        self.topology.route_types = updated_route_types
        updated_route_signal_aspects: dict[str, SignalAspect] = {}
        for route_key, signal_aspect in self.topology.route_signal_aspects.items():
            entry_signal_id, separator, exit_signal_id = route_key.partition("->")
            if not separator:
                continue
            if entry_signal_id == old_id:
                entry_signal_id = new_id
            if exit_signal_id == old_id:
                exit_signal_id = new_id
            updated_route_signal_aspects[f"{entry_signal_id}->{exit_signal_id}"] = signal_aspect
        self.topology.route_signal_aspects = updated_route_signal_aspects

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

    def rename_annotation_line(self, old_id: str, new_id: str) -> None:
        self._ensure_layout_edit_allowed("canvas.action.rename_elements")
        if old_id not in self.annotation_line_items:
            raise KeyError(self._t("canvas.error.unknown_element", element_id=old_id))
        if (
            new_id in self.nodes
            or new_id in self.annotation_line_items
            or self.topology.get_element(new_id)
        ):
            raise ValueError(
                self._t(
                    "canvas.error.element_id_exists",
                    element_id=new_id,
                )
            )
        self._push_undo_state()
        line = self.topology.annotation_lines.pop(old_id)
        line.id = new_id
        self.topology.annotation_lines[new_id] = line
        item = self.annotation_line_items.pop(old_id)
        self.annotation_line_items[new_id] = item
        item.refresh_geometry()
        self.topology_changed.emit()

    def delete_selected_items(self) -> None:
        selected = list(self.scene_ref.selectedItems())
        edges = [item for item in selected if isinstance(item, EdgeItem)]
        nodes = [item for item in selected if isinstance(item, NodeItem)]
        lines = [item for item in selected if isinstance(item, AnnotationLineItem)]

        if not edges and not nodes and not lines:
            return
        self._ensure_layout_edit_allowed("canvas.action.delete_elements_or_connections")
        self._push_undo_state()

        changed = False
        for line in lines:
            self.delete_annotation_line(line, emit_change=False, record_undo=False)
            changed = True

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
        elif node_id in self.topology.labels:
            self.topology.labels.pop(node_id, None)
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
        self.topology.route_types = {
            route_key: route_type
            for route_key, route_type in self.topology.route_types.items()
            if node_id not in route_key.split("->", 1)
        }
        self.topology.route_signal_aspects = {
            route_key: signal_aspect
            for route_key, signal_aspect in self.topology.route_signal_aspects.items()
            if node_id not in route_key.split("->", 1)
        }

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

    def delete_annotation_line(
        self,
        line_item: AnnotationLineItem,
        emit_change: bool = True,
        record_undo: bool = True,
    ) -> None:
        self._ensure_layout_edit_allowed("canvas.action.delete_elements")
        line_id = line_item.line.id
        if line_id not in self.annotation_line_items:
            return
        if record_undo:
            self._push_undo_state()
        self.scene_ref.removeItem(line_item)
        self.annotation_line_items.pop(line_id, None)
        self.topology.annotation_lines.pop(line_id, None)
        if emit_change:
            self.topology_changed.emit()

    def update_annotation_line_geometry(
        self,
        line_id: str,
        *,
        start: QPointF | None = None,
        end: QPointF | None = None,
        record_undo: bool = False,
        emit_change: bool = True,
    ) -> None:
        line = self.topology.annotation_lines.get(line_id)
        item = self.annotation_line_items.get(line_id)
        if line is None or item is None:
            raise KeyError(self._t("canvas.error.unknown_element", element_id=line_id))
        if record_undo:
            self._push_undo_state()
        if start is not None:
            line.start = (float(start.x()), float(start.y()))
        if end is not None:
            line.end = (float(end.x()), float(end.y()))
        item.refresh_geometry()
        if emit_change:
            self.topology_changed.emit()

    def move_annotation_line(
        self,
        line_id: str,
        delta: QPointF,
        *,
        emit_change: bool = True,
    ) -> None:
        line = self.topology.annotation_lines.get(line_id)
        item = self.annotation_line_items.get(line_id)
        if line is None or item is None:
            raise KeyError(self._t("canvas.error.unknown_element", element_id=line_id))
        start = QPointF(line.start[0] + delta.x(), line.start[1] + delta.y())
        snapped_start = self.snap_to_grid(start)
        snap_delta = snapped_start - QPointF(*line.start)
        line.start = (line.start[0] + snap_delta.x(), line.start[1] + snap_delta.y())
        line.end = (line.end[0] + snap_delta.x(), line.end[1] + snap_delta.y())
        item.refresh_geometry()
        if emit_change:
            self.topology_changed.emit()

    def edit_annotation_line_properties_dialog(self, line_item: AnnotationLineItem) -> None:
        """Open a double-click edit dialog for a visual annotation line."""
        if not self._edit_dialog_enabled:
            return
        line = line_item.line
        dialog = QDialog(self)
        dialog.setWindowTitle(self._t("canvas.dialog.edit_element.title", element_id=line.id))
        form = QFormLayout(dialog)

        id_input = QLineEdit(line.id, dialog)
        color_input = create_color_combo(line.color)
        width_input = QDoubleSpinBox(dialog)
        width_input.setRange(1.0, 8.0)
        width_input.setSingleStep(0.5)
        width_input.setValue(float(line.width))
        start_x = QDoubleSpinBox(dialog)
        start_y = QDoubleSpinBox(dialog)
        end_x = QDoubleSpinBox(dialog)
        end_y = QDoubleSpinBox(dialog)
        for widget in (start_x, start_y, end_x, end_y):
            widget.setRange(-100000.0, 100000.0)
            widget.setDecimals(1)
        start_x.setValue(float(line.start[0]))
        start_y.setValue(float(line.start[1]))
        end_x.setValue(float(line.end[0]))
        end_y.setValue(float(line.end[1]))

        form.addRow(self._t("field.id"), id_input)
        form.addRow(self._t("field.color"), color_input)
        form.addRow(self._t("field.width"), width_input)
        form.addRow(self._t("field.start_x"), start_x)
        form.addRow(self._t("field.start_y"), start_y)
        form.addRow(self._t("field.end_x"), end_x)
        form.addRow(self._t("field.end_y"), end_y)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            current_id = line.id
            new_id = str(id_input.text()).strip()
            if new_id and new_id != line.id:
                self.rename_annotation_line(line.id, new_id)
                current_id = new_id
            self.update_node_properties(
                current_id,
                {
                    "color": combo_color_value(color_input),
                    "width": float(width_input.value()),
                    "start_x": float(start_x.value()),
                    "start_y": float(start_y.value()),
                    "end_x": float(end_x.value()),
                    "end_y": float(end_y.value()),
                },
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                self._t("canvas.dialog.property_update_failed.title"),
                str(exc),
            )

    def edit_node_properties_dialog(self, node: NodeItem) -> None:
        """Open a double-click edit dialog for a node."""
        if not self._edit_dialog_enabled:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(
            self._t("canvas.dialog.edit_element.title", element_id=node.element_id)
        )
        form = QFormLayout(dialog)
        layout_lock_hint = self._layout_edit_lock_reason or self._t(
            "canvas.lock.layout_editing_locked"
        )

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
            controls["length"] = length
            controls["occupied"] = occupied
            form.addRow(self._t("field.length"), length)
            form.addRow(self._t("field.state"), occupied)
            if self._layout_edit_locked:
                length.setEnabled(False)
                length.setToolTip(layout_lock_hint)
            if self._runtime_edit_locked:
                occupied.setEnabled(False)
                hint = self._runtime_edit_lock_reason or self._t("canvas.lock.runtime_lock_active")
                occupied.setToolTip(hint)
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
            controls["position"] = position
            controls["symbol_orientation"] = symbol_orientation
            controls["normal_target"] = normal
            controls["reverse_target"] = reverse
            form.addRow(self._t("field.position"), position)
            form.addRow(self._t("field.symbol"), symbol_orientation)
            form.addRow(self._t("field.normal_to"), normal)
            form.addRow(self._t("field.reverse_to"), reverse)
            if self._layout_edit_locked:
                symbol_orientation.setEnabled(False)
                normal.setEnabled(False)
                reverse.setEnabled(False)
                symbol_orientation.setToolTip(layout_lock_hint)
                normal.setToolTip(layout_lock_hint)
                reverse.setToolTip(layout_lock_hint)
        elif node.element_type == ANNOTATION_LABEL_NODE_TYPE:
            text = QLineEdit(str(node.payload.get("text", "LABEL")), dialog)
            font_size = QDoubleSpinBox(dialog)
            font_size.setRange(6.0, 96.0)
            font_size.setValue(float(node.payload.get("font_size", 18.0)))
            color = create_color_combo(str(node.payload.get("color", "#111111")))
            width = QDoubleSpinBox(dialog)
            height = QDoubleSpinBox(dialog)
            for widget in (width, height):
                widget.setRange(40.0, 2000.0)
                widget.setDecimals(1)
                widget.setSingleStep(10.0)
            width.setValue(float(node.payload.get("width", 120.0)))
            height.setValue(float(node.payload.get("height", 48.0)))
            controls["text"] = text
            controls["font_size"] = font_size
            controls["color"] = color
            controls["width"] = width
            controls["height"] = height
            form.addRow(self._t("field.text"), text)
            form.addRow(self._t("field.font_size"), font_size)
            form.addRow(self._t("field.color"), color)
            form.addRow(self._t("field.width"), width)
            form.addRow(self._t("field.height"), height)
            if self._layout_edit_locked:
                text.setEnabled(False)
                font_size.setEnabled(False)
                color.setEnabled(False)
                width.setEnabled(False)
                height.setEnabled(False)
                text.setToolTip(layout_lock_hint)
                font_size.setToolTip(layout_lock_hint)
                color.setToolTip(layout_lock_hint)
                width.setToolTip(layout_lock_hint)
                height.setToolTip(layout_lock_hint)
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
            for signal_aspect in (
                SignalAspect.RED,
                SignalAspect.YELLOW,
                SignalAspect.GREEN,
                SignalAspect.BLUE,
            ):
                aspect.addItem(
                    self._t(f"signal_aspect.{signal_aspect.value.lower()}"),
                    signal_aspect.value,
                )
            current_aspect = normalize_signal_aspect(
                node.payload.get("aspect", SignalAspect.RED.value)
            ).value
            aspect_index = aspect.findData(current_aspect)
            aspect.setCurrentIndex(aspect_index if aspect_index >= 0 else 0)
            blocking = QCheckBox(dialog)
            blocking.setChecked(bool(node.payload.get("is_blocking", False)))
            reverse_signal = QCheckBox(dialog)
            reverse_signal.setChecked(bool(node.payload.get("is_reverse_signal", False)))
            controls["protects"] = protects
            controls["approach_section"] = approach_section
            controls["direction"] = direction
            controls["aspect"] = aspect
            controls["is_blocking"] = blocking
            controls["is_reverse_signal"] = reverse_signal
            form.addRow(self._t("field.protects"), protects)
            form.addRow(self._t("field.approach_section"), approach_section)
            form.addRow(self._t("field.direction"), direction)
            form.addRow(self._t("field.aspect"), aspect)
            form.addRow(self._t("field.blocking_signal"), blocking)
            form.addRow(self._t("field.reverse_signal"), reverse_signal)

            def sync_signal_route_controls() -> None:
                is_blocking = blocking.isChecked()
                if is_blocking:
                    red_index = aspect.findData(SignalAspect.RED.value)
                    aspect.setCurrentIndex(red_index if red_index >= 0 else 0)
                aspect.setEnabled((not is_blocking) and (not self._layout_edit_locked))

            blocking.toggled.connect(sync_signal_route_controls)
            sync_signal_route_controls()
            if self._layout_edit_locked:
                protects.setEnabled(False)
                approach_section.setEnabled(False)
                direction.setEnabled(False)
                aspect.setEnabled(False)
                blocking.setEnabled(False)
                reverse_signal.setEnabled(False)
                protects.setToolTip(layout_lock_hint)
                approach_section.setToolTip(layout_lock_hint)
                direction.setToolTip(layout_lock_hint)
                aspect.setToolTip(layout_lock_hint)
                blocking.setToolTip(layout_lock_hint)
                reverse_signal.setToolTip(layout_lock_hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            parent=dialog,
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
                        if key == "color":
                            updates[key] = combo_color_value(widget)
                        elif key == "symbol_orientation":
                            symbol_orientation = widget.currentData()
                            updates[key] = str(symbol_orientation or widget.currentText())
                        elif key == "occupied":
                            updates[key] = bool(widget.currentData())
                        else:
                            updates[key] = str(widget.currentData() or widget.currentText())
                    elif isinstance(widget, QCheckBox):
                        updates[key] = bool(widget.isChecked())
                    elif isinstance(widget, QLineEdit):
                        updates[key] = str(widget.text()).strip()
                if "is_blocking" in updates and updates["is_blocking"]:
                    updates["aspect"] = SignalAspect.RED.value
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
        track_occupied_before = (
            bool(element.occupied) if isinstance(element, TrackSection) else None
        )
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
                    raise ValueError(self._t("canvas.error.protects_invalid"))
                element.protects = new_protects
                self.topology.sync_signal_virtual_routes()
                self._rebuild_edge_items()
                emit_topology_change = True
            if "approach_section" in updates:
                approach_section = str(updates["approach_section"]).strip()
                if approach_section:
                    approach_element = self.topology.get_element(approach_section)
                    if not isinstance(approach_element, ApproachSection):
                        raise ValueError(self._t("canvas.error.approach_section_invalid"))
                    if not self.topology.is_signal_back_side_node(element_id, approach_section):
                        raise ValueError(self._t("canvas.error.approach_section_rear_side"))
                element.approach_section = approach_section
            if "direction" in updates:
                element.direction = SignalDirection(str(updates["direction"]))
                node = self.nodes.get(element_id)
                if node is not None:
                    node.element_type = (
                        "SignalLeft" if element.direction == SignalDirection.LEFT else "SignalRight"
                    )
            if "is_blocking" in updates:
                element.is_blocking = bool(updates["is_blocking"])
                if element.is_blocking:
                    element.aspect = SignalAspect.RED
                emit_topology_change = True
            if "is_reverse_signal" in updates:
                element.is_reverse_signal = bool(updates["is_reverse_signal"])
                emit_topology_change = True
            if "aspect" in updates:
                element.aspect = (
                    SignalAspect.RED
                    if element.is_blocking
                    else normalize_signal_aspect(str(updates["aspect"]))
                )
        elif isinstance(element, DisplayLabel):
            node = self.nodes.get(element_id)
            if node is not None and ("width" in updates or "height" in updates):
                node.prepareGeometryChange()
            if "text" in updates:
                element.text = str(updates["text"]).strip() or "LABEL"
            if "font_size" in updates:
                element.font_size = max(6.0, float(updates["font_size"]))
            if "color" in updates:
                element.color = str(updates["color"]).strip() or "#111111"
            if "width" in updates:
                element.width = max(40.0, float(updates["width"]))
            if "height" in updates:
                element.height = max(24.0, float(updates["height"]))
            emit_topology_change = True
        elif isinstance(element, DisplayLine):
            start_x = float(updates.get("start_x", element.start[0]))
            start_y = float(updates.get("start_y", element.start[1]))
            end_x = float(updates.get("end_x", element.end[0]))
            end_y = float(updates.get("end_y", element.end[1]))
            element.start = (start_x, start_y)
            element.end = (end_x, end_y)
            if "color" in updates:
                element.color = str(updates["color"]).strip() or "#111111"
            if "width" in updates:
                element.width = max(0.5, float(updates["width"]))
            line_item = self.annotation_line_items.get(element_id)
            if line_item is not None:
                line_item.refresh_geometry()
            emit_topology_change = True

        self.refresh_element_visuals({element_id})
        self._on_selection_changed()
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

        if (
            isinstance(element, TrackSection)
            and "length" in updates
            and float(updates["length"]) != float(element.length)
        ):
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
            static_fields = {
                "is_blocking",
                "is_reverse_signal",
            }
            for field_name in static_fields.intersection(updates):
                current_value = getattr(element, field_name)
                incoming_value = updates[field_name]
                if isinstance(current_value, bool):
                    changed = bool(incoming_value) != current_value
                else:
                    changed = str(incoming_value).strip() != str(current_value).strip()
                if changed:
                    raise RuntimeError(
                        self._t(
                            "canvas.error.cannot_edit_signal_direction_locked",
                            reason=reason,
                        )
                    )

    def _validate_runtime_state_updates(self, element: Any, updates: dict[str, Any]) -> None:
        if not updates:
            return
        runtime_reason = self._runtime_edit_lock_reason or self._t(
            "canvas.lock.runtime_lock_active"
        )
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
                next_aspect = normalize_signal_aspect(str(updates["aspect"]))
                if next_aspect != element.aspect:
                    raise RuntimeError(
                        "Manual signal aspect editing is blocked outside "
                        f"Design Layout workspace ({layout_reason})."
                    )
            if "route_id" in updates:
                next_route_id = str(updates["route_id"]).strip() or None
                if next_route_id != element.route_id:
                    raise RuntimeError(
                        "Manual signal route editing is blocked outside "
                        f"Design Layout workspace ({layout_reason})."
                    )

    def handle_node_moved(self, node: NodeItem) -> None:
        """Persist node position and update connected edges."""
        self.topology.update_position(node.element_id, (node.pos().x(), node.pos().y()))
        for edge in self._connected_edges_for_node(node.element_id):
            edge.update_geometry()

    def _on_selection_changed(self) -> None:
        self.canvas_selection_changed.emit()
        selected_items = [
            item for item in self.scene_ref.selectedItems() if isinstance(item, NodeItem)
        ]
        selected_lines = [
            item for item in self.scene_ref.selectedItems() if isinstance(item, AnnotationLineItem)
        ]
        if selected_lines:
            line = selected_lines[0].line
            self.node_selected.emit(
                {
                    "id": line.id,
                    "type": ANNOTATION_LINE_TYPE,
                    "properties": {
                        "start_x": line.start[0],
                        "start_y": line.start[1],
                        "end_x": line.end[0],
                        "end_y": line.end[1],
                        "color": line.color,
                        "width": line.width,
                    },
                    "signal_ids": sorted(self.topology.signals),
                }
            )
            return
        if not selected_items:
            self.node_selected.emit(None)
            return
        node = selected_items[0]
        self.node_selected.emit(
            {
                "id": node.element_id,
                "type": node.element_type,
                "properties": dict(node.payload),
                "signal_ids": sorted(self.topology.signals),
            }
        )

    def _node_at_view_pos(self, pos: Any) -> NodeItem | None:
        scene_pos = self.mapToScene(pos)
        item = self.scene_ref.itemAt(scene_pos, self.transform())
        return self._extract_node_item(item)

    @staticmethod
    def _extract_node_item(item: Any) -> NodeItem | None:
        while item is not None and not isinstance(item, NodeItem):
            item = item.parentItem()
        return item if isinstance(item, NodeItem) else None

    @staticmethod
    def _extract_annotation_line_item(item: Any) -> AnnotationLineItem | None:
        while item is not None and not isinstance(item, AnnotationLineItem):
            item = item.parentItem()
        return item if isinstance(item, AnnotationLineItem) else None

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
            payload["aspect"] = (
                SignalAspect.RED.value if element.is_blocking else element.aspect.value
            )
            payload["direction"] = element.direction.value
            return payload
        if isinstance(element, DisplayLabel):
            return asdict(element)
        if isinstance(element, DisplayLine):
            payload = asdict(element)
            payload["start_x"] = element.start[0]
            payload["start_y"] = element.start[1]
            payload["end_x"] = element.end[0]
            payload["end_y"] = element.end[1]
            return payload
        return {}

    def _node_scene_anchor(self, node_id: str) -> QPointF | None:
        return node_scene_anchor(
            node=self.nodes.get(node_id),
            sprite_width=TrainSpriteItem.WIDTH,
            sprite_height=TrainSpriteItem.HEIGHT,
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

    def _animate_train_item(
        self, train_id: str, sprite: TrainSpriteItem, target_pos: QPointF
    ) -> None:
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
        return is_train_renderable(train, nodes=self.nodes, topology=self.topology)

    def _sync_train_visuals(self) -> None:
        if self._runtime_view_state is None:
            self._clear_train_visuals()
            return
        trains_by_id = getattr(self._runtime_view_state, "trains_by_id", {}) or {}
        visible_trains = {
            train_id: train
            for train_id, train in trains_by_id.items()
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
            previous_anchor = (
                self._node_scene_anchor(previous_section) if previous_section else None
            )
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
        for line in self.annotation_line_items.values():
            line.refresh_geometry()
        self._sync_train_visuals()

    def refresh_element_visuals(self, element_ids: set[str]) -> None:
        """Refresh a small set of nodes and directly connected visual edges."""
        refreshed_edges: set[EdgeItem] = set()
        for element_id in element_ids:
            node = self.nodes.get(element_id)
            if node is None:
                continue
            node.payload = self._element_payload(element_id)
            node.update()
            for edge in self._connected_edges_for_node(element_id):
                if edge in refreshed_edges:
                    continue
                edge.update_geometry()
                refreshed_edges.add(edge)
        self._sync_train_visuals()

    def _connection_pairs(self) -> list[tuple[str, str]]:
        """Return visualized connections in deterministic order."""
        return connection_pairs(
            topology=self.topology,
            nodes=self.nodes,
            signal_links=self.signal_links,
        )

    def _connected_edges_for_node(self, node_id: str) -> tuple[EdgeItem, ...]:
        return tuple(self._edges_by_node.get(node_id, ()))

    def _register_edge_item(self, edge: EdgeItem) -> None:
        self.edges.append(edge)
        self._edges_by_node.setdefault(edge.source.element_id, set()).add(edge)
        self._edges_by_node.setdefault(edge.target.element_id, set()).add(edge)

    def _rebuild_edge_items(self) -> None:
        """Recreate all edge graphics from current topology links."""
        for edge in list(self.edges):
            self.scene_ref.removeItem(edge)
        self.edges.clear()
        self._edges_by_node.clear()

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
            self._register_edge_item(edge)
            seen.add((source_id, target_id))

    def load_topology(self, topology: RailwayTopology, *, emit_change: bool = True) -> None:
        """Load topology object directly."""
        self._rebuild_from_topology(topology, emit_change=emit_change)

    def clear_layout(self) -> None:
        """Clear current scene and reset to an empty topology."""
        if self.nodes or self.edges or self.annotation_line_items:
            self._push_undo_state()
        self._rebuild_from_topology(RailwayTopology())

    def _rebuild_from_topology(
        self, topology: RailwayTopology, *, emit_change: bool = True
    ) -> None:
        self.clear_route_visualization()
        self._clear_train_visuals()
        self.cancel_annotation_tool()
        self._finish_inline_label_edit(commit=False)
        self.scene_ref.clear()
        self.nodes.clear()
        self.annotation_line_items.clear()
        self.edges.clear()
        self._edges_by_node.clear()
        self._connect_source = None
        self.topology = topology
        self.signal_links = self.topology.signal_links
        self.topology.sync_signal_virtual_routes()
        self._counter = {
            "TrackSection": 0,
            "ApproachSection": 0,
            "Point": 0,
            "Signal": 0,
            "Label": 0,
            "Line": 0,
        }

        for node_id in topology.graph.nodes:
            element = topology.graph.nodes[node_id]["element"]
            if isinstance(element, ApproachSection):
                element_type = "ApproachSection"
                self._counter[element_type] = max(
                    self._counter[element_type], self._extract_suffix(node_id)
                )
            elif isinstance(element, TrackSection):
                element_type = "TrackSection"
                self._counter[element_type] = max(
                    self._counter[element_type], self._extract_suffix(node_id)
                )
            elif isinstance(element, Point):
                element_type = "Point"
                self._counter[element_type] = max(
                    self._counter[element_type], self._extract_suffix(node_id)
                )
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
            signal_type = (
                "SignalLeft" if signal.direction == SignalDirection.LEFT else "SignalRight"
            )
            node = NodeItem(signal_id, signal_type, self._element_payload(signal_id))
            node.setPos(QPointF(position[0], position[1]))
            self.scene_ref.addItem(node)
            node.editor = self
            self.nodes[signal_id] = node

        for label_id in topology.labels:
            self._counter["Label"] = max(self._counter["Label"], self._extract_suffix(label_id))
            position = topology.ui_positions.get(label_id, (0.0, 0.0))
            node = NodeItem(label_id, ANNOTATION_LABEL_NODE_TYPE, self._element_payload(label_id))
            node.setPos(QPointF(position[0], position[1]))
            self.scene_ref.addItem(node)
            node.editor = self
            self.nodes[label_id] = node

        for line_id, line in topology.annotation_lines.items():
            self._counter["Line"] = max(self._counter["Line"], self._extract_suffix(line_id))
            item = AnnotationLineItem(line)
            item.editor = self
            self.scene_ref.addItem(item)
            self.annotation_line_items[line_id] = item

        self._rebuild_edge_items()
        self._apply_layout_edit_flags()

        self.refresh_visual_state()
        if emit_change:
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
