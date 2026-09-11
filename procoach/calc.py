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


def stat_est(base, level, is_hp=False):
    if is_hp:
        return int((2 * base + 31 + 21) * level / 100) + level + 10
    return int((2 * base + 31 + 21) * level / 100) + 5


def _base_stats(mon):
    from .state import DEX

    entry = DEX.get(mon["key"], {})
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
    physical = m["category"] == "Physical"
    A = stat_est(a_bs.get("atk", 50) if physical else a_bs.get("spa", 50), att["level"])
    D = stat_est(d_bs.get("def", 50) if physical else d_bs.get("spd", 50), dfn["level"])
    HP = stat_est(d_bs.get("hp", 60), dfn["level"], is_hp=True)
    stab = 1.5 if m["type"].lower() in [t.lower() for t in att["types"]] else 1.0
    eff = effectiveness(m["type"].lower(), [t.lower() for t in dfn["types"]])
    if eff == 0:
        return None
    item = (att.get("item") or "").lower().replace(" ", "").replace("(knockedoff)", "")
    mult = ITEM_ATK_MULT.get(item, 1.0) if item else 1.0
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
    base = mon.get("base_spe", 80)
    s = float(stat_est(base, mon["level"]))
    stage = mon.get("speed_stage", 0) or 0
    if stage > 0:
        s *= (2 + stage) / 2
    elif stage < 0:
        s *= 2 / (2 - stage)
    item = (mon.get("item") or "").lower().replace(" ", "")
    if "choicescarf" in item:
        s *= 1.5
    return int(s)
