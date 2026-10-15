"""Settings dialog: check standards, markers, STT, VST chain, updates, AI review."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox,
    QTabWidget, QVBoxLayout, QWidget)

from engine.config import Config, default_config_path
from gui.theme import APP_VERSION, BORDER, MUTED, PANEL, PANEL2, TEXT
from gui.model_pack_dialog import ModelPackDialog

# Mastering chain rows: (Config field, label, min, max, step, suffix).
CHAIN_ROWS = (
    ("master_pre_normalize_lufs", "Pre-normalise to:", -60, -6, 0.5, " LUFS"),
    ("master_noise_gate_threshold_db", "Gate threshold:", -120, 0, 1, " dB"),
    ("master_noise_gate_attack_ms", "Gate attack:", 0.1, 500, 1, " ms"),
    ("master_noise_gate_release_ms", "Gate release:", 1, 2000, 10, " ms"),
    ("master_highpass_freq", "High-pass (0 = off):", 0, 400, 5, " Hz"),
    ("master_low_shelf_hz", "Low shelf frequency:", 20, 1000, 10, " Hz"),
    ("master_low_shelf_db", "Low shelf gain (0 = off):", -12, 12, 0.5, " dB"),
    ("master_high_shelf_hz", "High shelf frequency:", 1000, 20000, 100, " Hz"),
    ("master_high_shelf_db", "High shelf gain (0 = off):", -12, 12, 0.5, " dB"),
    ("master_comp_threshold_db", "Compressor threshold:", -60, 0, 0.5, " dB"),
    ("master_comp_ratio", "Compressor ratio (1 = off):", 1, 20, 0.1, " :1"),
    ("master_comp_attack_ms", "Compressor attack:", 0.1, 200, 1, " ms"),
    ("master_comp_release_ms", "Compressor release:", 1, 2000, 10, " ms"),
    ("master_limiter_release_ms", "Limiter release:", 10, 2000, 10, " ms"),
)


class SettingsDialog(QDialog):
    def __init__(self, cfg: Config, parent=None):
        super().__init__(parent)
        self.show_quick_start = cfg.show_quick_start
        self.ai_review_preferences = {
            name: getattr(cfg, name) for name in (
                "ai_review_model", "ai_review_free_only",
                "ai_review_deny_collection", "ai_review_report_language")}
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
        f2.addRow(QLabel(
            "<b>Processing chain</b> (pre-normalise, gate, EQ, compressor, "
            "limiter)"))
        hint = QLabel(
            "<i>Make-up gain is automatic: after the compressor the app "
            "measures the loudness and raises it exactly to the target, "
            "limiting true peak to the ceiling.</i>")
        hint.setWordWrap(True)
        f2.addRow(hint)
        self.gate_on = QCheckBox("Noise gate")
        self.gate_on.setChecked(cfg.master_apply_noise_gate)
        f2.addRow(self.gate_on)
        self.chain = {}
        for name, label, lo, hi, step, suffix in CHAIN_ROWS:
            self.chain[name] = self._d(getattr(cfg, name), lo, hi, step, suffix)
            f2.addRow(label, self.chain[name])
        scroll2 = QScrollArea(); scroll2.setWidgetResizable(True)
        scroll2.setWidget(tab2)
        tabs.addTab(scroll2, "Mastering")

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
        from engine.languages import (
            INDIAN_LANGUAGES,
            indian_whisper_codes,
            whisper_language_options,
        )
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
        priority_codes = list(indian_whisper_codes()) + ["en"]
        added_codes = set()
        for code in priority_codes:
            if code in languages:
                indian = INDIAN_LANGUAGES.get(code)
                name = indian.display_name if indian else languages[code]
                self.whisper_lang.addItem(
                    "%s [%s]" % (name, code), code)
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
            "project. The Indian-language database contains all 22 scheduled "
            "languages; only languages supported by Whisper can be forced "
            "here. Use Auto-detect when the language is unknown or does not "
            "have a dedicated Whisper token.")
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

        ai_tab = QWidget()
        ai_layout = QVBoxLayout(ai_tab)
        ai_help = QLabel(
            "Optional OpenRouter AI review is available in Processing → AI Review Chapter. "
            "Select a chapter first, then enter your API key and choose a free model in "
            "the review window's Connection tab. Keys are kept only for the app session.\n\n"
            "Audio measurements remain local. The app previews the selected script, "
            "transcript and QC text before asking permission to send it. AI findings "
            "do not change markers, audio or QC pass/fail results.\n\n"
            "For local transcription, select the language/model in Script STT. "
            "Assamese uses the installed Meta MMS pack. Cloud transcription settings "
            "are never used by AI Chapter Review.")
        ai_help.setWordWrap(True)
        ai_layout.addWidget(ai_help)
        ai_layout.addStretch()
        tabs.addTab(ai_tab, "AI Review")

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
            master_apply_noise_gate=self.gate_on.isChecked(),
            **{name: box.value() for name, box in self.chain.items()},
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
            **self.ai_review_preferences,
        )


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
