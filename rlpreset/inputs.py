"""Mouse and keyboard input through Windows SendInput. No controller or driver needed."""

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_VIRTUALDESK = 0x4000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79

VK = {"enter": 0x0D, "esc": 0x1B, "backspace": 0x08, "f8": 0x77, "end": 0x23}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


class Aborted(Exception):
    """User pressed F8 or threw the mouse into the top-left corner."""


def _send(*inputs):
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise ctypes.WinError(ctypes.get_last_error())


def _mouse(flags, dx=0, dy=0, data=0):
    inp = INPUT(type=INPUT_MOUSE)
    inp.u.mi = MOUSEINPUT(dx, dy, data & 0xFFFFFFFF, flags, 0, 0)
    return inp


def _key(vk=0, scan=0, flags=0):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return inp


def check_abort():
    """Stop if F8 is held or the mouse is in the top-left screen corner."""
    if user32.GetAsyncKeyState(VK["f8"]) & 0x8000:
        raise Aborted("F8 pressed")
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    if pt.x <= 2 and pt.y <= 2:
        raise Aborted("mouse moved to the top-left corner")


def sleep(seconds):
    """Sleep in small steps so F8 still works during waits."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        check_abort()
        time.sleep(min(0.05, max(0, end - time.monotonic())))


def move(x, y):
    check_abort()
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    vw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    vh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    ax = int((x - vx) * 65535 / max(vw - 1, 1))
    ay = int((y - vy) * 65535 / max(vh - 1, 1))
    _send(_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, ax, ay))


def click(x, y, button="left", settle=0.04, hold=0.06, after=0.06):
    # Rocket League checks where the mouse is a frame AFTER the button is released: if the mouse
    # has already moved off the button, the click is cancelled. So stay put for `after` seconds.
    # (Tested live: moving away instantly makes every click fail; waiting 0.06s works.)
    move(x - 3, y - 2)
    sleep(settle)
    move(x, y)
    sleep(settle)
    down, up = ((MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if button == "right"
                else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP))
    _send(_mouse(down))
    time.sleep(hold)
    _send(_mouse(up))
    time.sleep(after)


def scroll(x, y, notches):
    """Positive notches scroll up, negative scroll down."""
    move(x, y)
    for _ in range(abs(notches)):
        _send(_mouse(MOUSEEVENTF_WHEEL, data=120 if notches > 0 else -120))
        time.sleep(0.03)


def press(name):
    check_abort()
    vk = VK[name]
    _send(_key(vk))
    time.sleep(0.03)
    _send(_key(vk, flags=KEYEVENTF_KEYUP))


VK_SHIFT = 0x10


def type_text(text, hold=0.015, gap=0.01):
    """Type text with real key presses. Rocket League's search box ignores Unicode-typed characters
    (tested live), so only characters on the keyboard layout can be typed; others are skipped.
    Tested live: 14 characters in 0.15s all arrive."""
    for ch in text:
        check_abort()
        mapping = user32.VkKeyScanW(ord(ch))
        if mapping == -1 or mapping & 0xFF == 0xFF:
            continue
        vk, shift = mapping & 0xFF, mapping & 0x100
        if shift:
            _send(_key(VK_SHIFT))
        _send(_key(vk))
        time.sleep(hold)
        _send(_key(vk, flags=KEYEVENTF_KEYUP))
        if shift:
            _send(_key(VK_SHIFT, flags=KEYEVENTF_KEYUP))
        time.sleep(gap)


def clear_text(max_chars=30):
    """Empty a text box with Backspace (the game ignores Ctrl+A, tested live)."""
    for _ in range(max_chars):
        check_abort()
        _send(_key(VK["backspace"]))
        time.sleep(0.01)
        _send(_key(VK["backspace"], flags=KEYEVENTF_KEYUP))
        time.sleep(0.01)
