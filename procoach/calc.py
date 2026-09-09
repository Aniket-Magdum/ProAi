"""Rough damage/speed estimation for outcome branching.

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
    from .advisor import effectiveness  # deferred: advisor imports this module

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
    s = stat_est(base, mon["level"])
    item = (mon.get("item") or "").lower().replace(" ", "")
    if "choicescarf" in item:
        s = int(s * 1.5)
    return s
