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
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import Qt, QThread, Signal, QObject, QRectF, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QPainter, QPen, QAction, QIcon, QPixmap, QDesktopServices)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QLabel, QFileDialog, QSplitter, QFrame,
    QHeaderView, QMessageBox, QDialog, QFormLayout, QDoubleSpinBox, QLineEdit,
    QCheckBox, QDialogButtonBox, QProgressBar, QStatusBar, QSpinBox, QMenu,
    QTabWidget, QScrollArea, QComboBox,
    QAbstractItemView,
)
from PySide6.QtSvg import QSvgRenderer

from engine.config import Config, default_config_path
from engine.checker import check_file, FileReport
from engine.loudness import ffmpeg_available
from engine.waveform import extract_waveform, WaveformData
from engine.auto_marker import auto_mark_file, auto_mark_files, AutoMarkResult
from engine.correction_memory import CorrectionMemory
from engine.marker_writer import generate_output_path
from engine.project import AudioBibleProject, ProjectPreset, new_project
from engine.marker_editor import MarkerEditSession
from engine.review import (
    merge_review_items, review_from_automark, review_from_file_report,
    review_from_language, review_from_calibration,
)

APP_NAME = "ScriptureSound QC"
APP_VERSION = "v4.0 Beta"
APP_UPDATE_VERSION = "4.0.0-beta"
AUTO_MARK_ENABLED = False
AUTO_MARK_DISABLED_MESSAGE = (
    "Automatic verse marking is temporarily disabled in this release while "
    "its timing accuracy is being improved. Existing markers can still be "
    "reviewed and edited in Markers & Waveform.")

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
QLabel { background: transparent; border: none; }
QLabel#Title { font-size: 20px; font-weight: 700; color: %(TEXT)s; }
QLabel#Version { color: %(ACCENT)s; font-weight: 600; }
QLabel#Subtitle { color: %(MUTED)s; font-size: 12px; }
QLabel#Credit { color: %(ACCENT)s; font-size: 12px; font-weight: 600; }
QFrame#Header { background: %(PANEL)s; border-bottom: 1px solid %(BORDER)s; }
QFrame#IssueBar { background: %(PANEL2)s; border: 1px solid %(BORDER)s; border-radius: 8px; }
QTabWidget#WorkspaceTabs::pane {
    background: %(BG)s; border: 1px solid %(BORDER)s;
    border-radius: 0 8px 8px 8px; top: -1px;
}
QTabWidget#WorkspaceTabs QTabBar::tab {
    background: #121a2a; color: #aeb9ca;
    border: 1px solid %(BORDER)s; border-bottom: none;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
    min-width: 112px; padding: 10px 16px; margin-right: 4px;
    font-size: 13px; font-weight: 600;
}
QTabWidget#WorkspaceTabs QTabBar::tab:hover {
    background: #202b42; color: %(TEXT)s;
}
QTabWidget#WorkspaceTabs QTabBar::tab:selected {
    background: %(PANEL2)s; color: #ffffff;
    border-color: #4dd9c0; border-top: 3px solid #4dd9c0;
    padding-top: 8px;
}
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

    markerSelected = Signal(int)
    markerMoved = Signal(int, float, float)

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
        self._editable = False
        self._drag_marker_index = -1
        self._drag_marker_original_time = 0.0
        self._selected_marker_index = -1
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
        self._selected_marker_index = -1
        self.update()

    def set_editable(self, editable=True):
        self._editable = bool(editable)

    def clear(self):
        self._wave = None
        self._zoom = 1.0
        self._pan_offset = 0.0
        self._selected_marker_index = -1
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

    def _time_at_x(self, x):
        if self._wave is None:
            return 0.0
        plot_left = 8.0
        plot_width = max(1.0, self.width() - 16.0)
        fraction = max(0.0, min(1.0, (x - plot_left) / plot_width))
        start, end = self._visible_range()
        return start + fraction * (end - start)

    def _marker_at_x(self, x, tolerance_px=7.0):
        if self._wave is None or not self._wave.markers:
            return -1
        start, end = self._visible_range()
        duration = max(0.000001, end - start)
        plot_left = 8.0
        plot_width = max(1.0, self.width() - 16.0)
        best_index = -1
        best_distance = tolerance_px + 1.0
        for index, (time_s, _label) in enumerate(self._wave.markers):
            marker_x = plot_left + (
                (time_s - start) / duration) * plot_width
            distance = abs(marker_x - x)
            if distance <= tolerance_px and distance < best_distance:
                best_index = index
                best_distance = distance
        return best_index

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
        if event.button() != Qt.LeftButton or self._wave is None:
            return
        marker_index = (
            self._marker_at_x(event.position().x())
            if self._editable else -1)
        if marker_index >= 0:
            self._drag_marker_index = marker_index
            self._selected_marker_index = marker_index
            self._drag_marker_original_time = float(
                self._wave.markers[marker_index][0])
            self.markerSelected.emit(marker_index)
            self.setCursor(Qt.SizeHorCursor)
            self.update()
        elif self._zoom > 1.0:
            self._dragging = True
            self._drag_start_x = event.position().x()
            self._drag_start_offset = self._pan_offset
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        """Pan while dragging."""
        if self._drag_marker_index >= 0 and self._wave:
            new_time = max(
                0.0, min(self._wave.duration_s,
                         self._time_at_x(event.position().x())))
            _old_time, label = self._wave.markers[
                self._drag_marker_index]
            self._wave.markers[self._drag_marker_index] = (
                new_time, label)
            self.setCursor(Qt.SizeHorCursor)
            self.update()
        elif self._dragging and self._wave:
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
            if self._drag_marker_index >= 0 and self._wave:
                index = self._drag_marker_index
                new_time = float(self._wave.markers[index][0])
                original_time = self._drag_marker_original_time
                self._drag_marker_index = -1
                self.markerMoved.emit(index, original_time, new_time)
                self.setCursor(Qt.ArrowCursor)
                return
            self._dragging = False
            if self._wave and self._zoom > 1.0:
                self.setCursor(Qt.OpenHandCursor)
            else:
                self.setCursor(Qt.ArrowCursor)

    def mouseDoubleClickEvent(self, event):
        """Reset zoom to full view on double-click."""
        if event.button() == Qt.LeftButton:
            marker_index = (
                self._marker_at_x(event.position().x())
                if self._editable else -1)
            if marker_index >= 0:
                self._selected_marker_index = marker_index
                self.markerSelected.emit(marker_index)
                self.update()
                return
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
        for marker_index, (t, label) in enumerate(markers):
            if t < view_start - 0.5 or t > view_end + 0.5:
                continue
            x = x_at(t)
            low = (label or "").lower()
            is_ct = ("chapter" in low) or ("head" in low)
            width = 3 if marker_index == self._selected_marker_index else 1
            pen = QPen(
                MARK_CT if is_ct else MARK_V, width, Qt.DashLine)
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

    def __init__(self, paths, cfg, do_loudness, script_verses=None,
                 script_chapters=None, script_book_chapters=None):
        super().__init__()
        self.paths = paths; self.cfg = cfg; self.do_loudness = do_loudness
        self.script_verses = script_verses or {}
        self.script_chapters = script_chapters or {}
        self.script_book_chapters = script_book_chapters or {}
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
                verses = self._script_for_path(path)
                r = check_file(path, self.cfg, do_loudness=self.do_loudness,
                               script_verses=verses if verses else None)
            except Exception as e:
                r = FileReport(path=path, filename=os.path.basename(path),
                               error="Unexpected error: %s" % e)
            self.file_done.emit(r)
        self.finished.emit()

    def _script_for_path(self, path):
        from engine.bible_db import parse_filename
        bc = parse_filename(path)
        if bc and (bc.book, bc.chapter) in self.script_book_chapters:
            return self.script_book_chapters[(bc.book, bc.chapter)]
        if bc and bc.chapter in self.script_chapters:
            return self.script_chapters[bc.chapter]
        if (0 in self.script_chapters and len(self.script_chapters) == 1
                and len(self.paths) == 1):
            return self.script_chapters[0]
        return self.script_verses if not self.script_chapters else {}


class UpdateCheckWorker(QObject):
    """Fetch release metadata without blocking the GUI thread."""
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, current_version: str, channel: str):
        super().__init__()
        self.current_version = current_version
        self.channel = channel

    def run(self):
        try:
            from engine.updates import check_for_updates
            self.finished.emit(check_for_updates(
                self.current_version, self.channel))
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Auto-Mark background worker
# ---------------------------------------------------------------------------
class AutoMarkWorker(QObject):
    progress = Signal(int, int, str)
    stage_progress = Signal(int, int, str, str, float)
    marker_preview = Signal(str, object)
    file_done = Signal(object)
    finished = Signal()

    def __init__(self, wav_paths, verses, language, model, reader_id="",
                 script_chapters=None, script_book_chapters=None,
                 script_headings=None, script_book_headings=None,
                 alignment_backend="auto", language_by_path=None):
        super().__init__()
        self.wav_paths = wav_paths
        self.verses = verses
        self.script_chapters = script_chapters or {}
        self.script_book_chapters = script_book_chapters or {}
        self.script_headings = script_headings or {}
        self.script_book_headings = script_book_headings or {}
        self.language = language
        self.model = model
        self.reader_id = reader_id
        self.alignment_backend = alignment_backend
        self.language_by_path = language_by_path or {}
        self._stop = False
        self.correction_memory = CorrectionMemory()

    def stop(self):
        self._stop = True

    def run(self):
        total = len(self.wav_paths)
        for i, wav_path in enumerate(self.wav_paths):
            if self._stop:
                break
            filename = os.path.basename(wav_path)
            self.progress.emit(i + 1, total, filename)
            try:
                verses, headings = self._script_for_path(wav_path)
                if not verses:
                    raise ValueError(
                        "No matching script chapter for %s" %
                        os.path.basename(wav_path))
                selected_language = (
                    self.language or
                    self.language_by_path.get(wav_path, ""))
                result = auto_mark_file(
                    wav_path, verses,
                    language=selected_language,
                    model=self.model,
                    reader_id=self.reader_id,
                    headings=headings,
                    alignment_backend=self.alignment_backend,
                    correction_memory=self.correction_memory,
                    progress_callback=lambda stage, fraction:
                        self.stage_progress.emit(
                            i + 1, total, filename, stage, float(fraction)),
                    marker_preview_callback=lambda markers:
                        self.marker_preview.emit(wav_path, markers),
                )
            except Exception as e:
                result = AutoMarkResult(
                    input_path=wav_path,
                    error="Unexpected error: %s" % e)
            self.file_done.emit(result)
        self.finished.emit()

    def _script_for_path(self, path):
        from engine.bible_db import parse_filename
        bc = parse_filename(path)
        if bc and (bc.book, bc.chapter) in self.script_book_chapters:
            key = (bc.book, bc.chapter)
            return (
                self.script_book_chapters[key],
                self.script_book_headings.get(key, []))
        if bc and bc.chapter in self.script_chapters:
            return (
                self.script_chapters[bc.chapter],
                self.script_headings.get(bc.chapter, []))
        if (0 in self.script_chapters and len(self.script_chapters) == 1
                and len(self.wav_paths) == 1):
            return self.script_chapters[0], self.script_headings.get(0, [])
        return (
            self.verses if not self.script_chapters else {},
            self.script_headings.get(0, []))


class ScriptLoadWorker(QObject):
    loaded = Signal(object, bool, str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, path):
        super().__init__()
        self.path = path

    def run(self):
        try:
            if self.path.lower().endswith(".pdf"):
                from engine.script_cache import load_or_parse_pdf
                cache_result = load_or_parse_pdf(self.path)
                self.loaded.emit(
                    cache_result.collection, cache_result.from_cache,
                    cache_result.cache_path)
            else:
                from engine.pdf_parser import parse_text_chapters
                with open(self.path, "r", encoding="utf-8") as stream:
                    result = parse_text_chapters(stream.read())
                self.loaded.emit(result, False, "")
        except Exception as exc:
            self.failed.emit(str(exc))
        self.finished.emit()


class LanguageDetectWorker(QObject):
    progress = Signal(int, int, str)
    file_done = Signal(str, object)
    finished = Signal()

    def __init__(self, paths, model):
        super().__init__()
        self.paths = list(paths)
        self.model = model
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from engine.transcriber import Transcriber
        transcriber = Transcriber(
            mode="local", model=self.model, language="")
        total = len(self.paths)
        for index, path in enumerate(self.paths, 1):
            if self._stop:
                break
            self.progress.emit(
                index, total, os.path.basename(path))
            result = transcriber.detect_language(path, top_n=3)
            self.file_done.emit(path, result)
        self.finished.emit()


class MasterWorker(QObject):
    progress = Signal(int, int, str)
    file_done = Signal(object)
    finished = Signal()

    def __init__(self, paths, settings):
        super().__init__()
        self.paths = list(paths)
        self.settings = settings
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        from engine.mastering import master_file, MasteringResult
        total = len(self.paths)
        for index, path in enumerate(self.paths, 1):
            if self._stop:
                break
            self.progress.emit(index, total, os.path.basename(path))
            try:
                result = master_file(path, self.settings)
            except Exception as exc:
                result = MasteringResult(
                    output_path=path,
                    error="Unexpected mastering error: %s" % exc)
            self.file_done.emit(result)
        self.finished.emit()


class ModelPackDownloadWorker(QObject):
    progress = Signal(str, int, int, float)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal(str)
    finished = Signal()

    def __init__(self, model_key):
        super().__init__()
        self.model_key = model_key
        self._cancel = False

    def stop(self):
        self._cancel = True

    def run(self):
        from engine.model_packs import (
            ModelPackCancelled, download_model_pack)
        try:
            result = download_model_pack(
                self.model_key,
                progress_callback=lambda stage, done, total, elapsed:
                self.progress.emit(stage, done, total, elapsed),
                cancel_callback=lambda: self._cancel)
            self.completed.emit(result)
        except ModelPackCancelled as exc:
            self.cancelled.emit(str(exc))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self.finished.emit()


class ModelPackDialog(QDialog):
    """No-command-line installer for speech and alignment model weights."""

    activeModelChanged = Signal(str)

    def __init__(self, cfg, cfg_path, parent=None, select_model=""):
        super().__init__(parent)
        self.cfg = cfg
        self.cfg_path = cfg_path
        self.download_thread = None
        self.download_worker = None
        self._last_message = ""
        self._requested_selection = select_model or cfg.whisper_model
        self.setWindowTitle("AI Model Packs")
        self.setMinimumSize(920, 540)

        layout = QVBoxLayout(self)
        introduction = QLabel(
            "<b>Download speech-recognition models inside the app</b><br>"
            "Meta MMS Assamese Precision is recommended for non-commercial "
            "Assamese Auto-Mark. Whisper packs remain available for general "
            "multilingual transcription and other languages. Choose the "
            "spoken language separately in Settings. Large weights are "
            "downloaded only when requested.")
        introduction.setWordWrap(True)
        introduction.setObjectName("IssueBar")
        introduction.setContentsMargins(12, 10, 12, 10)
        layout.addWidget(introduction)

        self.pack_table = QTableWidget(0, 4)
        self.pack_table.setHorizontalHeaderLabels(
            ["Model pack", "Approx. download", "Purpose", "Status"])
        self.pack_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.pack_table.setSelectionMode(QTableWidget.SingleSelection)
        self.pack_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pack_table.verticalHeader().setVisible(False)
        header = self.pack_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.pack_table.itemSelectionChanged.connect(
            self._refresh_button_state)
        layout.addWidget(self.pack_table, 1)

        self.pack_progress = QProgressBar()
        self.pack_progress.setRange(0, 1000)
        self.pack_progress.setValue(0)
        self.pack_progress.setVisible(False)
        layout.addWidget(self.pack_progress)
        self.pack_status = QLabel("")
        self.pack_status.setWordWrap(True)
        self.pack_status.setObjectName("Subtitle")
        layout.addWidget(self.pack_status)

        buttons = QHBoxLayout()
        self.btn_pack_download = QPushButton("Download / Verify")
        self.btn_pack_download.setObjectName("Primary")
        self.btn_pack_download.clicked.connect(self.download_selected)
        self.btn_pack_activate = QPushButton("Use Selected Model")
        self.btn_pack_activate.clicked.connect(self.activate_selected)
        self.btn_pack_remove = QPushButton("Remove Download")
        self.btn_pack_remove.clicked.connect(self.remove_selected)
        self.btn_pack_cancel = QPushButton("Pause Download")
        self.btn_pack_cancel.clicked.connect(self.cancel_download)
        self.btn_pack_cancel.setEnabled(False)
        self.btn_pack_close = QPushButton("Close")
        self.btn_pack_close.clicked.connect(self.accept)
        for button in (
                self.btn_pack_download, self.btn_pack_activate,
                self.btn_pack_remove, self.btn_pack_cancel):
            buttons.addWidget(button)
        buttons.addStretch(1)
        buttons.addWidget(self.btn_pack_close)
        layout.addLayout(buttons)

        self.refresh()

    def _packs(self):
        from engine.model_packs import available_model_packs
        return available_model_packs()

    def _selected_pack(self):
        rows = self.pack_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        packs = self._packs()
        return packs[row] if 0 <= row < len(packs) else None

    def refresh(self):
        from engine.model_packs import (
            format_bytes, is_model_pack_installed, model_cache_dir,
            model_pack_partial_bytes)
        packs = self._packs()
        self.pack_table.setRowCount(len(packs))
        selected_row = 0
        for row, pack in enumerate(packs):
            installed = is_model_pack_installed(pack.key)
            active = (
                pack.backend == "whisper" and
                pack.key == self.cfg.whisper_model)
            partial = model_pack_partial_bytes(pack.key)
            if pack.backend == "mms" and installed:
                status = "INSTALLED - AUTO FOR ASSAMESE"
            elif active and installed:
                status = "ACTIVE · INSTALLED"
            elif installed:
                status = "INSTALLED"
            elif partial:
                status = "PAUSED (%s)" % format_bytes(partial)
            else:
                status = "NOT INSTALLED"
            name = pack.display_name
            if pack.recommended:
                name += " · Recommended"
            values = [
                name, format_bytes(pack.approx_bytes),
                pack.description, status]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.UserRole, pack.key)
                if active:
                    item.setForeground(PASSFG)
                elif installed:
                    item.setForeground(QColor(110, 220, 200))
                self.pack_table.setItem(row, column, item)
            if pack.key == self._requested_selection:
                selected_row = row
        if packs:
            self.pack_table.selectRow(selected_row)
        self.pack_status.setText(
            self._last_message or
            "Model storage: %s" % model_cache_dir())
        self._refresh_button_state()

    def _refresh_button_state(self):
        from engine.model_packs import is_model_pack_installed
        pack = self._selected_pack()
        busy = self.download_thread is not None
        installed = bool(
            pack and is_model_pack_installed(pack.key))
        self.btn_pack_download.setEnabled(bool(pack) and not busy)
        self.btn_pack_activate.setEnabled(
            installed and not busy and
            pack.backend == "whisper" and
            pack.key != self.cfg.whisper_model)
        self.btn_pack_remove.setEnabled(installed and not busy)
        self.btn_pack_close.setEnabled(not busy)

    def download_selected(self):
        pack = self._selected_pack()
        if pack is None or self.download_thread is not None:
            return
        self._requested_selection = pack.key
        self._last_message = ""
        self.pack_progress.setVisible(True)
        self.pack_progress.setValue(0)
        self.pack_status.setText(
            "Preparing %s. Existing partial downloads will resume…" %
            pack.display_name)
        self.download_thread = QThread()
        self.download_worker = ModelPackDownloadWorker(pack.key)
        self.download_worker.moveToThread(self.download_thread)
        self.download_thread.started.connect(self.download_worker.run)
        self.download_worker.progress.connect(self._on_download_progress)
        self.download_worker.completed.connect(self._on_download_complete)
        self.download_worker.failed.connect(self._on_download_failed)
        self.download_worker.cancelled.connect(self._on_download_cancelled)
        self.download_worker.finished.connect(self.download_thread.quit)
        self.download_worker.finished.connect(
            self.download_worker.deleteLater)
        self.download_thread.finished.connect(self._on_download_thread_done)
        self.btn_pack_cancel.setEnabled(True)
        self._refresh_button_state()
        self.download_thread.start()

    def _on_download_progress(self, stage, completed, total, elapsed):
        from engine.model_packs import format_bytes
        ratio = completed / float(total) if total > 0 else 0.0
        self.pack_progress.setValue(
            max(0, min(1000, int(round(ratio * 1000)))))
        speed = completed / elapsed if elapsed > 0 else 0.0
        if stage == "verifying":
            self.pack_status.setText(
                "Verifying checksum: %s / %s" %
                (format_bytes(completed), format_bytes(total)))
        else:
            self.pack_status.setText(
                "Downloading: %s / %s · %s/s" %
                (format_bytes(completed), format_bytes(total),
                 format_bytes(int(speed))))

    def _on_download_complete(self, result):
        if result.pack.backend == "whisper":
            self.cfg.whisper_model = result.pack.key
            self.cfg.save(self.cfg_path)
        self.activeModelChanged.emit(result.pack.key)
        self.pack_progress.setValue(1000)
        self._last_message = (
            "%s is installed and checksum-verified%s." %
            (result.pack.display_name,
             ("; it will be used automatically for Assamese Auto-Mark"
              if result.pack.backend == "mms" else " and active")))
        self.pack_status.setText(self._last_message)

    def _on_download_failed(self, message):
        self._last_message = "Download failed: %s" % message
        self.pack_status.setText(self._last_message)
        QMessageBox.warning(self, "Model Download Failed", message)

    def _on_download_cancelled(self, message):
        self._last_message = message
        self.pack_status.setText(message)

    def _on_download_thread_done(self):
        self.download_thread.deleteLater()
        self.download_worker = None
        self.download_thread = None
        self.btn_pack_cancel.setEnabled(False)
        self.refresh()

    def cancel_download(self):
        if self.download_worker:
            self.download_worker.stop()
            self.pack_status.setText(
                "Pausing after the current download block…")

    def activate_selected(self):
        from engine.model_packs import is_model_pack_installed
        pack = self._selected_pack()
        if not pack or not is_model_pack_installed(pack.key):
            QMessageBox.warning(
                self, "Model Not Installed",
                "Download and verify this model before selecting it.")
            return
        if pack.backend == "mms":
            QMessageBox.information(
                self, "Precision Pack Ready",
                "Meta MMS Assamese Precision is selected automatically "
                "whenever Auto-Mark runs with Assamese.")
            return
        self.cfg.whisper_model = pack.key
        self.cfg.save(self.cfg_path)
        self._requested_selection = pack.key
        self.activeModelChanged.emit(pack.key)
        self.refresh()

    def remove_selected(self):
        from engine.model_packs import remove_model_pack
        pack = self._selected_pack()
        if not pack:
            return
        if (
                pack.backend == "whisper" and
                pack.key == self.cfg.whisper_model):
            QMessageBox.warning(
                self, "Active Model",
                "Select another installed model before removing the active "
                "model pack.")
            return
        reply = QMessageBox.question(
            self, "Remove Model Pack?",
            "Remove %s from this computer?\n\nIt can be downloaded again "
            "later." % pack.display_name,
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            remove_model_pack(pack.key)
            self._last_message = "Removed %s." % pack.display_name
            self.pack_status.setText(self._last_message)
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(
                self, "Remove Failed", str(exc))

    def reject(self):
        if self.download_thread is not None:
            QMessageBox.information(
                self, "Download Running",
                "Pause the current download before closing this window.")
            return
        super().reject()

    def accept(self):
        if self.download_thread is not None:
            return
        super().accept()


# ---------------------------------------------------------------------------
# First-run guide
# ---------------------------------------------------------------------------
class QuickStartDialog(QDialog):
    """Short, non-technical workflow guide for packaged-app users."""

    def __init__(self, show_on_startup=True, parent=None):
        super().__init__(parent)
        self.open_models_requested = False
        self.setWindowTitle("Quick Start — ScriptureSound QC")
        self.setMinimumSize(720, 590)

        layout = QVBoxLayout(self)
        title = QLabel(
            "<span style='font-size:20px; font-weight:700;'>"
            "Create accurate, reviewable Audio Bible markers</span><br>"
            "<span style='color:#8a97ad;'>No Python or command-line setup "
            "is required in the packaged application.</span>")
        title.setWordWrap(True)
        title.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(title)

        guide = QLabel("""
        <div style='line-height:1.35;'>
          <h3 style='color:#f4c95d;'>1. Auto-Mark status</h3>
          <p><b>Automatic verse marking is temporarily disabled</b> while its
          timing accuracy is being improved. You do not need to download an
          AI model pack for this release.</p>

          <h3 style='color:#4dd9c0;'>2. Choose the spoken language</h3>
          <p>Open <b>Settings → Script STT</b> and select Assamese, Bengali,
          Hindi, English, or another language. Choose Automatic only when
          you genuinely do not know the language.</p>

          <h3 style='color:#4dd9c0;'>3. Load the Bible PDF and audio</h3>
          <p>Click <b>Load Bible PDF</b>, then <b>Add Files</b> or
          <b>Add Folder</b>. Audio files do not need to appear in the same
          order as the PDF—the filename is used to identify its book and
          chapter.</p>

          <h3 style='color:#4dd9c0;'>4. Review existing markers</h3>
          <p>Open <b>Markers &amp; Waveform</b> to inspect, play, add, delete,
          or adjust markers already present in a WAV file. Save changes as a
          reviewed copy so the original remains untouched.</p>

          <h3 style='color:#4dd9c0;'>5. Review before delivery</h3>
          <p>Yellow markers have lower confidence. Listen around them,
          drag or edit their time if needed, and save a reviewed copy.
          Originals are never overwritten.</p>

          <h3 style='color:#4dd9c0;'>6. Master and check</h3>
          <p>Set the desired LUFS, true-peak ceiling, and front/back silence
          in Settings. Run <b>Master Loaded Chapters</b>, then
          <b>Check All</b> and export the QC report.</p>
        </div>
        """)
        guide.setWordWrap(True)
        guide.setTextFormat(Qt.RichText)
        guide.setContentsMargins(14, 8, 14, 8)
        scroll = QScrollArea()
        scroll.setWidget(guide)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll, 1)

        self.show_on_startup = QCheckBox(
            "Show this Quick Start guide when the app opens")
        self.show_on_startup.setChecked(bool(show_on_startup))
        layout.addWidget(self.show_on_startup)

        buttons = QHBoxLayout()
        model_button = QPushButton("Open AI Model Packs")
        model_button.setObjectName("Primary")
        model_button.clicked.connect(self._open_models)
        close_button = QPushButton("Start Working")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(model_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def _open_models(self):
        self.open_models_requested = True
        self.accept()


# ---------------------------------------------------------------------------
# Settings dialog — tabbed layout to fit on screen
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.show_quick_start = cfg.show_quick_start
        self.cfg_path = default_config_path()
        self.setWindowTitle("Settings — Check Standards")
        self.setMinimumSize(560, 620)

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
        self.fix_head = QCheckBox("Apply target silence at the FRONT")
        self.fix_head.setChecked(cfg.fix_head_silence)
        self.fix_tail = QCheckBox("Apply target silence at the BACK")
        self.fix_tail.setChecked(cfg.fix_tail_silence)
        f2.addRow("Target loudness:", self.target)
        f2.addRow("Loudness tolerance (+/-):", self.tol)
        f2.addRow("True-peak ceiling:", self.tp)
        f2.addRow("Edge silence length:", self.sil)
        f2.addRow("Silence tolerance (+/-):", self.siltol)
        f2.addRow("Silence threshold:", self.silth)
        f2.addRow("Expected sample rate:", self.sr)
        f2.addRow("Expected bit depth:", self.bits)
        f2.addRow(self.ck_fmt)
        f2.addRow(QLabel("<b>Silence repair / mastering:</b>"))
        f2.addRow(self.fix_head)
        f2.addRow(self.fix_tail)
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
        self.auto_headings = QCheckBox(
            "Auto-create Heading markers from PDF section headings")
        self.auto_headings.setChecked(cfg.auto_mark_headings)
        f3.addRow("Chapter-title marker text:", self.ct)
        f3.addRow("Heading marker text:", self.hd)
        f3.addRow("Verse marker word:", self.vw)
        f3.addRow(self.req_ct)
        f3.addRow(self.req_hd)
        f3.addRow(self.strict)
        f3.addRow(self.auto_headings)
        tabs.addTab(tab3, "Markers")

        # === Tab 4: Script Verification ===
        tab4 = QWidget()
        f4 = QFormLayout(tab4); f4.setContentsMargins(12, 12, 12, 12)
        from engine.languages import whisper_language_options
        self.whisper_mode = QLineEdit(cfg.whisper_mode)
        self.whisper_mode.setPlaceholderText("local or api")
        self.whisper_model = QComboBox()
        from engine.model_packs import available_model_packs
        for pack in available_model_packs():
            if pack.backend != "whisper":
                continue
            label = pack.display_name
            if pack.recommended:
                label += " (recommended)"
            self.whisper_model.addItem(label, pack.key)
        configured_model_index = self.whisper_model.findData(
            cfg.whisper_model)
        if configured_model_index < 0:
            self.whisper_model.addItem(
                cfg.whisper_model or "large-v3",
                cfg.whisper_model or "large-v3")
            configured_model_index = self.whisper_model.count() - 1
        self.whisper_model.setCurrentIndex(configured_model_index)
        model_row = QWidget()
        model_row_layout = QHBoxLayout(model_row)
        model_row_layout.setContentsMargins(0, 0, 0, 0)
        model_row_layout.addWidget(self.whisper_model, 1)
        self.btn_manage_models_settings = QPushButton("Manage Packs…")
        self.btn_manage_models_settings.clicked.connect(
            self.open_model_pack_manager)
        model_row_layout.addWidget(self.btn_manage_models_settings)
        self.whisper_lang = QComboBox()
        self.whisper_lang.setEditable(True)
        self.whisper_lang.setInsertPolicy(QComboBox.NoInsert)
        self.whisper_lang.setMinimumContentsLength(28)
        self.whisper_lang.addItem("Auto-detect", "")
        languages = whisper_language_options()
        priority_codes = ["as", "en", "bn", "hi", "ta", "te", "ml",
                          "kn", "mr", "gu", "pa", "ur", "ne"]
        added_codes = set()
        for code in priority_codes:
            if code in languages:
                self.whisper_lang.addItem(
                    "%s (%s)" % (languages[code], code), code)
                added_codes.add(code)
        for code, name in sorted(
                languages.items(), key=lambda item: item[1].lower()):
            if code not in added_codes:
                self.whisper_lang.addItem("%s (%s)" % (name, code), code)
        configured_code = (cfg.whisper_language or "").strip().lower()
        selected_index = self.whisper_lang.findData(configured_code)
        if selected_index < 0 and configured_code:
            self.whisper_lang.addItem(
                "Custom language code (%s)" % configured_code,
                configured_code)
            selected_index = self.whisper_lang.count() - 1
        self.whisper_lang.setCurrentIndex(max(0, selected_index))
        self.whisper_lang.setToolTip(
            "Choose the spoken language. Assamese is the default for this "
            "project. Auto-detect is available when the language is unknown.")
        self.api_key = QLineEdit(cfg.openai_api_key)
        self.api_key.setEchoMode(QLineEdit.Password)
        self.api_key.setPlaceholderText("sk-... (only needed for API mode)")
        self.match_thresh = self._d(cfg.script_match_threshold, 0.0, 1.0, 0.05, "")
        self.match_thresh.setToolTip("Minimum similarity (0.0-1.0) to count as a match")
        self.reader_id = QLineEdit(cfg.reader_id)
        self.reader_id.setPlaceholderText(
            "Optional narrator name or recording profile")
        self.alignment_backend = QComboBox()
        from engine.alignment_backends import alignment_backends
        for backend in alignment_backends():
            self.alignment_backend.addItem(backend.name, backend.key)
            index = self.alignment_backend.count() - 1
            self.alignment_backend.setItemData(
                index, backend.description, Qt.ToolTipRole)
        backend_index = self.alignment_backend.findData(
            cfg.alignment_backend)
        self.alignment_backend.setCurrentIndex(max(0, backend_index))
        f4.addRow("Whisper mode:", self.whisper_mode)
        f4.addRow("AI model pack:", model_row)
        f4.addRow("Language:", self.whisper_lang)
        f4.addRow("Reader / narrator:", self.reader_id)
        f4.addRow("OpenAI API key:", self.api_key)
        f4.addRow("Match threshold:", self.match_thresh)
        f4.addRow("Alignment engine:", self.alignment_backend)
        f4.addRow(QLabel(""))
        f4.addRow(QLabel(
            "<i>The dropdown contains every language supported by the "
            "installed Whisper backend.<br>Assamese remains the default; "
            "each project can save a different language.</i>"))
        tabs.addTab(tab4, "Script STT")

        # === Tab 5: VST Plugin Chain ===
        tab5 = QWidget()
        f5 = QVBoxLayout(tab5); f5.setContentsMargins(12, 12, 12, 12); f5.setSpacing(8)
        f5.addWidget(QLabel("<b>VST3 Plugin Chain</b>"))
        f5.addWidget(QLabel("<i>Add as many VST3 plugins as you need. They are applied in order (top to bottom).<br>"
                            "Name them whatever you want (e.g. 'My Limiter', 'Vocal Compressor', etc.)</i>"))

        self.use_vst = QCheckBox("Enable VST3 plugin chain")
        self.use_vst.setChecked(cfg.use_vst_plugins)
        f5.addWidget(self.use_vst)

        # VST list widget
        from PySide6.QtWidgets import QListWidget, QListWidgetItem
        self.vst_list = QListWidget()
        self.vst_list.setMinimumHeight(120)
        self.vst_list.setStyleSheet("QListWidget { background: %s; border: 1px solid %s; }" % (PANEL2, BORDER))
        f5.addWidget(self.vst_list)

        # Load existing VST chain from config
        self._vst_chain = list(cfg.vst_chain) if hasattr(cfg, 'vst_chain') and cfg.vst_chain else []
        # Backward compat: migrate old 3-slot config to chain
        if not self._vst_chain:
            if cfg.vst_compressor_path:
                self._vst_chain.append({"name": "Compressor", "path": cfg.vst_compressor_path})
            if cfg.vst_eq_path:
                self._vst_chain.append({"name": "EQ", "path": cfg.vst_eq_path})
            if cfg.vst_limiter_path:
                self._vst_chain.append({"name": "Limiter", "path": cfg.vst_limiter_path})
        self._refresh_vst_list()

        # Buttons: Add, Remove, Move Up, Move Down
        vst_btn_row = QHBoxLayout()
        btn_add_vst = QPushButton("+ Add Plugin")
        btn_add_vst.clicked.connect(self._add_vst_slot)
        btn_remove_vst = QPushButton("- Remove")
        btn_remove_vst.clicked.connect(self._remove_vst_slot)
        btn_up_vst = QPushButton("Move Up")
        btn_up_vst.clicked.connect(self._move_vst_up)
        btn_down_vst = QPushButton("Move Down")
        btn_down_vst.clicked.connect(self._move_vst_down)
        for b in (btn_add_vst, btn_remove_vst, btn_up_vst, btn_down_vst):
            vst_btn_row.addWidget(b)
        vst_btn_row.addStretch(1)
        f5.addLayout(vst_btn_row)

        f5.addWidget(QLabel(""))
        f5.addWidget(QLabel("<i>Plugins are processed in order. Drag to reorder.<br>"
                            "If a bundled VST3 exists in assets/vst/, it is available as fallback.</i>"))
        f5.addStretch(1)
        tabs.addTab(tab5, "VST Chain")

        # === Tab 6: Updates ===
        tab6 = QWidget()
        f6 = QVBoxLayout(tab6)
        f6.setContentsMargins(12, 12, 12, 12)
        f6.setSpacing(10)
        f6.addWidget(QLabel("<b>Application updates</b>"))
        f6.addWidget(QLabel(
            "ScriptureSoundQC checks the official VerseVox Studio release "
            "feed. Updates are never installed without your permission."))
        self.check_updates_startup = QCheckBox(
            "Automatically check for updates when ScriptureSoundQC starts")
        self.check_updates_startup.setChecked(cfg.check_updates_at_startup)
        f6.addWidget(self.check_updates_startup)
        channel_row = QFormLayout()
        self.update_channel = QComboBox()
        self.update_channel.addItem("Beta and stable releases", "beta")
        self.update_channel.addItem("Stable releases only", "stable")
        channel_index = self.update_channel.findData(cfg.update_channel)
        self.update_channel.setCurrentIndex(max(0, channel_index))
        channel_row.addRow("Release channel:", self.update_channel)
        f6.addLayout(channel_row)
        f6.addWidget(QLabel(
            "Current release: <b>%s</b><br>Use the Check for Updates button "
            "in the Processing tab to check immediately." % APP_VERSION))
        f6.addStretch(1)
        tabs.addTab(tab6, "Updates")

        # OK / Cancel buttons
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        layout.addWidget(bb)

    def _d(self, val, lo, hi, step, suffix):
        s = QDoubleSpinBox(); s.setRange(lo, hi); s.setSingleStep(step)
        s.setDecimals(2); s.setValue(val); s.setSuffix(suffix); return s

    def open_model_pack_manager(self):
        working_config = self.result_config()
        dialog = ModelPackDialog(
            working_config, self.cfg_path, self,
            select_model=str(
                self.whisper_model.currentData() or "large-v3"))
        dialog.exec()
        index = self.whisper_model.findData(
            working_config.whisper_model)
        if index >= 0:
            self.whisper_model.setCurrentIndex(index)

    def _selected_whisper_language(self):
        """Return the selected ISO language code, or empty for auto-detect."""
        data = self.whisper_lang.currentData()
        if data is not None:
            return str(data).strip().lower()
        text = self.whisper_lang.currentText().strip()
        match = re.search(r"\(([a-z]{2,3})\)\s*$", text, re.IGNORECASE)
        return (match.group(1) if match else text).strip().lower()

    def _browse_vst(self, line_edit):
        """Open a file dialog to select a VST3 plugin."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select VST3 Plugin", "",
            "VST3 plugins (*.vst3);;All files (*)")
        if path:
            line_edit.setText(path)

    def _refresh_vst_list(self):
        """Refresh the VST list widget from self._vst_chain."""
        self.vst_list.clear()
        for item in self._vst_chain:
            self.vst_list.addItem("%s  |  %s" % (item.get("name", "Unnamed"), item.get("path", "")))

    def _add_vst_slot(self):
        """Add a new VST plugin slot."""
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Plugin Name",
                                        "Give this plugin a name (e.g. 'My Limiter', 'Vocal Comp'):")
        if not ok or not name.strip():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select VST3 Plugin: %s" % name, "", "VST3 plugins (*.vst3);;All files (*)")
        if not path:
            return
        self._vst_chain.append({"name": name.strip(), "path": path})
        self._refresh_vst_list()

    def _remove_vst_slot(self):
        """Remove selected VST plugin slot."""
        row = self.vst_list.currentRow()
        if row >= 0 and row < len(self._vst_chain):
            self._vst_chain.pop(row)
            self._refresh_vst_list()

    def _move_vst_up(self):
        """Move selected VST plugin up in the chain."""
        row = self.vst_list.currentRow()
        if row > 0:
            self._vst_chain[row], self._vst_chain[row - 1] = self._vst_chain[row - 1], self._vst_chain[row]
            self._refresh_vst_list()
            self.vst_list.setCurrentRow(row - 1)

    def _move_vst_down(self):
        """Move selected VST plugin down in the chain."""
        row = self.vst_list.currentRow()
        if row >= 0 and row < len(self._vst_chain) - 1:
            self._vst_chain[row], self._vst_chain[row + 1] = self._vst_chain[row + 1], self._vst_chain[row]
            self._refresh_vst_list()
            self.vst_list.setCurrentRow(row + 1)

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
            auto_mark_headings=self.auto_headings.isChecked(),
            show_quick_start=self.show_quick_start,
            check_updates_at_startup=self.check_updates_startup.isChecked(),
            update_channel=str(self.update_channel.currentData() or "beta"),
            # Toggle flags
            enable_format=self.en_format.isChecked(),
            enable_loudness=self.en_loudness.isChecked(),
            enable_true_peak=self.en_true_peak.isChecked(),
            enable_head_silence=self.en_head_sil.isChecked(),
            enable_tail_silence=self.en_tail_sil.isChecked(),
            enable_markers=self.en_markers.isChecked(),
            enable_verses=self.en_verses.isChecked(),
            enable_script_verification=self.en_script.isChecked(),
            fix_head_silence=self.fix_head.isChecked(),
            fix_tail_silence=self.fix_tail.isChecked(),
            # VST plugins
            use_vst_plugins=self.use_vst.isChecked(),
            vst_chain=self._vst_chain,
            vst_compressor_path=self._vst_chain[0]["path"] if len(self._vst_chain) > 0 else "",
            vst_limiter_path="",
            vst_eq_path="",
            # Script verification
            whisper_mode=self.whisper_mode.text().strip() or "local",
            whisper_model=str(
                self.whisper_model.currentData() or "large-v3"),
            whisper_language=self._selected_whisper_language(),
            reader_id=self.reader_id.text().strip(),
            openai_api_key=self.api_key.text().strip(),
            script_match_threshold=self.match_thresh.value(),
            alignment_backend=str(
                self.alignment_backend.currentData() or "auto"),
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
        self.script_chapters = {}     # chapter number -> verse dict
        self.script_book_chapters = {}  # (canonical book, chapter) -> verses
        self.script_headings = {}       # chapter -> PDF section headings
        self.script_book_headings = {}  # (canonical book, chapter) -> headings
        self._missing_chapters = []   # missing chapter reports (persisted after check)
        self.current_project = None
        self.language_results = {}
        self.automark_results_by_path = {}
        self.review_items = []
        self.accepted_review_paths = set()
        self.calibration_result = None
        self.calibration_auto_path = ""
        self.calibration_reference_path = ""
        self.marker_session = None
        self.marker_session_path = ""
        self._updating_marker_table = False
        self._automark_total = 0
        self._automark_last_fraction = 0.0
        self._automark_live_preview_shown = False
        self._script_pending_path = ""
        self._project_dirty = False
        self._audio_player = None
        self._audio_output = None
        self.update_thread = None
        self.update_worker = None
        self._update_check_manual = False
        self.setAcceptDrops(True)
        self._build_ui()
        if not ffmpeg_available():
            self.status("Warning: ffmpeg not found — loudness & true-peak checks will be skipped.")
        else:
            self.status("Ready. Add WAV files or drag them onto the window.")
        if self.cfg.show_quick_start:
            QTimer.singleShot(650, self.open_quick_start)
        if self.cfg.check_updates_at_startup:
            QTimer.singleShot(
                3000, lambda: self.check_for_updates(manual=False))

    def _build_ui(self):
        central = QWidget(); self.setCentralWidget(central)
        outer = QVBoxLayout(central); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        # Set window icon
        icon = _load_logo_icon()
        if not icon.isNull():
            self.setWindowIcon(icon)

        # Clean, transparent-brand header.
        header = QFrame(); header.setObjectName("Header")
        header.setMinimumHeight(76)
        hl = QHBoxLayout(header); hl.setContentsMargins(18, 9, 18, 9); hl.setSpacing(14)

        # Logo icon in header (rendered from SVG)
        logo_lbl = QLabel()
        logo_path = _asset("logo.svg")
        if os.path.isfile(logo_path):
            renderer = QSvgRenderer(logo_path)
            logo_px = QPixmap(50, 50)
            logo_px.fill(Qt.transparent)
            p = QPainter(logo_px)
            renderer.render(p)
            p.end()
            logo_lbl.setPixmap(logo_px)
        logo_lbl.setFixedSize(50, 50)
        hl.addWidget(logo_lbl)

        # Title block
        title_block = QVBoxLayout(); title_block.setSpacing(1)
        title = QLabel("<span style='color:#e6ebf5; font-size:22px; font-weight:700;'>Scripture</span>"
                       "<span style='color:#d4a843; font-size:22px; font-weight:700;'>Sound</span>"
                       "<span style='color:#4dd9c0; font-size:22px; font-weight:700;'>QC</span>"
                       "  <span style='color:#8a97ad; font-size:12px; font-weight:600;'>%s</span>" % APP_VERSION)
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
        self.summary_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        hl.addWidget(self.summary_lbl)
        outer.addWidget(header)

        body = QWidget(); bl = QVBoxLayout(body); bl.setContentsMargins(12, 12, 12, 8)
        outer.addWidget(body, 1)

        # Primary toolbar: project intake and QC actions only.
        bar = QHBoxLayout()
        self.btn_project = QPushButton("Project ▾")
        self.btn_project.clicked.connect(self.project_menu)
        self.btn_add = QPushButton("Add Files…"); self.btn_add.clicked.connect(self.add_files)
        self.btn_folder = QPushButton("Add Folder…"); self.btn_folder.clicked.connect(self.add_folder)
        self.btn_script = QPushButton("Load Bible PDF…"); self.btn_script.clicked.connect(self.load_script)
        self.btn_clear = QPushButton("Clear"); self.btn_clear.clicked.connect(self.clear_all)
        self.btn_settings = QPushButton("Settings…"); self.btn_settings.clicked.connect(self.open_settings)
        self.btn_about = QPushButton("About"); self.btn_about.clicked.connect(self.open_about)
        self.btn_changelog = QPushButton("Changelog"); self.btn_changelog.clicked.connect(self.open_changelog)
        self.btn_updates = QPushButton("Check for Updates")
        self.btn_updates.clicked.connect(
            lambda: self.check_for_updates(manual=True))
        self.btn_export = QPushButton("Export ▾"); self.btn_export.clicked.connect(self.export_menu)
        self.btn_stop = QPushButton("Stop"); self.btn_stop.clicked.connect(self.stop_checks); self.btn_stop.setEnabled(False)
        self.btn_check = QPushButton("Check All"); self.btn_check.setObjectName("Primary"); self.btn_check.clicked.connect(self.run_checks)
        for b in (self.btn_project, self.btn_add, self.btn_folder,
                  self.btn_script, self.btn_clear):
            bar.addWidget(b)
        bar.addStretch(1)
        self.script_lbl = QLabel("")
        self.script_lbl.setObjectName("Subtitle")
        bar.addWidget(self.script_lbl)
        for b in (self.btn_settings, self.btn_export, self.btn_stop, self.btn_check):
            bar.addWidget(b)
        bl.addLayout(bar)

        # Main workspace.
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.setObjectName("WorkspaceTabs")
        self.workspace_tabs.setDocumentMode(True)
        bl.addWidget(self.workspace_tabs, 1)

        # --- Chapters / QC tab ---
        chapters_tab = QWidget()
        chapters_layout = QVBoxLayout(chapters_tab)
        chapters_layout.setContentsMargins(0, 8, 0, 0)
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.itemSelectionChanged.connect(self.on_select)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Interactive)
        column_widths = [210, 135, 74, 76, 92, 86, 78, 78, 76, 76, 92]
        for column, width in enumerate(column_widths):
            self.table.setColumnWidth(column, width)
        chapters_layout.addWidget(self.table, 1)
        self.issue = QLabel("Select a chapter to inspect."); self.issue.setObjectName("IssueBar")
        self.issue.setWordWrap(True); self.issue.setTextFormat(Qt.RichText)
        self.issue.setContentsMargins(12, 8, 12, 8)
        chapters_layout.addWidget(self.issue)
        self.workspace_tabs.addTab(chapters_tab, "Chapters & QC")

        # --- Marker inspector / waveform tab ---
        markers_tab = QWidget()
        markers_layout = QVBoxLayout(markers_tab)
        markers_layout.setContentsMargins(0, 8, 0, 0)
        self.marker_title = QLabel(
            "<b>Select a chapter in the Chapters & QC tab.</b>")
        self.marker_title.setTextFormat(Qt.RichText)
        markers_layout.addWidget(self.marker_title)
        self.marker_summary = QLabel("")
        self.marker_summary.setObjectName("Subtitle")
        markers_layout.addWidget(self.marker_summary)
        marker_controls = QHBoxLayout()
        self.btn_marker_play = QPushButton("Play Around Marker")
        self.btn_marker_play.clicked.connect(self.play_selected_marker)
        self.btn_marker_add = QPushButton("+ Add")
        self.btn_marker_add.clicked.connect(self.add_marker)
        self.btn_marker_delete = QPushButton("- Delete")
        self.btn_marker_delete.clicked.connect(self.delete_marker)
        self.btn_marker_undo = QPushButton("Undo")
        self.btn_marker_undo.clicked.connect(self.undo_marker_edit)
        self.btn_marker_redo = QPushButton("Redo")
        self.btn_marker_redo.clicked.connect(self.redo_marker_edit)
        self.btn_marker_speech = QPushButton("Snap to Speech")
        self.btn_marker_speech.clicked.connect(
            self.snap_marker_to_speech)
        self.btn_marker_zero = QPushButton("Snap to Zero")
        self.btn_marker_zero.clicked.connect(
            self.snap_marker_to_zero)
        self.btn_marker_save = QPushButton("Save Reviewed Copy…")
        self.btn_marker_save.setObjectName("Primary")
        self.btn_marker_save.clicked.connect(self.save_marker_edits)
        for button in (
                self.btn_marker_play, self.btn_marker_add,
                self.btn_marker_delete, self.btn_marker_undo,
                self.btn_marker_redo, self.btn_marker_speech,
                self.btn_marker_zero, self.btn_marker_save):
            marker_controls.addWidget(button)
        marker_controls.addStretch(1)
        markers_layout.addLayout(marker_controls)
        marker_split = QSplitter(Qt.Vertical)
        self.marker_table = QTableWidget(0, 7)
        self.marker_table.setHorizontalHeaderLabels(
            ["Type", "Label", "Time", "Sample", "Confidence",
             "Method", "Duration"])
        self.marker_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.marker_table.setSelectionMode(QTableWidget.SingleSelection)
        self.marker_table.setEditTriggers(
            QAbstractItemView.DoubleClicked |
            QAbstractItemView.SelectedClicked)
        self.marker_table.setAlternatingRowColors(True)
        self.marker_table.itemSelectionChanged.connect(
            self.on_marker_selection_changed)
        self.marker_table.itemChanged.connect(
            self.on_marker_item_changed)
        marker_header = self.marker_table.horizontalHeader()
        marker_header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        marker_header.setSectionResizeMode(1, QHeaderView.Stretch)
        for column in range(2, 7):
            marker_header.setSectionResizeMode(
                column, QHeaderView.ResizeToContents)
        marker_split.addWidget(self.marker_table)
        self.wave = WaveformView()
        self.wave.set_editable(True)
        self.wave.markerSelected.connect(
            lambda index: self.marker_table.setCurrentCell(index, 0))
        self.wave.markerMoved.connect(self.on_wave_marker_moved)
        marker_split.addWidget(self.wave)
        marker_split.setSizes([260, 360])
        markers_layout.addWidget(marker_split, 1)
        self.workspace_tabs.addTab(markers_tab, "Markers & Waveform")

        # --- Unified review queue ---
        review_tab = QWidget()
        review_layout = QVBoxLayout(review_tab)
        review_layout.setContentsMargins(0, 8, 0, 0)
        review_header = QHBoxLayout()
        review_header.addWidget(QLabel(
            "<b>Files and markers requiring human review</b>"))
        review_header.addStretch(1)
        self.btn_review_refresh = QPushButton("Refresh Queue")
        self.btn_review_refresh.clicked.connect(self.refresh_review_queue)
        self.btn_review_open = QPushButton("Open Selected")
        self.btn_review_open.clicked.connect(self.open_selected_review)
        self.btn_review_accept = QPushButton("Accept Selected File")
        self.btn_review_accept.clicked.connect(self.accept_selected_review_file)
        review_header.addWidget(self.btn_review_refresh)
        review_header.addWidget(self.btn_review_open)
        review_header.addWidget(self.btn_review_accept)
        review_layout.addLayout(review_header)
        self.review_table = QTableWidget(0, 6)
        self.review_table.setHorizontalHeaderLabels(
            ["Severity", "File", "Category", "Marker", "Time", "Message"])
        self.review_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.review_table.setSelectionMode(QTableWidget.SingleSelection)
        self.review_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.review_table.setAlternatingRowColors(True)
        self.review_table.cellDoubleClicked.connect(
            lambda _row, _column: self.open_selected_review())
        review_header_view = self.review_table.horizontalHeader()
        for column in range(5):
            review_header_view.setSectionResizeMode(
                column, QHeaderView.ResizeToContents)
        review_header_view.setSectionResizeMode(5, QHeaderView.Stretch)
        review_layout.addWidget(self.review_table, 1)
        self.review_summary = QLabel("No review items yet.")
        self.review_summary.setObjectName("Subtitle")
        review_layout.addWidget(self.review_summary)
        self.workspace_tabs.addTab(review_tab, "Review Queue")

        # --- Accuracy calibration ---
        calibration_tab = QWidget()
        calibration_layout = QVBoxLayout(calibration_tab)
        calibration_layout.setContentsMargins(0, 8, 0, 0)
        calibration_controls = QHBoxLayout()
        self.btn_cal_auto = QPushButton("Automatic Markers…")
        self.btn_cal_auto.clicked.connect(self.choose_calibration_automatic)
        self.btn_cal_reference = QPushButton("Reference Markers…")
        self.btn_cal_reference.clicked.connect(
            self.choose_calibration_reference)
        self.calibration_threshold = QDoubleSpinBox()
        self.calibration_threshold.setRange(0.01, 5.0)
        self.calibration_threshold.setDecimals(3)
        self.calibration_threshold.setValue(0.25)
        self.calibration_threshold.setSuffix(" s limit")
        self.btn_cal_run = QPushButton("Compare Accuracy")
        self.btn_cal_run.setObjectName("Primary")
        self.btn_cal_run.clicked.connect(self.run_calibration)
        self.btn_cal_export = QPushButton("Export Results ▾")
        self.btn_cal_export.clicked.connect(self.export_calibration_menu)
        for widget in (
                self.btn_cal_auto, self.btn_cal_reference,
                self.calibration_threshold, self.btn_cal_run,
                self.btn_cal_export):
            calibration_controls.addWidget(widget)
        calibration_controls.addStretch(1)
        calibration_layout.addLayout(calibration_controls)
        self.calibration_paths = QLabel(
            "Choose an automatic marked WAV/CSV and a manually checked "
            "reference WAV/CSV.")
        self.calibration_paths.setWordWrap(True)
        self.calibration_paths.setObjectName("Subtitle")
        calibration_layout.addWidget(self.calibration_paths)
        self.calibration_summary = QLabel("No comparison has been run.")
        self.calibration_summary.setObjectName("IssueBar")
        self.calibration_summary.setContentsMargins(12, 8, 12, 8)
        calibration_layout.addWidget(self.calibration_summary)
        self.calibration_table = QTableWidget(0, 6)
        self.calibration_table.setHorizontalHeaderLabels([
            "Marker", "Automatic", "Reference", "Signed Error",
            "Absolute Error", "Result"])
        self.calibration_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.calibration_table.setAlternatingRowColors(True)
        calibration_header = self.calibration_table.horizontalHeader()
        calibration_header.setSectionResizeMode(0, QHeaderView.Stretch)
        for column in range(1, 6):
            calibration_header.setSectionResizeMode(
                column, QHeaderView.ResizeToContents)
        calibration_layout.addWidget(self.calibration_table, 1)
        self.workspace_tabs.addTab(calibration_tab, "Calibration")

        # --- Processing tab ---
        processing_tab = QWidget()
        processing_layout = QVBoxLayout(processing_tab)
        processing_layout.setContentsMargins(16, 16, 16, 16)
        processing_layout.setSpacing(12)
        processing_layout.addWidget(QLabel(
            "<b style='font-size:16px'>Chapter Processing</b>"))
        processing_description = QLabel(
            "Automatic verse marking is temporarily disabled while its timing "
            "accuracy is being improved. Mastering, silence processing, marker "
            "review, QC, and exports remain available.")
        processing_description.setWordWrap(True)
        processing_layout.addWidget(processing_description)
        process_buttons_top = QHBoxLayout()
        process_buttons_bottom = QHBoxLayout()
        self.btn_automark = QPushButton("Auto-Mark — Temporarily Disabled")
        self.btn_automark.setToolTip(AUTO_MARK_DISABLED_MESSAGE)
        self.btn_automark.clicked.connect(self.run_auto_mark)
        self.btn_automark.setEnabled(AUTO_MARK_ENABLED)
        self.btn_detect_language = QPushButton("Detect Languages")
        self.btn_detect_language.clicked.connect(self.run_language_detection)
        self.btn_model_packs = QPushButton("AI Model Packs…")
        self.btn_model_packs.clicked.connect(self.open_model_packs)
        self.btn_fixsilence = QPushButton("Apply Silence Settings")
        self.btn_fixsilence.clicked.connect(self.run_fix_silence)
        self.btn_master = QPushButton("Master Loaded Chapters")
        self.btn_master.clicked.connect(self.run_master)
        self.btn_extract_markers = QPushButton("Export Marker CSV")
        self.btn_extract_markers.clicked.connect(self.run_extract_markers)
        process_buttons_top.addWidget(self.btn_automark)
        process_buttons_top.addWidget(self.btn_detect_language)
        process_buttons_top.addWidget(self.btn_model_packs)
        process_buttons_top.addWidget(self.btn_master)
        process_buttons_top.addStretch(1)
        process_buttons_bottom.addWidget(self.btn_fixsilence)
        process_buttons_bottom.addWidget(self.btn_extract_markers)
        process_buttons_bottom.addStretch(1)
        processing_layout.addLayout(process_buttons_top)
        processing_layout.addLayout(process_buttons_bottom)
        self.processing_help = QLabel("")
        self.processing_help.setWordWrap(True)
        self.processing_help.setObjectName("IssueBar")
        self.processing_help.setContentsMargins(12, 12, 12, 12)
        processing_layout.addWidget(self.processing_help)
        utility_buttons = QHBoxLayout()
        self.btn_quick_start = QPushButton("Quick Start")
        self.btn_quick_start.clicked.connect(self.open_quick_start)
        utility_buttons.addWidget(self.btn_quick_start)
        utility_buttons.addWidget(self.btn_about)
        utility_buttons.addWidget(self.btn_changelog)
        utility_buttons.addWidget(self.btn_updates)
        utility_buttons.addStretch(1)
        processing_layout.addLayout(utility_buttons)
        processing_layout.addStretch(1)
        self.workspace_tabs.addTab(processing_tab, "Processing")
        self._refresh_processing_help()

        self.operation_detail = QLabel("")
        self.operation_detail.setObjectName("Subtitle")
        self.operation_detail.setVisible(False)
        bl.addWidget(self.operation_detail)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setTextVisible(True)
        self.progress.setFixedHeight(22)
        bl.addWidget(self.progress)

        self.setStatusBar(QStatusBar())
        _cr = QLabel("Created by VerseVox Studio"); _cr.setObjectName("Credit")
        self.statusBar().addPermanentWidget(_cr)
        self._install_marker_shortcuts()

    def _install_marker_shortcuts(self):
        shortcuts = [
            ("Ctrl+Z", self.undo_marker_edit),
            ("Ctrl+Y", self.redo_marker_edit),
            ("Delete", self.delete_marker),
            ("Space", self.play_selected_marker),
            ("Ctrl+Down", lambda: self.select_relative_marker(1)),
            ("Ctrl+Up", lambda: self.select_relative_marker(-1)),
            ("Ctrl+Shift+S", self.save_marker_edits),
        ]
        self._marker_actions = []
        for shortcut, callback in shortcuts:
            action = QAction(self)
            action.setShortcut(shortcut)
            action.triggered.connect(callback)
            self.addAction(action)
            self._marker_actions.append(action)

    def select_relative_marker(self, delta):
        if self.marker_table.rowCount() <= 0:
            return
        current = self._selected_marker_row()
        target = max(
            0, min(self.marker_table.rowCount() - 1,
                   (current if current >= 0 else 0) + delta))
        self.marker_table.setCurrentCell(target, 0)

    def status(self, msg):
        self.statusBar().showMessage(msg)

    def _refresh_processing_help(self):
        if not hasattr(self, "processing_help"):
            return
        sides = []
        if self.cfg.fix_head_silence:
            sides.append("front")
        if self.cfg.fix_tail_silence:
            sides.append("back")
        side_text = " and ".join(sides) if sides else "neither edge"
        self.processing_help.setText(
            "<b>Current processing profile</b><br>"
            "<span style='color:#f4c95d'><b>Auto verse marking: "
            "Temporarily disabled</b></span><br>"
            "Silence: <b>%.1f seconds</b> applied to <b>%s</b><br>"
            "Mastering target: <b>%.1f LUFS</b> · true peak "
            "<b>%.1f dBTP</b> · output <b>%d Hz / %d-bit</b><br><br>"
            "<span style='color:%s'>Change these values in Settings. "
            "Existing WAV markers can be reviewed and edited in "
            "Markers & Waveform.</span>" %
            (self.cfg.silence_seconds,
             side_text,
             self.cfg.target_lufs,
             self.cfg.true_peak_max,
             self.cfg.expected_sample_rate,
             self.cfg.expected_bits,
             MUTED))

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

    # project files
    def project_menu(self):
        menu = QMenu(self)
        action_new = QAction("New Project…", self)
        action_open = QAction("Open Project…", self)
        action_save = QAction("Save Project", self)
        action_save_as = QAction("Save Project As…", self)
        action_new.triggered.connect(self.new_project_dialog)
        action_open.triggered.connect(self.open_project_dialog)
        action_save.triggered.connect(self.save_project)
        action_save_as.triggered.connect(
            lambda: self.save_project(save_as=True))
        for action in (
                action_new, action_open, action_save, action_save_as):
            menu.addAction(action)
        menu.exec(
            self.btn_project.mapToGlobal(
                self.btn_project.rect().bottomLeft()))

    def new_project_dialog(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Create Audio Bible Project", "AudioBible.bacproject",
            "Bible Audio project (*.bacproject)")
        if not path:
            return
        if not path.lower().endswith(".bacproject"):
            path += ".bacproject"
        name = os.path.splitext(os.path.basename(path))[0]
        root_dir = os.path.dirname(path)
        project = new_project(name, path, root_dir)
        project.preset = self._project_preset_from_config()
        project.save()
        self.current_project = project
        self._project_dirty = False
        self._refresh_project_label()
        self.status("Created project: %s" % name)

    def open_project_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Audio Bible Project", "",
            "Bible Audio project (*.bacproject);;JSON files (*.json)")
        if not path:
            return
        try:
            project = AudioBibleProject.load(path)
        except Exception as exc:
            QMessageBox.warning(
                self, "Project Error", "Could not open project: %s" % exc)
            return
        self.clear_all(keep_project=True)
        self.current_project = project
        self.files = [
            item.path for item in project.files
            if os.path.isfile(item.path)]
        self.accepted_review_paths = {
            item.path for item in project.files
            if item.status == "approved"}
        self._apply_project_preset(project.preset)
        self._refresh_table()
        self._project_dirty = False
        self._refresh_project_label()
        if project.script_path and os.path.isfile(project.script_path):
            self._begin_script_load(project.script_path)
        self.status(
            "Opened project: %s (%d available files)" %
            (project.name, len(self.files)))

    def save_project(self, save_as=False):
        if self.current_project is None:
            self.new_project_dialog()
            return
        path = self.current_project.project_path
        if save_as or not path:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Audio Bible Project", path or
                "AudioBible.bacproject",
                "Bible Audio project (*.bacproject)")
            if not path:
                return
            if not path.lower().endswith(".bacproject"):
                path += ".bacproject"
        self._sync_project_state()
        try:
            self.current_project.save(path)
            self._project_dirty = False
            self._refresh_project_label()
            self.status("Project saved: %s" % path)
        except Exception as exc:
            QMessageBox.warning(
                self, "Project Error", "Could not save project: %s" % exc)

    def _project_preset_from_config(self):
        return ProjectPreset(
            language=self.cfg.whisper_language,
            whisper_model=self.cfg.whisper_model,
            alignment_backend=self.cfg.alignment_backend,
            auto_mark_headings=self.cfg.auto_mark_headings,
            reader_id=self.cfg.reader_id,
            target_lufs=self.cfg.target_lufs,
            lufs_tolerance=self.cfg.lufs_tolerance,
            true_peak_max=self.cfg.true_peak_max,
            silence_seconds=self.cfg.silence_seconds,
            fix_front_silence=self.cfg.fix_head_silence,
            fix_back_silence=self.cfg.fix_tail_silence,
        )

    def _apply_project_preset(self, preset):
        self.cfg.whisper_language = preset.language
        self.cfg.whisper_model = preset.whisper_model
        self.cfg.alignment_backend = preset.alignment_backend
        self.cfg.auto_mark_headings = preset.auto_mark_headings
        self.cfg.reader_id = preset.reader_id
        self.cfg.target_lufs = preset.target_lufs
        self.cfg.lufs_tolerance = preset.lufs_tolerance
        self.cfg.true_peak_max = preset.true_peak_max
        self.cfg.silence_seconds = preset.silence_seconds
        self.cfg.fix_head_silence = preset.fix_front_silence
        self.cfg.fix_tail_silence = preset.fix_back_silence
        self._refresh_processing_help()

    def _sync_project_state(self):
        if self.current_project is None:
            return
        self.current_project.preset = self._project_preset_from_config()
        self.current_project.script_path = self.script_pdf_path
        self.current_project.add_files(self.files)
        for path in self.files:
            language = self.language_results.get(path)
            changes = {}
            if language is not None and language.ok:
                changes.update(
                    detected_language=language.language,
                    language_confidence=language.confidence)
            reasons = [
                item.message for item in self.review_items
                if item.path == path]
            if reasons:
                changes.update(status="review", review_reasons=reasons)
            elif path in self.reports:
                changes.update(
                    status="approved" if self.reports[path].passed
                    else "failed",
                    review_reasons=[])
            if changes:
                self.current_project.update_file(path, **changes)

    def _refresh_project_label(self):
        if self.current_project is None:
            self.btn_project.setText("Project ▾")
            return
        dirty = " *" if self._project_dirty else ""
        self.btn_project.setText(
            "%s%s ▾" % (self.current_project.name, dirty))

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Select WAV files", "", "WAV files (*.wav)")
        self._add_paths(paths)

    def add_folder(self):
        d = QFileDialog.getExistingDirectory(self, "Select folder of WAV files")
        if d:
            self._add_paths(self._folder_wavs(d))

    def load_script(self):
        """Choose a chapter-aware PDF/text script and load it in background."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Script PDF", "", "PDF files (*.pdf);;Text files (*.txt);;All files (*)")
        if not path:
            return
        self._begin_script_load(path)

    def _begin_script_load(self, path):
        if self.thread is not None:
            self.status("Another operation is in progress.")
            return
        self._script_pending_path = path
        self.thread = QThread()
        self.worker = ScriptLoadWorker(path)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.loaded.connect(self._on_script_loaded)
        self.worker.failed.connect(self._on_script_failed)
        self.worker.finished.connect(self._finish_script_load)
        self.btn_script.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self.status("Loading and caching script: %s…" %
                    os.path.basename(path))
        self.thread.start()

    def _on_script_loaded(self, result, from_cache, cache_path):
        path = self._script_pending_path
        if not result.ok:
            message = "Could not parse verses from the file."
            if result.warnings:
                message += "\n" + "\n".join(result.warnings[:5])
            QMessageBox.warning(self, "Script Parse Error", message)
            return
        self.script_pdf_path = path
        self.script_chapters = result.chapters
        self.script_book_chapters = result.book_chapters
        self.script_headings = result.headings
        self.script_book_headings = result.book_headings
        self.script_verses = (
            next(iter(result.chapters.values()))
            if len(result.chapters) == 1 else {})
        self.script_lbl.setText(
            "Script: %s (%s%d chapter%s / %d verses / %d headings)" %
            (os.path.basename(path),
             ("%d books / " % result.total_books)
             if result.total_books else "",
             result.total_chapters,
             "" if result.total_chapters == 1 else "s",
             result.total_verses,
             result.total_headings))
        source = "cache" if from_cache else "PDF"
        self.status(
            "Loaded script from %s: %d chapter(s), %d verses." %
            (source, result.total_chapters, result.total_verses))
        self._project_dirty = True
        self._refresh_project_label()

    def _on_script_failed(self, message):
        QMessageBox.warning(
            self, "Script Load Error",
            "Failed to load script: %s" % message)

    def _finish_script_load(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self.btn_script.setEnabled(True)
        self.progress.setVisible(False)
        self.progress.setRange(0, 1)

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
            absolute = os.path.abspath(p)
            if absolute not in self.files:
                self.files.append(absolute); new += 1
        if new:
            if self.current_project is not None:
                self.current_project.add_files(self.files)
                self._project_dirty = True
                self._refresh_project_label()
            self._refresh_table()
            self.status("Added %d file(s). %d total." % (new, len(self.files)))

    def clear_all(self, keep_project=False):
        self.files = []; self.reports = {}; self.wave_cache = {}
        self.script_pdf_path = ""; self.script_verses = {}; self.script_chapters = {}
        self.script_book_chapters = {}
        self.script_headings = {}
        self.script_book_headings = {}
        self.language_results = {}
        self.automark_results_by_path = {}
        self.review_items = []
        self.accepted_review_paths = set()
        self.marker_session = None
        self.marker_session_path = ""
        self.calibration_result = None
        self.calibration_auto_path = ""
        self.calibration_reference_path = ""
        self._missing_chapters = []
        if not keep_project:
            self.current_project = None
            self._project_dirty = False
            self._refresh_project_label()
        self.script_lbl.setText("")
        self.table.setRowCount(0); self.wave.clear(); self.issue.setText("Select a chapter to inspect.")
        self.marker_table.setRowCount(0)
        if hasattr(self, "review_table"):
            self.review_table.setRowCount(0)
        if hasattr(self, "calibration_table"):
            self.calibration_table.setRowCount(0)
            self.calibration_summary.setText(
                "No comparison has been run.")
            self._refresh_calibration_paths()
        self.marker_title.setText("<b>Select a chapter in the Chapters & QC tab.</b>")
        self.marker_summary.setText("")
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
        self._show_markers(path, r)

    def _show_markers(self, path, report=None):
        from engine.bible_db import parse_filename

        self.wave.set_editable(True)
        bc = parse_filename(path)
        identity = (
            "%s %d" % (bc.book, bc.chapter)
            if bc else os.path.basename(path))
        self.marker_title.setText(
            "<b>%s</b> — %s" % (identity, os.path.basename(path)))

        try:
            if path != self.marker_session_path:
                self.marker_session = MarkerEditSession(path)
                self.marker_session_path = path
        except Exception as exc:
            self.marker_session = None
            self.marker_session_path = ""
            self.marker_table.setRowCount(0)
            self.marker_summary.setText("Could not read markers: %s" % exc)
            return
        self._render_marker_session()

    def _editor_marker_type(self, label):
        text = (label or "").strip()
        low = text.lower()
        if low == self.cfg.chapter_title_name.strip().lower():
            return "Chapter Title"
        if re.match(
                r"^%s(?:\s*\d*)$" %
                re.escape(self.cfg.heading_name.strip()),
                text, re.IGNORECASE):
            return "Heading"
        verse_match = re.match(
            r"^%s\s*0*(\d+)$" %
            re.escape(self.cfg.verse_word.strip()),
            text, re.IGNORECASE)
        if verse_match:
            return "Verse %d" % int(verse_match.group(1))
        if low.startswith(self.cfg.verse_word.strip().lower()):
            return "Malformed"
        return "Unknown"

    def _auto_marker_metadata(self, marker):
        result = self.automark_results_by_path.get(
            self.marker_session_path)
        if result is None:
            return marker.confidence, marker.method
        time_s = marker.sample_offset / float(
            self.marker_session.info.sample_rate)
        candidates = [
            candidate for candidate in result.markers
            if candidate.label == marker.label]
        if not candidates:
            return marker.confidence, marker.method
        candidate = min(
            candidates, key=lambda item: abs(item.time_s - time_s))
        return candidate.confidence, candidate.method

    def _render_marker_session(self, select_row=-1):
        if self.marker_session is None:
            return
        self._updating_marker_table = True
        markers = self.marker_session.markers
        self.marker_table.setRowCount(len(markers))
        counts = {
            "Chapter Title": 0, "Heading": 0, "Verse": 0,
            "attention": 0}
        for row, marker in enumerate(markers):
            marker_type = self._editor_marker_type(marker.label)
            if marker_type == "Chapter Title":
                counts["Chapter Title"] += 1
            elif marker_type == "Heading":
                counts["Heading"] += 1
            elif marker_type.startswith("Verse "):
                counts["Verse"] += 1
            else:
                counts["attention"] += 1
            confidence, method = self._auto_marker_metadata(marker)
            attention_threshold = (
                0.75 if method.startswith("mms-") else 0.55)
            low_confidence = (
                confidence < attention_threshold or
                "interpolated" in method)
            if (
                    low_confidence and
                    marker_type not in ("Malformed", "Unknown")):
                counts["attention"] += 1
            time_s = marker.sample_offset / float(
                self.marker_session.info.sample_rate)
            values = [
                marker_type, marker.label, "%.3f" % time_s,
                str(marker.sample_offset), "%.0f%%" % (confidence * 100),
                method, "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column not in (1, 2):
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if marker_type in ("Malformed", "Unknown"):
                    item.setBackground(FAILBG)
                    item.setForeground(FAILFG)
                elif low_confidence:
                    item.setBackground(QColor(79, 63, 26))
                    item.setForeground(QColor(255, 214, 120))
                self.marker_table.setItem(row, column, item)
        self._updating_marker_table = False
        self.marker_summary.setText(
            "%d markers · %d chapter title · %d headings · %d verses · "
            "%d need attention · double-click Label or Time to edit" %
            (len(markers), counts["Chapter Title"], counts["Heading"],
             counts["Verse"], counts["attention"]))
        self._sync_wave_from_marker_session()
        if 0 <= select_row < len(markers):
            self.marker_table.setCurrentCell(select_row, 0)

    def _sync_wave_from_marker_session(self):
        if self.marker_session is None:
            return
        wave = self.wave_cache.get(self.marker_session_path)
        if wave is None:
            try:
                wave = extract_waveform(self.marker_session_path)
                self.wave_cache[self.marker_session_path] = wave
            except Exception:
                return
        wave.markers = [
            (marker.sample_offset /
             float(self.marker_session.info.sample_rate), marker.label)
            for marker in self.marker_session.markers]
        self.wave.update()

    def _selected_marker_row(self):
        rows = self.marker_table.selectionModel().selectedRows()
        if not rows:
            return -1
        return rows[0].row()

    def on_marker_selection_changed(self):
        row = self._selected_marker_row()
        if row < 0:
            return
        self.wave._selected_marker_index = row
        self.wave.update()

    def _parse_marker_time(self, value):
        text = value.strip().lower().rstrip("s")
        if ":" not in text:
            return float(text)
        parts = text.split(":")
        if len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        if len(parts) == 3:
            return (float(parts[0]) * 3600.0 +
                    float(parts[1]) * 60.0 + float(parts[2]))
        raise ValueError("Invalid marker time.")

    def on_marker_item_changed(self, item):
        if self._updating_marker_table or self.marker_session is None:
            return
        row, column = item.row(), item.column()
        if row < 0 or row >= len(self.marker_session.markers):
            return
        try:
            if column == 1:
                self.marker_session.rename(row, item.text())
                selected = row
            elif column == 2:
                selected = self.marker_session.move(
                    row, self._parse_marker_time(item.text()))
            else:
                return
            self._render_marker_session(selected)
            self._mark_project_dirty("marker_edit")
        except Exception as exc:
            QMessageBox.warning(
                self, "Marker Edit", "Could not edit marker: %s" % exc)
            self._render_marker_session(row)

    def on_wave_marker_moved(self, index, old_time, new_time):
        if self.marker_session is None:
            return
        selected = self.marker_session.move(index, new_time)
        self._render_marker_session(selected)
        self.status(
            "Marker moved %.3fs -> %.3fs" % (old_time, new_time))
        self._mark_project_dirty("marker_drag")

    def add_marker(self):
        if self.marker_session is None:
            return
        from PySide6.QtWidgets import QInputDialog
        label, accepted = QInputDialog.getText(
            self, "Add Marker", "Marker label:")
        if not accepted or not label.strip():
            return
        row = self._selected_marker_row()
        if row >= 0:
            time_s = self.marker_session.time_s(row) + 0.1
        else:
            start, end = self.wave._visible_range()
            time_s = (start + end) / 2.0
        selected = self.marker_session.add(label, time_s)
        self._render_marker_session(selected)
        self._mark_project_dirty("marker_add")

    def delete_marker(self):
        row = self._selected_marker_row()
        if self.marker_session is None or row < 0:
            return
        self.marker_session.delete(row)
        self._render_marker_session(
            min(row, len(self.marker_session.markers) - 1))
        self._mark_project_dirty("marker_delete")

    def undo_marker_edit(self):
        if self.marker_session and self.marker_session.undo():
            self._render_marker_session()

    def redo_marker_edit(self):
        if self.marker_session and self.marker_session.redo():
            self._render_marker_session()

    def snap_marker_to_speech(self):
        row = self._selected_marker_row()
        if self.marker_session is None or row < 0:
            return
        selected = self.marker_session.snap_to_speech_onset(row)
        self._render_marker_session(selected)
        self._mark_project_dirty("marker_snap_speech")

    def snap_marker_to_zero(self):
        row = self._selected_marker_row()
        if self.marker_session is None or row < 0:
            return
        selected = self.marker_session.snap_to_zero_crossing(row)
        self._render_marker_session(selected)
        self._mark_project_dirty("marker_snap_zero")

    def play_selected_marker(self):
        row = self._selected_marker_row()
        if self.marker_session is None or row < 0:
            return
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            if self._audio_player is None:
                self._audio_output = QAudioOutput(self)
                self._audio_player = QMediaPlayer(self)
                self._audio_player.setAudioOutput(self._audio_output)
            time_s = self.marker_session.time_s(row)
            self._audio_player.setSource(
                QUrl.fromLocalFile(self.marker_session_path))
            self._audio_player.setPosition(
                int(max(0.0, time_s - 2.0) * 1000))
            self._audio_player.play()
            QTimer.singleShot(5000, self._audio_player.pause)
        except Exception as exc:
            QMessageBox.warning(
                self, "Playback Error",
                "Could not play this marker: %s" % exc)

    def save_marker_edits(self):
        if self.marker_session is None:
            return
        base, extension = os.path.splitext(self.marker_session_path)
        default = base + "_reviewed" + extension
        output, _ = QFileDialog.getSaveFileName(
            self, "Save Reviewed Marker Copy", default,
            "WAV files (*.wav)")
        if not output:
            return
        reader_id = (
            self.current_project.preset.reader_id
            if self.current_project else "")
        try:
            self.marker_session.save(
                output, language=self.cfg.whisper_language,
                reader_id=reader_id)
        except Exception as exc:
            QMessageBox.warning(
                self, "Marker Save Error",
                "Could not save markers: %s" % exc)
            return
        self._add_paths([output])
        if self.current_project is not None:
            self.current_project.update_file(
                output, status="review", output_path=output,
                review_reasons=["Reviewed marker copy requires final QC."])
            self.current_project.record(
                "marker_copy_saved", output,
                "source=%s" % self.marker_session_path)
        self.status("Saved reviewed marker copy: %s" % output)

    def _mark_project_dirty(self, action):
        if self.current_project is not None:
            self.current_project.record(
                action, self.marker_session_path)
            self._project_dirty = True
            self._refresh_project_label()

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
                                  script_verses=self.script_verses,
                                  script_chapters=self.script_chapters,
                                  script_book_chapters=self.script_book_chapters)
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
        self.refresh_review_queue()
        if self.current_project is not None:
            self.current_project.record(
                "qc_complete",
                detail="%d passed, %d need attention" % (npass, nfail))
            self._project_dirty = True
            self._refresh_project_label()

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
    # Language detection and unified review
    # ---------------------------------------------------------------------------
    def _script_text_for_language_detection(self, path):
        """Return the PDF chapter text matching one audio filename."""
        from engine.bible_db import parse_filename

        verses = {}
        bc = parse_filename(path)
        if bc and (bc.book, bc.chapter) in self.script_book_chapters:
            verses = self.script_book_chapters[(bc.book, bc.chapter)]
        elif bc and bc.chapter in self.script_chapters:
            verses = self.script_chapters[bc.chapter]
        elif (len(self.files) == 1 and len(self.script_chapters) == 1):
            verses = next(iter(self.script_chapters.values()))
        elif self.script_verses:
            verses = self.script_verses
        return " ".join(
            str(verses[number])
            for number in sorted(verses)
            if verses[number])

    def run_language_detection(self):
        if not self.files:
            self.status("Add WAV files before detecting languages.")
            return
        saved_config = Config.load(self.cfg_path)
        self.cfg.whisper_model = saved_config.whisper_model
        if not self._ensure_ai_model_ready("Language detection"):
            return
        if self.thread is not None:
            self.status("Another operation is in progress.")
            return
        self.thread = QThread()
        self.worker = LanguageDetectWorker(
            list(self.files), self.cfg.whisper_model)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_language_progress)
        self.worker.file_done.connect(self._on_language_file_done)
        self.worker.finished.connect(self._on_language_finished)
        self.btn_detect_language.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(self.files))
        self.progress.setValue(0)
        self.thread.start()

    def _on_language_progress(self, done, total, name):
        self.progress.setValue(max(0, done - 1))
        self.status(
            "Detecting language %d/%d: %s" % (done, total, name))

    def _on_language_file_done(self, path, result):
        from engine.language_resolution import resolve_language_with_script

        result = resolve_language_with_script(
            result, self._script_text_for_language_detection(path))
        self.language_results[path] = result
        self.progress.setValue(self.progress.value() + 1)
        if self.current_project is not None:
            if result.ok:
                self.current_project.update_file(
                    path, detected_language=result.language,
                    language_confidence=result.confidence)
            self.current_project.record(
                "language_detection", path,
                ("%s %.1f%%" %
                 (result.language or "failed", result.confidence * 100))
                if not result.error else result.error)
            self._project_dirty = True

    def _on_language_finished(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self.btn_detect_language.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.progress.setVisible(False)
        self.refresh_review_queue()
        self._refresh_project_label()

        lines = []
        resolution_notes = []
        for path in self.files:
            result = self.language_results.get(path)
            if result is None:
                continue
            if result.error:
                lines.append(
                    "%s: FAILED - %s" %
                    (os.path.basename(path), result.error))
                continue
            candidates = ", ".join(
                "%s %.0f%%" % (candidate.name,
                               candidate.confidence * 100)
                for candidate in result.candidates)
            if result.resolution_source == "script-confirmed":
                lines.append(
                    "%s: Assamese — PDF script confirmed | "
                    "Raw Whisper: %s %.0f%% | Candidates: %s" %
                    (os.path.basename(path),
                     result.raw_language_name or result.raw_language,
                     result.raw_confidence * 100, candidates))
                if result.resolution_note:
                    resolution_notes.append(result.resolution_note)
            elif result.resolution_source == "script-conflict":
                lines.append(
                    "%s: CHECK LANGUAGE — Audio: %s %.0f%% | "
                    "PDF: Assamese | Candidates: %s" %
                    (os.path.basename(path), result.language_name,
                     result.confidence * 100, candidates))
                if result.resolution_note:
                    resolution_notes.append(result.resolution_note)
            else:
                lines.append(
                    "%s: %s (%.0f%%) | %s" %
                    (os.path.basename(path), result.language_name,
                     result.confidence * 100, candidates))
        if resolution_notes:
            lines.append("")
            lines.append(
                "Script-aware result: " + resolution_notes[0])
        self.status("Language detection finished.")
        QMessageBox.information(
            self, "Detected Languages",
            "\n".join(lines[:40]) or "No language result was produced.")
        confident = [
            result for result in self.language_results.values()
            if result.ok and result.confidence >= 0.65]
        detected_codes = {result.language for result in confident}
        if len(detected_codes) == 1:
            detected_code = next(iter(detected_codes))
            detected_name = confident[0].language_name
            # Never replace a language explicitly chosen by the operator.
            # Closely related languages can be confidently confused; this
            # Assamese production sample is detected as Bengali by Whisper.
            if not self.cfg.whisper_language:
                reply = QMessageBox.question(
                    self, "Use Detected Language?",
                    "The confident results agree on %s (%s).\n\n"
                    "Use this as the project Auto-Mark language?" %
                    (detected_name, detected_code),
                    QMessageBox.Yes | QMessageBox.No)
                if reply == QMessageBox.Yes:
                    self.cfg.whisper_language = detected_code
                    self.cfg.save(self.cfg_path)
                    self._project_dirty = True
                    self._refresh_project_label()
                    self._refresh_processing_help()
                    self.status(
                        "Auto-Mark language set to %s (%s)." %
                        (detected_name, detected_code))

    def refresh_review_queue(self):
        groups = []
        for path in self.files:
            groups.append(
                review_from_file_report(path, self.reports.get(path)))
            groups.append(
                review_from_language(
                    path, self.language_results.get(path)))
            groups.append(
                review_from_automark(
                    path, self.automark_results_by_path.get(path)))
            groups.append(
                review_from_calibration(
                    path, self.calibration_result))
        self.review_items = [
            item for item in merge_review_items(*groups)
            if not (
                item.severity != "error" and
                item.path in self.accepted_review_paths)]
        self.review_table.setRowCount(len(self.review_items))
        for row, item in enumerate(self.review_items):
            values = [
                item.severity.upper(), os.path.basename(item.path),
                item.category, item.marker_label,
                _mmss_precise(item.time_s) if item.time_s >= 0 else "",
                item.message,
            ]
            for column, value in enumerate(values):
                table_item = QTableWidgetItem(value)
                table_item.setData(Qt.UserRole, item.path)
                if item.severity == "error":
                    table_item.setBackground(FAILBG)
                    table_item.setForeground(FAILFG)
                elif item.severity == "warning":
                    table_item.setBackground(QColor(79, 63, 26))
                    table_item.setForeground(QColor(255, 214, 120))
                self.review_table.setItem(row, column, table_item)
        errors = sum(item.severity == "error"
                     for item in self.review_items)
        warnings = sum(item.severity == "warning"
                       for item in self.review_items)
        self.review_summary.setText(
            "%d review item(s): %d errors, %d warnings" %
            (len(self.review_items), errors, warnings))
        if self.current_project is not None:
            self._sync_project_state()

    def _selected_review(self):
        rows = self.review_table.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        if 0 <= row < len(self.review_items):
            return self.review_items[row]
        return None

    def open_selected_review(self):
        item = self._selected_review()
        if item is None:
            return
        try:
            file_row = self.files.index(item.path)
        except ValueError:
            return
        self.table.setCurrentCell(file_row, 0)
        self.workspace_tabs.setCurrentIndex(1)
        if item.marker_label:
            for row in range(self.marker_table.rowCount()):
                label_item = self.marker_table.item(row, 1)
                if label_item and label_item.text() == item.marker_label:
                    self.marker_table.setCurrentCell(row, 0)
                    break

    def accept_selected_review_file(self):
        item = self._selected_review()
        if item is None:
            return
        errors = [
            candidate for candidate in self.review_items
            if candidate.path == item.path and candidate.severity == "error"]
        if errors:
            QMessageBox.warning(
                self, "Cannot Accept",
                "This file still has QC errors. Correct or recheck it first.")
            return
        self.accepted_review_paths.add(item.path)
        if self.current_project is not None:
            self.current_project.update_file(
                item.path, status="approved", review_reasons=[])
            self.current_project.record(
                "review_accepted", item.path)
            self._project_dirty = True
            self._refresh_project_label()
        self.status(
            "Review accepted for %s." % os.path.basename(item.path))
        self.refresh_review_queue()

    # ---------------------------------------------------------------------------
    # Marker accuracy calibration
    # ---------------------------------------------------------------------------
    def _selected_chapter_path(self):
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return ""
        row = rows[0].row()
        return self.files[row] if 0 <= row < len(self.files) else ""

    def choose_calibration_automatic(self):
        selected = self._selected_chapter_path()
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Automatic Marker File",
            selected or "",
            "Marker files (*.wav *.csv *.json);;All files (*)")
        if path:
            self.calibration_auto_path = path
            self._refresh_calibration_paths()

    def choose_calibration_reference(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose Manually Checked Reference", "",
            "Marker files (*.wav *.csv *.json);;All files (*)")
        if path:
            self.calibration_reference_path = path
            self._refresh_calibration_paths()

    def _refresh_calibration_paths(self):
        self.calibration_paths.setText(
            "<b>Automatic:</b> %s<br><b>Reference:</b> %s" %
            (self.calibration_auto_path or "not selected",
             self.calibration_reference_path or "not selected"))

    def run_calibration(self):
        if not self.calibration_auto_path:
            self.calibration_auto_path = self._selected_chapter_path()
        if (not self.calibration_auto_path or
                not self.calibration_reference_path):
            QMessageBox.warning(
                self, "Calibration",
                "Choose both the automatic marker file and the manually "
                "checked reference.")
            return
        try:
            from engine.calibration import compare_marker_files
            result = compare_marker_files(
                self.calibration_auto_path,
                self.calibration_reference_path,
                self.calibration_threshold.value())
        except Exception as exc:
            QMessageBox.warning(
                self, "Calibration Error",
                "Could not compare markers: %s" % exc)
            return
        self.calibration_result = result
        self.calibration_table.setRowCount(len(result.matched))
        for row, entry in enumerate(result.matched):
            passed = entry.absolute_error_s <= result.threshold_s
            values = [
                entry.label, "%.3fs" % entry.automatic_time_s,
                "%.3fs" % entry.reference_time_s,
                "%+.3fs" % entry.signed_error_s,
                "%.3fs" % entry.absolute_error_s,
                "PASS" if passed else "REVIEW",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setBackground(PASSBG if passed else FAILBG)
                item.setForeground(PASSFG if passed else FAILFG)
                self.calibration_table.setItem(row, column, item)
        self.calibration_summary.setText(
            "<b>%s</b><br>Missing: %d · Extra: %d · Overall: %s" %
            (result.summary, len(result.missing_in_automatic),
             len(result.extra_in_automatic),
             "PASS" if result.ok else "REVIEW REQUIRED"))
        if self.current_project is not None:
            self.current_project.record(
                "calibration", result.automatic_path, result.summary)
            self._project_dirty = True
            self._refresh_project_label()
        self.refresh_review_queue()

    def export_calibration_menu(self):
        if self.calibration_result is None:
            self.status("Run a calibration comparison first.")
            return
        menu = QMenu(self)
        csv_action = QAction("Calibration CSV…", self)
        json_action = QAction("Calibration JSON…", self)
        csv_action.triggered.connect(
            lambda: self._export_calibration("csv"))
        json_action.triggered.connect(
            lambda: self._export_calibration("json"))
        menu.addAction(csv_action)
        menu.addAction(json_action)
        menu.exec(
            self.btn_cal_export.mapToGlobal(
                self.btn_cal_export.rect().bottomLeft()))

    def _export_calibration(self, format_name):
        extension = "." + format_name
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Calibration", "calibration" + extension,
            "%s (*%s)" % (format_name.upper(), extension))
        if not path:
            return
        from engine.calibration import (
            write_calibration_csv, write_calibration_json)
        if format_name == "csv":
            write_calibration_csv(path, self.calibration_result)
        else:
            write_calibration_json(path, self.calibration_result)
        self.status("Exported calibration: %s" % path)

    # ---------------------------------------------------------------------------
    # Auto-Mark
    # ---------------------------------------------------------------------------
    def run_auto_mark(self):
        """Auto-mark loaded chapters using their matching PDF chapters."""
        if not AUTO_MARK_ENABLED:
            self.status(AUTO_MARK_DISABLED_MESSAGE)
            QMessageBox.information(
                self, "Auto-Mark Temporarily Disabled",
                AUTO_MARK_DISABLED_MESSAGE)
            return
        # Pick up configuration changes made while this window was already
        # open (for example after installing a larger Whisper model).
        saved_config = Config.load(self.cfg_path)
        self.cfg.whisper_model = saved_config.whisper_model
        self.cfg.whisper_language = saved_config.whisper_language
        self.cfg.alignment_backend = saved_config.alignment_backend
        self.cfg.auto_mark_headings = saved_config.auto_mark_headings
        if self.files:
            # Generated drafts are added to the GUI for review, but must not
            # become inputs on the next Auto-Mark run.
            paths = [
                path for path in self.files
                if not re.search(
                    r"_(?:marked|reviewed|edited|mastered)(?:_\d+)?\.wav$",
                    os.path.basename(path), re.IGNORECASE)]
            if not paths:
                self.status(
                    "No original WAV files are loaded; generated marked "
                    "copies are not valid Auto-Mark inputs.")
                return
        else:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select WAV files to auto-mark", "",
                "WAV files (*.wav)")
            if not paths:
                return

        if (self.cfg.alignment_backend != "pause" and
                not self._ensure_ai_model_ready("Auto-Mark")):
            return

        if (not self.script_book_chapters and not self.script_chapters
                and not self.script_verses):
            self.load_script()
            if (not self.script_book_chapters and not self.script_chapters
                    and not self.script_verses):
                self.status("Auto-Mark cancelled: no usable script loaded.")
                return

        # Start auto-marking in background
        if self.thread is not None:
            self.status("Another operation is in progress.")
            return

        language = self.cfg.whisper_language
        model = self.cfg.whisper_model
        from engine.mms_pack import MMS_PACK_KEY
        from engine.model_packs import is_model_pack_installed
        display_model = (
            "Meta MMS Assamese Precision"
            if (
                language == "as" and
                is_model_pack_installed(MMS_PACK_KEY))
            else model)

        reply = QMessageBox.question(
            self, "Auto-Mark %d chapter(s)?" % len(paths),
            "Language: %s\nModel: %s\n\n"
            "Each filename chapter will be matched to the same chapter in:\n"
            "%s\n\n"
            "New *_marked.wav and CSV files will be created. "
            "Low-confidence results will be marked as drafts for review.\n\n"
            "Proceed?" %
            (language or "auto-detect", display_model,
             os.path.basename(self.script_pdf_path) or "loaded script"),
            QMessageBox.Yes | QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        self.btn_check.setEnabled(False)
        self.btn_automark.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.setVisible(True)
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setFormat("Preparing Auto-Mark… 0%")
        self.operation_detail.setText(
            "Preparing AI alignment for %d chapter(s)…" % len(paths))
        self.operation_detail.setVisible(True)
        self._automark_total = len(paths)
        self._automark_last_fraction = 0.0
        self._automark_live_preview_shown = False
        self._automark_results = []

        self.thread = QThread()
        self.worker = AutoMarkWorker(
            paths, self.script_verses, language, model,
            reader_id=self.cfg.reader_id,
            script_chapters=self.script_chapters,
            script_book_chapters=self.script_book_chapters,
            script_headings=(
                self.script_headings if self.cfg.auto_mark_headings else {}),
            script_book_headings=(
                self.script_book_headings
                if self.cfg.auto_mark_headings else {}),
            alignment_backend=self.cfg.alignment_backend)
        self.worker.language_by_path = {
            path: result.language
            for path, result in self.language_results.items()
            if result.ok and result.confidence >= 0.50}
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_automark_progress)
        self.worker.stage_progress.connect(self._on_automark_stage_progress)
        self.worker.marker_preview.connect(
            self._on_automark_marker_preview)
        self.worker.file_done.connect(self._on_automark_file_done)
        self.worker.finished.connect(self._on_automark_finished)
        self.thread.start()

    def _on_automark_progress(self, done, total, name):
        self._automark_last_fraction = 0.0
        self.status("Auto-marking %d/%d: %s" % (done, total, name))
        self.operation_detail.setText(
            "Chapter %d of %d · %s" % (done, total, name))

    def _on_automark_stage_progress(
            self, file_number, total, name, stage, fraction):
        fraction = max(
            self._automark_last_fraction,
            min(1.0, max(0.0, float(fraction))))
        self._automark_last_fraction = fraction
        overall = (
            (max(1, file_number) - 1 + fraction) /
            float(max(1, total)))
        value = max(0, min(1000, int(round(overall * 1000))))
        readable_stage = str(stage).strip().replace("_", " ").title()
        self.progress.setValue(value)
        self.progress.setFormat(
            "Chapter %d/%d · %s · %d%%" %
            (file_number, total, readable_stage,
             int(round(overall * 100))))
        self.operation_detail.setText(
            "%s — %s" % (name, readable_stage))
        self.status(
            "Auto-Mark %d/%d: %s — %s" %
            (file_number, total, name, readable_stage))

    def _on_automark_marker_preview(self, path, markers):
        """Show accurate provisional positions before the WAV is written."""
        if not markers:
            return
        self.marker_session = None
        self.marker_session_path = ""
        self._updating_marker_table = True
        self.marker_table.setRowCount(len(markers))
        for row, marker in enumerate(markers):
            marker_type = self._editor_marker_type(marker.label)
            attention_threshold = (
                0.75 if marker.method.startswith("mms-") else 0.55)
            values = [
                marker_type, marker.label, "%.3f" % marker.time_s,
                str(marker.sample_offset),
                "%.0f%%" % (marker.confidence * 100),
                marker.method, "LIVE",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if (
                        marker.confidence < attention_threshold or
                        "interpolated" in marker.method):
                    item.setBackground(QColor(79, 63, 26))
                    item.setForeground(QColor(255, 214, 120))
                self.marker_table.setItem(row, column, item)
        self._updating_marker_table = False
        self.marker_title.setText(
            "<b>Live Auto-Mark Preview</b> — %s" %
            os.path.basename(path))
        low_confidence = sum(
            1 for marker in markers
            if (
                marker.confidence <
                (0.75 if marker.method.startswith("mms-") else 0.55) or
                "interpolated" in marker.method))
        self.marker_summary.setText(
            "%d accurate positions available · %d low-confidence · "
            "writing the marked WAV now…" %
            (len(markers), low_confidence))

        try:
            source_wave = self.wave_cache.get(path)
            if source_wave is None:
                source_wave = extract_waveform(path)
                self.wave_cache[path] = source_wave
            preview_wave = WaveformData(
                peaks=source_wave.peaks,
                duration_s=source_wave.duration_s,
                sample_rate=source_wave.sample_rate,
                channels=source_wave.channels,
                bits=source_wave.bits,
                markers=[
                    (marker.time_s, marker.label)
                    for marker in markers],
            )
            self.wave.set_editable(False)
            self.wave.set_data(
                preview_wave, title="LIVE · %s" %
                os.path.basename(path))
        except Exception as exc:
            self.marker_summary.setText(
                self.marker_summary.text() +
                " · waveform unavailable: %s" % exc)

        if not self._automark_live_preview_shown:
            self.workspace_tabs.setCurrentIndex(1)
            self._automark_live_preview_shown = True

    def _on_automark_file_done(self, result):
        self._automark_results.append(result)
        result_path = result.output_path or result.input_path
        if result_path:
            self.automark_results_by_path[result_path] = result
        completed = len(self._automark_results)
        overall = completed / float(max(1, self._automark_total))
        self.progress.setValue(int(round(overall * 1000)))
        self.progress.setFormat(
            "Completed %d/%d chapters · %d%%" %
            (completed, self._automark_total,
             int(round(overall * 100))))

        if result.ok and result.output_path and os.path.isfile(
                result.output_path):
            try:
                self.wave.set_editable(True)
                self._show_markers(result.output_path)
                self.marker_title.setText(
                    "<b>Completed %d/%d</b> — %s" %
                    (completed, self._automark_total,
                     os.path.basename(result.output_path)))
            except Exception:
                pass

    def _on_automark_finished(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self.btn_check.setEnabled(True)
        self.btn_automark.setEnabled(AUTO_MARK_ENABLED)
        self.btn_stop.setEnabled(False)
        self.progress.setValue(1000)
        self.progress.setFormat("Auto-Mark complete · 100%")
        self.progress.setVisible(False)
        self.operation_detail.setVisible(False)
        self.wave.set_editable(True)

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
                state = "DRAFT" if r.needs_review else "OK"
                language_detail = r.language_used
                if (
                        r.decoder_language_used and
                        r.decoder_language_used != r.language_used):
                    language_detail += (
                        " (Whisper decoder %s)" %
                        r.decoder_language_used)
                detail_lines.append(
                    "%s: %s (%d markers, %s/%s, method: %s, "
                    "script overlap: %.1f%%, min confidence: %.0f%%)"
                    % (state, os.path.basename(r.output_path),
                       r.markers_placed, language_detail, r.model_used,
                       r.method_used, r.alignment_coverage * 100,
                       r.minimum_confidence * 100))
            else:
                detail_lines.append("FAIL: %s" % r.error)
            for w in r.warnings:
                detail_lines.append("  Warning: %s" % w)

        QMessageBox.information(
            self, "Auto-Mark Results",
            summary + "\n\n" + "\n".join(detail_lines[:20]))

        generated = [
            r.output_path for r in success
            if r.output_path and os.path.isfile(r.output_path)]
        if generated:
            self._add_paths(generated)
            first_row = self.files.index(generated[0])
            self.table.setCurrentCell(first_row, 0)
            self.workspace_tabs.setCurrentIndex(1)
        self.refresh_review_queue()

    # ---------------------------------------------------------------------------
    # Mastering
    # ---------------------------------------------------------------------------
    def run_master(self):
        """Master loaded WAV files — normalize loudness, limit peaks, fix silence."""
        from engine.mastering import (
            dependencies_available, get_dependency_message,
            MasteringSettings)

        if not dependencies_available():
            QMessageBox.warning(self, "Missing Dependencies",
                                "Mastering requires additional packages:\n\n" +
                                get_dependency_message())
            return
        if self.thread is not None:
            self.status("Another operation is in progress.")
            return

        if not self.files:
            # Ask user to select files
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select WAV files to master", "", "WAV files (*.wav)")
            if not paths:
                return
        else:
            paths = list(self.files)

        reply = QMessageBox.question(
            self, "Master %d file(s)?" % len(paths),
            "This will create mastered copies of %d file(s) with:\n\n"
            "  - Loudness normalized to %.1f LUFS\n"
            "  - True peak limited to %.1f dBTP\n"
            "  - High-pass filter at 80 Hz\n"
            "  - Noise gate applied\n"
            "  - Selected silence edge(s) set to %.1fs\n"
            "  - Format: %d Hz / %d-bit\n\n"
            "Output: a per-book _Mastered folder (originals untouched)\n"
            "Every output also receives a validation JSON report.\n\n"
            "Proceed?" % (len(paths), self.cfg.target_lufs, self.cfg.true_peak_max,
                          self.cfg.silence_seconds, self.cfg.expected_sample_rate,
                          self.cfg.expected_bits),
            QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        # Run mastering in background
        settings = MasteringSettings(
            target_lufs=self.cfg.target_lufs,
            lufs_tolerance=self.cfg.lufs_tolerance,
            true_peak_max=self.cfg.true_peak_max,
            target_silence_s=self.cfg.silence_seconds,
            silence_tolerance_s=self.cfg.silence_tolerance,
            silence_threshold_dbfs=self.cfg.silence_threshold_dbfs,
            target_sample_rate=self.cfg.expected_sample_rate,
            target_bits=self.cfg.expected_bits,
            fix_head_silence=self.cfg.fix_head_silence,
            fix_tail_silence=self.cfg.fix_tail_silence,
            use_vst_plugins=self.cfg.use_vst_plugins,
            vst_chain=list(self.cfg.vst_chain or []),
        )

        self.btn_check.setEnabled(False)
        self.btn_master.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.status("Mastering %d file(s)..." % len(paths))
        self.btn_stop.setEnabled(True)
        self._master_results = []
        self.thread = QThread()
        self.worker = MasterWorker(paths, settings)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progress.connect(self._on_master_progress)
        self.worker.file_done.connect(self._on_master_file_done)
        self.worker.finished.connect(self._on_master_finished)
        self.thread.start()

    def _on_master_progress(self, done, total, name):
        self.status("Mastering %d/%d: %s" % (done, total, name))

    def _on_master_file_done(self, result):
        self._master_results.append(result)
        self.progress.setValue(self.progress.value() + 1)

    def _on_master_finished(self):
        self.thread.quit()
        self.thread.wait()
        self.thread = None
        self.worker = None
        self.progress.setVisible(False)
        self.btn_check.setEnabled(True)
        self.btn_master.setEnabled(True)
        self.btn_stop.setEnabled(False)

        results = self._master_results
        success = [result for result in results if result.success]
        detail_lines = []
        generated = []
        for result in results:
            filename = (
                os.path.basename(result.output_path)
                if result.output_path else "?")
            if result.success:
                detail_lines.append(
                    "VALIDATED: %s\n    %.1f LUFS, %.1f dBTP; "
                    "front %.2fs, back %.2fs" %
                    (filename, result.output_lufs, result.output_peak,
                     result.output_head_silence,
                     result.output_tail_silence))
                generated.append(result.output_path)
            else:
                detail_lines.append(
                    "REVIEW: %s\n    %s" %
                    (filename, result.error or "validation failed"))
            if result.report_path:
                detail_lines.append(
                    "    Report: %s" %
                    os.path.basename(result.report_path))

        summary = "%d/%d mastered and independently validated." % (
            len(success), len(results))
        self.status("Mastering complete. " + summary)
        if generated:
            self._add_paths([
                path for path in generated if os.path.isfile(path)])
        QMessageBox.information(
            self, "Mastering Results",
            summary + "\n\n" + "\n".join(detail_lines[:30]))

    # ---------------------------------------------------------------------------
    # Extract Markers (export WAV markers as Adobe Audition CSV)
    # ---------------------------------------------------------------------------
    def run_extract_markers(self):
        """Extract markers from WAV files and save as Adobe Audition CSV."""
        from engine.wav_markers import read_markers
        from engine.csv_markers import CSVMarker, write_csv_markers

        if not self.files:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select WAV files to extract markers from", "", "WAV files (*.wav)")
            if not paths:
                return
        else:
            paths = list(self.files)

        # Ask where to save CSVs
        output_dir = QFileDialog.getExistingDirectory(
            self, "Select folder to save CSV marker files")
        if not output_dir:
            # Default: same folder as the WAV files
            output_dir = ""

        self.status("Extracting markers...")
        QApplication.processEvents()

        success = 0
        failed = 0
        no_markers = 0
        details = []

        for path in paths:
            filename = os.path.basename(path)
            csv_name = os.path.splitext(filename)[0] + ".csv"

            if output_dir:
                csv_path = os.path.join(output_dir, csv_name)
            else:
                csv_path = os.path.join(os.path.dirname(path), csv_name)

            try:
                markers = read_markers(path)
                if not markers:
                    no_markers += 1
                    details.append("SKIP: %s (no markers)" % filename)
                    continue

                # Convert to CSVMarker format
                csv_markers = []
                for m in markers:
                    csv_markers.append(CSVMarker(
                        name=m.label,
                        start_seconds=m.seconds,
                        duration_seconds=0.0,
                        time_format="decimal",
                        marker_type="Cue",
                        description="",
                    ))

                write_csv_markers(csv_path, csv_markers)
                success += 1
                details.append("OK: %s (%d markers)" % (csv_name, len(markers)))

            except Exception as e:
                failed += 1
                details.append("FAIL: %s — %s" % (filename, str(e)))

        summary = "%d CSV files exported." % success
        if no_markers:
            summary += " %d skipped (no markers)." % no_markers
        if failed:
            summary += " %d failed." % failed

        self.status("Extract Markers complete. " + summary)

        QMessageBox.information(
            self, "Extract Markers",
            summary + "\n\n" + "\n".join(details[:20]))

    # ---------------------------------------------------------------------------
    # Fix Silence (trim/pad to exact 2 seconds — no mastering, just silence fix)
    # ---------------------------------------------------------------------------
    def run_fix_silence(self):
        """Fix head/tail silence to exactly 2 seconds. No other processing."""
        from engine.mastering import (
            _read_audio_as_float, _write_wav_float, _fix_silence_sides,
            _measure_silence)
        from engine.wav_markers import read_markers
        from engine.marker_writer import write_markers as write_markers_to_wav

        try:
            import numpy as np  # noqa: F401
        except ImportError:
            QMessageBox.warning(self, "Missing Dependencies",
                                "Fix Silence requires NumPy.\n\n"
                                "Install with: pip install numpy")
            return

        if not self.files:
            paths, _ = QFileDialog.getOpenFileNames(
                self, "Select WAV files to fix silence", "", "WAV files (*.wav)")
            if not paths:
                return
        else:
            paths = list(self.files)

        target_s = self.cfg.silence_seconds  # default 2.0
        threshold = self.cfg.silence_threshold_dbfs  # default -60
        fix_head = self.cfg.fix_head_silence
        fix_tail = self.cfg.fix_tail_silence
        if not fix_head and not fix_tail:
            QMessageBox.warning(
                self, "No Silence Edge Selected",
                "Enable FRONT, BACK, or both in Settings → Mastering.")
            return
        selected_sides = (
            "front and back" if fix_head and fix_tail
            else "front only" if fix_head else "back only")

        reply = QMessageBox.question(
            self, "Fix Silence — %d file(s)" % len(paths),
            "This will trim/pad %s silence to exactly %.1f seconds.\n\n"
            "- No loudness changes\n"
            "- No compression or limiting\n"
            "- Markers preserved\n"
            "- Original filename kept, output in folder\n\n"
            "Proceed?" % (selected_sides, target_s),
            QMessageBox.Yes | QMessageBox.No)

        if reply != QMessageBox.Yes:
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.status("Fixing silence...")
        QApplication.processEvents()

        success = 0
        failed = 0
        details = []

        for i, path in enumerate(paths):
            self.status("Fixing silence %d/%d: %s" % (i + 1, len(paths), os.path.basename(path)))
            self.progress.setValue(i)
            QApplication.processEvents()

            try:
                audio, sr, bits = _read_audio_as_float(path)

                # Read markers to preserve
                original_markers = []
                try:
                    markers = read_markers(path)
                    original_markers = [(m.sample_offset, m.label) for m in markers]
                except Exception:
                    pass

                # Measure current silence
                head_s, tail_s = _measure_silence(audio, sr, threshold)

                # Fix it
                audio, marker_delta_samples = _fix_silence_sides(
                    audio, sr, target_s, threshold,
                    fix_head=fix_head, fix_tail=fix_tail)
                new_head_s, new_tail_s = _measure_silence(
                    audio, sr, threshold)

                # Generate output path (same folder structure as mastering)
                import re
                src_dir = os.path.dirname(path)
                filename = os.path.basename(path)
                m = re.match(r"^([A-Za-z0-9]+?)[\s_\-\.]", filename)
                if m:
                    folder_name = "%s_Fixed" % m.group(1)
                else:
                    folder_name = "Fixed"
                output_dir = os.path.join(src_dir, folder_name)
                os.makedirs(output_dir, exist_ok=True)
                output_path = os.path.join(output_dir, filename)

                # Write output with markers
                if original_markers:
                    tmp_path = output_path + ".tmp.wav"
                    _write_wav_float(tmp_path, audio, sr, bits)
                    # Apply the exact head trim/pad timing transform.
                    adjusted_markers = []
                    for sample_offset, label in original_markers:
                        new_offset = max(
                            0, sample_offset + marker_delta_samples)
                        if 0 <= new_offset < audio.shape[1]:
                            adjusted_markers.append((new_offset, label))
                    if adjusted_markers:
                        write_markers_to_wav(tmp_path, output_path, adjusted_markers)
                        os.remove(tmp_path)
                    else:
                        os.rename(tmp_path, output_path)
                else:
                    _write_wav_float(output_path, audio, sr, bits)

                details.append(
                    "OK: %s (front %.1fs→%.1fs, back %.1fs→%.1fs)" %
                    (filename, head_s, new_head_s, tail_s, new_tail_s))
                success += 1

            except Exception as e:
                details.append("FAIL: %s — %s" % (os.path.basename(path), str(e)))
                failed += 1

        self.progress.setVisible(False)
        summary = "%d/%d fixed. Output in *_Fixed/ folder." % (success, len(paths))
        self.status("Fix Silence complete. " + summary)

        QMessageBox.information(
            self, "Fix Silence Results",
            summary + "\n\n" + "\n".join(details[:20]))

    def save_marker_correction(self, language: str, verse_number: int,
                               expected_time: float, corrected_time: float,
                               reader_id: str = "") -> None:
        """Save a user correction for a marker position (for learning)."""
        mem = CorrectionMemory()
        mem.add_correction(language, verse_number, expected_time,
                           corrected_time, reader_id)
        self.status("Correction saved for verse %d (%.2fs -> %.2fs)"
                    % (verse_number, expected_time, corrected_time))

    def open_quick_start(self):
        dialog = QuickStartDialog(
            show_on_startup=self.cfg.show_quick_start, parent=self)
        dialog.exec()
        self.cfg.show_quick_start = (
            dialog.show_on_startup.isChecked())
        self.cfg.save(self.cfg_path)
        if dialog.open_models_requested:
            self.open_model_packs()

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self)
        if dlg.exec() == QDialog.Accepted:
            self.cfg = dlg.result_config(); self.cfg.save(self.cfg_path)
            self._refresh_processing_help()
            self.status("Settings saved. Re-run 'Check All' to apply.")

    def open_model_packs(self, select_model=""):
        if self.thread is not None:
            self.status(
                "Finish or stop the current operation before managing models.")
            return
        dialog = ModelPackDialog(
            self.cfg, self.cfg_path, self,
            select_model=select_model or self.cfg.whisper_model)
        dialog.activeModelChanged.connect(
            lambda _model: self._refresh_processing_help())
        dialog.exec()
        self._refresh_processing_help()

    def check_for_updates(self, manual=True):
        """Check the official feed in the background."""
        if self.update_thread is not None:
            if manual:
                self.status("An update check is already running.")
            return
        self._update_check_manual = bool(manual)
        self.btn_updates.setEnabled(False)
        self.btn_updates.setText("Checking…")
        if manual:
            self.status("Checking for ScriptureSoundQC updates…")
        self.update_thread = QThread(self)
        self.update_worker = UpdateCheckWorker(
            APP_UPDATE_VERSION, self.cfg.update_channel)
        self.update_worker.moveToThread(self.update_thread)
        self.update_thread.started.connect(self.update_worker.run)
        self.update_worker.finished.connect(self._on_update_check_finished)
        self.update_worker.failed.connect(self._on_update_check_failed)
        self.update_worker.finished.connect(self.update_worker.deleteLater)
        self.update_worker.failed.connect(self.update_worker.deleteLater)
        self.update_worker.finished.connect(self.update_thread.quit)
        self.update_worker.failed.connect(self.update_thread.quit)
        self.update_thread.finished.connect(self._cleanup_update_check)
        self.update_thread.start()

    def _on_update_check_finished(self, info):
        if info.update_available:
            notes = (info.notes or "No release notes were provided.").strip()
            if len(notes) > 1600:
                notes = notes[:1600].rstrip() + "…"
            message = (
                "A newer ScriptureSoundQC release is available.\n\n"
                "Installed: %s\nAvailable: %s\n\n%s\n\n"
                "Open the official release page to download the installer?"
                % (APP_VERSION, info.version, notes))
            reply = QMessageBox.question(
                self, "ScriptureSoundQC Update Available", message,
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(info.page_url))
            self.status("Update available: %s" % info.version)
        elif self._update_check_manual:
            QMessageBox.information(
                self, "No ScriptureSoundQC Update",
                "%s\n\nInstalled version: %s\nChannel: %s"
                % (info.notes, APP_VERSION, self.cfg.update_channel.title()))
            self.status("ScriptureSoundQC is up to date.")

    def _on_update_check_failed(self, error):
        if self._update_check_manual:
            QMessageBox.warning(
                self, "Could Not Check for Updates",
                "%s\n\nYou can continue using ScriptureSoundQC normally."
                % error)
            self.status("Update check could not be completed.")

    def _cleanup_update_check(self):
        if self.update_thread is not None:
            self.update_thread.deleteLater()
        self.update_worker = None
        self.update_thread = None
        self.btn_updates.setEnabled(True)
        self.btn_updates.setText("Check for Updates")

    def _ensure_ai_model_ready(self, operation_name):
        from engine.model_packs import (
            get_model_pack, is_model_pack_installed)
        from engine.mms_pack import MMS_PACK_KEY
        use_assamese_precision = (
            operation_name == "Auto-Mark" and
            self.cfg.whisper_language == "as")
        model = (
            MMS_PACK_KEY if use_assamese_precision else
            self.cfg.whisper_model)
        pack = get_model_pack(model)
        if pack and is_model_pack_installed(model):
            return True
        if pack is None:
            QMessageBox.warning(
                self, "Unknown AI Model",
                "The selected model '%s' is not available in this build. "
                "Choose a model from AI Model Packs." % model)
            self.open_model_packs()
            return False
        reply = QMessageBox.question(
            self, "AI Model Download Required",
            "%s requires the %s model pack, which is not installed.\n\n"
            "Approximate download: %.2f GB\n"
            "%s\n\n"
            "Open AI Model Packs and download it now?" %
            (operation_name, pack.display_name,
             pack.approx_bytes / float(1024**3),
             ("This precision pack is used only for Assamese Auto-Mark."
              if pack.backend == "mms" else
              "This multilingual Whisper pack supports many languages.")),
            QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.open_model_packs(select_model=model)
        return False

    def open_about(self):
        """Show the About dialog with credits and license info."""
        about_text = """
        <div style='text-align:center;'>
        <h2 style='color:#e6ebf5;'>
            <span style='color:#e6ebf5;'>Scripture</span><span style='color:#d4a843;'>Sound</span><span style='color:#4dd9c0;'>QC</span>
        </h2>
        <p style='color:#4dd9c0; font-size:14px;'><b>%s</b></p>
        <p style='color:#8a97ad;'>Audio Bible Quality Control</p>
        <hr style='border-color:#2a3547;'>
        <p style='color:#e6ebf5;'><b>Created by VerseVox Studio</b></p>
        <p style='color:#8a97ad;'>
            Loudness &middot; True Peak &middot; Silence &middot; Verse Markers<br>
            Auto-Marker (temporarily disabled) &middot; Script Verification &middot; Zoomable Waveform
        </p>
        <hr style='border-color:#2a3547;'>
        <p style='color:#8a97ad; font-size:11px;'>
            <b>License:</b> GNU General Public License v3 (GPL-3.0)<br><br>
            This is free software. You may redistribute and/or modify it<br>
            under the terms of the GPL v3. If you use this software,<br>
            modify it, or build upon it, you <b>must</b>:<br><br>
            1. Keep the copyright and attribution notices intact<br>
            2. Credit the project as required by its LICENSE<br>
            3. Open-source your modifications under GPL v3<br>
            4. Link back to the original repository
        </p>
        <p style='color:#4dd9c0; font-size:12px;'>
            <b>github.com/Voxsama/BibleAudioChecker</b>
        </p>
        <p style='color:#8a97ad; font-size:11px;'>
            VerseVox Studio &copy; 2024-2026
        </p>
        <hr style='border-color:#2a3547;'>
        <p><a style='color:#4dd9c0;' href='#'>Click "Changelog" button for version history</a></p>
        </div>
        """ % APP_VERSION
        QMessageBox.about(self, "About ScriptureSound QC", about_text)

    def open_changelog(self):
        """Show the changelog dialog."""
        changelog_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "CHANGELOG.md")

        # Try to read from file, fallback to embedded
        changelog_text = ""
        if os.path.isfile(changelog_path):
            try:
                with open(changelog_path, "r", encoding="utf-8") as f:
                    changelog_text = f.read()
            except Exception:
                pass

        # Also check PyInstaller bundle path
        if not changelog_text:
            import sys
            meipass = getattr(sys, "_MEIPASS", None)
            if meipass:
                alt_path = os.path.join(meipass, "CHANGELOG.md")
                if os.path.isfile(alt_path):
                    try:
                        with open(alt_path, "r", encoding="utf-8") as f:
                            changelog_text = f.read()
                    except Exception:
                        pass

        if not changelog_text:
            changelog_text = "Changelog not found."

        # Convert markdown to basic HTML
        html = "<pre style='color:#e6ebf5; font-size:12px; font-family:monospace;'>%s</pre>" % changelog_text
        dlg = QDialog(self)
        dlg.setWindowTitle("Changelog — ScriptureSound QC")
        dlg.setMinimumSize(500, 400)
        layout = QVBoxLayout(dlg)
        lbl = QLabel(html)
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)

        scroll = QScrollArea()
        scroll.setWidget(lbl)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        bb = QDialogButtonBox(QDialogButtonBox.Ok)
        bb.accepted.connect(dlg.accept)
        layout.addWidget(bb)
        dlg.exec()

    # export
    def export_menu(self):
        m = QMenu(self)
        a1 = QAction("Mistakes only (CSV)  — just what to fix", self)
        a2 = QAction("Full report (CSV)  — every check", self)
        a3 = QAction("Selected chapter marker bundle", self)
        a4 = QAction("All loaded marker bundles", self)
        a1.triggered.connect(lambda: self._export(mistakes_only=True))
        a2.triggered.connect(lambda: self._export(mistakes_only=False))
        a3.triggered.connect(
            lambda: self._export_marker_bundles(selected_only=True))
        a4.triggered.connect(
            lambda: self._export_marker_bundles(selected_only=False))
        a1.setEnabled(bool(self.reports))
        a2.setEnabled(bool(self.reports))
        a3.setEnabled(bool(self._selected_chapter_path()))
        a4.setEnabled(bool(self.files))
        m.addAction(a1)
        m.addAction(a2)
        m.addSeparator()
        m.addAction(a3)
        m.addAction(a4)
        m.exec(self.btn_export.mapToGlobal(self.btn_export.rect().bottomLeft()))

    def _export_marker_bundles(self, selected_only=False):
        paths = (
            [self._selected_chapter_path()] if selected_only
            else list(self.files))
        paths = [path for path in paths if path]
        if not paths:
            self.status("Select or add a WAV file before exporting markers.")
            return
        output_dir = QFileDialog.getExistingDirectory(
            self, "Choose Marker Export Folder")
        if not output_dir:
            return
        from engine.exports import export_marker_bundle
        from engine.wav_markers import read_markers
        project_name = (
            self.current_project.name if self.current_project else "")
        written = []
        skipped = []
        for wav_path in paths:
            try:
                markers = [
                    (marker.label, marker.seconds)
                    for marker in read_markers(wav_path)]
                if not markers:
                    skipped.append(os.path.basename(wav_path))
                    continue
                written.extend(export_marker_bundle(
                    output_dir, wav_path, markers,
                    {"project": project_name,
                     "language": self.cfg.whisper_language}))
            except Exception:
                skipped.append(os.path.basename(wav_path))
        self.status(
            "Exported %d marker files for %d chapter(s).%s" %
            (len(written), len(written) // 4,
             (" Skipped: " + ", ".join(skipped[:5]))
             if skipped else ""))

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
