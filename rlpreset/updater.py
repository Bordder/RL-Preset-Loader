"""Finds a newer release on GitHub and swaps the .exe for it.

Only the exe updates itself; run from source, the app just links to the release page.
Safety: the latest release is read from GitHub's API over HTTPS, the download must come from this
repo's own release files, and the file is only used if its SHA-256 matches the one GitHub lists
for it (and the one in the release notes, when they give one).
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

from . import __version__

REPO = "Bordder/RL-Preset-Loader"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
ASSET_NAME = "RL-Preset-Loader.exe"
MAX_SIZE = 200 * 1024 * 1024
HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "RL-Preset-Loader"}


class UpdateError(Exception):
    pass


def _version(text):
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (text or "").strip())
    return tuple(int(n) for n in m.groups()) if m else None


def can_install():
    """True when running as the exe (the only thing that can be swapped)."""
    return bool(getattr(sys, "frozen", False))


def _exe():
    return pathlib.Path(sys.executable)


def _old_exe():
    exe = _exe()
    return exe.with_name(f"{exe.stem}.old{exe.suffix}")


def _new_exe():
    exe = _exe()
    return exe.with_name(f"{exe.stem}.new{exe.suffix}")


def check():
    """The newest release if it's newer than this one: {"version", "url", "sha256", "size"}, else None."""
    with urllib.request.urlopen(urllib.request.Request(LATEST_URL, headers=HEADERS), timeout=8) as r:
        data = json.loads(r.read(2_000_000))
    latest = _version(data.get("tag_name"))
    if not latest or latest <= _version(__version__):
        return None
    asset = next((a for a in data.get("assets") or [] if a.get("name") == ASSET_NAME), None)
    if not asset:
        return None
    url, size = asset.get("browser_download_url") or "", asset.get("size")
    if not url.startswith(DOWNLOAD_PREFIX) or not isinstance(size, int) or not 0 < size <= MAX_SIZE:
        return None
    digest = asset.get("digest") or ""
    sha = digest[len("sha256:"):] if digest.startswith("sha256:") else None
    in_notes = re.search(r"SHA-256:\s*`([0-9a-f]{64})`", data.get("body") or "")
    if in_notes and sha and in_notes.group(1) != sha:
        return None  # the two don't agree: don't offer it
    sha = sha or (in_notes.group(1) if in_notes else None)
    if not sha or not re.fullmatch(r"[0-9a-f]{64}", sha):
        return None
    return {"version": ".".join(map(str, latest)), "url": url, "sha256": sha, "size": size}


def install(info, progress=None):
    """Download the new exe next to this one, check it, swap them and start the new one.
    The caller closes the app afterwards. Raises UpdateError if anything doesn't check out."""
    if not can_install():
        raise UpdateError("Updating only works in the exe.")
    if not info["url"].startswith(DOWNLOAD_PREFIX):
        raise UpdateError("Unexpected download address.")
    exe, new, old = _exe(), _new_exe(), _old_exe()
    sha, got = hashlib.sha256(), 0
    try:
        with urllib.request.urlopen(urllib.request.Request(info["url"], headers=HEADERS), timeout=30) as r, \
                open(new, "wb") as out:
            while chunk := r.read(256 * 1024):
                got += len(chunk)
                if got > info["size"]:
                    raise UpdateError("The download is bigger than expected.")
                sha.update(chunk)
                out.write(chunk)
                if progress:
                    progress(got / info["size"])
        if got != info["size"] or sha.hexdigest() != info["sha256"]:
            raise UpdateError("The download didn't match the release's checksum, so it wasn't used.")
    except Exception:
        new.unlink(missing_ok=True)
        raise
    # Windows lets a running exe be renamed (not deleted), so this one steps aside for the new one.
    old.unlink(missing_ok=True)
    try:
        exe.rename(old)
    except OSError as e:
        new.unlink(missing_ok=True)
        raise UpdateError(f"Couldn't replace the app file ({e.strerror}). "
                          f"Download the new version from GitHub instead.") from e
    try:
        new.rename(exe)
    except OSError as e:
        old.rename(exe)
        new.unlink(missing_ok=True)
        raise UpdateError(f"Couldn't replace the app file ({e.strerror}).") from e
    # A fresh environment so the new exe unpacks itself instead of reusing this one's files.
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    subprocess.Popen([str(exe)], env=env, cwd=str(exe.parent), close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def clean_up():
    """Remove the previous version's file left by the last update (it was still running then)."""
    if can_install():
        try:
            _old_exe().unlink(missing_ok=True)
        except OSError:
            pass  # still closing: it goes next time
