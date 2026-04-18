"""
Downloads Gemini logo mask PNGs from GeminiWatermarkTool at first use.

Masks are NOT bundled in the repo to avoid distributing Google's trademark
assets.  They are fetched once from the MIT-licensed GWT source and cached
locally in assets/.  Subsequent runs use the local cache.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.request
from pathlib import Path

_ASSETS  = Path(__file__).parent.parent / "assets"
_HPP_URL = (
    "https://api.github.com/repos/allenk/GeminiWatermarkTool"
    "/contents/assets/embedded_assets.hpp"
)


def masks_ready() -> bool:
    return (_ASSETS / "bg_48.png").exists() and (_ASSETS / "bg_96.png").exists()


def fetch_masks(progress_cb=None) -> tuple[bool, str]:
    """
    Download and extract both mask PNGs.
    Returns (ok, error_message).
    progress_cb(pct: int) is called with 0..100 if provided.
    """
    _ASSETS.mkdir(exist_ok=True)

    try:
        if progress_cb:
            progress_cb(5)

        req = urllib.request.Request(
            _HPP_URL,
            headers={
                "Accept":     "application/vnd.github.v3+json",
                "User-Agent": "passport-photo-tool/1.0",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())

        if progress_cb:
            progress_cb(50)

        hpp: str = base64.b64decode(data["content"]).decode("utf-8")

        def _extract(name: str) -> bytes | None:
            m = re.search(
                rf"inline constexpr unsigned char {name}\[\]\s*=\s*\{{([^}}]+)\}}",
                hpp,
                re.DOTALL,
            )
            if not m:
                return None
            vals = [
                int(x.strip(), 16)
                for x in m.group(1).split(",")
                if x.strip().startswith("0x")
            ]
            return bytes(vals)

        b48 = _extract("bg_48_png")
        b96 = _extract("bg_96_png")

        if not b48 or not b96:
            return False, "無法從 hpp 解析 mask 資料"

        (_ASSETS / "bg_48.png").write_bytes(b48)
        (_ASSETS / "bg_96.png").write_bytes(b96)

        if progress_cb:
            progress_cb(100)
        return True, ""

    except Exception as exc:
        return False, str(exc)
