"""Drives the Rocket League garage: find screens, switch tabs, search items, click them."""

import pathlib
import time
from dataclasses import dataclass

from PIL import ImageChops, ImageDraw, ImageStat

from . import game, inputs, layout, screen

DEBUG_DIR = pathlib.Path(__file__).resolve().parent.parent / "debug"

# Things that only appear on one screen, used to tell where we are.
MAIN_MENU_WORDS = ["GARAGE", "SETTINGS", "PROFILE"]
GARAGE_WORDS = ["CUSTOMIZE CAR", "CREATE NEW PRESET"]
CUSTOMIZE_WORDS = ["COLLECTED", "RANDOMIZE PRESET", "PAINT FINISH"]

# Body first (decals depend on it), then left-to-right through the tab strip so the arrows
# never have to double back. Paint finishes and colours are applied when passing their tab.
ITEM_SLOTS = ["body", "decal", "wheels", "boost", "goal_explosion", "trail"]
# Slots the inventory scan checks. Decals aren't scanned: the list only shows decals for the
# body on the car, and switching body would change the user's preset.
SCANNED_SLOTS = ["body", "wheels", "boost", "goal_explosion", "trail"]


class NavigationError(Exception):
    pass


class PresetSkipped(Exception):
    """The preset can't be made (e.g. the body isn't owned), so it wasn't started."""


@dataclass
class Tile:
    name: str
    paint: str | None
    point: tuple  # click point, as screen fractions


@dataclass
class Options:
    skip_unchanged: bool = True      # new presets copy the current car, so skip slots already right
    left_click_sets_both_teams: bool = True  # tested live
    speed: float = 1.0                # bigger = slower, safer


def item_label(name, paint=None):
    return f"{paint} {name}" if paint else name


def owns(owned_items, name, paint):
    """True if the scanned list of (name, paint) pairs has this exact item and paint."""
    return any(p == paint and screen.name_score(n, name) >= 0.82 for n, p in owned_items)


class Garage:
    def __init__(self, hwnd, log=print, options=None, inventory=None):
        self.hwnd = hwnd
        self.log = log
        self.opt = options or Options()
        self.rect = game.client_rect(hwnd)
        self._frame = None
        self.where = None
        # What we know is equipped on the current preset, per team: slot -> (name, paint).
        self.equipped = {"blue": {}, "orange": {}}
        # Items found missing this session, so the next preset doesn't search for them again.
        self.missing = set()
        # From the inventory scan: slot -> [(name, paint), ...]. Slots not in it get searched for.
        self.owned = {slot: [tuple(i) for i in items] for slot, items in ((inventory or {}).get("items") or {}).items()}
        # Paint finishes the user owns, per list ("primary" / "accent").
        self.finishes = dict((inventory or {}).get("finishes") or {})

    # ---------- screen helpers ----------

    @property
    def size(self):
        return self.rect[2] - self.rect[0], self.rect[3] - self.rect[1]

    def grab(self):
        """Fresh screenshot of the game. Kept until the next grab so several reads share it."""
        self._frame = screen.capture(self.rect)
        return self._frame

    def frame(self):
        return self._frame or self.grab()

    def _box(self, region):
        w, h = self.size
        return (int(region[0] * w), int(region[1] * h), int(region[2] * w), int(region[3] * h))

    def read(self, region, **ocr_options):
        """Text lines inside region (fractions). Positions come back as fractions of the full picture."""
        img = self.frame()
        w, h = img.size
        box = self._box(region)
        words = screen.read_lines(img.crop(box), **ocr_options)
        for word in words:
            word.left = (word.left + box[0]) / w
            word.top = (word.top + box[1]) / h
            word.width /= w
            word.height /= h
        return words

    def read_now(self, region, **ocr_options):
        """Capture just this region right now and read it (faster than a full-screen grab)."""
        left, top, right, bottom = self._box(region)
        img = screen.capture((self.rect[0] + left, self.rect[1] + top, self.rect[0] + right, self.rect[1] + bottom))
        return screen.read_lines(img, **ocr_options)

    def snapshot(self, region):
        """Small grey copy of part of the screen, for spotting when it changes or settles."""
        left, top, right, bottom = self._box(region)
        img = screen.capture((self.rect[0] + left, self.rect[1] + top, self.rect[0] + right, self.rect[1] + bottom))
        return img.convert("L").resize((max(1, img.width // 4), max(1, img.height // 4)))

    def pixel(self, point):
        """Colour of the game picture at point (fractions), from the current frame."""
        img = self.frame()
        return img.getpixel((int(point[0] * img.width), int(point[1] * img.height)))[:3]

    @staticmethod
    def _differs(a, b, threshold=2.0):
        return ImageStat.Stat(ImageChops.difference(a, b)).mean[0] > threshold

    def wait_settled(self, region, before=None, min_wait=0.12, timeout=2.5):
        """Wait until region has changed from `before` (if given) and then stopped changing."""
        self.wait(min_wait)
        end = time.monotonic() + timeout * self.opt.speed
        last = self.snapshot(region)
        changed = before is None or self._differs(before, last)
        while time.monotonic() < end:
            inputs.sleep(0.04)
            now = self.snapshot(region)
            moving = self._differs(last, now, threshold=0.8)
            changed = changed or (before is not None and self._differs(before, now))
            if changed and not moving:
                break
            last = now
        self._frame = None

    def to_screen(self, point):
        return (self.rect[0] + int(point[0] * self.size[0]), self.rect[1] + int(point[1] * self.size[1]))

    def wait(self, seconds):
        inputs.sleep(seconds * self.opt.speed)

    def click(self, point, button="left", wait=0.0, allow_delete=False):
        if self.where == "garage" and not allow_delete:
            x0, y0, x1, y1 = layout.DELETE_BIN_ZONE
            if x0 <= point[0] <= x1 and y0 <= point[1] <= y1:
                raise NavigationError("Refused to click near the preset DELETE button.")
        inputs.click(*self.to_screen(point), button=button)
        self.park_mouse()
        if wait:
            self.wait(wait)
        self._frame = None

    def park_mouse(self):
        """Move the mouse off the menus so hover tooltips don't cover text we want to read."""
        inputs.move(*self.to_screen((0.55, 0.97)))

    def save_debug(self, label):
        DEBUG_DIR.mkdir(exist_ok=True)
        path = DEBUG_DIR / f"{time.strftime('%H%M%S')}_{label}.png"
        self.frame().save(path)
        return path

    # ---------- where are we ----------

    def which_screen(self):
        words = self.read(layout.MENU_REGION)
        def has(names):
            return sum(1 for n in names if screen.find_text(words, n))
        if has(CUSTOMIZE_WORDS) >= 1 and not has(GARAGE_WORDS):
            where = "customize"
        elif has(GARAGE_WORDS) >= 1:
            where = "garage"
        elif has(MAIN_MENU_WORDS) >= 2:
            where = "main_menu"
        else:
            where = "unknown"
        self.where = where
        return where, words

    def wait_for_screen(self, wanted, timeout=4.0):
        end = time.monotonic() + timeout * self.opt.speed
        while True:
            self.grab()
            where, words = self.which_screen()
            if where == wanted or time.monotonic() > end:
                return where, words
            inputs.sleep(0.15)

    def go_to_garage(self):
        for _ in range(4):
            self.grab()
            where, words = self.which_screen()
            if where == "garage":
                return words
            if where == "main_menu":
                self.click(screen.find_text(words, "GARAGE").center)
            elif where == "customize":
                inputs.press("esc")  # same as BACK, tested live
            else:
                break
            where, words = self.wait_for_screen("garage")
            if where == "garage":
                return words
        path = self.save_debug("not_in_garage")
        raise NavigationError(
            "Couldn't find the garage. Open Rocket League's main menu (English language) and try again. "
            f"Screenshot saved: {path}")

    # ---------- garage screen ----------

    def preset_title(self):
        self._frame = None
        self.grab()
        return " ".join(w.text for w in self.read(layout.PRESET_TITLE_REGION))

    def create_preset(self, name):
        """Always work in a brand-new preset, so the user's own presets are never touched."""
        words = self.go_to_garage()
        button = screen.find_text(words, "CREATE NEW PRESET")
        if not button:
            raise NavigationError("Couldn't find CREATE NEW PRESET")
        before = self.preset_title()
        for _ in range(2):  # one retry in case the click didn't register
            title_before = self.snapshot(layout.PRESET_TITLE_REGION)
            self.click(button.center)
            self.wait_settled(layout.PRESET_TITLE_REGION, before=title_before, timeout=2.0)
            after = self.preset_title()
            if after != before and screen.normalize(after).startswith("preset"):
                break
        else:
            raise NavigationError(f"CREATE NEW PRESET didn't make a new preset (still on '{after or before}'). "
                                  "Your garage may be full: delete an old preset and try again.")
        self.log(f"Created new preset ({after.title()})")
        return self.rename_preset(name, current=after)

    def rename_preset(self, name, current):
        """Rename the preset we just created. Only ever called right after CREATE NEW PRESET,
        and only while its title is still the default 'Preset N', so a user's own preset is never renamed.
        Returns the name the preset ended up with."""
        if not screen.normalize(current).startswith("preset"):
            return current
        base = name[:layout.PRESET_NAME_MAX]
        for attempt in range(1, 10):
            suffix = "" if attempt == 1 else f" {attempt}"
            wanted = base[:layout.PRESET_NAME_MAX - len(suffix)] + suffix
            result = self._try_rename(wanted, current)
            if result == "ok":
                return wanted
            if result != "duplicate":
                return current
        self.log("  every name variant was taken, keeping the default name")
        return current

    def _try_rename(self, name, current):
        """One rename attempt. Returns 'ok', 'failed' or 'duplicate'."""
        self.click(layout.PRESET_RENAME_PENCIL)
        self.wait_settled(layout.DIALOG_REGION, min_wait=0.15, timeout=1.5)
        self.grab()
        dialog = self.read(layout.DIALOG_REGION)
        if not screen.find_text(dialog, "RENAME PRESET"):
            # Never confirm anything we don't recognise (e.g. a delete prompt): cancel it.
            cancel = screen.find_text(dialog, "CANCEL")
            if cancel:
                self.click(cancel.center, wait=0.4)
            self.log("  couldn't open the rename box, keeping the default name")
            return "failed"
        self.click(layout.RENAME_TEXT_BOX)
        inputs.press("end")
        inputs.clear_text(len(current) + 4)
        inputs.type_text(name)
        self.wait(0.15)
        self.grab()
        ok = screen.find_text(self.read(layout.DIALOG_REGION), "OK", min_score=0.5)
        if ok:
            self.click(ok.center)
        else:
            inputs.press("enter")
        self.wait(0.4)
        self.grab()
        dialog = self.read(layout.DIALOG_REGION)
        # Only treat it as a prompt if it looks like one (the car behind can produce stray text).
        if screen.find_text(dialog, "CANCEL") or screen.find_text(dialog, "RENAME PRESET"):
            # "You already have a preset with this name." (OK / CANCEL). Never press OK on a
            # prompt like this: it could replace the user's existing preset. CANCEL keeps ours
            # as "Preset N" (tested live), then we retry with a number on the end.
            cancel = screen.find_text(dialog, "CANCEL")
            if cancel:
                self.click(cancel.center, wait=0.5)
            else:
                inputs.press("esc")
                self.wait(0.5)
            if screen.find_text(dialog, "already have a preset", min_score=0.7):
                return "duplicate"
            self.log(f"  unexpected prompt after renaming ({' '.join(w.text for w in dialog)}), cancelled it")
            return "failed"
        self.wait_settled(layout.PRESET_TITLE_REGION, min_wait=0.1, timeout=1.5)
        title = self.preset_title()
        if screen.similarity(title, name) >= 0.8:
            self.log(f"Named it '{title}'")
            return "ok"
        self.log(f"  rename may have failed: preset now shows '{title}'")
        return "failed"

    def list_presets(self, progress=None):
        """Names of every preset in the garage, read by stepping through them with the arrows.
        Ends back on the preset that was selected at the start."""
        self.go_to_garage()
        first = self.preset_title()
        names = [first]
        for _ in range(300):
            before = self.snapshot(layout.PRESET_TITLE_REGION)
            self.click(layout.PRESET_NEXT_ARROW)
            self.wait_settled(layout.PRESET_TITLE_REGION, before=before, min_wait=0.08, timeout=1.5)
            title = self.preset_title()
            if screen.similarity(title, first) >= 0.95:
                break
            if title == names[-1]:
                continue  # the click didn't register, try again
            names.append(title)
            if progress:
                progress(f"Reading your presets: {len(names)} so far")
        return names

    def go_to_preset(self, name, max_steps=300):
        """Step through the garage presets until the one called `name` is selected. True if found."""
        self.go_to_garage()
        first = None
        for _ in range(max_steps):
            title = self.preset_title()
            # Exact apart from spacing (the text reader sometimes drops a space): "X 2" never matches "X".
            if screen.normalize(title).replace(" ", "") == screen.normalize(name).replace(" ", ""):
                return True
            if first is None:
                first = title
            elif screen.similarity(title, first) >= 0.95:
                return False  # went all the way round
            before = self.snapshot(layout.PRESET_TITLE_REGION)
            self.click(layout.PRESET_NEXT_ARROW)
            self.wait_settled(layout.PRESET_TITLE_REGION, before=before, min_wait=0.08, timeout=1.5)
        return False

    def delete_current_preset(self):
        """Delete the selected preset through the bin button and its YES/NO prompt.
        Only presses YES on the exact 'DELETE PRESET' prompt; anything else is backed out of.
        Returns the deleted preset's name, or None."""
        title = self.preset_title()
        before = self.snapshot(layout.PRESET_TITLE_REGION)
        self.click(layout.DELETE_BIN, allow_delete=True)
        self.wait_settled(layout.DIALOG_REGION, min_wait=0.15, timeout=1.5)
        self.grab()
        dialog = self.read(layout.DIALOG_REGION)
        buttons = self.read(layout.DELETE_BUTTONS_REGION)
        yes = screen.find_text(buttons, "YES")
        is_prompt = (screen.find_text(dialog, "DELETE PRESET") and
                     screen.find_text(dialog, "delete this preset", min_score=0.7))
        if not (is_prompt and yes):
            # Not the delete prompt (e.g. "can't delete your last preset"): back out.
            no = screen.find_text(buttons, "NO") or screen.find_text(dialog, "CANCEL")
            if no:
                self.click(no.center, wait=0.4)
            else:
                inputs.press("esc")
                self.wait(0.4)
            self.log(f"No delete prompt for '{title}': {' '.join(w.text for w in dialog) or 'nothing showed up'}")
            return None
        self.click(yes.center)
        self.wait_settled(layout.PRESET_TITLE_REGION, before=before, min_wait=0.15, timeout=2.5)
        if self.preset_title() == title:
            self.log(f"'{title}' is still there")
            return None
        self.log(f"Deleted '{title}'")
        return title

    def delete_all_presets(self, progress=None):
        """Deletes every preset in the garage. Only called from the 'Clear all presets' button,
        after the user confirmed it. Stops at anything it doesn't recognise. Returns how many went."""
        total = len(self.list_presets(progress))
        deleted = 0
        for _ in range(total):
            if not self.delete_current_preset():
                break
            deleted += 1
            if progress:
                progress(f"Deleting presets: {deleted} of {total}", deleted / total)
        return deleted

    def open_customize(self):
        words = self.go_to_garage()
        button = screen.find_text(words, "CUSTOMIZE CAR")
        if not button:
            raise NavigationError("Couldn't find CUSTOMIZE CAR")
        self.click(button.center)
        where, _ = self.wait_for_screen("customize")
        if where != "customize":
            raise NavigationError("CUSTOMIZE CAR didn't open")

    # ---------- customize screen ----------

    def current_tab(self):
        words = self.read(layout.PANEL_TITLE_REGION)
        for key, titles in layout.TABS:
            for title in titles:
                for w in words:
                    if screen.similarity(w.text, title) >= 0.8:
                        return key
        return None

    def go_to_tab(self, key):
        order = [k for k, _ in layout.TABS]
        self.grab()
        current = self.current_tab()
        for _ in range(len(order) + 4):
            if current == key:
                return
            if current is None:
                arrow = layout.TAB_RIGHT_ARROW
            else:
                arrow = layout.TAB_RIGHT_ARROW if order.index(key) > order.index(current) else layout.TAB_LEFT_ARROW
            self.click(arrow)
            # Wait for the panel title to change (tested live: ~0.16s).
            end = time.monotonic() + 1.5 * self.opt.speed
            previous = current
            while time.monotonic() < end:
                inputs.sleep(0.05)
                self.grab()
                current = self.current_tab()
                if current and current != previous:
                    break
        path = self.save_debug(f"tab_{key}")
        raise NavigationError(f"Couldn't open the {key} tab. Screenshot saved: {path}")

    def view_team(self, team):
        """Show the blue or orange car. The bottom button names the team you'll switch TO."""
        self.grab()
        words = self.read(layout.BOTTOM_BUTTONS_REGION)
        button = screen.find_text(words, f"VIEW {team.upper()} CAR")
        if button:
            self.click(button.center, wait=0.6)
        elif not screen.find_text(words, f"VIEW {'ORANGE' if team == 'blue' else 'BLUE'} CAR"):
            self.log("  couldn't find the view-team button, staying on the current team")

    def open_filters(self):
        """Make sure the filter panel (with the search box) is open. Always checked on screen:
        clicking the search box spot while the panel is closed would hit an item tile instead."""
        buttons = self.read_now(layout.FILTER_BUTTON_REGION)
        if screen.find_text(buttons, "HIDE FILTERS"):
            return
        if not screen.find_text(buttons, "SHOW FILTERS"):
            raise NavigationError("Couldn't find the SHOW FILTERS button")
        self.click(layout.FILTER_BUTTON)
        self.wait_settled(layout.SEARCH_TEXT_REGION, min_wait=0.12, timeout=1.5)
        if not screen.find_text(self.read_now(layout.FILTER_BUTTON_REGION), "HIDE FILTERS"):
            raise NavigationError("The filter panel didn't open")

    def search(self, text):
        """Type into the item search box. The filter panel stays open: the grid rows don't move,
        and the top row's names and paint badges are still readable below it (tested live)."""
        self.open_filters()
        before = self.snapshot(layout.GRID_REGION)
        clear = screen.find_text(self.read_now(layout.CLEAR_FILTERS_REGION), "CLEAR FILTERS")
        if clear:
            x0, y0 = layout.CLEAR_FILTERS_REGION[:2]
            w, h = self.size
            self.click((x0 + clear.center[0] / w, y0 + clear.center[1] / h))  # empties the search (tested live)
            self.wait(0.1)
        if text:
            self.click(layout.SEARCH_BOX)
            inputs.type_text(text)
        self.wait_settled(layout.GRID_REGION, before=before if (text or clear) else None, min_wait=0.15)

    def read_tiles(self):
        """Read each visible tile: its name, and its paint badge (read separately with a contrast
        boost, which reads coloured badges like LIME or CRIMSON far better). ~0.2s for 16 tiles."""
        paint_names = {screen.normalize(p): p for p in layout.PAINTS}

        def is_paint(text):
            hit = max(paint_names, key=lambda p: screen.similarity(text, p))
            return paint_names[hit] if screen.similarity(text, hit) >= 0.8 else None

        tiles = []
        for y in layout.GRID_ROWS_NAME_Y:
            for x in layout.GRID_COLUMNS_X:
                badge_region = (x - layout.TILE_HALF_WIDTH, y - layout.BADGE_ABOVE_NAME,
                                x + layout.TILE_HALF_WIDTH, y - layout.BADGE_BELOW_NAME)
                paint = None
                for line in self.read(badge_region, scale=4, boost_contrast=True):
                    paint = paint or is_paint(line.text)

                name_region = (x - layout.TILE_HALF_WIDTH, y - layout.TILE_TEXT_ABOVE_NAME,
                               x + layout.TILE_HALF_WIDTH, y + layout.TILE_TEXT_BELOW_NAME)
                name = " ".join(w.text for w in self.read(name_region) if not is_paint(w.text)).strip()
                if name:
                    tiles.append(Tile(name, paint, (x, y)))
        return tiles

    def result_pages(self, max_pages=6):
        """Yields (page number, tiles) for each page of search results, scrolling down between pages."""
        last = None
        for page in range(max_pages):
            self.grab()
            tiles = self.read_tiles()
            yield page, tiles
            seen = [(t.name, t.paint) for t in tiles]
            if len(tiles) < 16 or seen == last:
                return  # last page of results
            last = seen
            inputs.scroll(*self.to_screen(layout.GRID_SCROLL_POINT), -4)
            self.park_mouse()
            self.wait_settled(layout.GRID_REGION, min_wait=0.2)

    @staticmethod
    def pick_tile(tiles, name, paint):
        """The tile with this name in exactly this paint (None = unpainted). A different paint
        counts as not owned: it can look nothing like the pro's car."""
        for t in tiles:
            if t.paint == paint and screen.name_score(t.name, name) >= 0.82:
                return t
        return None

    def _record(self, team, slot, name, paint, team_only):
        teams = [team] if team_only or not self.opt.left_click_sets_both_teams else ["blue", "orange"]
        for t in teams:
            if slot == "body" and self.equipped[t].get("body") != (screen.normalize(name), paint):
                self.equipped[t].pop("decal", None)  # decals belong to a body; don't trust the old one
            self.equipped[t][slot] = (screen.normalize(name), paint)

    def click_tile(self, tile, team_only=None):
        """Left-click equips for both teams. For one team only, right-click opens a small menu
        ("Equip To Blue" / "Equip To Orange", seen live) and we pick the team from it."""
        if not team_only:
            self.click(tile.point)
            self.wait(0.15)
            return True
        self.click(tile.point, button="right")
        self.wait(0.25)
        self.grab()
        x, y = tile.point
        menu = self.read((x - 0.02, y - 0.01, x + 0.12, y + 0.09))
        choice = screen.find_text(menu, f"Equip To {team_only.title()}", min_score=0.75)
        if not choice:
            inputs.press("esc")  # close the menu
            self.wait(0.2)
            return False
        self.click(choice.center)
        self.wait(0.15)
        return True

    def find_and_click(self, name, paint, team_only=None):
        """Search for the item and click it. Returns the tile, or None if it isn't owned."""
        if screen.normalize(name) == "none":
            # "None" can't be searched for; it's always the first tile of the full list.
            self.search("")
            inputs.scroll(*self.to_screen(layout.GRID_SCROLL_POINT), 40)
            self.park_mouse()
            self.wait_settled(layout.GRID_REGION, min_wait=0.2)
            self.grab()
            tile = self.pick_tile(self.read_tiles()[:4], "None", None)
            return tile if tile and self.click_tile(tile, team_only) else None
        self.search(name)
        for _, tiles in self.result_pages():
            tile = self.pick_tile(tiles, name, paint)
            if tile:
                return tile if self.click_tile(tile, team_only) else None
        return None

    def known_missing(self, slot, name, paint):
        """True if the inventory scan says the item isn't owned (so there's no need to search)."""
        return slot in self.owned and not owns(self.owned[slot], name, paint)

    def equip(self, team, slot, item, team_only=False):
        """Make sure `item` is equipped in `slot`. If it isn't owned, the free default goes on instead.
        Returns (outcome, label of what's on the car): outcome is set / already / default / skipped."""
        name, paint = item["name"], item["paint"]
        want = (screen.normalize(name), paint)
        only = team if team_only else None
        if self.opt.skip_unchanged and self.equipped[team].get(slot) == want:
            return "already", item_label(name, paint)

        if (slot, want) not in self.missing and not self.known_missing(slot, name, paint):
            if self.find_and_click(name, paint, only):
                self._record(team, slot, name, paint, team_only)
                return "set", item_label(name, paint)
            self.missing.add((slot, want))

        default = layout.DEFAULT_ITEMS.get(slot)
        if not default or screen.normalize(default) == want[0]:
            return "skipped", None
        if self.opt.skip_unchanged and self.equipped[team].get(slot) == (screen.normalize(default), None):
            return "default", default
        if not self.find_and_click(default, None, only):
            return "skipped", None
        self._record(team, slot, default, None, team_only)
        return "default", default

    # ---------- paint finishes ----------

    def open_finish_list(self, team, part):
        self.click(layout.FINISH_BUTTONS[(team, part)])
        self.wait_settled(layout.FINISH_LIST_REGION, min_wait=0.2)
        inputs.scroll(*self.to_screen(layout.FINISH_LIST_SCROLL_POINT), 25)  # to the top
        self.park_mouse()
        self.wait_settled(layout.FINISH_LIST_REGION, min_wait=0.15)

    def finish_list_open(self):
        """The open list shows a column of different finish names; the closed tab shows at most the
        four finish buttons (seen live: all four read 'ANODIZED PEARL' when the list didn't open)."""
        self.grab()
        return len({w.text for w in self.read(layout.FINISH_LIST_REGION)}) >= 5

    def owned_finishes(self, part):
        """Scan the finish list once (primary and accent lists differ) and remember it."""
        if part not in self.finishes:
            for _ in range(3):
                # Right after switching tabs the first click can get lost, so check the list opened.
                self.open_finish_list("blue", part)
                if self.finish_list_open():
                    break
                inputs.press("esc")
                self.wait(0.5)
            else:
                raise NavigationError(f"Couldn't open the {part} paint finish list")
            names, scroll_at = [], self.to_screen(layout.FINISH_LIST_SCROLL_POINT)
            for _ in range(12):
                self.grab()
                new = [w.text for w in self.read(layout.FINISH_LIST_REGION)
                       if "COLLECTED" not in w.text and w.text not in names]
                if not new:
                    break
                names += new
                inputs.scroll(*scroll_at, -3)
                self.park_mouse()
                self.wait_settled(layout.FINISH_LIST_REGION, min_wait=0.12)
            inputs.press("esc")  # closes the list (tested live: stays on the paint finish tab)
            self.wait(0.3)
            self.finishes[part] = names
            self.log(f"  you own {len(names)} {part} finishes")
        return self.finishes[part]

    def set_finish(self, team, part, finish):
        """Returns (outcome, label) like equip(). Not owned = Glossy."""
        key = f"{part}_finish"
        owned = self.owned_finishes(part)
        match = max(owned, key=lambda n: screen.similarity(n, finish), default=None)
        outcome = "set"
        if not match or screen.similarity(match, finish) < 0.85:
            match, outcome = layout.DEFAULT_FINISH, "default"
        if self.opt.skip_unchanged and self.equipped[team].get(key) == screen.normalize(match):
            return ("already" if outcome == "set" else outcome), match

        self.open_finish_list(team, part)
        scroll_at = self.to_screen(layout.FINISH_LIST_SCROLL_POINT)
        for _ in range(10):
            self.grab()
            hit = screen.find_text(self.read(layout.FINISH_LIST_REGION), match, min_score=0.85)
            if hit:
                self.click(hit.center)
                self.wait_settled(layout.FINISH_LIST_REGION, min_wait=0.2)
                self.equipped[team][key] = screen.normalize(match)
                return outcome, match
            inputs.scroll(*scroll_at, -3)
            self.park_mouse()
            self.wait_settled(layout.FINISH_LIST_REGION, min_wait=0.12)
        inputs.press("esc")
        self.wait(0.3)
        return "skipped", None

    # ---------- body colours ----------

    def set_colour(self, team, part, cell):
        """Pick a square in the primary/accent colour grid. cell = {"col", "row"} read from the
        sheet's colour picture. Checks the swatch took the square's colour afterwards."""
        key = f"{part}_colour"
        want = (cell["col"], cell["row"])
        label = f"square {want[0] + 1},{want[1] + 1}"
        if self.opt.skip_unchanged and self.equipped[team].get(key) == want:
            return "already", label
        swatch = layout.COLOUR_SWATCHES[(team, part)]
        cell_w, cell_h = layout.COLOUR_CELL
        top = swatch[1] + layout.COLOUR_GRID_TOP_BELOW_SWATCH
        rows, cols = layout.COLOUR_GRID_ROWS, layout.COLOUR_GRID_COLUMNS[part]
        grid = (layout.COLOUR_GRID_LEFT, top, layout.COLOUR_GRID_LEFT + cols * cell_w, top + rows * cell_h)
        target = (layout.COLOUR_GRID_LEFT + (want[0] + 0.5) * cell_w, top + (want[1] + 0.5) * cell_h)

        before = self.snapshot(grid)
        self.click(swatch)
        self.wait_settled(grid, before=before, min_wait=0.15, timeout=1.5)
        self.grab()
        expected = self.pixel(target)
        self.click(target)
        self.wait_settled(grid, min_wait=0.15, timeout=1.5)
        self.grab()
        got = self.pixel(swatch)
        if sum(abs(a - b) for a, b in zip(expected, got)) > 90:
            inputs.press("esc")  # make sure no grid is left open
            self.wait(0.3)
            self.save_debug(f"colour_{team}_{part}")
            return "skipped", None
        self.equipped[team][key] = want
        return "set", label

    # ---------- whole preset ----------

    def apply(self, preset, name):
        """Build one pro preset in a new garage preset called `name`.
        Returns {"name": final preset name, "results": [{team, slot, wanted, got, outcome}, ...]}."""
        blue, orange = preset["blue"], preset["orange"]
        for team in ("blue", "orange"):
            body = preset[team].get("body")
            if body and self.known_missing("body", body["name"], body["paint"]):
                raise PresetSkipped(f"you don't own the {item_label(body['name'], body['paint'])} body")

        start = time.monotonic()
        results = []

        def note(team, slot, wanted, outcome, got):
            results.append({"team": team, "slot": slot, "wanted": wanted, "got": got, "outcome": outcome})
            self.log(f"  {team:6} {slot:15} {outcome}: {got or '-'}")

        self.log(f"Applying {preset['player']} (preset {preset['id']})")
        final_name = self.create_preset(name)
        self.open_customize()

        paint_jobs = [(team, part) for team in ("blue", "orange") for part in ("primary", "accent")
                      if preset[team].get(f"{part}_finish") or preset[team].get(f"{part}_colour")]
        for slot in ITEM_SLOTS:
            item = blue.get(slot)
            if item:
                self.go_to_tab(slot)
                team = "both" if item == orange.get(slot) else "blue"
                outcome, got = self.equip("blue", slot, item)
                note(team, slot, item_label(item["name"], item["paint"]), outcome, got)
                if slot == "body" and outcome not in ("set", "already"):
                    # Only happens without an inventory scan; the preset was already created.
                    self.go_to_garage()
                    raise PresetSkipped(f"you don't own the {item_label(item['name'], item['paint'])} body "
                                        f"(left as '{final_name}')")
            if slot == "decal" and paint_jobs:
                self.go_to_tab("paint_finish")
                for team, part in paint_jobs:
                    finish = preset[team].get(f"{part}_finish")
                    if finish:
                        outcome, got = self.set_finish(team, part, finish)
                        note(team, f"{part}_finish", finish, outcome, got)
                    colour = preset[team].get(f"{part}_colour")
                    if colour:
                        outcome, got = self.set_colour(team, part, colour)
                        note(team, f"{part}_colour", f"square {colour['col'] + 1},{colour['row'] + 1}", outcome, got)

        different = [s for s in ITEM_SLOTS if orange.get(s) and orange[s] != blue.get(s)]
        if different or not self.opt.left_click_sets_both_teams:
            self.view_team("orange")
            for slot in reversed(ITEM_SLOTS):  # walk back along the tab strip
                item = orange.get(slot)
                if not item:
                    continue
                if slot in different:
                    self.go_to_tab(slot)
                    outcome, got = self.equip("orange", slot, item, team_only=True)
                    note("orange", slot, item_label(item["name"], item["paint"]), outcome, got)
                elif not self.opt.left_click_sets_both_teams:
                    self.go_to_tab(slot)
                    outcome, got = self.equip("orange", slot, item)
                    note("orange", slot, item_label(item["name"], item["paint"]), outcome, got)
            self.view_team("blue")

        self.go_to_garage()
        swapped = sum(1 for r in results if r["outcome"] in ("default", "skipped"))
        self.log(f"Finished {preset['player']} in {time.monotonic() - start:.0f}s, {swapped} swapped")
        return {"name": final_name, "results": results}

    # ---------- inventory scan ----------

    def scan_inventory(self, needed, progress=None):
        """Check which of the needed items the user owns, by searching for each one.
        needed = {slot: [item names]}. Read-only: nothing is clicked except tabs, the search box and
        the finish lists, so the selected preset isn't changed.
        Returns {"items": {slot: [[name, paint], ...]}, "finishes": {"primary": [...], "accent": [...]}}."""
        self.open_customize()
        items = {}
        total = sum(len(v) for v in needed.values())
        done = 0
        for slot in SCANNED_SLOTS:
            names = needed.get(slot) or []
            if not names:
                continue
            self.go_to_tab(slot)
            found = set()
            for name in names:
                done += 1
                if progress:
                    progress(f"Checking your inventory: {name}", done / (total + 2))
                self.search(name)
                for _, tiles in self.result_pages():
                    found.update((t.name, t.paint) for t in tiles)
            items[slot] = sorted(found, key=lambda t: (t[0], t[1] or ""))
            self.search("")  # leave the search box empty
        self.go_to_tab("paint_finish")
        self.finishes = {}
        for i, part in enumerate(("primary", "accent")):
            if progress:
                progress(f"Checking your {part} paint finishes", (total + i + 1) / (total + 2))
            self.owned_finishes(part)
        self.go_to_garage()
        self.owned = {slot: [tuple(i) for i in v] for slot, v in items.items()}
        return {"items": {slot: [list(i) for i in v] for slot, v in items.items()}, "finishes": self.finishes}


def describe_screen(garage):
    """For the 'Check screen' button: what the app can see right now."""
    garage.grab()
    where, words = garage.which_screen()
    lines = [f"Screen: {where}", f"Text seen: {', '.join(w.text for w in words[:25])}"]
    if where == "customize":
        lines.append(f"Tab: {garage.current_tab()}")
        tiles = garage.read_tiles()
        lines.append("Tiles: " + ", ".join(f"{t.name}{' [' + t.paint + ']' if t.paint else ''}" for t in tiles))
    img = garage.frame().copy()
    draw = ImageDraw.Draw(img)
    w, h = img.size
    for word in words:
        draw.rectangle([word.left * w, word.top * h, (word.left + word.width) * w, (word.top + word.height) * h],
                       outline="lime", width=2)
    DEBUG_DIR.mkdir(exist_ok=True)
    path = DEBUG_DIR / "check_screen.png"
    img.save(path)
    lines.append(f"Saved marked-up screenshot: {path}")
    return "\n".join(lines)
