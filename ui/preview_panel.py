"""Right-side panel: shows a live preview of the cropped passport photo output."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QSizePolicy, QVBoxLayout, QWidget

from core.specs import OUT_H_PX, OUT_W_PX, PHOTO_ASPECT

_PREVIEW_W = 175
_PREVIEW_H = round(_PREVIEW_W / PHOTO_ASPECT)   # ≈ 225


class PreviewPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_PREVIEW_W + 20)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        header = QLabel("輸出預覽")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setStyleSheet(
            "font-weight: bold; font-size: 12px; padding-bottom: 4px;"
            "border-bottom: 1px solid #ccc;"
        )
        layout.addWidget(header)

        self._img_label = _PreviewLabel()
        layout.addWidget(self._img_label)

        self._info_label = QLabel("35 × 45 mm\n600 DPI\n"
                                  f"{OUT_W_PX} × {OUT_H_PX} px")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._info_label.setStyleSheet("font-size: 9px; color: #888;")
        layout.addWidget(self._info_label)

        layout.addStretch()

    def update_preview(self, pixmap: QPixmap | None) -> None:
        if pixmap is None or pixmap.isNull():
            self._img_label.set_pixmap(None)
        else:
            scaled = pixmap.scaled(
                _PREVIEW_W, _PREVIEW_H,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self._img_label.set_pixmap(scaled)


class _PreviewLabel(QWidget):
    """Fixed-size image frame with border."""

    def __init__(self) -> None:
        super().__init__()
        self._pixmap: QPixmap | None = None
        self.setFixedSize(_PREVIEW_W, _PREVIEW_H)
        self.setStyleSheet("background: white; border: 1px solid #aaa;")

    def set_pixmap(self, px: QPixmap | None) -> None:
        self._pixmap = px
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255))
        if self._pixmap:
            x = (self.width()  - self._pixmap.width())  // 2
            y = (self.height() - self._pixmap.height()) // 2
            painter.drawPixmap(x, y, self._pixmap)
        else:
            painter.setPen(QColor(180, 180, 180))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                "預覽\n（載入照片後顯示）"
            )
