import json

ls = json.load(open("data/learnsets.json"))
checks = {
    "kadabra": ["flash", "roleplay", "psychic", "allyswitch", "synchronoise"],
    "garchomp": ["dragonclaw", "falseswipe", "dig", "earthquake"],
    "darkrai": ["doubleteam", "nightmare", "feintattack", "hypnosis"],
    "scyther": ["xscissor", "airslash", "razorwind", "agility"],
    "anorith": ["bugbite", "ancientpower", "metalclaw", "smackdown"],
    "crawdaunt": ["cut", "waterfall", "dig", "crunch"],
}
for mon, mv in checks.items():
    learn = set(ls.get(mon, []))
    print(mon, {m: (m in learn) for m in mv})
