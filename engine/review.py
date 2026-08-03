"""Build one review queue from QC, Auto-Mark, language, and mastering results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List


@dataclass
class ReviewItem:
    path: str
    category: str
    severity: str
    message: str
    marker_label: str = ""
    time_s: float = -1.0


def review_from_file_report(path: str, report) -> List[ReviewItem]:
    if report is None:
        return [ReviewItem(path, "QC", "warning", "File has not been checked.")]
    if report.error:
        return [ReviewItem(path, "QC", "error", report.error)]
    return [
        ReviewItem(path, item.name, "error", item.detail)
        for item in report.items if not item.passed]


def review_from_automark(path: str, result) -> List[ReviewItem]:
    if result is None:
        return []
    if result.error:
        return [ReviewItem(path, "Auto-Mark", "error", result.error)]
    items = []
    for marker in result.markers:
        if marker.label == "Chapter Title":
            continue
        if marker.confidence < 0.55 or "interpolated" in marker.method:
            items.append(ReviewItem(
                path=path, category="Marker", severity="warning",
                message="%s confidence %.0f%% (%s)" %
                (marker.label, marker.confidence * 100, marker.method),
                marker_label=marker.label, time_s=marker.time_s))
    return items


def review_from_language(path: str, detection,
                         minimum_confidence: float = 0.70) -> List[ReviewItem]:
    if detection is None:
        return []
    if detection.error:
        return [ReviewItem(path, "Language", "error", detection.error)]
    if detection.resolution_source == "script-conflict":
        return [ReviewItem(
            path, "Language", "warning",
            detection.resolution_note or
            "The detected audio language conflicts with the loaded script.")]
    if detection.confidence < minimum_confidence:
        return [ReviewItem(
            path, "Language", "warning",
            "Detected %s at only %.0f%% confidence." %
            (detection.language or "unknown", detection.confidence * 100))]
    return []


def review_from_calibration(path: str, calibration) -> List[ReviewItem]:
    if calibration is None or calibration.automatic_path != path:
        return []
    items = [
        ReviewItem(
            path, "Calibration", "error",
            "Missing automatic marker: %s" % label,
            marker_label=label)
        for label in calibration.missing_in_automatic]
    items.extend(
        ReviewItem(
            path, "Calibration", "warning",
            "%s differs by %.3fs (limit %.3fs)" %
            (entry.label, entry.absolute_error_s,
             calibration.threshold_s),
            marker_label=entry.label,
            time_s=entry.automatic_time_s)
        for entry in calibration.matched
        if entry.absolute_error_s > calibration.threshold_s)
    return items


def merge_review_items(*groups: Iterable[ReviewItem]) -> List[ReviewItem]:
    items = []
    for group in groups:
        items.extend(list(group))
    severity_order = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda item: (
        severity_order.get(item.severity, 9), item.path,
        item.time_s if item.time_s >= 0 else -1))
    return items
