"""A consent-first, selected-chapter AI reviewer with session-only credentials."""
from __future__ import annotations

import json
import os

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QPlainTextEdit, QTabWidget,
    QWidget, QProgressBar, QMessageBox, QFileDialog, QListWidget,
)

from engine import ai_review
from engine.config import default_config_path


class ReviewTask(QThread):
    progress = Signal(str)

    def __init__(self, action, parent):
        super().__init__(parent)
        self.action = action
        self.result = None
        self.error = ""

    def run(self):
        try:
            self.result = self.action(self.progress.emit)
        except ai_review.AIReviewError as exc:
            self.error = str(exc)
        except Exception:
            # Do not expose request objects, credentials or service responses.
            self.error = "The operation could not finish. Check local dependencies/model packs or try another model. Nothing was applied."
        finally:
            self.action = None  # release captured credentials after the request


class AIReviewDialog(QDialog):
    def __init__(self, path, cfg, script="", mapping_note="", parent=None):
        super().__init__(parent)
        self.path, self.cfg = path, cfg
        self.payload = self.result = self.task = self.player = None
        self.playback_timer = QTimer(self)
        self.playback_timer.setSingleShot(True)
        self.playback_timer.timeout.connect(self.stop_audio)
        self.setWindowTitle("AI Chapter Review — ScriptureSound QC")
        self.resize(960, 750)
        layout = QVBoxLayout(self)
        title = QLabel("AI Chapter Review · " + os.path.basename(path))
        title.setTextFormat(Qt.PlainText)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")
        layout.addWidget(title)
        warning = QLabel("AI suggestions are not verified errors. Measurements and processing stay local. "
                         "Only the text you preview is sent to OpenRouter and its model provider; never the WAV or PDF file.")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        connection = QWidget()
        form = QFormLayout(connection)
        self.key = QLineEdit(getattr(parent, "_openrouter_session_key", ""))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("Paste your own OpenRouter API key; never saved to disk")
        form.addRow("API key (this session only)", self.key)
        self.model = QComboBox()
        self.model.setEditable(True)
        self.model.addItem("openrouter/free")
        self.model.setCurrentText(cfg.ai_review_model)
        form.addRow("OpenRouter model ID", self.model)
        self.free_only = QCheckBox("Free models only — block paid fallback")
        self.free_only.setChecked(cfg.ai_review_free_only)
        form.addRow(self.free_only)
        self.private = QCheckBox("Exclude providers that collect prompts (may reduce availability)")
        self.private.setChecked(cfg.ai_review_deny_collection)
        form.addRow(self.private)
        self.report_language = QLineEdit(cfg.ai_review_report_language)
        form.addRow("Explain findings in", self.report_language)
        row = QHBoxLayout()
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self.test_key)
        self.refresh_button = QPushButton("Refresh Free Models")
        self.refresh_button.clicked.connect(self.refresh_models)
        row.addWidget(self.test_button)
        row.addWidget(self.refresh_button)
        form.addRow(row)
        help_text = QLabel("Get a key at openrouter.ai → API Keys. Each user supplies their own key. "
                           "Test Connection checks authentication only; it does not send chapter data. "
                           "Free models have rate limits and may be unavailable. openrouter/free can select "
                           "different models between reviews. Provider privacy policies still apply. "
                           "This is an online feature; local QC works without it.")
        help_text.setWordWrap(True)
        form.addRow(help_text)
        save = QPushButton("Save Preferences (not the key)")
        save.clicked.connect(self.save_preferences)
        form.addRow(save)
        self.tabs.addTab(connection, "1 · Connection")

        inputs = QWidget()
        inputs_layout = QVBoxLayout(inputs)
        mapping = QLabel(mapping_note + "\nConfirm the book, chapter, translation and spoken headings. "
                         "Edit/paste text below if PDF extraction is wrong. Only this selection will be reviewed.")
        mapping.setTextFormat(Qt.PlainText)
        mapping.setWordWrap(True)
        inputs_layout.addWidget(mapping)
        inputs_layout.addWidget(QLabel("Expected script — include verse numbers and spoken headings"))
        self.script = QPlainTextEdit(script)
        self.script.setPlaceholderText("Paste the matching chapter here, or load a Bible PDF in the main window first.")
        inputs_layout.addWidget(self.script, 1)
        self.transcribe = QCheckBox("Generate an independent transcript locally (installed model required)")
        inputs_layout.addWidget(self.transcribe)
        inputs_layout.addWidget(QLabel("Or paste the actual transcript — not a copy of the expected script"))
        self.transcript = QPlainTextEdit()
        self.transcript.setPlaceholderText("Without a transcript, AI can explain local QC but cannot check spoken text.")
        inputs_layout.addWidget(self.transcript, 1)
        inputs_layout.addWidget(QLabel("Local language/model: %s / %s. Change these in Settings → Script STT.\n"
                                      "Reads saved markers in this WAV; save/select your reviewed copy first if needed."
                                      % (cfg.whisper_language or "auto", "Meta MMS" if cfg.whisper_language in ("as", "asm") else cfg.whisper_model)))
        self.prepare_button = QPushButton("Prepare Locally & Preview")
        self.prepare_button.setObjectName("Primary")
        self.prepare_button.clicked.connect(self.prepare)
        inputs_layout.addWidget(self.prepare_button)
        self.tabs.addTab(inputs, "2 · Chapter")

        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        preview_layout.addWidget(QLabel("Exact request messages below (API key excluded). Check extracted text before sending."))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        preview_layout.addWidget(self.preview, 1)
        self.consent = QCheckBox("I checked the chapter selection and consent to sending this text to OpenRouter and its provider.")
        self.consent.setEnabled(False)
        preview_layout.addWidget(self.consent)
        self.send_button = QPushButton("Send Previewed Text for AI Review")
        self.send_button.setObjectName("Primary")
        self.send_button.setEnabled(False)
        self.send_button.clicked.connect(self.send)
        preview_layout.addWidget(self.send_button)
        self.tabs.addTab(preview, "3 · Preview && Send")

        results = QWidget()
        results_layout = QVBoxLayout(results)
        self.report = QPlainTextEdit()
        self.report.setReadOnly(True)
        results_layout.addWidget(self.report, 2)
        results_layout.addWidget(QLabel("Select supplied evidence to listen at its approximate local timestamp:"))
        self.evidence_list = QListWidget()
        results_layout.addWidget(self.evidence_list, 1)
        buttons = QHBoxLayout()
        self.play_button = QPushButton("Play Evidence (8 seconds)")
        self.play_button.clicked.connect(self.play_evidence)
        stop = QPushButton("Stop Playback")
        stop.clicked.connect(self.stop_audio)
        self.export_button = QPushButton("Export Review JSON…")
        self.export_button.clicked.connect(self.export_report)
        self.export_button.setEnabled(False)
        buttons.addWidget(self.play_button)
        buttons.addWidget(stop)
        buttons.addWidget(self.export_button)
        results_layout.addLayout(buttons)
        self.tabs.addTab(results, "4 · Findings")
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel("Start in Connection, then open Chapter. No chapter data has been sent.")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.reject)
        layout.addWidget(self.close_button)
        for edit in (self.script, self.transcript):
            edit.textChanged.connect(self.invalidate)
        self.transcribe.toggled.connect(self.invalidate)
        self.transcribe.toggled.connect(lambda checked: self.transcript.setEnabled(not checked))
        self.report_language.textChanged.connect(self.invalidate)
        self.model.currentTextChanged.connect(self.revoke_consent)
        self.free_only.toggled.connect(self.revoke_consent)
        self.private.toggled.connect(self.revoke_consent)
        self.consent.toggled.connect(lambda checked: self.send_button.setEnabled(checked and self.payload is not None and self.task is None))

    def revoke_consent(self, *args):
        self.consent.setChecked(False)

    def invalidate(self, *args):
        self.payload = self.result = None
        self.preview.clear()
        self.report.clear()
        self.evidence_list.clear()
        self.export_button.setEnabled(False)
        self.revoke_consent()
        self.consent.setEnabled(False)
        self.stop_audio()

    def start_task(self, action, done, message):
        if self.task is not None:
            return
        self.stop_audio()
        self.tabs.setEnabled(False)
        self.close_button.setEnabled(False)
        self.progress.setRange(0, 0)
        self.progress.show()
        self.status.setText(message)
        self.task = ReviewTask(action, self)
        self.task.progress.connect(self.status.setText)
        self.task.finished.connect(lambda: self.finish_task(done))
        self.task.start()

    def finish_task(self, done):
        task, self.task = self.task, None
        self.tabs.setEnabled(True)
        self.close_button.setEnabled(True)
        self.progress.hide()
        try:
            if task.error:
                self.status.setText(task.error)
                QMessageBox.warning(self, "AI Review", task.error)
            else:
                done(task.result)
        finally:
            task.deleteLater()

    def save_preferences(self):
        try:
            model = ai_review.validate_model(self.model.currentText(), self.free_only.isChecked())
            self.cfg.ai_review_model = model
            self.cfg.ai_review_free_only = self.free_only.isChecked()
            self.cfg.ai_review_deny_collection = self.private.isChecked()
            self.cfg.ai_review_report_language = self.report_language.text().strip() or "English"
            self.cfg.save(getattr(self.parent(), "cfg_path", default_config_path()))
            self.status.setText("Preferences saved. The OpenRouter key is kept only for this app session.")
        except (ai_review.AIReviewError, OSError) as exc:
            QMessageBox.warning(self, "Preferences", str(exc))

    def test_key(self):
        key = self.key.text().strip()
        self.start_task(lambda progress: ai_review.test_connection(key), self.status.setText, "Checking API key; no chapter is sent…")

    def refresh_models(self):
        def loaded(models):
            selected = self.model.currentText()
            self.model.clear()
            self.model.addItems(models)
            self.model.setCurrentText(selected)
            self.status.setText("Free-model list refreshed. Availability, limits and language quality vary.")
        self.start_task(lambda progress: ai_review.free_models(), loaded, "Fetching public model list…")

    def prepare(self):
        self.invalidate()
        script, transcript = self.script.toPlainText(), self.transcript.toPlainText()
        transcribe = self.transcribe.isChecked()
        language = self.report_language.text().strip() or "English"
        def prepared(payload):
            self.payload = payload
            self.preview.setPlainText("SYSTEM MESSAGE\n" + ai_review.SYSTEM_PROMPT + "\n\nCHAPTER MESSAGE\n" + ai_review.encode_payload(payload))
            self.consent.setEnabled(True)
            self.tabs.setCurrentIndex(2)
            self.status.setText("Prepared locally. Review all text and tick consent before sending. No chapter data has been sent.")
        self.start_task(lambda progress: ai_review.prepare_review(self.path, self.cfg, script, transcript, transcribe, language, progress),
                        prepared, "Preparing locally…")

    def send(self):
        if not self.payload or not self.consent.isChecked():
            return
        try:
            model = ai_review.validate_model(self.model.currentText(), self.free_only.isChecked())
        except ai_review.AIReviewError as exc:
            QMessageBox.warning(self, "Model", str(exc))
            return
        free = self.free_only.isChecked()
        if not free and QMessageBox.question(self, "Possible API charges", "Free-only mode is OFF. This review may charge your OpenRouter account. Send?") != QMessageBox.Yes:
            return
        key, payload, private = self.key.text().strip(), self.payload, self.private.isChecked()
        self.revoke_consent()
        self.result = None
        self.report.clear()
        self.evidence_list.clear()
        self.export_button.setEnabled(False)
        self.start_task(lambda progress: ai_review.review(key, model, free, payload, private), self.show_report,
                        "Sending previewed text and awaiting AI review… No audio is uploaded.")

    def show_report(self, result):
        self.result = result
        lines = ["ADVISORY ONLY — NOT A QC PASS OR VERIFIED ERROR LIST", "Model: " + result["model"],
                 "", result["summary"], "", "Limitations: " + result["limitations"]]
        refs = set()
        for i, finding in enumerate(result["findings"], 1):
            lines.extend(["", "%d. [%s] %s" % (i, finding["severity"], finding["explanation"]),
                          "Evidence: " + ", ".join(finding["evidence_ids"]), "Listen/check: " + finding["suggestion"]])
            refs.update(finding["evidence_ids"])
        if not result["findings"]:
            lines.append("\nNo issues were suggested. This does not certify the chapter or marker accuracy.")
        self.report.setPlainText("\n".join(lines))
        self.evidence_list.clear()
        for evidence in self.payload["evidence"]:
            if evidence["id"] not in refs:
                continue
            text = evidence.get("text", evidence.get("label", evidence.get("detail", "")))
            timestamp = evidence.get("start_s")
            prefix = "%.3fs" % timestamp if timestamp is not None else "no timing"
            self.evidence_list.addItem("%s · %s · %s" % (evidence["id"], prefix, text))
            item = self.evidence_list.item(self.evidence_list.count() - 1)
            item.setData(Qt.UserRole, timestamp)
            item.setToolTip(text)
        self.export_button.setEnabled(True)
        self.tabs.setCurrentIndex(3)
        self.status.setText("Review received. Original audio, measurements and markers are unchanged. Listen before deciding.")

    def play_evidence(self):
        item = self.evidence_list.currentItem()
        start = item.data(Qt.UserRole) if item else None
        if start is None or not self.payload or not 0 <= start < self.payload["duration_s"]:
            self.status.setText("Choose evidence with a valid local timestamp. Pasted text has no playback position.")
            return
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
            if self.player is None:
                self.player = QMediaPlayer(self)
                self.audio_output = QAudioOutput(self)
                self.player.setAudioOutput(self.audio_output)
                self.player.setSource(QUrl.fromLocalFile(self.path))
            self.player.setPosition(int(max(0, start - 1) * 1000))
            self.player.play()
            self.playback_timer.start(8000)
        except Exception:
            self.status.setText("Playback unavailable. Listen to this timestamp in Markers & Waveform.")

    def stop_audio(self):
        self.playback_timer.stop()
        if self.player is not None:
            self.player.pause()

    def export_report(self):
        if not self.result or not self.payload:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export AI Review (contains chapter text)", "ai-review.json", "JSON (*.json)")
        if path:
            try:
                if os.path.exists(path) and os.path.samefile(path, self.path):
                    raise OSError("Choose a new JSON file, not the source audio.")
                if not path.lower().endswith(".json"):
                    raise OSError("Use a .json filename for this report.")
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump({"evidence": self.payload, "review": self.result}, handle, ensure_ascii=False, indent=2, allow_nan=False)
                self.status.setText("Review exported locally. It includes the previewed text; no API key.")
            except OSError as exc:
                QMessageBox.warning(self, "Export", str(exc))

    def reject(self):
        if self.task is not None:
            self.status.setText("Please wait for this operation to finish before closing. Network requests time out; local transcription may take longer.")
            return
        self.stop_audio()
        if self.parent() is not None:
            self.parent()._openrouter_session_key = self.key.text().strip()
        self.key.clear()
        super().reject()

    def closeEvent(self, event):
        if self.task is not None:
            event.ignore()
            self.reject()
        else:
            self.reject()
            event.accept()
