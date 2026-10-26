"""The user's own saved data: inventory scan, garage preset names, presets the app added.

Kept in %LOCALAPPDATA%\\RL Preset Loader\\ so it stays on the user's PC and out of the repo.
"""

import json
import os
import pathlib
import tempfile
import time

DIR = pathlib.Path(os.environ.get("LOCALAPPDATA") or pathlib.Path.home()) / "RL Preset Loader"


def _path(name):
    return DIR / f"{name}.json"


def load(name, default=None):
    try:
        return json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def save(name, data):
    """Write via a temp file so a crash never leaves a half-written file behind."""
    DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DIR, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, _path(name))


def stamp():
    return time.strftime("%Y-%m-%d %H:%M")
