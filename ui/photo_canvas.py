from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QPoint, QPointF, QRectF, Signal
from PySide6.QtGui import (
    QBrush, QColor, QCursor, QFont, QImage, QPainter, QPen, QPixmap,
)
from PySide6.QtWidgets import QWidget

from core.specs import (
    CHIN_FROM_TOP_FRAC,
    FACE_OVAL_WIDTH_FRAC,
    HEAD_TOP_MAX_FRAC, HEAD_TOP_MIN_FRAC,
    PHOTO_ASPECT,
)

_CLR_FRAME       = QColor(0,   140, 220)
_CLR_GUIDE       = QColor(180, 120,   0)
_CLR_CENTER      = QColor(180,  30,  30)
_CLR_OVAL        = QColor( 80,  80,  80)
_CLR_ZONE        = QColor(0,   200,   0,  45)
_CLR_LABEL       = QColor( 20,  20,  20)    # dark text
_CLR_LABEL_HALO  = QColor(255, 255, 255)    # white outline for readability

_ZOOM_MIN  = 1.0
_ZOOM_MAX  = 8.0
_ZOOM_STEP = 0.01       # per scroll notch (1 % increments)
_TOP_EXTRA = 0.45       # fraction of frame height user can expose at top (for crown space)

_rng = np.random.default_rng(seed=42)   # fixed seed → stable noise (no flicker)


def _sample_top_rgb(px: QPixmap, n_rows: int = 5) -> np.ndarray:
    """Return median RGB (float, shape (3,)) of the top n_rows of a QPixmap."""
    n   = min(n_rows, px.height())
    img = px.copy(0, 0, px.width(), n).toImage() \
            .convertToFormat(QImage.Format.Format_RGB888)
    w, h = img.width(), img.height()
    bpl  = img.bytesPerLine()
    raw  = np.frombuffer(img.bits(), dtype=np.uint8).copy()
    rows = np.stack([raw[r * bpl: r * bpl + w * 3] for r in range(h)])
    return np.median(rows.reshape(-1, 3), axis=0)   # (3,) float


def _noisy_fill(w: int, h: int, base_rgb: np.ndarray) -> np.ndarray:
    """
    Noisy fill using *base_rgb* as the centre colour (σ = 5).
    Sampling the photo's top edge as base_rgb avoids a visible colour seam.
    """
    base  = np.broadcast_to(base_rgb.astype(np.int16), (h, w, 3)).copy()
    noise = (_rng.standard_normal((h, w, 3)) * 5).astype(np.int16)
    return np.clip(base + noise, 0, 255).astype(np.uint8)


class PhotoCanvas(QWidget):
    """Main editing canvas.  User drags to pan, scrolls to zoom."""

    crop_changed = Signal()   # emitted whenever the visible crop changes

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.pixmap: QPixmap | None = None
        self.show_spec_guide    = True
        self.show_contour_guide = True

        self._zoom: float       = 1.0
        self._pan:  QPointF     = QPointF(0.0, 0.0)
        self._drag_start: QPoint | None = None
        self._drag_pan_start: QPointF   = QPointF(0.0, 0.0)
        # Cached top-edge colour for seamless noisy fill; updated on photo load
        self._top_rgb: np.ndarray = np.array([252, 252, 252], dtype=np.float64)

        self.setMinimumSize(420, 540)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    # ── public API ────────────────────────────────────────────────────────────

    def load_photo(self, pixmap: QPixmap) -> None:
        self.pixmap  = pixmap
        self._zoom   = 1.0
        self._pan    = QPointF(0.0, 0.0)
        # Sample top 5 rows of the original photo as the fill base colour
        self._top_rgb = _sample_top_rgb(pixmap, n_rows=5)
        self.update()
        self.crop_changed.emit()

    def crop_pixmap(self) -> QPixmap | None:
        """Return a QPixmap of what would be saved.

        If the photo doesn't cover the full frame (e.g. the user panned down
        to add crown space), the exposed area is filled with near-white noise
        instead of a solid colour so it blends naturally with photo backgrounds.
        """
        if not self.pixmap:
            return None
        frame = self._frame_rect()
        fw, fh = frame.width(), frame.height()
        iw, ih = self.pixmap.width(), self.pixmap.height()
        eff = self._effective_scale(fw, fh, iw, ih)
        sw, sh = iw * eff, ih * eff
        cx = (fw - sw) / 2 + self._pan.x()
        cy = (fh - sh) / 2 + self._pan.y()
        ifw, ifh = round(fw), round(fh)

        # Simple path: photo covers the whole frame
        if cx <= 0 and cy <= 0 and cx + sw >= fw and cy + sh >= fh:
            src_x = max(0, round(-cx / eff))
            src_y = max(0, round(-cy / eff))
            src_w = min(iw - src_x, round(fw / eff))
            src_h = min(ih - src_y, round(fh / eff))
            return self.pixmap.copy(src_x, src_y, src_w, src_h)

        # Exposed area: sample the photo's top edge for seamless fill colour
        scaled_for_sample = self.pixmap.scaled(
            round(sw), round(sh),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.FastTransformation,   # quick, only for sampling
        )
        top_rgb = _sample_top_rgb(scaled_for_sample, n_rows=5)

        bg = _noisy_fill(ifw, ifh, top_rgb)
        bg_img = QImage(bg.tobytes(), ifw, ifh, ifw * 3, QImage.Format.Format_RGB888)
        result  = QPixmap.fromImage(bg_img)

        scaled_photo = self.pixmap.scaled(
            round(sw), round(sh),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        p = QPainter(result)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(round(cx), round(cy), scaled_photo)
        p.end()
        return result

    # ── mouse / wheel events ──────────────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.pixmap:
            self._drag_start      = event.pos()
            self._drag_pan_start  = QPointF(self._pan)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag_start is None or not self.pixmap:
            return
        delta = event.pos() - self._drag_start
        self._pan = self._drag_pan_start + QPointF(delta)
        self._clamp_pan()
        self.update()
        self.crop_changed.emit()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)

    def mouseDoubleClickEvent(self, event) -> None:
        # Reset zoom and pan on double-click
        self._zoom = 1.0
        self._pan  = QPointF(0.0, 0.0)
        self.update()
        self.crop_changed.emit()

    def wheelEvent(self, event) -> None:
        if not self.pixmap:
            return
        # angleDelta is in eighths of a degree; one standard notch = 120 units
        steps = event.angleDelta().y() / 120.0
        self._zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, self._zoom + steps * _ZOOM_STEP))
        self._clamp_pan()
        self.update()
        self.crop_changed.emit()

    # ── painting ─────────────────────────────────────────────────────────────

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(60, 60, 60))

        frame = self._frame_rect()

        if self.pixmap:
            self._draw_photo(painter, frame)
        else:
            painter.fillRect(frame.toRect(), QColor(220, 220, 220))
            painter.setPen(QPen(QColor(160, 160, 160)))
            painter.drawText(
                frame, Qt.AlignmentFlag.AlignCenter,
                "拖入照片或點擊「載入照片」\n\n滾輪縮放 / 拖曳移動"
            )

        if self.show_spec_guide:
            self._draw_spec_guide(painter, frame)
        if self.show_contour_guide:
            self._draw_contour_guide(painter, frame)

        # Hint text (outlined for legibility over white backgrounds)
        if self.pixmap:
            f = QFont()
            f.setPointSize(8)
            painter.setFont(f)
            hint = f"縮放 {self._zoom:.1f}×  ·  滾輪縮放  ·  雙擊重置"
            hint_rect = frame.toRect().adjusted(4, 0, -4, -4)
            flags = Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight
            painter.setPen(QPen(_CLR_LABEL_HALO))
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                painter.drawText(hint_rect.adjusted(dx, dy, dx, dy), flags, hint)
            painter.setPen(QPen(QColor(60, 60, 60)))
            painter.drawText(hint_rect, flags, hint)

    def _draw_photo(self, painter: QPainter, frame: QRectF) -> None:
        fw, fh = frame.width(), frame.height()
        iw, ih = self.pixmap.width(), self.pixmap.height()
        eff = self._effective_scale(fw, fh, iw, ih)

        sw, sh = iw * eff, ih * eff
        cx = (fw - sw) / 2 + self._pan.x()
        cy = (fh - sh) / 2 + self._pan.y()

        painter.setClipRect(frame)

        # Fill any exposed area with the photo's top-edge colour (preview)
        if cx > 0 or cy > 0 or cx + sw < fw or cy + sh < fh:
            r, g, b = (int(v) for v in self._top_rgb)
            painter.fillRect(frame.toRect(), QColor(r, g, b))

        scaled = self.pixmap.scaled(
            int(sw), int(sh),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter.drawPixmap(int(frame.x() + cx), int(frame.y() + cy), scaled)
        painter.setClipping(False)

    def _draw_spec_guide(self, painter: QPainter, frame: QRectF) -> None:
        fx, fy = frame.x(), frame.y()
        fw, fh = frame.width(), frame.height()

        painter.setPen(QPen(_CLR_FRAME, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(frame)

        dashed = QPen(_CLR_GUIDE, 1.5, Qt.PenStyle.DashLine)

        # Crown zone shading
        zone_y0 = fy + HEAD_TOP_MIN_FRAC * fh
        zone_y1 = fy + HEAD_TOP_MAX_FRAC * fh
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(_CLR_ZONE))
        painter.drawRect(QRectF(fx, zone_y0, fw, zone_y1 - zone_y0))

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(dashed)
        painter.drawLine(QPointF(fx, zone_y0), QPointF(fx + fw, zone_y0))
        painter.drawLine(QPointF(fx, zone_y1), QPointF(fx + fw, zone_y1))

        chin_y = fy + CHIN_FROM_TOP_FRAC * fh
        painter.drawLine(QPointF(fx, chin_y), QPointF(fx + fw, chin_y))

        painter.setPen(QPen(_CLR_CENTER, 1, Qt.PenStyle.DashLine))
        cx_ = fx + fw / 2
        painter.drawLine(QPointF(cx_, fy), QPointF(cx_, fy + fh))

        font = QFont()
        font.setPointSize(9)
        font.setBold(True)
        painter.setFont(font)
        lx = fx + 5
        self._draw_label(painter, QPointF(lx, zone_y0 - 4), "頭頂上限")
        self._draw_label(painter, QPointF(lx, zone_y1 - 4), "頭頂下限")
        self._draw_label(painter, QPointF(lx, chin_y   - 4), "下巴線")

    def _draw_contour_guide(self, painter: QPainter, frame: QRectF) -> None:
        fx, fy = frame.x(), frame.y()
        fw, fh = frame.width(), frame.height()
        oval_w = fw * FACE_OVAL_WIDTH_FRAC
        oval_h = fh * (CHIN_FROM_TOP_FRAC - HEAD_TOP_MIN_FRAC)
        oval_rect = QRectF(
            fx + (fw - oval_w) / 2,
            fy + HEAD_TOP_MIN_FRAC * fh,
            oval_w, oval_h,
        )
        painter.setBrush(QBrush(QColor(255, 255, 255, 25)))
        painter.setPen(QPen(_CLR_OVAL, 2, Qt.PenStyle.DashLine))
        painter.drawEllipse(oval_rect)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _draw_label(
        self, painter: QPainter, pos: QPointF, text: str,
        fg: QColor = _CLR_LABEL,
    ) -> None:
        """Draw text with a white halo so it's legible over any background."""
        painter.setPen(QPen(_CLR_LABEL_HALO))
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (1, -1), (-1, 1), (1, 1)):
            painter.drawText(QPointF(pos.x() + dx, pos.y() + dy), text)
        painter.setPen(QPen(fg))
        painter.drawText(pos, text)

    def _frame_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        aw, ah = w * 0.92, h * 0.92
        if aw / ah > PHOTO_ASPECT:
            fh = ah;  fw = fh * PHOTO_ASPECT
        else:
            fw = aw;  fh = fw / PHOTO_ASPECT
        return QRectF((w - fw) / 2, (h - fh) / 2, fw, fh)

    def _effective_scale(self, fw: float, fh: float, iw: int, ih: int) -> float:
        return max(fw / iw, fh / ih) * self._zoom

    def _clamp_pan(self) -> None:
        if not self.pixmap:
            return
        frame = self._frame_rect()
        fw, fh = frame.width(), frame.height()
        iw, ih = self.pixmap.width(), self.pixmap.height()
        eff = self._effective_scale(fw, fh, iw, ih)
        sw, sh = iw * eff, ih * eff

        # Horizontal: photo must always cover left and right edges
        max_px = max(0.0, (sw - fw) / 2)

        # Vertical:
        #   - Photo must cover the BOTTOM (no dark gap below)
        #   - TOP may be exposed (user drags photo down to add crown space)
        #     — exposed pixels are filled with noisy white in crop_pixmap()
        max_py_bottom = max(0.0, (sh - fh) / 2)         # covers bottom
        max_py_top    = max_py_bottom + fh * _TOP_EXTRA  # allows top exposure

        self._pan = QPointF(
            max(-max_px,       min(max_px,       self._pan.x())),
            max(-max_py_bottom, min(max_py_top,  self._pan.y())),
        )
