"""PRO Instant Coach - main loop.

Watches the PROClient window: cheap pixel scans every tick (HP bars),
OCR only on small label crops with throttles, keeps the scout sheet,
shows instant advice in an overlay and writes state.txt for the chat AI.
"""
import argparse
import re
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach import capture, hp, ocr
from procoach.advisor import advise
from procoach.state import BattleState, match_item, moves_in_learnset, resolve_mon, resolve_move

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
        self.mode = "random"            # "random" | "pvp"
        self.scan_active = False
        self.scan_status = ""
        self.scan_keys = set()

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

        # keep last tick's HP readings as pre-replacement HP for faint inference
        self.state.my_hp_prev = self.state.my_hp
        self.state.their_hp_prev = self.state.their_hp

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

    # ---------- PvP mode + team scanner ----------

    def get_mode(self):
        return self.mode

    def toggle_mode(self):
        self.mode = "pvp" if self.mode == "random" else "random"
        if self.mode == "random" and self.scan_active:
            self.scan_active = False
            self.scan_status = "SCAN stopped (random mode)"
        return self.mode

    def get_scan_status(self):
        if self.mode == "random":
            return "switch to PVP to scan"
        return self.scan_status

    def toggle_scan(self):
        if self.mode != "pvp":
            self.scan_status = "switch to PVP mode first"
            return
        if self.scan_active:
            self.scan_active = False
            self.scan_status = "SCAN stopped"
            return
        self.scan_active = True
        self.scan_status = "SCAN: starting..."
        threading.Thread(target=self.scan_loop, daemon=True).start()

    def _parse_scan_frame(self, text):
        """Parse OCR text from the Pokémon detail popup.

        Primary identification: header line with a 'Lv.' pattern (tolerates the
        common OCR misreads '1v'/'Lv'/'lv'). Fallback: a name candidate is only
        accepted when the frame's moves are actually in that species' learnset
        (>=2) - party-panel noise and cross-read popups can't register anymore.
        Every move is learnset-gated before it is returned."""
        level = None
        moves, item = [], None
        mon_key = None
        fallback_candidates = []

        # noise words that should never be resolved as mon names
        _SKIP = {
            "ability", "nature", "moves", "stats", "copy", "close",
            "attack", "defense", "speed", "special", "total",
            "exp", "next", "status", "trainer", "pokemon",
            "adamant", "jolly", "timid", "modest", "bold", "impish",
            "careful", "calm", "hasty", "naive", "brave", "quiet",
            "relaxed", "sassy", "rash", "mild", "gentle", "lax",
            "naughty", "lonely", "serious", "bashful", "docile",
            "quirky", "hardy", "atk", "def", "spd", "hp",
            "technician", "levitate", "intimidate", "overgrow",
            "blaze", "torrent", "swarm", "guts", "pressure",
            "synchronize", "inner focus", "magic guard",
        }

        # the name+level line is the popup's TITLE: always near the top of the
        # frame. Deep digit-bearing lines are OT/trainer names ("Electro008"
        # fuzzy-matches Electrode!) and must never claim the header.
        _GENERIC_HEADER_WINDOW = 10

        for idx, raw in enumerate((text or "").splitlines()):
            line = raw.strip()
            if not line or len(line) < 3:
                continue

            # skip lines that are clearly noise
            if line.lower() in _SKIP:
                continue
            # skip pure numbers / stat lines
            if re.match(r"^[\d\s./%:]+$", line):
                continue

            # ---- header line: "Scyther ♂ Lv.42 Kaida ID:30003557" ----
            # The Lv marker garbles systematically in OCR ('Lw46', '@L100',
            # 'QL100', 'Lx.60', 'dx 42'). Strict 'lv' first; otherwise accept
            # any line ending in a 1-3 digit number whose preceding text -
            # minus one short trailing marker token like 'Lw'/'@L'/'QL' -
            # resolves to a species. Non-resolving lines fall through to
            # move parsing (a move+PP line must never be eaten as a header).
            if level is None and re.search(r"\d", line):
                lm = re.search(r"[l1]v\.?\s*(\d{1,3})(?![a-z0-9])", line, re.I)
                if lm is None and idx < _GENERIC_HEADER_WINDOW:
                    lm = re.search(r"(\d{1,3})[\s.]*$", line)
                if lm:
                    lvl = int(lm.group(1))
                    if 1 <= lvl <= 100:
                        name_part = line[:lm.start()]
                        name_part = re.sub(r"[♂♀\u2642\u2640]", "", name_part).strip()
                        name_part = name_part.strip(" .:;|-_")
                        toks = name_part.split()
                        while toks and len(toks[-1]) <= 3 and not resolve_mon(toks[-1]):
                            toks.pop()
                        name_part = " ".join(toks)
                        if len(name_part) >= 3:
                            k = resolve_mon(name_part)
                            if k:
                                mon_key = k
                                level = lvl
                                continue

            # ---- ability / nature / label lines: skip ----
            if re.match(r"abilit\w*[:\s]|nature[:\s]|sumatt|tillnext|till next|^ot\b|^id[:\s]", line, re.I):
                continue

            # ---- move lines (strip trailing PP like "7/15" or "35 35") ----
            clean = re.sub(r"\s+\d+[/\\]\d+\s*$", "", line)    # "7/15"
            clean = re.sub(r"\s+\d{1,3}\s+\d{1,3}\s*$", "", clean)  # "35 35"
            clean = re.sub(r"\s+\d{1,3}\s*$", "", clean)        # trailing number
            clean = clean.strip()
            if clean and len(clean) >= 3:
                mv = resolve_move(clean)
                if mv and mv not in moves and len(moves) < 6:
                    moves.append(mv)
                    continue

            # ---- held item ----
            it = match_item(line)
            if it and item is None:
                item = it
                continue

            # ---- fallback mon candidate: strict match, longer names only ----
            if mon_key is None and 5 <= len(line) <= 20 and line.lower() not in _SKIP:
                k = resolve_mon(line)
                if k and k not in fallback_candidates:
                    fallback_candidates.append(k)

        # header-line identification failed: accept a fallback candidate only
        # when the frame's moves are legal for it - the party panel lists other
        # mons' names, and blind fallback attributed their moves to them
        if mon_key is None and fallback_candidates:
            for k in fallback_candidates:
                if len(moves_in_learnset(k, moves)) >= 2:
                    mon_key = k
                    break

        # the Lv marker sometimes lands on its own line ("Lx.60") with the
        # name above it - recover the level from that marker-only line
        if mon_key is not None and level is None:
            for raw in (text or "").splitlines():
                mm = re.match(r"^[a-z@][\w@.]{0,2}\.?\s*(\d{1,3})$", raw.strip(), re.I)
                if mm and 1 <= int(mm.group(1)) <= 100:
                    level = int(mm.group(1))
                    break

        if mon_key:
            moves = moves_in_learnset(mon_key, moves)

        return mon_key, moves, item, level

    # Capture region: the detail popup area.  Wide enough to catch the popup
    # on various window sizes; excludes the far-right game world.
    _SCAN_REGION = {"detail": (0.08, 0.0, 0.70, 0.70)}

    def scan_loop(self):
        self.scan_status = "SCAN: open each Pokemon's detail page"
        deadline = time.time() + 180
        last_sig = None          # image signature for change detection
        last_key = None          # last mon we registered (debounce)
        while self.scan_active and time.time() < deadline:
            hwnd = capture.find_pro_hwnd()
            if not hwnd:
                self.scan_status = "SCAN: game not visible"
                time.sleep(1.5)
                continue
            # the capture reads physical screen pixels: if another window is in
            # front of the game we would OCR THAT window's text (poisoned scans)
            try:
                import win32gui
                if win32gui.GetForegroundWindow() != hwnd:
                    self.scan_status = "SCAN: bring the game window to the front"
                    time.sleep(1.0)
                    continue
            except Exception:
                pass
            regions = capture.grab_regions(hwnd, self._SCAN_REGION)
            img = regions.get("detail")
            if img is None:
                time.sleep(1.5)
                continue

            # change detection: skip identical frames
            sig = img_sig(img)
            if sig == last_sig:
                time.sleep(0.8)
                continue
            last_sig = sig

            # quality engine: the popup's small text is unreadable at the fast
            # engine's 320px detection cap on this large region
            text = ocr.read_image(img, scale=2, fast=False)

            # always print scan OCR to console for debugging
            print(f"--- SCAN OCR ({len(self.scan_keys)}/6) ---")
            print(text or "(empty)")
            print("---")

            key, moves, item, level = self._parse_scan_frame(text)

            # a frame only counts as a scanned mon when it has the evidence:
            # name + learnset-legal moves (+ level, or >=3 legal moves when
            # even the garbled-marker recovery missed it - party-panel reads
            # have names but never a move list, so they still can't pass)
            complete = (
                key is not None
                and bool(moves)
                and (level is not None or len(moves) >= 3)
            )

            if complete and key != last_key:
                # debounce: confirm with a second read after a short pause
                time.sleep(0.6)
                regions2 = capture.grab_regions(hwnd, self._SCAN_REGION)
                img2 = regions2.get("detail")
                if img2:
                    text2 = ocr.read_image(img2, scale=2, fast=False)
                    key2, moves2, item2, level2 = self._parse_scan_frame(text2)
                    if key2 == key:
                        # merge moves/items from both reads
                        for mv in moves2:
                            if mv not in moves:
                                moves.append(mv)
                        if item2 and not item:
                            item = item2
                        if level2 and not level:
                            level = level2
                    else:
                        # screen changed between reads, retry
                        last_sig = None
                        continue

                self.state.register_scanned(key, moves, item, level)
                self.scan_keys.add(key)
                last_key = key
                n = len(self.scan_keys)
                self.scan_status = f"SCAN: {n}/6 ✓ {key}"
                if n >= 6:
                    self.scan_status = "SCAN COMPLETE (6/6) ✓"
                    self.scan_active = False
                    return
                self.scan_status += " — open next Pokemon"
            elif key and key == last_key:
                # same mon still open, waiting for user to switch
                self.scan_status = f"SCAN: {len(self.scan_keys)}/6 — open next Pokemon"
            else:
                self.scan_status = f"SCAN: reading... ({len(self.scan_keys)}/6) - open the detail page"
            time.sleep(1.2)
        if self.scan_active:
            self.scan_status = "SCAN stopped (timeout)"

    def clear_team(self):
        """Wipes all scanned team data (bad OCR reads can pollute it)."""
        self.state.my_team_data = {}
        self.state.save()
        self.scan_keys = set()
        self.scan_status = "team scan data cleared"

    def run(self):

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
                        from procoach import log_error
                        log_error(f"tick failed: {type(e).__name__}: {e}")
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
            self.overlay = Overlay(
                rect,
                lambda: list(self.latest),
                on_mode=self.toggle_mode,
                on_scan=self.toggle_scan,
                on_clear=self.clear_team,
                get_mode=self.get_mode,
                get_scan=self.get_scan_status,
            )
            self.overlay.run()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--debug", action="store_true", help="print OCR text every tick")
    ap.add_argument("--headless", action="store_true", help="no overlay, console only")
    args = ap.parse_args()
    if not acquire_single_instance():
        sys.exit(1)
    Coach(**vars(args)).run()
