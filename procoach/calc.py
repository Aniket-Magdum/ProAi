"""Type chart, damage/speed estimation, KO probability.

Assumes neutral nature, 31 IVs, ~85 EVs (random-battle average). Unknown
EVs/natures/abilities add real spread, so all outputs are treated as
estimates with ~15% uncertainty.
"""

ITEM_ATK_MULT = {
    "lifeorb": 1.3,
    "choiceband": 1.5,
    "choicespecs": 1.5,
    "expertbelt": 1.2,
}

TYPE_CHART = {
    "normal": {"rock": 0.5, "ghost": 0},
    "fire": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 2, "bug": 2, "rock": 0.5, "dragon": 0.5, "steel": 2},
    "water": {"fire": 2, "water": 0.5, "grass": 0.5, "ground": 2, "rock": 2, "dragon": 0.5},
    "electric": {"water": 2, "electric": 0.5, "grass": 0.5, "ground": 0, "flying": 2, "dragon": 0.5},
    "grass": {"fire": 0.5, "water": 2, "grass": 0.5, "poison": 0.5, "ground": 2, "flying": 0.5, "bug": 0.5, "rock": 2, "dragon": 0.5, "steel": 0.5},
    "ice": {"fire": 0.5, "water": 0.5, "grass": 2, "ice": 0.5, "ground": 2, "flying": 2, "dragon": 2, "steel": 0.5},
    "fighting": {"normal": 2, "ice": 2, "poison": 0.5, "flying": 0.5, "psychic": 0.5, "bug": 0.5, "rock": 2, "ghost": 0, "dark": 2, "steel": 2, "fairy": 0.5},
    "poison": {"grass": 2, "poison": 0.5, "ground": 0.5, "rock": 0.5, "ghost": 0.5, "steel": 0, "fairy": 2},
    "ground": {"fire": 2, "electric": 2, "grass": 0.5, "poison": 2, "flying": 0, "bug": 0.5, "rock": 2, "steel": 2},
    "flying": {"electric": 0.5, "grass": 2, "fighting": 2, "bug": 2, "rock": 0.5, "steel": 0.5},
    "psychic": {"fighting": 2, "poison": 2, "psychic": 0.5, "dark": 0, "steel": 0.5},
    "bug": {"fire": 0.5, "grass": 2, "fighting": 0.5, "poison": 0.5, "flying": 0.5, "psychic": 2, "ghost": 0.5, "dark": 2, "steel": 0.5, "fairy": 0.5},
    "rock": {"fire": 2, "ice": 2, "fighting": 0.5, "ground": 0.5, "flying": 2, "bug": 2, "steel": 0.5},
    "ghost": {"normal": 0, "psychic": 2, "ghost": 2, "dark": 0.5},
    "dragon": {"dragon": 2, "steel": 0.5, "fairy": 0},
    "dark": {"fighting": 0.5, "psychic": 2, "ghost": 2, "dark": 0.5, "fairy": 0.5},
    "steel": {"fire": 0.5, "water": 0.5, "electric": 0.5, "ice": 2, "rock": 2, "steel": 0.5, "fairy": 2},
    "fairy": {"fire": 0.5, "fighting": 2, "poison": 0.5, "dragon": 2, "dark": 2, "steel": 0.5},
}


def effectiveness(move_type, def_types):
    mult = 1.0
    for t in def_types:
        mult *= TYPE_CHART.get(move_type, {}).get(t.lower(), 1.0)
    return mult


NATURES = {
    "hardy": {}, "docile": {}, "bashful": {}, "quirky": {}, "serious": {},
    "lonely": {"atk": 1.1, "def": 0.9},
    "brave": {"atk": 1.1, "spe": 0.9},
    "adamant": {"atk": 1.1, "spa": 0.9},
    "naughty": {"atk": 1.1, "spd": 0.9},
    "bold": {"def": 1.1, "atk": 0.9},
    "relaxed": {"def": 1.1, "spe": 0.9},
    "impish": {"def": 1.1, "spa": 0.9},
    "lax": {"def": 1.1, "spd": 0.9},
    "timid": {"spe": 1.1, "atk": 0.9},
    "hasty": {"spe": 1.1, "def": 0.9},
    "jolly": {"spe": 1.1, "spa": 0.9},
    "naive": {"spe": 1.1, "spd": 0.9},
    "modest": {"spa": 1.1, "atk": 0.9},
    "mild": {"spa": 1.1, "def": 0.9},
    "quiet": {"spa": 1.1, "spe": 0.9},
    "rash": {"spa": 1.1, "spd": 0.9},
    "calm": {"spd": 1.1, "atk": 0.9},
    "gentle": {"spd": 1.1, "def": 0.9},
    "sassy": {"spd": 1.1, "spe": 0.9},
    "careful": {"spd": 1.1, "spa": 0.9},
}


def calc_stat(base, stat_name, level=100, iv=31, ev=85, nature=None):
    """Computes exact Pokémon stat from base stat, IV, EV, and Nature."""
    if stat_name == "hp":
        return int((2 * base + iv + (ev // 4)) * level / 100) + level + 10
    raw = int((2 * base + iv + (ev // 4)) * level / 100) + 5
    nat_mod = 1.0
    if nature:
        nat_mod = NATURES.get(str(nature).lower(), {}).get(stat_name, 1.0)
    return int(raw * nat_mod)


MOVE_PRIORITIES = {
    # +5
    "helpinghand": 5,
    # +4
    "protect": 4, "detect": 4, "kingsshield": 4, "spikyshield": 4, "banefulbunker": 4,
    "magiccoat": 4, "snatch": 4, "endure": 4,
    # +3
    "fakeout": 3, "quickguard": 3, "wideguard": 3,
    # +2
    "extremespeed": 2, "feint": 2, "firstimpression": 2,
    # +1
    "aquajet": 1, "bulletpunch": 1, "iceshard": 1, "machpunch": 1, "quickattack": 1,
    "shadowsneak": 1, "suckerpunch": 1, "vacuumwave": 1, "accelerock": 1, "watershuriken": 1,
    "babyteleyes": 1, "bide": 1,
    # -1
    "vitalthrow": -1,
    # -3
    "focuspunch": -3,
    # -4
    "avalanche": -4, "revenge": -4,
    # -5
    "counter": -5, "mirrorcoat": -5,
    # -6
    "roar": -6, "whirlwind": -6, "dragontail": -6, "circlethrow": -6, "teleport": -6,
    # -7
    "trickroom": -7,
}


def get_move_priority(move_key):
    if not move_key:
        return 0
    clean = str(move_key).lower().replace(" ", "").replace("-", "")
    return MOVE_PRIORITIES.get(clean, 0)


def infer_opponent_archetype(mon):
    """Infers realistic competitive Smogon 252/252 archetype, EVs, and Nature for opponent.
    Returns: (archetype_name, ev_dict, nature_str)
    """
    if not mon or not isinstance(mon, dict):
        return "Standard", {"hp": 85, "atk": 85, "def": 85, "spa": 85, "spd": 85, "spe": 85}, None

    key = mon.get("key")
    from .state import DEX
    bs = DEX.get(key, {}).get("baseStats") if key else {}
    if not bs:
        bs = {
            "hp": 80, "atk": 80, "def": 80,
            "spa": 80, "spd": 80, "spe": mon.get("base_spe", 80)
        }

    item = (mon.get("item") or "").lower().replace(" ", "")
    moves = [str(m).lower().replace(" ", "") for m in mon.get("moves", [])]

    hp_b = bs.get("hp", 80)
    atk_b = bs.get("atk", 80)
    def_b = bs.get("def", 80)
    spa_b = bs.get("spa", 80)
    spd_b = bs.get("spd", 80)
    spe_b = bs.get("spe", 80)

    is_offensive_item = any(x in item for x in ("lifeorb", "choice", "band", "specs", "scarf", "dice", "plate", "gem"))
    is_defensive_item = any(x in item for x in ("leftovers", "rockyhelmet", "blacksludge", "eviolite", "boots", "heavy-duty"))

    has_defensive_moves = any(x in moves for x in ("toxic", "stealthrock", "spikes", "roost", "recover", "softboiled", "defog", "haze"))

    # 1. Clear Wall / Tank
    if is_defensive_item or has_defensive_moves or (spe_b < 75 and (def_b >= 100 or spd_b >= 100 or hp_b >= 100)):
        if def_b >= spd_b:
            nat = "Impish" if atk_b >= spa_b else "Bold"
            return "Physical Wall", {"hp": 252, "atk": 0, "def": 252, "spa": 0, "spd": 4, "spe": 0}, nat
        else:
            nat = "Careful" if atk_b >= spa_b else "Calm"
            return "Special Wall", {"hp": 252, "atk": 0, "def": 4, "spa": 0, "spd": 252, "spe": 0}, nat

    # 2. Fast Sweepers (Atk or SpA with Spe >= 70)
    if is_offensive_item or spe_b >= 70 or atk_b >= 95 or spa_b >= 95:
        if atk_b >= spa_b:
            nat = "Jolly" if spe_b >= 70 else "Adamant"
            return "Physical Sweeper", {"hp": 4, "atk": 252, "def": 0, "spa": 0, "spd": 0, "spe": 252}, nat
        else:
            nat = "Timid" if spe_b >= 70 else "Modest"
            return "Special Sweeper", {"hp": 4, "atk": 0, "def": 0, "spa": 252, "spd": 0, "spe": 252}, nat

    # 3. Bulky Pivot
    nat = "Adamant" if atk_b >= spa_b else "Modest"
    return "Bulky Pivot", {"hp": 252, "atk": 128 if atk_b >= spa_b else 0, "def": 64, "spa": 128 if spa_b > atk_b else 0, "spd": 64, "spe": 0}, nat


def stat_est(base, level, is_hp=False, mon=None, stat_name=None):
    if mon and isinstance(mon, dict):
        s_name = stat_name or ("hp" if is_hp else "atk")
        ivs = mon.get("ivs") if isinstance(mon.get("ivs"), dict) else {}
        evs = mon.get("evs") if isinstance(mon.get("evs"), dict) else {}
        nat = mon.get("nature")

        # If opponent with no explicit EVs specified, infer competitive archetype
        if not evs and mon.get("side") == "their":
            arch, inf_evs, inf_nat = infer_opponent_archetype(mon)
            if "inferred_archetype" not in mon:
                mon["inferred_archetype"] = arch
            ev = inf_evs.get(s_name, 85)
            nat = nat or inf_nat
        else:
            ev = evs.get(s_name, 85)

        iv = ivs.get(s_name, 31)
        return calc_stat(base, s_name, level, iv=iv, ev=ev, nature=nat)
    if is_hp:
        return int((2 * base + 31 + 21) * level / 100) + level + 10
    return int((2 * base + 31 + 21) * level / 100) + 5


MEGA_STONE_MAP = {
    "abomasite": ("abomasnowmega", ["Grass", "Ice"]),
    "absolite": ("absolmega", ["Dark"]),
    "aerodactylite": ("aerodactylmega", ["Rock", "Flying"]),
    "aggronite": ("aggronmega", ["Steel"]),
    "alakazite": ("alakazammega", ["Psychic"]),
    "altarianite": ("altariamega", ["Dragon", "Fairy"]),
    "ampharosite": ("ampharosmega", ["Electric", "Dragon"]),
    "audinite": ("audinomega", ["Normal", "Fairy"]),
    "banettite": ("banettemega", ["Ghost"]),
    "beedrillite": ("beedrillmega", ["Bug", "Poison"]),
    "blastoisinite": ("blastoisemega", ["Water"]),
    "blazikenite": ("blazikenmega", ["Fire", "Fighting"]),
    "cameruptite": ("cameruptmega", ["Fire", "Ground"]),
    "charizarditex": ("charizardmegax", ["Fire", "Dragon"]),
    "charizarditey": ("charizardmegay", ["Fire", "Flying"]),
    "diancite": ("dianciemega", ["Rock", "Fairy"]),
    "galladite": ("gallademega", ["Psychic", "Fighting"]),
    "garchompite": ("garchompmega", ["Dragon", "Ground"]),
    "gardevoirite": ("gardevoirmega", ["Psychic", "Fairy"]),
    "gengarite": ("gengarmega", ["Ghost", "Poison"]),
    "glalitite": ("glaliemega", ["Ice"]),
    "gyaradosite": ("gyaradosmega", ["Water", "Dark"]),
    "heracronite": ("heracrossmega", ["Bug", "Fighting"]),
    "houndoominite": ("houndoommega", ["Dark", "Fire"]),
    "kangaskhanite": ("kangaskhanmega", ["Normal"]),
    "latiasite": ("latiasmega", ["Dragon", "Psychic"]),
    "latiosite": ("latiosmega", ["Dragon", "Psychic"]),
    "lopunnite": ("lopunnymega", ["Normal", "Fighting"]),
    "lucarionite": ("lucariomega", ["Fighting", "Steel"]),
    "manectite": ("manectricmega", ["Electric"]),
    "mawilite": ("mawilemega", ["Steel", "Fairy"]),
    "medichamite": ("medichammega", ["Fighting", "Psychic"]),
    "metagrossite": ("metagrossmega", ["Steel", "Psychic"]),
    "mewtwonitex": ("mewtwomegax", ["Psychic", "Fighting"]),
    "mewtwonitey": ("mewtwomegay", ["Psychic"]),
    "pidgeotite": ("pidgeotmega", ["Normal", "Flying"]),
    "pinsirite": ("pinsirmega", ["Bug", "Flying"]),
    "sablenite": ("sableyemega", ["Dark", "Ghost"]),
    "salamencite": ("salamencemega", ["Dragon", "Flying"]),
    "sceptilite": ("sceptilemega", ["Grass", "Dragon"]),
    "scizorite": ("scizormega", ["Bug", "Steel"]),
    "sharpedonite": ("sharpedomega", ["Water", "Dark"]),
    "slowbronite": ("slowbromega", ["Water", "Psychic"]),
    "steelixite": ("steelixmega", ["Steel", "Ground"]),
    "swampertite": ("swampertmega", ["Water", "Ground"]),
    "tyranitarite": ("tyranitarmega", ["Rock", "Dark"]),
    "venusaurite": ("venusaurmega", ["Grass", "Poison"]),
}


def _base_stats(mon):
    from .state import DEX

    item = (mon.get("item") or "").lower().replace(" ", "")
    key = mon.get("key", "")
    if item in MEGA_STONE_MAP and not ("mega" in key):
        mega_key = MEGA_STONE_MAP[item][0]
        if mega_key in DEX:
            return DEX[mega_key].get("baseStats", {})

    entry = DEX.get(key, {})
    return entry.get("baseStats", {})


def est_damage_pct(att, dfn, mv, moves_db):
    """Max-roll damage as % of defender max HP; returns (min_pct, max_pct)."""
    m = moves_db[mv]
    if m["category"] == "Status" or m["basePower"] <= 0:
        return None
    a_bs = _base_stats(att)
    d_bs = _base_stats(dfn)
    if not a_bs or not d_bs:
        return None

    a_types = list(att.get("types") or [])
    d_types = list(dfn.get("types") or [])
    a_item = (att.get("item") or "").lower().replace(" ", "").replace("(knockedoff)", "")
    d_item = (dfn.get("item") or "").lower().replace(" ", "").replace("(knockedoff)", "")

    if a_item in MEGA_STONE_MAP and not ("mega" in att.get("key", "")):
        a_types = MEGA_STONE_MAP[a_item][1]
    if d_item in MEGA_STONE_MAP and not ("mega" in dfn.get("key", "")):
        d_types = MEGA_STONE_MAP[d_item][1]

    physical = m["category"] == "Physical"
    atk_stat = "atk" if physical else "spa"
    def_stat = "def" if physical else "spd"
    A = stat_est(a_bs.get(atk_stat, 50), att["level"], mon=att, stat_name=atk_stat)
    D = stat_est(d_bs.get(def_stat, 50), dfn["level"], mon=dfn, stat_name=def_stat)
    HP = stat_est(d_bs.get("hp", 60), dfn["level"], is_hp=True, mon=dfn, stat_name="hp")
    stab = 1.5 if m["type"].lower() in [t.lower() for t in a_types] else 1.0
    eff = effectiveness(m["type"].lower(), [t.lower() for t in d_types])
    if eff == 0:
        return None
    mult = ITEM_ATK_MULT.get(a_item, 1.0) if a_item else 1.0
    if a_item and a_item.endswith("gem"):
        gem_type = a_item[:-3]
        if m["type"].lower() == gem_type:
            mult = 1.3
    base = ((2 * att["level"] / 5 + 2) * m["basePower"] * A / D) / 50 + 2
    pct = base * eff * stab * mult / HP * 100
    return (pct * 0.85, pct)


def ko_chance(dmg, their_hp):
    """Rough KO probability from a damage range vs remaining HP fraction."""
    if dmg is None:
        return None
    lo, hi = dmg
    remaining = max(their_hp, 0.01) * 100.0
    if lo >= remaining:
        return 1.0
    if hi < remaining:
        return 0.0
    return (hi - remaining) / max(hi - lo, 1e-6)


def effective_speed(mon):
    base = mon.get("base_spe")
    item = (mon.get("item") or "").lower().replace(" ", "")
    if item in MEGA_STONE_MAP and not ("mega" in mon.get("key", "")):
        from .state import DEX
        mega_key = MEGA_STONE_MAP[item][0]
        if mega_key in DEX:
            base = DEX[mega_key].get("baseStats", {}).get("spe")
    if base is None and mon.get("key"):
        from .state import DEX
        base = DEX.get(mon.get("key"), {}).get("baseStats", {}).get("spe")
    if base is None:
        base = mon.get("base_spe", 80)
    lvl = mon.get("level", 100) or 100
    s = float(stat_est(base, lvl, is_hp=False, mon=mon, stat_name="spe"))
    stage = mon.get("speed_stage", 0) or 0
    if stage > 0:
        s *= (2 + stage) / 2
    elif stage < 0:
        s *= 2 / (2 - stage)
    if "choicescarf" in item:
        s *= 1.5
    res = int(s)
    floor_spe = mon.get("speed_floor")
    if floor_spe is not None and floor_spe > 0:
        res = max(res, int(floor_spe))
    ceil_spe = mon.get("speed_ceiling")
    if ceil_spe is not None and ceil_spe > 0:
        res = min(res, int(ceil_spe))
    return res


def detect_item_traps(species_key, current_hp=1.0):
    """Detects high-frequency surprise items (Focus Sash, Choice Scarf, Air Balloon)."""
    if not species_key:
        return []
    try:
        from .state import get_smogon_data
        smogon = get_smogon_data().get(species_key, {})
        items = smogon.get("items", {})
    except Exception:
        return []
    if not items:
        return []

    traps = []
    # 1. Focus Sash (only active if HP is near full)
    sash_odds = items.get("focussash", 0.0)
    if sash_odds >= 0.15 and (current_hp is None or current_hp >= 0.95):
        traps.append({
            "item": "Focus Sash",
            "pct": int(round(sash_odds * 100)),
            "alert": f"⚠️ SASH ALERT ({int(round(sash_odds * 100))}% odds) — will survive lethal OHKO from full HP!",
        })

    # 2. Choice Scarf surprise
    scarf_odds = items.get("choicescarf", 0.0)
    if scarf_odds >= 0.15:
        traps.append({
            "item": "Choice Scarf",
            "pct": int(round(scarf_odds * 100)),
            "alert": f"⚠️ SCARF THREAT ({int(round(scarf_odds * 100))}% odds) — may outspeed faster threats!",
        })

    # 3. Air Balloon
    balloon_odds = items.get("airballoon", 0.0)
    if balloon_odds >= 0.15:
        traps.append({
            "item": "Air Balloon",
            "pct": int(round(balloon_odds * 100)),
            "alert": f"⚠️ AIR BALLOON ({int(round(balloon_odds * 100))}% odds) — Ground immunity!",
        })

    return traps


def identify_win_con(my_team, their_team):
    """Evaluates player's alive team to identify the best late-game sweeper / Win-Con
    against the opponent's remaining Pokémon."""
    if not my_team:
        return None
    try:
        from .state import DEX
    except Exception:
        DEX = {}

    alive_my = [m for m in my_team if not (m.get("fainted") if isinstance(m, dict) else False)]
    alive_th = [m for m in (their_team or []) if not (m.get("fainted") if isinstance(m, dict) else False)]
    if not alive_my:
        return None

    SETUP_MOVES = {"swordsdance", "dragondance", "quiverdance", "nastyplot", "calmmind", "shellsmash", "agility"}

    candidates = []
    for m in alive_my:
        k = m.get("key") if isinstance(m, dict) else m
        dex_entry = DEX.get(k, {})
        m_moves = set(m.get("moves", []) if isinstance(m, dict) else [])
        has_setup = bool(m_moves & SETUP_MOVES)
        b_stats = dex_entry.get("baseStats", {})
        atk_stat = max(b_stats.get("atk", 50), b_stats.get("spa", 50))
        spe_stat = b_stats.get("spe", 50)

        se_hits = 0
        m_types = [t.lower() for t in dex_entry.get("types", [])]
        for th in alive_th:
            th_k = th.get("key") if isinstance(th, dict) else th
            th_types = [t.lower() for t in DEX.get(th_k, {}).get("types", [])]
            for mt in m_types:
                if effectiveness(mt, th_types) > 1.0:
                    se_hits += 1
                    break

        score = (atk_stat * 0.5) + (spe_stat * 0.5) + (se_hits * 25)
        if has_setup:
            score += 50
        candidates.append({
            "key": k,
            "name": dex_entry.get("name", k.capitalize()),
            "score": score,
            "has_setup": has_setup,
        })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    best = candidates[0]
    reason = "Setup sweeper with decisive endgame sweep potential" if best["has_setup"] else "High offensive stats & multi-target coverage"
    return {
        "key": best["key"],
        "name": best["name"],
        "reason": reason,
    }


def compute_switch_pressure(my_mon, their_mon, their_bench=None, my_moves=None, their_hp=1.0):
    """Calculates whether the opponent active mon is in a Forced Turn and estimates
    the switch probability (%) and top likely switch targets on their bench."""
    if not my_mon or not their_mon:
        return None
    try:
        from .state import DEX, MOVES
    except Exception:
        DEX, MOVES = {}, {}

    my_spe = effective_speed(my_mon)
    th_spe = effective_speed(their_mon)
    i_outspeed = my_spe > th_spe

    moves_to_eval = list(my_moves) if my_moves else list(my_mon.get("moves") or [])
    curr_th_hp = max(their_hp if their_hp is not None else 1.0, 0.01)

    max_dmg_lo = 0.0
    max_dmg_hi = 0.0
    best_move = None
    for mk in moves_to_eval:
        dmg = est_damage_pct(my_mon, their_mon, mk, MOVES)
        if dmg and dmg[1] > max_dmg_hi:
            max_dmg_lo, max_dmg_hi = dmg
            best_move = mk

    threatens_ko = (max_dmg_hi >= curr_th_hp * 100.0) or (max_dmg_lo >= curr_th_hp * 85.0)

    th_moves = list(their_mon.get("moves") or [])
    th_threatens_ko = False
    for tmk in th_moves:
        tdmg = est_damage_pct(their_mon, my_mon, tmk, MOVES)
        if tdmg and tdmg[1] >= 90.0:
            th_threatens_ko = True
            break

    is_forced = False
    th_name = their_mon.get('name', 'Foe')
    if i_outspeed and threatens_ko and not th_threatens_ko:
        is_forced = True
        base_odds = 85
        reason = f"{th_name} is outsped and faces lethal KO."
    elif threatens_ko and not th_threatens_ko:
        is_forced = True
        base_odds = 70
        reason = f"{th_name} faces lethal damage from your attacks."
    elif i_outspeed and (max_dmg_hi >= 50.0):
        base_odds = 55
        reason = f"Even pressure; {th_name} takes solid chip."
    elif th_threatens_ko and not i_outspeed:
        base_odds = 15
        reason = f"{th_name} outspeeds and threatens you; unlikely to switch."
    else:
        base_odds = 40
        reason = "Neutral / disputed turn."

    bench_candidates = []
    raw_bench = list(their_bench or [])
    my_types = [t.lower() for t in my_mon.get("types", [])]

    for b in raw_bench:
        bk = b.get("key") if isinstance(b, dict) else b
        if not bk or bk == their_mon.get("key"):
            continue
        b_info = DEX.get(bk, {})
        b_types = [t.lower() for t in b_info.get("types", [])]
        if not b_types:
            continue

        eff_scores = []
        for mt in my_types:
            eff_scores.append(effectiveness(mt, b_types))
        if best_move and best_move in MOVES:
            eff_scores.append(effectiveness(MOVES[best_move]["type"].lower(), b_types))

        avg_eff = sum(eff_scores) / max(len(eff_scores), 1)
        resists_all = all(s <= 1.0 for s in eff_scores)
        has_immunity = any(s == 0.0 for s in eff_scores)
        has_resist = any(s < 1.0 for s in eff_scores)

        suitability = 100 - int(avg_eff * 50)
        if has_immunity:
            suitability += 40
        elif has_resist:
            suitability += 20
        if not resists_all:
            suitability -= 25

        reasons = []
        if has_immunity:
            reasons.append("Type immunity")
        elif has_resist:
            reasons.append("Resists attacks")
        b_stats = b_info.get("baseStats", {})
        if b_stats.get("def", 0) >= 100 or b_stats.get("spd", 0) >= 100:
            reasons.append("defensive bulk")

        bench_candidates.append({
            "key": bk,
            "name": b_info.get("name", bk.capitalize()),
            "score": suitability,
            "reason": ", ".join(reasons) if reasons else "Neutral pivot",
        })

    bench_candidates.sort(key=lambda x: x["score"], reverse=True)
    if not bench_candidates:
        if raw_bench and len(raw_bench) == 0:
            base_odds = 0
            reason = "No bench available (last mon)."
    else:
        top_score = bench_candidates[0]["score"]
        if is_forced:
            if top_score >= 100:
                base_odds = min(90, base_odds + 5)
            elif top_score < 60:
                base_odds = max(55, base_odds - 15)

    total_top = bench_candidates[:3]
    tot_score = max(sum(max(c["score"], 1) for c in total_top), 1)
    for c in total_top:
        c["pct"] = int(round((max(c["score"], 1) / tot_score) * 100))

    level_str = "HIGH" if base_odds >= 70 else ("MEDIUM" if base_odds >= 40 else "LOW")

    return {
        "odds": base_odds,
        "level": level_str,
        "is_forced": is_forced,
        "reason": reason,
        "top_targets": total_top,
    }


ABILITY_IMMUNITIES = {
    "ground": ["levitate"],
    "electric": ["voltabsorb", "lightningrod", "motordrive"],
    "fire": ["flashfire"],
    "water": ["waterabsorb", "stormdrain", "dryskin"],
    "grass": ["sapsipper"],
}


def compute_match_eval(my_team=None, their_team=None, my_mon=None, their_mon=None, my_hp=1.0, their_hp=1.0, my_fainted=None, their_fainted=None, moves_db=None):
    """Computes real-time Stockfish-style Win Probability % and Evaluation Score (<0.2ms).
    Considers:
      - Material balance (alive mon count difference, 100 pts each)
      - Remaining HP pools across active and bench (50 pts per 1.0 HP)
      - Active speed tempo (+15 pts if faster, -15 pts if slower)
      - Active immediate threat / OHKO leverage (+25 pts if we OHKO, -25 pts if they OHKO)
    Returns a dict with win_pct, eval_score, eval_str, bar_color, lead_text, and summary.
    """
    import math

    # Material & HP counts
    my_fainted_count = len(my_fainted) if my_fainted else 0
    th_fainted_count = len(their_fainted) if their_fainted else 0

    my_alive = 0
    my_hp_sum = 0.0
    if my_team:
        for m in my_team:
            is_dead = m.get("fainted", False) if isinstance(m, dict) else False
            if is_dead:
                my_fainted_count = max(my_fainted_count, 1)
            else:
                my_alive += 1
                is_active = (isinstance(m, dict) and m.get("key") == (my_mon.get("key") if my_mon else None))
                if is_active and my_hp is not None:
                    my_hp_sum += max(0.0, min(1.0, float(my_hp)))
                else:
                    my_hp_sum += 1.0
        if len(my_team) < 6:
            unrevealed = max(0, 6 - len(my_team) - my_fainted_count)
            my_alive += unrevealed
            my_hp_sum += float(unrevealed)
    elif my_mon:
        my_alive = max(0, 6 - my_fainted_count)
        act_hp = max(0.0, min(1.0, float(my_hp))) if my_hp is not None else 1.0
        my_hp_sum = max(0.0, float(max(0, my_alive - 1))) + act_hp
    else:
        my_alive = max(0, 6 - my_fainted_count)
        my_hp_sum = float(my_alive)

    th_alive = 0
    th_hp_sum = 0.0
    if their_team:
        for m in their_team:
            is_dead = m.get("fainted", False) if isinstance(m, dict) else False
            if is_dead:
                th_fainted_count = max(th_fainted_count, 1)
            else:
                th_alive += 1
                is_active = (isinstance(m, dict) and m.get("key") == (their_mon.get("key") if their_mon else None))
                if is_active and their_hp is not None:
                    th_hp_sum += max(0.0, min(1.0, float(their_hp)))
                else:
                    th_hp_sum += 1.0
        if len(their_team) < 6:
            unrevealed = max(0, 6 - len(their_team) - th_fainted_count)
            th_alive += unrevealed
            th_hp_sum += float(unrevealed)
    elif their_mon:
        th_alive = max(0, 6 - th_fainted_count)
        act_hp = max(0.0, min(1.0, float(their_hp))) if their_hp is not None else 1.0
        th_hp_sum = max(0.0, float(max(0, th_alive - 1))) + act_hp
    else:
        th_alive = max(0, 6 - th_fainted_count)
        th_hp_sum = float(th_alive)

    # Edge cases: Complete wipeout
    if my_alive <= 0:
        return {
            "win_pct": 0,
            "eval_score": -9.9,
            "eval_str": "-9.9",
            "bar_color": "#FF4D4D",
            "lead_text": "DEFEAT",
            "summary": "-9.9 EVAL | 0% WIN PROBABILITY",
        }
    if th_alive <= 0:
        return {
            "win_pct": 100,
            "eval_score": 9.9,
            "eval_str": "+9.9",
            "bar_color": "#7CFC00",
            "lead_text": "VICTORY",
            "summary": "+9.9 EVAL | 100% WIN PROBABILITY",
        }

    # Active tempo & immediate lethal threat calculation
    tempo_score = 0
    if my_mon and their_mon:
        my_spe = effective_speed(my_mon)
        th_spe = effective_speed(their_mon)
        if my_spe > th_spe:
            tempo_score += 15
        elif my_spe < th_spe:
            tempo_score -= 15

        if moves_db is None:
            try:
                from .state import MOVES
                moves_db = MOVES
            except Exception:
                moves_db = {}

        th_curr_hp = max(their_hp if their_hp is not None else 1.0, 0.01)
        my_mvs = list(my_mon.get("moves") or [])
        for mk in my_mvs:
            if mk in moves_db:
                dmg = est_damage_pct(my_mon, their_mon, mk, moves_db)
                if dmg and ko_chance(dmg, th_curr_hp) and ko_chance(dmg, th_curr_hp) >= 0.75:
                    tempo_score += 25
                    break

        my_curr_hp = max(my_hp if my_hp is not None else 1.0, 0.01)
        th_mvs = list(their_mon.get("moves") or [])
        for mk in th_mvs:
            if mk in moves_db:
                dmg = est_damage_pct(their_mon, my_mon, mk, moves_db)
                if dmg and ko_chance(dmg, my_curr_hp) and ko_chance(dmg, my_curr_hp) >= 0.75:
                    tempo_score -= 25
                    break

    material_diff = (my_alive - th_alive) * 100
    hp_diff = (my_hp_sum - th_hp_sum) * 50
    net_diff = material_diff + hp_diff + tempo_score

    eval_score = round(net_diff / 100.0, 1)

    # Sigmoid mapping to Win %: ~100 diff gives ~77%, ~200 diff gives ~91%, ~300 diff gives ~97%
    p = 1.0 / (1.0 + math.exp(-0.012 * net_diff))
    win_pct = int(round(p * 100))
    win_pct = max(3, min(97, win_pct))

    if eval_score >= 1.5:
        bar_color = "#7CFC00"  # emerald green / strong lead
        lead_text = "DOMINANT LEAD"
    elif eval_score >= 0.4:
        bar_color = "#00E5FF"  # cyan / favored
        lead_text = "FAVORED"
    elif eval_score > -0.4:
        bar_color = "#FFD700"  # yellow / even
        lead_text = "EVEN MATCH"
    elif eval_score > -1.5:
        bar_color = "#FF9F43"  # orange / deficit
        lead_text = "DEFICIT"
    else:
        bar_color = "#FF4D4D"  # red / critical deficit
        lead_text = "CRITICAL DEFICIT"

    eval_str = f"{'+' if eval_score > 0 else ''}{eval_score:.1f}"
    summary = f"{eval_str} EVAL | {win_pct}% WIN PROBABILITY"

    return {
        "win_pct": win_pct,
        "eval_score": eval_score,
        "eval_str": eval_str,
        "bar_color": bar_color,
        "lead_text": lead_text,
        "summary": summary,
        "my_alive": my_alive,
        "th_alive": th_alive,
    }


def detect_choice_lock_and_bluff(my_mon, their_mon, my_team=None, their_locked_move=None, moves_db=None):
    """Detects opponent Choice-lock exploitation and player Bluff / Conditioning opportunities (<0.1ms)."""
    if moves_db is None:
        try:
            from .state import MOVES
            moves_db = MOVES
        except Exception:
            moves_db = {}

    th_item = (their_mon.get("item") or "").lower().replace(" ", "") if their_mon else ""
    is_th_choice = any(c in th_item for c in ("choicescarf", "choiceband", "choicespecs"))

    th_locked_move = their_locked_move if (is_th_choice and their_locked_move) else None
    th_locked_name = moves_db.get(th_locked_move, {}).get("name", th_locked_move) if th_locked_move else None
    exploit_advice = None
    immune_targets = []
    resist_targets = []

    if th_locked_move and th_locked_move in moves_db:
        m_info = moves_db[th_locked_move]
        m_type = m_info.get("type", "Normal").lower()

        team_candidates = list(my_team) if my_team else []
        for cand in team_candidates:
            if not isinstance(cand, dict) or cand.get("fainted"):
                continue
            cand_types = [t.lower() for t in cand.get("types", [])]
            cand_ability = (cand.get("ability") or "").lower().replace(" ", "")

            eff = effectiveness(m_type, cand_types)
            is_immune = (eff == 0.0)
            if not is_immune and m_type in ABILITY_IMMUNITIES:
                if cand_ability in ABILITY_IMMUNITIES[m_type]:
                    is_immune = True

            cand_name = cand.get("name") or cand.get("key", "").capitalize()
            if is_immune:
                immune_targets.append({"name": cand_name, "key": cand.get("key"), "eff": 0.0})
            elif eff <= 0.5:
                resist_targets.append({"name": cand_name, "key": cand.get("key"), "eff": eff})

        if immune_targets:
            t_name = immune_targets[0]["name"]
            exploit_advice = f"Locked into {th_locked_name}! Switch to {t_name} for 100% IMMUNITY and free setup turn!"
        elif resist_targets:
            t_name = resist_targets[0]["name"]
            exploit_advice = f"Locked into {th_locked_name}! Switch to {t_name} (resists {th_locked_name}) to seize momentum."
        else:
            exploit_advice = f"Opponent locked into {th_locked_name}. Exploit restricted lock!"

    bluff_ready = False
    bluff_advice = None
    if my_mon:
        my_item = (my_mon.get("item") or "").lower().replace(" ", "")
        is_my_choice = any(c in my_item for c in ("choicescarf", "choiceband", "choicespecs"))

        if not is_my_choice:
            COMMON_BLUFF_MONS = {
                "garchomp", "dragapult", "hydreigon", "latios", "latias",
                "tyranitar", "greninja", "kartana", "weavile", "zarude",
                "rotomwash", "rotomheat", "volcarona", "landorustherian", "scizor"
            }
            COMMON_BLUFF_MOVES = {
                "dracometeor", "closecombat", "uturn", "voltswitch", "overheat",
                "leafstorm", "earthquake", "stoneedge", "outrage", "shadowball",
                "hydropump", "trick", "blizzard", "focusblast"
            }
            my_key = (my_mon.get("key") or "").lower().replace("-", "")
            my_mvs = set(m.lower().replace("-", "") for m in (my_mon.get("moves") or []))

            matched_bluff_moves = my_mvs.intersection(COMMON_BLUFF_MOVES)
            if my_key in COMMON_BLUFF_MONS or matched_bluff_moves:
                bluff_ready = True
                item_disp = my_mon.get("item") or "Life Orb/Leftovers"
                mv_disp = moves_db.get(list(matched_bluff_moves)[0], {}).get("name", "high-damage move") if matched_bluff_moves else "powerful attack"
                bluff_advice = f"Holding {item_disp}: Feign Choice-lock after clicking {mv_disp}. Opponent will predict you are locked and switch into an answer—punish their switch with unexpected coverage!"

    return {
        "th_locked_move": th_locked_move,
        "th_locked_name": th_locked_name,
        "exploit_advice": exploit_advice,
        "immune_targets": immune_targets,
        "resist_targets": resist_targets,
        "bluff_ready": bluff_ready,
        "bluff_advice": bluff_advice,
    }


def get_turn_quick_calc(my_mon, their_mon, my_moves=None, moves_db=None, their_hp=1.0, my_hp=1.0, their_bench=None, my_team=None, their_team=None, my_fainted=None, their_fainted=None, their_locked_move=None):
    """Computes instant zero-latency speed tiers, move damage ranges, Stockfish match evaluation, and tactical switch/trap predictions (<1ms).
    Returns a dict with speed comparison, move damage percentages, evaluation, and tactical context.
    """
    if not my_mon or not their_mon:
        return None
    if moves_db is None:
        try:
            from .state import MOVES
            moves_db = MOVES
        except Exception:
            moves_db = {}

    my_spe = effective_speed(my_mon)
    th_spe = effective_speed(their_mon)

    if my_spe > th_spe:
        status = "FASTER"
        color = "#7CFC00"  # bright green
        sp_text = f"🟢 FASTER ({my_spe} vs {th_spe} Spe)"
    elif my_spe < th_spe:
        status = "SLOWER"
        color = "#FF6B6B"  # light red
        sp_text = f"🔴 SLOWER ({my_spe} vs {th_spe} Spe)"
    else:
        status = "TIE"
        color = "#FFD700"  # yellow
        sp_text = f"⚠️ SPEED TIE ({my_spe} Spe)"

    th_item = (their_mon.get("item") or "").lower().replace(" ", "")
    has_scarf = "choicescarf" in th_item
    scarf_threat = False
    scarf_text = ""
    if not has_scarf and status == "FASTER":
        pot_scarf = int(th_spe * 1.5)
        if pot_scarf > my_spe:
            scarf_threat = True
            scarf_text = f"⚠️ Scarf outspeeds ({pot_scarf} Spe)"

    moves_out = []
    moves_to_eval = list(my_moves) if my_moves else list(my_mon.get("moves") or [])
    curr_hp = max(their_hp if their_hp is not None else 1.0, 0.01)

    for mk in moves_to_eval:
        if mk not in moves_db:
            continue
        m = moves_db[mk]
        cat = m.get("category", "Status")
        dmg = est_damage_pct(my_mon, their_mon, mk, moves_db)
        if dmg:
            lo, hi = dmg
            dmg_str = f"{int(round(lo))}-{int(round(hi))}%"
            ko = ko_chance(dmg, curr_hp)
            if ko is not None:
                if ko >= 1.0:
                    ko_str = "OHKO"
                elif ko > 0.0:
                    ko_str = f"OHKO ~{int(round(ko*100))}%"
                elif lo * 2 >= curr_hp * 100:
                    ko_str = "2HKO"
                elif lo * 3 >= curr_hp * 100:
                    ko_str = "3HKO"
                else:
                    ko_str = ""
            else:
                ko_str = ""
        else:
            dmg_str = "Status"
            ko_str = ""

        eff = effectiveness(m["type"].lower(), [t.lower() for t in their_mon.get("types", [])])
        moves_out.append({
            "key": mk,
            "name": m.get("name", mk),
            "type": m.get("type", "Normal"),
            "category": cat,
            "damage_str": dmg_str,
            "ko_str": ko_str,
            "effectiveness": eff,
        })

    # Tactical Intelligence calculations (<0.2ms)
    switch_info = compute_switch_pressure(my_mon, their_mon, their_bench=their_bench, my_moves=moves_to_eval, their_hp=curr_hp)
    traps = detect_item_traps(their_mon.get("key"), curr_hp)
    win_con = identify_win_con(my_team, their_team) if my_team else None

    # Quantum Evaluation Engine (<0.1ms)
    eval_info = compute_match_eval(
        my_team=my_team,
        their_team=their_team or their_bench,
        my_mon=my_mon,
        their_mon=their_mon,
        my_hp=my_hp,
        their_hp=curr_hp,
        my_fainted=my_fainted,
        their_fainted=their_fainted,
        moves_db=moves_db,
    )

    # Choice-Lock & Bluff Intel (<0.1ms)
    choice_intel = detect_choice_lock_and_bluff(
        my_mon=my_mon,
        their_mon=their_mon,
        my_team=my_team,
        their_locked_move=their_locked_move,
        moves_db=moves_db,
    )

    return {
        "speed": {
            "my_spe": my_spe,
            "th_spe": th_spe,
            "status": status,
            "color": color,
            "text": sp_text,
            "scarf_threat": scarf_threat,
            "scarf_text": scarf_text,
        },
        "moves": moves_out,
        "eval": eval_info,
        "choice_intel": choice_intel,
        "tactics": {
            "switch_pressure": switch_info,
            "traps": traps,
            "win_con": win_con,
            "eval": eval_info,
            "choice_intel": choice_intel,
        }
    }


