"""
gui/app.py — Bible Audio Checker desktop application (PySide6).

A single-window app:
  * Add files or a whole folder (or drag-and-drop WAVs onto the window).
  * "Check All" runs every check on a background thread (UI stays responsive
    while ffmpeg measures loudness).
  * Results table with an overall PASS/FAIL badge + a compact per-check summary.
  * Click any row to see a full breakdown of what failed and where.
  * Settings dialog to edit loudness target/tolerance, true-peak ceiling,
    silence length/tolerance, and marker names. Saved to disk.
  * Export the report to CSV or JSON.

Run:  python3 main.py
"""

from __future__ import annotations

import os
import sys

# allow "python3 gui/app.py" as well as "python3 main.py"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QThread, Signal, QObject
from PySide6.QtGui import QColor, QAction, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QTextEdit, QSplitter,
    QHeaderView, QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QLineEdit,
    QCheckBox, QDialogButtonBox, QProgressBar, QStatusBar,
)

from engine.config import Config, default_config_path
from engine.checker import check_file, FileReport
from engine.loudness import ffmpeg_available

GREEN = QColor(198, 239, 206)
RED = QColor(255, 199, 206)
GREY = QColor(230, 230, 230)
DGREEN = QColor(0, 110, 40)
DRED = QColor(156, 0, 6)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
class CheckWorker(QObject):
    progress = Signal(int, int, str)      # done, total, filename
    file_done = Signal(object)            # FileReport
    finished = Signal()

    def __init__(self, paths, cfg: Config, do_loudness: bool):
        super().__init__()
        self.paths = paths
        self.cfg = cfg
        self.do_loudness = do_loudness
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.paths)
        for i, p in enumerate(self.paths, start=1):
            if self._stop:
                break
            self.progress.emit(i, total, os.path.basename(p))
            try:
                r = check_file(p, self.cfg, do_loudness=self.do_loudness)
            except Exception as e:
                r = FileReport(path=p, filename=os.path.basename(p),
                               error="Unexpected error: %s" % e)
            self.file_done.emit(r)
        self.finished.emit()


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Check Standards")
        self.cfg = cfg
        form = QFormLayout(self)

        self.target = self._dspin(cfg.target_lufs, -60, 0, 0.1, " LUFS")
        self.tol = self._dspin(cfg.lufs_tolerance, 0, 10, 0.1, " LU")
        self.tp = self._dspin(cfg.true_peak_max, -20, 0, 0.1, " dBTP")
        self.sil = self._dspin(cfg.silence_seconds, 0, 30, 0.1, " s")
        self.siltol = self._dspin(cfg.silence_tolerance, 0, 10, 0.1, " s")
        self.silth = self._dspin(cfg.silence_threshold_dbfs, -120, 0, 1, " dBFS")

        self.ct = QLineEdit(cfg.chapter_title_name)
        self.hd = QLineEdit(cfg.heading_name)
        self.vw = QLineEdit(cfg.verse_word)
        self.req_ct = QCheckBox("Require a Chapter Title marker"); self.req_ct.setChecked(cfg.require_chapter_title)
        self.req_hd = QCheckBox("Require a Heading marker"); self.req_hd.setChecked(cfg.require_heading)
        self.strict = QCheckBox("Flag misspelled / unrecognised marker names"); self.strict.setChecked(cfg.strict_verse_spelling)

        form.addRow("Target loudness:", self.target)
        form.addRow("Loudness tolerance (±):", self.tol)
        form.addRow("True-peak ceiling (max):", self.tp)
        form.addRow("Edge silence length:", self.sil)
        form.addRow("Silence tolerance (±):", self.siltol)
        form.addRow("Silence threshold:", self.silth)
        form.addRow("Chapter-title marker text:", self.ct)
        form.addRow("Heading marker text:", self.hd)
        form.addRow("Verse marker word:", self.vw)
        form.addRow(self.req_ct)
        form.addRow(self.req_hd)
        form.addRow(self.strict)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _dspin(self, val, lo, hi, step, suffix):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step)
        s.setDecimals(2); s.setValue(val); s.setSuffix(suffix)
        return s

    def result_config(self) -> Config:
        return Config(
            target_lufs=self.target.value(),
            lufs_tolerance=self.tol.value(),
            true_peak_max=self.tp.value(),
            silence_seconds=self.sil.value(),
            silence_tolerance=self.siltol.value(),
            silence_threshold_dbfs=self.silth.value(),
            chapter_title_name=self.ct.text() or "Chapter Title",
            heading_name=self.hd.text() or "Heading",
            verse_word=self.vw.text() or "Verse",
            require_chapter_title=self.req_ct.isChecked(),
            require_heading=self.req_hd.isChecked(),
            strict_verse_spelling=self.strict.isChecked(),
        )


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
COLS = ["File", "Book / Chapter", "Result", "Loudness", "True Peak",
        "Head Sil.", "Tail Sil.", "Markers", "Verses"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Bible Audio Checker")
        self.resize(1150, 680)
        self.cfg_path = default_config_path()
        self.cfg = Config.load(self.cfg_path)
        self.files = []          # list of paths
        self.reports = {}        # path -> FileReport
        self.thread = None
        self.worker = None
        self.setAcceptDrops(True)
        self._build_ui()
        self._check_ffmpeg_banner()

    # ---- UI construction ----
    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central)

        # toolbar row
        bar = QHBoxLayout()
        self.btn_add = QPushButton("Add Files…"); self.btn_add.clicked.connect(self.add_files)
        self.btn_folder = QPushButton("Add Folder…"); self.btn_folder.clicked.connect(self.add_folder)
        self.btn_clear = QPushButton("Clear"); self.btn_clear.clicked.connect(self.clear_all)
        self.btn_check = QPushButton("Check All"); self.btn_check.clicked.connect(self.run_checks)
        self.btn_check.setStyleSheet("font-weight:bold;")
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self.stop_checks); self.btn_stop.setEnabled(False)
        self.btn_export = QPushButton("Export Report…"); self.btn_export.clicked.connect(self.export_report)
        self.btn_settings = QPushButton("Settings…"); self.btn_settings.clicked.connect(self.open_settings)
        for b in (self.btn_add, self.btn_folder, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        for b in (self.btn_settings, self.btn_export, self.btn_stop, self.btn_check):
            bar.addWidget(b)
        outer.addLayout(bar)

        # splitter: table (top) + detail (bottom)
        split = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self.show_detail)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        split.addWidget(self.table)

        self.detail = QTextEdit(); self.detail.setReadOnly(True)
        self.detail.setFont(QFont("Menlo", 11) if sys.platform == "darwin" else QFont("Consolas", 10))
        self.detail.setPlaceholderText("Select a row to see full check details…")
        split.addWidget(self.detail)
        split.setSizes([440, 240])
        outer.addWidget(split, 1)

        self.progress = QProgressBar(); self.progress.setVisible(False)
        outer.addWidget(self.progress)

        self.setStatusBar(QStatusBar())
        self.status("Ready. Add WAV files or drag them onto the window.")

    def _check_ffmpeg_banner(self):
        if not ffmpeg_available():
            self.status("⚠ ffmpeg not found — loudness & true-peak checks will be skipped. See README to install.")

    def status(self, msg):
        self.statusBar().showMessage(msg)

    # ---- drag & drop ----
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        added = []
        for url in e.mimeData().urls():
            p = url.toLocalFile()
            if os.path.isdir(p):
                added += self._folder_wavs(p)
            elif p.lower().endswith(".wav"):
                added.append(p)
        self._add_paths(added)

    # ---- file management ----
    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select WAV files", "", "WAV files (*.wav)")
        self._add_paths(paths)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select folder of WAV files")
        if d:
            self._add_paths(self._folder_wavs(d))

    def _folder_wavs(self, d):
        out = []
        for root, _dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith(".wav"):
                    out.append(os.path.join(root, f))
        return sorted(out)

    def _add_paths(self, paths):
        new = 0
        for p in paths:
            if p not in self.files:
                self.files.append(p); new += 1
        if new:
            self._refresh_table()
            self.status("Added %d file(s). %d total." % (new, len(self.files)))

    def clear_all(self):
        self.files = []; self.reports = {}
        self.table.setRowCount(0); self.detail.clear()
        self.status("Cleared.")

    # ---- table rendering ----
    def _refresh_table(self):
        self.table.setRowCount(len(self.files))
        for row, path in enumerate(self.files):
            self._render_row(row, path)

    def _render_row(self, row, path):
        r = self.reports.get(path)
        self._set(row, 0, os.path.basename(path))
        if r is None:
            self._set(row, 1, "")
            self._set(row, 2, "—", GREY)
            for c in range(3, len(COLS)):
                self._set(row, c, "")
            return
        bc = ("%s %s" % (r.book, r.chapter)) if r.book else "unknown"
        self._set(row, 1, bc)
        if r.error:
            self._set(row, 2, "ERROR", RED, DRED)
            self._set(row, 8, r.error)
            return
        ok = r.passed
        self._set(row, 2, "PASS" if ok else "FAIL", GREEN if ok else RED, DGREEN if ok else DRED, bold=True)
        # map named checks into columns
        by = {i.name: i for i in r.items}
        self._cell_check(row, 3, by.get("Loudness"))
        self._cell_check(row, 4, by.get("True Peak"))
        self._cell_check(row, 5, by.get("Head Silence"))
        self._cell_check(row, 6, by.get("Tail Silence"))
        # markers column = worst of chapter-title/heading/spelling
        marker_items = [by.get(n) for n in ("Chapter Title", "Heading", "Marker Spelling", "Markers")]
        marker_items = [m for m in marker_items if m]
        if marker_items:
            worst_ok = all(m.passed for m in marker_items)
            self._set(row, 7, "OK" if worst_ok else "FAIL",
                      GREEN if worst_ok else RED, DGREEN if worst_ok else DRED)
        else:
            self._set(row, 7, "")
        self._cell_check(row, 8, by.get("Verses"))

    def _cell_check(self, row, col, item):
        if item is None:
            self._set(row, col, ""); return
        txt = item.value if item.value else ("OK" if item.passed else "FAIL")
        self._set(row, col, txt, GREEN if item.passed else RED,
                  DGREEN if item.passed else DRED)

    def _set(self, row, col, text, bg=None, fg=None, bold=False):
        it = QTableWidgetItem(str(text))
        if bg: it.setBackground(bg)
        if fg: it.setForeground(fg)
        if bold:
            f = it.font(); f.setBold(True); it.setFont(f)
        self.table.setItem(row, col, it)

    # ---- detail pane ----
    def show_detail(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        path = self.files[rows[0].row()]
        r = self.reports.get(path)
        if r is None:
            self.detail.setPlainText("%s\n\n(not checked yet)" % os.path.basename(path))
            return
        lines = []
        lines.append(os.path.basename(path))
        if r.book:
            lines.append("Identified as: %s chapter %s  (expected %s verses)" %
                         (r.book, r.chapter, r.expected_verses))
        else:
            lines.append("Book/chapter: NOT recognised from filename "
                         "(verse-count check skipped).")
        lines.append("Overall: %s" % ("PASS ✓" if r.passed else "FAIL ✗"))
        lines.append("")
        if r.error:
            lines.append("ERROR: %s" % r.error)
        for i in r.items:
            mark = "✓" if i.passed else "✗"
            lines.append("%s  %-15s %s" % (mark, i.name + ":", i.value))
            if not i.passed:
                lines.append("        → %s" % i.detail)
        self.detail.setPlainText("\n".join(lines))

    # ---- running checks ----
    def run_checks(self):
        if not self.files:
            self.status("No files to check."); return
        if self.thread is not None:
            return
        self.btn_check.setEnabled(False); self.btn_stop.setEnabled(True)
        self.progress.setVisible(True); self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)

        self.thread = QThread()
        self.worker = CheckWorker(list(self.files), self.cfg, ffmpeg_available())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished.connect(self._on_finished)
        self.thread.start()

    def _on_progress(self, done, total, name):
        self.progress.setValue(done - 1)
        self.status("Checking %d/%d: %s" % (done, total, name))

    def _on_file_done(self, report: FileReport):
        self.reports[report.path] = report
        row = self.files.index(report.path)
        self._render_row(row, report.path)
        self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self):
        self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        self.btn_check.setEnabled(True); self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)
        n_pass = sum(1 for r in self.reports.values() if r.passed)
        n = len(self.reports)
        self.status("Done. %d/%d files passed all checks." % (n_pass, n))

    def stop_checks(self):
        if self.worker:
            self.worker.stop()
            self.status("Stopping…")

    # ---- settings ----
    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.Accepted:
            self.cfg = dlg.result_config()
            self.cfg.save(self.cfg_path)
            self.status("Settings saved to %s. Re-run 'Check All' to apply." % self.cfg_path)

    # ---- export ----
    def export_report(self):
        if not self.reports:
            self.status("Nothing to export yet — run 'Check All' first."); return
        path, flt = QFileDialog.getSaveFileName(
            self, "Export report", "bible_audio_report.csv",
            "CSV (*.csv);;JSON (*.json)")
        if not path:
            return
        try:
            if path.lower().endswith(".json") or "JSON" in flt:
                self._export_json(path)
            else:
                self._export_csv(path)
            self.status("Report written to %s" % path)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))

    def _export_csv(self, path):
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["File", "Book", "Chapter", "ExpectedVerses", "Overall",
                        "Check", "Status", "Value", "Detail"])
            for p in self.files:
                r = self.reports.get(p)
                if not r:
                    continue
                overall = "PASS" if r.passed else "FAIL"
                if r.error:
                    w.writerow([r.filename, r.book or "", r.chapter or "",
                                r.expected_verses or "", overall, "ERROR",
                                "FAIL", "", r.error]); continue
                for i in r.items:
                    w.writerow([r.filename, r.book or "", r.chapter or "",
                                r.expected_verses or "", overall, i.name,
                                i.status, i.value, i.detail])

    def _export_json(self, path):
        import json
        data = []
        for p in self.files:
            r = self.reports.get(p)
            if not r:
                continue
            data.append({
                "file": r.filename, "book": r.book, "chapter": r.chapter,
                "expected_verses": r.expected_verses, "passed": r.passed,
                "error": r.error,
                "checks": [{"name": i.name, "status": i.status,
                            "value": i.value, "detail": i.detail} for i in r.items],
            })
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Bible Audio Checker")
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
