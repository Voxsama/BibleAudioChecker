"""
gui/app.py — ScriptureSound QC desktop application (PySide6).

Features:
  * Add files / folder / drag-drop; background "Check All".
  * Results table with a compact PASS/FAIL badge + per-check columns
    (Format, Loudness, True Peak, Head/Tail silence, Markers, Verses).
  * Embedded waveform panel that redraws for whichever chapter you click,
    with markers overlaid (like Audition) and head/tail silence shaded.
  * A concise "issues" strip so non-technical users see only what to fix.
  * Export: "Mistakes only" (one tidy row per failing file) or full report.
  * Settings for every threshold incl. the 48 kHz / 24-bit spec.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QSplitter, QFrame,
    QHeaderView, QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QLineEdit,
    QCheckBox, QDialogButtonBox, QProgressBar, QStatusBar, QSpinBox, QMenu,
)

from engine.config import Config, default_config_path
from engine.checker import check_file, FileReport
from engine.loudness import ffmpeg_available
from engine.waveform import extract_waveform, WaveformData

APP_NAME = "ScriptureSound QC"
APP_VERSION = "v1.0"

# palette
BG      = "#0e1320"
PANEL   = "#161d2e"
PANEL2  = "#1c2536"
BORDER  = "#2a3547"
TEXT    = "#e6ebf5"
MUTED   = "#8a97ad"
ACCENT  = "#4ade80"
PASSBG  = QColor(30, 71, 48)
FAILBG  = QColor(86, 28, 36)
PASSFG  = QColor(120, 230, 160)
FAILFG  = QColor(255, 138, 150)
WAVE    = QColor(74, 222, 128)
WAVE_SIL= QColor(60, 74, 96)
MARK_V  = QColor(120, 180, 255)
MARK_CT = QColor(255, 196, 92)


STYLE = """
* { color: %(TEXT)s; font-size: 13px; }
QWidget { background: %(BG)s; }
QLabel#Title { font-size: 20px; font-weight: 700; color: %(TEXT)s; }
QLabel#Version { color: %(ACCENT)s; font-weight: 600; }
QLabel#Subtitle { color: %(MUTED)s; font-size: 12px; }
QLabel#Credit { color: %(ACCENT)s; font-size: 12px; font-weight: 600; }
QFrame#Header { background: %(PANEL)s; border-bottom: 1px solid %(BORDER)s; }
QFrame#IssueBar { background: %(PANEL2)s; border: 1px solid %(BORDER)s; border-radius: 8px; }
QPushButton {
    background: %(PANEL2)s; border: 1px solid %(BORDER)s; border-radius: 8px;
    padding: 7px 14px; color: %(TEXT)s;
}
QPushButton:hover { background: #24304a; }
QPushButton:disabled { color: #5a6478; background: #141a28; }
QPushButton#Primary { background: %(ACCENT)s; color: #06210f; font-weight: 700; border: none; }
QPushButton#Primary:hover { background: #62e695; }
QTableWidget {
    background: %(PANEL)s; gridline-color: %(BORDER)s; border: 1px solid %(BORDER)s;
    border-radius: 8px; selection-background-color: #2b3a57; alternate-background-color: #131a29;
}
QHeaderView::section {
    background: %(PANEL2)s; color: %(MUTED)s; padding: 6px; border: none;
    border-right: 1px solid %(BORDER)s; border-bottom: 1px solid %(BORDER)s; font-weight: 600;
}
QTableWidget::item:selected { background: #2b3a57; color: %(TEXT)s; }
QStatusBar { background: %(PANEL)s; color: %(MUTED)s; border-top: 1px solid %(BORDER)s; }
QProgressBar { background: %(PANEL2)s; border: 1px solid %(BORDER)s; border-radius: 6px; text-align: center; }
QProgressBar::chunk { background: %(ACCENT)s; border-radius: 6px; }
QDialog { background: %(BG)s; }
QLineEdit, QDoubleSpinBox, QSpinBox {
    background: %(PANEL2)s; border: 1px solid %(BORDER)s; border-radius: 6px; padding: 4px 6px;
}
QMenu { background: %(PANEL2)s; border: 1px solid %(BORDER)s; }
QMenu::item:selected { background: #2b3a57; }
""" % dict(
    BG=BG, PANEL=PANEL, PANEL2=PANEL2, BORDER=BORDER, TEXT=TEXT, MUTED=MUTED, ACCENT=ACCENT)


# ---------------------------------------------------------------------------
# Waveform widget
# ---------------------------------------------------------------------------
class WaveformView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._wave: WaveformData | None = None
        self._head_s = 0.0
        self._tail_s = 0.0
        self._title = ""
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:%s; border:1px solid %s; border-radius:8px;" % (PANEL, BORDER))

    def set_data(self, wave: WaveformData, head_s=0.0, tail_s=0.0, title=""):
        self._wave = wave
        self._head_s = head_s
        self._tail_s = tail_s
        self._title = title
        self.update()

    def clear(self):
        self._wave = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, False)
        w = self.width(); h = self.height()
        p.fillRect(self.rect(), QColor(PANEL))

        ml, mr, mt, mb = 8, 8, 26, 20
        plot = QRectF(ml, mt, max(1, w - ml - mr), max(1, h - mt - mb))
        ymid = plot.top() + plot.height() / 2.0
        half = plot.height() / 2.0 * 0.92

        if self._wave is None or not self._wave.ok:
            p.setPen(QColor(MUTED))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "Select a chapter above to see its waveform and markers")
            p.end(); return

        wave = self._wave
        dur = wave.duration_s

        def x_at(t):
            return plot.left() + (t / dur) * plot.width() if dur > 0 else plot.left()

        # shade head/tail silence regions
        if self._head_s > 0:
            p.fillRect(QRectF(plot.left(), plot.top(), max(0.0, x_at(self._head_s) - plot.left()),
                              plot.height()), QColor(40, 52, 74, 120))
        if self._tail_s > 0:
            tx = x_at(dur - self._tail_s)
            p.fillRect(QRectF(tx, plot.top(), max(0.0, plot.right() - tx), plot.height()),
                       QColor(40, 52, 74, 120))

        # center line
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(int(plot.left()), int(ymid), int(plot.right()), int(ymid))

        # waveform envelope
        n = len(wave.peaks)
        p.setPen(QPen(WAVE, 1))
        pw = plot.width()
        for i, (mn, mx) in enumerate(wave.peaks):
            x = plot.left() + (i / max(1, n - 1)) * pw
            y1 = ymid - mx * half
            y2 = ymid - mn * half
            p.drawLine(int(x), int(y1), int(x), int(y2))

        # markers
        markers = wave.markers or []
        # decide which labels to draw to avoid clutter
        last_label_x = -1e9
        min_gap = 34
        for t, label in markers:
            x = x_at(t)
            low = (label or "").lower()
            is_ct = ("chapter" in low) or ("head" in low)
            pen = QPen(MARK_CT if is_ct else MARK_V, 1, Qt.DashLine)
            p.setPen(pen)
            p.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))
            # label
            draw_label = is_ct or (x - last_label_x) >= min_gap
            if draw_label:
                p.setPen(QColor(MARK_CT if is_ct else "#cfe0ff"))
                txt = _short_marker(label)
                p.drawText(int(x) + 2, int(plot.top()) - 14 + 12, txt)
                last_label_x = x

        # time axis ticks
        p.setPen(QColor(MUTED))
        ticks = 6
        for k in range(ticks + 1):
            t = dur * k / ticks
            x = x_at(t)
            p.drawLine(int(x), int(plot.bottom()), int(x), int(plot.bottom()) + 4)
            p.drawText(int(x) - 14, int(plot.bottom()) + 16, _mmss(t))

        p.end()


def _short_marker(label):
    low = label.lower()
    if "chapter" in low:
        return "Chapter"
    if "head" in low:
        return "Heading"
    # "Verse 12" -> "12"
    digits = "".join(ch for ch in label if ch.isdigit())
    return digits if digits else label


def _mmss(t):
    return "%d:%02d" % (int(t // 60), int(t % 60))


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
class CheckWorker(QObject):
    progress = Signal(int, int, str)
    file_done = Signal(object)
    finished = Signal()

    def __init__(self, paths, cfg, do_loudness):
        super().__init__()
        self.paths = paths; self.cfg = cfg; self.do_loudness = do_loudness
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.paths)
        for i, path in enumerate(self.paths, start=1):
            if self._stop:
                break
            self.progress.emit(i, total, os.path.basename(path))
            try:
                r = check_file(path, self.cfg, do_loudness=self.do_loudness)
            except Exception as e:
                r = FileReport(path=path, filename=os.path.basename(path),
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
        form = QFormLayout(self)
        self.target = self._d(cfg.target_lufs, -60, 0, 0.1, " LUFS")
        self.tol = self._d(cfg.lufs_tolerance, 0, 10, 0.1, " LU")
        self.tp = self._d(cfg.true_peak_max, -20, 0, 0.1, " dBTP")
        self.sil = self._d(cfg.silence_seconds, 0, 30, 0.1, " s")
        self.siltol = self._d(cfg.silence_tolerance, 0, 10, 0.05, " s")
        self.silth = self._d(cfg.silence_threshold_dbfs, -120, 0, 1, " dBFS")
        self.sr = QSpinBox(); self.sr.setRange(8000, 384000); self.sr.setSingleStep(1000); self.sr.setValue(cfg.expected_sample_rate); self.sr.setSuffix(" Hz")
        self.bits = QSpinBox(); self.bits.setRange(8, 32); self.bits.setSingleStep(8); self.bits.setValue(cfg.expected_bits); self.bits.setSuffix(" bit")
        self.ck_fmt = QCheckBox("Check sample rate / bit depth"); self.ck_fmt.setChecked(cfg.check_format)
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
        form.addRow("Expected sample rate:", self.sr)
        form.addRow("Expected bit depth:", self.bits)
        form.addRow(self.ck_fmt)
        form.addRow("Chapter-title marker text:", self.ct)
        form.addRow("Heading marker text:", self.hd)
        form.addRow("Verse marker word:", self.vw)
        form.addRow(self.req_ct)
        form.addRow(self.req_hd)
        form.addRow(self.strict)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        form.addRow(bb)

    def _d(self, val, lo, hi, step, suffix):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step)
        s.setDecimals(2); s.setValue(val); s.setSuffix(suffix); return s

    def result_config(self):
        return Config(
            target_lufs=self.target.value(), lufs_tolerance=self.tol.value(),
            true_peak_max=self.tp.value(), silence_seconds=self.sil.value(),
            silence_tolerance=self.siltol.value(), silence_threshold_dbfs=self.silth.value(),
            expected_sample_rate=self.sr.value(), expected_bits=self.bits.value(),
            check_format=self.ck_fmt.isChecked(),
            chapter_title_name=self.ct.text() or "Chapter Title",
            heading_name=self.hd.text() or "Heading", verse_word=self.vw.text() or "Verse",
            require_chapter_title=self.req_ct.isChecked(),
            require_heading=self.req_hd.isChecked(),
            strict_verse_spelling=self.strict.isChecked())


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
COLS = ["File", "Book / Chapter", "Result", "Format", "Loudness", "True Peak",
        "Head Sil.", "Tail Sil.", "Markers", "Verses"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("%s %s" % (APP_NAME, APP_VERSION))
        self.resize(1240, 760)
        self.cfg_path = default_config_path()
        self.cfg = Config.load(self.cfg_path)
        self.files = []
        self.reports = {}
        self.wave_cache = {}
        self.thread = None
        self.worker = None
        self.setAcceptDrops(True)
        self._build_ui()
        if not ffmpeg_available():
            self.status("⚠ ffmpeg not found — loudness & true-peak checks will be skipped.")
        else:
            self.status("Ready. Add WAV files or drag them onto the window.")

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # header
        header = QFrame(); header.setObjectName("Header")
        hl = QHBoxLayout(header); hl.setContentsMargins(16, 10, 16, 10)
        title = QLabel(APP_NAME); title.setObjectName("Title")
        ver = QLabel(APP_VERSION); ver.setObjectName("Version")
        sub = QLabel("   Audio Bible QC · loudness · silence · markers · verses"); sub.setObjectName("Subtitle")
        hl.addWidget(title); hl.addWidget(ver); hl.addWidget(sub); hl.addStretch(1)
        self.summary_lbl = QLabel(""); self.summary_lbl.setObjectName("Subtitle")
        hl.addWidget(self.summary_lbl)
        credit = QLabel("   Made by Voxsama"); credit.setObjectName("Credit")
        hl.addWidget(credit)
        outer.addWidget(header)

        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(12, 12, 12, 8)
        outer.addWidget(body, 1)

        # toolbar
        bar = QHBoxLayout()
        self.btn_add = QPushButton("Add Files…"); self.btn_add.clicked.connect(self.add_files)
        self.btn_folder = QPushButton("Add Folder…"); self.btn_folder.clicked.connect(self.add_folder)
        self.btn_clear = QPushButton("Clear"); self.btn_clear.clicked.connect(self.clear_all)
        self.btn_settings = QPushButton("Settings…"); self.btn_settings.clicked.connect(self.open_settings)
        self.btn_export = QPushButton("Export ▾"); self.btn_export.clicked.connect(self.export_menu)
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self.stop_checks); self.btn_stop.setEnabled(False)
        self.btn_check = QPushButton("Check All"); self.btn_check.setObjectName("Primary"); self.btn_check.clicked.connect(self.run_checks)
        for b in (self.btn_add, self.btn_folder, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        for b in (self.btn_settings, self.btn_export, self.btn_stop, self.btn_check):
            bar.addWidget(b)
        bl.addLayout(bar)

        split = QSplitter(Qt.Vertical)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self.on_select)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(COLS)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeToContents)
        split.addWidget(self.table)

        # bottom: issue strip + waveform
        bottom = QWidget(); bvl = QVBoxLayout(bottom); bvl.setContentsMargins(0, 8, 0, 0)
        self.issue = QLabel("Select a chapter to inspect."); self.issue.setObjectName("IssueBar")
        self.issue.setWordWrap(True); self.issue.setTextFormat(Qt.RichText)
        self.issue.setContentsMargins(12, 8, 12, 8)
        bvl.addWidget(self.issue)
        self.wave = WaveformView()
        bvl.addWidget(self.wave, 1)
        split.addWidget(bottom)
        split.setSizes([430, 300])
        bl.addWidget(split, 1)

        self.progress = QProgressBar(); self.progress.setVisible(False); self.progress.setFixedHeight(16)
        bl.addWidget(self.progress)

        self.setStatusBar(QStatusBar())
        _cr = QLabel("Made by Voxsama"); _cr.setObjectName("Credit")
        self.statusBar().addPermanentWidget(_cr)

    def status(self, msg):
        self.statusBar().showMessage(msg)

    # drag & drop
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
        self.files = []; self.reports = {}; self.wave_cache = {}
        self.table.setRowCount(0); self.wave.clear(); self.issue.setText("Select a chapter to inspect.")
        self.summary_lbl.setText(""); self.status("Cleared.")

    # table
    def _refresh_table(self):
        self.table.setRowCount(len(self.files))
        for row, path in enumerate(self.files):
            self._render_row(row, path)

    def _render_row(self, row, path):
        r = self.reports.get(path)
        self._set(row, 0, os.path.basename(path))
        if r is None:
            self._set(row, 1, ""); self._set(row, 2, "—")
            for c in range(3, len(COLS)):
                self._set(row, c, "")
            return
        self._set(row, 1, ("%s %s" % (r.book, r.chapter)) if r.book else "unknown")
        if r.error:
            self._set(row, 2, "ERROR", FAILBG, FAILFG); self._set(row, 9, r.error)
            return
        ok = r.passed
        self._set(row, 2, "PASS" if ok else "FAIL", PASSBG if ok else FAILBG,
                  PASSFG if ok else FAILFG, bold=True)
        by = {i.name: i for i in r.items}
        self._cell(row, 3, by.get("Format"))
        self._cell(row, 4, by.get("Loudness"))
        self._cell(row, 5, by.get("True Peak"))
        self._cell(row, 6, by.get("Head Silence"))
        self._cell(row, 7, by.get("Tail Silence"))
        marker_items = [by.get(n) for n in ("Chapter Title", "Heading", "Marker Spelling", "Markers")]
        marker_items = [m for m in marker_items if m]
        if marker_items:
            w = all(m.passed for m in marker_items)
            self._set(row, 8, "OK" if w else "FAIL", PASSBG if w else FAILBG, PASSFG if w else FAILFG)
        else:
            self._set(row, 8, "")
        self._cell(row, 9, by.get("Verses"))

    def _cell(self, row, col, item):
        if item is None:
            self._set(row, col, ""); return
        txt = item.value if item.value else ("OK" if item.passed else "FAIL")
        self._set(row, col, txt, PASSBG if item.passed else FAILBG,
                  PASSFG if item.passed else FAILFG)

    def _set(self, row, col, text, bg=None, fg=None, bold=False):
        it = QTableWidgetItem(str(text))
        if bg: it.setBackground(bg)
        if fg: it.setForeground(fg)
        if bold:
            f = it.font(); f.setBold(True); it.setFont(f)
        self.table.setItem(row, col, it)

    # selection -> waveform + issues
    def on_select(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return
        path = self.files[rows[0].row()]
        r = self.reports.get(path)
        self._show_issues(path, r)
        self._show_wave(path, r)

    def _measured_sil(self, r, name):
        if not r:
            return 0.0
        for i in r.items:
            if i.name == name:
                try:
                    return float(str(i.value).replace("s", "").strip())
                except ValueError:
                    return 0.0
        return 0.0

    def _show_wave(self, path, r):
        wave = self.wave_cache.get(path)
        if wave is None:
            self.status("Rendering waveform…"); QApplication.processEvents()
            try:
                wave = extract_waveform(path)
            except Exception as e:
                self.issue.setText("<span style='color:%s'>Could not read waveform: %s</span>" % (MUTED, e))
                self.wave.clear(); return
            self.wave_cache[path] = wave
            self.status("Ready.")
        head = self._measured_sil(r, "Head Silence")
        tail = self._measured_sil(r, "Tail Silence")
        title = os.path.basename(path)
        self.wave.set_data(wave, head_s=head, tail_s=tail, title=title)

    def _show_issues(self, path, r):
        name = os.path.basename(path)
        if r is None:
            self.issue.setText("<b>%s</b> — not checked yet. Click <b>Check All</b>." % name)
            return
        ident = ("%s %s" % (r.book, r.chapter)) if r.book else "book/chapter not recognised"
        if r.error:
            self.issue.setText("<b>%s</b> · %s<br><span style='color:%s'>ERROR: %s</span>"
                               % (name, ident, "#ff8a96", r.error))
            return
        fails = [i for i in r.items if not i.passed]
        if not fails:
            self.issue.setText("<b>%s</b> · %s · <span style='color:%s'><b>PASS</b></span> — all checks OK."
                               % (name, ident, "#78e6a0"))
            return
        bullets = "".join("<li><b>%s:</b> %s</li>" % (i.name, i.detail) for i in fails)
        self.issue.setText("<b>%s</b> · %s · <span style='color:%s'><b>FAIL</b></span>"
                           "<ul style='margin:4px 0 0 0;'>%s</ul>" % (name, ident, "#ff8a96", bullets))

    # running
    def run_checks(self):
        if not self.files:
            self.status("No files to check."); return
        if self.thread is not None:
            return
        self.btn_check.setEnabled(False); self.btn_stop.setEnabled(True)
        self.progress.setVisible(True); self.progress.setRange(0, len(self.files)); self.progress.setValue(0)
        self.thread = QThread()
        self.worker = CheckWorker(list(self.files), self.cfg, ffmpeg_available())
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_progress)
        self.worker.file_done.connect(self._on_file_done)
        self.worker.finished.connect(self._on_finished)
        self.thread.start()

    def _on_progress(self, done, total, name):
        self.status("Checking %d/%d: %s" % (done, total, name))

    def _on_file_done(self, report):
        self.reports[report.path] = report
        self.wave_cache.pop(report.path, None)
        row = self.files.index(report.path)
        self._render_row(row, report.path)
        self.progress.setValue(self.progress.value() + 1)

    def _on_finished(self):
        self.thread.quit(); self.thread.wait()
        self.thread = None; self.worker = None
        self.btn_check.setEnabled(True); self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)
        n = len(self.reports); npass = sum(1 for r in self.reports.values() if r.passed)
        nfail = n - npass
        self.summary_lbl.setText("%d passed · %d to fix · %d total" % (npass, nfail, n))
        self.status("Done. %d/%d passed. %d need attention." % (npass, n, nfail))

    def stop_checks(self):
        if self.worker:
            self.worker.stop(); self.status("Stopping…")

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.Accepted:
            self.cfg = dlg.result_config(); self.cfg.save(self.cfg_path)
            self.status("Settings saved. Re-run 'Check All' to apply.")

    # export
    def export_menu(self):
        if not self.reports:
            self.status("Nothing to export yet — run 'Check All' first."); return
        m = QMenu(self)
        a1 = QAction("Mistakes only (CSV)  — just what to fix", self)
        a2 = QAction("Full report (CSV)  — every check", self)
        a1.triggered.connect(lambda: self._export(mistakes_only=True))
        a2.triggered.connect(lambda: self._export(mistakes_only=False))
        m.addAction(a1); m.addAction(a2)
        m.exec(self.btn_export.mapToGlobal(self.btn_export.rect().bottomLeft()))

    def _export(self, mistakes_only):
        import csv
        default = "mistakes.csv" if mistakes_only else "full_report.csv"
        path, _ = QFileDialog.getSaveFileName(self, "Export report", default, "CSV (*.csv)")
        if not path:
            return
        try:
            with open(path, "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if mistakes_only:
                    w.writerow(["File", "Book", "Chapter", "Issues"])
                    n = 0
                    for p in self.files:
                        r = self.reports.get(p)
                        if not r or r.passed:
                            continue
                        if r.error:
                            issues = r.error
                        else:
                            issues = " | ".join("%s: %s" % (i.name, i.detail)
                                                for i in r.items if not i.passed)
                        w.writerow([r.filename, r.book or "", r.chapter or "", issues]); n += 1
                    self.status("Exported %d file(s) that need fixing to %s" % (n, path))
                else:
                    w.writerow(["File", "Book", "Chapter", "ExpectedVerses", "Overall",
                                "Check", "Status", "Value", "Detail"])
                    for p in self.files:
                        r = self.reports.get(p)
                        if not r:
                            continue
                        overall = "PASS" if r.passed else "FAIL"
                        if r.error:
                            w.writerow([r.filename, r.book or "", r.chapter or "", r.expected_verses or "",
                                        overall, "ERROR", "FAIL", "", r.error]); continue
                        for i in r.items:
                            w.writerow([r.filename, r.book or "", r.chapter or "", r.expected_verses or "",
                                        overall, i.name, i.status, i.value, i.detail])
                    self.status("Full report written to %s" % path)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
