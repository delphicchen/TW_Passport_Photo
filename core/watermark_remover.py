"""
Gemini visible-watermark removal.

Two backends:
  1. gwt-mini CLI binary  (higher quality, AI denoising)
  2. Python/PIL/numpy     (built-in fallback — no download required)

Algorithm (both backends):
  Gemini adds a logo via alpha blending:
      watermarked = α·logo + (1−α)·original
  We reverse this by sampling the background colour from pixels adjacent
  to the watermark region, then filling according to the logo mask weight:
      restored ≈ (watermarked − α·logo_norm·bg) / (1−α·logo_norm)

Watermark placement (bottom-right corner):
  48×48 mask + 32 px margin  if min(W,H) ≤ 1024
  96×96 mask + 64 px margin  otherwise

NOTE: SynthID (Google's invisible pixel watermark) is NOT removed here.
"""

from __future__ import annotations

import os
import platform
import stat
import subprocess
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# ── paths ─────────────────────────────────────────────────────────────────────
def _assets_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        d = Path.home() / ".tw_passport_photo" / "assets"
    else:
        d = Path(__file__).parent.parent / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d

_ASSETS  = _assets_dir()
_BIN_DIR = Path(__file__).parent.parent / "bin"

# gwt-mini release
_VERSION = "v0.2.7"
_BASE_URL = (
    "https://github.com/allenk/GeminiWatermarkTool"
    f"/releases/download/{_VERSION}"
)
_BINARY_MAP = {
    "linux":  "gwt-mini-linux-x64",
    "darwin": "gwt-mini-macos-universal",
    "win32":  "gwt-mini-windows-x64.exe",
}


@dataclass
class RemovalResult:
    success: bool
    output_path: str = ""
    message: str = ""


_rng = np.random.default_rng()   # for subtle grain in the inpainted fill


# ── gwt-mini binary helpers ───────────────────────────────────────────────────

def _platform_key() -> str:
    s = platform.system().lower()
    return "win32" if "win" in s else ("darwin" if s == "darwin" else "linux")


def binary_path() -> Path | None:
    p = _BIN_DIR / _BINARY_MAP[_platform_key()]
    return p if p.exists() else None


def binary_download_url() -> str:
    return f"{_BASE_URL}/{_BINARY_MAP[_platform_key()]}"


def download_binary(progress_cb=None) -> tuple[bool, str]:
    _BIN_DIR.mkdir(exist_ok=True)
    dest = _BIN_DIR / _BINARY_MAP[_platform_key()]
    try:
        def _hook(count, block, total):
            if progress_cb and total > 0:
                progress_cb(min(100, count * block * 100 // total))

        urllib.request.urlretrieve(binary_download_url(), dest, reporthook=_hook)
        if _platform_key() != "win32":
            dest.chmod(dest.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        return True, str(dest)
    except Exception as exc:
        return False, str(exc)


# ── pure-Python backend ───────────────────────────────────────────────────────

def _load_mask(mask_size: int) -> np.ndarray | None:
    """Return (H,W) float32 mask in [0,1], or None if unavailable."""
    from core.mask_fetcher import masks_ready, fetch_masks
    if not masks_ready():
        fetch_masks()       # silent best-effort download
    p = _ASSETS / f"bg_{mask_size}.png"
    if not p.exists():
        return None
    logo = np.array(Image.open(p).convert("L"), dtype=np.float32) / 255.0
    return logo


def _sample_background(arr: np.ndarray, x0: int, y0: int, ms: int,
                        border: int = 20) -> np.ndarray:
    """Median colour of pixels just outside the watermark bounding box."""
    ih, iw = arr.shape[:2]
    bx0 = max(0, x0 - border)
    by0 = max(0, y0 - border)
    bx1 = min(iw, x0 + ms + border)
    by1 = min(ih, y0 + ms + border)

    patch = arr[by0:by1, bx0:bx1].astype(np.float32)  # (h, w, 3)
    ph, pw = patch.shape[:2]

    # Mark pixels that belong to the watermark area as invalid
    lx0 = x0 - bx0
    ly0 = y0 - by0
    valid = np.ones((ph, pw), dtype=bool)
    valid[ly0:ly0 + ms, lx0:lx0 + ms] = False

    pixels = patch[valid]  # (N, 3)
    return np.median(pixels, axis=0)  # shape (3,)


def remove_watermark_python(input_path: str) -> RemovalResult:
    """Remove watermark without any external binary.

    Works best on near-white or near-uniform backgrounds (typical passport photos).
    """
    try:
        img = Image.open(input_path).convert("RGB")
        iw, ih = img.size

        if iw <= 1024 or ih <= 1024:
            ms, margin = 48, 32
        else:
            ms, margin = 96, 64

        x0 = iw - ms - margin
        y0 = ih - ms - margin

        if x0 < 0 or y0 < 0:
            return RemovalResult(success=False, message="圖片太小，無法定位浮水印區域")

        logo_mask = _load_mask(ms)          # (ms, ms) float32 [0,1] or None
        if logo_mask is None:
            return RemovalResult(success=False,
                                 message="無法取得 Gemini mask 資料（需要網路連線）")

        arr = np.array(img, dtype=np.float32)

        # Estimate background colour from surrounding area
        bg = _sample_background(arr, x0, y0, ms)  # (3,)

        # Convert logo mask to fill weight.
        # Use a steep curve: pixels with mask > ~0.15 get nearly full replacement.
        # This ensures single-pass removal even for strong logo pixels.
        fill_weight = np.clip(logo_mask * 4.0, 0.0, 1.0)  # aggressive ramp
        alpha_fill = fill_weight[..., np.newaxis]          # (ms, ms, 1)

        region = arr[y0:y0 + ms, x0:x0 + ms].copy()
        region = region * (1.0 - alpha_fill) + bg * alpha_fill

        arr[y0:y0 + ms, x0:x0 + ms] = region

        # Soften the hard boundary of the filled region
        _smooth_boundary(arr, x0, y0, ms, radius=3)

        out_img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

        suffix = Path(input_path).suffix or ".jpg"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.close()
        out_img.save(tmp.name)
        return RemovalResult(success=True, output_path=tmp.name)

    except Exception as exc:
        return RemovalResult(success=False, message=str(exc))


def _smooth_boundary(arr: np.ndarray, x0: int, y0: int, ms: int,
                     radius: int = 3) -> None:
    """Gaussian-blend a thin band at the edge of the filled region."""
    from PIL import ImageFilter
    ih, iw = arr.shape[:2]
    pad = radius * 2
    bx0 = max(0, x0 - pad)
    by0 = max(0, y0 - pad)
    bx1 = min(iw, x0 + ms + pad)
    by1 = min(ih, y0 + ms + pad)

    patch = Image.fromarray(np.clip(arr[by0:by1, bx0:bx1], 0, 255).astype(np.uint8))
    blurred = patch.filter(ImageFilter.GaussianBlur(radius=radius))

    # Create blend weight: 1 inside boundary strip, 0 elsewhere
    ph, pw = by1 - by0, bx1 - bx0
    blend = np.zeros((ph, pw), dtype=np.float32)
    lx0, ly0 = x0 - bx0, y0 - by0
    lx1, ly1 = lx0 + ms, ly0 + ms
    for r in range(radius):
        w = (radius - r) / radius
        # top/bottom/left/right strips
        if ly0 + r < ph:
            blend[ly0 + r, max(0, lx0):min(pw, lx1)] = w
        if ly1 - 1 - r >= 0:
            blend[ly1 - 1 - r, max(0, lx0):min(pw, lx1)] = w
        if lx0 + r < pw:
            blend[max(0, ly0):min(ph, ly1), lx0 + r] = w
        if lx1 - 1 - r >= 0:
            blend[max(0, ly0):min(ph, ly1), lx1 - 1 - r] = w

    blend = blend[..., np.newaxis]
    blurred_arr = np.array(blurred, dtype=np.float32)
    orig_arr    = arr[by0:by1, bx0:bx1]
    arr[by0:by1, bx0:bx1] = orig_arr * (1 - blend) + blurred_arr * blend


# ── manual region removal (user-marked box) ───────────────────────────────────

def _resize_rgb(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    im = im.resize((max(1, w), max(1, h)), Image.BILINEAR)
    return np.asarray(im, dtype=np.float32)


def _resize_mask(mask: np.ndarray, w: int, h: int) -> np.ndarray:
    im = Image.fromarray((mask * 255).astype(np.uint8))
    im = im.resize((max(1, w), max(1, h)), Image.NEAREST)
    return np.asarray(im) > 127


def _dilate_mask(mask: np.ndarray, r: int) -> np.ndarray:
    """Grow the mask by r pixels so a slightly-too-small box still covers the mark."""
    if r <= 0:
        return mask
    from PIL import ImageFilter
    im = Image.fromarray((mask * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MaxFilter(2 * r + 1))
    return np.asarray(im) > 127


def _inpaint_diffuse(sub: np.ndarray, mask: np.ndarray,
                     iterations: int = 64) -> np.ndarray:
    """Fill masked pixels by solving Laplace's equation (diffusion inpaint).

    Coarse-to-fine (multiscale) so large regions converge in a fixed number of
    iterations.  Known surrounding pixels act as the boundary condition, so the
    filled patch is seamless at its edge.  Pure numpy/PIL — no external deps.
    """
    h, w = mask.shape
    out = sub.copy()
    if not mask.any():
        return out

    known = ~mask
    # Coarse solve gives the low-frequency fill as an initial guess.
    if max(h, w) > 24 and known.any():
        ch, cw = max(1, h // 2), max(1, w // 2)
        coarse = _inpaint_diffuse(
            _resize_rgb(sub, cw, ch), _resize_mask(mask, cw, ch), iterations
        )
        out[mask] = _resize_rgb(coarse, w, h)[mask]
    elif known.any():
        out[mask] = sub[known].mean(axis=0)
    else:
        out[mask] = 255.0

    # Jacobi relaxation toward the Laplace solution (edge-replicated borders).
    for _ in range(iterations):
        p = np.pad(out, ((1, 1), (1, 1), (0, 0)), mode="edge")
        avg = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]) * 0.25
        out[mask] = avg[mask]
    return out


def remove_watermark_region(input_path: str,
                            rect: tuple[int, int, int, int]) -> RemovalResult:
    """Remove a watermark from a user-marked rectangle (image-pixel coords).

    Unlike :func:`remove_watermark`, this does not assume a fixed corner or a
    known logo mask — it inpaints whatever the user boxed.  Works best when the
    box sits on a fairly uniform background (typical passport photos).

    ``rect`` is ``(x, y, w, h)`` in original-image pixels.
    """
    try:
        x, y, w, h = (int(round(v)) for v in rect)
        img = Image.open(input_path).convert("RGB")
        arr = np.array(img, dtype=np.float32)
        ih, iw = arr.shape[:2]

        x0, y0 = max(0, x), max(0, y)
        x1, y1 = min(iw, x + w), min(ih, y + h)
        if x1 - x0 < 1 or y1 - y0 < 1:
            return RemovalResult(success=False, message="標記區域無效")

        # Work on a padded sub-image so diffusion has a ring of known pixels.
        pad = 12
        bx0, by0 = max(0, x0 - pad), max(0, y0 - pad)
        bx1, by1 = min(iw, x1 + pad), min(ih, y1 + pad)

        sub = arr[by0:by1, bx0:bx1].copy()
        mask = np.zeros(sub.shape[:2], dtype=bool)
        mask[y0 - by0:y1 - by0, x0 - bx0:x1 - bx0] = True
        mask = _dilate_mask(mask, 3)

        solved = _inpaint_diffuse(sub, mask, iterations=64)

        # Add subtle grain matched to the surrounding area so the fill doesn't
        # read as an obviously smooth patch on a slightly noisy background.
        ring = sub[~mask]
        sigma = float(min(ring.std(), 6.0)) if ring.size else 0.0
        if sigma > 0:
            noise = _rng.standard_normal(solved.shape).astype(np.float32) * sigma
            solved[mask] += noise[mask]

        out = sub.copy()
        out[mask] = solved[mask]
        arr[by0:by1, bx0:bx1] = out

        out_img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
        suffix = Path(input_path).suffix or ".jpg"
        tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
        tmp.close()
        out_img.save(tmp.name)
        return RemovalResult(success=True, output_path=tmp.name)

    except Exception as exc:
        return RemovalResult(success=False, message=str(exc))


# ── unified entry point ───────────────────────────────────────────────────────

def remove_watermark(input_path: str, use_binary: bool = True,
                     denoise: bool = False) -> RemovalResult:
    """Remove Gemini watermark. Falls back to Python if binary unavailable."""
    if use_binary:
        bin_p = binary_path()
        if bin_p is not None:
            suffix = Path(input_path).suffix or ".jpg"
            tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
            tmp.close()
            cmd = [str(bin_p), "-i", input_path, "-o", tmp.name]
            if denoise:
                cmd += ["--denoise", "ai"]
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                if r.returncode == 0 and Path(tmp.name).stat().st_size > 0:
                    return RemovalResult(success=True, output_path=tmp.name)
            except Exception:
                pass  # fall through to Python backend

    return remove_watermark_python(input_path)
