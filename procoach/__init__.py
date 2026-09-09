"""PRO Instant Coach - local battle assistant for Pokemon Revolution Online."""
import time
from pathlib import Path

ERROR_LOG = Path(__file__).resolve().parent.parent / "coach_errors.log"


def log_error(msg):
    """Append an error to coach_errors.log - failures are never fully silent."""
    try:
        with open(ERROR_LOG, "a", encoding="utf8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")
    except Exception:
        pass
