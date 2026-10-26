"""Build the single-file Windows app: dist/RL Preset Loader.exe

Usage (needs PyInstaller in the venv: .venv\\Scripts\\python -m pip install pyinstaller):
    .venv\\Scripts\\python tools\\build_exe.py

Everything the app needs goes inside the .exe: Python, the packages, the window's page, the preset
list and the pictures. The user just runs it.
"""

import pathlib
import sys

import PyInstaller.__main__

ROOT = pathlib.Path(__file__).resolve().parent.parent
NAME = "RL Preset Loader"


def main():
    PyInstaller.__main__.run([
        str(ROOT / "rlpreset" / "__main__.py"),
        "--name", NAME,
        "--onefile",
        "--windowed",                      # no console window
        "--icon", str(ROOT / "assets" / "icon.ico"),
        "--add-data", f"{ROOT / 'data'};data",
        "--add-data", f"{ROOT / 'rlpreset' / 'ui'};rlpreset/ui",
        "--collect-submodules", "winrt",   # Windows text reading is split over many small packages
        "--distpath", str(ROOT / "dist"),
        "--workpath", str(ROOT / "build"),
        "--specpath", str(ROOT / "build"),
        "--noconfirm",
        "--clean",
    ])
    exe = ROOT / "dist" / f"{NAME}.exe"
    print(f"built {exe} ({exe.stat().st_size / 1e6:.0f} MB)")


if __name__ == "__main__":
    sys.exit(main())
