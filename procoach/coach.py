"""Coach engine: runs OCR, HP bar scans, party reads, state management and PvP team scanner."""
import argparse
import atexit
import ctypes
import os
import re
import sys
import threading
import time
from pathlib import Path

from . import capture, hp, ocr
from .advisor import advise
from .state import BattleState, match_item, moves_in_learnset, resolve_mon, resolve_move

STATE_FILE = Path(__file__).resolve().parent.parent / "state.txt"
LOCK_FILE = Path(__file__).resolve().parent.parent / "coach.lock"


def acquire_single_instance():
    """Refuses to start if another live coach process holds the lock."""
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
        self.last_battle_signal = 0.0
        self.slow_tick = False
        self.mode = "random"            # "random" | "pvp"
        self.scan_active = False
        self.scan_status = ""
        self.scan_keys = set()
        self._last_written_state = None

    def _ocr_label(self, side, zone_img, bar):
        now = time.time()
        current_sid = self.state.my_active_key if side == "my" else self.state.their_active_key
        if current_sid is not None and now - self._last_label_ocr[side] < LABEL_OCR_MIN_INTERVAL:
            return
        sc = bar.get("scale", 1)
        if zone_img.width < 40 or bar["y"] < 12 * sc:
            return
        x0 = max(0, bar["x0"] - int(zone_img.width * 0.25))
        x1 = min(zone_img.width, bar["x1"] + int(zone_img.width * 0.25))
        y0 = max(0, bar["y"] - int(38 * sc))
        y1 = max(y0 + 8, bar["y"] - 1)
        crop = zone_img.crop((x0, y0, x1, y1))
        sig = img_sig(crop)
        if sig == self._last_ocr_img.get(side):
            return
        self._last_ocr_img[side] = sig
        self._last_label_ocr[side] = now
        text = ocr.read_image(crop, scale=2)
        if self.debug and text:
            print(f"{side.upper()} LABEL OCR >>> {text!r}")
        if text:
            self.state.set_field_active(side, text.splitlines()[0])

    def tick(self):
        t0 = time.time()
        hwnd = capture.find_pro_hwnd()
        if not hwnd:
            return None
        regions = capture.grab_regions(hwnd)
        if not regions:
            return None

        log_img = regions.get("log")
        menu_img = regions.get("menu")

        menu_sig = img_sig(menu_img) if menu_img is not None else None
        menu_changed = menu_sig is not None and menu_sig != self._last_ocr_img.get("menu")
        if menu_changed:
            self._last_ocr_img["menu"] = menu_sig
            text = ocr.read_image(menu_img, scale=2)
            if self.debug and text:
                print("MENU OCR >>>")
                print(text)
            self.state.feed_menu(text or "")

        has_hp_bar = False
        for zone_name, side in (("foe_zone", "their"), ("my_zone", "my")):
            zone = regions.get(zone_name)
            if zone is None:
                continue
            bar = hp.locate_bar(zone)
            if bar is None:
                continue
            has_hp_bar = True
            if side == "my":
                self.state.my_hp = bar["frac"]
            else:
                self.state.their_hp = bar["frac"]
            self._ocr_label(side, zone, bar)
            if self.state.my_active_key or self.state.their_active_key:
                self.last_battle_signal = time.time()

        battle_live = bool(
            has_hp_bar
            or self.state.turn
            or self.state.my_active_key
            or self.state.their_active_key
            or self.state.menu_mode
        )
        battle_on_screen = battle_live and (has_hp_bar or time.time() - self.last_battle_signal < 60)

        if battle_live and battle_on_screen:
            party = regions.get("party")
            now = time.time()
            if (
                party is not None
                and (self.state.my_active_key is None or now - self._last_party_ocr > PARTY_OCR_MIN_INTERVAL)
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
                    if after != before:
                        self.last_battle_signal = time.time()

        try:
            results = advise(self.state)
        except Exception as e:
            from . import log_error
            log_error(f"advise failed: {type(e).__name__}: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            results = []

        if battle_live and not battle_on_screen and time.time() - self.last_battle_signal > 60:
            self.state.my_hp = None
            self.state.their_hp = None
            results = [("info", "no battle on screen - open game + Battle Log panel, queue up")]
        advice_txt = " | ".join(t for _, t in results) if results else ""

        self.state.my_hp_prev = self.state.my_hp
        self.state.their_hp_prev = self.state.their_hp

        new_state_text = self.state.state_line(advice_txt)
        if new_state_text != getattr(self, "_last_written_state", None):
            try:
                STATE_FILE.write_text(new_state_text, encoding="utf8")
                self._last_written_state = new_state_text
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
            if re.match(r"^(?:abilit\w*|nature|sumatt|tillnext|till next|^ot\b|^id[:\s])", line, re.I):
                continue

            # ---- held item ----
            it = match_item(line)
            if it and item is None:
                item = it
                continue

            # ---- move lines (strip leading bullets, trailing PP like "PP: 10/10", "7/15" or "35 35") ----
            clean = re.sub(r"^[-•*\d.]+\s*", "", line)
            clean = re.sub(r"\bpp\s*[:\s]*\d+.*$", "", clean, flags=re.I)
            clean = re.sub(r"\s+\(?\d+\s*[/\\]\s*\d+\)?\s*$", "", clean)
            clean = re.sub(r"\s+\d{1,3}\s+\d{1,3}\s*$", "", clean)
            clean = re.sub(r"\s+\d{1,3}\s*$", "", clean)
            clean = clean.strip(" .:;|-_~()")
            if clean and len(clean) >= 3:
                mv = resolve_move(clean)
                if mv and mv not in moves and len(moves) < 6:
                    moves.append(mv)
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

    def scan_loop(self):
        hwnd = capture.find_pro_hwnd()
        if not hwnd:
            self.scan_status = "SCAN error: PROClient window not found"
            self.scan_active = False
            return

        last_key = None
        last_sig = None
        t_start = time.time()

        # Capture full window area to guarantee popup header, stats, moves, item, and copy button are in frame
        SCAN_REGION = {"detail": (0.000, 0.000, 0.960, 0.980)}

        while self.scan_active:
            if time.time() - t_start > 180:
                break

            import win32gui
            fg = win32gui.GetForegroundWindow()
            if fg != hwnd:
                self.scan_status = "SCAN paused: PROClient not in focus"
                time.sleep(1.0)
                continue

            regions = capture.grab_regions(hwnd, regions=SCAN_REGION)
            img = regions.get("detail")
            if not img:
                time.sleep(0.5)
                continue

            sig = img_sig(img)
            if sig == last_sig:
                time.sleep(0.6)
                continue

            text = ocr.read_image(img, scale=2, fast=False)
            if self.debug and text:
                print("--- SCAN FRAME OCR ---")
                print(text)
                print("----------------------")

            key, moves, item, level = self._parse_scan_frame(text or "")

            if key:
                existing = self.state.my_team_data.get(key, {})
                existing_moves = existing.get("moves", [])
                existing_item = existing.get("item")

                # Accumulate moves and items progressively across frames
                has_new_info = any(m not in existing_moves for m in moves) or bool(item and not existing_item)

                if key not in self.scan_keys or has_new_info:
                    merged_moves = list(existing_moves)
                    for m in moves:
                        if m not in merged_moves and len(merged_moves) < 4:
                            merged_moves.append(m)
                    merged_item = item or existing_item
                    merged_level = level or existing.get("level")

                    self.state.register_scanned(key, merged_moves, merged_item, merged_level)
                    self.scan_keys.add(key)
                    last_key = key
                    last_sig = sig
                    n = len(self.scan_keys)
                    d = self.state.my_team_data.get(key, {})
                    mv_cnt = len(d.get("moves", []))
                    it_txt = f", {d['item']}" if d.get("item") else ""
                    self.scan_status = f"SCAN: {n}/6 ✓ {key} ({mv_cnt} moves{it_txt})"
                    if n >= 6 and all(len(self.state.my_team_data.get(k, {}).get("moves", [])) >= 4 for k in self.scan_keys):
                        self.scan_status = "SCAN COMPLETE (6/6) ✓"
                        self.scan_active = False
                        return
                    self.scan_status += " — open next Pokemon"
                elif key == last_key:
                    d = self.state.my_team_data.get(key, {})
                    mv_cnt = len(d.get("moves", []))
                    it_txt = f", {d['item']}" if d.get("item") else ""
                    self.scan_status = f"SCAN: {len(self.scan_keys)}/6 ✓ {key} ({mv_cnt} moves{it_txt}) — open next"
            else:
                self.scan_status = f"SCAN: reading... ({len(self.scan_keys)}/6) - open the detail page"
            time.sleep(1.0)
            time.sleep(1.2)
        if self.scan_active:
            self.scan_status = "SCAN stopped (timeout)"

    def set_manual_foe(self, text):
        if not text:
            return False
        from .state import parse_mon_and_item
        resolved, item = parse_mon_and_item(text.strip())
        if not resolved:
            return False
        self.state.set_field_active("their", resolved)
        self.state.add_their_team_mon(resolved, item=item)
        if item:
            self.state.set_mon_item("their", resolved, item)
        self.state.their_hp = 1.0
        if self.state.turn == 0:
            self.state.turn = 1
        self.state.save()
        self.last_battle_signal = time.time()
        return True

    def get_foe(self):
        th_sid = self.state.their_active_key
        if th_sid:
            m = self.state.mons.get(th_sid)
            return m.get("name") if m else ""
        return ""

    def clear_team(self):
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
                        from . import log_error
                        log_error(f"tick failed: {type(e).__name__}: {e}")
                        try:
                            STATE_FILE.write_text(
                                f"COACH ERROR: {type(e).__name__}: {e}", encoding="utf8")
                        except Exception:
                            pass
                        self.latest = [("info", f"(recovering: {type(e).__name__})")]
                    time.sleep(0.5 if not self.slow_tick else 1.2)

            threading.Thread(target=worker, daemon=True).start()

            print("Note: The offline overlay has been replaced by the unified AI Coach.")
            print("Please run 'python main.py' or 'run.bat' to launch the full AI Coach HUD.")
            print("Running in background headless mode...")
            try:
                while True:
                    self.tick()
                    time.sleep(0.5 if not self.slow_tick else 1.2)
            except KeyboardInterrupt:
                pass
