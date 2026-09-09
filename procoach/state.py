"""Parses OCR'd battle-log lines into a live battle state (the scout sheet)."""
import difflib
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

with open(DATA_DIR / "dex.json", encoding="utf8") as f:
    DEX = json.load(f)
with open(DATA_DIR / "moves.json", encoding="utf8") as f:
    MOVES = json.load(f)

_NAME_INDEX = {e["name"].lower(): key for key, e in DEX.items()}
_MOVE_INDEX = {e["name"].lower(): key for key, e in MOVES.items()}
_NAME_ALIASES = {
    "slowking galar": "slowkinggalar",
    "slowking": "slowking",  # keep plain slowking distinct
}

RESOLVE_CACHE = {}


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
    cache[low] = key
    return key


def resolve_move(text):
    if not text:
        return None
    t = text.strip().strip(".,!").lower()
    if t in _MOVE_INDEX:
        return _MOVE_INDEX[t]
    close = difflib.get_close_matches(t, list(_MOVE_INDEX), n=1, cutoff=0.85)
    return _MOVE_INDEX[close[0]] if close else None


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
        "side": side,
    }


class BattleState:
    STATE_FILE = DATA_DIR.parent / "battlestate.json"

    def __init__(self):
        self.my_active_key = None
        self.their_active_key = None
        self.mons = {}          # dex key -> mon dict
        self.turn = 0
        self.events = []        # recent raw log lines (last 40)
        self.menu_mode = None   # 'attack' | 'switch' | None
        self.menu_moves = []    # move keys when attack menu open
        self.my_fainted = []
        self.their_fainted = []
        self.my_hp = None       # 0.0..1.0 from bar scan
        self.their_hp = None
        self._came_back = {"my": False, "their": False}
        self.pending_switch = None   # set when my mon faints: "pick next"
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
            }
            self.STATE_FILE.write_text(json.dumps(data), encoding="utf8")
        except Exception:
            pass

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
        for key, m in (data.get("mons") or {}).items():
            if key in DEX:
                m.setdefault("side", None)
                self.mons[key] = m

    def reset(self):
        self.my_active_key = None
        self.their_active_key = None
        self.mons = {}          # dex key -> mon dict
        self.turn = 0
        self.events = []        # recent raw log lines (last 40)
        self.menu_mode = None   # 'attack' | 'switch' | None
        self.menu_moves = []    # move keys when attack menu open
        self.my_fainted = []
        self.their_fainted = []
        self.my_hp = None
        self.their_hp = None
        self._came_back = {"my": False, "their": False}
        self.pending_switch = None

    def mon(self, key, side=None):
        if key and key not in self.mons:
            self.mons[key] = new_mon(key, side)
        return self.mons.get(key)

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
            # new battle: turn counter dropped back to the start
            if self.turn and n < self.turn and n <= 2:
                self.reset()
            self.turn = n
            return

        m = re.match(r"^(?:the opposing )?(.+?) sends out (.+?)!$", low)
        if not m:
            # OCR-garbled variants: 'senos out', 'sends ot', 'sends ou'...
            m = re.match(r"^(?:the opposing )?(.+?) sen\w* o\w{0,2} (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(2))
            if key:
                old = self.their_active_key
                if (
                    old and old != key
                    and not self._came_back["their"]
                    and not self.mons.get(old, {}).get("fainted")
                ):
                    self.mons.setdefault(old, new_mon(old))["fainted"] = True
                    if old not in self.their_fainted:
                        self.their_fainted.append(old)
                self.their_active_key = key
                self.mon(key, side="their")
                self.mons[key]["fainted"] = False   # sent out = alive
                self._came_back["their"] = False
            return

        m = re.match(r"^go,? (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                old = self.my_active_key
                if (
                    old and old != key
                    and not self._came_back["my"]
                    and not self.mons.get(old, {}).get("fainted")
                ):
                    self.mons.setdefault(old, new_mon(old))["fainted"] = True
                    if old not in self.my_fainted:
                        self.my_fainted.append(old)
                self.my_active_key = key
                self.mon(key, side="my")
                self.mons[key]["fainted"] = False   # sent out = alive
                self._came_back["my"] = False
                self.pending_switch = None   # pick was made
            return

        m = re.match(r"^come back, (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                if key == self.my_active_key:
                    self.my_active_key = None
                    self._came_back["my"] = True
                elif key == self.their_active_key:
                    self.their_active_key = None
                    self._came_back["their"] = True
            return

        m = re.match(r"^(the opposing )?(.+?) attacks (?:the opposing )?(.+?) with (.+?)\.?$", low)
        if m:
            attacker = resolve_mon(m.group(2))
            move = resolve_move(m.group(4))
            if attacker and move:
                mon = self.mon(attacker)
                if move not in mon["moves"]:
                    mon["moves"].append(move)
            return

        m = re.match(r"^(?:the opposing )?(.+?) (?:has )?fainted", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["fainted"] = True
                if key == self.my_active_key:
                    self.my_fainted.append(key)
                    self.my_active_key = None
                    self.pending_switch = key   # prompt switch pick NOW
                elif key == self.their_active_key:
                    self.their_fainted.append(key)
                    self.their_active_key = None
            return

        m = re.match(r"^(.+?) restored hp using (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["item"] = m.group(2).title()
            return

        m = re.match(r"^(.+?) knocked off (?:the opposing )?(.+?)'s (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(2))
            if key:
                self.mon(key)["item"] = m.group(3).title() + " (knocked off)"
            return

        m = re.match(r"^(.+?) was hurt by (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            if key and "orb" in m.group(2) or "life orb" in m.group(2):
                self.mon(key)["item"] = "Life Orb"
            return

        m = re.match(r"^(.+?)'s (.+?)!$", low)
        if m:
            key = resolve_mon(m.group(1))
            what = m.group(2)
            if key:
                mon = self.mon(key)
                if "rose" in what or "fell" in what:
                    pass  # stat stages: noted via effectiveness anyway
                elif not any(
                    w in what for w in
                    ("was", "is", "were", "disabled", "sharply", "drastically", "hinted", "rose", "fell")
                ) and 1 <= len(what.split()) <= 3:
                    mon["ability"] = what.title()
            return

        m = re.match(r"^(.+?) (?:was|is|became) (badly )?poisoned", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["status"] = "TOX" if m.group(2) else "PSN"
            return

        m = re.match(r"^(.+?) was (paralyzed|burned|frozen)", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["status"] = m.group(2)[:3].upper()
            return

        m = re.match(r"^(.+?) fell asleep", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["status"] = "SLP"
            return

        m = re.match(r"^(.+?) (?:woke up|thawed out|snapped out of its confusion)!", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["status"] = None
            return

        m = re.match(r"^(.+?) was seeded!$", low)
        if m:
            key = resolve_mon(m.group(1))
            if key:
                self.mon(key)["seeded"] = True
            return

    def register_party(self, text):
        """Parse party-panel OCR: name/level lines. The panel is ground truth:
        bench mons not on it are stale ghosts from a previous battle."""
        if not text:
            return
        seen = []
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
                m = self.mon(key, side="my")
                seen.append(key)
            elif lm and current:
                lvl = int(lm.group(1))
                while lvl > 100:  # OCR merges ('810' -> 81)
                    lvl = int(str(lvl)[:-1])
                if 1 <= lvl <= 100:
                    self.mons[current]["level"] = lvl
                    current = None
        # prune ghosts: alive 'my' mons not in the current panel
        for key in [k for k, m in self.mons.items()
                    if m.get("side") == "my" and not m.get("fainted") and k not in seen]:
            del self.mons[key]

    # ---------- field nameplates ----------

    def set_field_active(self, side, text):
        """Authoritative active-mon override from the on-field HP nameplate.

        Text looks like 'Slowking Lv 84' / 'Thundurus Lv.80'. Returns True if
        a species was resolved.
        """
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
        if side == "my":
            old = self.my_active_key
        else:
            old = self.their_active_key
        # replacement without a logged "Come back" = the old mon fainted
        # (faint line missed by OCR); heals if it ever re-enters the field
        came_back = self._came_back[side]
        if old and old != key and not came_back:
            om = self.mons.get(old)
            if om and not om.get("fainted"):
                om["fainted"] = True
                fl = self.my_fainted if side == "my" else self.their_fainted
                if old not in fl:
                    fl.append(old)
        if side == "my":
            self.my_active_key = key
        else:
            self.their_active_key = key
        m = self.mon(key, side=side)
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

    def score(self):
        their_total = len({k for k, m in self.mons.items()}) - len(self.my_fainted)
        # fallback: we only know mons we've seen
        mine_alive = 6 - len(self.my_fainted) if self.my_fainted else None
        return mine_alive, len(self.their_fainted)

    def state_line(self, advice):
        def nm(key):
            return self.mons[key]["name"] if key in self.mons else (key or "?")

        def tag(key):
            m = self.mons.get(key)
            if not m:
                return key or "?"
            bits = [m["name"], f"{m['level']}"]
            if m.get("status"):
                bits.append(f"[{m['status']}]")
            if m.get("fainted"):
                bits.append("[DEAD]")
            if m.get("seeded"):
                bits.append("[SEEDED]")
            return " ".join(bits)

        my = self.mon(self.my_active_key) if self.my_active_key else None
        th = self.mon(self.their_active_key) if self.their_active_key else None
        lines = []
        lines.append(f"TURN {self.turn} | menu: {self.menu_mode or '-'}")
        hp_s = f" ~{int(self.my_hp*100)}%" if self.my_hp is not None else ""
        thp_s = f" ~{int(self.their_hp*100)}%" if self.their_hp is not None else ""
        lines.append(f"MY ACTIVE: {tag(self.my_active_key) + hp_s + ' (' + '/'.join(my['types']) + ')' if my else '-'}")
        lines.append(f"THEIR ACTIVE: {tag(self.their_active_key) + thp_s + ' (' + '/'.join(th['types']) + ')' if th else '-'}")
        bench = [
            tag(k)
            for k, m in self.mons.items()
            if m.get("side") == "my" and k not in (self.my_active_key,) and not m.get("fainted")
        ]
        if bench:
            lines.append("MY BENCH: " + " | ".join(bench))
        if my and self.menu_moves:
            lines.append("MY MOVES: " + ", ".join(MOVES[mk]["name"] for mk in self.menu_moves))
        if th and th["moves"]:
            lines.append("THEIR REVEALED MOVES: " + ", ".join(MOVES[mk]["name"] for mk in th["moves"]))
        scout = []
        for key, m in self.mons.items():
            tags = []
            if m["ability"]:
                tags.append(f"ability {m['ability']}")
            if m["item"]:
                tags.append(f"item {m['item']}")
            if m["seeded"]:
                tags.append("LEECH SEEDED")
            if tags:
                scout.append(f"{m['name']}: " + ", ".join(tags))
        if scout:
            lines.append("SCOUT: " + " || ".join(scout[-8:]))
        if self.my_fainted or self.their_fainted:
            lines.append(
                f"FAINTED mine: {', '.join(nm(k) for k in self.my_fainted) or '-'}"
                f" | theirs: {', '.join(nm(k) for k in self.their_fainted) or '-'}"
            )
        if advice:
            lines.append("ADVICE: " + advice)
        return "\n".join(lines)
