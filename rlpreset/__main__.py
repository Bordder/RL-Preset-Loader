"""Start the app: python -m rlpreset (also the entry point of the .exe)."""

import faulthandler
import os
import sys

from rlpreset import store

# Crashes get written to a log next to the user's saved data. With RLPL_DEBUG=1 set, the state of
# every thread is also written every 30 seconds, for tracking down freezes in the .exe.
store.DIR.mkdir(parents=True, exist_ok=True)
_log = open(store.DIR / "debug.log", "w", encoding="utf-8")
faulthandler.enable(_log)
if os.environ.get("RLPL_DEBUG"):
    faulthandler.dump_traceback_later(30, repeat=True, file=_log)
if sys.stdout is None:  # the .exe has no console
    sys.stdout = sys.stderr = _log

from rlpreset.app import main  # noqa: E402

main()
