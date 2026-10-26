# RL Preset Loader

Copies pro players' Rocket League car designs into your garage for you.

Pick the presets you want, hit apply, and the app goes through the garage menus the same way you
would: it makes a new preset, names it, and sets the body, decal, wheels, boost, trail, goal
explosion and paint finishes for blue and orange. You can queue up one preset or a few hundred.

> **This is not an item giver or an item swapper.** It can only use items that are already in
> your inventory. All it does is build presets in your garage out of what you own.

Still being worked on. There's no release yet.

## Features

- 375 pro presets from 134 players, taken from the RLCS Pro Preset Database
- Sets each item separately for blue and orange
- If you don't own an item, it uses the free default instead (Octane, OEM, Standard boost,
  Classic trail, Classic goal explosion, no decal) or skips it, your choice
- If you own the item but in a different paint, it can use that one
- If you don't own a paint finish, it uses Glossy
- Every pro preset goes into a **new** garage preset named after the player and decal
- Works on Steam and Epic, any 16:9 resolution
- No BakkesMod needed

## How it works

The app doesn't touch the game's files or memory. It takes screenshots of the game window, reads
the text on screen with Windows' built-in text recognition, and moves the mouse and presses keys
to click through the menus.

Because of that:

- Don't use the mouse or keyboard while it's running
- To stop it, hold **F8** or push the mouse into the top-left corner of the screen
- The game needs to be in English for now

**It never edits, renames or deletes your existing presets.** It only ever creates new ones, it
won't click anywhere near the delete button, and if a pop-up shows up that it doesn't expect, it
cancels it.

## Getting started

You need Windows 10 or 11 and [Python 3](https://www.python.org/downloads/).

1. Download or clone this repo
2. Start Rocket League and go to the main menu
3. Double-click `run.bat` (the first time, it installs what it needs)
4. Pick your presets and press **Apply selected**

A preset takes about 25 seconds. The first one takes a bit longer because the app checks which
paint finishes you own.

## Updating the preset list

```
.venv\Scripts\python tools\import_presets.py
```

## Project layout

```
rlpreset/   the app
  app.py      the window
  garage.py   moves around the garage and equips items
  layout.py   where everything sits on screen
  screen.py   screenshots and text reading
  inputs.py   mouse and keyboard
  game.py     finds the game window, launcher and resolution
tools/      script that downloads the preset list
data/       the preset list
docs/       notes on the garage menus
```

## Credits

Preset data comes from the **RLCS Pro Preset Database** by Hodge
([YouTube](https://www.youtube.com/@Hodge_), [X](https://x.com/RLCS_CarDesigns)).

Not affiliated with Psyonix or Epic Games. Rocket League is a trademark of Psyonix LLC.
The app automates mouse and keyboard input in the garage only, so use it at your own risk.

## License

[MIT](LICENSE)

---

Built by **bordder**
