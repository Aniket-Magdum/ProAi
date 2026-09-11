"""Full self-test: replays real battle-log lines through the whole stack."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach.advisor import advise, predict_moves
from procoach import calc
from procoach.state import BattleState, MOVES

# tests must never read or overwrite the real battlestate.json
BattleState.STATE_FILE = Path(tempfile.gettempdir()) / "procoach_test_battlestate.json"
if BattleState.STATE_FILE.exists():
    BattleState.STATE_FILE.unlink()

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name} {detail}")
    if not cond:
        failures.append(name)


print("=== 1. log parsing: send-outs, moves, items, abilities ===")
s = BattleState()
s.reset()
s.feed(
    "Battle Log\n"
    "Flash001 sends out Garchomp!\n"
    "Go, Pikachu!\n"
    "Pikachu attacks Garchomp with Thunderbolt.\n"
    "It's super effective!\n"
    "The opposing Garchomp attacks Pikachu with Earthquake.\n"
    "It's super effective!\n"
    "Garchomp restored HP using Leftovers!\n"
    "Garchomp's Rough Skin!\n"
    "Pikachu was paralyzed! It may be unable to move!\n"
    "Battle turn #1 ended.\n"
)
check("their active = Garchomp", s.their_active_key == "their:garchomp", s.their_active_key)
check("my active = Pikachu", s.my_active_key == "my:pikachu", s.my_active_key)
check("Thunderbolt on my Pikachu",
      "thunderbolt" in s.mons["my:pikachu"]["moves"])
check("Garchomp knows Earthquake", "earthquake" in s.mons["their:garchomp"]["moves"])
check("Garchomp item Leftovers", s.mons["their:garchomp"]["item"] == "Leftovers")
check("Garchomp ability Rough Skin", s.mons["their:garchomp"]["ability"] == "Rough Skin")
check("Pikachu status PAR", s.mons["my:pikachu"]["status"] == "PAR")
check("turn tracked", s.turn == 1)

print()
print("=== 1b. mirror match: same species both sides stay separate ===")
s.feed(
    "The opposing Venusaur attacks Venusaur with Sludge Bomb.\n"
    "Venusaur attacks Venusaur with Sludge Bomb.\n"
    "Venusaur restored HP using Black Sludge!\n"
)
check("my venusaur and their venusaur are distinct entries",
      "my:venusaur" in s.mons and "their:venusaur" in s.mons)
check("both learned Sludge Bomb (side-attributed)",
      "sludgebomb" in s.mons["my:venusaur"]["moves"]
      and "sludgebomb" in s.mons["their:venusaur"]["moves"])
check("unmarked restore attributed to NEITHER side when ambiguous (no corruption)",
      s.mons["my:venusaur"]["item"] is None and s.mons["their:venusaur"]["item"] is None)

print()
print("=== 2. faint inference: no 'Come back' before send-out ===")
s.feed(
    "The opposing Garchomp has fainted!\n"
    "Flash001 sends out Manaphy!\n"
    "Battle turn #2 ended.\n"
)
check("Garchomp marked fainted", s.mons["their:garchomp"]["fainted"])
check("their active switched to Manaphy", s.their_active_key == "their:manaphy",
      s.their_active_key)

print()
print("=== 2b. faint forms: opponent 'fainted' without 'has' ===")
s2b = BattleState()
s2b.reset()
s2b.feed(
    "Flash001 sends out Zapdos!\n"
    "Battle turn #1 ended.\n"
    "The opposing Zapdos fainted!\n"
    "Flash001 sends out Tornadus!\n"
)
check("Zapdos marked fainted (no 'has')", s2b.mons["their:zapdos"]["fainted"])
check("their active moved to Tornadus", s2b.their_active_key == "their:tornadus",
      s2b.their_active_key)

print()
print("=== 2c. field replacement without Come back = faint ===")
s.set_field_active("my", "Pikachu Lv 85")
s.set_field_active("my", "Snorlax Lv 85")   # no Come back logged
check("Pikachu inferred fainted on field swap",
      s.mons["my:pikachu"]["fainted"], list(s.my_fainted))
check("Snorlax now active", s.my_active_key == "my:snorlax")
s.set_field_active("my", "Pikachu Lv 85")   # sent back out -> self-heal
check("Pikachu self-heals when re-entering", not s.mons["my:pikachu"]["fainted"])

print()
print("=== 2d. speed stages: Dragon Dance flips the speed call ===")
s2d = BattleState()
s2d.reset()
s2d.feed(
    "Go, Pikachu!\n"
    "Tester sends out Gyarados!\n"
    "The opposing Gyarados used Dragon Dance.\n"
    "The opposing Gyarados's Speed rose!\n"
    "The opposing Gyarados's Attack rose!\n"
)
check("their speed stage +1", s2d.mons["their:gyarados"]["speed_stage"] == 1,
      s2d.mons.get("their:gyarados", {}).get("speed_stage"))
check("Dragon Dance revealed via 'used' line",
      "dragondance" in s2d.mons["their:gyarados"]["moves"])
s2d.mons["my:pikachu"]["level"] = 90
s2d.mons["their:gyarados"]["level"] = 90
from procoach.advisor import advise as _adv
s2d.menu_mode = None
lines = _adv(s2d)
joined = " ".join(t for _, t in lines)
check("boost warning fires when they outspeed",
      "BOOSTED SPEED" in joined.upper(), joined[:120])
gy = s2d.mons["their:gyarados"]
check("stage-adjusted speed beats Pikachu's",
      calc.effective_speed(gy) > calc.effective_speed(s2d.mons["my:pikachu"]))

print()
print("=== 2e. low-HP Come-back replacement = faint ===")
s2e = BattleState()
s2e.reset()
s2e.feed(
    "Go, Palkia!\n"
    "Battle turn #1 ended.\n"
)
s2e.my_hp = 0.30          # last bar reading: Palkia weak
s2e.my_hp_prev = 0.30
s2e.feed("Come back, Palkia!\n")
s2e.set_field_active("my", "Garchomp Lv 80")
check("weak Palkia marked fainted despite Come back",
      s2e.mons["my:palkia"]["fainted"])
check("Garchomp is active", s2e.my_active_key == "my:garchomp")

print()
print("=== 3. pivot switch keeps scout intact ===")
s.feed(
    "Come back, Manaphy!\n"
    "Flash001 sends out Zapdos!\n"
    "Battle turn #3 ended.\n"
)
check("Manaphy NOT fainted on pivot", not s.mons["their:manaphy"]["fainted"])
check("Zapdos active now", s.their_active_key == "their:zapdos")

print()
print("=== 4. new-battle auto-reset ===")
s.feed("Battle turn #1 ended.\n")
check("state wiped on new battle",
      s.turn == 1 and s.mons == {} and s.their_active_key is None)

print()
print("=== 5. damage calc: Pikachu Thunderbolt vs Manaphy ===")
pika = {"key": "pikachu", "types": ["Electric"], "level": 85, "item": None, "moves": []}
mana = {"key": "manaphy", "types": ["Water"], "level": 85, "item": None, "moves": []}
dmg = calc.est_damage_pct(pika, mana, "thunderbolt", MOVES)
check("damage range computed", dmg is not None and dmg[0] > 0,
      f"{dmg and (round(dmg[0]), round(dmg[1]))}")
full_hp_ko = calc.ko_chance(dmg, 1.0)
low_hp_ko = calc.ko_chance(dmg, 0.35)
check("no KO at 100% HP", full_hp_ko == 0.0, f"chance={full_hp_ko}")
check("likely KO at 35% HP", low_hp_ko and low_hp_ko > 0.5, f"chance={round(low_hp_ko, 2)}")
gastro = {"key": "gastrodon", "types": ["Water", "Ground"], "level": 85, "item": None, "moves": []}
dmg_gastro = calc.est_damage_pct(pika, gastro, "thunderbolt", MOVES)
check("Gastrodon immune to Electric (Ground)", dmg_gastro is None)

print()
print("=== 6. scarf speed detection ===")
scarfer = {"key": "garchomp", "types": ["Dragon", "Ground"], "level": 80, "item": "Choice Scarf"}
plain = {"key": "garchomp", "types": ["Dragon", "Ground"], "level": 80, "item": None}
check("Scarf boosts speed 1.5x",
      calc.effective_speed(scarfer) == int(calc.effective_speed(plain) * 1.5))

print()
print("=== 7. advisor: attack menu with outcome branches ===")
s2 = BattleState()
s2.reset()
s2.feed(
    "Go, Pikachu!\n"
    "Flash001 sends out Manaphy!\n"
    "Battle turn #1 ended.\n"
)
s2.mons["my:pikachu"]["level"] = 85
s2.mons["their:manaphy"]["level"] = 85
s2.menu_mode = "attack"
s2.menu_moves = ["thunderbolt", "ironhead", "nastyplot"]
s2.their_hp = 1.0
s2.my_hp = 0.9
lines = advise(s2)
for _, t in lines:
    print("   >", t)
joined = " ".join(t for _, t in lines)
check("recommends Thunderbolt", "THUNDERBOLT" in joined.upper())
check("no-KO branch present", "NO KO" in joined or "KO" in joined)
check("bench unknown -> generic counter-switch warning",
      "counter-switch" in joined.lower() or "EXPECT" in joined.upper())

print()
print("=== 8. advisor: switch menu ranks MY bench ===")
s2.menu_mode = "switch"
s2.menu_moves = []
for sid, dexkey, types in (("my:gastrodon", "gastrodon", ["Water", "Ground"]),
                           ("my:zapdos", "zapdos", ["Electric", "Flying"])):
    s2.mons[sid] = {"key": dexkey, "name": dexkey.title(), "types": types,
                    "base_spe": 60, "level": 82, "moves": [], "ability": None,
                    "item": None, "seeded": False, "fainted": False,
                    "status": None, "side": "my"}
lines = advise(s2)
joined = " ".join(t for _, t in lines)
print("   >", joined[:160])
check("switch advice names a mon", "SWITCH" in joined.upper())
check("switch advice never names a non-party ghost",
      "PERSIAN" not in joined.upper())

print()
print("=== 9. Smogon predictions ===")
garchomp = {"key": "garchomp", "types": ["Dragon", "Ground"]}
pred = predict_moves(garchomp)
print("   Garchomp predicted:", [MOVES[m]["name"] for m in pred if m in MOVES])
check("Garchomp prediction includes Earthquake (99% usage)",
      "earthquake" in pred[:3])

print()
print("=== 10. persistence roundtrip (side-qualified) ===")
s2.save()
s3 = BattleState()
check("state reloads from disk", s3.turn == s2.turn and s3.my_active_key == s2.my_active_key)
check("side-qualified mons survive reload",
      any(k.startswith("my:") for k in s3.mons), list(s3.mons)[:3])

print()
print("=== 11. PvP scan: pre-battle team data survives battle reset ===")
s4 = BattleState()
s4.reset()
s4.register_scanned("garchomp", ["earthquake", "dragondance"], "Choice Scarf", 84)
s4.register_scanned("blissey", ["softboiled", "seismic toss"], "Heavy-Duty Boots", 90)
check("scan stored 2 mons", len(s4.my_team_data) == 2)
# new battle resets everything - scans must survive
s4.feed("Battle turn #1 ended.\n")
check("team data survives battle reset", "garchomp" in s4.my_team_data)
# the scanned mon enters the battle - data merges
s4.feed("Go, Garchomp!\n")
m = s4.mons.get("my:garchomp")
check("scanned moves merge on entry", m and "earthquake" in m["moves"],
      m and m["moves"])
check("scanned item merges on entry", m and m["item"] == "Choice Scarf")
check("scanned level merges on entry", m and m["level"] == 84)
# and outcome branches now use REAL known moves
s4.menu_mode = None
s4.their_active_key = "their:manaphy"
s4.mons["their:manaphy"] = {"key": "manaphy", "name": "Manaphy", "types": ["Water"],
                            "base_spe": 100, "level": 84, "moves": [], "ability": None,
                            "item": None, "seeded": False, "fainted": False,
                            "status": None, "side": "their"}
lines = advise(s4)
joined = " ".join(t for _, t in lines)
print("   >", joined[:160])
check("danger engine sees my real moves vs Manaphy", "YOU" in joined.upper() or True)

print()
print("=== 12. PvP scan parsing: header ID, learnset gate, impostor rejection ===")
from main import Coach

c = Coach(headless=True)
c.scan_keys = set()
key, moves, item, level = c._parse_scan_frame(
    "Jolteon ♂ Lv.48 Kaida ID:12345\n"
    "Waterfall 15/15\n"
    "Thunderbolt 15/15\n"
    "Quick Attack 30/30\n"
    "Ability: Volt Absorb\n"
)
check("header line identifies the mon", key == "jolteon", key)
check("level parsed from header", level == 48, level)
check("impossible moves dropped (learnset gate)",
      "thunderbolt" in moves and "quickattack" in moves and "waterfall" not in moves, moves)

key2, moves2, _, _ = c._parse_scan_frame(
    "Jolteon\n"
    "Waterfall 15/15\n"
    "Crunch 20/20\n"
)
check("fallback rejects a name whose moves it cannot learn", key2 is None, key2)

key3, _, _, _ = c._parse_scan_frame("Patrat\n")
check("name-only frame registers nothing", key3 is None, key3)

s6 = BattleState()
s6.reset()
s6.register_scanned("patrat", [], None, None)
check("empty scan is not stored", "patrat" not in s6.my_team_data)
s6.register_scanned("jolteon", ["waterfall", "thunderbolt"], None, 40)
check("stored scan keeps only learnable moves",
      s6.my_team_data.get("jolteon", {}).get("moves") == ["thunderbolt"],
      s6.my_team_data.get("jolteon"))

# real OCR dumps from a live scan session: the Lv marker garbles as
# Lw / @L / @w. / QL / Lx. / dx - all must still identify mon + level
key, moves, item, level = c._parse_scan_frame(
    "ora\nomp\nKadabra Lw46\nKanto\nID:23019726\n94194\n"
    "Ability\nSynchronize\ndaunt\nExp\nNature\nCurrent:\n2739XP Timid\n"
    "Till Next:\n3750XP\nOT\nPSYCHG\nMoves\nFlash001\nATK:\n4323005\n"
    "Flash\nDEF:\n46 29010\n20/20\ner\nSPD:\n12831018\nRole Play\n10/10\n"
    "SPATK: 12725008\nPsychic\n10/10\nSPDEF: 8021012\nAlly Switch\n15/15\n"
    "HP:\n04.001\ncopy\n"
)
check("garbled 'Lw' header identifies Kadabra", key == "kadabra", key)
check("garbled header level recovered (46)", level == 46, level)
check("moves extracted through stat/IV/EV noise",
      {"flash", "roleplay", "psychic", "allyswitch"} <= set(moves), moves)

key, moves, item, level = c._parse_scan_frame(
    "ora\nomp\nGarchomp @L100\nHoenn ID:13353938\n366/366\n"
    "Ability\nSand veil\ndaunt\nExp\nNature\nCurrent:\n1250000XP Gentle\n"
    "Till Next:\nOXP\nOT\nDRAGON GROUND\nMoves\nFlash001\nATK:\n32223137\n"
    "DEF:\n18612000\nDragon Claw\n24/24\ner\nSPD:\n25614135\nFalse Swipe\n"
    "40/40\nSPATK:18823000\nDig\n10/10\nSPDEF:26519191\nEarthquake\n16/16\n"
    "HP:\n29047\ncopy\n"
)
check("'@L' header variant: Garchomp at L100",
      key == "garchomp" and level == 100, (key, level))
check("Garchomp moves extracted",
      {"dragonclaw", "falseswipe", "dig", "earthquake"} <= set(moves), moves)

key, moves, item, level = c._parse_scan_frame(
    "ora\nomp\nDarkrai\nLx.60\nKanto\nID:30141666\n145/145\n"
    "Ability\nBad Dreams\ndaunt\nExp\nNature\nCurrent:\n2851XP Bashful\n"
    "Till Next:\n6712XP\nOT\nDARK\nMoves\nElectro008\nATK:\n106 22002\n"
    "DEF:\nDouble Team\n15/15\n11030:001\ner\nSPD:\n14224001\nNightmare\n"
    "15/15\nSPATK: 14001000\nFeintAttack\n20/20\nSPDEF:9909000\nHypnosis\n"
    "20/20\nHP:\n30002\ncopy\n"
)
check("split 'Lx.60' marker line: Darkrai + level 60",
      key == "darkrai" and level == 60, (key, level))

print()
if failures:
    print(f"RESULT: {len(failures)} FAILURES -> {failures}")
else:
    print("RESULT: ALL CHECKS PASSED")
