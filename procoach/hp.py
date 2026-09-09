"""Locates HP bars in a battle-scene zone and reads their fill fraction.

Robust against PRO's shifting layout: we search for the longest contiguous
run of HP-colored (green/yellow/orange/red) pixels row by row, then expand
to the bar track with a hard cap so dark UI rows can't swallow the measure.
All pixel classification is NumPy-vectorized (this runs every tick).
"""
import numpy as np


def _masks(img):
    a = np.asarray(img.convert("RGB"), dtype=np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    colored = (g > 100) & (g > r + 25) & (g > b + 25)
    colored |= (r > 140) & (g > 120) & (b < 100)
    colored |= (r > 140) & (g < 120) & (b < 110)
    mx = a.max(axis=2)
    mn = a.min(axis=2)
    track = (mx < 100) & ((mx - mn) < 30)
    return colored, track


def locate_bar(img, min_run=30):
    """Returns dict(frac, y, x0, x1) for the strongest HP bar, else None.
    Scans at half resolution for speed; returned coords are in original pixels."""
    try:
        img = img.convert("RGB")
        orig_w = img.width
        scale = 2 if orig_w > 400 else 1
        if scale == 2:
            img = img.resize((orig_w // 2, img.height // 2))
        colored, track = _masks(img)
        h, w = colored.shape

        counts = colored.sum(axis=1)
        y = int(counts.argmax())
        if counts[y] * scale < min_run:
            return None

        row = colored[y]
        # longest colored run on that row (vectorized run boundaries)
        padded = np.concatenate(([False], row, [False])).astype(np.int8)
        d = np.diff(padded)
        starts = np.where(d == 1)[0]
        ends = np.where(d == -1)[0]
        lens = ends - starts
        i = int(lens.argmax())
        bx0, bx1 = int(starts[i]), int(ends[i])

        run = bx1 - bx0
        cap = run * 1.6
        ext = row | track[y]
        x0, x1 = bx0, bx1
        while x0 > 0 and (x1 - x0) < cap and ext[x0 - 1]:
            x0 -= 1
        while x1 < w and (x1 - x0) < cap and ext[x1]:
            x1 += 1
        frac = row[x0:x1].sum() / max(1, x1 - x0)
        return {
            "frac": max(0.0, min(1.0, float(frac))),
            "y": y * scale,
            "x0": x0 * scale,
            "x1": x1 * scale,
            "scale": scale,
        }
    except Exception:
        return None
