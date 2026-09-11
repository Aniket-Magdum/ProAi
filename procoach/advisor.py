"""Instant rules-based advice: type effectiveness, speed, threats, switches."""
import json
from pathlib import Path

from . import calc
from .calc import effectiveness
from .state import DEX, MOVES

_DATA = Path(__file__).resolve().parent.parent / "data"
try:
    with open(_DATA / "learnsets.json", encoding="utf8") as f:
        LEARNSETS = json.load(f)
except OSError:
    LEARNSETS = {}
try:
    with open(_DATA / "smogon_sets.json", encoding="utf8") as f:
        SMOGON = json.load(f)
except OSError:
    SMOGON = {}

STAPLES = {
    "swordsdance", "nastyplot", "dragondance", "calmmind", "irondefense", "agility",
    "bulkup", "curse", "shellsmash", "quiverdance", "rockpolish", "cosmicpower",
    "substitute", "protect", "recover", "roost", "moonlight", "morningsun",
    "slackoff", "synthesis", "strengthsap", "shoreup", "rest", "softboiled",
    "stealthrock", "spikes", "toxicspikes", "stickyweb", "leechseed",
    "willowisp", "toxic", "thunderwave", "glare", "hypnosis", "sleeppowder",
    "spore", "yawn", "encore", "taunt", "trickroom", "uturn", "flipturn",
    "voltswitch", "batonpass", "partingshot", "healingwish", "lunardance",
    "destinybond", "fakeout", "pursuit", "rapidspin", "defog", "knockoff",
    "trick", "switcheroo", "followme", "ragepowder", "wideguard",
    "suckerpunch", "extremespeed", "aquajet", "bulletpunch", "machpunch",
    "quickattack", "vacuumwave",
}

# type chart + effectiveness live in calc.py (shared with the damage calc)
CHART = calc.TYPE_CHART


def est_speed(base_spe, level):
    """Neutral nature, moderate EVs (85)."""
    return int((2 * base_spe + 31 + 21) * level / 100) + 5


def type_of(move_key):
    return MOVES[move_key]["type"].lower()


def score_move(move_key, my_types, their_types):
    mv = MOVES[move_key]
    if mv["category"] == "Status":
        return 0.0, "status"
    eff = effectiveness(mv["type"].lower(), [t.lower() for t in their_types])
    stab = 1.5 if mv["type"].lower() in [t.lower() for t in my_types] else 1.0
    acc = mv["accuracy"] / 100.0
    bp = max(mv["basePower"], 40) if eff > 0 else 0
    return eff * stab * acc * bp, None


def predict_moves(mon):
    """Likely moves for a species: Smogon set frequency first, learnset fallback."""
    learn = LEARNSETS.get(mon["key"]) or []
    smogon = SMOGON.get(mon["key"], {})
    stab = {t.lower() for t in mon["types"]}
    scored = []
    for mk in learn:
        mv = MOVES.get(mk)
        if not mv:
            continue
        s = 0.0
        if mv["category"] != "Status":
            if mv["type"].lower() in stab:
                s += 2.0 + mv["basePower"] / 150.0
            elif mv["basePower"] >= 70:
                s += 0.5 + mv["basePower"] / 300.0
            elif mv["basePower"] >= 40:
                s += 0.2
        if mk in STAPLES:
            s += 1.5
        sg = smogon.get(mk, 0)
        if sg:
            s += 2.0 + sg * 8.0   # real Smogon usage frequency (0..1) = strongest signal
        if s > 0:
            scored.append((s, mk))
    scored.sort(reverse=True)
    return [mk for _, mk in scored[:5]]


def _hopeless(my, th, th_moves):
    """True if my active can't meaningfully damage th while th threatens it."""
    my_eff = [
        effectiveness(MOVES[mk]["type"].lower(), [t.lower() for t in th["types"]])
        for mk in (my["moves"] or [])
        if mk in MOVES and MOVES[mk]["category"] != "Status"
    ]
    can_hurt = max(my_eff, default=0) >= 1.5
    if can_hurt:
        return False
    threatens = any(
        effectiveness(MOVES[mk]["type"].lower(), [t.lower() for t in my["types"]]) >= 2
        for mk in th_moves
        if mk in MOVES
    )
    stab_threat = any(
        effectiveness(t.lower(), [x.lower() for x in my["types"]]) >= 2
        for t in th["types"]
    )
    return threatens or stab_threat


def rank_my_bench(state, th):
    """(score, name) for every healthy bench mon vs their active. Best first."""
    ranked = []
    for key, m in state.mons.items():
        if m["fainted"] or key == state.my_active_key or m.get("side") != "my":
            continue
        resist = sum(
            1 for t in th["types"]
            if effectiveness(t.lower(), [x.lower() for x in m["types"]]) < 1
        )
        weak = sum(
            1 for t in th["types"]
            if effectiveness(t.lower(), [x.lower() for x in m["types"]]) > 1
        )
        hit = max(
            (
                effectiveness(MOVES[mk]["type"].lower(), [x.lower() for x in m["types"]])
                for mk in th["moves"]
                if mk in MOVES
            ),
            default=1,
        )
        ranked.append((resist * 2 - weak * 2 - hit, m["name"]))
    ranked.sort(reverse=True)
    return ranked


def danger_engine(state):
    """HP-aware pre-emptive warnings: SWITCH NOW / FINISH IT."""
    out = []
    my = state.mons.get(state.my_active_key)
    th = state.mons.get(state.their_active_key)
    if not my or not th:
        return out

    th_known_se = [
        MOVES[mk]["name"]
        for mk in th["moves"]
        if mk in MOVES and MOVES[mk]["category"] != "Status"
        and effectiveness(MOVES[mk]["type"].lower(), [t.lower() for t in my["types"]]) >= 2
    ]

    bench_pick = ""
    ranked = rank_my_bench(state, th)
    if ranked:
        bench_pick = f" -> send {ranked[0][1].upper()}"

    # SWITCH NOW: I can't hurt them and they threaten me
    if _hopeless(my, th, th["moves"]):
        out.append(("use", f"SWITCH NOW: you can't hurt {th['name']} and it threatens you{bench_pick}"))
    # SWITCH NOW: their SE move + my low HP
    elif th_known_se and state.my_hp is not None and state.my_hp <= 0.40:
        out.append((
            "use",
            f"SWITCH NOW: {', '.join(th_known_se)} KOs you at ~{int(state.my_hp*100)}% HP{bench_pick}",
        ))
    elif th_known_se and state.my_hp is None and len(th_known_se) >= 1 and my["moves"]:
        pass  # don't nag without HP info

    # FINISH IT: their active is low and I have a SE STAB ready
    if state.their_hp is not None and state.their_hp <= 0.35:
        for mk in state.menu_moves or my["moves"]:
            if mk not in MOVES or MOVES[mk]["category"] == "Status":
                continue
            eff = effectiveness(MOVES[mk]["type"].lower(), [t.lower() for t in th["types"]])
            stab = MOVES[mk]["type"].lower() in [t.lower() for t in my["types"]]
            if eff >= 2 or (eff >= 1 and stab and state.their_hp <= 0.25):
                out.append(("use", f"FINISH IT: {MOVES[mk]['name']} KOs {th['name']} at ~{int(state.their_hp*100)}%"))
                break

    # their HP low -> tell me to pressure, not pivot
    if state.their_hp is not None and state.their_hp <= 0.35:
        out.append(("info", f"{th['name']} is low (~{int(state.their_hp*100)}%) - don't switch, pressure it"))
    return out


PIVOT_MOVES = {"flipturn", "uturn", "voltswitch", "batonpass", "partingshot", "teleport", "shedtail"}


def incoming_score(bench_mon, my):
    """How happy THEY are to send bench_mon into my active (higher = better for them)."""
    score = 0.0
    my_stabs = {t.lower() for t in my["types"]}
    for t in my_stabs:
        eff = effectiveness(t, [x.lower() for x in bench_mon["types"]])
        if eff < 1:
            score += 2.0
        elif eff >= 2:
            score -= 2.0
    for t in (x.lower() for x in bench_mon["types"]):
        if effectiveness(t, [x.lower() for x in my["types"]]) >= 2:
            score += 2.0
    for mk in bench_mon["moves"]:
        if mk in MOVES and effectiveness(MOVES[mk]["type"].lower(), [x.lower() for x in my["types"]]) >= 2:
            score += 1.5
    return score


def opponent_switch_watch(state):
    """Predict their switching intent: pivot moves, low-HP pull-backs."""
    out = []
    my = state.mons.get(state.my_active_key)
    th = state.mons.get(state.their_active_key)
    if not my or not th:
        return out

    bench = [
        m for k, m in state.mons.items()
        if m.get("side") == "their" and k != state.their_active_key and not m.get("fainted")
    ]
    pivots = [mk for mk in th["moves"] if mk in PIVOT_MOVES]
    if not pivots:
        pivots = [mk for mk in predict_moves(th) if mk in PIVOT_MOVES]

    if pivots and bench:
        best = max(bench, key=lambda m: incoming_score(m, my))
        if incoming_score(best, my) >= 2.0:
            out.append((
                "beware",
                f"PIVOT WATCH: {th['name']} has {MOVES[pivots[0]]['name']} - expect "
                f"{best['name']} in (handles your {my['name']}); preview your move vs IT",
            ))
    if state.their_hp is not None and state.their_hp <= 0.35:
        out.append((
            "info",
            f"{th['name']} is low - expect a pull-back; don't chase it with anything frail",
        ))
    return out


def expect_their_switchin(state, my, my_move_key):
    """Predict their best response to my move: stay-in or which bench mon."""
    bench = [
        m for k, m in state.mons.items()
        if m.get("side") == "their" and k != state.their_active_key and not m.get("fainted")
    ]
    if not bench:
        return "EXPECT: counter-switch incoming (slot unknown) - don't overcommit next turn"
    mv = MOVES[my_move_key]

    def score(m):
        s = 0.0
        eff_in = effectiveness(mv["type"].lower(), [t.lower() for t in m["types"]])
        if eff_in == 0:
            s += 3.0
        elif eff_in < 1:
            s += 2.0
        for t in m["types"]:
            if effectiveness(t.lower(), [x.lower() for x in my["types"]]) >= 2:
                s += 2.0
        for km in m["moves"]:
            if (
                km in MOVES
                and effectiveness(MOVES[km]["type"].lower(), [x.lower() for x in my["types"]]) >= 2
            ):
                s += 1.5
        return s

    best = max(bench, key=score)
    best_s = score(best)
    if best_s >= 4.0:
        return (
            f"EXPECT: switch to {best['name']} (absorbs your {mv['name']}, threatens you) "
            "- plan next move vs IT"
        )
    if best_s >= 2.0:
        return f"EXPECT: likely switch to {best['name']} - preview your options vs IT"
    return "EXPECT: counter-switch incoming - hold your best coverage"


def move_outcomes(state, my, th):
    """Branch prediction per menu move: damage range, KO odds, their response."""
    lines = []
    their_hp = state.their_hp if state.their_hp is not None else 1.0
    i_first = calc.effective_speed(my) > calc.effective_speed(th) * 1.05

    atk_rows = []
    for mk in state.menu_moves:
        if mk not in MOVES or MOVES[mk]["category"] == "Status":
            continue
        dmg = calc.est_damage_pct(my, th, mk, MOVES)
        if dmg is None:
            continue
        chance = calc.ko_chance(dmg, their_hp)
        atk_rows.append((chance, mk, dmg))

    if not atk_rows:
        return lines

    atk_rows.sort(key=lambda r: (-(r[0] if r[0] is not None else 0), -r[2][1]))
    chance, mk, (lo, hi) = atk_rows[0]
    name = MOVES[mk]["name"].upper()
    speed_note = "you hit first" if i_first else "they move first - watch for the trade"
    if chance >= 0.85 and i_first:
        lines.append(("use", f"USE {name}: ~{int(lo)}-{int(hi)}% vs ~{int(their_hp*100)}% HP - LIKELY KO ({speed_note})"))
    elif chance >= 0.4:
        lines.append(("use", f"USE {name}: ~{int(lo)}-{int(hi)}% - KO {int(chance*100)}% likely ({speed_note})"))
    else:
        lines.append(("use", f"USE {name}: ~{int(lo)}-{int(hi)}% vs ~{int(their_hp*100)}% HP - NO KO ({speed_note})"))
        exp = expect_their_switchin(state, my, mk)
        if exp:
            lines.append(("beware", exp))
    return lines


def advise(state):
    """Returns (advice_line, overlay_lines)."""
    out = danger_engine(state) + opponent_switch_watch(state)
    my = state.mons.get(state.my_active_key)
    th = state.mons.get(state.their_active_key)

    if state.menu_mode == "attack" and my and th:
        outcome_lines = move_outcomes(state, my, th)
        if outcome_lines:
            out.extend(outcome_lines)
        else:
            scored = []
            for mk in state.menu_moves:
                s, note = score_move(mk, my["types"], th["types"])
                scored.append((s, mk, note))
            scored.sort(reverse=True)
            if scored and scored[0][0] > 0:
                best_s, best, _ = scored[0]
                eff = effectiveness(type_of(best), [t.lower() for t in th["types"]])
                stab = type_of(best) in [t.lower() for t in my["types"]]
                why = []
                if eff >= 2:
                    why.append("super effective")
                elif eff == 0:
                    why.append("immune targets only")
                elif eff < 1:
                    why.append("resisted")
                if stab:
                    why.append("STAB")
                out.append(("use", f"USE: {MOVES[best]['name'].upper()}" + (f" ({', '.join(why)})" if why else "")))
                worst = scored[-1]
                if worst[0] > 0 and worst[1] != best:
                    weff = effectiveness(type_of(worst[1]), [t.lower() for t in th["types"]])
                    if weff < 1:
                        out.append(("avoid", f"AVOID: {MOVES[worst[1]]['name']} (resisted)"))
            # speed
            my_spd = est_speed(my["base_spe"], my["level"])
            th_spd = est_speed(th["base_spe"], th["level"])
            if my_spd > th_spd * 1.1:
                out.append(("speed", "SPEED: you likely outspeed"))
            elif th_spd > my_spd * 1.1:
                out.append(("speed", "SPEED: they likely outspeed - expect them to move first"))
            else:
                out.append(("speed", "SPEED: too close to call"))

    # beware: their STABs that hit my active hard + predicted moves
    if my and th:
        threats = []
        for t in th["types"]:
            eff = effectiveness(t.lower(), [x.lower() for x in my["types"]])
            if eff >= 2:
                threats.append(f"{t}-type moves ({eff:.0f}x on you)")
        known = [
            MOVES[mk]["name"]
            for mk in th["moves"]
            if mk in MOVES
            and effectiveness(MOVES[mk]["type"].lower(), [x.lower() for x in my["types"]]) >= 2
        ]
        predicted = predict_moves(th)
        pred_se = [
            MOVES[mk]["name"]
            for mk in predicted
            if effectiveness(MOVES[mk]["type"].lower(), [x.lower() for x in my["types"]]) >= 2
        ]
        # only warn when there is a real threat - silence is not advice
        if threats or known or pred_se:
            line = "BEWARE: " + ("; ".join(threats) if threats else "no STAB threat, but:")
            if known:
                line += f" SE known: {', '.join(known)}"
            elif pred_se:
                line += f" SE likely: {', '.join(pred_se[:3])}"
            out.append(("beware", line))
        if predicted and len(th["moves"]) < 3:
            names = []
            for mk in predicted[:3]:
                mark = MOVES[mk]["name"]
                if mk not in th["moves"]:
                    mark += "?"
                names.append(mark)
            out.append(("info", f"THEIR LIKELY MOVES: {', '.join(names)}"))

    # their active boosted Speed past ours (Dragon Dance, Agility...) - recheck trades
    if my and th and (th.get("speed_stage", 0) or 0) > 0:
        if calc.effective_speed(th) > calc.effective_speed(my):
            out.append((
                "beware",
                f"THEY BOOSTED SPEED (+{th['speed_stage']}) - {th['name']} outspeeds "
                f"{my['name']} now; don't count on hitting first",
            ))

    # switch advice: on the switch screen OR right after my faint
    if th and (state.menu_mode == "switch" or state.pending_switch):
        prefix = (
            f"YOUR {state.mons.get(state.pending_switch, {}).get('name', 'mon')} FAINTED - "
            if state.pending_switch and not state.menu_mode == "switch"
            else ""
        )
        ranked = rank_my_bench(state, th)
        if ranked:
            out.append(("use", f"{prefix}SWITCH -> {ranked[0][1].upper()} (best matchup vs {th['name']})"))
        elif prefix:
            out.append(("use", f"{prefix}pick your best resist (bench not scanned yet)"))

    return out
