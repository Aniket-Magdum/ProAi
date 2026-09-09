"""Full self-test: replays real battle-log lines through the whole stack."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from procoach.advisor import advise, predict_moves
from procoach import calc
from procoach.state import BattleState, MOVES

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
    s2.mons[sid] = {"key": dexkey, "name": MOVES and dexkey.title(), "types": types,
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
if failures:
    print(f"RESULT: {len(failures)} FAILURES -> {failures}")
else:
    print("RESULT: ALL CHECKS PASSED")
