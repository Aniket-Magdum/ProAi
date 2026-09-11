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


ITEM_ALIASES = {
    "scarf": "Choice Scarf",
    "band": "Choice Band",
    "specs": "Choice Specs",
    "boots": "Heavy-Duty Boots",
    "boot": "Heavy-Duty Boots",
    "heavy duty boots": "Heavy-Duty Boots",
    "sash": "Focus Sash",
    "balloon": "Air Balloon",
    "air balloon": "Air Balloon",
    "av": "Assault Vest",
    "assault vest": "Assault Vest",
    "lefties": "Leftovers",
    "leftover": "Leftovers",
    "leftovers": "Leftovers",
    "orb": "Life Orb",
    "life orb": "Life Orb",
    "helmet": "Rocky Helmet",
    "rocky helmet": "Rocky Helmet",
    "eviolite": "Eviolite",
    "sludge": "Black Sludge",
    "black sludge": "Black Sludge",
    "lo": "Life Orb",
    "hdb": "Heavy-Duty Boots",
    "lum": "Lum Berry",
    "sitrus": "Sitrus Berry",
}


def match_item(text):
    """Finds an item name inside an OCR line or user entry, with alias support."""
    if not text:
        return None
    raw = text.strip().strip(".,!'")
    # Clean leading label prefixes like "Item:", "Held Item:", "Held:"
    clean = re.sub(r"^(?:held\s+item|item|held)\s*[:\s-]+\s*", "", raw, flags=re.I).strip()
    if clean.lower() in ("none", "no item", "nil", "n/a", "-", "(none)"):
        return None
    t = clean.lower().strip(".,!'")
    if t in ITEM_ALIASES:
        return ITEM_ALIASES[t]
    if t in ITEM_INDEX:
        return ITEM_INDEX[t]
    t_nospace = t.replace(" ", "")
    for low, disp in ITEM_INDEX.items():
        if low.replace(" ", "") == t_nospace:
            return disp
    for alias, disp in ITEM_ALIASES.items():
        if alias in t.split():
            return disp
    for low, disp in ITEM_INDEX.items():
        if len(low) > 4 and low in t:
            return disp
    close = difflib.get_close_matches(
        t, _ITEM_KEYS, n=1, cutoff=0.85
    )
    return ITEM_INDEX[close[0]] if close else None

_NAME_INDEX = {e["name"].lower(): key for key, e in DEX.items()}
_MOVE_INDEX = {e["name"].lower(): key for key, e in MOVES.items()}
_ITEM_KEYS = tuple(ITEM_INDEX.keys())
_NAME_KEYS = tuple(_NAME_INDEX.keys())
_MOVE_KEYS = tuple(_MOVE_INDEX.keys())
_RE_SPACES = re.compile(r"\s+")

RESOLVE_CACHE = {}  # capped at 5000 entries
_MOVE_CACHE = {}    # capped at 5000 entries
_CACHE_CAP = 5000


def _try_dex(text):
    clean = text.strip().strip(".,!'")
    low = clean.lower()
    t = _RE_SPACES.sub(" ", low.replace("-", " "))
    if t in _NAME_INDEX:
        return _NAME_INDEX[t]
    t_hyphen = t.replace(" ", "-")
    if t_hyphen in _NAME_INDEX:
        return _NAME_INDEX[t_hyphen]
    if t.startswith("mega "):
        rest = t[5:].split()
        if len(rest) >= 2 and rest[-1] in ("x", "y"):
            cand = f"{'-'.join(rest[:-1])}-mega-{rest[-1]}"
        else:
            cand = f"{'-'.join(rest)}-mega"
        if cand in _NAME_INDEX:
            return _NAME_INDEX[cand]
        cand_space = cand.replace("-", " ")
        if cand_space in _NAME_INDEX:
            return _NAME_INDEX[cand_space]
    # short names (Mew, Oddish...) garble easily in OCR; be more lenient
    cutoff = 0.6 if len(t) <= 5 else 0.8
    close = difflib.get_close_matches(t, _NAME_KEYS, n=1, cutoff=cutoff)
    return _NAME_INDEX[close[0]] if close else None


def resolve_mon(text, cache=RESOLVE_CACHE):
    """OCR-garbled display name -> dex key. Returns dex key or None."""
    if not text:
        return None
    t = text.strip().strip(".,!'-")
    # Strip battle log prefixes like 'the opposing ' or 'opposing '
    t = re.sub(r"^(?:the\s+)?opposing\s+", "", t, flags=re.I).strip()
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
        t_nospace = _RE_SPACES.sub("", t)
        if t_nospace in _MOVE_INDEX:
            result = _MOVE_INDEX[t_nospace]
        else:
            cutoff = 0.85 if len(t_nospace) <= 5 else 0.68
            close = difflib.get_close_matches(t, _MOVE_KEYS, n=1, cutoff=cutoff)
            if close:
                result = _MOVE_INDEX[close[0]]
            else:
                close_ns = difflib.get_close_matches(t_nospace, _MOVE_KEYS, n=1, cutoff=cutoff)
                result = _MOVE_INDEX[close_ns[0]] if close_ns else None
    if len(_MOVE_CACHE) >= _CACHE_CAP:
        _MOVE_CACHE.clear()
    _MOVE_CACHE[t] = result
    return result


def parse_mon_and_item(text):
    """Parses text that may contain a Pokemon species and an optional held item.
    Supports:
      - 'Zarude @ Choice Scarf' or 'Darkrai @ Life Orb'
      - 'Scarf Garchomp' or 'Leftovers Corviknight'
      - 'Garchomp'
    Returns (dexkey, item_name or None).
    """
    if not text:
        return None, None
    raw = text.strip()
    if "@" in raw:
        mon_part, item_part = raw.split("@", 1)
        mon_key = resolve_mon(mon_part)
        item = match_item(item_part) or item_part.strip()
        return mon_key, item

    tokens = raw.split()
    if len(tokens) >= 2:
        first = tokens[0].lower().strip(".,!'")
        if first in ITEM_ALIASES:
            mon_key = resolve_mon(" ".join(tokens[1:]))
            if mon_key:
                return mon_key, ITEM_ALIASES[first]
        last = tokens[-1].lower().strip(".,!'")
        if last in ITEM_ALIASES:
            mon_key = resolve_mon(" ".join(tokens[:-1]))
            if mon_key:
                return mon_key, ITEM_ALIASES[last]

    mon_key = resolve_mon(raw)
    return mon_key, None


def _extract_mon_key(text):
    if not text:
        return None
    clean = re.sub(r"\([MFmf]\)", "", text).strip()
    clean = re.sub(r"[♂♀★]", "", clean).strip()
    m = re.search(r"\(([^)]+)\)", clean)
    if m:
        cand = resolve_mon(m.group(1).strip())
        if cand:
            return cand
    return resolve_mon(clean)


def parse_stat_spread(text):
    """Parses 'EVs: 6 HP / 252 SpA / 252 Spe' or 'IVs: 18 HP / 29 Def' into a stat dict."""
    if not text:
        return {}
    if ":" in text:
        text = text.split(":", 1)[1]
    res = {}
    stat_map = {
        "hp": "hp",
        "atk": "atk", "attack": "atk",
        "def": "def", "defense": "def",
        "spa": "spa", "spatk": "spa", "sp.atk": "spa", "specialattack": "spa",
        "spd": "spd", "spdef": "spd", "sp.def": "spd", "specialdefense": "spd",
        "spe": "spe", "spd_spe": "spe", "speed": "spe",
    }
    matches = re.findall(r"(\d+)\s*([a-zA-Z.]+)", text)
    for num_str, s_name in matches:
        k = stat_map.get(s_name.lower().replace(" ", "").replace(".", ""))
        if k:
            try:
                res[k] = int(num_str)
            except ValueError:
                pass
    return res


def parse_showdown_team(text):
    """Parses standard Pokémon Showdown export, Poképaste, or PRO in-game copied text.
    Handles blocks with or without blank lines, items formatted with '@' or 'Item:',
    and PRO export lines (EVs, IVs, Natures, Abilities, Levels).
    Returns list of dicts:
        [{"key": dexkey, "name": name, "item": item, "ability": ability, "level": lvl, "nature": nature, "evs": {...}, "ivs": {...}, "moves": [mk1, ...], "locked": True}]
    """
    if not text:
        return []

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    results = []
    current = None

    def _finalize(mon_dict):
        if not mon_dict or not mon_dict.get("key"):
            return
        mon_dict["moves"] = mon_dict.get("moves", [])[:4]
        results.append(mon_dict)

    for ln in lines:
        if ln.startswith("===") or ln.startswith("---") or ln.startswith("***"):
            continue

        low = ln.lower()

        # Check if line is a new mon header:
        # e.g. "Ralts", "Zarude @ Choice Scarf", "Garchomp (M) @ Life Orb", "Chomp (Garchomp)"
        is_header = False
        mon_key = None
        item = None

        if "@" in ln:
            m_part, i_part = ln.split("@", 1)
            k = _extract_mon_key(m_part)
            if k:
                is_header = True
                mon_key = k
                item = match_item(i_part) or i_part.strip()
        elif not any(low.startswith(p) for p in ("level:", "lvl:", "lv.", "ability:", "item:", "held item:", "evs:", "ivs:", "nature", "moves:", "ot:", "id:", "-", "•", "*")):
            if "nature" not in low and not re.match(r"^[\d\s./%:]+$", ln):
                k = _extract_mon_key(ln)
                if k:
                    is_header = True
                    mon_key = k

        if is_header and mon_key:
            _finalize(current)
            name = DEX.get(mon_key, {}).get("name", mon_key.capitalize())
            current = {
                "key": mon_key,
                "name": name,
                "base_spe": DEX.get(mon_key, {}).get("baseStats", {}).get("spe", 80),
                "item": item,
                "ability": None,
                "level": 100,
                "nature": None,
                "evs": {},
                "ivs": {},
                "moves": [],
                "locked": True,
            }
            continue

        if not current:
            continue

        if low.startswith("evs:"):
            current["evs"] = parse_stat_spread(ln)
        elif low.startswith("ivs:"):
            current["ivs"] = parse_stat_spread(ln)
        elif low.startswith("item:") or low.startswith("held item:"):
            it_val = ln.split(":", 1)[1].strip()
            matched = match_item(it_val)
            current["item"] = matched or it_val
        elif low.startswith("ability:"):
            current["ability"] = ln.split(":", 1)[1].strip()
        elif low.startswith("level:") or low.startswith("lvl:") or re.match(r"^lv\.?\s*\d+", low):
            lm = re.search(r"\d+", ln)
            if lm:
                current["level"] = int(lm.group(0))
        elif "nature" in low:
            parts = ln.split()
            if parts:
                nat = parts[0].capitalize()
                if nat.lower() != "nature":
                    current["nature"] = nat
        elif ln.startswith("-") or ln.startswith("•") or ln.startswith("*") or re.match(r"^\d+\.\s*", ln):
            mv_txt = re.sub(r"^[-•*\d.]+\s*", "", ln).strip()
            mk = resolve_move(mv_txt)
            if mk and mk not in current["moves"] and len(current["moves"]) < 4:
                current["moves"].append(mk)
        else:
            mk = resolve_move(ln)
            if mk and mk not in current["moves"] and len(current["moves"]) < 4 and mk not in DEX:
                current["moves"].append(mk)

    _finalize(current)
    return results[:6]


def format_showdown_team(team_data, dex=None, moves_db=None):
    """Formats internal team data into clean Showdown / PRO copyable text."""
    if not team_data:
        return ""
    if dex is None:
        dex = DEX
    if moves_db is None:
        moves_db = MOVES

    blocks = []
    entries = team_data.values() if isinstance(team_data, dict) else team_data
    for entry in entries:
        if not isinstance(entry, dict) or not entry.get("key"):
            continue
        key = entry["key"]
        name = entry.get("name") or dex.get(key, {}).get("name", key.capitalize())
        item = entry.get("item")
        header = f"{name} @ {item}" if item else name
        lines = [header]

        ability = entry.get("ability")
        if ability:
            lines.append(f"Ability: {ability}")
        level = entry.get("level")
        if level and level != 100:
            lines.append(f"Level: {level}")
        nature = entry.get("nature")
        if nature:
            lines.append(f"{nature} Nature")

        evs = entry.get("evs")
        if evs and any(v > 0 for v in evs.values()):
            ev_parts = []
            for s_name in ("hp", "atk", "def", "spa", "spd", "spe"):
                if evs.get(s_name, 0) > 0:
                    label = "HP" if s_name == "hp" else ("SpA" if s_name == "spa" else ("SpD" if s_name == "spd" else s_name.capitalize()))
                    ev_parts.append(f"{evs[s_name]} {label}")
            if ev_parts:
                lines.append("EVs: " + " / ".join(ev_parts))

        ivs = entry.get("ivs")
        if ivs and any(v != 31 for v in ivs.values()):
            iv_parts = []
            for s_name in ("hp", "atk", "def", "spa", "spd", "spe"):
                if s_name in ivs:
                    label = "HP" if s_name == "hp" else ("SpA" if s_name == "spa" else ("SpD" if s_name == "spd" else s_name.capitalize()))
                    iv_parts.append(f"{ivs[s_name]} {label}")
            if iv_parts:
                lines.append("IVs: " + " / ".join(iv_parts))

        moves = entry.get("moves", [])
        for mk in moves:
            mv_name = moves_db.get(mk, {}).get("name", mk.title())
            lines.append(f"- {mv_name}")
        blocks.append("\n".join(lines))

    return "\n\n".join(blocks)



_SMOGON_DATA = None


def get_smogon_data():
    """Lazy load Smogon gen8ou usage dataset."""
    global _SMOGON_DATA
    if _SMOGON_DATA is None:
        try:
            p = DATA_DIR / "smogon_sets.json"
            if p.exists():
                _SMOGON_DATA = json.loads(p.read_text(encoding="utf8"))
            else:
                _SMOGON_DATA = {}
        except Exception:
            _SMOGON_DATA = {}
    return _SMOGON_DATA


def get_opponent_unrevealed_scout(species_key, revealed_moves=None, my_types=None):
    """Returns top unrevealed moves for an opponent species based on Smogon usage statistics.
    Filters out revealed_moves and flags super-effective threats vs my_types.
    """
    if not species_key:
        return []
    smogon = get_smogon_data().get(species_key, {})
    moves_usage = smogon.get("moves", {})
    if not moves_usage:
        return []

    from .calc import effectiveness

    rev_set = set(revealed_moves or [])
    my_t_set = [t.lower() for t in my_types] if my_types else []

    scored = []
    for mk, freq in moves_usage.items():
        if mk in rev_set:
            continue
        m_info = MOVES.get(mk)
        if not m_info:
            continue
        pct = int(round(freq * 100))
        if pct < 5:
            continue
        cat = m_info.get("category", "Status")
        m_type = m_info.get("type", "Normal")
        eff = effectiveness(m_type.lower(), my_t_set) if my_t_set else 1.0
        is_threat = (eff >= 2.0 and cat != "Status")
        
        # Threats get high priority so dangerous coverage appears first
        rank_score = (1000 + pct * 10) if is_threat else pct
        scored.append({
            "key": mk,
            "name": m_info.get("name", mk),
            "pct": pct,
            "type": m_type,
            "category": cat,
            "eff_vs_my": eff,
            "is_threat": is_threat,
            "rank_score": rank_score,
        })

    scored.sort(key=lambda x: x["rank_score"], reverse=True)
    return scored[:4]


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
        "speed_floor": None,
        "speed_ceiling": None,
        "inferred_archetype": None,
        "side": side,
    }


def _sid(side, key):
    return f"{side}:{key}"


# Pre-compiled log parsing regexes for fast matching
_RE_TIMESTAMP = re.compile(r"^\[\d{1,2}:\d{2}(?::\d{2})?(?:\s*[ap]m)?\]\s*")
_RE_BULLETS = re.compile(r"^[\s>*•|·\-_~]+\s*")
_RE_TURN = re.compile(r"(?:battle\s+)?turn\s*#?\s*(\d+)(?:\s+ended)?")
_RE_SEND_OUT_THEIR_1 = re.compile(r"^(?:the opposing )?(.+?) sends out (.+?)!$")
_RE_SEND_OUT_THEIR_2 = re.compile(r"^(?:the opposing )?(.+?) sen\w* o\w{0,2} (.+?)!$")
_RE_SEND_OUT_MY = re.compile(r"^go[,!]?\s*(.+?)!$")
_RE_COME_BACK = re.compile(r"^come back, (.+?)!$")
_RE_ATTACK = re.compile(r"^(the opposing )?(.+?) attacks (?:the opposing )?(.+?) with (.+?)\.?$")
_RE_USED = re.compile(r"^(the opposing )?(.+?) used (.+?)\.?$")
_RE_FAINTED = re.compile(r"^(?:the opposing )?(.+?) (?:has )?fainted")
_RE_RESTORE_HP = re.compile(r"^(.+?) restored hp using (.+?)!$")
_RE_KNOCK_OFF = re.compile(r"^(.+?) knocked off (?:the opposing )?(.+?)'s (.+?)!$")
_RE_LIFE_ORB = re.compile(r"^(.+?) was hurt by (.+?)!$")
_RE_SPEED_STAGE = re.compile(r"^(?:the opposing )?(.+?)'s speed (?:sharply |drastically )?(rose|fell)")
_RE_ABILITY = re.compile(r"^(.+?)'s (.+?)!$")
_RE_POISON = re.compile(r"^(.+?) (?:was|is|became) (badly )?poisoned")
_RE_STATUS = re.compile(r"^(.+?) was (paralyzed|burned|frozen)")
_RE_SLEEP = re.compile(r"^(.+?) fell asleep")
_RE_WAKE = re.compile(r"^(.+?) (?:woke up|thawed out|snapped out of its confusion)")
_RE_SEEDED = re.compile(r"^(.+?) was seeded!$")


class BattleState:
    STATE_FILE = DATA_DIR.parent / "battlestate.json"
    SAVED_TEAM_FILE = DATA_DIR.parent / "saved_team.txt"

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
        self.their_team = []             # opponent's team slots: list of {"key": dexkey, "item": item}
        self.th_choice_locked_move = None  # Choice item locked move key e.g. "earthquake"
        self._turn_actions = []            # (side, key, move) recorded in current turn for speed caliper
        self._last_saved_json = None
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
                "their_team": self.their_team,
                "th_choice_locked_move": self.th_choice_locked_move,
            }
            dumped = json.dumps(data)
            if dumped != getattr(self, "_last_saved_json", None):
                self.STATE_FILE.write_text(dumped, encoding="utf8")
                self._last_saved_json = dumped
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
        self.their_team = []
        for entry in (data.get("their_team") or []):
            if isinstance(entry, dict) and entry.get("key") in DEX:
                self.their_team.append({"key": entry["key"], "item": entry.get("item")})
            elif isinstance(entry, str) and entry in DEX:
                self.their_team.append({"key": entry, "item": None})
        self.th_choice_locked_move = data.get("th_choice_locked_move")

    def load_saved_team(self):
        """Loads permanent saved team from saved_team.txt if it exists."""
        if self.SAVED_TEAM_FILE.exists():
            try:
                raw_saved = self.SAVED_TEAM_FILE.read_text(encoding="utf8").strip()
                if raw_saved:
                    return self.import_showdown_team(raw_saved)
            except Exception:
                pass
        return 0

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
        self.their_team = []
        self.th_choice_locked_move = None
        self._turn_actions = []

    def _check_turn_order_caliper(self):
        """Compares turn attack sequence to calibrate opponent's speed floor or ceiling."""
        if len(self._turn_actions) < 2:
            return
        my_act = None
        their_act = None
        my_idx = -1
        their_idx = -1
        for idx, act in enumerate(self._turn_actions):
            if act.get("side") == "my" and my_act is None:
                my_act = act
                my_idx = idx
            elif act.get("side") == "their" and their_act is None:
                their_act = act
                their_idx = idx
        if not my_act or not their_act:
            return

        from .calc import get_move_priority, effective_speed
        prio_my = get_move_priority(my_act.get("move"))
        prio_th = get_move_priority(their_act.get("move"))

        # Only compare if move priorities are identical (neutral priority turns)
        if prio_my != prio_th:
            return

        my_mon = self.mons.get(self.my_active_key)
        th_mon = self.mons.get(self.their_active_key)
        if not my_mon or not th_mon:
            return

        my_spe = effective_speed(my_mon)

        if their_idx < my_idx:
            # Opponent moved FIRST: their speed >= my speed
            old_floor = th_mon.get("speed_floor")
            new_floor = max(old_floor or 0, my_spe)
            th_mon["speed_floor"] = new_floor
        elif my_idx < their_idx:
            # Player moved FIRST: their speed <= my speed
            old_ceil = th_mon.get("speed_ceiling")
            new_ceil = min(old_ceil or 999, my_spe)
            th_mon["speed_ceiling"] = new_ceil

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
        has_lines = False
        for raw in text.splitlines():
            line = raw.strip()
            if not line or len(line) < 4:
                continue
            has_lines = True
            self.events.append(line)
            self._parse_line(line)
        self.events = self.events[-40:]
        if has_lines:
            self.save()

    def _parse_line(self, line):
        # Strip timestamp prefix e.g. [12:34:56] or [12:34] or [02:30 pm]
        clean = _RE_TIMESTAMP.sub("", line)
        # Strip leading bullet/noise characters e.g. > * - • |
        clean = _RE_BULLETS.sub("", clean)
        low = clean.lower()

        m = _RE_TURN.search(low)
        if m:
            n = int(m.group(1))
            if self.turn and n < self.turn and n <= 2:
                self.reset()
            self.turn = n
            self._turn_actions = []
            return

        m = _RE_SEND_OUT_THEIR_1.match(low)
        if not m:
            m = _RE_SEND_OUT_THEIR_2.match(low)
        if m:
            self._handle_send_out("their", m.group(2))
            return

        m = _RE_SEND_OUT_MY.match(low)
        if m:
            self._handle_send_out("my", m.group(1))
            return

        m = _RE_COME_BACK.match(low)
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
                    self.th_choice_locked_move = None
            return

        # attacks carry a reliable side marker ("The opposing X attacks ...")
        m = _RE_ATTACK.match(low)
        if m:
            side = "their" if m.group(1) else "my"
            key = resolve_mon(m.group(2))
            move = resolve_move(m.group(4))
            if key and move:
                self._turn_actions.append({"side": side, "key": key, "move": move})
                self._check_turn_order_caliper()
                mon = self.mon(_sid(side, key), side)
                if mon and move not in mon["moves"]:
                    mon["moves"].append(move)
                if side == "my" and key in self.my_team_data:
                    t_entry = self.my_team_data[key]
                    if move not in t_entry.setdefault("moves", []) and len(t_entry["moves"]) < 4:
                        t_entry["moves"].append(move)
                    t_entry["locked"] = True
                elif side == "their":
                    th_item = (mon.get("item") or "").lower() if mon else ""
                    if not th_item and key:
                        for te in self.their_team:
                            if isinstance(te, dict) and te.get("key") == key and te.get("item"):
                                th_item = te["item"].lower()
                                break
                    if any(ci in th_item for ci in ("choice", "scarf", "band", "specs")):
                        self.th_choice_locked_move = move
            return

        # "X used Y" lines reveal status/setup moves (Swords Dance, Dragon Dance...)
        m = _RE_USED.match(low)
        if m:
            side = "their" if m.group(1) else "my"
            key = resolve_mon(m.group(2))
            move = resolve_move(m.group(3))
            if key and move:
                self._turn_actions.append({"side": side, "key": key, "move": move})
                self._check_turn_order_caliper()
                mon = self.mon(_sid(side, key), side)
                if mon and move not in mon["moves"]:
                    mon["moves"].append(move)
                if side == "my" and key in self.my_team_data:
                    t_entry = self.my_team_data[key]
                    if move not in t_entry.setdefault("moves", []) and len(t_entry["moves"]) < 4:
                        t_entry["moves"].append(move)
                    t_entry["locked"] = True
                elif side == "their":
                    th_item = (mon.get("item") or "").lower() if mon else ""
                    if not th_item and key:
                        for te in self.their_team:
                            if isinstance(te, dict) and te.get("key") == key and te.get("item"):
                                th_item = te["item"].lower()
                                break
                    if any(ci in th_item for ci in ("choice", "scarf", "band", "specs")):
                        self.th_choice_locked_move = move
            return

        m = _RE_FAINTED.match(low)
        if m:
            key = resolve_mon(m.group(1))
            self._handle_faint(key)
            return

        m = _RE_RESTORE_HP.match(low)
        if m:
            key = resolve_mon(m.group(1))
            side = "their" if "opposing" in m.group(1).lower() else None
            sid = self._attr_sid(key, default_side=side)
            if sid:
                matched = match_item(m.group(2))
                it_name = matched if matched else m.group(2).title()
                self.mons[sid]["item"] = it_name
                if "leftover" in it_name.lower():
                    self.mons[sid]["inferred_archetype"] = "Physical Wall" if self.mons[sid].get("base_spe", 80) < 75 else "Bulky Pivot"
                if sid.startswith("their:"):
                    th_k = sid.split(":", 1)[1]
                    for te in self.their_team:
                        if isinstance(te, dict) and te.get("key") == th_k:
                            te["item"] = it_name
                            if self.mons[sid].get("inferred_archetype"):
                                te["archetype"] = self.mons[sid]["inferred_archetype"]
            return

        m = _RE_KNOCK_OFF.match(low)
        if m:
            key = resolve_mon(m.group(2))
            sid = self._attr_sid(key, default_side="their")
            if sid:
                it_name = m.group(3).title() + " (knocked off)"
                self.mons[sid]["item"] = it_name
                if sid.startswith("their:"):
                    th_k = sid.split(":", 1)[1]
                    for te in self.their_team:
                        if isinstance(te, dict) and te.get("key") == th_k:
                            te["item"] = it_name
            return

        m = _RE_LIFE_ORB.match(low)
        if m:
            key = resolve_mon(m.group(1))
            side = "their" if "opposing" in m.group(1).lower() else None
            sid = self._attr_sid(key, default_side=side)
            if sid and ("orb" in m.group(2) or "life orb" in m.group(2)):
                self.mons[sid]["item"] = "Life Orb"
                self.mons[sid]["inferred_archetype"] = "Physical Sweeper" if self.mons[sid].get("base_spe", 80) >= 70 else "Special Sweeper"
                if sid.startswith("their:"):
                    th_k = sid.split(":", 1)[1]
                    for te in self.their_team:
                        if isinstance(te, dict) and te.get("key") == th_k:
                            te["item"] = "Life Orb"
                            te["archetype"] = self.mons[sid]["inferred_archetype"]
            return

        m = _RE_SPEED_STAGE.match(low)
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

        m = _RE_ABILITY.match(low)
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

        m = _RE_POISON.match(low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = "TOX" if m.group(2) else "PSN"
            return

        m = _RE_STATUS.match(low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = m.group(2)[:3].upper()
            return

        m = _RE_SLEEP.match(low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = "SLP"
            return

        m = _RE_WAKE.match(low)
        if m:
            sid = self._attr_sid(resolve_mon(m.group(1)))
            if sid:
                self.mons[sid]["status"] = None
            return

        m = _RE_SEEDED.match(low)
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
            self.th_choice_locked_move = None
            self.add_their_team_mon(key)
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
            self.th_choice_locked_move = None

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
        if d.get("locked") and d.get("moves"):
            m["moves"] = list(d["moves"])
        else:
            for mv in d.get("moves", []):
                if mv not in m["moves"]:
                    m["moves"].append(mv)
        if d.get("item"):
            m["item"] = d["item"]
        if d.get("level") and (not m.get("level") or m.get("level") == 80):
            m["level"] = d["level"]
        if d.get("ability"):
            m["ability"] = d["ability"]
        if d.get("nature"):
            m["nature"] = d["nature"]
        if d.get("evs"):
            m["evs"] = dict(d["evs"])
        if d.get("ivs"):
            m["ivs"] = dict(d["ivs"])

    def import_showdown_team(self, text):
        """Imports up to 6 Pokémon from Pokémon Showdown / Poképaste format.
        Locks their moves and immediately applies them to live team entries.
        """
        parsed = parse_showdown_team(text)
        if not parsed:
            return 0
        self.my_team_data.clear()
        for p in parsed[:6]:
            k = p["key"]
            self.my_team_data[k] = {
                "moves": list(p["moves"]),
                "item": p["item"],
                "level": p.get("level", 100),
                "locked": True,
                "ability": p.get("ability"),
                "nature": p.get("nature"),
                "evs": dict(p.get("evs") or {}),
                "ivs": dict(p.get("ivs") or {}),
            }
            sid = _sid("my", k)
            if sid in self.mons:
                m = self.mons[sid]
                if p["moves"]:
                    m["moves"] = list(p["moves"])
                if p["item"]:
                    m["item"] = p["item"]
                if p.get("level"):
                    m["level"] = p["level"]
                if p.get("ability"):
                    m["ability"] = p["ability"]
                if p.get("nature"):
                    m["nature"] = p["nature"]
                if p.get("evs"):
                    m["evs"] = dict(p["evs"])
                if p.get("ivs"):
                    m["ivs"] = dict(p["ivs"])
            else:
                m = new_mon(k, "my")
                m["moves"] = list(p["moves"])
                m["item"] = p["item"]
                m["level"] = p.get("level", 100)
                if p.get("ability"):
                    m["ability"] = p["ability"]
                if p.get("nature"):
                    m["nature"] = p["nature"]
                if p.get("evs"):
                    m["evs"] = dict(p["evs"])
                if p.get("ivs"):
                    m["ivs"] = dict(p["ivs"])
                self.mons[sid] = m

        # Persist raw import text to saved_team.txt
        try:
            if text and text.strip():
                self.SAVED_TEAM_FILE.write_text(text.strip(), encoding="utf8")
        except Exception:
            pass

        self.save()
        return len(parsed[:6])

    def add_their_team_mon(self, name_or_key, item=None):
        """Adds or updates an opponent team member (up to 6 slots)."""
        if not name_or_key:
            return None
        key = resolve_mon(name_or_key) if name_or_key not in DEX else name_or_key
        if not key or key not in DEX:
            return None
        sid = _sid("their", key)
        m = self.mon(sid, "their")
        resolved_item = match_item(item) or item if item else (m.get("item") if m else None)
        if resolved_item and m:
            m["item"] = resolved_item

        found = False
        for entry in self.their_team:
            if entry.get("key") == key:
                if resolved_item:
                    entry["item"] = resolved_item
                found = True
                break
        if not found and len(self.their_team) < 6:
            self.their_team.append({"key": key, "item": resolved_item})
        self.save()
        return key

    def remove_their_team_mon(self, key):
        """Removes a mon from opponent's 6 slots."""
        self.their_team = [e for e in self.their_team if e.get("key") != key]
        self.save()

    def clear_their_team(self):
        """Clears all opponent team slots."""
        self.their_team = []
        self.save()

    def set_mon_item(self, side, name_or_key, item_name):
        """Sets or updates the held item for a mon on either side ('my' or 'their')."""
        if not name_or_key:
            return False
        key = resolve_mon(name_or_key) if name_or_key not in DEX else name_or_key
        if not key or key not in DEX:
            return False
        item = match_item(item_name) if item_name else None

        sid = _sid(side, key)
        m = self.mon(sid, side)
        if m:
            m["item"] = item

        if side == "my":
            d = self.my_team_data.setdefault(key, {"moves": [], "item": None, "level": None})
            d["item"] = item
        elif side == "their":
            found = False
            for entry in self.their_team:
                if entry.get("key") == key:
                    entry["item"] = item
                    found = True
                    break
            if not found and len(self.their_team) < 6:
                self.their_team.append({"key": key, "item": item})

        self.save()
        return True

    def set_my_team_mon(self, name_or_key, item=None, moves=None, level=None):
        """Adds or updates a player's team member (up to 6)."""
        if not name_or_key:
            return None
        key = resolve_mon(name_or_key) if name_or_key not in DEX else name_or_key
        if not key or key not in DEX:
            return None
        resolved_item = match_item(item) if item else None
        d = self.my_team_data.setdefault(key, {"moves": [], "item": None, "level": None})
        if resolved_item:
            d["item"] = resolved_item
        if level and 1 <= level <= 100:
            d["level"] = level
        if moves:
            for mv in moves:
                resolved_mv = resolve_move(mv) if mv not in MOVES else mv
                if resolved_mv and resolved_mv not in d["moves"] and len(d["moves"]) < 6:
                    d["moves"].append(resolved_mv)
        self._apply_team_data(key)
        self.save()
        return key

    def remove_my_team_mon(self, key):
        """Removes a Pokemon from player's scanned team."""
        if key in self.my_team_data:
            del self.my_team_data[key]
        sid = _sid("my", key)
        if sid in self.mons and sid != self.my_active_key:
            del self.mons[sid]
        self.save()

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
            self._apply_team_data(key)
        else:
            self.their_active_key = sid
            self._last_their_active = sid
            self.add_their_team_mon(key)
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
            my_key = self.mons.get(self.my_active_key, {}).get("key") if self.my_active_key else None
            for line in text.splitlines():
                l_str = line.strip().lower()
                if not l_str or "choose" in l_str or l_str == "attack":
                    continue
                mk = resolve_move(line.strip())
                if not mk or mk in self.menu_moves:
                    continue
                if my_key:
                    valid = moves_in_learnset(my_key, [mk])
                    if not valid:
                        continue
                self.menu_moves.append(mk)
            if self.my_active_key and self.menu_moves:
                m = self.mons.get(self.my_active_key)
                if m:
                    for mk in self.menu_moves:
                        if mk not in m["moves"] and len(m["moves"]) < 4:
                            m["moves"].append(mk)
        elif "choose pokemon" in low or "choose pokémon" in low:
            self.menu_mode = "switch"
            self.menu_moves = []
        else:
            self.menu_mode = None
            self.menu_moves = []

    # ---------- summary ----------

    def state_line(self, advice=None):
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
            my_key = my.get("key")
            t_data = self.my_team_data.get(my_key, {})
            nat = my.get("nature") or t_data.get("nature")
            evs = my.get("evs") or t_data.get("evs") or {}
            ivs = my.get("ivs") or t_data.get("ivs") or {}
            stat_note = ""
            bs_s = DEX.get(my_key, {}).get("baseStats", {})
            if bs_s and (evs or ivs or nat):
                from .calc import calc_stat
                lvl = my.get("level", 100) or 100
                hp_val = calc_stat(bs_s.get("hp", 80), "hp", lvl, iv=ivs.get("hp", 31), ev=evs.get("hp", 85))
                spe_val = calc_stat(bs_s.get("spe", 80), "spe", lvl, iv=ivs.get("spe", 31), ev=evs.get("spe", 85), nature=nat)
                atk_val = calc_stat(bs_s.get("atk", 80), "atk", lvl, iv=ivs.get("atk", 31), ev=evs.get("atk", 85), nature=nat)
                spa_val = calc_stat(bs_s.get("spa", 80), "spa", lvl, iv=ivs.get("spa", 31), ev=evs.get("spa", 85), nature=nat)
                nat_part = f" [{nat}]" if nat else ""
                stat_note = f" | Stats{nat_part}: HP {hp_val} | Spe {spe_val} | Atk {atk_val} | SpA {spa_val}"
            lines.append(f"MY ACTIVE: {tag(self.my_active_key)}{hp_s} ({'/'.join(my['types'])}){stat_note}")
        else:
            lines.append("MY ACTIVE: -")
        if th:
            th_arch = th.get("inferred_archetype")
            if not th_arch and th.get("key"):
                from .calc import infer_opponent_archetype
                th_arch, _, _ = infer_opponent_archetype(th)
                th["inferred_archetype"] = th_arch
            th_floor = th.get("speed_floor")
            th_ceil = th.get("speed_ceiling")
            th_spd_bound = ""
            if th_floor and th_ceil and th_floor == th_ceil:
                th_spd_bound = f"Spe: ={th_floor}"
            elif th_floor:
                th_spd_bound = f"Spe: ≥{th_floor}"
            elif th_ceil:
                th_spd_bound = f"Spe: ≤{th_ceil}"
            build_parts = [p for p in [th_arch, th_spd_bound] if p]
            th_build_str = f" | Build: {', '.join(build_parts)}" if build_parts else ""
            lines.append(f"THEIR ACTIVE: {tag(self.their_active_key)}{thp_s} ({'/'.join(th['types'])}){th_build_str}")
        else:
            lines.append("THEIR ACTIVE: -")
        bench = [
            tag(k)
            for k, m in self.mons.items()
            if m.get("side") == "my" and k != self.my_active_key and not m.get("fainted")
        ]
        if bench:
            lines.append("MY BENCH: " + " | ".join(bench))
        if my:
            my_key = my.get("key")
            t_data = self.my_team_data.get(my_key, {})
            is_locked = t_data.get("locked", False)
            if self.menu_moves:
                mv_names = [MOVES[mk]["name"] for mk in self.menu_moves if mk in MOVES]
                lines.append("AVAILABLE IN-GAME ATTACKS (STRICT - MUST CHOOSE ONE OF THESE): " + ", ".join(mv_names))
            else:
                known = list(my.get("moves") or [])
                if not known and my_key and my_key in self.my_team_data:
                    known = list(self.my_team_data[my_key].get("moves") or [])
                if known:
                    mv_names = [MOVES[mk]["name"] for mk in known if mk in MOVES]
                    if is_locked or self.menu_mode == "attack":
                        lines.append("LOCKED KNOWN MOVES (STRICT - ONLY RECOMMEND FROM THESE): " + ", ".join(mv_names))
                    else:
                        lines.append("MY KNOWN MOVES: " + ", ".join(mv_names))
                else:
                    lines.append("MY MOVES: Unknown (attack menu closed / unscanned)")
        if th:
            th_key = th.get("key")
            if th.get("moves"):
                lines.append("THEIR REVEALED MOVES: " + ", ".join(MOVES[mk]["name"] for mk in th["moves"]))
            my_t = my.get("types", []) if my else []
            scout_threats = get_opponent_unrevealed_scout(th_key, th.get("moves", []), my_t)
            if scout_threats:
                threat_strs = []
                for st in scout_threats:
                    warning = f" [⚠️ {st['eff_vs_my']}x EFFECTIVE]" if st["is_threat"] else ""
                    threat_strs.append(f"{st['name']} ({st['pct']}%){warning}")
                lines.append("OPPONENT UNREVEALED THREATS (SMOGON ODDS): " + " | ".join(threat_strs))

        # --- Full 6v6 Team Rosters & Held Items ---
        my_keys = list(self.my_team_data.keys())
        for sid, m in self.mons.items():
            if m.get("side") == "my":
                k = m.get("key")
                if k and k not in my_keys:
                    my_keys.append(k)

        if my_keys:
            lines.append(f"MY FULL TEAM ({len(my_keys[:6])}/6):")
            for idx, k in enumerate(my_keys[:6], 1):
                m_info = DEX.get(k, {})
                t_str = "/".join(m_info.get("types", []))
                sid = _sid("my", k)
                live_m = self.mons.get(sid, {})
                t_data = self.my_team_data.get(k, {})

                status_flags = []
                if sid == self.my_active_key:
                    status_flags.append("ACTIVE")
                elif live_m.get("fainted") or sid in self.my_fainted:
                    status_flags.append("FAINTED")
                status_str = f" [{'/'.join(status_flags)}]" if status_flags else ""

                item = live_m.get("item") or t_data.get("item")
                item_str = f" @ {item}" if item else ""

                moves = t_data.get("moves") or live_m.get("moves") or []
                mv_names = [MOVES[mv]["name"] for mv in moves if mv in MOVES]
                is_lck = t_data.get("locked", False)
                lck_tag = " [LOCKED]" if is_lck else ""
                mv_str = f" | Moves{lck_tag}: {', '.join(mv_names)}" if mv_names else ""

                nat = t_data.get("nature") or live_m.get("nature")
                nat_str = f" | {nat} Nature" if nat else ""
                spe_stat = ""
                bs_s = DEX.get(k, {}).get("baseStats", {})
                if bs_s:
                    from .calc import calc_stat
                    iv_spe = t_data.get("ivs", {}).get("spe", 31) if isinstance(t_data.get("ivs"), dict) else 31
                    ev_spe = t_data.get("evs", {}).get("spe", 85) if isinstance(t_data.get("evs"), dict) else 85
                    lvl_m = t_data.get("level", 100) or 100
                    sp_v = calc_stat(bs_s.get("spe", 80), "spe", lvl_m, iv=iv_spe, ev=ev_spe, nature=nat)
                    spe_stat = f" (Spe: {sp_v})"

                lines.append(f"  {idx}. {tag(k)} ({t_str}){item_str}{status_str}{nat_str}{spe_stat}{mv_str}")

        th_entries = list(self.their_team)
        th_k = self._active_dex_key("their")
        if th_k and not any(e.get("key") == th_k for e in th_entries):
            th_item = self.mons.get(self.their_active_key, {}).get("item")
            th_entries.insert(0, {"key": th_k, "item": th_item})

        revealed_count = min(6, len(th_entries))
        lines.append(f"OPPONENT TEAM (6 SLOTS - {revealed_count}/6 REVEALED):")
        for idx in range(1, 7):
            if idx <= len(th_entries):
                entry = th_entries[idx - 1]
                ek = entry.get("key")
                e_info = DEX.get(ek, {})
                t_str = "/".join(e_info.get("types", []))
                sid = _sid("their", ek)
                live_m = self.mons.get(sid, {})

                status_flags = []
                if sid == self.their_active_key:
                    status_flags.append("ACTIVE")
                elif live_m.get("fainted") or sid in self.their_fainted:
                    status_flags.append("FAINTED")
                status_str = f" [{'/'.join(status_flags)}]" if status_flags else ""

                item = entry.get("item") or live_m.get("item")
                item_str = f" @ {item}" if item else ""

                moves = live_m.get("moves") or []
                mv_names = [MOVES[mv]["name"] for mv in moves if mv in MOVES]
                mv_str = f" | Revealed: {', '.join(mv_names)}" if mv_names else ""

                my_t = my.get("types", []) if my else []
                scout_threats = get_opponent_unrevealed_scout(ek, live_m.get("moves", []), my_t)
                scout_str = ""
                if scout_threats:
                    scout_items = [f"{st['name']}:{st['pct']}%" for st in scout_threats[:2]]
                    scout_str = f" | Scout: [{', '.join(scout_items)}]"

                arch = live_m.get("inferred_archetype")
                if not arch and ek:
                    from .calc import infer_opponent_archetype
                    arch, _, _ = infer_opponent_archetype(live_m or {"key": ek})
                fl_s = live_m.get("speed_floor")
                cl_s = live_m.get("speed_ceiling")
                sp_b = ""
                if fl_s and cl_s and fl_s == cl_s:
                    sp_b = f"Spe: ={fl_s}"
                elif fl_s:
                    sp_b = f"Spe: ≥{fl_s}"
                elif cl_s:
                    sp_b = f"Spe: ≤{cl_s}"
                b_parts = [p for p in [arch, sp_b] if p]
                arch_str = f" | Build: {', '.join(b_parts)}" if b_parts else ""

                lines.append(f"  Slot {idx}: {tag(ek)} ({t_str}){item_str}{status_str}{arch_str}{mv_str}{scout_str}")
            else:
                lines.append(f"  Slot {idx}: [Unknown / Unrevealed]")

        # --- Tactical Intelligence, Stockfish Evaluation & Choice-Lock Intel ---
        if my and th:
            try:
                from .calc import (
                    compute_switch_pressure,
                    detect_item_traps,
                    identify_win_con,
                    compute_match_eval,
                    detect_choice_lock_and_bluff,
                )
                th_key = th.get("key")

                # Build team lists for evaluation
                my_team_list = []
                for k in my_keys:
                    sid = _sid("my", k)
                    live_m = self.mons.get(sid, {})
                    is_dead = bool(live_m.get("fainted") or sid in self.my_fainted)
                    t_data = self.my_team_data.get(k, {})
                    my_team_list.append({
                        "key": k,
                        "name": DEX.get(k, {}).get("name", k.capitalize()),
                        "types": DEX.get(k, {}).get("types", []),
                        "item": live_m.get("item") or t_data.get("item"),
                        "moves": t_data.get("moves") or live_m.get("moves") or [],
                        "level": t_data.get("level", 100) or 100,
                        "nature": t_data.get("nature") or live_m.get("nature"),
                        "evs": t_data.get("evs") or live_m.get("evs") or {},
                        "ivs": t_data.get("ivs") or live_m.get("ivs") or {},
                        "fainted": is_dead,
                    })

                th_team_list = []
                for te in th_entries:
                    tek = te.get("key")
                    sid = _sid("their", tek)
                    live_m = self.mons.get(sid, {})
                    is_dead = bool(live_m.get("fainted") or sid in self.their_fainted)
                    th_team_list.append({
                        "key": tek,
                        "name": DEX.get(tek, {}).get("name", tek.capitalize()),
                        "types": DEX.get(tek, {}).get("types", []),
                        "item": te.get("item") or live_m.get("item"),
                        "moves": live_m.get("moves") or [],
                        "fainted": is_dead,
                    })

                # Stockfish Match Evaluation
                eval_res = compute_match_eval(
                    my_team=my_team_list,
                    their_team=th_team_list,
                    my_mon=my,
                    their_mon=th,
                    my_hp=self.my_hp,
                    their_hp=self.their_hp,
                    my_fainted=self.my_fainted,
                    their_fainted=self.their_fainted,
                    moves_db=MOVES,
                )
                if eval_res:
                    lines.append(f"MATCH EVALUATION: {eval_res['eval_str']} ADVANTAGE ({eval_res['win_pct']}% Win Probability) [{eval_res['lead_text']}]")

                # Choice-Lock & Bluff Intel
                choice_intel = detect_choice_lock_and_bluff(
                    my_mon=my,
                    their_mon=th,
                    my_team=my_team_list,
                    their_locked_move=getattr(self, "th_choice_locked_move", None),
                    moves_db=MOVES,
                )
                if choice_intel:
                    if choice_intel.get("th_locked_move"):
                        lines.append(f"OPPONENT CHOICE-LOCK: LOCKED into {choice_intel['th_locked_name']}! {choice_intel.get('exploit_advice', '')}")
                    if choice_intel.get("bluff_ready") and choice_intel.get("bluff_advice"):
                        lines.append(f"PLAYER BLUFF POTENTIAL: {choice_intel['bluff_advice']}")

                sw = compute_switch_pressure(my, th, their_bench=th_entries, my_moves=my.get("moves"), their_hp=self.their_hp)
                if sw:
                    lines.append(f"TACTICAL SWITCH PRESSURE: {sw['level']} ({sw['odds']}% Odds) - {sw['reason']}")
                    if sw.get("top_targets"):
                        t_strs = [f"{t['name']} ({t['pct']}%) [{t['reason']}]" for t in sw["top_targets"]]
                        lines.append("LIKELY OPPONENT SWITCH-INS: " + " | ".join(t_strs))

                traps = detect_item_traps(th_key, self.their_hp)
                if traps:
                    lines.append("OPPONENT ITEM TRAP ALERTS: " + " | ".join(t["alert"] for t in traps))

                wc = identify_win_con([m for m in my_team_list if not m["fainted"]], th_entries)
                if wc:
                    lines.append(f"PLAYER MATCH WIN-CON ANCHOR: {wc['name']} - {wc['reason']}. Preserve this Pokémon!")
            except Exception:
                pass


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
