import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import Coach

c = Coach(debug=True, headless=True)
for i in range(4):
    print(f"tick {i}")
    c.tick()
    time.sleep(1)

print("=== state.txt ===")
print(Path("state.txt").read_text(encoding="utf8"))
