"""Download Hodge's RLCS Pro Preset Database and convert it to data/presets.json.

Source: https://docs.google.com/spreadsheets/d/11LkBBLSSAbib1bGwrxEPpneBW7eOPlgRzVWCJvzJUkI
Made by Hodge (youtube.com/@Hodge_, x.com/RLCS_CarDesigns). The sheet says it is free to use;
keep this credit in anything built from it.

Also downloads each preset's car pictures into data/images/ and reads the pro's body colours
from the sheet's colour grid pictures (the ticked square is the chosen colour).
Pictures are only downloaded for presets that are new or changed since the last run.

Usage:
    python tools/import_presets.py            # download fresh copy
    python tools/import_presets.py file.csv   # use a saved CSV instead (no pictures or colours)
"""

import collections
import concurrent.futures
import csv
import datetime
import hashlib
import html.parser
import io
import json
import pathlib
import statistics
import sys
import urllib.parse
import urllib.request

from PIL import Image

SHEET_ID = "11LkBBLSSAbib1bGwrxEPpneBW7eOPlgRzVWCJvzJUkI"
SHEET_GID = "284327834"
# The normal /export URL needs a Google login; the gviz endpoint does not.
CSV_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/gviz/tq?tqx=out:csv&gid={SHEET_GID}"
# Same sheet as a web page: the only place the pictures are linked from.
HTML_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/htmlview/sheet?headers=true&gid={SHEET_GID}"

DATA_DIR = pathlib.Path(__file__).resolve().parent.parent / "data"
OUT_PATH = DATA_DIR / "presets.json"
IMAGES_DIR = DATA_DIR / "images"
INDEX_PATH = IMAGES_DIR / "index.json"

# Only fetch pictures from Google's image host, and never anything huge.
IMAGE_HOST_SUFFIX = ".googleusercontent.com"
MAX_IMAGE_BYTES = 2_000_000
MAX_IMAGE_PIXELS = 2_000_000  # the real pictures are ~270x160
CARD_WIDTH = 270

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


class _SheetPage(html.parser.HTMLParser):
    """Collects every table row of the sheet's web page as a list of cells (text + picture links)."""

    def __init__(self):
        super().__init__()
        self.rows, self._row, self._cell = [], None, None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell = {"text": "", "imgs": []}
            self._row.append(self._cell)
        elif tag == "img" and self._cell is not None:
            src = dict(attrs).get("src")
            if src:
                self._cell["imgs"].append(src)

    def handle_endtag(self, tag):
        if tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell["text"] += data


def load_picture_links(rows):
    """Adds row["_pictures"] = {"car", "primary", "accent"} links to each CSV row.

    The web page lists the same rows in the same order as the CSV; player names are checked to be sure.
    """
    with urllib.request.urlopen(HTML_URL, timeout=60) as resp:
        page = _SheetPage()
        page.feed(resp.read().decode("utf-8"))
    # Cell 0 of each web row is the row number, so the header row is found by its "Player" cell.
    header_at = next(i for i, r in enumerate(page.rows) if len(r) > 1 and clean(r[1]["text"]) == "Player")
    col = {clean(c["text"]): i for i, c in enumerate(page.rows[header_at])}
    player = col["Player"]
    web_rows = [r for r in page.rows[header_at + 1:] if len(r) > player and clean(r[player]["text"])]
    if len(web_rows) != len(rows):
        raise RuntimeError(f"sheet page has {len(web_rows)} rows but the CSV has {len(rows)}")

    def first_img(cells, name):
        i = col.get(name)
        return cells[i]["imgs"][0] if i is not None and i < len(cells) and cells[i]["imgs"] else None

    for row, cells in zip(rows, web_rows):
        if clean(cells[player]["text"]).lower() != row["Player"].lower():
            raise RuntimeError(f"row mismatch: {row['Player']!r} vs {cells[player]['text']!r}")
        row["_pictures"] = {
            "car": first_img(cells, "Image"),
            "primary": first_img(cells, "Primary Colour"),
            "accent": first_img(cells, "Secondary Colour"),
        }


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


def split_paint_from_name(name, paint, known_names):
    """Some rows put the paint in the item name ("Standard Purple", paint empty). Split it off,
    but only when the rest is an item name seen elsewhere in the sheet, e.g. "Standard"."""
    if paint:
        return name, paint
    for p in PAINT_LOOKUP:
        if name.lower().endswith(" " + p):
            base = name[: -len(p) - 1].strip()
            if base.lower() in known_names:
                return base, p
    return name, paint


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
        name, paint = split_paint_from_name(name, paint, spelling)
        team[slot] = {"name": spelling[name.lower()], "paint": PAINT_LOOKUP.get(paint.lower())}
    for col, slot in FINISH_SLOTS:
        name = row.get(col, "")
        team[slot] = FINISH_FIXES.get(name.lower(), spelling[name.lower()]) if name else None
    # Filled in from the colour grid pictures later; None = leave the colour as it is.
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
            "_pictures": {"blue": blue_row.get("_pictures"), "orange": orange_row.get("_pictures")},
        })
    return presets, warnings


def check_image_link(url):
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or not (parts.hostname or "").endswith(IMAGE_HOST_SUFFIX):
        raise ValueError(f"refusing picture link outside {IMAGE_HOST_SUFFIX}: {parts.hostname}")


class _ImageHostOnly(urllib.request.HTTPRedirectHandler):
    """Follow redirects only while they stay on Google's image host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_image_link(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_image_opener = urllib.request.build_opener(_ImageHostOnly)


def fetch_image(url):
    """Downloads one picture from Google's image host and returns it as a PIL image."""
    check_image_link(url)
    with _image_opener.open(url, timeout=30) as resp:
        data = resp.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ValueError("picture too big")
    img = Image.open(io.BytesIO(data))
    if img.width * img.height > MAX_IMAGE_PIXELS:  # checked before decoding the pixels
        raise ValueError(f"picture too big ({img.width}x{img.height})")
    img.load()
    return img.convert("RGB")


def find_ticked_square(img):
    """Returns {"grid", "col", "row"} of the ticked square in a colour grid picture, or None if unsure.

    The grids are 7 rows high: 10 columns for the primary (team) colours, 15 for the accent colours.
    Every square is one flat colour except the ticked one, which has a white tick drawn on it.
    """
    w, h = img.size
    cols = 10 if w / h < 1.8 else 15
    rows = 7
    px = img.load()
    scores = []
    for r in range(rows):
        for c in range(cols):
            # Stay 3px inside the square to skip the grid lines and the tick box's frame.
            x0, x1 = int(c * w / cols) + 3, int((c + 1) * w / cols) - 3
            y0, y1 = int(r * h / rows) + 3, int((r + 1) * h / rows) - 3
            pts = [px[x, y] for x in range(x0, x1) for y in range(y0, y1)]
            if not pts:
                return None
            mid = [statistics.median(p[i] for p in pts) for i in range(3)]
            odd = sum(1 for p in pts if abs(p[0] - mid[0]) + abs(p[1] - mid[1]) + abs(p[2] - mid[2]) > 90)
            scores.append((odd, c, r))
    scores.sort(reverse=True)
    (best, c, r), (second, _, _) = scores[0], scores[1]
    if best < 12 or second > best / 3:
        return None
    return {"grid": "primary" if cols == 10 else "accent", "col": c, "row": r}


def preset_signature(preset):
    """Changes whenever the preset's items change, so its pictures get downloaded again."""
    data = {k: preset[k] for k in ("player", "blue", "orange")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]


def update_pictures(presets):
    """Downloads car pictures and reads colours, skipping presets that haven't changed.

    Google gives the pictures new links on every visit, so a preset counts as unchanged when its
    items are the same and its picture files are already there.
    """
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    try:
        index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        index = {}

    def work(preset):
        sig = preset_signature(preset)
        known = index.get(preset["id"])
        files_ok = all((IMAGES_DIR / f"{preset['id']}-{team}.webp").exists() for team in ("blue", "orange"))
        if known and known.get("signature") == sig and files_ok:
            return known, False
        entry = {"signature": sig, "colours": {}}
        for team in ("blue", "orange"):
            links = (preset.get("_pictures") or {}).get(team) or {}
            if links.get("car"):
                img = fetch_image(links["car"])
                if img.width > CARD_WIDTH:
                    img = img.resize((CARD_WIDTH, round(img.height * CARD_WIDTH / img.width)), Image.LANCZOS)
                img.save(IMAGES_DIR / f"{preset['id']}-{team}.webp", "WEBP", quality=82, method=6)
            for kind in ("primary", "accent"):
                if links.get(kind):
                    tick = find_ticked_square(fetch_image(links[kind]))
                    if tick and tick["grid"] == kind:
                        entry["colours"][f"{team}_{kind}"] = {"col": tick["col"], "row": tick["row"]}
        return entry, True

    fetched, failed = 0, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(work, p): p["id"] for p in presets}
        for fut in concurrent.futures.as_completed(futures):
            pid = futures[fut]
            try:
                entry, new = fut.result()
            except Exception as e:  # one bad picture shouldn't stop the whole update
                failed.append(f"{pid}: {e}")
                continue
            index[pid] = entry
            fetched += new

    # Drop pictures of presets that left the sheet.
    ids = {p["id"] for p in presets}
    for pid in [k for k in index if k not in ids]:
        del index[pid]
        for team in ("blue", "orange"):
            (IMAGES_DIR / f"{pid}-{team}.webp").unlink(missing_ok=True)

    INDEX_PATH.write_text(json.dumps(index, indent=1, sort_keys=True), encoding="utf-8")
    for preset in presets:
        colours = (index.get(preset["id"]) or {}).get("colours", {})
        for team in ("blue", "orange"):
            preset[team]["primary_colour"] = colours.get(f"{team}_primary")
            preset[team]["accent_colour"] = colours.get(f"{team}_accent")
    return fetched, failed


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    rows = load_rows(csv_path)
    if not csv_path:
        load_picture_links(rows)
    presets, warnings = convert(rows)
    if not csv_path:
        fetched, failed = update_pictures(presets)
        print(f"pictures: {fetched} presets downloaded, {len(presets) - fetched - len(failed)} unchanged")
        for f in failed:
            print("picture failed:", f)
    for p in presets:
        p.pop("_pictures", None)
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
