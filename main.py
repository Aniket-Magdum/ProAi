"""PRO Instant Coach - main loop.

Watches the PROClient window: cheap pixel scans every tick (HP bars),
OCR only on small label crops with throttles, keeps the scout sheet,
shows instant advice in an overlay and writes state.txt for the chat AI.
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach import capture, hp, ocr
from procoach.advisor import advise
from procoach.state import BattleState

STATE_FILE = Path(__file__).resolve().parent / "state.txt"
LOCK_FILE = Path(__file__).resolve().parent / "coach.lock"


def acquire_single_instance():
    """Refuses to start if another live coach process holds the lock."""
    import ctypes
    import os

    if LOCK_FILE.exists():
        try:
            pid = int(LOCK_FILE.read_text().strip())
            if pid != os.getpid():
                handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    ctypes.windll.kernel32.CloseHandle(handle)
                    print(f"Coach already running (PID {pid}) - close it first "
                          f"(✕ button on the overlay) or run: taskkill /f /im python.exe")
                    return False
        except (ValueError, OSError):
            pass
    LOCK_FILE.write_text(str(os.getpid()))

    import atexit

    def _cleanup_lock():
        try:
            if LOCK_FILE.exists() and LOCK_FILE.read_text().strip() == str(os.getpid()):
                LOCK_FILE.unlink()
        except Exception:
            pass

    atexit.register(_cleanup_lock)
    return True

LABEL_OCR_MIN_INTERVAL = 2.5   # seconds between nameplate OCRs per side
PARTY_OCR_MIN_INTERVAL = 5.0   # seconds between party-panel OCRs
TICK_BUDGET = 1.5              # if a tick exceeds this, skip optional OCRs


def img_sig(img):
    if img is None:
        return None
    # downscale-based signature: cheap and robust to 1px animation noise
    small = img.resize((max(1, img.width // 8), max(1, img.height // 8)))
    return (img.width, img.height, hash(small.tobytes()))


class Coach:
    def __init__(self, debug=False, headless=False):
        self.state = BattleState()
        self.debug = debug
        self.headless = headless
        self.overlay = None
        self._last_ocr_img = {}
        self._last_label_ocr = {"their": 0.0, "my": 0.0}
        self._last_label_key = {"their": None, "my": None}
        self._last_party_ocr = 0.0
        self._last_party_img = None
        self._last_log_ocr = 0.0
        self._last_full_log = 0.0
        self.last_battle_signal = 0.0   # last time we saw proof of a battle on screen
        self.slow_tick = False

    def _ocr_label(self, side, zone_img, bar):
        """OCR the small strip just above the located HP bar."""
        now = time.time()
        if now - self._last_label_ocr[side] < LABEL_OCR_MIN_INTERVAL:
            return
        sc = bar.get("scale", 1)
        if zone_img.width < 40 or bar["y"] < 12 * sc:
            return
        # label text sits above the bar; crop generously around the bar extent
        x0 = max(0, bar["x0"] - zone_img.width // 6)
        x1 = min(zone_img.width, bar["x1"] + zone_img.width // 6)
        y0 = max(0, bar["y"] - 34 * sc)
        y1 = max(y0 + 8, bar["y"] - 2)
        crop = zone_img.crop((x0, y0, x1, y1))
        sig = img_sig(crop)
        if sig == self._last_ocr_img.get(side):
            return
        self._last_ocr_img[side] = sig
        self._last_label_ocr[side] = now
        text = ocr.read_image(crop)
        if self.debug and text:
            print(f"{side.upper()} LABEL OCR >>> {text!r}")
        if text:
            self.state.set_field_active(side, text.splitlines()[0])

    def tick(self):
        """One observe -> advise cycle. Returns overlay lines or None."""
        t0 = time.time()
        hwnd = capture.find_pro_hwnd()
        if not hwnd:
            return None
        regions = capture.grab_regions(hwnd)
        if not regions:
            return None

        log_img = regions.get("log")
        menu_img = regions.get("menu")

        # ---- fast, advice-critical reads first ----
        menu_sig = img_sig(menu_img) if menu_img is not None else None
        menu_changed = menu_sig is not None and menu_sig != self._last_ocr_img.get("menu")
        if menu_changed:
            self._last_ocr_img["menu"] = menu_sig
            text = ocr.read_image(menu_img, scale=2)
            if self.debug and text:
                print("MENU OCR >>>")
                print(text)
            self.state.feed_menu(text or "")

        battle_live = bool(
            self.state.turn
            or self.state.my_active_key
            or self.state.their_active_key
            or self.state.menu_mode
        )
        battle_on_screen = battle_live and (time.time() - self.last_battle_signal < 60)
        if battle_live and battle_on_screen:
            for zone_name, side in (("foe_zone", "their"), ("my_zone", "my")):
                zone = regions.get(zone_name)
                if zone is None:
                    continue
                bar = hp.locate_bar(zone)
                if bar is None:
                    continue
                if side == "my":
                    self.state.my_hp = bar["frac"]
                else:
                    self.state.their_hp = bar["frac"]
                # nameplate read: self-throttled (2.5s), keeps actives fresh
                # even when fast action scrolls log lines past us
                self._ocr_label(side, zone, bar)
                if self.state.my_active_key or self.state.their_active_key:
                    self.last_battle_signal = time.time()

            # party panel: periodic bench read (skipped when the tick is already slow)
            party = regions.get("party")
            now = time.time()
            if (
                party is not None
                and now - self._last_party_ocr > PARTY_OCR_MIN_INTERVAL
                and now - t0 < TICK_BUDGET
            ):
                if img_sig(party) != img_sig(self._last_party_img):
                    self._last_party_img = party.copy()
                    self._last_party_ocr = now
                    text = ocr.read_image(party, scale=2, fast=True)
                    if self.debug and text:
                        print("PARTY OCR >>>")
                        print(text)
                    self.state.register_party(text or "")

        # ---- slow log OCR last (history/scout), capped ----
        # incremental: newest slice every 2s, full panel resync every 12s.
        # PAUSED while a choice menu is open - those ticks belong to fresh advice.
        log_sig = img_sig(log_img) if log_img is not None else None
        log_changed = log_sig is not None and log_sig != self._last_ocr_img.get("log")
        menu_open = self.state.menu_mode is not None
        if log_changed:
            now = time.time()
            full_resync = now - self._last_full_log > 12.0
            if (now - self._last_log_ocr > 2.0 or full_resync) and (not menu_open or full_resync):
                self._last_ocr_img["log"] = log_sig
                self._last_log_ocr = now
                if full_resync:
                    self._last_full_log = now
                    target = log_img
                else:
                    target = log_img.crop(
                        (0, int(log_img.height * 0.62), log_img.width, log_img.height)
                    )
                text = ocr.read_image(target, scale=2, fast=True)
                if self.debug and text:
                    print("LOG OCR >>>")
                    print(text)
                if text:
                    before = (self.state.turn, self.state.menu_mode, len(self.state.mons))
                    self.state.feed(text)
                    after = (self.state.turn, self.state.menu_mode, len(self.state.mons))
                    # only a REAL state change proves a battle is live
                    # (keyword matches fired on chat text covering the game)
                    if after != before:
                        self.last_battle_signal = time.time()

        try:
            results = advise(self.state)
        except Exception as e:
            from procoach import log_error
            log_error(f"advise failed: {type(e).__name__}: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            results = []

        # out-of-battle: stale HP from menu/chat bars must not mislead
        if battle_live and not battle_on_screen and time.time() - self.last_battle_signal > 60:
            self.state.my_hp = None
            self.state.their_hp = None
            results = [("info", "no battle on screen - open game + Battle Log panel, queue up")]
        advice_txt = " | ".join(t for _, t in results) if results else ""

        try:
            STATE_FILE.write_text(self.state.state_line(advice_txt), encoding="utf8")
        except Exception as e:
            STATE_FILE.write_text(f"COACH WRITE ERROR: {e}", encoding="utf8")
        self.state.save()

        self.slow_tick = time.time() - t0 > TICK_BUDGET
        if self.debug:
            print(self.state.state_line(advice_txt))
            print("-" * 50)

        if not results:
            results = [("info", f"TURN {self.state.turn} - watching...")]
        return results

    def run(self):
        import threading

        if not ocr.warmup():
            print("OCR engine failed to start")
            sys.exit(1)
        if self.headless:
            print("Headless mode: ctrl+c to stop. Writing", STATE_FILE)
            try:
                while True:
                    self.tick()
                    time.sleep(0.4 if not self.slow_tick else 1.0)
            except KeyboardInterrupt:
                pass
        else:
            # worker thread does the slow capture/OCR; overlay just displays
            self.latest = [("info", "starting...")]

            def worker():
                while True:
                    try:
                        res = self.tick()
                        if res is None:
                            self.latest = [("info", "PROClient not found - open the game")]
                        else:
                            self.latest = res
                    except Exception as e:
                        try:
                            STATE_FILE.write_text(
                                f"COACH ERROR: {type(e).__name__}: {e}", encoding="utf8")
                        except Exception:
                            pass
                        self.latest = [("info", f"(recovering: {type(e).__name__})")]
                    time.sleep(0.5 if not self.slow_tick else 1.2)

            threading.Thread(target=worker, daemon=True).start()

            from procoach.overlay import Overlay

            hwnd = capture.find_pro_hwnd()
            rect = capture.client_rect(hwnd) if hwnd else (100, 100, 900, 700)
            self.overlay = Overlay(rect, lambda: list(self.latest))
            self.overlay.run()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="print OCR text every tick")
    ap.add_argument("--headless", action="store_true", help="no overlay, console only")
    args = ap.parse_args()
    if not acquire_single_instance():
        sys.exit(1)
    Coach(**vars(args)).run()
