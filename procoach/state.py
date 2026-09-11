"""Parses OCR'd battle-log lines into a live battle state (the scout sheet).

Mons are stored SIDE-QUALIFIED ("my:venusaur" / "their:venusaur") so mirror
matches (both players own the same species) never share scout data.
"""
import difflib
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

with open(DATA_DIR / "dex.json", encoding="utf8") as f:
    DEX = json.load(f)
with open(DATA_DIR / "moves.json", encoding="utf8") as f:
    MOVES = json.load(f)
try:
    with open(DATA_DIR / "items.json", encoding="utf8") as f:
        _ITEMS = json.load(f)
    ITEM_INDEX = {e["name"].lower(): e["name"] for e in _ITEMS.values()}
except Exception:
    ITEM_INDEX = {}
try:
    with open(DATA_DIR / "learnsets.json", encoding="utf8") as f:
        LEARNSETS = json.load(f)
except Exception:
    LEARNSETS = {}


def moves_in_learnset(key, moves):
    """Filters a scanned move list down to what the species can actually learn.

    The team scanner OCRs whatever is on screen; without this gate one popup's
    moves get attributed to the wrong species. A species with no learnset entry
    (data gap) is passed through unfiltered."""
    learn = LEARNSETS.get(key)
    if not learn:
        return list(moves)
    return [mv for mv in moves if mv in learn]


def match_item(text):
    """Finds an item name inside an OCR line (PvP team scans)."""
    if not text:
        return None
    t = text.lower()
    for low, disp in ITEM_INDEX.items():
        if len(low) > 4 and low in t:
            return disp
    close = difflib.get_close_matches(
        t.strip().strip(".,!"), list(ITEM_INDEX), n=1, cutoff=0.85
    )
    return ITEM_INDEX[close[0]] if close else None

_NAME_INDEX = {e["name"].lower(): key for key, e in DEX.items()}
_MOVE_INDEX = {e["name"].lower(): key for key, e in MOVES.items()}

RESOLVE_CACHE = {}  # capped at 5000 entries
_MOVE_CACHE = {}    # capped at 5000 entries
_CACHE_CAP = 5000


def _try_dex(text):
    t = text.strip().strip(".,!'").lower().replace("-", " ")
    t = re.sub(r"\s+", " ", t)
    if t in _NAME_INDEX:
        return _NAME_INDEX[t]
    # short names (Mew, Oddish...) garble easily in OCR; be more lenient
    cutoff = 0.6 if len(t) <= 5 else 0.8
    close = difflib.get_close_matches(t, list(_NAME_INDEX), n=1, cutoff=cutoff)
    return _NAME_INDEX[close[0]] if close else None


def resolve_mon(text, cache=RESOLVE_CACHE):
    """OCR-garbled display name -> dex key. Returns dex key or None."""
    if not text:
        return None
    t = text.strip().strip(".,!'-")
    low = t.lower()
    if low in cache:
        return cache[low]
    key = _try_dex(t)
    if len(cache) >= _CACHE_CAP:
        cache.clear()
    cache[low] = key
    return key


def resolve_move(text):
    if not text:
        return None
    t = text.strip().strip(".,!").lower()
    if t in _MOVE_CACHE:
        return _MOVE_CACHE[t]
    if t in _MOVE_INDEX:
        result = _MOVE_INDEX[t]
    else:
        close = difflib.get_close_matches(t, list(_MOVE_INDEX), n=1, cutoff=0.85)
        result = _MOVE_INDEX[close[0]] if close else None
    if len(_MOVE_CACHE) >= _CACHE_CAP:
        _MOVE_CACHE.clear()
    _MOVE_CACHE[t] = result
    return result


def new_mon(key, side=None):
    return {
        "key": key,
        "name": DEX[key]["name"],
        "types": DEX[key]["types"],
        "base_spe": DEX[key]["baseStats"]["spe"],
        "level": 80,
        "moves": [],
        "ability": None,
        "item": None,
        "seeded": False,
        "fainted": False,
        "status": None,
        "speed_stage": 0,
        "side": side,
    }


def _sid(side, key):
    return f"{side}:{key}"


class BattleState:
    STATE_FILE = DATA_DIR.parent / "battlestate.json"

    def __init__(self):
        self.my_active_key = None     # side-qualified id, e.g. "my:pikachu"
        self.their_active_key = None  # e.g. "their:garchomp"
        self.mons = {}                # sid -> mon dict
        self.turn = 0
        self.events = []              # recent raw log lines (last 40)
        self.menu_mode = None         # 'attack' | 'switch' | None
        self.menu_moves = []          # move keys when attack menu open
        self.my_fainted = []          # sids
        self.their_fainted = []       # sids
        self.my_hp = None
        self.their_hp = None
        self.my_hp_prev = None        # last tick's bar reading (pre-replacement HP)
        self.their_hp_prev = None
        self._came_back = {"my": False, "their": False}
        self.pending_switch = None
        self._last_my_active = None      # remembered through "Come back" clears
        self._last_their_active = None
        self.my_team_data = {}           # pre-battle scans: dexkey -> moves/item/level
        self.load()

    # ---------- persistence ----------

    def save(self):
        try:
            data = {
                "turn": self.turn,
                "my_active": self.my_active_key,
                "their_active": self.their_active_key,
                "my_hp": self.my_hp,
                "their_hp": self.their_hp,
                "my_fainted": self.my_fainted,
                "their_fainted": self.their_fainted,
                "mons": self.mons,
                "my_team_data": self.my_team_data,
            }
            self.STATE_FILE.write_text(json.dumps(data), encoding="utf8")
        except Exception as e:
            from . import log_error
            log_error(f"save failed: {e}")

    def load(self):
        try:
            data = json.loads(self.STATE_FILE.read_text(encoding="utf8"))
        except Exception:
            return
        self.turn = data.get("turn", 0)
        self.my_active_key = data.get("my_active")
        self.their_active_key = data.get("their_active")
        self.my_hp = data.get("my_hp")
        self.their_hp = data.get("their_hp")
        self.my_fainted = data.get("my_fainted", [])
        self.their_fainted = data.get("their_fainted", [])
        for sid, m in (data.get("mons") or {}).items():
            # side-qualified ids carry "my:"/"their:" - older formats are dropped
            if ":" in sid and m.get("key") in DEX:
                m.setdefault("side", sid.split(":", 1)[0])
                self.mons[sid] = m
        for key, d in (data.get("my_team_data") or {}).items():
            if key in DEX:
                self.my_team_data[key] = d

    def reset(self):
        self.my_active_key = None
        self.their_active_key = None
        self.mons = {}
        self.turn = 0
        self.events = []
        self.menu_mode = None
        self.menu_moves = []
        self.my_fainted = []
        self.their_fainted = []
        self.my_hp = None
        self.their_hp = None
        self.my_hp_prev = None
        self.their_hp_prev = None
        self._came_back = {"my": False, "their": False}
        self.pending_switch = None

    def mon(self, sid, side=None):
        if sid and sid not in self.mons:
            dexkey = sid.split(":", 1)[1] if ":" in sid else sid
            if dexkey in DEX:
                self.mons[sid] = new_mon(dexkey, side)
        return self.mons.get(sid)

    def _active_dex_key(self, side):
        sid = self.my_active_key if side == "my" else self.their_active_key
        return self.mons.get(sid, {}).get("key") if sid else None

    def _attr_sid(self, key, default_side=None):
        """Attribute a side-unmarked log mention to a mon.
        Returns sid or None when ambiguous (e.g. true mirror)."""
        my_sid, th_sid = self.my_active_key, self.their_active_key
        my_k = self._active_dex_key("my")
        th_k = self._active_dex_key("their")
        if key == my_k and key != th_k:
            return my_sid
        if key == th_k and key != my_k:
            return th_sid
        my_hit = [s for s, m in self.mons.items()
                  if m.get("key") == key and m.get("side") == "my"]
        th_hit = [s for s, m in self.mons.items()
                  if m.get("key") == key and m.get("side") == "their"]
        if my_hit and not th_hit:
            return my_hit[0]
        if th_hit and not my_hit:
            return th_hit[0]
        if default_side:
            return _sid(default_side, key)
        return None

    # ---------- log parsing ----------

    def feed(self, text):
        """Feed one OCR'd log chunk (multi-line). Each line parsed exactly once."""
        for raw in text.splitlines():
            line = raw.strip()
            if not line or len(line) < 4:
                continue
            self.events.append(line)
            self._parse_line(line)
        self.events = self.events[-40:]

    def _parse_line(self, line):
        low = line.lower()

        m = re.match(r"battle turn #(\d+) ended", low)
        if m:
            n = int(m.group(1))
            if self.turn and n < self.turn and n <= 2:
                self.reset()
            self.turn = n
            return

        m = re.match(r"^(?:the opposing )?(.+?) sends out (.+?)!$", low)
        if not m:
            m = re.match(r"^(?:the opposing )?(.+?) sen\w* o\w{0,2} (.+?)!$", low)
        if m:
            self._handle_send_out("their", m.group(2))
            return

        m = re.match(r"^go,? (.+?)!$", low)
        if m:
            self._handle_send_out("my", m.group(1))
            return

        m = re.match(r"^come back, (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                sid = _sid("my", key)
                sid_t = _sid("their", key)
                if sid == self.my_active_key:
                    self.my_active_key = None
                    self._came_back["my"] = True
                elif sid_t == self.their_active_key:
                    self.their_active_key = None
                    self._came_back["their"] = True
            return

        # attacks carry a reliable side marker ("The opposing X attacks ...")
        m = re.match(r"^(the opposing )?(.+?) attacks (?:the opposing )?(.+?) with (.+?)\.?$", low)
        if m:
            side = "their" if m.group(1) else "my"
            key = resolve_mon(m.group(2))
            move = resolve_move(m.group(4))
            if key and move:
                mon = self.mon(_sid(side, key), side)
                if mon and move not in mon["moves"]:
                    mon["moves"].append(move)
            return

        # "X used Y" lines reveal status/setup moves (Swords Dance, Dragon Dance...)
        m = re.match(r"^(the opposing )?(.+?) used (.+?)\.?$", low)
        if m:
            side = "their" if m.group(1) else "my"
            key = resolve_mon(m.group(2))
            move = resolve_move(m.group(3))
            if key and move:
                mon = self.mon(_sid(side, key), side)
                if mon and move not in mon["moves"]:
                    mon["moves"].append(move)
            return

        m = re.match(r"^(?:the opposing )?(.+?) (?:has )?fainted", low)
        if m:
            key = resolve_mon(m.group(1))
            self._handle_faint(key)
            return

        m = re.match(r"^(.+?) restored hp using (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            sid = self._attr_sid(key)
            if sid:
                matched = match_item(m.group(2))
                self.mons[sid]["item"] = matched if matched else m.group(2).title()
            return

        m = re.match(r"^(.+?) knocked off (?:the opposing )?(.+?)'s (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(2))
            sid = self._attr_sid(key)
            if sid:
                self.mons[sid]["item"] = m.group(3).title() + " (knocked off)"
            return

        m = re.match(r"^(.+?) was hurt by (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            sid = self._attr_sid(key)
            if sid and ("orb" in m.group(2) or "life orb" in m.group(2)):
                self.mons[sid]["item"] = "Life Orb"
            return

        m = re.match(r"^(?:the opposing )?(.+?)'s speed (?:sharply |drastically )?(rose|fell)", low)
        if m:
            key = resolve_mon(m.group(1))
            sid = self._attr_sid(key)
            if sid:
                mon = self.mons[sid]
                up = m.group(2) == "rose"
                mag = 2 if ("sharply" in low or "drastically" in low) else 1
                if up:
                    mon["speed_stage"] = min(6, mon.get("speed_stage", 0) + mag)
                else:
                    mon["speed_stage"] = max(-6, mon.get("speed_stage", 0) - mag)
            return

        m = re.match(r"^(.+?)'s (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            what = m.group(2)
            if key:
                sid = self._attr_sid(key)
                if sid and "rose" not in what and "fell" not in what and not any(
                    w in what for w in
                    ("was", "is", "were", "disabled", "sharply", "drastically", "hinted")
                ) and 1 <= len(what.split()) <= 3:
                    self.mons[sid]["ability"] = what.title()
            return

        m = re.match(r"^(.+?) (?:was|is|became) (badly )?poisoned", low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = "TOX" if m.group(2) else "PSN"
            return

        m = re.match(r"^(.+?) was (paralyzed|burned|frozen)", low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = m.group(2)[:3].upper()
            return

        m = re.match(r"^(.+?) fell asleep", low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = "SLP"
            return

        m = re.match(r"^(.+?) (?:woke up|thawed out|snapped out of its confusion)", low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = None
            return

        m = re.match(r"^(.+?) was seeded!$", low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["seeded"] = True
            return

    def _handle_send_out(self, side, name_text):
        key = resolve_mon(name_text)
        if not key:
            return
        sid = _sid(side, key)
        old = self.my_active_key if side == "my" else self.their_active_key
        if old and old != sid and not self._came_back[side] \
                and not self.mons.get(old, {}).get("fainted"):
            self.mons.setdefault(old, new_mon(old.split(":", 1)[1], side))["fainted"] = True
            fl = self.my_fainted if side == "my" else self.their_fainted
            if old not in fl:
                fl.append(old)
        if side == "my":
            self.my_active_key = sid
            self._last_my_active = sid
        else:
            self.their_active_key = sid
            self._last_their_active = sid
        m = self.mon(sid, side)
        if m:
            m["fainted"] = False   # sent out = alive
            m["speed_stage"] = 0   # fresh entry = no stat stages
            if side == "my":
                self._apply_team_data(key)
        self._came_back[side] = False

    def _handle_faint(self, key):
        if not key:
            return
        my_sid, th_sid = self.my_active_key, self.their_active_key
        my_k = self._active_dex_key("my")
        th_k = self._active_dex_key("their")
        # mirror matches: both actives share the dex key - attribute mine first
        if key == my_k:
            sid = my_sid
        elif key == th_k:
            sid = th_sid
        else:
            sid = self._attr_sid(key)
        if not sid:
            return
        self.mons.setdefault(sid, new_mon(key, sid.split(":", 1)[0]))["fainted"] = True
        if sid == self.my_active_key:
            if sid not in self.my_fainted:
                self.my_fainted.append(sid)
            self.my_active_key = None
            self.pending_switch = sid
        elif sid == self.their_active_key:
            if sid not in self.their_fainted:
                self.their_fainted.append(sid)
            self.their_active_key = None

    # ---------- party panel ----------

    def register_party(self, text):
        """Parse party-panel OCR: name/level lines. The panel is ground truth."""
        if not text:
            return
        seen = []
        roster = []   # (key, level or None) in panel order
        current = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            lm = re.search(r"(\d+)", line)
            core = re.sub(r"(?:lv\.?\s*)?[\d.\s]+$", "", line).strip(" .:♀♂")
            key = resolve_mon(core) if len(core) >= 3 else None
            if key:
                current = key
                roster.append([key, None])
                seen.append(_sid("my", key))
            elif lm and current is not None and roster:
                lvl = int(lm.group(1))
                while lvl > 100:
                    lvl = int(str(lvl)[:-1])
                if 1 <= lvl <= 100:
                    roster[-1][1] = lvl
                    current = None

        # a full panel of mons we've never seen = a new battle the turn-reset
        # missed (e.g. coach started mid-queue): wipe stale state
        known_my = [s for s, m in self.mons.items() if m.get("side") == "my"]
        if len(seen) >= 4 and known_my and not (set(known_my) & set(seen)):
            self.reset()

        for key, lvl in roster:
            sid = _sid("my", key)
            m = self.mon(sid, "my")
            if m and lvl:
                m["level"] = lvl
            if m:
                self._apply_team_data(key)   # scanned moves/items merge in

        # prune ghosts: alive 'my' mons not in the current panel
        # (never the active mon - a garbled panel read must not wipe its scout data)
        for key in [k for k, m in self.mons.items()
                    if m.get("side") == "my" and not m.get("fainted")
                    and k not in seen and k != self.my_active_key]:
            del self.mons[key]

    # ---------- pre-battle team scans (PvP mode) ----------

    def register_scanned(self, key, moves=None, item=None, level=None):
        """Stores a scanned team member. Survives battle resets; merged into
        the mon's live entry the moment it enters a battle.

        Gates: moves the species cannot learn are dropped (OCR cross-reads),
        and an entry with no usable data at all is not stored."""
        if not key or key not in DEX:
            return
        clean_moves = moves_in_learnset(key, [mv for mv in (moves or []) if mv in MOVES])
        if not clean_moves and not item and not level:
            return
        d = self.my_team_data.setdefault(key, {"moves": [], "item": None, "level": None})
        for mv in clean_moves:
            if mv not in d["moves"] and len(d["moves"]) < 6:
                d["moves"].append(mv)
        if item:
            d["item"] = item
        if level and 1 <= level <= 100:
            d["level"] = level
        self._apply_team_data(key)
        self.save()

    def _apply_team_data(self, key):
        d = self.my_team_data.get(key)
        if not d:
            return
        m = self.mons.get(_sid("my", key))
        if not m:
            return
        for mv in d["moves"]:
            if mv not in m["moves"]:
                m["moves"].append(mv)
        if d["item"] and not m.get("item"):
            m["item"] = d["item"]
        if d["level"] and (not m.get("level") or m.get("level") == 80):
            m["level"] = d["level"]

    # ---------- field nameplates ----------

    def set_field_active(self, side, text):
        """Authoritative active-mon override from the on-field HP nameplate."""
        if not text:
            return False
        raw = text.strip()
        lm = re.search(r"lv\.?\s*(\d+)", raw, re.I)
        level = int(lm.group(1)) if lm else None
        name_part = re.split(r"\blv\b|\blv\.|♂|♀|\u2642|\u2640", raw, flags=re.I)[0]
        name_part = name_part.strip(" .:;|-_0123456789")
        if len(name_part) < 3:
            return False
        key = resolve_mon(name_part)
        if not key:
            return False
        sid = _sid(side, key)
        old = (self.my_active_key if side == "my" else self.their_active_key) \
            or (self._last_my_active if side == "my" else self._last_their_active)
        pre_hp = self.my_hp_prev if side == "my" else self.their_hp_prev
        came_back = self._came_back[side]
        if old and old != sid:
            om = self.mons.get(old)
            if om and not om.get("fainted"):
                # replaced without Come back = faint. With Come back: PRO also
                # recalls fainted mons, so use last-seen HP - a weak mon that
                # leaves was almost certainly KO'd, a healthy one was pivoted.
                likely_fainted = (not came_back) or (pre_hp is not None and pre_hp <= 0.45)
                if likely_fainted:
                    om["fainted"] = True
                    fl = self.my_fainted if side == "my" else self.their_fainted
                    if old not in fl:
                        fl.append(old)
        if side == "my":
            self.my_active_key = sid
            self._last_my_active = sid
        else:
            self.their_active_key = sid
            self._last_their_active = sid
        m = self.mon(sid, side)
        if m:
            m["fainted"] = False   # on the field = alive, self-heal wrong marks
            if level:
                m["level"] = level
        return True

    # ---------- menu parsing ----------

    def feed_menu(self, text):
        low = text.lower()
        if "choose attack" in low:
            self.menu_mode = "attack"
            self.menu_moves = []
            for line in text.splitlines():
                mk = resolve_move(line.strip())
                if mk and mk not in self.menu_moves:
                    self.menu_moves.append(mk)
        elif "choose pokemon" in low or "choose pokémon" in low:
            self.menu_mode = "switch"
            self.menu_moves = []
        else:
            self.menu_mode = None
            self.menu_moves = []

    # ---------- summary ----------

    def state_line(self, advice):
        def tag(sid):
            m = self.mons.get(sid)
            if not m:
                return sid or "?"
            bits = [m["name"], f"{m['level']}"]
            if m.get("status"):
                bits.append(f"[{m['status']}]")
            if m.get("fainted"):
                bits.append("[DEAD]")
            if m.get("seeded"):
                bits.append("[SEEDED]")
            return " ".join(bits)

        my = self.mons.get(self.my_active_key)
        th = self.mons.get(self.their_active_key)
        lines = []
        lines.append(f"TURN {self.turn} | menu: {self.menu_mode or '-'}")
        hp_s = f" ~{int(self.my_hp*100)}%" if self.my_hp is not None else ""
        thp_s = f" ~{int(self.their_hp*100)}%" if self.their_hp is not None else ""
        if my:
            lines.append(f"MY ACTIVE: {tag(self.my_active_key)}{hp_s} ({'/'.join(my['types'])})")
        else:
            lines.append("MY ACTIVE: -")
        if th:
            lines.append(f"THEIR ACTIVE: {tag(self.their_active_key)}{thp_s} ({'/'.join(th['types'])})")
        else:
            lines.append("THEIR ACTIVE: -")
        bench = [
            tag(k)
            for k, m in self.mons.items()
            if m.get("side") == "my" and k != self.my_active_key and not m.get("fainted")
        ]
        if bench:
            lines.append("MY BENCH: " + " | ".join(bench))
        if my and self.menu_moves:
            lines.append("MY MOVES: " + ", ".join(MOVES[mk]["name"] for mk in self.menu_moves))
        if th and th["moves"]:
            lines.append("THEIR REVEALED MOVES: " + ", ".join(MOVES[mk]["name"] for mk in th["moves"]))
        scout = []
        for sid, m in self.mons.items():
            tags = []
            if m.get("ability"):
                tags.append(f"ability {m['ability']}")
            if m.get("item"):
                tags.append(f"item {m['item']}")
            if m.get("seeded"):
                tags.append("LEECH SEEDED")
            if tags:
                scout.append(f"{m['name']}: " + ", ".join(tags))
        if scout:
            lines.append("SCOUT: " + " || ".join(scout[-8:]))
        if self.my_fainted or self.their_fainted:
            fmine = ", ".join(tag(k) for k in self.my_fainted) or "-"
            ftheirs = ", ".join(tag(k) for k in self.their_fainted) or "-"
            lines.append(f"FAINTED mine: {fmine} | theirs: {ftheirs}")
        if advice:
            lines.append("ADVICE: " + advice)
        return "\n".join(lines)
