"""One-shot OCR validation against the live PROClient window."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach import capture, ocr

hwnd = capture.find_pro_hwnd()
if not hwnd:
    print("PROClient window not found - is the game open?")
    sys.exit(1)

print("window ok")
print("OCR engine:", "ok" if ocr.warmup() else "UNAVAILABLE")

regions = capture.grab_regions(hwnd)
for name, img in regions.items():
    text = ocr.read_image(img)
    print(f"--- {name} ({img.width}x{img.height}) ---")
    print(text or "(nothing read)")
