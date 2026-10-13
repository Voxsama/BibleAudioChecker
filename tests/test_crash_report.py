"""The crash reporter must name the project section that failed."""
import logging
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import crash_report


class CrashReportTests(unittest.TestCase):
    def test_python_exception_names_project_section(self):
        try:
            crash_report.section_of  # project frame below is the test itself
            raise ValueError("boom")
        except ValueError:
            tb = sys.exc_info()[2]
            import traceback
            section = crash_report.section_of(traceback.extract_tb(tb))
        self.assertTrue(section.startswith("tests/test_crash_report.py:test_python_exception_names_project_section:"))

    def test_segfault_dump_names_deepest_project_frame(self):
        root = crash_report.ROOT
        dump = (
            "Fatal Python error: Segmentation fault\n\n"
            "Current thread 0x1 (most recent call first):\n"
            '  File "/site-packages/PySide6/x.py", line 3 in paint\n'
            '  File "%s/gui/main_window.py", line 120 in _build_ui\n'
            '  File "%s/main.py", line 41 in main\n' % (root, root))
        self.assertEqual(crash_report.crash_section(dump), "gui/main_window.py:_build_ui:120")

    def test_excepthook_logs_without_qt(self):
        with self.assertLogs("crash", level="ERROR") as logs:
            try:
                raise RuntimeError("worker failed")
            except RuntimeError:
                crash_report._excepthook(*sys.exc_info())
        self.assertIn("Unhandled error in tests/test_crash_report.py:test_excepthook_logs_without_qt:", logs.output[0])


if __name__ == "__main__":
    unittest.main()
