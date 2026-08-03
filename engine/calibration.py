"""Compare automatic markers with a manually checked reference."""

from __future__ import annotations

import csv
import json
import math
import os
import statistics
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Tuple

from .csv_markers import read_csv_markers
from .wav_markers import read_markers


@dataclass
class CalibrationEntry:
    label: str
    automatic_time_s: float
    reference_time_s: float
    signed_error_s: float
    absolute_error_s: float


@dataclass
class CalibrationResult:
    automatic_path: str = ""
    reference_path: str = ""
    matched: List[CalibrationEntry] = field(default_factory=list)
    missing_in_automatic: List[str] = field(default_factory=list)
    extra_in_automatic: List[str] = field(default_factory=list)
    median_error_s: float = 0.0
    p95_error_s: float = 0.0
    worst_error_s: float = 0.0
    mean_error_s: float = 0.0
    threshold_s: float = 0.25

    @property
    def pass_rate(self) -> float:
        if not self.matched:
            return 0.0
        passed = sum(entry.absolute_error_s <= self.threshold_s
                     for entry in self.matched)
        return passed / float(len(self.matched))

    @property
    def ok(self) -> bool:
        return (bool(self.matched) and not self.missing_in_automatic
                and not self.extra_in_automatic
                and self.p95_error_s <= self.threshold_s)

    @property
    def summary(self) -> str:
        return (
            "%d matched | median %.3fs | P95 %.3fs | worst %.3fs | "
            "%.0f%% within %.3fs" %
            (len(self.matched), self.median_error_s, self.p95_error_s,
             self.worst_error_s, self.pass_rate * 100, self.threshold_s))


def _normal_label(label: str) -> str:
    return " ".join((label or "").strip().lower().split())


def load_marker_points(path: str) -> List[Tuple[str, float]]:
    extension = os.path.splitext(path)[1].lower()
    if extension == ".wav":
        return [(marker.label, marker.seconds)
                for marker in read_markers(path)]
    if extension == ".csv":
        return [(marker.name, marker.start_seconds)
                for marker in read_csv_markers(path)]
    if extension == ".json":
        with open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        source = payload.get("markers", payload)
        return [(str(item["label"]), float(item["time_s"]))
                for item in source]
    raise ValueError("Unsupported marker reference: %s" % extension)


def _percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def compare_marker_files(
        automatic_path: str, reference_path: str,
        threshold_s: float = 0.25) -> CalibrationResult:
    automatic = load_marker_points(automatic_path)
    reference = load_marker_points(reference_path)
    return compare_marker_points(
        automatic, reference, threshold_s,
        automatic_path=automatic_path, reference_path=reference_path)


def compare_marker_points(
        automatic: Iterable[Tuple[str, float]],
        reference: Iterable[Tuple[str, float]],
        threshold_s: float = 0.25,
        automatic_path: str = "", reference_path: str = ""
        ) -> CalibrationResult:
    auto_by_label: Dict[str, List[Tuple[str, float]]] = {}
    ref_by_label: Dict[str, List[Tuple[str, float]]] = {}
    for label, time_s in automatic:
        auto_by_label.setdefault(
            _normal_label(label), []).append((label, float(time_s)))
    for label, time_s in reference:
        ref_by_label.setdefault(
            _normal_label(label), []).append((label, float(time_s)))

    result = CalibrationResult(
        automatic_path=automatic_path,
        reference_path=reference_path,
        threshold_s=threshold_s,
    )
    for key in sorted(set(auto_by_label) | set(ref_by_label)):
        auto_items = auto_by_label.get(key, [])
        ref_items = ref_by_label.get(key, [])
        pair_count = min(len(auto_items), len(ref_items))
        for index in range(pair_count):
            label, auto_time = auto_items[index]
            _reference_label, reference_time = ref_items[index]
            signed = auto_time - reference_time
            result.matched.append(CalibrationEntry(
                label=label,
                automatic_time_s=auto_time,
                reference_time_s=reference_time,
                signed_error_s=signed,
                absolute_error_s=abs(signed),
            ))
        result.extra_in_automatic.extend(
            label for label, _time in auto_items[pair_count:])
        result.missing_in_automatic.extend(
            label for label, _time in ref_items[pair_count:])

    absolute_errors = [entry.absolute_error_s for entry in result.matched]
    if absolute_errors:
        result.median_error_s = statistics.median(absolute_errors)
        result.p95_error_s = _percentile(absolute_errors, 0.95)
        result.worst_error_s = max(absolute_errors)
        result.mean_error_s = statistics.mean(absolute_errors)
    return result


def write_calibration_json(path: str, result: CalibrationResult) -> None:
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(asdict(result), stream, ensure_ascii=False, indent=2)


def write_calibration_csv(path: str, result: CalibrationResult) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow([
            "Label", "AutomaticSeconds", "ReferenceSeconds",
            "SignedErrorSeconds", "AbsoluteErrorSeconds", "WithinThreshold"])
        for entry in result.matched:
            writer.writerow([
                entry.label, "%.6f" % entry.automatic_time_s,
                "%.6f" % entry.reference_time_s,
                "%.6f" % entry.signed_error_s,
                "%.6f" % entry.absolute_error_s,
                "YES" if entry.absolute_error_s <= result.threshold_s else "NO",
            ])

