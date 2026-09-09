"""Benchmarks RapidOCR engine configs on a synthetic PRO-log-like image."""
import time

import numpy as np
from PIL import Image, ImageDraw

W, H = 820, 560  # log panel at scale=2
img = Image.new("RGB", (W, H), (20, 24, 30))
d = ImageDraw.Draw(img)
lines = [
    "The opposing Garchomp attacks Pikachu with Earthquake.",
    "It's super effective!",
    "Pikachu has fainted!",
    "Flash001 sends out Manaphy!",
    "Go, Zapdos!",
    "Manaphy restored HP using Leftovers!",
    "Battle turn #12 ended.",
    "Thunder Wave paralyzed the foe!",
]
y = 12
for t in lines:
    d.text((10, y), t, fill=(220, 225, 230))
    y += 40
arr = np.asarray(img.convert("L"))

from rapidocr_onnxruntime import RapidOCR


def bench(name, **kw):
    eng = RapidOCR(**kw)
    # warmup inference (loads + allocates model graph)
    t0 = time.time()
    eng(arr)
    warm = time.time() - t0
    times = []
    for _ in range(3):
        t0 = time.time()
        res, _ = eng(arr)
        times.append(time.time() - t0)
    n_lines = len(res) if res else 0
    print(f"{name:38s} warm={warm:5.2f}s  calls={[round(t,2) for t in times]}  lines={n_lines}")


bench("default")
bench("no-cls", use_cls=False)
bench("no-cls + det480", use_cls=False, det_limit_side_len=480)
bench("no-cls + det320", use_cls=False, det_limit_side_len=320)
bench("no-cls + det480 + 2threads", use_cls=False, det_limit_side_len=480,
      intra_op_num_threads=2)
bench("no-cls + det480 + 1thread", use_cls=False, det_limit_side_len=480,
      intra_op_num_threads=1)
