"""Locates HP bars in a battle-scene zone and reads their fill fraction.

Robust against PRO's shifting layout: we search for the longest contiguous
run of HP-colored (green/yellow/orange/red) pixels row by row, then expand
to the bar track with a hard cap so dark UI rows can't swallow the measure.
"""


def _hp_colored(r, g, b):
    if g > 100 and g > r + 25 and g > b + 25:          # green
        return True
    if r > 140 and g > 120 and b < 100:                # yellow
        return True
    if r > 140 and g < 120 and b < 110:                # orange/red
        return True
    return False


def _track(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    return mx < 100 and (mx - mn) < 30                 # dark gray track


def locate_bar(img, min_run=30):
    """Returns dict(frac, y, x0, x1) for the strongest HP bar, else None.
    Scans at half resolution for speed; returned coords are in original pixels."""
    try:
        img = img.convert("RGB")
        w, h = img.size
        scale = 2 if w > 400 else 1
        if scale == 2:
            img = img.resize((w // 2, h // 2))
        w, h = img.size
        px = img.load()
        best = None  # (run_len, y, x0, x1)
        for y in range(h):
            run = 0
            start = 0
            best_a, best_b = 0, 0
            for x in range(w + 1):
                on = x < w and _hp_colored(*px[x, y])
                if on:
                    if run == 0:
                        start = x
                    run += 1
                else:
                    if run > best_b - best_a:
                        best_a, best_b = start, start + run
                    run = 0
            if best_b - best_a > (best[0] if best else 0):
                best = (best_b - best_a, y, best_a, best_b)
        if not best or best[0] * scale < min_run:
            return None
        run, y, bx0, bx1 = best
        cap = run * 1.6
        x0 = bx0
        x1 = bx1
        while x0 > 0 and (x1 - x0) < cap and (_hp_colored(*px[x0 - 1, y]) or _track(*px[x0 - 1, y])):
            x0 -= 1
        while x1 < w and (x1 - x0) < cap and (_hp_colored(*px[x1, y]) or _track(*px[x1, y])):
            x1 += 1
        colored = sum(1 for x in range(x0, x1) if _hp_colored(*px[x, y]))
        frac = colored / max(1, (x1 - x0))
        return {
            "frac": max(0.0, min(1.0, frac)),
            "y": y * scale,
            "x0": x0 * scale,
            "x1": x1 * scale,
            "scale": scale,
        }
    except Exception:
        return None
