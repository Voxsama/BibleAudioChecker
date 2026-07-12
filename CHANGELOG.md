# Changelog

## v2.5 (2026-07-12)
- **Mastering**: Auto-master WAV files to broadcast standards (Pedalboard + pyloudnorm)
  - High-pass filter, noise gate, loudness normalize, gentle limiter
  - Output to folder: `GEN_Mastered/GEN_001.wav` (filename unchanged)
  - Mono output, preserves markers
  - Two-pass loudness + guaranteed true peak <= -1 dBTP
- **Heading markers**: Recognizes `Heading 01`, `Heading 02`, etc. (not just "Heading")
- Dependencies: pedalboard, pyloudnorm, numpy

## v2.0 (2026-07-12)
- **AI Auto-Marker**: Automatically place verse markers using Whisper (free, offline)
  - Transcribes audio with word-level timestamps
  - Matches script verses to find verse boundaries
  - Falls back to pause detection for unsupported languages
  - Learns from user corrections over time
  - Output: `GEN_001_marked.wav`
- **Correction Memory**: Gets smarter the more you use it
- **GPL v3 License**: Must credit Voxsama if you use/modify this software
- **About dialog**: Shows credits, license, and version info
- **Whisper bundled in .exe build**

## v1.5 (2026-07-12)
- **Speech-to-Text Script Verification**: Upload PDF, verify audio matches script
  - Supports all Indian languages (Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, etc.)
  - Local Whisper or OpenAI API mode
- **Zoomable Waveform**: Mouse wheel zoom, click-drag pan, double-click reset
- **Toggle-able Checks**: Enable/disable individual checks in Settings
- **Missing Chapter Detection**: Flags if a book is missing chapters
- **Settings Tabs**: Organized into Checks / Mastering / Markers / Script STT
- **Logo & Banner**: Custom branding in header
- **INSTALL.md**: Detailed installation guide for beginners

## v1.0 (2024)
- Initial release
- Loudness check (ffmpeg EBU R128)
- True peak check
- Head/tail silence check
- Format check (48kHz / 24-bit)
- Marker validation (Chapter Title, Heading, Verse spelling)
- Verse completeness (KJV 66-book database)
- Waveform view with marker overlay
- CSV export (mistakes only / full report)
- CLI batch mode with JSON export
- PySide6 desktop GUI
- Windows .exe and macOS .app build scripts
