@echo off
rem Starts RL Preset Loader. The first run sets up Python packages; later runs only add new ones.
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || goto :nopython
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt || goto :failed
start "" .venv\Scripts\pythonw -m rlpreset.app
goto :eof

:nopython
echo Python 3 is needed: https://www.python.org/downloads/
pause
goto :eof

:failed
echo Couldn't install the packages the app needs. Check your internet connection and try again.
pause
