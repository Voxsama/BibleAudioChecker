"""
gui/app.py — ScriptureSound QC desktop application entry point (PySide6).

The window, dialogs and workers live in their own modules under gui/; this
module only builds the QApplication and re-exports the public classes.
"""

from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from engine import crash_report
from engine.config import default_config_path

from gui.theme import APP_NAME, APP_VERSION, STYLE, _load_logo_icon
from gui.main_window import MainWindow
from gui.settings_dialog import SettingsDialog
from gui.model_pack_dialog import ModelPackDialog
from gui.quick_start_dialog import QuickStartDialog

__all__ = ["APP_NAME", "APP_VERSION", "MainWindow", "SettingsDialog",
           "ModelPackDialog", "QuickStartDialog", "main"]


def main():
    previous_crash = crash_report.install(os.path.dirname(default_config_path()))
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    if sys.platform == "linux":
        app.setDesktopFileName("scripturesound-qc")
    app.setStyleSheet(STYLE)
    # Set app-wide icon (shows in dock/taskbar)
    icon = _load_logo_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    if previous_crash:
        QMessageBox.warning(
            None, "The last run crashed",
            "ScriptureSound QC stopped unexpectedly last time in section:\n%s\n\n"
            "The full crash log is beside config.json as crash.log.previous."
            % crash_report.crash_section(previous_crash))
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
