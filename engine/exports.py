"""Additional marker and review export formats."""

from __future__ import annotations

import csv
import json
import os
import xml.etree.ElementTree as ET
from typing import Iterable, List, Tuple


def write_marker_json(
        path: str, wav_path: str,
        markers: Iterable[Tuple[str, float]],
        metadata: dict = None) -> None:
    payload = {
        "version": 1,
        "audio_file": os.path.abspath(wav_path),
        "metadata": metadata or {},
        "markers": [
            {"label": label, "time_s": float(time_s)}
            for label, time_s in markers],
    }
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)


def write_reaper_csv(
        path: str, markers: Iterable[Tuple[str, float]]) -> None:
    """Write REAPER-compatible marker/region CSV."""
    with open(path, "w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["#", "Name", "Start", "End", "Length", "Color"])
        for index, (label, time_s) in enumerate(markers, 1):
            writer.writerow([
                "M%d" % index, label, "%.6f" % float(time_s), "", "", ""])


def write_cue_sheet(
        path: str, wav_path: str,
        markers: Iterable[Tuple[str, float]]) -> None:
    """Write a human-readable CUE sheet."""
    with open(path, "w", encoding="utf-8") as stream:
        stream.write('FILE "%s" WAVE\n' % os.path.basename(wav_path))
        for index, (label, time_s) in enumerate(markers, 1):
            total_frames = int(round(float(time_s) * 75.0))
            minutes = total_frames // (60 * 75)
            seconds = (total_frames // 75) % 60
            frames = total_frames % 75
            stream.write("  TRACK %02d AUDIO\n" % index)
            stream.write('    TITLE "%s"\n' % label.replace('"', "'"))
            stream.write(
                "    INDEX 01 %02d:%02d:%02d\n" %
                (minutes, seconds, frames))


def write_ixml_sidecar(
        path: str, wav_path: str,
        markers: Iterable[Tuple[str, float]],
        project_name: str = "") -> None:
    """Write an iXML-style sidecar without modifying the source WAV."""
    root = ET.Element("BWFXML")
    ET.SubElement(root, "PROJECT").text = project_name
    ET.SubElement(root, "FILENAME").text = os.path.basename(wav_path)
    marker_list = ET.SubElement(root, "MARKERS")
    for index, (label, time_s) in enumerate(markers, 1):
        marker = ET.SubElement(marker_list, "MARKER")
        ET.SubElement(marker, "ID").text = str(index)
        ET.SubElement(marker, "NAME").text = label
        ET.SubElement(marker, "TIME_SECONDS").text = "%.6f" % float(time_s)
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)


def export_marker_bundle(
        output_dir: str, wav_path: str,
        markers: Iterable[Tuple[str, float]],
        metadata: dict = None) -> List[str]:
    os.makedirs(output_dir, exist_ok=True)
    marker_list = list(markers)
    base = os.path.splitext(os.path.basename(wav_path))[0]
    outputs = [
        os.path.join(output_dir, base + "_markers.json"),
        os.path.join(output_dir, base + "_reaper.csv"),
        os.path.join(output_dir, base + ".cue"),
        os.path.join(output_dir, base + "_ixml.xml"),
    ]
    write_marker_json(outputs[0], wav_path, marker_list, metadata)
    write_reaper_csv(outputs[1], marker_list)
    write_cue_sheet(outputs[2], wav_path, marker_list)
    write_ixml_sidecar(
        outputs[3], wav_path, marker_list,
        (metadata or {}).get("project", ""))
    return outputs

