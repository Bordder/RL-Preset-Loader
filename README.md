# RL Preset Loader

Copies pro players' Rocket League car designs into your garage for you.

Pick the presets you want, hit add, and the app goes through the garage menus the same way you
would: it makes a new preset, names it, and sets the body, decal, wheels, boost, trail, goal
explosion, paint finishes and colours for blue and orange. You can queue up one preset or a few hundred.

> **This is not an item swapper.** It only uses items you already own.

Still being worked on. I will continue updating the presets database when I can.

## Features

- 375 pro presets from 134 players, with pictures of both cars
- One exe, nothing to install, with a quick setup that detects your platform, resolution and game settings
- Filter by player, body, decal, wheels and boost
- Scans your inventory and marks each preset as Full, Partial or Can't make
- Checks your garage first so the same preset isn't added twice
- Copies the pro's body colours as well as their items
- If you don't own the wheels, boost, trail or goal explosion in the right paint, it uses the free
  default instead (OEM, Standard boost, Classic trail, Classic goal explosion). Missing paint
  finishes become Glossy
- Skips presets whose car body or decal you don't own. If you own the decal in a different
  paint, it uses that instead, plainest first (unpainted, black, white, grey)
- Shows what got swapped after each run
- Clear all presets button, with a warning first
- Works on Steam and Epic, any 16:9 resolution
- No BakkesMod needed

## How it works

The app doesn't touch the game's files or memory. It takes screenshots of the game window, reads
the text on screen with Windows' built-in text recognition, and moves the mouse and presses keys
to click through the menus.

Because of that:

- Don't use the mouse or keyboard while it's running
- To stop it, press **Stop**, hold **F8**, or push the mouse into the top-left corner of the screen
- The game needs to be in English for now

**Adding presets never changes your existing ones.** Every pro preset goes into a new preset, and
if a pop-up shows up that the app doesn't expect, it cancels it. The only thing that deletes
presets is the Clear all presets button, and only after you type DELETE to confirm.

## Getting started

1. Download **RL-Preset-Loader.exe** from the [latest release](../../releases/latest)
2. Start Rocket League and go to the main menu
3. Run the exe and follow the setup: it detects your platform, resolution and game settings,
   you just confirm them
4. Let it scan your inventory (about 9 minutes)
5. Pick your presets and press **Add to garage**

Nothing to install. Windows 10 or 11. You can change your answers any time with the **Setup** button.

Windows may warn that the exe is from an unknown publisher, because it isn't code-signed.
Click **More info → Run anyway**, or run it from source instead (below).

### Run from source

With [Python 3](https://www.python.org/downloads/) installed, double-click `run.bat`.
To build the exe yourself: `.venv\Scripts\python -m pip install pyinstaller`, then
`.venv\Scripts\python tools\build_exe.py`.

A preset takes about 15–30 seconds, depending on how many items it changes.

## Updating the preset list

```
.venv\Scripts\python tools\import_presets.py
```

Only new or changed presets download their pictures, so updates are quick.

## Project layout

```
rlpreset/     the app
  app.py        the window and background jobs
  ui/           the page shown in the window
  garage.py     moves around the garage and equips items
  catalog.py    the preset list, filters and what you own
  store.py      your saved scan results (kept in %LOCALAPPDATA%)
  layout.py     where everything sits on screen
  screen.py     screenshots and text reading
  inputs.py     mouse and keyboard
  game.py       finds the game window, launcher and resolution
tools/        scripts to update the preset list and build the exe
assets/       app icon
data/         the preset list and pictures
docs/         notes on the garage menus
```

## Credits

Preset data and pictures come from the **RLCS Pro Preset Database** by Hodge
([YouTube](https://www.youtube.com/@Hodge_), [X](https://x.com/RLCS_CarDesigns)).

Not affiliated with Psyonix or Epic Games. Rocket League is a trademark of Psyonix LLC.
The app automates mouse and keyboard input in the garage only, so use it at your own risk.

## License

[MIT](LICENSE)

---

Built by **bordder**
