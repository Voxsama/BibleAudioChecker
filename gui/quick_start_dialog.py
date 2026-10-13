"""First-run Quick Start guide dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout)


class QuickStartDialog(QDialog):
    """Short, non-technical workflow guide for packaged-app users."""

    def __init__(self, show_on_startup=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Quick Start — ScriptureSound QC")
        self.setMinimumSize(650, 500)

        layout = QVBoxLayout(self)
        title = QLabel(
            "<span style='font-size:20px; font-weight:700;'>"
            "Check your first Audio Bible WAV</span><br>"
            "<span style='color:#8a97ad;'>No Python or command-line setup "
            "is required in the packaged application.</span>")
        title.setWordWrap(True)
        title.setContentsMargins(12, 8, 12, 8)
        layout.addWidget(title)

        guide = QLabel("""
        <div style='line-height:1.35;'>
          <h3 style='color:#4dd9c0;'>1. Add your audio</h3>
          <p>Click <b>Add Files</b> and choose one or more WAV files. A Bible
          PDF is optional for ordinary marker checking.</p>

          <h3 style='color:#4dd9c0;'>2. Run the checks</h3>
          <p>Click <b>Check All</b>. The Chapters &amp; QC tab shows which files
          passed and which ones need attention.</p>

          <h3 style='color:#4dd9c0;'>3. Review the markers</h3>
          <p>Open <b>Markers &amp; Waveform</b>. Select a marker to listen around
          it, or edit its label and time. Click <b>Save Reviewed Copy</b> when
          finished; the original WAV remains untouched.</p>

          <h3 style='color:#4dd9c0;'>4. Master or add silence (optional)</h3>
          <p>Set LUFS, true peak, and front/back silence in <b>Settings</b>.
          Run the operation from <b>Processing</b>, then check the new file.</p>

          <p style='color:#f4c95d;'><b>Automatic verse marking is temporarily
          disabled in this Beta.</b> You do not need an AI model pack to check
          existing markers, edit markers, master audio, or apply silence.</p>
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
        close_button = QPushButton("Got It — Start Working")
        close_button.setObjectName("Primary")
        close_button.clicked.connect(self.accept)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)


# ---------------------------------------------------------------------------
# Settings dialog — tabbed layout to fit on screen
# ---------------------------------------------------------------------------
