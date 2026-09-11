import argparse
import os
import sys
import threading
import time
from pathlib import Path

_this_dir = str(Path(__file__).resolve().parent)
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from ai_coach import AICoach
from overlay import AIOverlay
from procoach.coach import Coach


def is_external_coach_running():
    """Returns True if an external coach process holds the lock."""
    lock_file = Path(__file__).resolve().parent / "coach.lock"
    if not lock_file.exists():
        return False
    try:
        import ctypes
        pid = int(lock_file.read_text().strip())
        if pid == os.getpid():
            return False
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
    except Exception:
        pass
    return False


def find_game_rect():
    """Find PROClient game rect. Uses procoach if available, else win32gui fallback."""
    try:
        from procoach import capture
        hwnd = capture.find_pro_hwnd()
        if hwnd:
            return capture.client_rect(hwnd)
    except Exception:
        pass

    try:
        import win32gui
        found = []

        def cb(hwnd, _):
            if win32gui.IsWindowVisible(hwnd):
                title = (win32gui.GetWindowText(hwnd) or "").lower()
                if "proclient" in title:
                    found.append(hwnd)

        win32gui.EnumWindows(cb, None)
        if found:
            hwnd = found[0]
            pt = win32gui.ClientToScreen(hwnd, (0, 0))
            rect = win32gui.GetClientRect(hwnd)
            return (pt[0], pt[1], pt[0] + rect[2], pt[1] + rect[3])
    except Exception:
        pass

    return (100, 100, 900, 700)


BATTLE_END_PHRASES = (
    "won the battle",
    "lost the battle",
    "defeated the opposing",
    "has been defeated",
    "blacked out",
    "got away safely",
    "fled from battle",
    "you fled",
    "earned $",
    "earned exp",
)


class CaptureWorker:
    """Runs a local OCR/capture loop if the main coach process is not running."""

    def __init__(self, state_file, debug=False, on_battle_end=None):
        self.state_file = Path(state_file)
        self.debug = debug
        self.on_battle_end = on_battle_end
        self.running = True
        self.status = "init OCR..."
        self.coach = None
        self._thread = None
        self.battle_active = False
        self.last_battle_visible = 0.0

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _clear_battle_state(self):
        """Cleanly wipes state when battle ends."""
        if self.coach:
            self.coach.state.reset()
            self.coach.state.save()
        try:
            self.state_file.write_text("TURN 0 | menu: -\nMY ACTIVE: -\nTHEIR ACTIVE: -\n", encoding="utf8")
        except Exception:
            pass

    def _run(self):
        try:
            from procoach import ocr
            self.status = "warming up OCR..."
            if not ocr.warmup():
                self.status = "OCR init failed"
                return
        except Exception as e:
            self.status = f"OCR error: {e}"
            return

        try:
            try:
                from procoach.coach import Coach
            except ImportError:
                from main import Coach
            self.coach = Coach(headless=True, debug=self.debug)
        except Exception as e:
            self.status = f"Coach error: {e}"
            return

        self.status = "OCR ready"
        while self.running:
            try:
                if is_external_coach_running():
                    self.status = "linked to main coach"
                    time.sleep(1.0)
                    continue

                from procoach import capture
                hwnd = capture.find_pro_hwnd()
                if not hwnd:
                    self.status = "PROClient not found"
                    time.sleep(1.5)
                    continue

                self.coach.tick()
                st = self.coach.state

                has_hp = (st.my_hp is not None) or (st.their_hp is not None)
                has_menu = bool(st.menu_mode)
                has_actives = bool(st.my_active_key or st.their_active_key)

                # Check recent events for battle-end markers
                log_ended = False
                for ev in (st.events[-8:] if st.events else []):
                    low = ev.lower()
                    if any(phrase in low for phrase in BATTLE_END_PHRASES):
                        log_ended = True
                        break

                now = time.time()
                if (has_hp or has_menu or has_actives) and not log_ended:
                    self.battle_active = True
                    self.last_battle_visible = now
                    my_name = st.mons.get(st.my_active_key, {}).get("name", "?")
                    th_name = st.mons.get(st.their_active_key, {}).get("name", "?")
                    self.status = f"T{st.turn}: {my_name} vs {th_name}"
                elif self.battle_active:
                    # Was in battle, but either log announced end or no battle visible for > 3.5s
                    if log_ended or (now - self.last_battle_visible > 3.5):
                        self.battle_active = False
                        self._clear_battle_state()
                        self.status = "battle ended"
                        if self.on_battle_end:
                            self.on_battle_end()
                    else:
                        self.status = "watching..."
                else:
                    self.status = "watching Battle Log..."

                time.sleep(0.4)
            except Exception as e:
                time.sleep(1.0)


class GeminiCoachApp:
    def __init__(self, manual_only=False, cooldown=10, state_file=None, model=None, debug=False):
        self.ai = AICoach(model=model)
        self.ai.cooldown = cooldown
        self.manual_only = manual_only
        self.auto_send = False  # default to manual review: user sees data and clicks SEND TO AI
        self.debug = debug
        self.overlay = None
        self._last_state = ""
        self._last_sent_key = None
        self._last_turn_sent = None

        if state_file:
            self.state_file = Path(state_file)
        else:
            candidates = [
                Path(__file__).resolve().parent / "state.txt",
                Path(__file__).resolve().parent.parent / "state.txt",
                Path("state.txt"),
            ]
            self.state_file = next((p for p in candidates if p.exists()), candidates[0])

        self.capture_worker = CaptureWorker(
            state_file=self.state_file,
            debug=debug,
            on_battle_end=self._on_battle_end,
        )

    def _on_battle_end(self):
        """Called immediately when a battle ends."""
        self.ai.cancel()
        self._last_sent_key = None
        self._last_turn_sent = None
        if self.overlay:
            self.overlay.set_text(
                "Battle finished.\n\n"
                "• Ready for your next battle!\n"
                "• Keep the in-game 'Battle Log' chat tab selected.",
                "info",
            )

    def _on_toggle_auto(self):
        self.auto_send = not self.auto_send
        return self.auto_send

    def _get_auto(self):
        return self.auto_send

    def _on_reload_state(self):
        return self._read_state()

    def _on_mode(self):
        if self.capture_worker.coach:
            return self.capture_worker.coach.toggle_mode()
        return "random"

    def _on_scan(self):
        if self.capture_worker.coach:
            self.capture_worker.coach.toggle_scan()

    def _on_clear(self):
        if self.capture_worker.coach:
            self.capture_worker.coach.clear_team()

    def _get_mode(self):
        if self.capture_worker.coach:
            return self.capture_worker.coach.get_mode()
        return "random"

    def _get_scan(self):
        if self.capture_worker.coach:
            return self.capture_worker.coach.get_scan_status()
        return ""

    def _read_state(self):
        """Read current state text from memory or state.txt."""
        if self.capture_worker.coach and not is_external_coach_running():
            st = self.capture_worker.coach.state
            if st.my_active_key or st.their_active_key or st.turn > 0 or st.my_hp is not None or st.their_hp is not None:
                try:
                    from procoach.advisor import advise
                    adv_results = advise(st)
                    advice_txt = " | ".join(t for _, t in adv_results) if adv_results else ""
                except Exception:
                    advice_txt = ""
                return st.state_line(advice_txt)
            return ""

        try:
            if not self.state_file.exists():
                return ""
            text = self.state_file.read_text(encoding="utf8")
            self._last_state = text
            return text
        except Exception:
            return self._last_state

    def _extract_turn(self, state_text):
        """Extract turn number from state text."""
        for line in state_text.splitlines():
            if line.startswith("TURN "):
                try:
                    return int(line.split()[1])
                except (IndexError, ValueError):
                    pass
        return 0

    def _on_set_foe(self, name_or_raw):
        """Manually sets the opponent's active Pokemon, with optional item support."""
        if not name_or_raw or not name_or_raw.strip():
            return
        from procoach.state import parse_mon_and_item, DEX
        resolved, item = parse_mon_and_item(name_or_raw.strip())
        if not resolved or resolved not in DEX:
            if self.overlay:
                self.overlay.set_text(
                    f"Could not resolve Pokemon '{name_or_raw}'.\n\n"
                    "Please check the spelling and try again.",
                    "warn",
                )
            return

        mon_name = DEX[resolved]["name"]

        # Update local coach state if capture_worker is active
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.set_field_active("their", resolved)
            st.add_their_team_mon(resolved, item=item)
            if item:
                st.set_mon_item("their", resolved, item)
            st.their_hp = 1.0
            if st.turn == 0:
                st.turn = 1
            self.capture_worker.battle_active = True
            self.capture_worker.last_battle_visible = time.time()
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
        else:
            # Standalone state.txt edit
            try:
                text = self.state_file.read_text(encoding="utf8") if self.state_file.exists() else ""
                lines = text.splitlines()
                item_s = f" @ {item}" if item else ""
                replaced = False
                for i, l in enumerate(lines):
                    if l.startswith("THEIR ACTIVE:"):
                        lines[i] = f"THEIR ACTIVE: {mon_name}{item_s} ~100% ({'/'.join(DEX[resolved]['types'])})"
                        replaced = True
                        break
                if not replaced:
                    lines.append(f"THEIR ACTIVE: {mon_name}{item_s} ~100% ({'/'.join(DEX[resolved]['types'])})")
                state_text = "\n".join(lines)
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                item_s = f" @ {item}" if item else ""
                state_text = f"TURN 1 | menu: -\nTHEIR ACTIVE: {mon_name}{item_s} ~100% ({'/'.join(DEX[resolved]['types'])})"

        # Refresh overlay editor & team views
        if self.overlay:
            self.overlay.set_state_data(state_text, force=True)
            self.overlay.refresh_teams_view()

        # Immediate AI analysis
        self.ai.cancel()
        item_info = f" (holding {item})" if item else ""
        if self.overlay:
            self.overlay.set_text(f"Enemy set to {mon_name}{item_info} (100% HP).\nAnalyzing battle turn with Gemini...", "info")
        turn = self._extract_turn(state_text)
        self._last_sent_key = self._extract_state_key(state_text)
        self.ai.ask(state_text, callback=self._on_response, turn=turn)

    def _on_add_foe(self, text):
        from procoach.state import parse_mon_and_item
        mon_key, item = parse_mon_and_item(text)
        if not mon_key:
            return
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.add_their_team_mon(mon_key, item=item)
            if item:
                st.set_mon_item("their", mon_key, item)
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
            if self.overlay:
                self.overlay.set_state_data(state_text, force=True)

    def _on_remove_foe(self, key):
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.remove_their_team_mon(key)
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
            if self.overlay:
                self.overlay.set_state_data(state_text, force=True)

    def _on_clear_foe(self):
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.clear_their_team()
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
            if self.overlay:
                self.overlay.set_state_data(state_text, force=True)

    def _on_set_item(self, side, key, item):
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.set_mon_item(side, key, item)
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
            if self.overlay:
                self.overlay.set_state_data(state_text, force=True)

    def _on_add_my_mon(self, text):
        from procoach.state import parse_mon_and_item
        mon_key, item = parse_mon_and_item(text)
        if not mon_key:
            return
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.set_my_team_mon(mon_key, item=item)
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
            if self.overlay:
                self.overlay.set_state_data(state_text, force=True)

    def _on_remove_my_mon(self, key):
        if self.capture_worker and self.capture_worker.coach:
            st = self.capture_worker.coach.state
            st.remove_my_team_mon(key)
            st.save()
            state_text = self._read_state()
            try:
                self.state_file.write_text(state_text, encoding="utf8")
            except Exception:
                pass
            if self.overlay:
                self.overlay.set_state_data(state_text, force=True)

    def _get_teams(self):
        """Returns 6v6 team data for the overlay manager."""
        from procoach.state import DEX, MOVES, _sid, get_opponent_unrevealed_scout
        st = self.capture_worker.coach.state if (self.capture_worker and self.capture_worker.coach) else None
        if not st:
            return {"my": [], "their": []}

        my_list = []
        my_keys = list(st.my_team_data.keys())
        for sid, m in st.mons.items():
            if m.get("side") == "my":
                k = m.get("key")
                if k and k not in my_keys:
                    my_keys.append(k)

        for k in my_keys[:6]:
            d = DEX.get(k, {})
            t_data = st.my_team_data.get(k, {})
            sid = _sid("my", k)
            live_m = st.mons.get(sid, {})
            item = live_m.get("item") or t_data.get("item")
            mvs = t_data.get("moves") or live_m.get("moves") or []
            mv_names = [MOVES[mv]["name"] for mv in mvs if mv in MOVES]
            status = "ACTIVE" if sid == st.my_active_key else ("FAINTED" if (live_m.get("fainted") or sid in st.my_fainted) else "BENCH")
            my_list.append({
                "key": k,
                "name": d.get("name", k.title()),
                "types": d.get("types", []),
                "item": item or "",
                "moves": mv_names,
                "status": status,
                "locked": t_data.get("locked", False),
            })

        their_list = []
        th_entries = list(st.their_team)
        th_k = st._active_dex_key("their")
        if th_k and not any(e.get("key") == th_k for e in th_entries):
            th_item = st.mons.get(st.their_active_key, {}).get("item")
            th_entries.insert(0, {"key": th_k, "item": th_item})

        my_act_m = st.mons.get(st.my_active_key)
        my_types = my_act_m.get("types", []) if my_act_m else []

        for entry in th_entries[:6]:
            k = entry.get("key")
            d = DEX.get(k, {})
            sid = _sid("their", k)
            live_m = st.mons.get(sid, {})
            item = entry.get("item") or live_m.get("item")
            mvs = live_m.get("moves") or []
            mv_names = [MOVES[mv]["name"] for mv in mvs if mv in MOVES]
            status = "ACTIVE" if sid == st.their_active_key else ("FAINTED" if (live_m.get("fainted") or sid in st.their_fainted) else "BENCH")
            scout_threats = get_opponent_unrevealed_scout(k, live_m.get("moves", []), my_types)
            their_list.append({
                "key": k,
                "name": d.get("name", k.title()),
                "types": d.get("types", []),
                "item": item or "",
                "moves": mv_names,
                "status": status,
                "scout_threats": scout_threats,
            })

        return {"my": my_list, "their": their_list}

    def _get_foe(self):
        """Current opponent name for prefilling input."""
        state = self._read_state()
        for line in state.splitlines():
            if line.startswith("THEIR ACTIVE:"):
                raw = line.replace("THEIR ACTIVE:", "").strip()
                if raw and raw != "-":
                    return raw.split()[0]
        return ""

    def _quantize_hp(self, text):
        """Quantize HP percentages to 4% intervals to prevent 1px render jitter from triggering AI."""
        import re
        return re.sub(r"~(\d+)%", lambda m: f"~{(int(m.group(1)) // 4) * 4}%", text)

    def _extract_state_key(self, state_text):
        """Generates a compact fingerprint of the current battle situation.
        Changes to turn, active mons, quantized HP, fainted list, moves, or menu trigger a new key.
        """
        if not state_text:
            return None

        turn = 0
        my_act = "-"
        th_act = "-"
        fainted_mine = ""
        fainted_theirs = ""
        menu_mode = "-"
        advice = ""
        my_moves = ""

        for line in state_text.splitlines():
            line_str = line.strip()
            if line_str.startswith("TURN "):
                try:
                    parts = line_str.split("|")
                    turn = int(parts[0].split()[1])
                    if len(parts) > 1 and "menu:" in parts[1]:
                        menu_mode = parts[1].split("menu:")[1].strip()
                except Exception:
                    pass
            elif line_str.startswith("MY ACTIVE:"):
                my_act = self._quantize_hp(line_str.replace("MY ACTIVE:", "").strip())
            elif line_str.startswith("THEIR ACTIVE:"):
                th_act = self._quantize_hp(line_str.replace("THEIR ACTIVE:", "").strip())
            elif line_str.startswith("FAINTED"):
                parts = line_str.split("|")
                fainted_mine = parts[0].strip()
                if len(parts) > 1:
                    fainted_theirs = parts[1].strip()
            elif line_str.startswith("MY MOVES") or line_str.startswith("MY KNOWN MOVES"):
                my_moves = line_str
            elif line_str.startswith("ADVICE:"):
                advice = line_str.replace("ADVICE:", "").strip()

        return (turn, my_act, th_act, fainted_mine, fainted_theirs, menu_mode, my_moves, advice)

    def _has_battle(self, state_text):
        """True if state text contains real battle data."""
        if not state_text:
            return False
        has_my = "MY ACTIVE:" in state_text and "MY ACTIVE: -" not in state_text
        has_th = "THEIR ACTIVE:" in state_text and "THEIR ACTIVE: -" not in state_text
        has_hp = "~" in state_text and "%" in state_text
        has_turn = "TURN " in state_text and "TURN 0 | menu: -" not in state_text
        return has_my or has_th or has_hp or has_turn

    def _on_send_to_ai(self, state_text=None):
        """Sends either the user-edited battle state or the live state to Gemini."""
        state = (state_text or "").strip()
        if not state:
            state = self._read_state()
        if not state or not self._has_battle(state):
            hint = self.capture_worker.status if self.capture_worker else ""
            msg = (
                f"No battle data to send ({hint}).\n\n"
                "Please verify:\n"
                "1. PROClient game window is open\n"
                "2. The in-game 'Battle Log' chat tab is selected\n"
                "3. You are currently in a battle\n\n"
                "Or click the '✏️ BATTLE DATA' tab to type/paste battle state directly!"
            )
            if self.overlay:
                self.overlay.set_text(msg, "info")
            return

        turn = self._extract_turn(state)
        self._last_sent_key = self._extract_state_key(state)
        if self.overlay:
            self.overlay.set_text("AI analyzing turn...", "info")
        self.ai.cancel()
        self.ai.ask(state, callback=self._on_response, turn=turn)

    def _on_ask(self):
        """Legacy ask fallback."""
        self._on_send_to_ai()

    def _on_response(self, text, turn=None):
        """Called when Gemini responds."""
        if self.overlay and text:
            self.overlay.set_text(text)

    def _get_status(self):
        """Status text for the overlay bottom bar."""
        if self.ai.busy:
            return "AI analyzing turn..."
        if self.ai.error and not self.ai.enabled:
            return self.ai.error
        if not self.ai.enabled:
            return "click ASK AI to start"

        cap = self.capture_worker.status if self.capture_worker else ""
        ago = int(time.time() - self.ai.last_call) if self.ai.last_call else 0
        mode = "AUTO" if self.auto_send else "MANUAL"
        parts = []
        if cap:
            parts.append(cap)
        parts.append(mode)
        if ago:
            parts.append(f"{ago}s ago")
        return " | ".join(parts)

    def _on_import_showdown(self, text):
        """Callback from overlay to import team from Showdown text."""
        st = self.capture_worker.coach.state if (self.capture_worker and self.capture_worker.coach) else None
        if not st:
            return 0
        count = st.import_showdown_team(text)
        state_text = st.state_line()
        try:
            self.state_file.write_text(state_text, encoding="utf8")
        except Exception:
            pass
        return count

    def _on_save_raw_data(self, text):
        """Callback from overlay to save manual edits to the raw battle data."""
        if not text:
            return
        try:
            self.state_file.write_text(text.strip(), encoding="utf8")
        except Exception:
            pass
        st = self.capture_worker.coach.state if (self.capture_worker and self.capture_worker.coach) else None
        if st:
            st.save()

    def _watcher(self):
        """Background thread: streams live state to the editable data viewer and handles auto-send if enabled."""
        last_seen_key = None
        change_time = 0.0
        DEBOUNCE_SECS = 0.5  # wait 0.5s of state stability before sending to Gemini

        while True:
            try:
                state = self._read_state()
                if state and self.overlay:
                    self.overlay.set_state_data(state)

                # Compute instant zero-latency quick-calc (<1ms)
                st = self.capture_worker.coach.state if (self.capture_worker and self.capture_worker.coach) else None
                if st and st.my_active_key and st.their_active_key:
                    from procoach.calc import get_turn_quick_calc
                    from procoach.state import _sid
                    my_m = st.mons.get(st.my_active_key)
                    th_m = st.mons.get(st.their_active_key)
                    my_mvs = st.menu_moves if (st.menu_mode == "attack" and st.menu_moves) else (my_m.get("moves") if my_m else [])
                    if not my_mvs and my_m and my_m.get("key") in st.my_team_data:
                        my_mvs = st.my_team_data[my_m["key"]].get("moves") or []
                    th_entries = list(st.their_team)
                    my_team_list = [
                        {
                            "key": k,
                            "moves": st.my_team_data.get(k, {}).get("moves", []),
                            "fainted": bool(st.mons.get(_sid("my", k), {}).get("fainted") or _sid("my", k) in st.my_fainted),
                        }
                        for k in st.my_team_data.keys()
                    ]
                    quick_data = get_turn_quick_calc(
                        my_m, th_m, my_mvs,
                        my_hp=st.my_hp,
                        their_hp=st.their_hp,
                        their_bench=th_entries,
                        my_team=my_team_list,
                        their_team=th_entries,
                        my_fainted=st.my_fainted,
                        their_fainted=st.their_fainted,
                        their_locked_move=getattr(st, "th_choice_locked_move", None),
                    )
                    if self.overlay:
                        self.overlay.set_quick_calc(quick_data)
                elif self.overlay:
                    self.overlay.set_quick_calc(None)

                if self.auto_send and not self.manual_only and state and self._has_battle(state):
                    current_key = self._extract_state_key(state)
                    now = time.time()

                    # Check if the battle state has changed on screen
                    if current_key != last_seen_key:
                        last_seen_key = current_key
                        change_time = now

                    # State must be settled (no rapid OCR fluctuations for DEBOUNCE_SECS)
                    # and must represent a new situation not yet advised by AI
                    is_stable = (now - change_time) >= DEBOUNCE_SECS
                    is_new_situation = (current_key is not None) and (current_key != self._last_sent_key)

                    if is_stable and is_new_situation and self.ai.enabled:
                        # If user opened the attack menu, cancel any slower background call and prioritize attacks
                        menu_mode = current_key[5] if current_key and len(current_key) > 5 else "-"
                        if self.ai.busy and menu_mode == "attack":
                            self.ai.cancel()

                        if not self.ai.busy:
                            turn = self._extract_turn(state)
                            self._last_sent_key = current_key
                            self.ai.ask(state, callback=self._on_response, turn=turn)
            except Exception:
                pass
            time.sleep(0.25)

    def run(self):
        # init AI (prints error if no key)
        self.ai.init()

        # start local capture worker (captures PROClient if main coach not running)
        self.capture_worker.start()

        # auto-load permanent saved team if available
        st = self.capture_worker.coach.state if (self.capture_worker and self.capture_worker.coach) else None
        if st and not st.my_team_data:
            st.load_saved_team()

        # get window rect for overlay positioning
        rect = find_game_rect()

        # start watcher thread
        threading.Thread(target=self._watcher, daemon=True).start()

        # create and run overlay
        self.overlay = AIOverlay(
            rect,
            on_send_to_ai=self._on_send_to_ai,
            on_set_foe=self._on_set_foe,
            on_mode=self._on_mode,
            on_scan=self._on_scan,
            on_clear=self._on_clear,
            get_mode=self._get_mode,
            get_scan=self._get_scan,
            get_status=self._get_status,
            get_foe=self._get_foe,
            on_toggle_auto=self._on_toggle_auto,
            get_auto=self._get_auto,
            on_reload_state=self._on_reload_state,
            on_add_foe=self._on_add_foe,
            on_remove_foe=self._on_remove_foe,
            on_clear_foe=self._on_clear_foe,
            on_set_item=self._on_set_item,
            on_add_my_mon=self._on_add_my_mon,
            on_remove_my_mon=self._on_remove_my_mon,
            get_teams=self._get_teams,
            on_import_showdown=self._on_import_showdown,
            on_save_raw_data=self._on_save_raw_data,
        )

        # show initial message
        if self.ai.enabled:
            self.overlay.set_text(
                f"PRO AI Coach Ready (model: {self.ai.model_name})\n\n"
                "• Watching PROClient in background (auto-OCR active)\n"
                "• [ 🎯 SEND TO AI ]: Click anytime for deep tactical turn advice\n"
                "• [ ⚡ AUTO ]: Toggle automatic turn-by-turn advice\n"
                "• [ 👥 6v6 TEAMS ]: Manage your 6 Pokémon, opponent slots & held items\n"
                "• Keep your in-game Battle Log tab visible during battles.",
                "info",
            )
        else:
            self.overlay.set_text(self.ai.last_response, "warn")

        self.overlay.run()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="PRO AI Coach (Gemini)")
    ap.add_argument("--manual", action="store_true",
                    help="manual-only mode (no auto-trigger)")
    ap.add_argument("--cooldown", type=int, default=10,
                    help="seconds between auto AI calls (default: 10)")
    ap.add_argument("--state", type=str, default=None,
                    help="path to state.txt (default: auto-detected)")
    ap.add_argument("--model", type=str, default=None,
                    help="Gemini model name (default: gemini-3.5-flash)")
    ap.add_argument("--debug", action="store_true",
                    help="print debug OCR and state output")
    args = ap.parse_args()
    GeminiCoachApp(
        manual_only=args.manual,
        cooldown=args.cooldown,
        state_file=args.state,
        model=args.model,
        debug=args.debug,
    ).run()
