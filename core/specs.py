# ROC Passport photo specifications (中華民國護照照片規格)

PHOTO_WIDTH_MM  = 35
PHOTO_HEIGHT_MM = 45
PHOTO_ASPECT    = PHOTO_WIDTH_MM / PHOTO_HEIGHT_MM   # ≈ 0.778 (portrait)
PRINT_DPI       = 600

# Output pixel dimensions at 600 DPI
OUT_W_PX = round(PHOTO_WIDTH_MM  / 25.4 * PRINT_DPI)  # 827
OUT_H_PX = round(PHOTO_HEIGHT_MM / 25.4 * PRINT_DPI)  # 1063

# Face height (chin → crown): 32–36 mm
FACE_MIN_MM = 32
FACE_MAX_MM = 36

# ── Guide fractions (measured from top of photo frame) ──────────────────────
#
#   7% ┬ HEAD_TOP_MIN_FRAC  (crown upper bound: largest face 36mm)
#  16% ┼ HEAD_TOP_MAX_FRAC  (crown lower bound: smallest face 32mm)
#      │   ← green zone: place crown anywhere in this band
#  38% ┼ EYE_LINE_FRAC      (approximate eye level)
#  87% ┼ CHIN_FROM_TOP_FRAC (chin; 13% from bottom)
# 100% ┘

CHIN_FROM_TOP_FRAC   = 1 - 0.13
HEAD_TOP_MIN_FRAC    = CHIN_FROM_TOP_FRAC - FACE_MAX_MM / PHOTO_HEIGHT_MM  # ≈ 0.07
HEAD_TOP_MAX_FRAC    = CHIN_FROM_TOP_FRAC - FACE_MIN_MM / PHOTO_HEIGHT_MM  # ≈ 0.16
EYE_LINE_FRAC        = 0.38

FACE_OVAL_WIDTH_FRAC = 0.60
