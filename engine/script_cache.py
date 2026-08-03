"""Persistent PDF parse cache keyed by the source file's SHA-256 hash."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Callable, Optional

from .pdf_parser import (
    ParsedScriptCollection,
    ScriptHeading,
    parse_pdf_chapters,
)


_CACHE_VERSION = 3


@dataclass
class ScriptCacheResult:
    collection: ParsedScriptCollection
    from_cache: bool
    cache_path: str


def _default_cache_dir() -> str:
    return os.path.join(
        os.path.expanduser("~"), ".bible_audio_checker", "script_cache")


def file_sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cache_path(source_path: str, cache_dir: str) -> str:
    digest = file_sha256(source_path)
    basename = os.path.splitext(os.path.basename(source_path))[0]
    safe_name = "".join(
        char if char.isalnum() or char in "-_" else "_"
        for char in basename)[:80]
    return os.path.join(cache_dir, "%s_%s.json.gz" % (
        safe_name or "script", digest[:20]))


def _serialize(collection: ParsedScriptCollection, source_path: str) -> dict:
    return {
        "version": _CACHE_VERSION,
        "source_path": os.path.abspath(source_path),
        "source_sha256": file_sha256(source_path),
        "chapters": {
            str(chapter): {str(number): text
                           for number, text in verses.items()}
            for chapter, verses in collection.chapters.items()
        },
        "book_chapters": {
            "%s\t%d" % (book, chapter): {
                str(number): text for number, text in verses.items()}
            for (book, chapter), verses in
            collection.book_chapters.items()
        },
        "headings": {
            str(chapter): [
                {"text": heading.text, "before_verse": heading.before_verse}
                for heading in headings
            ]
            for chapter, headings in collection.headings.items()
        },
        "book_headings": {
            "%s\t%d" % (book, chapter): [
                {"text": heading.text, "before_verse": heading.before_verse}
                for heading in headings
            ]
            for (book, chapter), headings in
            collection.book_headings.items()
        },
        "warnings": collection.warnings,
    }


def _deserialize(payload: dict) -> ParsedScriptCollection:
    chapters = {
        int(chapter): {int(number): text
                       for number, text in verses.items()}
        for chapter, verses in payload.get("chapters", {}).items()
    }
    book_chapters = {}
    for key, verses in payload.get("book_chapters", {}).items():
        book, chapter = key.rsplit("\t", 1)
        book_chapters[(book, int(chapter))] = {
            int(number): text for number, text in verses.items()}
    headings = {
        int(chapter): [
            ScriptHeading(
                text=str(item.get("text", "")),
                before_verse=int(item.get("before_verse", 1)))
            for item in items if item.get("text")
        ]
        for chapter, items in payload.get("headings", {}).items()
    }
    book_headings = {}
    for key, items in payload.get("book_headings", {}).items():
        book, chapter = key.rsplit("\t", 1)
        book_headings[(book, int(chapter))] = [
            ScriptHeading(
                text=str(item.get("text", "")),
                before_verse=int(item.get("before_verse", 1)))
            for item in items if item.get("text")
        ]
    return ParsedScriptCollection(
        chapters=chapters,
        book_chapters=book_chapters,
        headings=headings,
        book_headings=book_headings,
        raw_text="",
        warnings=list(payload.get("warnings", [])),
    )


def load_or_parse_pdf(
        source_path: str,
        cache_dir: Optional[str] = None,
        parser: Callable[[str], ParsedScriptCollection] = parse_pdf_chapters,
        force_refresh: bool = False) -> ScriptCacheResult:
    """Load a cached parse or parse and cache the PDF.

    The cache contains extracted chapter text, never audio or API credentials.
    """
    cache_dir = cache_dir or _default_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    destination = _cache_path(source_path, cache_dir)

    if not force_refresh and os.path.isfile(destination):
        try:
            with gzip.open(destination, "rt", encoding="utf-8") as stream:
                payload = json.load(stream)
            if (payload.get("version") == _CACHE_VERSION and
                    payload.get("source_sha256") == file_sha256(source_path)):
                return ScriptCacheResult(
                    _deserialize(payload), True, destination)
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    collection = parser(source_path)
    payload = _serialize(collection, source_path)
    temporary = destination + ".tmp"
    with gzip.open(temporary, "wt", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False)
    os.replace(temporary, destination)
    return ScriptCacheResult(collection, False, destination)
