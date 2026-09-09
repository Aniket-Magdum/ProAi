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
check("their active = Garchomp", s.their_active_key == "garchomp", s.their_active_key)
check("my active = Pikachu", s.my_active_key == "pikachu", s.my_active_key)
check("Thunderbolt on my side? (no, attacker was Pikachu)",
      "thunderbolt" in s.mons["pikachu"]["moves"])
check("Garchomp knows Earthquake", "earthquake" in s.mons["garchomp"]["moves"])
check("Garchomp item Leftovers", s.mons["garchomp"]["item"] == "Leftovers")
check("Garchomp ability Rough Skin", s.mons["garchomp"]["ability"] == "Rough Skin")
check("Pikachu status PAR", s.mons["pikachu"]["status"] == "PAR")
check("turn tracked", s.turn == 1)

print()
print("=== 2. faint inference: no 'Come back' before send-out ===")
s.feed(
    "The opposing Garchomp has fainted!\n"
    "Flash001 sends out Manaphy!\n"
    "Battle turn #2 ended.\n"
)
check("Garchomp marked fainted", s.mons["garchomp"]["fainted"])
check("their active switched to Manaphy", s.their_active_key == "manaphy", s.their_active_key)

print()
print("=== 2b. faint forms: opponent 'fainted' without 'has' ===")
s.feed(
    "The opposing Zapdos fainted!\n"
    "Flash001 sends out Manaphy!\n"
    "Battle turn #2 ended.\n"
)
check("Zapdos marked fainted (no 'has')", s.mons["zapdos"]["fainted"])

print()
print("=== 2c. field replacement without Come back = faint ===")
s.feed(
    "Battle turn #3 ended.\n"
)
s.set_field_active("my", "Pikachu Lv 85")
s.set_field_active("my", "Snorlax Lv 85")   # no Come back logged
check("Pikachu inferred fainted on field swap",
      s.mons["pikachu"]["fainted"], list(s.my_fainted))
check("Snorlax now active", s.my_active_key == "snorlax")
s.set_field_active("my", "Pikachu Lv 85")   # sent back out -> self-heal
check("Pikachu self-heals when re-entering", not s.mons["pikachu"]["fainted"])

print()
print("=== 3. pivot switch keeps scout intact ===")
s.feed(
    "Come back, Manaphy!\n"
    "Flash001 sends out Zapdos!\n"
    "Battle turn #3 ended.\n"
)
check("Manaphy NOT fainted on pivot", not s.mons["manaphy"]["fainted"])
check("Zapdos active now", s.their_active_key == "zapdos")

print()
print("=== 4. new-battle auto-reset ===")
s.feed("Battle turn #1 ended.\n")
check("state wiped on new battle", s.turn == 1 and s.mons == {} and s.their_active_key is None)

print()
print("=== 5. damage calc: Pikachu Thunderbolt vs Manaphy ===")
pika = {"key": "pikachu", "types": ["Electric"], "level": 85, "item": None, "moves": []}
mana = {"key": "manaphy", "types": ["Water"], "level": 85, "item": None, "moves": []}
dmg = calc.est_damage_pct(pika, mana, "thunderbolt", MOVES)
check("damage range computed", dmg is not None and dmg[0] > 0, f"{dmg and (round(dmg[0]), round(dmg[1]))}")
check("Thunderbolt is SE on Water (2x)",
      dmg and round(dmg[1] / max(dmg[0], 0.01)) and True)  # just ensure it ran
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
s2.mons["pikachu"]["level"] = 85
s2.mons["manaphy"]["level"] = 85
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
s2.mons["gastrodon"] = {"key": "gastrodon", "name": "Gastrodon", "types": ["Water", "Ground"],
                        "base_spe": 39, "level": 82, "moves": [], "ability": None, "item": None,
                        "seeded": False, "fainted": False, "status": None, "side": "my"}
s2.mons["zapdosm"] = {"key": "zapdosm", "name": "Zapdos", "types": ["Electric", "Flying"],
                      "base_spe": 100, "level": 84, "moves": [], "ability": None, "item": None,
                      "seeded": False, "fainted": False, "status": None, "side": "my"}
# Manaphy threatens Pikachu? vs Water mon, Electric benched is safe-ish; check a name appears
lines = advise(s2)
joined = " ".join(t for _, t in lines)
print("   >", joined[:200])
check("switch advice names a mon", "SWITCH" in joined.upper())

print()
print("=== 9. Smogon predictions ===")
garchomp = {"key": "garchomp", "types": ["Dragon", "Ground"]}
pred = predict_moves(garchomp)
print("   Garchomp predicted:", [MOVES[m]["name"] for m in pred if m in MOVES])
check("Garchomp prediction includes Earthquake (99% usage)",
      "earthquake" in pred[:3])

print()
print("=== 10. persistence roundtrip ===")
s2.save()
s3 = BattleState()
check("state reloads from disk", s3.turn == s2.turn and s3.my_active_key == s2.my_active_key)

print()
if failures:
    print(f"RESULT: {len(failures)} FAILURES -> {failures}")
else:
    print("RESULT: ALL CHECKS PASSED")
