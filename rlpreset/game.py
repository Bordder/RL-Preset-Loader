"""Find the Rocket League window, detect launcher and resolution, start the game."""

import ctypes
import json
import os
import pathlib
import re
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Make window and mouse coordinates real pixels, not Windows-scaled ones.
try:
    ctypes.WinDLL("shcore").SetProcessDpiAwareness(2)
except OSError:
    user32.SetProcessDPIAware()

GAME_EXE = "rocketleague.exe"
STEAM_APP_ID = 252950
STEAM_LAUNCH = f"steam://rungameid/{STEAM_APP_ID}"
EPIC_LAUNCH = "com.epicgames.launcher://apps/Sugar?action=launch&silent=true"

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SW_RESTORE = 9
VK_MENU = 0x12


def _exe_path(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return ""
    finally:
        kernel32.CloseHandle(handle)


def find_window():
    """Handle of the visible Rocket League game window, or None."""
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        if user32.IsWindowVisible(hwnd) and _exe_path(hwnd).lower().endswith(GAME_EXE):
            found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def detect_launcher(hwnd):
    """'steam', 'epic', or None if it can't tell from the game's install folder."""
    path = _exe_path(hwnd).lower() if hwnd else ""
    if "steamapps" in path:
        return "steam"
    if "epic games" in path or "epicgames" in path:
        return "epic"
    return None


def _steam_libraries():
    """Steam library folders (from the registry and libraryfolders.vdf), or [] without Steam."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = pathlib.Path(winreg.QueryValueEx(key, "SteamPath")[0])
    except OSError:
        return []
    libraries = [steam]
    vdf = steam / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        libraries += [pathlib.Path(p.replace("\\\\", "\\"))
                      for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore"))]
    return libraries


def steam_language():
    """The game's language as Steam has it (e.g. 'english'), or None."""
    for lib in _steam_libraries():
        manifest = lib / "steamapps" / f"appmanifest_{STEAM_APP_ID}.acf"
        if manifest.exists():
            m = re.search(r'"language"\s+"([^"]+)"', manifest.read_text(encoding="utf-8", errors="ignore"))
            if m:
                return m.group(1).lower()
    return None


def installed_launchers():
    """Launchers that have Rocket League installed, found without the game running.
    Steam: its library folders (from the registry). Epic: the launcher's install manifests."""
    found = []
    if any((lib / "steamapps" / "common" / "rocketleague").exists() for lib in _steam_libraries()):
        found.append("steam")
    manifests = pathlib.Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    for item in manifests.glob("*.item") if manifests.exists() else []:
        try:
            if json.loads(item.read_text(encoding="utf-8", errors="ignore")).get("DisplayName") == "Rocket League":
                found.append("epic")
                break
        except ValueError:
            continue
    return found


def _settings_text():
    path = (pathlib.Path(os.environ.get("USERPROFILE", "")) / "Documents" / "My Games" / "Rocket League" /
            "TAGame" / "Config" / "TASystemSettings.ini")
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def settings_resolution():
    """(width, height) from Rocket League's own settings file, or None. Works with the game closed."""
    text = _settings_text()
    if not text:
        return None
    x, y = re.search(r"^ResX=(\d+)", text, re.M), re.search(r"^ResY=(\d+)", text, re.M)
    return (int(x.group(1)), int(y.group(1))) if x and y else None


def launch(launcher):
    os.startfile(STEAM_LAUNCH if launcher == "steam" else EPIC_LAUNCH)


def client_rect(hwnd):
    """Game picture area in screen pixels: (left, top, right, bottom)."""
    rect = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(rect))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    return (origin.x, origin.y, origin.x + rect.right, origin.y + rect.bottom)


def resolution(hwnd):
    left, top, right, bottom = client_rect(hwnd)
    return right - left, bottom - top


SWP_NOACTIVATE, SWP_ASYNCWINDOWPOS = 0x0010, 0x4000
HWND_TOPMOST, HWND_NOTOPMOST = -1, -2


def own_window(title):
    """This app's own top-level window (matched by title and by belonging to this process)."""
    found = []
    pid = os.getpid()

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def callback(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            if buf.value == title:
                found.append(hwnd)
        return True

    user32.EnumWindows(callback, 0)
    return found[0] if found else None


def window_rect(hwnd):
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return rect.left, rect.top, rect.right, rect.bottom


def place_window(hwnd, x, y, width, height, on_top):
    """Move/resize a window without waiting for it and without giving it focus."""
    user32.SetWindowPos(wintypes.HWND(hwnd), wintypes.HWND(HWND_TOPMOST if on_top else HWND_NOTOPMOST),
                        int(x), int(y), int(width), int(height), SWP_NOACTIVATE | SWP_ASYNCWINDOWPOS)


def is_foreground(hwnd, settle=0.3):
    """True if hwnd is still the active window after a short wait."""
    time.sleep(settle)
    return user32.GetForegroundWindow() == hwnd


def display_mode():
    """'fullscreen', 'borderless', 'windowed' or None, from the game's settings file."""
    text = _settings_text()
    if not text:
        return None
    full = re.search(r"^Fullscreen=(\w+)", text, re.M)
    borderless = re.search(r"^Borderless=(\w+)", text, re.M)
    if borderless and borderless.group(1).lower() == "true":
        return "borderless"
    if full:
        return "fullscreen" if full.group(1).lower() == "true" else "windowed"
    return None


def focus(hwnd):
    """Bring the game to the front. Windows blocks this unless a key was just pressed, so tap Alt first."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return user32.GetForegroundWindow() == hwnd
