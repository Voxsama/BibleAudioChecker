"""Offscreen GUI checks; skip on engine-only test installations without Qt."""
import os
import tempfile
import time
import unittest
import wave
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication, QWidget
    from PySide6.QtTest import QTest
    from gui.ai_review import AIReviewDialog
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

from engine.config import Config


@unittest.skipUnless(QT_AVAILABLE, "PySide6 is optional for engine-only tests")
class ReviewDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "1CH_001.wav")
        with wave.open(self.path, "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(8000)
            output.writeframes(b"\x00\x00" * 8000)
        self.parent = QWidget()
        self.parent.cfg_path = os.path.join(self.temp.name, "config.json")
        self.cfg = Config(check_updates_at_startup=False)
        self.dialog = AIReviewDialog(self.path, self.cfg, "Verse 1: expected", "Test chapter", self.parent)
        self.addCleanup(self.dialog.reject)

    def finish(self):
        deadline = time.monotonic() + 10
        while self.dialog.task is not None and time.monotonic() < deadline:
            QTest.qWait(10)
        self.assertIsNone(self.dialog.task)

    def test_prepare_consent_send_and_edit_invalidation(self):
        dialog = self.dialog
        self.assertFalse(dialog.send_button.isEnabled())
        with patch("engine.ai_review._request") as network, patch("engine.loudness.ffmpeg_available", return_value=False):
            dialog.transcript.setPlainText("actual words")
            dialog.prepare()
            self.finish()
            network.assert_not_called()
        self.assertIsNotNone(dialog.payload)
        self.assertIn("SYSTEM MESSAGE", dialog.preview.toPlainText())
        self.assertFalse(dialog.send_button.isEnabled())
        dialog.consent.setChecked(True)
        self.assertTrue(dialog.send_button.isEnabled())
        dialog.model.setCurrentText("example/model:free")
        self.assertFalse(dialog.consent.isChecked())
        dialog.consent.setChecked(True)
        result = {"model": "example/model:free", "summary": "Uncertain", "limitations": "Listen first",
                  "findings": [{"severity": "warning", "explanation": "Potential mismatch", "evidence_ids": ["T1"], "suggestion": "Listen"}],
                  "advisory_only": True}
        with patch("engine.ai_review.review", return_value=result) as review:
            dialog.send()
            self.finish()
            review.assert_called_once()
        self.assertIn("ADVISORY ONLY", dialog.report.toPlainText())
        self.assertTrue(dialog.export_button.isEnabled())
        self.assertEqual(dialog.evidence_list.count(), 1)
        dialog.transcript.setPlainText("corrected words")
        self.assertIsNone(dialog.payload)
        self.assertIsNone(dialog.result)
        self.assertFalse(dialog.export_button.isEnabled())
        self.assertFalse(dialog.send_button.isEnabled())

    def test_key_session_only_preferences_persist(self):
        dialog = self.dialog
        dialog.key.setText("SESSION_ONLY_SECRET")
        dialog.model.setCurrentText("example/model:free")
        dialog.save_preferences()
        with open(self.parent.cfg_path, encoding="utf-8") as handle:
            data = handle.read()
        self.assertNotIn("SESSION_ONLY_SECRET", data)
        self.assertIn("example/model:free", data)
        dialog.reject()
        self.assertEqual(self.parent._openrouter_session_key, "SESSION_ONLY_SECRET")
        self.assertEqual(dialog.key.text(), "")

    def test_close_during_task_is_blocked_safely(self):
        dialog = self.dialog
        finished = []
        def work(progress):
            time.sleep(0.1)
            return "finished"
        dialog.start_task(work, finished.append, "test")
        dialog.reject()
        self.assertIsNotNone(dialog.task)
        self.finish()
        self.assertEqual(finished, ["finished"])
        self.assertTrue(dialog.close_button.isEnabled())

    def test_settings_preserve_ai_preferences(self):
        from gui.app import SettingsDialog
        self.cfg.ai_review_model = "example/model:free"
        self.cfg.ai_review_report_language = "Hindi"
        settings = SettingsDialog(self.cfg)
        result = settings.result_config()
        self.assertEqual(result.ai_review_model, "example/model:free")
        self.assertEqual(result.ai_review_report_language, "Hindi")
        settings.reject()

    def test_main_window_maps_exact_book_and_chapter_not_order(self):
        from types import SimpleNamespace
        from gui.app import MainWindow
        parent = SimpleNamespace(
            thread=None, cfg=self.cfg,
            _selected_chapter_path=lambda: self.path,
            script_book_chapters={
                ("Genesis", 1): {1: "Wrong book"},
                ("1 Chronicles", 1): {1: "Correct book"}},
            script_book_headings={
                ("1 Chronicles", 1): [SimpleNamespace(before_verse=1, text="Spoken heading")]},
        )
        with patch("gui.ai_review.AIReviewDialog") as dialog:
            MainWindow.open_ai_review(parent)
        self.assertIn("Verse 1: Correct book", dialog.call_args.args[2])
        self.assertIn("Heading: Spoken heading", dialog.call_args.args[2])
        self.assertNotIn("Wrong book", dialog.call_args.args[2])
        del parent.script_book_chapters[("1 Chronicles", 1)]
        with patch("gui.ai_review.AIReviewDialog") as dialog:
            MainWindow.open_ai_review(parent)
        self.assertEqual(dialog.call_args.args[2], "")
        self.assertIn("no exact", dialog.call_args.args[3])


if __name__ == "__main__":
    unittest.main()
