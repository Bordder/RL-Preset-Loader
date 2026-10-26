@echo off
rem Starts the RL Pro Preset Loader. First run sets up Python packages.
cd /d "%~dp0"
if not exist .venv (
    python -m venv .venv || goto :nopython
    .venv\Scripts\python -m pip install -r requirements.txt || goto :eof
)
start "" .venv\Scripts\pythonw -m rlpreset.app
goto :eof

:nopython
echo Python 3 is needed: https://www.python.org/downloads/
pause
