"""One-time converter: Smogon Showdown data files -> dex.json / moves.json"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

ENTRY_RE = re.compile(r"^\t(\w+): \{", re.M)


def extract_entries(text: str) -> dict:
    """Scan a showdown .ts data file for top-level tab-indented entries."""
    starts = [(m.start(), m.group(1)) for m in ENTRY_RE.finditer(text)]
    entries = {}
    for i, (pos, key) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        entries[key] = text[pos:end]
    return entries


def grab_str(block: str, field: str):
    m = re.search(rf'\b{field}: "([^"]*)"', block)
    return m.group(1) if m else None


def grab_int(block: str, field: str):
    m = re.search(rf'\b{field}: (\d+)', block)
    return int(m.group(1)) if m else None


def grab_types(block: str):
    m = re.search(r"types?: \[([^\]]*)\]", block)
    if not m:
        return None
    return re.findall(r'"([^"]+)"', m.group(1))


def grab_base_stats(block: str):
    m = re.search(r"baseStats: \{([^}]+)\}", block)
    if not m:
        return None
    body = m.group(1)
    out = {}
    for stat in ("hp", "atk", "def", "spa", "spd", "spe"):
        sm = re.search(rf"\b{stat}: (\d+)", body)
        if sm:
            out[stat] = int(sm.group(1))
    return out or None


def grab_learnset(block: str):
    m = re.search(r"learnset: \{(.*?)\n\t\t\}", block, re.S)
    if not m:
        return None
    return re.findall(r"^\t\t\t(\w+): \[", m.group(1), re.M)


def main():
    dex_raw = extract_entries((DATA_DIR / "pokedex.ts").read_text(encoding="utf8"))
    dex = {}
    for key, block in dex_raw.items():
        name = grab_str(block, "name") or key
        types = grab_types(block)
        stats = grab_base_stats(block)
        if not (types and stats and "spe" in stats):
            continue
        dex[key] = {"name": name, "types": types, "baseStats": stats}

    moves_raw = extract_entries((DATA_DIR / "moves.ts").read_text(encoding="utf8"))
    moves = {}
    for key, block in moves_raw.items():
        name = grab_str(block, "name") or key
        mtype = grab_str(block, "type")
        category = grab_str(block, "category")
        power = grab_int(block, "basePower")
        acc = re.search(r"\baccuracy: (?:true|(\d+))", block)
        if not (mtype and category):
            continue
        moves[key] = {
            "name": name,
            "type": mtype,
            "category": category,
            "basePower": power or 0,
            "accuracy": int(acc.group(1)) if acc and acc.group(1) else 100,
        }

    learnsets_raw = extract_entries((DATA_DIR / "learnsets.ts").read_text(encoding="utf8"))
    learnsets = {}
    for key, block in learnsets_raw.items():
        lm = grab_learnset(block)
        if lm:
            learnsets[key] = lm

    items_raw = extract_entries((DATA_DIR / "items.ts").read_text(encoding="utf8"))
    items = {}
    for key, block in items_raw.items():
        name = grab_str(block, "name")
        if name:
            items[key] = {"name": name}

    (DATA_DIR / "dex.json").write_text(json.dumps(dex, indent=0), encoding="utf8")
    (DATA_DIR / "moves.json").write_text(json.dumps(moves, indent=0), encoding="utf8")
    (DATA_DIR / "learnsets.json").write_text(json.dumps(learnsets, indent=0), encoding="utf8")
    (DATA_DIR / "items.json").write_text(json.dumps(items, indent=0), encoding="utf8")
    print(
        f"dex.json: {len(dex)} species | moves.json: {len(moves)} moves | "
        f"learnsets.json: {len(learnsets)} species | items.json: {len(items)} items"
    )


if __name__ == "__main__":
    main()
