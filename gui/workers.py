"""Background workers run on QThreads by the main window."""

from __future__ import annotations

import os

from PySide6.QtCore import Signal, QObject

from engine.checker import check_file, FileReport
from engine.auto_marker import auto_mark_file, AutoMarkResult
from engine.correction_memory import CorrectionMemory


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
