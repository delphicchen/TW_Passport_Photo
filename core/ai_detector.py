"""
Heuristic AI-editing detector.

SynthID's invisible pixel watermark cannot be reliably detected without
Google's proprietary model.  This module instead inspects EXIF/metadata
and reports any signals that suggest AI processing.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image
from PIL.ExifTags import TAGS

# Keywords that commonly appear in AI-tool metadata
_AI_KEYWORDS = re.compile(
    r"gemini|bard|imagen|stable.?diffusion|midjourney|dall.?e|firefly"
    r"|generative|ai.generated|synthid|deepmind|openai|runwayml"
    r"|adobe.generative|canva.ai",
    re.IGNORECASE,
)

_GOOGLE_KEYWORDS = re.compile(r"google|goog", re.IGNORECASE)


@dataclass
class DetectionResult:
    has_ai_metadata: bool = False
    software_tag: str = ""
    artist_tag: str = ""
    comment_tag: str = ""
    copyright_tag: str = ""
    suspicious_fields: list[str] = field(default_factory=list)
    all_metadata: dict[str, str] = field(default_factory=dict)
    synthid_note: str = (
        "SynthID 隱形浮水印需要 Google 的專有偵測器，"
        "目前無法透過第三方工具可靠偵測。"
    )


def detect(image_path: str | Path) -> DetectionResult:
    result = DetectionResult()

    try:
        img = Image.open(image_path)
    except Exception:
        return result

    # ── Collect all readable EXIF tags ──────────────────────────────────────
    raw_exif: dict = {}
    try:
        exif_data = img._getexif() or {}
        for tag_id, value in exif_data.items():
            tag_name = TAGS.get(tag_id, str(tag_id))
            str_val = str(value)
            raw_exif[tag_name] = str_val
    except Exception:
        pass

    # Also grab PNG text chunks or JPEG comments
    info = getattr(img, "info", {}) or {}
    for k, v in info.items():
        raw_exif[str(k)] = str(v)

    result.all_metadata = raw_exif

    # ── Extract key fields ───────────────────────────────────────────────────
    result.software_tag  = raw_exif.get("Software", "")
    result.artist_tag    = raw_exif.get("Artist", "")
    result.comment_tag   = raw_exif.get("UserComment", raw_exif.get("Comment", ""))
    result.copyright_tag = raw_exif.get("Copyright", "")

    # ── Check for AI / Google signals ────────────────────────────────────────
    fields_to_scan = {
        "Software":    result.software_tag,
        "Artist":      result.artist_tag,
        "Comment":     result.comment_tag,
        "Copyright":   result.copyright_tag,
        **{k: v for k, v in raw_exif.items()
           if k not in ("Software", "Artist", "UserComment", "Comment", "Copyright")},
    }

    for field_name, value in fields_to_scan.items():
        if _AI_KEYWORDS.search(value) or _GOOGLE_KEYWORDS.search(value):
            result.suspicious_fields.append(f"{field_name}: {value[:120]}")

    result.has_ai_metadata = bool(result.suspicious_fields)
    return result
