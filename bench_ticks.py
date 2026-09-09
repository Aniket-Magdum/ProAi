"""5-tick latency benchmark: measures real per-tick cost on this machine."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import Coach

c = Coach(headless=True)
timings = []
for i in range(5):
    t0 = time.time()
    c.tick()
    timings.append(time.time() - t0)
    time.sleep(0.4)

print("tick seconds:", [round(t, 2) for t in timings])
print(f"mean: {sum(timings)/len(timings):.2f}s  max: {max(timings):.2f}s")
