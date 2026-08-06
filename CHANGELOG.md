# Changelog

## v4.0 Beta (2026-07-28)
- Replaced the mixed developer notes with a complete beginner installation and
  first-use guide for Windows, Apple Silicon Macs, and Intel Macs
- Added a one-page `START_HERE.md` installer guide and reduced the in-app Quick
  Start to four plain-language steps for checking, reviewing, and processing WAVs
- Added a documentation index and a dedicated Mac `.pkg` guide covering local
  Intel/Apple Silicon builds, GitHub Actions artifacts, testing, and signing
- Fixed Intel Mac source/build installation by selecting an isolated Python
  3.12 environment instead of an incompatible Homebrew Python 3.14 runtime
- Prevented Intel Macs from compiling LLVM by pinning the last compatible
  prebuilt NumPy, PyTorch, Numba, and llvmlite wheels; added `setup_mac.sh` to
  install and verify the correct dependency set for beginners
- Added a centralized database of all 22 scheduled Indian languages with
  native names, ISO codes, script metadata, and safe Whisper compatibility
  flags; corrected Bodo to `brx` so it cannot collide with Tibetan `bo`
- Changed Windows packaging from one-file extraction to a fast-start installed
  layout; users still receive one normal Setup installer
- Added reproducible Apple Silicon and Intel macOS `.pkg` build automation
- Added an in-app update checker with an optional automatic startup check,
  Beta/stable channels, and a safe link to the official installer release
- Added the optional Meta MMS Assamese Precision Pack (`asm`) with pinned,
  resumable, SHA-256-verified in-app download; weights remain outside the EXE
- Assamese Auto-Mark now prefers MMS CTC frame timestamps, monotonic fuzzy
  scripture alignment, and pause refinement; Whisper remains the fallback
- Real `1CH_001.wav` validation improved script coverage from 34.01% with the
  Whisper workaround to 84.81% with MMS, with 54 ordered verse anchors
- Fixed the marker table's “need attention” count so low-confidence MMS and
  interpolated markers are visibly included
- Added a first-run Quick Start guide for packaged users, with direct access
  to the in-app AI Model Packs manager
- Added stage-aware Auto-Mark progress and live marker table/waveform previews
  as soon as alignment positions are available
- Language detection now resolves Whisper's Bengali/Assamese confusion using
  distinctive Assamese letters in the matching loaded PDF chapter, while
  retaining the raw acoustic result and warning on real script/audio conflicts
- When the MMS precision pack is unavailable, Assamese Auto-Mark can still use
  Whisper's Bengali acoustic decoder as a clearly reported fallback
- Added persistent Whisper word-timeline caching, strict low-overlap rejection,
  mandatory pause-draft review, and numerical verse-order protection
- Added an in-app multilingual AI Model Packs manager with resumable downloads,
  progress/speed display, SHA-256 verification, activation, and safe removal
- Auto-Mark and language detection now offer the model manager when the
  selected model pack is missing
- Added persistent multilingual Audio Bible project files and production history
- Added editable marker table and draggable waveform markers with undo/redo,
  speech/zero-crossing snapping, preview, and reviewed-copy saving
- Added unified review queue for QC, language, Auto-Mark, and calibration issues
- Added automatic spoken-language detection with top-three candidates
- Added calibration metrics and CSV/JSON evidence export
- Added SHA-256 PDF parse cache and background script loading
- Added typography-aware Assamese PDF heading extraction and optional
  transcript-aligned Heading markers
- Added cross-script Indic phonetic alignment for cases where Whisper decodes
  Assamese speech in Devanagari while the PDF uses Assamese/Bengali script
- Zero-anchor transcriptions are now rejected instead of producing a complete
  set of misleading script-interpolated markers
- Added alignment backend selector with script and pause-draft modes
- Added ordered VST3 processing and background batch mastering
- Added strict post-master LUFS, true-peak, silence, format, mono, and marker
  preservation validation plus a JSON audit report
- Added JSON, REAPER CSV, CUE, and iXML-style marker bundle exports
## v3.0 Preview (2026-07-28)
- Reworked GUI with Chapters & QC, Markers & Waveform, and Processing tabs
- Selected-chapter marker table with type, time, sample offset, and duration
- Independent front/back silence application settings
- Marker timing transform fixed for head trim/pad and sample-rate conversion
- Chapter-aware Assamese/English PDF script parsing
- Assamese Auto-Mark defaults to language `as` and Whisper `large-v3`
- Replaced sliding character matching with ordered Unicode script-token alignment
- Pause fallback now includes Verse 1 and every expected verse
- Auto-Mark confidence scoring and draft/review warnings
- Mastering button restored and packaging dependencies aligned

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
