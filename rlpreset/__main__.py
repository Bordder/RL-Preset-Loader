"""Start the app: python -m rlpreset (also the entry point of the .exe)."""

import faulthandler
import logging
import os
import sys
import time

from rlpreset import store

# Everything goes to debug.log next to the user's saved data, so problems can be looked into.
# Each start adds to the log (several copies can run at once); it's trimmed when it gets large.
# With RLPL_DEBUG=1 set, the state of every thread is also written every 30 seconds.
store.DIR.mkdir(parents=True, exist_ok=True)
_log_path = store.DIR / "debug.log"
try:
    if _log_path.stat().st_size > 1_000_000:
        _log_path.unlink()
except OSError:
    pass  # can't check or trim the log: keep adding to it
_log = open(_log_path, "a", encoding="utf-8", buffering=1)
_log.write(f"\n=== started {time.strftime('%Y-%m-%d %H:%M:%S')} pid {os.getpid()} ===\n")
faulthandler.enable(_log)
if os.environ.get("RLPL_DEBUG"):
    faulthandler.dump_traceback_later(30, repeat=True, file=_log)
if sys.stdout is None:  # the .exe has no console
    sys.stdout = sys.stderr = _log
logging.basicConfig(stream=_log, level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from rlpreset.app import main  # noqa: E402

main()
