"""Screen capture and text reading (Windows built-in OCR, no extra installs)."""

import asyncio
import ctypes
import ctypes.wintypes as wintypes
import difflib
import re
from dataclasses import dataclass

from PIL import Image, ImageGrab, ImageOps
from winrt.windows.graphics.imaging import BitmapPixelFormat, SoftwareBitmap
from winrt.windows.media.ocr import OcrEngine
from winrt.windows.storage.streams import DataWriter

# Small text in the game reads much better when enlarged before OCR.
UPSCALE = 2


@dataclass
class Word:
    """A line of text found on screen. Box is in the coordinates of the image that was read."""
    text: str
    left: float
    top: float
    width: float
    height: float

    @property
    def center(self):
        return (self.left + self.width / 2, self.top + self.height / 2)


_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = OcrEngine.try_create_from_user_profile_languages()
        if _engine is None:
            raise RuntimeError("Windows OCR is not available. Add a language pack in Windows Settings > Time & language.")
    return _engine


def ocr_language():
    """The language Windows OCR is reading, e.g. 'en-GB'."""
    return _get_engine().recognizer_language.language_tag


def _to_bitmap(img):
    img = img.convert("RGBA")
    writer = DataWriter()
    writer.write_bytes(img.tobytes("raw", "BGRA"))
    return SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(), BitmapPixelFormat.BGRA8, img.width, img.height)


async def _recognize(bitmap):
    return await _get_engine().recognize_async(bitmap)


def read_lines(img, invert=False, scale=UPSCALE, boost_contrast=False):
    """Read text lines from a PIL image. Returns Words in the image's own pixel coordinates."""
    big = img.resize((img.width * scale, img.height * scale), Image.LANCZOS)
    if boost_contrast:
        # Coloured paint badges (LIME, CRIMSON, ...) read far better in high-contrast grey.
        big = ImageOps.autocontrast(ImageOps.grayscale(big)).convert("RGB")
    if invert:
        big = ImageOps.invert(big.convert("RGB"))
    result = asyncio.run(_recognize(_to_bitmap(big)))
    lines = []
    for line in result.lines:
        boxes = [w.bounding_rect for w in line.words]
        left = min(b.x for b in boxes)
        top = min(b.y for b in boxes)
        right = max(b.x + b.width for b in boxes)
        bottom = max(b.y + b.height for b in boxes)
        lines.append(Word(line.text, left / scale, top / scale,
                          (right - left) / scale, (bottom - top) / scale))
    return lines


class _BitmapInfoHeader(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


_user32, _gdi32 = ctypes.WinDLL("user32"), ctypes.WinDLL("gdi32")
_HANDLE = ctypes.c_void_p
for _fn, _args, _ret in [
    (_user32.GetDC, [_HANDLE], _HANDLE),
    (_user32.ReleaseDC, [_HANDLE, _HANDLE], ctypes.c_int),
    (_gdi32.CreateCompatibleDC, [_HANDLE], _HANDLE),
    (_gdi32.CreateCompatibleBitmap, [_HANDLE, ctypes.c_int, ctypes.c_int], _HANDLE),
    (_gdi32.SelectObject, [_HANDLE, _HANDLE], _HANDLE),
    (_gdi32.BitBlt, [_HANDLE] + [ctypes.c_int] * 4 + [_HANDLE, ctypes.c_int, ctypes.c_int, wintypes.DWORD], wintypes.BOOL),
    (_gdi32.GetDIBits, [_HANDLE, _HANDLE, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT], ctypes.c_int),
    (_gdi32.DeleteObject, [_HANDLE], wintypes.BOOL),
    (_gdi32.DeleteDC, [_HANDLE], wintypes.BOOL),
]:
    _fn.argtypes, _fn.restype = _args, _ret
_SRCCOPY = 0x00CC0020


def capture(rect):
    """Screenshot of (left, top, right, bottom) in screen pixels.

    Copies only that area. PIL's ImageGrab copies every monitor and then crops, which measured
    ~65 ms per small capture on a 3-monitor PC versus ~3 ms this way, and caused frame drops in the
    game while the app was polling the screen."""
    left, top, right, bottom = rect
    width, height = right - left, bottom - top
    screen_dc = _user32.GetDC(None)
    if not screen_dc or width <= 0 or height <= 0:
        return ImageGrab.grab(bbox=rect, all_screens=True)
    mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
    bitmap = _gdi32.CreateCompatibleBitmap(screen_dc, width, height)
    old = _gdi32.SelectObject(mem_dc, bitmap)
    try:
        _gdi32.BitBlt(mem_dc, 0, 0, width, height, screen_dc, left, top, _SRCCOPY)
        # Negative height = rows top to bottom; 32 bits per pixel, stored as BGRX.
        info = _BitmapInfoHeader(ctypes.sizeof(_BitmapInfoHeader), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        buffer = ctypes.create_string_buffer(width * height * 4)
        if not _gdi32.GetDIBits(mem_dc, bitmap, 0, height, buffer, ctypes.byref(info), 0):
            return ImageGrab.grab(bbox=rect, all_screens=True)
        return Image.frombuffer("RGB", (width, height), buffer, "raw", "BGRX", 0, 1)
    finally:
        _gdi32.SelectObject(mem_dc, old)
        _gdi32.DeleteObject(bitmap)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(None, screen_dc)


def normalize(text):
    """Lower-case, letters and digits only, so 'Laser Wave III' == 'LASER WAVE lll'-ish OCR output."""
    text = text.lower().replace("’", "'")
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def similarity(a, b):
    return difflib.SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def name_score(seen, target):
    """How well OCR text matches an item name, ignoring stray words around it ('ruxeb 1 Divine Intervention')."""
    seen_words, n = normalize(seen).split(), len(normalize(target).split())
    best = similarity(seen, target)
    for size in (n - 1, n, n + 1):
        for i in range(0, max(len(seen_words) - size + 1, 0)):
            if size > 0:
                best = max(best, similarity(" ".join(seen_words[i:i + size]), target))
    return best


def find_text(words, target, min_score=0.8):
    """Best Word matching target, or None. Also matches when a line contains the target."""
    best, best_score = None, 0.0
    t = normalize(target)
    for w in words:
        n = normalize(w.text)
        score = similarity(n, t)
        if t and t in n:
            score = max(score, 0.9)
        if score > best_score:
            best, best_score = w, score
    return best if best_score >= min_score else None
