# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## Architecture

```
main.py                     Entry point (QApplication + MainWindow, global font +2pt)
core/
  specs.py                  ROC passport photo constants (sizes, guide fractions)
  ai_detector.py            EXIF/metadata scan for AI-editing signals
  mask_fetcher.py           Downloads Gemini logo masks at first use (not bundled)
  watermark_remover.py      Python-native watermark removal; optional gwt-mini binary
ui/
  main_window.py            Main window — sidebar | PhotoCanvas | PreviewPanel
  photo_canvas.py           Editing canvas: pan/zoom, guide overlays, noisy-fill padding
  preview_panel.py          Live 35×45 crop preview (right panel)
  ai_panel.py               AI detection badge + EXIF detail
  print_sheet.py            4×6 landscape print-sheet dialog (4 cols × 2 rows)
assets/                     Gemini mask PNGs — gitignored, fetched at runtime
bin/                        gwt-mini binaries — gitignored, optional quality upgrade
```

## Key design decisions

**Guide coordinate system** — all overlay positions are fractions of the frame height/width in `core/specs.py`. The canvas converts fractions to pixels in `paintEvent`. Never hardcode pixel positions.

**Photo display** — `PhotoCanvas._frame_rect()` computes the largest 35:45 rect that fits within the widget (8% margin). The photo renders in *cover* mode (KeepAspectRatioByExpanding + clip).

**Pan/zoom** — scroll wheel adjusts zoom by 1% per notch (`_ZOOM_STEP = 0.01`). The bottom of the photo is always clamped to the frame bottom; the top may be exposed (up to 45% of frame height) so the user can add crown space.

**Noisy top fill** — when the top of the frame is exposed, `crop_pixmap()` fills that area with Gaussian noise (σ=5) centred on the median colour of the photo's top 5 rows, avoiding a visible seam. The canvas preview uses the same base colour (without per-pixel noise) so it doesn't flicker during drag.

**Watermark removal** — pure-Python backend (PIL + numpy) using the Gemini logo mask fetched from GeminiWatermarkTool. An optional gwt-mini CLI binary can be placed in `bin/` for higher-quality removal (AI denoising). The mask PNGs are downloaded by `core/mask_fetcher.py` on first use and cached in `assets/`.

**Save output** — `_save_photo` calls `canvas.crop_pixmap()`, which returns the user-adjusted crop (including any noisy fill), then resizes to 827×1063 px at 600 DPI via Pillow.

**Print sheet** — `ui/print_sheet.py` composes a 1800×1200 px image (4×6 in landscape @ 300 DPI) with 8 slots arranged in 4 cols × 2 rows. Each slot accepts an independent photo; PIL handles the final compositing.

## ROC passport photo spec

| Field | Value |
|---|---|
| Size | 35 × 45 mm |
| Face height (chin → crown) | 32–36 mm |
| Print resolution | 600 DPI |
| Output pixels | 827 × 1063 |
| Background | White or near-white |
