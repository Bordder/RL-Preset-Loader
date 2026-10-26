"""The app window: a web page (rlpreset/ui) shown with Windows' built-in Edge engine.

The page talks to Python through `Api` (window.pywebview.api in JavaScript). Long jobs run in a
background thread; while one runs the window shrinks to a small always-on-top progress bar.
The page asks for progress (get_progress) rather than Python pushing it: calling into the page
from the job thread can freeze in pywebview.
"""

import pathlib
import threading
import time

import bottle
import webview

from . import catalog, game, garage, inputs, store

UI_DIR = pathlib.Path(__file__).resolve().parent / "ui"
EXPECTED_ASPECT = 16 / 9
SECONDS_PER_PRESET = 25
SECONDS_PER_SCAN_ITEM = 2
SECONDS_PER_GARAGE_PRESET = 0.8  # reading the garage list, measured live
# A garage list read this recently (in this session) is trusted instead of reading it again.
GARAGE_FRESH_SECONDS = 10 * 60
FULL_SIZE = (1280, 840)
MINI_SIZE = (440, 150)
CLEAR_CONFIRM_WORD = "DELETE"

# Local web server for the page and the preset pictures. Only these two folders are served.
server = bottle.Bottle()


@server.route("/")
def _index():
    return bottle.static_file("index.html", root=str(UI_DIR))


@server.route("/ui/<name:re:[\\w.-]+>")
def _ui(name):
    return bottle.static_file(name, root=str(UI_DIR))


@server.route("/img/<name:re:[\\w-]+\\.webp>")
def _img(name):
    response = bottle.static_file(name, root=str(catalog.IMAGES_DIR))
    response.set_header("Cache-Control", "max-age=86400")
    return response


class Api:
    def __init__(self):
        self._presets, self._credit = catalog.load()
        self._by_id = {p["id"]: p for p in self._presets}
        self._window = None
        self._worker = None
        self._saved_geometry = None
        self._job = {"running": False, "id": 0}
        self._garage_read_at = None  # time.monotonic() of the last garage read this session

    # ---------- called from the page ----------

    def get_state(self):
        inventory = store.load("inventory")
        garage_list = store.load("garage") or {}
        return {
            "presets": catalog.cards(self._presets, inventory, garage_list.get("names", [])),
            "credit": self._credit,
            "inventory_checked": (inventory or {}).get("checked_at"),
            "garage_checked": garage_list.get("checked_at"),
            "game": self.game_status(),
            "busy": self.is_busy(),
            "seconds_per_preset": SECONDS_PER_PRESET,
        }

    def game_status(self):
        hwnd = game.find_window()
        if not hwnd:
            return {"found": False, "text": "Rocket League isn't running"}
        width, height = game.resolution(hwnd)
        launcher = game.detect_launcher(hwnd)
        ok_aspect = height and abs(width / height - EXPECTED_ASPECT) <= 0.02
        text = f"Game found · {width}×{height} · {(launcher or 'unknown launcher').title()}"
        if not ok_aspect:
            text += " · needs a 16:9 resolution"
        return {"found": True, "ok": bool(ok_aspect), "text": text, "launcher": launcher}

    def launch_game(self, launcher):
        if launcher not in ("steam", "epic"):
            return False
        game.launch(launcher)
        return True

    def is_busy(self):
        return bool(self._worker and self._worker.is_alive())

    def stop(self):
        inputs.request_stop()

    def get_progress(self):
        return dict(self._job)

    def start_scan(self):
        needed = catalog.needed_items(self._presets)
        count = sum(len(v) for v in needed.values())
        return self._start("Checking your inventory", count * SECONDS_PER_SCAN_ITEM + 30,
                           lambda g, progress: self._scan(g, needed, progress))

    def start_check_garage(self):
        return self._start("Checking your garage presets", 60, self._check_garage)

    def start_apply(self, ids, skip_added=True):
        chosen = [self._by_id[i] for i in ids if i in self._by_id]
        if not chosen:
            return {"ok": False, "error": "Pick at least one preset first."}
        # Similar presets one after another means more slots are already right and get skipped.
        chosen.sort(key=lambda p: [str((p["blue"].get(s) or {}).get("name")) for s in garage.ITEM_SLOTS])
        return self._start(f"Adding {len(chosen)} preset{'s' if len(chosen) > 1 else ''}",
                           self._prep_seconds(skip_added) + len(chosen) * SECONDS_PER_PRESET,
                           lambda g, progress: self._apply(g, chosen, skip_added, progress))

    def _garage_fresh(self):
        return self._garage_read_at is not None and time.monotonic() - self._garage_read_at < GARAGE_FRESH_SECONDS

    def _prep_seconds(self, skip_added):
        """Time spent before the first preset: an inventory scan if there isn't one, and the garage check."""
        seconds = 0
        if not store.load("inventory"):
            seconds += sum(len(v) for v in catalog.needed_items(self._presets).values()) * SECONDS_PER_SCAN_ITEM + 30
        if skip_added and not self._garage_fresh():
            known = len((store.load("garage") or {}).get("names", [])) or 40
            seconds += known * SECONDS_PER_GARAGE_PRESET + 5
        return round(seconds)

    def start_clear_all(self, typed):
        # The page asks the user to type the word; it's checked here too so nothing else can trigger it.
        if (typed or "").strip().upper() != CLEAR_CONFIRM_WORD:
            return {"ok": False, "error": f"Type {CLEAR_CONFIRM_WORD} to confirm."}
        return self._start("Deleting all garage presets", 120, self._clear_all)

    # ---------- jobs ----------

    def _start(self, title, estimate, job):
        if self.is_busy():
            return {"ok": False, "error": "Already working on something. Press Stop first."}
        hwnd = game.find_window()
        if not hwnd:
            return {"ok": False, "error": "Rocket League isn't running. Start it and go to the main menu."}
        inputs.clear_stop()
        self._job = {"running": True, "id": self._job["id"] + 1, "title": title, "step": title,
                     "fraction": 0.0, "seconds_left": estimate, "result": None}
        self._worker = threading.Thread(target=self._run, args=(hwnd, title, estimate, job), daemon=True)
        self._worker.start()
        return {"ok": True}

    def _run(self, hwnd, title, estimate, job):
        started = time.monotonic()
        state = {"step": title, "fraction": 0.0}

        def progress(step, fraction=None, seconds_left=None):
            state["step"] = step
            if fraction is not None:
                state["fraction"] = max(0.0, min(1.0, fraction))
            elapsed = time.monotonic() - started
            if seconds_left is not None:
                left = seconds_left
            elif state["fraction"] > 0.02:
                left = elapsed / state["fraction"] - elapsed
            else:
                left = max(estimate - elapsed, 5)
            self._job.update(step=state["step"], fraction=state["fraction"], seconds_left=round(left))

        result = {"title": title}
        self._mini(True)
        try:
            progress(title, 0)
            if not game.focus(hwnd):
                raise garage.NavigationError("Couldn't bring Rocket League to the front. Click the game, then try again.")
            g = garage.Garage(hwnd, lambda text: None, garage.Options(), store.load("inventory"))
            result.update(job(g, progress) or {})
        except inputs.Aborted as e:
            result["stopped"] = str(e)
        except garage.NavigationError as e:
            result["error"] = str(e)
        except Exception as e:  # show anything unexpected instead of dying silently
            result["error"] = f"{type(e).__name__}: {e}"
        finally:
            result["seconds"] = round(time.monotonic() - started)
            self._mini(False)
            self._job.update(running=False, result=result)

    def _scan(self, g, needed, progress):
        inventory = g.scan_inventory(needed, progress)
        inventory["checked_at"] = store.stamp()
        inventory["missing_decals"] = []  # learned again while adding presets
        store.save("inventory", inventory)
        owned = sum(len(v) for v in inventory["items"].values())
        return {"message": f"Found {owned} matching items and "
                           f"{sum(len(v) for v in inventory['finishes'].values())} paint finishes."}

    def _read_garage(self, g, progress):
        names = g.list_presets(lambda text: progress(text))
        store.save("garage", {"checked_at": store.stamp(), "names": names})
        self._garage_read_at = time.monotonic()
        return names

    def _check_garage(self, g, progress):
        names = self._read_garage(g, progress)
        return {"message": f"You have {len(names)} presets in your garage."}

    def _apply(self, g, chosen, skip_added, progress):
        if not store.load("inventory"):
            # The scan tells us which bodies are missing before any preset gets created.
            progress("Checking your inventory first", 0)
            self._scan(g, catalog.needed_items(self._presets), lambda step, f=None: progress(step))
            g.owned = {s: [tuple(i) for i in v] for s, v in store.load("inventory")["items"].items()}
        # The garage itself is the record of what's there (so presets deleted in the game count as gone).
        # A list read in the last few minutes is reused; presets added since are appended to it.
        if skip_added and not self._garage_fresh():
            progress("Checking which presets you already have", 0)
            self._read_garage(g, progress)
        garage_names = (store.load("garage") or {}).get("names", []) if skip_added else []

        report = []
        started, done_count = time.monotonic(), 0
        for number, preset in enumerate(chosen):
            name = catalog.preset_name(preset)
            entry = {"id": preset["id"], "player": preset["player"], "name": name}
            report.append(entry)
            per_preset = (time.monotonic() - started) / done_count if done_count else SECONDS_PER_PRESET
            progress(f"{number + 1} of {len(chosen)}: {preset['player']} · {name}", number / len(chosen),
                     seconds_left=round(per_preset * (len(chosen) - number)))
            if skip_added and catalog.already_added(preset, garage_names):
                entry["outcome"] = "already"
                continue
            try:
                done = g.apply(preset, name)
                done_count += 1
            except garage.PresetSkipped as e:
                entry.update(outcome="skipped", reason=str(e))
                continue
            except garage.NavigationError as e:
                if "garage may be full" in str(e):
                    entry.update(outcome="error", reason=str(e))
                    break
                entry.update(outcome="error", reason=str(e))
                g.equipped = {"blue": {}, "orange": {}}  # unsure what's equipped now
                continue
            entry.update(outcome="added", name=done["name"],
                         swaps=[r for r in done["results"] if r["outcome"] in ("default", "skipped")])
            garage_names.append(done["name"])
            self._remember(garage_names, g)
        progress("Done", 1)
        return {"report": report}

    def _remember(self, garage_names, g):
        """Save what this run learned: the new preset names, and decals found missing (the inventory
        scan can't check decals, so they're learned while adding)."""
        garage_list = store.load("garage") or {}
        store.save("garage", {"checked_at": garage_list.get("checked_at") or store.stamp(), "names": garage_names})
        inventory = store.load("inventory")
        if inventory is not None:
            missing = {tuple(d) for d in inventory.get("missing_decals", [])}
            missing |= {(name, paint) for slot, (name, paint) in g.missing if slot == "decal"}
            inventory["missing_decals"] = sorted([list(d) for d in missing], key=str)
            store.save("inventory", inventory)

    def _clear_all(self, g, progress):
        deleted = g.delete_all_presets(progress)
        self._read_garage(g, progress)
        return {"message": f"Deleted {deleted} preset{'s' if deleted != 1 else ''}."}

    # ---------- window ----------

    def _mini(self, on):
        """Shrink to a small always-on-top bar in the top-right corner of the game's screen, or restore."""
        w = self._window
        if not w:
            return
        if on:
            self._saved_geometry = (w.x, w.y, w.width, w.height)
            hwnd = game.find_window()
            left, top, right, _ = game.client_rect(hwnd) if hwnd else (0, 0, 1920, 1080)
            w.resize(*MINI_SIZE)
            w.move(right - MINI_SIZE[0] - 24, top + 24)
            w.on_top = True
        else:
            w.on_top = False
            if self._saved_geometry:
                x, y, width, height = self._saved_geometry
                w.resize(width, height)
                w.move(x, y)


def main():
    api = Api()
    api._window = webview.create_window("RL Preset Loader", server, js_api=api,
                                       width=FULL_SIZE[0], height=FULL_SIZE[1], min_size=(MINI_SIZE[0] - 20, MINI_SIZE[1] - 20),
                                       background_color="#0a1020")
    webview.start(private_mode=True)


if __name__ == "__main__":
    main()
