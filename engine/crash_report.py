"""Record every crash with the section (file, function, line) that caused it.

Python exceptions go to ``errors.log`` and the UI's dialog; hard crashes such as
segmentation faults go to ``crash.log`` via faulthandler and are reported at
the next start, because nothing can run after a segfault.
"""
from __future__ import annotations

import faulthandler
import logging
import os
import sys
import threading
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_crash_stream = None
_dialog = None


def section_of(frames) -> str:
    """Name the deepest frame that belongs to this project, e.g. gui/main_window.py:run_fix_silence:1234."""
    for frame in reversed(frames):
        path = os.path.abspath(frame.filename)
        if path.startswith(ROOT) and "site-packages" not in path:
            rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
            return "%s:%s:%d" % (rel, frame.name, frame.lineno)
    return "outside the application (a library)"


def _excepthook(exc_type, exc, tb):
    text = "".join(traceback.format_exception(exc_type, exc, tb))
    section = section_of(traceback.extract_tb(tb))
    logging.getLogger("crash").error("Unhandled error in %s\n%s", section, text)
    if threading.current_thread() is not threading.main_thread():
        return  # ponytail: no dialog from worker threads; the log still names the section.
    _show_dialog(section, exc_type, exc, text)


def _show_dialog(section, exc_type, exc, text):
    """Hand the error to the UI's dialog, if one was registered in install()."""
    if _dialog is None:
        return
    try:
        _dialog(section, exc_type, exc, text)
    except Exception:
        logging.getLogger("crash").exception("Could not show the error dialog")


def install(log_dir: str, show_dialog=None) -> str | None:
    """Start logging and crash capture. Returns the previous run's crash text, if any.

    show_dialog(section, exc_type, exc, text) is called on the main thread for
    unhandled errors; the engine stays free of any UI toolkit.
    """
    global _crash_stream, _dialog
    _dialog = show_dialog
    os.makedirs(log_dir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(os.path.join(log_dir, "errors.log"), encoding="utf-8"),
                  logging.StreamHandler()])
    sys.excepthook = _excepthook
    threading.excepthook = lambda args: _excepthook(args.exc_type, args.exc_value, args.exc_traceback)

    crash_path = os.path.join(log_dir, "crash.log")
    previous = None
    if os.path.isfile(crash_path) and os.path.getsize(crash_path):
        with open(crash_path, encoding="utf-8", errors="replace") as stream:
            previous = stream.read()
        os.replace(crash_path, crash_path + ".previous")
    _crash_stream = open(crash_path, "w", encoding="utf-8")
    faulthandler.enable(file=_crash_stream, all_threads=True)
    return previous


def crash_section(crash_text: str) -> str:
    """Pick the project section out of a faulthandler dump."""
    frames = []
    for line in crash_text.splitlines():
        line = line.strip()
        if line.startswith("File \""):
            # File "/path/x.py", line 12 in func
            path = line.split('"')[1]
            rest = line.split('"')[2]
            lineno = int(rest.split("line ")[1].split()[0])
            name = rest.split(" in ", 1)[1] if " in " in rest else "?"
            frames.append(traceback.FrameSummary(path, lineno, name))
    # faulthandler lists the innermost frame first; section_of expects outermost first.
    return section_of(list(reversed(frames)))
