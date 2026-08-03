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
    if "--packaging-mms-self-test" in sys.argv:
        _run_packaging_mms_self_test()
        return
    if "--packaging-self-test" in sys.argv:
        _run_packaging_self_test()
        return
    try:
        from gui.app import main as app_main
        app_main()
    except ImportError as e:
        _show_error(
            "Missing dependency",
            "A required package is not installed:\n\n%s\n\n"
            "Fix: Run this in a terminal:\n"
            "  pip install -r requirements.txt" % str(e))
    except Exception as e:
        _show_error("Startup Error",
                    "ScriptureSound QC failed to start:\n\n%s" % str(e))


def _run_packaging_self_test():
    """Exercise runtime data that PyInstaller must include in the EXE."""
    from engine.phonetic import alignment_tokens

    assamese = alignment_tokens("আদম চেথ ইনোচ")
    devanagari = alignment_tokens("आदम छेत इनूस")
    if not assamese or assamese != devanagari:
        raise RuntimeError(
            "Packaged Indic cross-script alignment self-test failed.")
    from engine.mms_transcriber import mms_runtime_available
    if not mms_runtime_available():
        raise RuntimeError(
            "Packaged Meta MMS runtime import self-test failed.")

    output_path = os.environ.get("BAC_SELF_TEST_OUTPUT", "").strip()
    if output_path:
        with open(output_path, "w", encoding="utf-8") as stream:
            stream.write("PACKAGED_INDIC_SELF_TEST_OK\n")
            stream.write("PACKAGED_MMS_RUNTIME_IMPORT_OK\n")


def _run_packaging_mms_self_test():
    """Run a short real transcription through the frozen MMS runtime."""
    import json
    from engine.mms_transcriber import transcribe_assamese_mms

    audio_path = os.environ.get(
        "BAC_MMS_SELF_TEST_AUDIO", "").strip()
    output_path = os.environ.get(
        "BAC_SELF_TEST_OUTPUT", "").strip()
    if not audio_path or not os.path.isfile(audio_path):
        raise RuntimeError(
            "BAC_MMS_SELF_TEST_AUDIO must name a readable WAV file.")
    result = transcribe_assamese_mms(audio_path)
    if not result.ok or result.token_count < 10:
        raise RuntimeError(
            "Packaged Meta MMS transcription self-test failed: %s" %
            (result.error or "insufficient tokens"))
    if output_path:
        with open(output_path, "w", encoding="utf-8") as stream:
            json.dump({
                "ok": True,
                "words": len(result.words),
                "tokens": result.token_count,
                "confidence": result.mean_token_confidence,
                "transcript": result.transcript,
            }, stream, ensure_ascii=False, indent=2)


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
