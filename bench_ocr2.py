"""Bench2: OCR configs on LIVE game pixels (fallback: synthetic image)."""
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach import capture, ocr

hwnd = capture.find_pro_hwnd()
live = None
if hwnd:
    regions = capture.grab_regions(hwnd, {"log": (0.0, 0.56, 0.40, 1.0)})
    live = regions.get("log")
    if live is not None:
        print(f"captured live log region: {live.width}x{live.height}")


def synthetic(w, h):
    img = Image.new("RGB", (w, h), (20, 24, 30))
    d = ImageDraw.Draw(img)
    lines = [
        "The opposing Garchomp attacks Pikachu with Earthquake.",
        "It is super effective!",
        "Pikachu has fainted!",
        "Flash001 sends out Manaphy!",
        "Go, Zapdos!",
        "Manaphy restored HP using Leftovers!",
        "Battle turn #12 ended.",
    ]
    y = 10
    for t in lines:
        d.text((8, y), t, fill=(220, 225, 230))
        y += (h - 20) // len(lines)
    return img


if live is None or live.width < 50:
    print("no live capture - using synthetic")
    live = synthetic(410, 280)

from rapidocr_onnxruntime import RapidOCR


def prep(img, scale):
    im = img.convert("L")
    if scale != 1:
        im = im.resize((im.width * scale, im.height * scale))
    from PIL import ImageOps

    return np.asarray(ImageOps.autocontrast(im))


def bench(name, img, **kw):
    eng = RapidOCR(**kw)
    arr = prep(img, kw.pop("scale", 2))
    eng(arr)
    ts = []
    texts = None
    for _ in range(3):
        t0 = time.time()
        res, _ = eng(arr)
        ts.append(time.time() - t0)
        texts = [r[1] for r in res] if res else []
    print(f"{name:24s} {[round(t, 2) for t in ts]}  lines={len(texts)}")
    for t in texts[:4]:
        print(f"    | {t}")


print("\n=== default (current prod-like): scale2, full engine ===")
bench("s2 default", live)
print("\n=== tuned candidates ===")
bench("s1 det320-max", live, scale=1, use_cls=False,
      det_limit_side_len=320, det_limit_type="max")
bench("s1.5 det320-max", live, scale=1.5, use_cls=False,
      det_limit_side_len=320, det_limit_type="max")
bench("s2 det320-max", live, scale=2, use_cls=False,
      det_limit_side_len=320, det_limit_type="max")
