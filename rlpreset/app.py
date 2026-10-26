"""The app window: pick pro presets, press Apply, watch the log."""

import json
import pathlib
import queue
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

from . import game, garage, inputs, screen

PRESETS_PATH = pathlib.Path(__file__).resolve().parent.parent / "data" / "presets.json"
EXPECTED_ASPECT = 16 / 9


def summary(preset):
    blue = preset["blue"]
    parts = []
    for slot in ("body", "decal", "wheels"):
        item = blue.get(slot)
        if item:
            parts.append(f"{item['paint'] + ' ' if item['paint'] else ''}{item['name']}")
    return " / ".join(parts)


class App:
    def __init__(self, root):
        self.root = root
        self.messages = queue.Queue()
        self.worker = None
        data = json.loads(PRESETS_PATH.read_text(encoding="utf-8"))
        self.presets = data["presets"]
        self.credit = data["credit"]

        root.title("RL Pro Preset Loader")
        root.geometry("760x640")
        root.minsize(620, 520)

        # --- game row ---
        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Launcher:").pack(side="left")
        self.launcher = tk.StringVar(value="steam")
        ttk.Radiobutton(top, text="Steam", variable=self.launcher, value="steam").pack(side="left")
        ttk.Radiobutton(top, text="Epic Games", variable=self.launcher, value="epic").pack(side="left")
        ttk.Button(top, text="Launch game", command=self.launch).pack(side="left", padx=6)
        ttk.Button(top, text="Find game", command=self.refresh_game).pack(side="left")
        ttk.Button(top, text="Check screen", command=self.check_screen).pack(side="left", padx=6)
        self.status = ttk.Label(root, text="", padding=(8, 0), foreground="#555")
        self.status.pack(fill="x")

        # --- preset list ---
        mid = ttk.Frame(root, padding=8)
        mid.pack(fill="both", expand=True)
        search_row = ttk.Frame(mid)
        search_row.pack(fill="x")
        ttk.Label(search_row, text="Search player or item:").pack(side="left")
        self.filter_text = tk.StringVar()
        self.filter_text.trace_add("write", lambda *_: self.fill_list())
        ttk.Entry(search_row, textvariable=self.filter_text).pack(side="left", fill="x", expand=True, padx=6)

        self.tree = ttk.Treeview(mid, columns=("player", "items"), show="headings", selectmode="extended")
        self.tree.heading("player", text="Player")
        self.tree.heading("items", text="Body / Decal / Wheels")
        self.tree.column("player", width=140, stretch=False)
        self.tree.pack(fill="both", expand=True, pady=6)

        # --- options + buttons ---
        opts = ttk.Frame(root, padding=(8, 0))
        opts.pack(fill="x")
        # Every preset always goes into a brand-new garage preset, so the user's own presets are
        # never changed, renamed or deleted.
        self.default_items = tk.BooleanVar(value=True)
        self.other_paint = tk.BooleanVar(value=True)
        self.slow = tk.BooleanVar(value=False)
        ttk.Checkbutton(opts, text="Use the default item if I don't own one (e.g. Classic trail)",
                        variable=self.default_items).pack(side="left")
        ttk.Checkbutton(opts, text="Use another paint if I don't own the exact one",
                        variable=self.other_paint).pack(side="left", padx=8)
        ttk.Checkbutton(opts, text="Slow mode", variable=self.slow).pack(side="left")

        buttons = ttk.Frame(root, padding=8)
        buttons.pack(fill="x")
        self.apply_button = ttk.Button(buttons, text="Apply selected", command=self.apply_selected)
        self.apply_button.pack(side="left")
        ttk.Button(buttons, text="Select all shown",
                   command=lambda: self.tree.selection_set(self.tree.get_children())).pack(side="left", padx=6)
        ttk.Label(buttons, text="Stop any time: hold F8 or push the mouse into the top-left corner",
                  foreground="#a33").pack(side="left", padx=10)

        self.log_box = tk.Text(root, height=10, state="disabled", wrap="word")
        self.log_box.pack(fill="both", padx=8, pady=(0, 4))
        ttk.Label(root, text=f"Presets: {self.credit}", foreground="#777", padding=(8, 0, 8, 6)).pack(fill="x")

        self.fill_list()
        self.refresh_game()
        root.after(100, self.drain_messages)

    # ---------- list ----------

    def fill_list(self):
        needle = screen.normalize(self.filter_text.get())
        self.tree.delete(*self.tree.get_children())
        for index, preset in enumerate(self.presets):
            text = f"{preset['player']} {summary(preset)}"
            if needle in screen.normalize(text):
                self.tree.insert("", "end", iid=str(index), values=(preset["player"], summary(preset)))

    # ---------- game ----------

    def refresh_game(self):
        hwnd = game.find_window()
        if not hwnd:
            self.status.config(text="Rocket League not found. Start it, then press Find game.")
            return None
        width, height = game.resolution(hwnd)
        launcher = game.detect_launcher(hwnd)
        if launcher:
            self.launcher.set(launcher)
        text = f"Game found: {width}x{height}, {launcher or 'launcher unknown'}, OCR language {screen.ocr_language()}"
        if height and abs(width / height - EXPECTED_ASPECT) > 0.02:
            text += "  WARNING: only 16:9 resolutions are supported"
        self.status.config(text=text)
        return hwnd

    def launch(self):
        game.launch(self.launcher.get())
        self.log(f"Asked {self.launcher.get()} to start Rocket League. Press Find game once it's on the main menu.")

    def check_screen(self):
        hwnd = self.refresh_game()
        if hwnd:
            self.run_in_background(lambda: self.log(garage.describe_screen(garage.Garage(hwnd, self.log))))

    # ---------- apply ----------

    def apply_selected(self):
        chosen = [self.presets[int(i)] for i in self.tree.selection()]
        if not chosen:
            messagebox.showinfo("Nothing selected", "Pick one or more presets in the list first.")
            return
        hwnd = self.refresh_game()
        if not hwnd:
            return
        if len(chosen) > 1 and not messagebox.askyesno(
                "Apply presets",
                f"Add {len(chosen)} new presets to your garage? Roughly {len(chosen) * 25 // 60 + 1} minutes.\n\n"
                "Don't touch the mouse or keyboard while it runs. Hold F8 to stop."):
            return
        options = garage.Options(allow_other_paint=self.other_paint.get(),
                                 use_default_when_missing=self.default_items.get(),
                                 speed=1.6 if self.slow.get() else 1.0)
        # Similar presets one after another means more slots are already right and get skipped.
        chosen.sort(key=lambda p: [str((p["blue"].get(s) or {}).get("name")) for s in garage.ITEM_SLOTS])

        def job():
            if not game.focus(hwnd):
                self.log("Couldn't bring Rocket League to the front. Click on the game window, then try again.")
                return
            g = garage.Garage(hwnd, self.log, options)
            start, done = time.monotonic(), 0
            for number, preset in enumerate(chosen, 1):
                try:
                    g.apply(preset)
                    done += 1
                except garage.NavigationError as e:
                    if "garage may be full" in str(e):
                        raise
                    self.log(f"Problem with {preset['player']}: {e}. Moving on to the next one.")
                    g.equipped = {"blue": {}, "orange": {}}  # unsure what's equipped now
                left = (time.monotonic() - start) / number * (len(chosen) - number)
                if len(chosen) > 1:
                    self.log(f"--- {number}/{len(chosen)} done, about {left / 60:.0f} min left ---")
            self.log(f"All done: {done} of {len(chosen)} preset(s) added.")

        self.run_in_background(job)

    def run_in_background(self, job):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Busy", "Still working. Hold F8 to stop it.")
            return

        def wrapper():
            try:
                job()
            except inputs.Aborted as e:
                self.log(f"Stopped: {e}")
            except garage.NavigationError as e:
                self.log(f"Problem: {e}")
            except Exception as e:  # show anything unexpected instead of dying silently
                self.log(f"Error: {type(e).__name__}: {e}")
            finally:
                self.messages.put(("idle", None))

        self.apply_button.config(state="disabled")
        self.worker = threading.Thread(target=wrapper, daemon=True)
        self.worker.start()

    # ---------- log ----------

    def log(self, text):
        self.messages.put(("log", text))

    def drain_messages(self):
        while not self.messages.empty():
            kind, text = self.messages.get()
            if kind == "log":
                self.log_box.config(state="normal")
                self.log_box.insert("end", text + "\n")
                self.log_box.see("end")
                self.log_box.config(state="disabled")
            elif kind == "idle":
                self.apply_button.config(state="normal")
        self.root.after(100, self.drain_messages)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
