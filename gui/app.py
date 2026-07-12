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
from PySide6.QtGui import QColor, QPainter, QPen, QAction, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QSplitter, QFrame,
    QHeaderView, QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QLineEdit,
    QCheckBox, QDialogButtonBox, QProgressBar, QStatusBar, QSpinBox, QMenu,
    QTabWidget, QScrollArea,
)
from PySide6.QtSvg import QSvgRenderer

from engine.config import Config, default_config_path
from engine.checker import check_file, FileReport
from engine.loudness import ffmpeg_available
from engine.waveform import extract_waveform, WaveformData
from engine.auto_marker import auto_mark_file, auto_mark_files, AutoMarkResult
from engine.correction_memory import CorrectionMemory
from engine.marker_writer import generate_output_path

APP_NAME = "ScriptureSound QC"
APP_VERSION = "v2.0"

# Assets path
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _asset(name: str) -> str:
    """Get full path to an asset file."""
    return os.path.join(_ASSETS_DIR, name)


def _load_logo_icon() -> QIcon:
    """Load the app logo SVG as a QIcon."""
    logo_path = _asset("logo.svg")
    if os.path.isfile(logo_path):
        renderer = QSvgRenderer(logo_path)
        pixmap = QPixmap(128, 128)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        return QIcon(pixmap)
    return QIcon()

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
# Waveform widget — with horizontal zoom and pan
# ---------------------------------------------------------------------------
class WaveformView(QWidget):
    """Zoomable waveform display with marker overlays.

    Controls:
      * Mouse wheel: zoom in/out horizontally (centered on cursor)
      * Left-click + drag: pan the view
      * Double-click: reset zoom to show full file
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self._wave: WaveformData | None = None
        self._head_s = 0.0
        self._tail_s = 0.0
        self._title = ""
        # Zoom/pan state
        self._zoom = 1.0          # 1.0 = full file visible
        self._pan_offset = 0.0    # offset in seconds from the start (left edge)
        self._max_zoom = 100.0    # max zoom level
        self._min_zoom = 1.0      # min zoom = full view
        # Drag state
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_offset = 0.0
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background:%s; border:1px solid %s; border-radius:8px;" % (PANEL, BORDER))
        self.setMouseTracking(True)

    def set_data(self, wave: WaveformData, head_s=0.0, tail_s=0.0, title=""):
        self._wave = wave
        self._head_s = head_s
        self._tail_s = tail_s
        self._title = title
        self._zoom = 1.0
        self._pan_offset = 0.0
        self.update()

    def clear(self):
        self._wave = None
        self._zoom = 1.0
        self._pan_offset = 0.0
        self.update()

    def _visible_range(self) -> tuple:
        """Return (start_s, end_s) of the currently visible time range."""
        if self._wave is None:
            return (0.0, 1.0)
        dur = self._wave.duration_s
        visible_dur = dur / self._zoom
        start = self._pan_offset
        end = start + visible_dur
        return (start, end)

    def _clamp_pan(self):
        """Ensure pan offset stays within valid range."""
        if self._wave is None:
            self._pan_offset = 0.0
            return
        dur = self._wave.duration_s
        visible_dur = dur / self._zoom
        max_offset = max(0.0, dur - visible_dur)
        self._pan_offset = max(0.0, min(self._pan_offset, max_offset))

    # --- Mouse events for zoom/pan ---
    def wheelEvent(self, event):
        """Zoom in/out centered on cursor position."""
        if self._wave is None or not self._wave.ok:
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return

        # Get cursor position as a fraction of the widget width
        ml, mr = 8, 8
        plot_left = ml
        plot_width = max(1, self.width() - ml - mr)
        cursor_x = event.position().x() - plot_left
        cursor_frac = max(0.0, min(1.0, cursor_x / plot_width))

        # Calculate the time at cursor before zoom
        start_s, end_s = self._visible_range()
        visible_dur = end_s - start_s
        cursor_time = start_s + cursor_frac * visible_dur

        # Apply zoom factor
        zoom_factor = 1.25 if delta > 0 else 1.0 / 1.25
        old_zoom = self._zoom
        self._zoom = max(self._min_zoom, min(self._max_zoom, self._zoom * zoom_factor))

        # Adjust pan so the cursor time stays at the same screen position
        new_visible_dur = self._wave.duration_s / self._zoom
        self._pan_offset = cursor_time - cursor_frac * new_visible_dur
        self._clamp_pan()
        self.update()

    def mousePressEvent(self, event):
        """Start panning on left-click."""
        if event.button() == Qt.LeftButton and self._wave and self._zoom > 1.0:
            self._dragging = True
            self._drag_start_x = event.position().x()
            self._drag_start_offset = self._pan_offset
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        """Pan while dragging."""
        if self._dragging and self._wave:
            ml, mr = 8, 8
            plot_width = max(1, self.width() - ml - mr)
            dx_pixels = event.position().x() - self._drag_start_x
            # Convert pixel movement to seconds
            visible_dur = self._wave.duration_s / self._zoom
            dx_seconds = -(dx_pixels / plot_width) * visible_dur
            self._pan_offset = self._drag_start_offset + dx_seconds
            self._clamp_pan()
            self.update()
        elif self._wave and self._zoom > 1.0:
            self.setCursor(Qt.OpenHandCursor)
        else:
            self.setCursor(Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        """Stop panning."""
        if event.button() == Qt.LeftButton:
            self._dragging = False
            if self._wave and self._zoom > 1.0:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        """Reset zoom to full view on double-click."""
        if event.button() == Qt.LeftButton:
            self._zoom = 1.0
            self._pan_offset = 0.0
            self.setCursor(Qt.ArrowCursor)
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
        view_start, view_end = self._visible_range()
        view_dur = view_end - view_start

        def x_at(t):
            """Convert time to x pixel coordinate in the visible range."""
            if view_dur <= 0:
                return plot.left()
            return plot.left() + ((t - view_start) / view_dur) * plot.width()

        # Zoom indicator (top-right)
        if self._zoom > 1.05:
            p.setPen(QColor(ACCENT))
            zoom_txt = "%.1fx zoom" % self._zoom
            p.drawText(int(plot.right()) - 80, int(plot.top()) - 8, zoom_txt)
            # Time range indicator
            p.setPen(QColor(MUTED))
            range_txt = "%s - %s" % (_mmss_precise(view_start), _mmss_precise(view_end))
            p.drawText(int(plot.left()), int(plot.top()) - 8, range_txt)

        # shade head/tail silence regions (if visible)
        if self._head_s > 0 and view_start < self._head_s:
            sil_x_start = x_at(max(0, view_start))
            sil_x_end = x_at(min(self._head_s, view_end))
            if sil_x_end > sil_x_start:
                p.fillRect(QRectF(sil_x_start, plot.top(),
                                  sil_x_end - sil_x_start, plot.height()),
                           QColor(40, 52, 74, 120))
        if self._tail_s > 0:
            tail_start_t = dur - self._tail_s
            if view_end > tail_start_t:
                sil_x_start = x_at(max(tail_start_t, view_start))
                sil_x_end = x_at(min(dur, view_end))
                if sil_x_end > sil_x_start:
                    p.fillRect(QRectF(sil_x_start, plot.top(),
                                      sil_x_end - sil_x_start, plot.height()),
                               QColor(40, 52, 74, 120))

        # center line
        p.setPen(QPen(QColor(BORDER), 1))
        p.drawLine(int(plot.left()), int(ymid), int(plot.right()), int(ymid))

        # waveform envelope — only draw the visible portion
        n = len(wave.peaks)
        pw = plot.width()
        if n > 0 and dur > 0:
            # Determine which peak samples fall in the visible range
            samples_per_sec = n / dur
            i_start = max(0, int(view_start * samples_per_sec) - 1)
            i_end = min(n, int(view_end * samples_per_sec) + 2)

            p.setPen(QPen(WAVE, 1))
            for i in range(i_start, i_end):
                # Time for this sample
                t = (i / max(1, n - 1)) * dur
                x = x_at(t)
                if x < plot.left() - 1 or x > plot.right() + 1:
                    continue
                mn, mx = wave.peaks[i]
                y1 = ymid - mx * half
                y2 = ymid - mn * half
                p.drawLine(int(x), int(y1), int(x), int(y2))

        # markers — only draw visible ones
        markers = wave.markers or []
        last_label_x = -1e9
        min_gap = 34 if self._zoom < 5 else 20  # tighter labels when zoomed in
        for t, label in markers:
            if t < view_start - 0.5 or t > view_end + 0.5:
                continue
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
                txt = _short_marker(label) if self._zoom < 10 else label
                p.drawText(int(x) + 2, int(plot.top()) - 14 + 12, txt)
                last_label_x = x

        # time axis ticks — adaptive based on visible duration
        p.setPen(QColor(MUTED))
        if view_dur > 0:
            # Choose tick interval based on visible duration
            if view_dur > 120:
                tick_interval = 30.0
            elif view_dur > 60:
                tick_interval = 10.0
            elif view_dur > 20:
                tick_interval = 5.0
            elif view_dur > 5:
                tick_interval = 1.0
            elif view_dur > 1:
                tick_interval = 0.5
            else:
                tick_interval = 0.1

            t = (int(view_start / tick_interval) + 1) * tick_interval
            while t < view_end:
                x = x_at(t)
                p.drawLine(int(x), int(plot.bottom()), int(x), int(plot.bottom()) + 4)
                p.drawText(int(x) - 18, int(plot.bottom()) + 16, _mmss_precise(t))
                t += tick_interval

        # Mini-map (overview bar at the bottom when zoomed)
        if self._zoom > 1.05:
            map_h = 3
            map_y = plot.bottom() + mb - map_h - 1
            map_w = plot.width()
            # Full duration background
            p.fillRect(QRectF(plot.left(), map_y, map_w, map_h), QColor(BORDER))
            # Visible region highlight
            frac_start = view_start / dur if dur > 0 else 0
            frac_end = view_end / dur if dur > 0 else 1
            p.fillRect(QRectF(plot.left() + frac_start * map_w, map_y,
                              (frac_end - frac_start) * map_w, map_h),
                       QColor(ACCENT))

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


def _mmss_precise(t):
    """More precise time format for zoomed views."""
    if t < 60:
        return "%.1fs" % t
    m = int(t // 60)
    s = t - m * 60
    return "%d:%04.1f" % (m, s)


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------
class CheckWorker(QObject):
    progress = Signal(int, int, str)
    file_done = Signal(object)
    finished = Signal()

    def __init__(self, paths, cfg, do_loudness, script_verses=None):
        super().__init__()
        self.paths = paths; self.cfg = cfg; self.do_loudness = do_loudness
        self.script_verses = script_verses or {}
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
                r = check_file(path, self.cfg, do_loudness=self.do_loudness,
                               script_verses=self.script_verses if self.script_verses else None)
            except Exception as e:
                r = FileReport(path=path, filename=os.path.basename(path),
                               error="Unexpected error: %s" % e)
            self.file_done.emit(r)
        self.finished.emit()


# ---------------------------------------------------------------------------
# Auto-Mark background worker
# ---------------------------------------------------------------------------
class AutoMarkWorker(QObject):
    progress = Signal(int, int, str)
    file_done = Signal(object)
    finished = Signal()

    def __init__(self, wav_paths, verses, language, model, reader_id=""):
        super().__init__()
        self.wav_paths = wav_paths
        self.verses = verses
        self.language = language
        self.model = model
        self.reader_id = reader_id
        self._stop = False
        self.correction_memory = CorrectionMemory()

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.wav_paths)
        for i, wav_path in enumerate(self.wav_paths):
            if self._stop:
                break
            self.progress.emit(i + 1, total, os.path.basename(wav_path))
            try:
                result = auto_mark_file(
                    wav_path, self.verses,
                    language=self.language,
                    model=self.model,
                    reader_id=self.reader_id,
                    correction_memory=self.correction_memory,
                )
            except Exception as e:
                result = AutoMarkResult(error="Unexpected error: %s" % e)
            self.file_done.emit(result)
        self.finished.emit()


# ---------------------------------------------------------------------------
# Settings dialog — tabbed layout to fit on screen
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings — Check Standards")
        self.setMinimumWidth(480)
        self.setMaximumHeight(520)

        layout = QVBoxLayout(self)

        # Tabs
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid %s; border-radius: 6px; }
            QTabBar::tab { background: %s; border: 1px solid %s; padding: 8px 16px;
                           border-top-left-radius: 6px; border-top-right-radius: 6px;
                           color: %s; margin-right: 2px; }
            QTabBar::tab:selected { background: %s; color: %s; }
        """ % (BORDER, PANEL2, BORDER, MUTED, PANEL, TEXT))
        layout.addWidget(tabs)

        # === Tab 1: Checks ===
        tab1 = QWidget()
        f1 = QVBoxLayout(tab1); f1.setContentsMargins(12, 12, 12, 12); f1.setSpacing(6)
        f1.addWidget(QLabel("<b>Enable / Disable Checks</b>"))
        self.en_format = QCheckBox("Format (sample rate / bit depth)")
        self.en_format.setChecked(cfg.enable_format)
        self.en_loudness = QCheckBox("Loudness (integrated LUFS)")
        self.en_loudness.setChecked(cfg.enable_loudness)
        self.en_true_peak = QCheckBox("True Peak (dBTP ceiling)")
        self.en_true_peak.setChecked(cfg.enable_true_peak)
        self.en_head_sil = QCheckBox("Head Silence")
        self.en_head_sil.setChecked(cfg.enable_head_silence)
        self.en_tail_sil = QCheckBox("Tail Silence")
        self.en_tail_sil.setChecked(cfg.enable_tail_silence)
        self.en_markers = QCheckBox("Markers (Chapter Title, Heading, spelling)")
        self.en_markers.setChecked(cfg.enable_markers)
        self.en_verses = QCheckBox("Verse Completeness (count against KJV DB)")
        self.en_verses.setChecked(cfg.enable_verses)
        self.en_script = QCheckBox("Script Verification (transcribe & compare to PDF)")
        self.en_script.setChecked(cfg.enable_script_verification)
        for cb in (self.en_format, self.en_loudness, self.en_true_peak,
                   self.en_head_sil, self.en_tail_sil, self.en_markers,
                   self.en_verses, self.en_script):
            f1.addWidget(cb)
        f1.addStretch(1)
        tabs.addTab(tab1, "Checks")

        # === Tab 2: Mastering ===
        tab2 = QWidget()
        f2 = QFormLayout(tab2); f2.setContentsMargins(12, 12, 12, 12)
        self.target = self._d(cfg.target_lufs, -60, 0, 0.1, " LUFS")
        self.tol = self._d(cfg.lufs_tolerance, 0, 10, 0.1, " LU")
        self.tp = self._d(cfg.true_peak_max, -20, 0, 0.1, " dBTP")
        self.sil = self._d(cfg.silence_seconds, 0, 30, 0.1, " s")
        self.siltol = self._d(cfg.silence_tolerance, 0, 10, 0.05, " s")
        self.silth = self._d(cfg.silence_threshold_dbfs, -120, 0, 1, " dBFS")
        self.sr = QSpinBox(); self.sr.setRange(8000, 384000); self.sr.setSingleStep(1000); self.sr.setValue(cfg.expected_sample_rate); self.sr.setSuffix(" Hz")
        self.bits = QSpinBox(); self.bits.setRange(8, 32); self.bits.setSingleStep(8); self.bits.setValue(cfg.expected_bits); self.bits.setSuffix(" bit")
        self.ck_fmt = QCheckBox("Check sample rate / bit depth"); self.ck_fmt.setChecked(cfg.check_format)
        f2.addRow("Target loudness:", self.target)
        f2.addRow("Loudness tolerance (+/-):", self.tol)
        f2.addRow("True-peak ceiling:", self.tp)
        f2.addRow("Edge silence length:", self.sil)
        f2.addRow("Silence tolerance (+/-):", self.siltol)
        f2.addRow("Silence threshold:", self.silth)
        f2.addRow("Expected sample rate:", self.sr)
        f2.addRow("Expected bit depth:", self.bits)
        f2.addRow(self.ck_fmt)
        tabs.addTab(tab2, "Mastering")

        # === Tab 3: Markers ===
        tab3 = QWidget()
        f3 = QFormLayout(tab3); f3.setContentsMargins(12, 12, 12, 12)
        self.ct = QLineEdit(cfg.chapter_title_name)
        self.hd = QLineEdit(cfg.heading_name)
        self.vw = QLineEdit(cfg.verse_word)
        self.req_ct = QCheckBox("Require a Chapter Title marker"); self.req_ct.setChecked(cfg.require_chapter_title)
        self.req_hd = QCheckBox("Require a Heading marker"); self.req_hd.setChecked(cfg.require_heading)
        self.strict = QCheckBox("Flag misspelled / unrecognised marker names"); self.strict.setChecked(cfg.strict_verse_spelling)
        f3.addRow("Chapter-title marker text:", self.ct)
        f3.addRow("Heading marker text:", self.hd)
        f3.addRow("Verse marker word:", self.vw)
        f3.addRow(self.req_ct)
        f3.addRow(self.req_hd)
        f3.addRow(self.strict)
        tabs.addTab(tab3, "Markers")

        # === Tab 4: Script Verification ===
        tab4 = QWidget()
        f4 = QFormLayout(tab4); f4.setContentsMargins(12, 12, 12, 12)
        from engine.pdf_parser import INDIAN_LANGUAGES
        self.whisper_mode = QLineEdit(cfg.whisper_mode)
        self.whisper_mode.setPlaceholderText("local or api")
        self.whisper_model = QLineEdit(cfg.whisper_model)
        self.whisper_model.setPlaceholderText("tiny, base, small, medium, large")
        self.whisper_lang = QLineEdit(cfg.whisper_language)
        self.whisper_lang.setPlaceholderText("e.g. hi, ta, te, kn, ml, bn (empty=auto)")
        self.whisper_lang.setToolTip(
            "Language codes:\n" + "\n".join(
                "  %s = %s" % (code, name)
                for code, name in sorted(INDIAN_LANGUAGES.items())))
        self.api_key = QLineEdit(cfg.openai_api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-... (only needed for API mode)")
        self.match_thresh = self._d(cfg.script_match_threshold, 0.0, 1.0, 0.05, "")
        self.match_thresh.setToolTip("Minimum similarity (0.0-1.0) to count as a match")
        f4.addRow("Whisper mode:", self.whisper_mode)
        f4.addRow("Model (local):", self.whisper_model)
        f4.addRow("Language:", self.whisper_lang)
        f4.addRow("OpenAI API key:", self.api_key)
        f4.addRow("Match threshold:", self.match_thresh)
        f4.addRow(QLabel(""))
        f4.addRow(QLabel("<i>Supported: Hindi, Tamil, Telugu, Kannada, Malayalam,<br>"
                         "Bengali, Marathi, Gujarati, Punjabi, Urdu, Odia, English...</i>"))
        tabs.addTab(tab4, "Script STT")

        # OK / Cancel buttons
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        layout.addWidget(bb)

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
            strict_verse_spelling=self.strict.isChecked(),
            # Toggle flags
            enable_format=self.en_format.isChecked(),
            enable_loudness=self.en_loudness.isChecked(),
            enable_true_peak=self.en_true_peak.isChecked(),
            enable_head_silence=self.en_head_sil.isChecked(),
            enable_tail_silence=self.en_tail_sil.isChecked(),
            enable_markers=self.en_markers.isChecked(),
            enable_verses=self.en_verses.isChecked(),
            enable_script_verification=self.en_script.isChecked(),
            # Script verification
            whisper_mode=self.whisper_mode.text().strip() or "local",
            whisper_model=self.whisper_model.text().strip() or "medium",
            whisper_language=self.whisper_lang.text().strip(),
            openai_api_key=self.api_key.text().strip(),
            script_match_threshold=self.match_thresh.value(),
        )


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
COLS = ["File", "Book / Chapter", "Result", "Format", "Loudness", "True Peak",
        "Head Sil.", "Tail Sil.", "Markers", "Verses", "Script"]


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
        self.script_pdf_path = ""     # loaded PDF path
        self.script_verses = {}       # parsed verse dict
        self._missing_chapters = []   # missing chapter reports (persisted after check)
        self.setAcceptDrops(True)
        self._build_ui()
        if not ffmpeg_available():
            self.status("Warning: ffmpeg not found — loudness & true-peak checks will be skipped.")
        else:
            self.status("Ready. Add WAV files or drag them onto the window.")

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # Set window icon
        icon = _load_logo_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        # header (matches banner design)
        header = QFrame(); header.setObjectName("Header")
        hl = QHBoxLayout(header); hl.setContentsMargins(16, 10, 16, 10); hl.setSpacing(12)

        # Logo icon in header (rendered from SVG)
        logo_lbl = QLabel()
        logo_path = _asset("logo.svg")
        if os.path.isfile(logo_path):
            renderer = QSvgRenderer(logo_path)
            logo_px = QPixmap(48, 48)
            logo_px.fill(Qt.transparent)
            p = QPainter(logo_px)
            renderer.render(p)
            p.end()
            logo_lbl.setPixmap(logo_px)
        logo_lbl.setFixedSize(48, 48)
        hl.addWidget(logo_lbl)

        # Divider
        divider = QFrame(); divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet("color: %s;" % BORDER)
        hl.addWidget(divider)

        # Title block
        title_block = QVBoxLayout(); title_block.setSpacing(2)
        # "ScriptureSoundQC" with mixed colors
        title = QLabel("<span style='color:#e6ebf5; font-size:20px; font-weight:700;'>Scripture</span>"
                       "<span style='color:#d4a843; font-size:20px; font-weight:700;'>Sound</span>"
                       "<span style='color:#4dd9c0; font-size:20px; font-weight:700;'>QC</span>"
                       "  <span style='color:#4dd9c0; font-size:13px; font-weight:600;'>%s</span>" % APP_VERSION)
        title.setTextFormat(Qt.RichText)
        subtitle = QLabel("AUDIO BIBLE QUALITY CONTROL")
        subtitle.setStyleSheet("color: %s; font-size: 11px; letter-spacing: 2px;" % MUTED)
        tagline = QLabel("Loudness · True Peak · Silence · Verse Markers")
        tagline.setStyleSheet("color: #4dd9c0; font-size: 11px;")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        title_block.addWidget(tagline)
        hl.addLayout(title_block)

        hl.addStretch(1)
        self.summary_lbl = QLabel(""); self.summary_lbl.setObjectName("Subtitle")
        hl.addWidget(self.summary_lbl)
        credit = QLabel("Made by Voxsama"); credit.setObjectName("Credit")
        hl.addWidget(credit)
        outer.addWidget(header)

        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(12, 12, 12, 8)
        outer.addWidget(body, 1)

        # toolbar
        bar = QHBoxLayout()
        self.btn_add = QPushButton("Add Files…"); self.btn_add.clicked.connect(self.add_files)
        self.btn_folder = QPushButton("Add Folder…"); self.btn_folder.clicked.connect(self.add_folder)
        self.btn_script = QPushButton("Load Script PDF..."); self.btn_script.clicked.connect(self.load_script)
        self.btn_automark = QPushButton("Auto-Mark"); self.btn_automark.clicked.connect(self.run_auto_mark)
        self.btn_clear = QPushButton("Clear"); self.btn_clear.clicked.connect(self.clear_all)
        self.btn_settings = QPushButton("Settings…"); self.btn_settings.clicked.connect(self.open_settings)
        self.btn_export = QPushButton("Export ▾"); self.btn_export.clicked.connect(self.export_menu)
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self.stop_checks); self.btn_stop.setEnabled(False)
        self.btn_check = QPushButton("Check All"); self.btn_check.setObjectName("Primary"); self.btn_check.clicked.connect(self.run_checks)
        for b in (self.btn_add, self.btn_folder, self.btn_script, self.btn_automark, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        # Script status label
        self.script_lbl = QLabel("")
        self.script_lbl.setObjectName("Subtitle")
        bar.addWidget(self.script_lbl)
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

    def load_script(self):
        """Load a PDF script for verse verification."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Script PDF", "", "PDF files (*.pdf);;Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            from engine.pdf_parser import parse_pdf, parse_plain_text
            if path.lower().endswith(".pdf"):
                result = parse_pdf(path)
            else:
                # Plain text fallback
                with open(path, "r", encoding="utf-8") as f:
                    text = f.read()
                result = parse_plain_text(text)

            if result.ok:
                self.script_pdf_path = path
                self.script_verses = result.verses
                self.script_lbl.setText(
                    "Script: %s (%d verses)" % (os.path.basename(path), result.total_verses))
                self.status("Loaded script: %s — %d verses parsed." % (
                    os.path.basename(path), result.total_verses))
                if result.warnings:
                    self.status("Script loaded with warnings: " + "; ".join(result.warnings[:3]))
            else:
                self.script_verses = {}
                self.script_pdf_path = ""
                self.script_lbl.setText("")
                msg = "Could not parse verses from the file."
                if result.warnings:
                    msg += "\n" + "\n".join(result.warnings[:5])
                QMessageBox.warning(self, "Script Parse Error", msg)
        except Exception as e:
            QMessageBox.warning(self, "Script Load Error",
                                "Failed to load script: %s" % str(e))

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
        self.script_pdf_path = ""; self.script_verses = {}
        self._missing_chapters = []
        self.script_lbl.setText("")
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
        self._cell(row, 10, by.get("Script Match"))

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
        # Always prepend missing chapters warning if present
        mc_banner = ""
        if hasattr(self, '_missing_chapters') and self._missing_chapters:
            mc_banner = self._missing_chapters_html() + "<br><hr style='border-color:#2a3547'>"

        if r is None:
            self.issue.setText(mc_banner +
                               "<b>%s</b> — not checked yet. Click <b>Check All</b>." % name)
            return
        ident = ("%s %s" % (r.book, r.chapter)) if r.book else "book/chapter not recognised"
        if r.error:
            self.issue.setText(mc_banner +
                               "<b>%s</b> · %s<br><span style='color:%s'>ERROR: %s</span>"
                               % (name, ident, "#ff8a96", r.error))
            return
        fails = [i for i in r.items if not i.passed]
        if not fails:
            self.issue.setText(mc_banner +
                               "<b>%s</b> · %s · <span style='color:%s'><b>PASS</b></span> — all checks OK."
                               % (name, ident, "#78e6a0"))
            return
        bullets = "".join("<li><b>%s:</b> %s</li>" % (i.name, i.detail) for i in fails)
        self.issue.setText(mc_banner +
                           "<b>%s</b> · %s · <span style='color:%s'><b>FAIL</b></span>"
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
        self.worker = CheckWorker(list(self.files), self.cfg, ffmpeg_available(),
                                  script_verses=self.script_verses if self.script_verses else None)
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

        # Check for missing chapters across all loaded files
        from engine.checker import check_missing_chapters
        chapter_reports = check_missing_chapters(list(self.reports.values()))
        self._missing_chapters = [cr for cr in chapter_reports if not cr.complete]
        if self._missing_chapters:
            self._show_missing_chapters_issue()
            self.status("Done. %d/%d passed. %d need attention. MISSING CHAPTERS FOUND." % (npass, n, nfail))
        else:
            self._missing_chapters = []
            self.status("Done. %d/%d passed. %d need attention." % (npass, n, nfail))

    def _missing_chapters_html(self) -> str:
        """Build HTML for the missing chapters warning banner."""
        if not self._missing_chapters:
            return ""
        warnings = []
        for cr in self._missing_chapters:
            warnings.append("<b>%s</b>: missing chapter(s) <b>%s</b> (have %d/%d)" % (
                cr.book, cr.missing_str, len(cr.chapters_found), cr.total_chapters))
            if cr.duplicate_chapters:
                warnings.append("&nbsp;&nbsp;(duplicate files for chapter(s): %s)" %
                                ", ".join(map(str, cr.duplicate_chapters)))
        return ("<span style='color:#ff8a96'><b>Missing Chapters:</b></span> " +
                " | ".join(warnings))

    def _show_missing_chapters_issue(self):
        """Show missing chapters in the issue strip."""
        self.issue.setText(
            self._missing_chapters_html() +
            "<br><br><span style='color:%s'>Select a file above for per-file details.</span>" % MUTED)

    def stop_checks(self):
        if self.worker:
            self.worker.stop(); self.status("Stopping...")

    # ---------------------------------------------------------------------------
    # Auto-Mark
    # ---------------------------------------------------------------------------
    def run_auto_mark(self):
        """Launch the auto-marking workflow: select WAV files + script PDF."""
        # Get WAV files
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select WAV files to auto-mark", "", "WAV files (*.wav)")
        if not paths:
            return

        # Get script PDF if not already loaded
        if not self.script_verses:
            script_path, _ = QFileDialog.getOpenFileName(
                self, "Select Script PDF for verse text", "",
                "PDF files (*.pdf);;Text files (*.txt);;All files (*)")
            if not script_path:
                self.status("Auto-Mark cancelled: no script selected.")
                return
            try:
                from engine.pdf_parser import parse_pdf, parse_plain_text
                if script_path.lower().endswith(".pdf"):
                    result = parse_pdf(script_path)
                else:
                    with open(script_path, "r", encoding="utf-8") as f:
                        text = f.read()
                    result = parse_plain_text(text)

                if result.ok:
                    self.script_pdf_path = script_path
                    self.script_verses = result.verses
                    self.script_lbl.setText(
                        "Script: %s (%d verses)" % (os.path.basename(script_path),
                                                     result.total_verses))
                else:
                    QMessageBox.warning(self, "Script Parse Error",
                                        "Could not parse verses from the file.")
                    return
            except Exception as e:
                QMessageBox.warning(self, "Script Load Error",
                                    "Failed to load script: %s" % str(e))
                return

        # Start auto-marking in background
        if self.thread is not None:
            self.status("Another operation is in progress.")
            return

        language = self.cfg.whisper_language
        model = self.cfg.whisper_model

        self.btn_check.setEnabled(False)
        self.btn_automark.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self._automark_results = []

        self.thread = QThread()
        self.worker = AutoMarkWorker(paths, self.script_verses, language, model)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_automark_progress)
        self.worker.file_done.connect(self._on_automark_file_done)
        self.worker.finished.connect(self._on_automark_finished)
        self.thread.start()

    def _on_automark_progress(self, done, total, name):
        self.status("Auto-marking %d/%d: %s" % (done, total, name))

    def _on_automark_file_done(self, result):
        self._automark_results.append(result)
        self.progress.setValue(self.progress.value() + 1)

    def _on_automark_finished(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self.btn_check.setEnabled(True)
        self.btn_automark.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)

        results = self._automark_results
        success = [r for r in results if r.ok]
        failed = [r for r in results if not r.ok]

        msg_parts = []
        if success:
            msg_parts.append("%d file(s) marked successfully" % len(success))
        if failed:
            msg_parts.append("%d file(s) failed" % len(failed))

        summary = ". ".join(msg_parts) + "."
        self.status("Auto-Mark complete. " + summary)

        # Show results dialog
        detail_lines = []
        for r in results:
            if r.ok:
                detail_lines.append("OK: %s (%d markers, method: %s)"
                                    % (os.path.basename(r.output_path),
                                       r.markers_placed, r.method_used))
            else:
                detail_lines.append("FAIL: %s" % r.error)
            for w in r.warnings:
                detail_lines.append("  Warning: %s" % w)

        QMessageBox.information(
            self, "Auto-Mark Results",
            summary + "\n\n" + "\n".join(detail_lines[:20]))

    def save_marker_correction(self, language: str, verse_number: int,
                               expected_time: float, corrected_time: float,
                               reader_id: str = "") -> None:
        """Save a user correction for a marker position (for learning)."""
        mem = CorrectionMemory()
        mem.add_correction(language, verse_number, expected_time,
                           corrected_time, reader_id)
        self.status("Correction saved for verse %d (%.2fs -> %.2fs)"
                    % (verse_number, expected_time, corrected_time))

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

                    # Add missing chapters section
                    if hasattr(self, '_missing_chapters') and self._missing_chapters:
                        w.writerow([])
                        w.writerow(["--- MISSING CHAPTERS ---", "", "", ""])
                        for cr in self._missing_chapters:
                            w.writerow(["", cr.book, "MISSING: " + cr.missing_str,
                                        "Have %d/%d chapters" % (len(cr.chapters_found), cr.total_chapters)])
                            if cr.duplicate_chapters:
                                w.writerow(["", cr.book, "DUPLICATES: " + ", ".join(map(str, cr.duplicate_chapters)), ""])
                        n += len(self._missing_chapters)

                    self.status("Exported %d item(s) to %s" % (n, path))
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

                    # Add missing chapters section
                    if hasattr(self, '_missing_chapters') and self._missing_chapters:
                        w.writerow([])
                        w.writerow(["--- MISSING CHAPTERS ---", "", "", "", "", "", "", "", ""])
                        for cr in self._missing_chapters:
                            w.writerow(["", cr.book, "", cr.total_chapters, "FAIL",
                                        "Missing Chapters", "FAIL",
                                        "%d/%d" % (len(cr.chapters_found), cr.total_chapters),
                                        "Missing chapter(s): " + cr.missing_str])
                            if cr.duplicate_chapters:
                                w.writerow(["", cr.book, "", "", "",
                                            "Duplicate Chapters", "WARN", "",
                                            "Duplicate files for chapter(s): " + ", ".join(map(str, cr.duplicate_chapters))])

                    self.status("Full report written to %s" % path)
        except Exception as e:
            QMessageBox.warning(self, "Export failed", str(e))


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLE)
    # Set app-wide icon (shows in dock/taskbar)
    icon = _load_logo_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)
    w = MainWindow(); w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
