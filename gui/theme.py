"""Application constants, colours, stylesheet and asset helpers."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QIcon, QPixmap
from PySide6.QtSvg import QSvgRenderer

APP_NAME = "ScriptureSound QC"
APP_VERSION = "Beta"
APP_UPDATE_VERSION = "4.0.0-beta.1"
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
