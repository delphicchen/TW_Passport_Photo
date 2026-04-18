"""Side-panel widget that shows AI / SynthID detection results."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import (
    QFrame, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from core.ai_detector import DetectionResult


class AiDetectionPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.show_idle()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QLabel("AI 痕跡偵測")
        header.setStyleSheet(
            "font-weight: bold; font-size: 12px; padding: 4px 0;"
        )
        layout.addWidget(header)

        self._status_badge = _Badge()
        layout.addWidget(self._status_badge)

        self._detail_label = QLabel()
        self._detail_label.setWordWrap(True)
        self._detail_label.setStyleSheet("font-size: 10px; color: #555;")
        self._detail_label.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum
        )
        layout.addWidget(self._detail_label)

        note_frame = QFrame()
        note_frame.setFrameShape(QFrame.Shape.StyledPanel)
        note_layout = QVBoxLayout(note_frame)
        note_layout.setContentsMargins(6, 6, 6, 6)
        note = QLabel(
            "⚠ SynthID 隱形浮水印需要 Google 專有偵測器，"
            "無法透過第三方工具可靠偵測。\n"
            "此處僅檢查 EXIF / metadata 中的 AI 相關標記。"
        )
        note.setWordWrap(True)
        note.setStyleSheet("font-size: 9px; color: #888;")
        note_layout.addWidget(note)
        layout.addWidget(note_frame)

    def show_idle(self) -> None:
        self._status_badge.set_neutral("尚未載入照片")
        self._detail_label.clear()

    def show_result(self, result: DetectionResult) -> None:
        if result.has_ai_metadata:
            self._status_badge.set_warning("偵測到 AI / Google 相關 metadata")
            lines = ["發現以下可疑欄位："]
            for f in result.suspicious_fields:
                lines.append(f"• {f}")
            self._detail_label.setText("\n".join(lines))
        else:
            self._status_badge.set_ok("未發現 AI metadata 痕跡")
            sw = result.software_tag or "（無）"
            self._detail_label.setText(f"Software 欄位：{sw}")


class _Badge(QLabel):
    """Coloured status pill."""

    def set_neutral(self, text: str) -> None:
        self._apply("#999", "#f0f0f0", text)

    def set_ok(self, text: str) -> None:
        self._apply("#2e7d32", "#e8f5e9", text)

    def set_warning(self, text: str) -> None:
        self._apply("#b71c1c", "#ffebee", text)

    def _apply(self, fg: str, bg: str, text: str) -> None:
        self.setText(text)
        self.setStyleSheet(
            f"color: {fg}; background: {bg}; border-radius: 4px;"
            f"padding: 3px 6px; font-size: 10px; font-weight: bold;"
        )
