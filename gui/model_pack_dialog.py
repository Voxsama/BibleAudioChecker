"""AI Model Packs manager dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QHeaderView, QLabel, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

from gui.theme import PASSFG
from gui.workers import ModelPackDownloadWorker


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
