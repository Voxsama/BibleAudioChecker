# ScriptureSound QC

A desktop app that automates the QC you currently do by hand in Audition + the
Orban Loudness Meter. Point it at your mastered WAV files and it checks, for
every file, all in one place:

1. **Format** — the file really is your studio spec (default **48 kHz / 24-bit**)
2. **Loudness** — integrated loudness is within your target (default **−18.0 LUFS ± 0.5**)
3. **True peak** — at or below your ceiling (default **−1.0 dBTP**)
4. **Head silence** — ~2 s of silence at the start
5. **Tail silence** — ~2 s of silence at the end
6. **Markers** — reads the markers embedded in the WAV, classifies each into
   **Chapter Title / Heading / Verse N**, checks the marker spelling, and
   verifies the verse markers are complete: if the chapter has 30 verses, there
   must be Verse 1…Verse 30 with none missing, extra, or duplicated (the
   Chapter Title and Heading are excluded from the count).

It figures out which book & chapter each file is from its **filename**
(e.g. `Gen_001.wav`, `GEN_001.wav`, `1Sa_005.wav`, `Ps_119.wav`) and looks up
the correct verse count from a built-in **KJV (66-book)** database.

Failing files are flagged red, and clicking a row tells you **exactly what is
wrong and where** (which verse numbers are missing, which marker is misspelled
and at what timecode, the measured LUFS, etc.).

**In the app you also get:** an embedded **waveform view** that redraws for
whichever chapter you click, with the markers overlaid like Audition and the
head/tail silence shaded; and a two-mode **export** — *Mistakes only* (one tidy
row per problem file, so people see just what to fix) or *Full report*.

---

## How the checks are measured (accuracy note)

- **Loudness & true peak** use **ffmpeg's EBU R128 meter** (`ebur128`), which
  implements the ITU-R BS.1770 / EBU R128 standard — the same standard the Orban
  Loudness Meter reports. Values track Orban within a few tenths of a LU. This
  is why ffmpeg is required (see install steps below).
- **Markers** are read straight out of the WAV's embedded `cue`/`labl` chunks —
  the same markers you place in Audition. No export step needed; just save the
  WAV with markers.
- **Silence** is measured from the actual audio samples (peak below −60 dBFS by
  default, all editable in Settings).
- **File format** — handles **48 kHz / 24-bit** WAV (and 16-bit), including
  `WAVE_FORMAT_EXTENSIBLE` files that Python's built-in reader chokes on. Headers
  are parsed directly and only the first/last few seconds are read for the
  silence check, so large 24-bit masters don't get loaded into memory.

---

## Install & run

### 1. Install Python 3.9+
- **Windows:** get it from https://www.python.org/downloads/ (tick *"Add
  Python to PATH"* during install).
- **macOS:** `brew install python` or from python.org.

### 2. Install ffmpeg (required for loudness/true-peak)
- **Windows:** download from https://www.gyan.dev/ffmpeg/builds/ (the
  "essentials" build), unzip, and add the `bin` folder to your PATH. Verify with
  `ffmpeg -version` in a new terminal.
- **macOS:** `brew install ffmpeg`

> If ffmpeg isn't found, the app still runs and checks markers + silence, but
> shows a warning and skips the loudness/true-peak checks.

### 3. Install the app's Python dependency
In a terminal, from this folder:
```
pip install -r requirements.txt
```

### 4. Run
```
python main.py
```
Then **Add Files…** or **Add Folder…** (or drag WAVs onto the window) and click
**Check All**.

---

## Command-line / batch mode (optional)

Handy for scripting or checking a whole folder at once without the window:
```
python -m cli  "C:\path\to\wavs"  --json report.json
python -m cli  file1.wav file2.wav --no-loudness
```
Exit code is `0` if every file passed, non-zero otherwise (useful in scripts).

---

## Settings (your studio's standards)

Open **Settings…** to edit and save:

| Setting | Default | Meaning |
|---|---|---|
| Target loudness | −18.0 LUFS | integrated loudness target |
| Loudness tolerance | ± 0.5 LU | pass band around the target |
| True-peak ceiling | −1.0 dBTP | maximum allowed true peak |
| Edge silence length | 2.0 s | expected silence at head & tail |
| Silence tolerance | ± 0.5 s | how much the silence length may vary |
| Silence threshold | −60 dBFS | level below which audio counts as "silent" |
| Chapter-title marker text | `Chapter Title` | exact marker name to match |
| Heading marker text | `Heading` | exact marker name to match |
| Verse marker word | `Verse` | verse markers look like "Verse 1", "Verse 2"… |

Settings are saved to `~/.bible_audio_checker/config.json` and persist between
runs.

---

## Filename → book/chapter

The app recognises common book abbreviations, case-insensitive, followed by a
separator and the chapter number. All of these work:

```
Gen_001.wav      GEN_001.wav      Genesis_1.wav
1Sa_005.wav      1Sam_005.wav     Ps_119.wav
Jon_001.wav      Rev_022.wav      1John_1.wav
```

If a filename can't be matched to a book/chapter, every other check still runs;
only the verse-count comparison is skipped (the app tells you so).

---

## Making a double-click app (.exe / .app)

There is **no prebuilt .exe in this download** — a Windows executable must be
compiled on a Windows machine (the same is true for a Mac .app on macOS). But
it's a one-step process:

**Windows** — double-click **`build_windows.bat`**.
It installs what's needed and produces **`dist\ScriptureSoundQC.exe`**, a single
file you can copy anywhere and run by double-clicking.

**macOS** — in Terminal run **`bash build_mac.sh`**.
It produces **`dist/ScriptureSoundQC.app`**.

### Make it fully self-contained (no ffmpeg install for end users)
The app needs ffmpeg at runtime for the loudness/true-peak checks. To bake it
in so nothing else has to be installed:

- **Windows:** download `ffmpeg.exe`, drop it in this folder next to
  `build_windows.bat`, then run the script. It gets bundled inside the .exe.
- **macOS:** `brew install ffmpeg`, then `cp $(which ffmpeg) ./ffmpeg` and run
  `build_mac.sh`.

The app looks for ffmpeg in this order: the `BAC_FFMPEG` environment variable,
a copy bundled inside the app, a copy sitting next to the app, then the system
PATH. So even after building, you can just drop an `ffmpeg` binary beside the
app and it will find it.

## Project layout

```
bible-audio-checker/
├─ main.py               # desktop entry point
├─ cli.py                # batch/command-line runner
├─ requirements.txt
├─ engine/               # all checking logic (no GUI, fully testable)
│  ├─ wavio.py           # low-level RIFF reader (24-bit / EXTENSIBLE safe)
│  ├─ wav_markers.py     # read embedded cue/labl markers (stdlib)
│  ├─ loudness.py        # LUFS + true peak via ffmpeg ebur128
│  ├─ silence.py         # head/tail silence (stdlib)
│  ├─ bible_db.py        # KJV 66-book verse counts + filename parser
│  ├─ checker.py         # runs all checks -> per-file report
│  └─ config.py          # editable thresholds, saved to disk
├─ gui/
│  └─ app.py             # PySide6 window
└─ tests/
   ├─ make_test_wav.py   # synthetic WAV generator (markers + silence)
   └─ test_engine.py     # automated checks
```

## Run the tests
```
python -m tests.test_engine
```
