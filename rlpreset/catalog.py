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
    for team in ("blue", "orange"):
        decal = preset[team].get("decal")
        owned_decal = decal_owned(inventory, preset[team].get("body"), decal)
        if owned_decal is None and decal and (screen.normalize(decal["name"]), decal["paint"]) in missing_decals:
            owned_decal = False
        if owned_decal is not None and decal and screen.normalize(decal["name"]) != "none":
            checks[("decal", decal["name"], decal["paint"])] = owned_decal is True
            if owned_decal == "other paint":
                swappable.add(("decal", decal["name"], decal["paint"]))
        for slot in garage.SCANNED_SLOTS:
            item = preset[team].get(slot)
            if not item or slot not in items:
                continue
            ok = _is_free_default(slot, item) or garage.owns(items[slot], item["name"], item["paint"])
            checks[(slot, item["name"], item["paint"])] = ok
        for part in ("primary", "accent"):
            finish = preset[team].get(f"{part}_finish")
            if finish and finishes.get(part):
                ok = any(screen.similarity(f, finish) >= 0.85 for f in finishes[part])
                checks[(f"{part} finish", finish, None)] = ok
    missing = [garage.item_label(name, paint) for (slot, name, paint), ok in checks.items() if not ok]
    owned = sum(checks.values())
    # Without its body or its decal a preset isn't really that preset, so it isn't made.
    essential_missing = any(not ok for key, ok in checks.items()
                            if key[0] in ("body", "decal") and key not in swappable)
    status = "cant" if essential_missing else "full" if owned == len(checks) else "partial"
    return {"status": status, "owned": owned, "total": len(checks), "missing": missing}


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
