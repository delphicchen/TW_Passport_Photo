from __future__ import annotations

import os
from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFrame, QLabel,
    QMainWindow, QMessageBox, QProgressDialog, QPushButton,
    QSizePolicy, QVBoxLayout, QHBoxLayout, QWidget,
)

from core import ai_detector, watermark_remover
from core.specs import OUT_H_PX, OUT_W_PX, PHOTO_ASPECT
from ui.ai_panel import AiDetectionPanel
from ui.photo_canvas import PhotoCanvas
from ui.preview_panel import PreviewPanel
from ui.print_sheet import PrintSheetDialog


# ── Background workers ────────────────────────────────────────────────────────

class _RemoveWorker(QThread):
    finished = Signal(bool, str, str)   # ok, output_path, message

    def __init__(self, input_path: str) -> None:
        super().__init__()
        self._input = input_path

    def run(self) -> None:
        result = watermark_remover.remove_watermark(self._input, use_binary=True)
        self.finished.emit(result.success, result.output_path, result.message)


# ── Main window ───────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("中華民國護照照片工具")
        self.setMinimumSize(980, 660)
        self._current_path: str | None = None
        self._setup_ui()
        self._update_wm_button()

    # ── layout ────────────────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        root.addWidget(self._build_sidebar())      # left  (fixed)

        self.canvas = PhotoCanvas()
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self.canvas.crop_changed.connect(self._refresh_preview)
        root.addWidget(self.canvas, stretch=1)     # center (flexible)

        self.preview = PreviewPanel()
        root.addWidget(self.preview)               # right (fixed)

    def _build_sidebar(self) -> QFrame:
        frame = QFrame()
        frame.setFixedWidth(205)
        frame.setFrameShape(QFrame.Shape.StyledPanel)
        lay = QVBoxLayout(frame)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        lay.setSpacing(7)
        lay.setContentsMargins(10, 10, 10, 10)

        title = QLabel("護照照片工具")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-weight: bold; font-size: 14px; padding-bottom: 5px;"
            "border-bottom: 1px solid #ccc;"
        )
        lay.addWidget(title)

        # Load / Save
        self.btn_load = QPushButton("📂  載入照片")
        self.btn_load.setMinimumHeight(36)
        self.btn_load.clicked.connect(self._load_photo)
        lay.addWidget(self.btn_load)

        self.btn_save = QPushButton("💾  儲存照片")
        self.btn_save.setMinimumHeight(36)
        self.btn_save.setEnabled(False)
        self.btn_save.clicked.connect(self._save_photo)
        lay.addWidget(self.btn_save)

        btn_print_sheet = QPushButton("🖨  列印排版（4×6）")
        btn_print_sheet.setMinimumHeight(36)
        btn_print_sheet.clicked.connect(self._open_print_sheet)
        lay.addWidget(btn_print_sheet)

        lay.addSpacing(6)

        # Watermark removal
        wm_hdr = QLabel("Gemini 浮水印")
        wm_hdr.setStyleSheet("font-weight: bold; font-size: 11px;")
        lay.addWidget(wm_hdr)

        self.btn_remove_wm = QPushButton("✨  移除 Gemini 浮水印")
        self.btn_remove_wm.setMinimumHeight(36)
        self.btn_remove_wm.setEnabled(False)
        self.btn_remove_wm.clicked.connect(self._remove_watermark)
        lay.addWidget(self.btn_remove_wm)

        lay.addSpacing(6)

        # Guide toggles
        guide_hdr = QLabel("顯示參考線")
        guide_hdr.setStyleSheet("font-weight: bold; font-size: 11px;")
        lay.addWidget(guide_hdr)

        self.chk_spec = QCheckBox("規格參考線")
        self.chk_spec.setChecked(True)
        self.chk_spec.toggled.connect(
            lambda v: (setattr(self.canvas, "show_spec_guide", v), self.canvas.update())
        )
        lay.addWidget(self.chk_spec)

        self.chk_contour = QCheckBox("輪廓參考線")
        self.chk_contour.setChecked(True)
        self.chk_contour.toggled.connect(
            lambda v: (setattr(self.canvas, "show_contour_guide", v), self.canvas.update())
        )
        lay.addWidget(self.chk_contour)

        lay.addSpacing(6)

        self.info_label = QLabel("尚未載入照片")
        self.info_label.setWordWrap(True)
        self.info_label.setStyleSheet("color: gray; font-size: 10px;")
        lay.addWidget(self.info_label)

        lay.addSpacing(6)

        self.ai_panel = AiDetectionPanel()
        lay.addWidget(self.ai_panel)

        lay.addStretch()

        spec = QLabel(
            "規格摘要\n"
            "尺寸：35 × 45 mm\n"
            "臉部高度：32–36 mm\n"
            "解析度：600 DPI\n"
            f"輸出像素：{OUT_W_PX} × {OUT_H_PX}"
        )
        spec.setStyleSheet(
            "font-size: 9px; color: #666;"
            "border-top: 1px solid #ccc; padding-top: 6px;"
        )
        lay.addWidget(spec)

        return frame

    # ── photo actions ─────────────────────────────────────────────────────────

    def _load_photo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "載入照片", "",
            "圖片檔案 (*.jpg *.jpeg *.png *.bmp *.tiff *.webp)",
        )
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return

        self._current_path = path
        self.canvas.load_photo(pixmap)
        self.btn_save.setEnabled(True)
        self._update_wm_button()
        self.info_label.setText(
            f"{os.path.basename(path)}\n{pixmap.width()} × {pixmap.height()} px"
        )
        self.ai_panel.show_result(ai_detector.detect(path))
        self._refresh_preview()

    def _save_photo(self) -> None:
        if not self._current_path:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "儲存護照照片", "passport_photo.jpg",
            "JPEG (*.jpg);;PNG (*.png)",
        )
        if not path:
            return

        # Use the crop pixmap from the canvas (respects user pan/zoom)
        crop_px = self.canvas.crop_pixmap()
        if crop_px is None:
            return

        # Convert to PIL, resize to spec output size
        tmp_buf = crop_px.toImage()
        tmp_buf.save("/tmp/_passport_crop.png")
        img = Image.open("/tmp/_passport_crop.png").convert("RGB")
        img = img.resize((OUT_W_PX, OUT_H_PX), Image.LANCZOS)

        kwargs: dict = {"dpi": (600, 600)}
        if path.lower().endswith((".jpg", ".jpeg")):
            kwargs.update(quality=95, subsampling=0)
        img.save(path, **kwargs)

        self.info_label.setText(
            self.info_label.text() + f"\n✓ 已儲存 {os.path.basename(path)}"
        )

    # ── watermark removal ─────────────────────────────────────────────────────

    def _update_wm_button(self) -> None:
        self.btn_remove_wm.setEnabled(self._current_path is not None)

    def _remove_watermark(self) -> None:
        if not self._current_path:
            return
        prog = QProgressDialog("正在移除 Gemini 浮水印 …", None, 0, 0, self)
        prog.setWindowModality(Qt.WindowModality.WindowModal)
        prog.show()

        self._rm_worker = _RemoveWorker(self._current_path)
        self._rm_worker.finished.connect(
            lambda ok, out, msg: self._on_rm_done(ok, out, msg, prog)
        )
        self._rm_worker.start()

    def _on_rm_done(
        self, ok: bool, output_path: str, message: str,
        prog: QProgressDialog,
    ) -> None:
        prog.close()
        if not ok:
            QMessageBox.critical(self, "移除失敗", message)
            return
        self._current_path = output_path
        px = QPixmap(output_path)
        self.canvas.load_photo(px)
        self.info_label.setText(self.info_label.text() + "\n✓ 浮水印已移除")
        self.ai_panel.show_result(ai_detector.detect(output_path))
        self._refresh_preview()

    # ── print sheet ───────────────────────────────────────────────────────────

    def _open_print_sheet(self) -> None:
        dlg = PrintSheetDialog(self)
        dlg.exec()

    # ── preview ───────────────────────────────────────────────────────────────

    def _refresh_preview(self) -> None:
        self.preview.update_preview(self.canvas.crop_pixmap())
