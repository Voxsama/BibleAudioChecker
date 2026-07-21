"""ScriptureSound QC — desktop entry point.

Run:  python3 main.py
"""
import sys
import os

# Ensure the project root is on the path (needed for PyInstaller bundles)
if getattr(sys, 'frozen', False):
    # Running as a PyInstaller bundle
    _base = sys._MEIPASS
    sys.path.insert(0, _base)
else:
    # Running from source
    _base = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, _base)


def main():
    try:
        from gui.app import main as app_main
        app_main()
    except ImportError as e:
        if getattr(sys, "frozen", False):
            message = ("This installation is incomplete and a required component "
                       "is missing:\n\n%s\n\nReinstall ScriptureSound QC using "
                       "the complete Windows installer." % str(e))
        else:
            message = ("A required package is not installed:\n\n%s\n\n"
                       "Run: pip install -r requirements.txt" % str(e))
        _show_error("Missing dependency", message)
    except Exception as e:
        _show_error("Startup Error",
                    "ScriptureSound QC failed to start:\n\n%s" % str(e))


def _show_error(title, message):
    """Show error in a message box if possible, otherwise print to console."""
    print("\n[ERROR] %s\n%s\n" % (title, message))
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, title, message)
    except Exception:
        # If even Qt fails, just keep console open
        if sys.platform == "win32":
            input("\nPress Enter to close...")


if __name__ == "__main__":
    main()
