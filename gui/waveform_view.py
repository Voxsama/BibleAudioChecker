"""Waveform widget with zoom, pan and marker overlay."""

from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget

from engine.waveform import WaveformData
from gui.theme import ACCENT, BORDER, MARK_CT, MARK_V, MUTED, PANEL, WAVE


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
