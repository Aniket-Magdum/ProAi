"""Build smogon_sets.json from pkmn/smogon usage-stats mirrors.

Merges gen9 nationaldex + ubers + ou usage stats into:
  {species_id: {"moves": {move_id: freq}, "items": {...}, "abilities": {...}}}
Species/move ids normalized (lowercase alphanumeric) to match dex.json/moves.json.
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"

SOURCES = [
    "https://raw.githubusercontent.com/pkmn/smogon/master/data/stats/gen9nationaldex.json",
    "https://raw.githubusercontent.com/pkmn/smogon/master/data/stats/gen9ubers.json",
    "https://raw.githubusercontent.com/pkmn/smogon/master/data/stats/gen9ou.json",
]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main():
    merged = {}
    for url in SOURCES:
        name = url.rsplit("/", 1)[-1]
        local = DATA_DIR / ("smogon_" + name)
        if not local.exists():
            import urllib.request

            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=120) as r:
                local.write_bytes(r.read())
        data = json.loads(local.read_text(encoding="utf8"))
        for species, info in (data.get("pokemon") or {}).items():
            k = norm(species)
            dst = merged.setdefault(k, {"moves": {}, "items": {}, "abilities": {}})
            for mv, f in (info.get("moves") or {}).items():
                mk = norm(mv)
                if mk:
                    dst["moves"][mk] = max(dst["moves"].get(mk, 0.0), float(f))
            for it, f in (info.get("items") or {}).items():
                dst["items"][norm(it)] = max(dst["items"].get(norm(it), 0.0), float(f))
            for ab, f in (info.get("abilities") or {}).items():
                dst["abilities"][norm(ab)] = max(dst["abilities"].get(norm(ab), 0.0), float(f))

    out = DATA_DIR / "smogon_sets.json"
    out.write_text(json.dumps(merged), encoding="utf8")
    sample = merged.get("garchomp", {}).get("moves", {})
    top = sorted(sample.items(), key=lambda kv: -kv[1])[:5]
    print(f"smogon_sets.json: {len(merged)} species")
    print("garchomp top moves:", top)


if __name__ == "__main__":
    main()
