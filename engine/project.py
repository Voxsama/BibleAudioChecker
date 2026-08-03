"""Persistent project files for multi-language Audio Bible production."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .bible_db import parse_filename


PROJECT_VERSION = 1


@dataclass
class ProjectPreset:
    """Settings that should travel with a production project."""
    language: str = "as"
    whisper_model: str = "large-v3"
    alignment_backend: str = "auto"
    auto_mark_headings: bool = True
    reader_id: str = ""
    marker_convention: str = "speech_start"
    target_lufs: float = -18.0
    lufs_tolerance: float = 0.5
    true_peak_max: float = -1.0
    silence_seconds: float = 2.0
    fix_front_silence: bool = True
    fix_back_silence: bool = True


@dataclass
class ProjectFile:
    path: str
    book: str = ""
    chapter: int = 0
    status: str = "pending"
    detected_language: str = ""
    language_confidence: float = 0.0
    output_path: str = ""
    review_reasons: List[str] = field(default_factory=list)
    updated_at: float = 0.0


@dataclass
class ProjectHistory:
    timestamp: float
    action: str
    path: str = ""
    detail: str = ""


@dataclass
class AudioBibleProject:
    name: str
    project_path: str = ""
    root_dir: str = ""
    script_path: str = ""
    preset: ProjectPreset = field(default_factory=ProjectPreset)
    files: List[ProjectFile] = field(default_factory=list)
    history: List[ProjectHistory] = field(default_factory=list)
    version: int = PROJECT_VERSION

    def add_files(self, paths: List[str]) -> int:
        existing = {os.path.normcase(os.path.abspath(item.path))
                    for item in self.files}
        added = 0
        for path in paths:
            absolute = os.path.abspath(path)
            key = os.path.normcase(absolute)
            if key in existing:
                continue
            bc = parse_filename(absolute)
            self.files.append(ProjectFile(
                path=absolute,
                book=bc.book if bc else "",
                chapter=bc.chapter if bc else 0,
                updated_at=time.time(),
            ))
            existing.add(key)
            added += 1
        if added:
            self.record("add_files", detail="%d file(s)" % added)
        return added

    def find_file(self, path: str) -> Optional[ProjectFile]:
        key = os.path.normcase(os.path.abspath(path))
        for item in self.files:
            if os.path.normcase(os.path.abspath(item.path)) == key:
                return item
        return None

    def update_file(self, path: str, **changes) -> ProjectFile:
        item = self.find_file(path)
        if item is None:
            self.add_files([path])
            item = self.find_file(path)
        if item is None:
            raise ValueError("Could not add project file: %s" % path)
        for name, value in changes.items():
            if hasattr(item, name):
                setattr(item, name, value)
        item.updated_at = time.time()
        return item

    def record(self, action: str, path: str = "", detail: str = "") -> None:
        self.history.append(ProjectHistory(
            timestamp=time.time(), action=action, path=path, detail=detail))
        # Keep project files compact during long-running productions.
        if len(self.history) > 5000:
            self.history = self.history[-5000:]

    def review_files(self) -> List[ProjectFile]:
        return [item for item in self.files
                if item.status in ("draft", "review", "failed")
                or item.review_reasons]

    def save(self, path: str = "") -> str:
        requested_path = path or self.project_path
        if not requested_path:
            raise ValueError("A project path is required.")
        destination = os.path.abspath(requested_path)
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        payload = asdict(self)
        payload["project_path"] = destination
        temporary = destination + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, destination)
        self.project_path = destination
        return destination

    @classmethod
    def load(cls, path: str) -> "AudioBibleProject":
        with open(path, "r", encoding="utf-8") as stream:
            data = json.load(stream)
        preset = ProjectPreset(**data.get("preset", {}))
        files = [ProjectFile(**item) for item in data.get("files", [])]
        history = [ProjectHistory(**item)
                   for item in data.get("history", [])]
        return cls(
            name=data.get("name") or os.path.splitext(
                os.path.basename(path))[0],
            project_path=os.path.abspath(path),
            root_dir=data.get("root_dir", ""),
            script_path=data.get("script_path", ""),
            preset=preset,
            files=files,
            history=history,
            version=int(data.get("version", PROJECT_VERSION)),
        )


def new_project(name: str, path: str, root_dir: str = "") -> AudioBibleProject:
    project = AudioBibleProject(
        name=name.strip() or "Audio Bible Project",
        project_path=os.path.abspath(path),
        root_dir=os.path.abspath(root_dir) if root_dir else "",
    )
    project.record("project_created")
    project.save()
    return project
