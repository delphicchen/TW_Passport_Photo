"""
4×6 inch print-sheet dialog — landscape orientation, 4 columns × 2 rows.

Output image: 1800 × 1200 px (6" × 4" @ 300 DPI), white background.
Each slot holds one passport photo (35 × 45 mm, portrait orientation).
"""
from __future__ import annotations

import os
import tempfile

from PIL import Image, ImageDraw
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QGridLayout, QHBoxLayout,
    QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from core.specs import PHOTO_ASPECT

# ── Output constants (300 DPI, 4×6 landscape: 6" wide × 4" tall) ─────────────
_DPI     = 300
_SHEET_W = round(6 * _DPI)   # 1800 px  (landscape width)
_SHEET_H = round(4 * _DPI)   # 1200 px  (landscape height)
_COLS    = 4
_ROWS    = 2
_MARGIN  = 18   # px around whole sheet
_GUTTER  = 8    # px between photos

_SLOT_W = (_SHEET_W - 2 * _MARGIN - (_COLS - 1) * _GUTTER) // _COLS  # 429 px
_SLOT_H = (_SHEET_H - 2 * _MARGIN - (_ROWS - 1) * _GUTTER) // _ROWS  # 587 px

# Screen preview: each slot shown proportionally
# Fit 4 slots in ~620 px width → each slot ~140 px wide
_PREV_W = 138
_PREV_H = round(_PREV_W / PHOTO_ASPECT)   # ≈ 177 px  (35:45 portrait)


# ── Single photo slot ─────────────────────────────────────────────────────────

class PhotoSlot(QWidget):
    slot_clicked = Signal(int)

    def __init__(self, index: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._index  = index
        self._pixmap: QPixmap | None = None
        self._path:   str | None     = None
        self.setFixedSize(_PREV_W, _PREV_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("點選以選擇照片")

    # ── public ────────────────────────────────────────────────────────────────

    def set_photo(self, path: str) -> None:
        self._path = path
        px = QPixmap(path)
        if not px.isNull():
            self._pixmap = px.scaled(
                _PREV_W, _PREV_H,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._path   = None
        self.update()

    @property
    def photo_path(self) -> str | None:
        return self._path

    # ── events ────────────────────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.slot_clicked.emit(self._index)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        if self._pixmap:
            x = (_PREV_W - self._pixmap.width())  // 2
            y = (_PREV_H - self._pixmap.height()) // 2
            painter.setClipRect(self.rect())
            painter.drawPixmap(x, y, self._pixmap)
            painter.setClipping(False)
        else:
            painter.setPen(QPen(QColor(190, 190, 190), 1, Qt.PenStyle.DashLine))
            painter.drawRect(self.rect().adjusted(2, 2, -2, -2))
            f = QFont()
            f.setPointSize(8)
            painter.setFont(f)
            painter.setPen(QColor(160, 160, 160))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter,
                f"點選以\n加入照片\n\n（{self._index + 1}）",
            )

        painter.setPen(QPen(QColor(180, 180, 180), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))


# ── Dialog ────────────────────────────────────────────────────────────────────

class PrintSheetDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("排版列印 — 4×6 吋相紙橫式（4 欄 × 2 列）")
        self._slots: list[PhotoSlot] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.setContentsMargins(16, 16, 16, 16)

        # Info
        info = QLabel(
            "4×6 吋相紙 · 橫式 · 300 DPI　　4 欄 × 2 列，共 8 張護照照片\n"
            "點選格子以選擇照片（每格可載入不同照片）"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #555;")
        root.addWidget(info)

        # Grid (4 cols × 2 rows) — landscape feel
        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setHorizontalSpacing(_GUTTER)
        grid.setVerticalSpacing(_GUTTER)
        grid.setContentsMargins(0, 0, 0, 0)

        for i in range(_COLS * _ROWS):
            slot = PhotoSlot(i)
            slot.slot_clicked.connect(self._on_slot_clicked)
            self._slots.append(slot)
            row, col = divmod(i, _COLS)
            grid.addWidget(slot, row, col)

        root.addWidget(grid_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Size note
        pw_mm = _SLOT_W / _DPI * 25.4
        ph_mm = _SLOT_H / _DPI * 25.4
        note = QLabel(
            f"每格輸出：{_SLOT_W} × {_SLOT_H} px"
            f"  （≈ {pw_mm:.0f} × {ph_mm:.0f} mm @ {_DPI} DPI）"
        )
        note.setStyleSheet("font-size: 9pt; color: #888;")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(note)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_clear = QPushButton("清除全部")
        btn_clear.clicked.connect(self._clear_all)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()

        for label, fmt in [("💾  儲存 JPEG", "jpg"), ("💾  儲存 PNG", "png")]:
            b = QPushButton(label)
            b.setMinimumHeight(36)
            b.clicked.connect(lambda _=False, f=fmt: self._save_sheet(f))
            btn_row.addWidget(b)

        btn_print = QPushButton("🖨  列印")
        btn_print.setMinimumHeight(36)
        btn_print.clicked.connect(self._print_sheet)
        btn_row.addWidget(btn_print)

        root.addLayout(btn_row)

    # ── slot interaction ──────────────────────────────────────────────────────

    def _on_slot_clicked(self, index: int) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, f"選擇第 {index + 1} 張照片", "",
            "圖片檔案 (*.jpg *.jpeg *.png *.bmp *.tiff *.webp)",
        )
        if path:
            self._slots[index].set_photo(path)

    def _clear_all(self) -> None:
        for s in self._slots:
            s.clear()

    # ── compose ───────────────────────────────────────────────────────────────

    def _compose(self) -> Image.Image:
        sheet = Image.new("RGB", (_SHEET_W, _SHEET_H), (255, 255, 255))
        draw  = ImageDraw.Draw(sheet)

        for i, slot in enumerate(self._slots):
            row, col = divmod(i, _COLS)
            x = _MARGIN + col * (_SLOT_W + _GUTTER)
            y = _MARGIN + row * (_SLOT_H + _GUTTER)

            if slot.photo_path:
                photo = Image.open(slot.photo_path).convert("RGB")
                pw, ph = photo.size

                # Centre-crop to 35:45
                if pw / ph > PHOTO_ASPECT:
                    nw = round(ph * PHOTO_ASPECT)
                    photo = photo.crop(((pw - nw) // 2, 0, (pw - nw) // 2 + nw, ph))
                else:
                    nh = round(pw / PHOTO_ASPECT)
                    photo = photo.crop((0, (ph - nh) // 2, pw, (ph - nh) // 2 + nh))

                # Scale to fit slot (no upscale beyond slot)
                scale = min(_SLOT_W / photo.width, _SLOT_H / photo.height)
                ow = round(photo.width  * scale)
                oh = round(photo.height * scale)
                photo = photo.resize((ow, oh), Image.LANCZOS)

                # Paste centred in slot
                px = x + (_SLOT_W - ow) // 2
                py = y + (_SLOT_H - oh) // 2
                sheet.paste(photo, (px, py))
            else:
                # Empty slot placeholder
                draw.rectangle([x, y, x + _SLOT_W, y + _SLOT_H],
                               outline=(210, 210, 210), width=2)
                cx = x + _SLOT_W // 2
                cy = y + _SLOT_H // 2
                draw.line([cx - 24, cy, cx + 24, cy], fill=(210, 210, 210), width=2)
                draw.line([cx, cy - 24, cx, cy + 24], fill=(210, 210, 210), width=2)

        return sheet

    # ── save ─────────────────────────────────────────────────────────────────

    def _save_sheet(self, fmt: str) -> None:
        filt    = "JPEG (*.jpg)" if fmt == "jpg" else "PNG (*.png)"
        default = f"passport_sheet.{fmt}"
        path, _ = QFileDialog.getSaveFileName(self, "儲存排版", default, filt)
        if not path:
            return
        sheet = self._compose()
        kw: dict = {"dpi": (_DPI, _DPI)}
        if fmt == "jpg":
            kw.update(quality=95, subsampling=0)
        sheet.save(path, **kw)
        QMessageBox.information(self, "已儲存", f"排版已儲存至：\n{path}")

    # ── print ─────────────────────────────────────────────────────────────────

    def _print_sheet(self) -> None:
        try:
            from PySide6.QtPrintSupport import QPrinter, QPrintDialog
            from PySide6.QtGui import QPageLayout
        except ImportError:
            QMessageBox.critical(self, "錯誤", "找不到列印模組 (QtPrintSupport)")
            return

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setPageOrientation(QPageLayout.Orientation.Landscape)

        if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
            return

        sheet = self._compose()
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        sheet.save(tmp.name)

        px = QPixmap(tmp.name)
        painter = QPainter(printer)
        vp = painter.viewport()
        scaled = px.scaled(
            vp.width(), vp.height(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = (vp.width()  - scaled.width())  // 2
        y = (vp.height() - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.end()
        os.unlink(tmp.name)
