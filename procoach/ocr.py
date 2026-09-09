"""OCR: RapidOCR (ONNX, pip-only) with light preprocessing.

PRO's panels are dark with colored text; we upscale, grayscale and
autocontrast before recognition. RapidOCR takes numpy arrays (RGB).
"""
import numpy as np
from PIL import Image, ImageOps

_engines = {}


def _get_engine(fast=False):
    """fast=True: tuned for the big log region (no cls, small det input).
    fast=False: quality engine for small accuracy-critical crops."""
    key = "fast" if fast else "quality"
    if key not in _engines:
        from rapidocr_onnxruntime import RapidOCR

        if fast:
            _engines[key] = RapidOCR(
                use_cls=False,
                det_limit_side_len=320,
                det_limit_type="max",
            )
        else:
            _engines[key] = RapidOCR(use_cls=False)
    return _engines[key]


def _preprocess(img: Image.Image, scale: int = 3) -> Image.Image:
    img = img.convert("L")
    img = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    return ImageOps.autocontrast(img)


def read_image(img: Image.Image, scale: int = 3, fast: bool = False) -> str:
    """OCR a PIL image, returning newline-joined text. Empty string on failure."""
    try:
        result, _ = _get_engine(fast)(np.asarray(_preprocess(img, int(scale))))
        if not result:
            return ""
        return "\n".join(str(line[1]) for line in result).strip()
    except Exception:
        return ""


def warmup() -> bool:
    try:
        _get_engine(fast=False)
        _get_engine(fast=True)
        return True
    except Exception:
        return False
