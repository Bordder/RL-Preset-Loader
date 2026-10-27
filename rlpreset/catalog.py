"""The pro preset list as the window shows it: names, filters, and what the user can make."""

import json
import pathlib

from . import garage, layout, screen

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
PRESETS_PATH = DATA_DIR / "presets.json"
IMAGES_DIR = DATA_DIR / "images"

FILTER_SLOTS = ["body", "decal", "wheels", "boost"]


def load():
    data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
    return data["presets"], data["credit"]


def preset_name(preset):
    """Name for the new garage preset, e.g. 'SQUISHY DEFRAG' (the game allows 20 characters)."""
    decal = (preset["blue"].get("decal") or {}).get("name")
    name = f"{preset['player']} {decal}" if decal and decal != "None" else f"{preset['player']} {preset['id']}"
    return name[:layout.PRESET_NAME_MAX]


def needed_items(presets):
    """Every item name the inventory scan should look for, per slot."""
    needed = {slot: set() for slot in garage.SCANNED_SLOTS}
    for p in presets:
        for team in ("blue", "orange"):
            for slot in garage.SCANNED_SLOTS:
                item = p[team].get(slot)
                if item and screen.normalize(item["name"]) != "none":
                    needed[slot].add(item["name"])
    return {slot: sorted(names) for slot, names in needed.items() if names}


def needed_decals(presets):
    """Decals to check per body ({body name: [decal names]}): the decal list only shows decals
    that fit the body on the car."""
    needed = {}
    for p in presets:
        for team in ("blue", "orange"):
            body, decal = p[team].get("body"), p[team].get("decal")
            if body and decal and screen.normalize(decal["name"]) != "none":
                needed.setdefault(body["name"], set()).add(decal["name"])
    return {body: sorted(names) for body, names in sorted(needed.items())}


def _wanted(presets):
    """Every (name, paint) the presets use: {slot: {name: {paints}}} and {body: {decal: {paints}}}."""
    items, decals = {}, {}
    for p in presets:
        for team in ("blue", "orange"):
            for slot in garage.SCANNED_SLOTS:
                item = p[team].get(slot)
                if item and screen.normalize(item["name"]) != "none":
                    items.setdefault(slot, {}).setdefault(item["name"], set()).add(item["paint"])
            body, decal = p[team].get("body"), p[team].get("decal")
            if body and decal and screen.normalize(decal["name"]) != "none":
                decals.setdefault(body["name"], {}).setdefault(decal["name"], set()).add(decal["paint"])
    return items, decals


def still_to_check(presets, inventory):
    """What a new-items check searches for: only items the last scan didn't find in every paint
    the presets use. Items already found are kept from the last scan.
    Returns (needed, decals_needed) in the same shapes as needed_items / needed_decals."""
    items, decals = _wanted(presets)
    known_items = inventory.get("items") or {}
    known_decals = inventory.get("decals") or {}

    def missing_some(owned, name, paints):
        return any(not garage.owns(owned, name, paint) for paint in paints)

    needed = {}
    for slot, names in items.items():
        todo = sorted(n for n, paints in names.items() if missing_some(known_items.get(slot, []), n, paints))
        if todo:
            needed[slot] = todo
    decals_needed = {}
    for body, names in sorted(decals.items()):
        owned = known_decals.get(screen.normalize(body), [])
        todo = sorted(n for n, paints in names.items() if missing_some(owned, n, paints))
        if todo:
            decals_needed[body] = todo
    return needed, decals_needed


def decal_owned(inventory, body, decal):
    """True / "other paint" / False from the inventory scan's decal check, or None if that body
    wasn't checked."""
    if not decal or screen.normalize(decal["name"]) == "none":
        return True
    decals = (inventory or {}).get("decals") or {}
    key = screen.normalize(body["name"]) if body else None
    if key not in decals:
        return None
    if garage.owns(decals[key], decal["name"], decal["paint"]):
        return True
    # Owned in another paint: it gets used instead, so the preset can still be made.
    return "other paint" if any(garage.same_item(n, decal["name"]) for n, _ in decals[key]) else False


def _is_free_default(slot, item):
    default = layout.DEFAULT_ITEMS.get(slot)
    return default and item["paint"] is None and screen.normalize(item["name"]) == screen.normalize(default)


def ownership(preset, inventory):
    """How much of the preset the user owns, from the inventory scan.
    Returns {"status": full / partial / cant / unknown, "owned", "total", "missing": [labels]}."""
    if not inventory:
        return {"status": "unknown", "owned": 0, "total": 0, "missing": []}
    items = inventory.get("items") or {}
    finishes = inventory.get("finishes") or {}
    # Decals can't be scanned, but ones found missing while adding presets are remembered.
    missing_decals = {(n, p) for n, p in inventory.get("missing_decals", [])}
    checks = {}
    swappable = set()  # missing, but used in another paint
    teams = {}  # which team(s) use each checked item

    def check(team, key, ok):
        checks[key] = ok
        teams.setdefault(key, set()).add(team)

    for team in ("blue", "orange"):
        decal = preset[team].get("decal")
        owned_decal = decal_owned(inventory, preset[team].get("body"), decal)
        if owned_decal is None and decal and (screen.normalize(decal["name"]), decal["paint"]) in missing_decals:
            owned_decal = False
        if owned_decal is not None and decal and screen.normalize(decal["name"]) != "none":
            check(team, ("decal", decal["name"], decal["paint"]), owned_decal is True)
            if owned_decal == "other paint":
                swappable.add(("decal", decal["name"], decal["paint"]))
        for slot in garage.SCANNED_SLOTS:
            item = preset[team].get(slot)
            if not item or slot not in items:
                continue
            ok = _is_free_default(slot, item) or garage.owns(items[slot], item["name"], item["paint"])
            check(team, (slot, item["name"], item["paint"]), ok)
            if slot == "body" and not ok and item["paint"] and garage.owns(items[slot], item["name"], None):
                swappable.add((slot, item["name"], item["paint"]))  # the unpainted body gets used
        for part in ("primary", "accent"):
            finish = preset[team].get(f"{part}_finish")
            if finish and finishes.get(part):
                ok = any(screen.similarity(f, finish) >= 0.85 for f in finishes[part])
                check(team, (f"{part} finish", finish, None), ok)
    missing = [garage.item_label(name, paint) for (slot, name, paint), ok in checks.items() if not ok]
    owned = sum(checks.values())
    # Without its body or its decal a preset isn't really that preset, so it isn't made.
    essential_missing = any(not ok for key, ok in checks.items()
                            if key[0] in ("body", "decal") and key not in swappable)
    status = "cant" if essential_missing else "full" if owned == len(checks) else "partial"
    return {"status": status, "owned": owned, "total": len(checks), "missing": missing,
            "parts": _parts(checks, swappable, teams)}


def _parts(checks, swappable, teams):
    """Each checked item for the card's hover list: {"slot", "item", "have", "note"}.
    have is yes / swap (something close gets used) / no (the free default gets used) /
    need (the preset can't be made without it)."""
    parts = []
    for key, ok in checks.items():
        slot, name, paint = key
        if ok:
            have, note = "yes", ""
        elif key in swappable:
            have = "swap"
            note = "other paint used" if slot == "decal" else f"plain {name} used"
        elif slot in ("body", "decal"):
            have, note = "need", "can't make without it"
        else:
            default = layout.DEFAULT_FINISH if slot.endswith("finish") else layout.DEFAULT_ITEMS.get(slot)
            have, note = "no", f"{default} used" if default else "left as is"
        if len(teams.get(key, ())) == 1:
            slot = f"{slot} ({next(iter(teams[key]))})"  # blue and orange differ here
        parts.append({"slot": slot.replace("_", " "), "item": garage.item_label(name, paint),
                      "have": have, "note": note})
    order = ["body", "decal", "wheels", "boost", "trail", "goal explosion", "primary finish", "accent finish"]
    def place(p):
        base = p["slot"].split(" (")[0]
        return order.index(base) if base in order else len(order)
    parts.sort(key=place)
    return parts


def already_added(preset, garage_names):
    """True if the garage has a preset with this preset's name (from the last garage check)."""
    # Fuzzy: the garage names are read off the screen, e.g. "WAHVEY" can come back as "WAY-IVEY".
    wanted = preset_name(preset)
    return any(screen.similarity(n, wanted) >= 0.85 for n in garage_names)


def cards(presets, inventory, garage_names):
    out = []
    for p in presets:
        blue = p["blue"]
        info = {slot: (blue.get(slot) or {}).get("name") for slot in FILTER_SLOTS}
        out.append({
            "id": p["id"],
            "player": p["player"],
            "name": preset_name(p),
            **info,
            "has_blue": (IMAGES_DIR / f"{p['id']}-blue.webp").exists(),
            "has_orange": (IMAGES_DIR / f"{p['id']}-orange.webp").exists(),
            "ownership": ownership(p, inventory),
            "added": already_added(p, garage_names),
        })
    return out
