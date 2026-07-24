from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import QObject, QRectF, QRunnable, QThreadPool, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsObject,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .graph_layout import force_layout
from .models import GraphEdge, GraphNode, coerce_many
from .theme import NODE_COLORS, Theme, panel_stylesheet


class _NodeItem(QGraphicsObject):
    selected = pyqtSignal(str)
    activated = pyqtSignal(str)

    def __init__(
        self,
        node: GraphNode,
        radius: float,
        show_labels: bool,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self.node = node
        self.radius = radius
        self.show_labels = show_labels
        self.highlighted = False
        self.hovered = False
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setToolTip(
            f"{node.label}\n{node.kind.upper()}"
            + (f"\n{node.project_id}" if node.project_id else "")
        )

    def boundingRect(self) -> QRectF:
        return QRectF(-66.0, -24.0, 132.0, 48.0)

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        color = QColor(self.node.color or NODE_COLORS.get(self.node.kind, Theme.PRIMARY))
        if not self.highlighted and not self.hovered and not self.isSelected():
            color.setAlpha(185)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(color)
        outline = QColor(Theme.WHITE if self.isSelected() or self.hovered else color.name())
        painter.setPen(QPen(outline, 1.8 if self.isSelected() or self.hovered else 0.8))
        painter.drawEllipse(
            QRectF(-self.radius, -self.radius, self.radius * 2.0, self.radius * 2.0)
        )

        if self.show_labels or self.hovered or self.isSelected() or self.highlighted:
            painter.setFont(QFont(Theme.UI, 7, QFont.Weight.DemiBold))
            painter.setPen(QColor(Theme.WHITE))
            label_rect = QRectF(-64.0, self.radius + 2.0, 128.0, 20.0)
            painter.drawText(
                label_rect,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self.node.label[:34],
            )

    def set_highlighted(self, highlighted: bool) -> None:
        self.highlighted = highlighted
        self.update()

    def set_show_labels(self, visible: bool) -> None:
        self.show_labels = visible
        self.update()

    def hoverEnterEvent(self, event) -> None:
        self.hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        self.selected.emit(self.node.id)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        self.activated.emit(self.node.id)
        super().mouseDoubleClickEvent(event)


class _LayoutSignals(QObject):
    ready = pyqtSignal(object)


class _LayoutWorker(QRunnable):
    def __init__(
        self,
        generation: int,
        nodes: list[GraphNode],
        edges: list[GraphEdge],
        compact: bool,
        hidden: int,
    ) -> None:
        super().__init__()
        self.generation = generation
        self.nodes = nodes
        self.edges = edges
        self.compact = compact
        self.hidden = hidden
        self.signals = _LayoutSignals()

    def run(self) -> None:
        layout_edges = [edge for edge in self.edges if edge.kind != "semantic"]
        positions = force_layout(
            self.nodes,
            layout_edges or self.edges,
            width=980.0,
            height=680.0,
            iterations=55 if self.compact else 90,
        )
        self.signals.ready.emit(
            (self.generation, self.nodes, self.edges, positions, self.hidden)
        )


class _GraphView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene, parent: QWidget | None = None) -> None:
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setBackgroundBrush(QColor(Theme.BG))
        self.setFrameShape(QFrame.Shape.NoFrame)

    def wheelEvent(self, event) -> None:
        factor = 1.17 if event.angleDelta().y() > 0 else 1.0 / 1.17
        current = self.transform().m11()
        if 0.18 < current * factor < 8.0:
            self.scale(factor, factor)

    def fit_graph(self) -> None:
        rect = self.scene().itemsBoundingRect().adjusted(-35, -35, 35, 35)
        if not rect.isEmpty():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)


class KnowledgeGraphWidget(QWidget):
    """Dependency-light native graph for a local or project-scoped vault view."""

    node_selected = pyqtSignal(str)
    node_activated = pyqtSignal(str)
    refresh_requested = pyqtSignal()

    def __init__(self, compact: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.compact = compact
        self.max_nodes = 180 if compact else 420
        self._nodes: list[GraphNode] = []
        self._edges: list[GraphEdge] = []
        self._positions: dict[str, tuple[float, float]] = {}
        self._node_items: dict[str, _NodeItem] = {}
        self._scene = QGraphicsScene(self)
        self._layout_generation = 0
        self._pool = QThreadPool.globalInstance()
        self.setStyleSheet(panel_stylesheet())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(5)

        controls = QHBoxLayout()
        title = QLabel("KNOWLEDGE GRAPH")
        title.setObjectName("SectionTitle")
        controls.addWidget(title)
        self._search = QLineEdit()
        self._search.setPlaceholderText("Find node...")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_search)
        controls.addWidget(self._search, stretch=1)
        self._semantic = QCheckBox("Semantic")
        self._semantic.setToolTip("Show embedding-similarity edges")
        self._semantic.toggled.connect(self._rebuild_scene)
        controls.addWidget(self._semantic)
        self._labels = QCheckBox("Labels")
        self._labels.setChecked(not compact)
        self._labels.toggled.connect(self._set_labels)
        controls.addWidget(self._labels)
        fit = QPushButton("FIT")
        fit.clicked.connect(lambda: self._view.fit_graph())
        controls.addWidget(fit)
        refresh = QPushButton("REFRESH")
        refresh.clicked.connect(lambda: self.refresh_requested.emit())
        controls.addWidget(refresh)
        layout.addLayout(controls)

        self._view = _GraphView(self._scene)
        layout.addWidget(self._view, stretch=1)
        self._status = QLabel("No graph data")
        self._status.setStyleSheet(
            f"color: {Theme.TEXT_DIM}; font-family: {Theme.MONO}; font-size: 8pt;"
        )
        layout.addWidget(self._status)

        if compact:
            self._semantic.hide()
            self._labels.hide()
            refresh.hide()
            self._search.setMaximumWidth(110)

    def set_graph(
        self,
        nodes: list[GraphNode | dict],
        edges: list[GraphEdge | dict],
    ) -> None:
        all_nodes = coerce_many(GraphNode, nodes)
        all_edges = coerce_many(GraphEdge, edges)
        degree = Counter()
        for edge in all_edges:
            degree[edge.source] += 1
            degree[edge.target] += 1
        ranked = sorted(
            all_nodes,
            key=lambda node: (degree[node.id], float(node.score or 0.0), node.updated),
            reverse=True,
        )
        selected_nodes = ranked[: self.max_nodes]
        visible = {node.id for node in selected_nodes}
        selected_edges = [
            edge for edge in all_edges if edge.source in visible and edge.target in visible
        ]
        hidden = len(all_nodes) - len(selected_nodes)
        self._layout_generation += 1
        self._status.setText(
            f"Laying out {len(selected_nodes)} nodes and {len(selected_edges)} edges..."
        )
        worker = _LayoutWorker(
            self._layout_generation,
            selected_nodes,
            selected_edges,
            self.compact,
            hidden,
        )
        worker.signals.ready.connect(self._apply_layout)
        self._pool.start(worker)

    def _apply_layout(self, result: object) -> None:
        generation, nodes, edges, positions, hidden = result
        if generation != self._layout_generation:
            return
        self._nodes = nodes
        self._edges = edges
        self._positions = positions
        self._rebuild_scene()
        suffix = f"  |  {hidden} lower-ranked nodes hidden" if hidden else ""
        self._status.setText(
            f"{len(self._nodes)} nodes  |  {len(self._edges)} edges{suffix}"
        )

    def focus_node(self, node_id: str) -> None:
        item = self._node_items.get(node_id)
        if not item:
            return
        self._scene.clearSelection()
        item.setSelected(True)
        self._view.centerOn(item)
        self.node_selected.emit(node_id)

    def _rebuild_scene(self) -> None:
        self._scene.clear()
        self._node_items = {}
        show_semantic = self._semantic.isChecked()
        for edge in self._edges:
            if edge.kind == "semantic" and not show_semantic:
                continue
            if edge.source not in self._positions or edge.target not in self._positions:
                continue
            sx, sy = self._positions[edge.source]
            tx, ty = self._positions[edge.target]
            line = QGraphicsLineItem(sx, sy, tx, ty)
            if edge.kind == "semantic":
                color = QColor(Theme.PURPLE)
                style = Qt.PenStyle.DashLine
            elif edge.kind in {"project", "contains"}:
                color = QColor(Theme.GREEN)
                style = Qt.PenStyle.SolidLine
            else:
                color = QColor(Theme.BORDER_BRIGHT)
                style = Qt.PenStyle.SolidLine
            color.setAlpha(80 if edge.kind != "semantic" else 105)
            line.setPen(QPen(color, max(0.6, min(2.2, edge.weight)), style))
            line.setZValue(-5)
            line.setToolTip(edge.label or edge.kind)
            self._scene.addItem(line)

        degree = Counter()
        for edge in self._edges:
            degree[edge.source] += 1
            degree[edge.target] += 1
        for node in self._nodes:
            radius = 4.2 + min(8.5, degree[node.id] * 0.55 + float(node.score or 0.0))
            item = _NodeItem(node, radius, self._labels.isChecked())
            x, y = self._positions.get(node.id, (0.0, 0.0))
            item.setPos(x, y)
            item.selected.connect(self.node_selected)
            item.activated.connect(self.node_activated)
            self._scene.addItem(item)
            self._node_items[node.id] = item
        self._scene.setSceneRect(0, 0, 980, 680)
        self._apply_search(self._search.text())
        self._view.fit_graph()

    def _set_labels(self, visible: bool) -> None:
        for item in self._node_items.values():
            item.set_show_labels(visible)

    def _apply_search(self, query: str) -> None:
        wanted = query.strip().casefold()
        first_match: _NodeItem | None = None
        for item in self._node_items.values():
            matched = bool(wanted) and wanted in " ".join(
                [item.node.label, item.node.kind, item.node.project_id, item.node.path]
            ).casefold()
            item.set_highlighted(matched)
            if matched and first_match is None:
                first_match = item
        if first_match and len(wanted) >= 2:
            self._view.centerOn(first_match)
