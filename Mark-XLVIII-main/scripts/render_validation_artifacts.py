"""Render desktop and Canvas validation screenshots without mutating live data."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QImage, QPainter, QPen
from PyQt6.QtWidgets import QApplication

from core.canvas_document import load_document
from core.canvas_layout import layout_document
from core.process_events import PROCESS_EVENTS, emit_process_event


def _render_canvas(payload: dict, target: Path, title: str) -> None:
    nodes = [node for node in payload.get("nodes", []) if isinstance(node, dict)]
    width, height = 1600, 900
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    image.fill(QColor("#00070c"))
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setFont(QFont("Courier New", 11))
    painter.setPen(QColor("#00d9ff"))
    painter.drawText(20, 28, title)
    if not nodes:
        painter.end()
        image.save(str(target))
        return
    min_x = min(int(node["x"]) for node in nodes)
    min_y = min(int(node["y"]) for node in nodes)
    max_x = max(int(node["x"] + node["width"]) for node in nodes)
    max_y = max(int(node["y"] + node["height"]) for node in nodes)
    scale = min((width - 80) / max(1, max_x - min_x), (height - 80) / max(1, max_y - min_y))
    scale = max(0.08, min(scale, 1.2))

    def centre(node):
        return QPointF(
            40 + (node["x"] - min_x + node["width"] / 2) * scale,
            50 + (node["y"] - min_y + node["height"] / 2) * scale,
        )

    by_id = {str(node.get("id")): node for node in nodes}
    painter.setPen(QPen(QColor("#17677a"), 1))
    for edge in payload.get("edges", []):
        left, right = by_id.get(str(edge.get("fromNode"))), by_id.get(str(edge.get("toNode")))
        if left and right:
            painter.drawLine(centre(left), centre(right))
    for node in nodes:
        rect = QRectF(
            40 + (node["x"] - min_x) * scale,
            50 + (node["y"] - min_y) * scale,
            max(20, node["width"] * scale),
            max(14, node["height"] * scale),
        )
        painter.fillRect(rect, QColor("#032331") if str(node.get("id", "")).startswith("jarvis-") else QColor("#18202a"))
        painter.setPen(QPen(QColor("#00bcd4"), 1))
        painter.drawRect(rect)
        if rect.width() >= 90 and rect.height() >= 35:
            text = str(node.get("text") or node.get("file") or node.get("url") or node.get("id") or "")
            text = " ".join(text.replace("#", "").split())[:90]
            painter.setPen(QColor("#b7edf3"))
            painter.drawText(rect.adjusted(5, 4, -5, -4), Qt.TextFlag.TextWordWrap, text)
    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(target))


def render_canvas_pairs(output: Path, vault_root: Path) -> list[Path]:
    sources = [
        vault_root / "Canvases" / "JARVIS" / "live-validation-task-dashboard.canvas",
        vault_root / "Canvases" / "JARVIS" / "plan-plan-wifi-sensing-pipeline-resource-research.canvas",
    ]
    created = []
    for source in sources:
        if not source.exists():
            continue
        payload = load_document(source)
        profile = "tasks" if "task" in source.stem else "plan"
        proposed, _ = layout_document(payload, profile=profile)
        before = output / "canvas" / f"{source.stem}-before.png"
        after = output / "canvas" / f"{source.stem}-after.png"
        _render_canvas(payload, before, f"BEFORE - {source.name}")
        _render_canvas(proposed, after, f"PREVIEW - {profile.upper()} LAYOUT")
        created.extend([before, after])
    return created


def render_desktop(output: Path) -> list[Path]:
    import ui

    app = QApplication.instance() or QApplication([])
    original_refresh = ui.MainWindow._refresh_operations
    ui.MainWindow._refresh_operations = lambda self: None
    try:
        window = ui.MainWindow("")
    finally:
        ui.MainWindow._refresh_operations = original_refresh
    PROCESS_EVENTS.clear()
    emit_process_event(category="router", source="jarvis", summary="Turn accepted; selecting a workflow.", state="running")
    emit_process_event(category="tool", source="jarvis_canvas", summary="Canvas validation completed.", state="completed")
    window._show_content("ROUTER MODE", "JARVIS response output remains readable beneath the bounded process trace.")
    window.show()
    created = []
    for width, height in ((820, 580), (980, 700), (1920, 1080)):
        window.resize(width, height)
        app.processEvents()
        target = output / "desktop" / f"mark-{width}x{height}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        window.grab().save(str(target))
        created.append(target)
    window.close()
    app.processEvents()
    return created


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="test_artifacts/vault-canvas-ui")
    parser.add_argument("--vault", default=r"F:\Mark-XLVIII-main\Jarvis_notes")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    app = QApplication.instance() or QApplication([])
    for font in (r"C:\Windows\Fonts\cour.ttf", r"C:\Windows\Fonts\courbd.ttf"):
        if Path(font).exists():
            QFontDatabase.addApplicationFont(font)
    created = render_canvas_pairs(output, Path(args.vault).resolve())
    created.extend(render_desktop(output))
    print("\n".join(str(path) for path in created))
    app.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
