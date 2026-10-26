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
STEAM_LAUNCH = "steam://rungameid/252950"
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


def installed_launchers():
    """Launchers that have Rocket League installed, found without the game running.
    Steam: its library folders (from the registry). Epic: the launcher's install manifests."""
    found = []
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            steam = pathlib.Path(winreg.QueryValueEx(key, "SteamPath")[0])
        libraries = [steam]
        vdf = steam / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            libraries += [pathlib.Path(p.replace("\\\\", "\\"))
                          for p in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore"))]
        if any((lib / "steamapps" / "common" / "rocketleague").exists() for lib in libraries):
            found.append("steam")
    except OSError:
        pass
    manifests = pathlib.Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    for item in manifests.glob("*.item") if manifests.exists() else []:
        try:
            if json.loads(item.read_text(encoding="utf-8", errors="ignore")).get("DisplayName") == "Rocket League":
                found.append("epic")
                break
        except ValueError:
            continue
    return found


def settings_resolution():
    """(width, height) from Rocket League's own settings file, or None. Works with the game closed."""
    path = (pathlib.Path(os.environ.get("USERPROFILE", "")) / "Documents" / "My Games" / "Rocket League" /
            "TAGame" / "Config" / "TASystemSettings.ini")
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
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


def focus(hwnd):
    """Bring the game to the front. Windows blocks this unless a key was just pressed, so tap Alt first."""
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.5)
    return user32.GetForegroundWindow() == hwnd
