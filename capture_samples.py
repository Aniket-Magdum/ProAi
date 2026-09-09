"""Captures live PRO regions to data/samples/ and validates fast-OCR vs quality-OCR
on real battle-log text. Run while the game is visible with the Battle Log open."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach import capture, ocr

OUT = Path(__file__).resolve().parent / "data" / "samples"
OUT.mkdir(exist_ok=True)

hwnd = capture.find_pro_hwnd()
if not hwnd:
    print("PROClient not found - open the game first")
    sys.exit(1)

regions = capture.grab_regions(hwnd)
if not regions:
    print("could not capture window")
    sys.exit(1)

for name, img in regions.items():
    p = OUT / f"{name}_{int(time.time())}.png"
    img.save(p)
    print(f"saved {p.name} ({img.width}x{img.height})")

log = regions.get("log")
if log is not None and log.width > 50:
    print("\n=== quality engine (scale=2, old config) ===")
    t0 = time.time()
    q = ocr.read_image(log, scale=2, fast=False)
    print(f"[{time.time()-t0:.2f}s]")
    print(q or "(nothing)")

    print("\n=== fast engine (scale=1, new config) ===")
    t0 = time.time()
    f = ocr.read_image(log, scale=1, fast=True)
    print(f"[{time.time()-t0:.2f}s]")
    print(f or "(nothing)")
