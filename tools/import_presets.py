"""Download Hodge's RLCS Pro Preset Database and convert it to data/presets.json.

Source: https://docs.google.com/spreadsheets/d/11LkBBLSSAbib1bGwrxEPpneBW7eOPlgRzVWCJvzJUkI
Made by Hodge (youtube.com/@Hodge_, x.com/RLCS_CarDesigns). The sheet says it is free to use;
keep this credit in anything built from it.

Usage:
    python tools/import_presets.py            # download fresh copy
    python tools/import_presets.py file.csv   # use a saved CSV instead
"""

import collections
import csv
import datetime
import io
import json
import pathlib
import sys
import urllib.request

SHEET_ID = "11LkBBLSSAbib1bGwrxEPpneBW7eOPlgRzVWCJvzJUkI"
SHEET_GID = "284327834"
# The normal /export URL needs a Google login; the gviz endpoint does not.
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}"

OUT_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "presets.json"

# Rocket League's item paint colours. Anything else in a paint column is a typo or junk.
PAINTS = [
    "Black", "Burnt Sienna", "Cobalt", "Crimson", "Forest Green", "Gold", "Grey",
    "Lime", "Orange", "Pink", "Purple", "Saffron", "Sky Blue", "Titanium White",
]
PAINT_LOOKUP = {p.lower(): p for p in PAINTS}
PAINT_LOOKUP["colbalt"] = "Cobalt"  # typo in the sheet
# Typos in the sheet's paint finish columns.
FINISH_FIXES = {"anodized peark": "Anodized Pearl", "anodzied": "Anodized"}

# (sheet item column, sheet paint column, our slot name)
ITEM_SLOTS = [
    ("Car Body", "Body Paint", "body"),
    ("Decal", "Decal Paint", "decal"),
    ("Wheels", "Wheels Paint", "wheels"),
    ("Boost", "Boost Paint", "boost"),
    ("Trail", "Trail Paint", "trail"),
    ("Goal Explosion", "GE Paint", "goal_explosion"),
]
FINISH_SLOTS = [
    ("Primary Paint Finish", "primary_finish"),
    ("Secondary Paint Finish", "accent_finish"),
]


def clean(text):
    return " ".join(text.split())


def load_rows(csv_path=None):
    if csv_path:
        text = pathlib.Path(csv_path).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(CSV_URL, timeout=30) as resp:
            text = resp.read().decode("utf-8")
    rows = list(csv.reader(io.StringIO(text)))
    header_index = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Player")
    header = [clean(h) for h in rows[header_index]]
    return [dict(zip(header, map(clean, r))) for r in rows[header_index + 1:] if r and r[0].strip()]


def build_spelling_map(rows):
    """Pick one spelling per item name, e.g. 'Laser wave III' -> 'Laser Wave III' (most common wins)."""
    counts = collections.defaultdict(collections.Counter)
    for row in rows:
        for item_col, _, _ in ITEM_SLOTS:
            name = row.get(item_col, "")
            if name:
                counts[name.lower()][name] += 1
        for col, _ in FINISH_SLOTS:
            name = row.get(col, "")
            if name:
                counts[name.lower()][name] += 1
    return {key: c.most_common(1)[0][0] for key, c in counts.items()}


def convert_team(row, spelling, warnings, preset_id):
    """One sheet row -> one team's loadout. A missing slot is None, meaning 'leave it as it is'."""
    team = {}
    for item_col, paint_col, slot in ITEM_SLOTS:
        name = row.get(item_col, "")
        if not name:
            team[slot] = None
            continue
        paint = row.get(paint_col, "")
        if paint and paint.lower() not in PAINT_LOOKUP:
            warnings.append(f"preset {preset_id}: dropped unknown {slot} paint {paint!r}")
            paint = ""
        team[slot] = {"name": spelling[name.lower()], "paint": PAINT_LOOKUP.get(paint.lower())}
    for col, slot in FINISH_SLOTS:
        name = row.get(col, "")
        team[slot] = FINISH_FIXES.get(name.lower(), spelling[name.lower()]) if name else None
    # The sheet has colour columns but they are empty, so colours are left alone for now.
    team["primary_colour"] = None
    team["accent_colour"] = None
    return team


def convert(rows):
    spelling = build_spelling_map(rows)
    by_id = collections.OrderedDict()
    for row in rows:
        by_id.setdefault(row.get("Preset ID Helper") or f"row-{len(by_id)}", []).append(row)

    presets, warnings = [], []
    for preset_id, group in by_id.items():
        # The sheet lists blue team first, then orange. One row means both teams match.
        if len(group) > 2:
            warnings.append(f"preset {preset_id}: {len(group)} rows, using the first two")
        blue_row = group[0]
        orange_row = group[1] if len(group) > 1 else group[0]
        presets.append({
            "id": preset_id,
            "player": blue_row["Player"],
            "source_post": next((r["Original Tweet"] for r in group if r.get("Original Tweet")), None),
            "blue": convert_team(blue_row, spelling, warnings, preset_id),
            "orange": convert_team(orange_row, spelling, warnings, preset_id),
        })
    return presets, warnings


def main():
    rows = load_rows(sys.argv[1] if len(sys.argv) > 1 else None)
    presets, warnings = convert(rows)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "source": f"https://docs.google.com/spreadsheets/d/{SHEET_ID}",
        "credit": "RLCS Pro Preset Database by Hodge (youtube.com/@Hodge_, x.com/RLCS_CarDesigns)",
        "imported": datetime.date.today().isoformat(),
        "presets": presets,
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    for w in warnings:
        print("warning:", w)
    players = {p["player"].lower() for p in presets}
    print(f"wrote {len(presets)} presets from {len(players)} players to {OUT_PATH}")


if __name__ == "__main__":
    main()
