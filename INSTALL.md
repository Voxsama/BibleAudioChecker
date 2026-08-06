# ScriptureSound QC — Beginner Installation and First-Use Guide

This guide is for people who have never installed software from GitHub. You do
not need to know Python or use a terminal when installing an official Windows
or macOS package.

Official project: <https://github.com/Voxsama/BibleAudioChecker>

Official downloads: <https://github.com/Voxsama/BibleAudioChecker/releases>

> **Want the easiest version?** Use the one-page
> **[Install and Start guide](START_HERE.md)**. Continue reading this document
> only if you need detailed help or troubleshooting.

> **Important:** On a GitHub Release page, download a file listed under
> **Assets**. Do not download “Source code (zip)” unless you intend to build the
> application yourself.

## Contents

1. [Before downloading](#1-before-downloading)
2. [Install on Windows](#2-install-on-windows)
3. [Install on macOS](#3-install-on-macos)
4. [First launch and basic setup](#4-first-launch-and-basic-setup)
5. [Check Audio Bible markers](#5-check-audio-bible-markers)
6. [Master audio and apply silence](#6-master-audio-and-apply-silence)
7. [AI model packs](#7-ai-model-packs)
8. [Update the application](#8-update-the-application)
9. [Uninstall the application](#9-uninstall-the-application)
10. [Troubleshooting](#10-troubleshooting)
11. [Build from source—advanced users only](#11-build-from-sourceadvanced-users-only)

---

## 1. Before downloading

### What you need

- A 64-bit Windows PC or a supported Mac.
- At least 4 GB of free disk space for the application and temporary files.
- More free space if you later download AI models. The largest model is about
  3.1 GB.
- Internet access for the first download and optional model/update downloads.
- WAV files for checking. The recommended production format is 48 kHz,
  24-bit mono WAV.

### Supported systems

- Windows 10 or Windows 11, 64-bit.
- macOS 13 Ventura or newer.
- Apple Silicon Macs and Intel Macs use different installer files.

### Confirm that a download is official

Only download ScriptureSoundQC from the VerseVox Studio repository shown at
the top of this guide. The official app is free.

A release may contain several files:

| File | Who should download it? |
|---|---|
| `ScriptureSoundQC-Setup-v4.0-Beta.exe` | Windows users |
| `ScriptureSoundQC-v4.0-Beta-macOS-apple-silicon.pkg` | M1/M2/M3/M4/M5 Mac users |
| `ScriptureSoundQC-v4.0-Beta-macOS-intel.pkg` | Intel Mac users |
| Source code (zip/tar.gz) | Developers only |

The Beta installers may not yet be digitally signed. Windows SmartScreen or
macOS Gatekeeper may therefore ask you to confirm the installation.

---

## 2. Install on Windows

### Step 1 — Download the correct file

1. Open the [ScriptureSoundQC Releases page](https://github.com/Voxsama/BibleAudioChecker/releases).
2. Open the newest release marked **Beta**.
3. Scroll to **Assets**. If the list is collapsed, click the small arrow beside
   **Assets**.
4. Click **`ScriptureSoundQC-Setup-v4.0-Beta.exe`**.
5. Wait for the download to finish. It is a large file, so this may take several
   minutes.

Do not choose “Source code (zip).” That archive is not the Windows installer.

### Step 2 — If the browser warns about the download

Microsoft Edge or Chrome may say that the file is not commonly downloaded.
This happens because the Beta is new and unsigned.

Before continuing, confirm that the address is
`github.com/Voxsama/BibleAudioChecker`.

- In Edge, open **Downloads**, click the three dots beside the file, choose
  **Keep**, then **Show more → Keep anyway** if shown.
- In Chrome, open **Downloads** and choose **Keep** only after verifying the
  official GitHub address.

Never bypass a warning for a copy obtained from an unknown website or person.

### Step 3 — Run Setup

1. Open the **Downloads** folder.
2. Double-click **`ScriptureSoundQC-Setup-v4.0-Beta.exe`**.
3. If Windows shows **Windows protected your PC**:
   1. Confirm that the app name is ScriptureSoundQC.
   2. Click **More info**.
   3. Click **Run anyway**.
4. If Windows asks whether the installer may make changes, click **Yes**.
5. Read and accept the displayed licence.
6. Keep the suggested installation folder unless you have a reason to change
   it.
7. Leave **Create a desktop shortcut** enabled if you want an icon on the
   desktop.
8. Click **Install**.
9. When Setup finishes, click **Finish**.

The installer includes Python, the application libraries, and FFmpeg. A normal
Windows user does not need to install Python, pip, Whisper, or FFmpeg manually.

### Step 4 — Open the application

Use any one of these methods:

- Double-click the desktop shortcut.
- Open **Start**, type `ScriptureSoundQC`, and press Enter.
- Open the installed ScriptureSoundQC folder and double-click the application.

The first start can be slower while Windows scans the newly installed files.
Later starts should be faster.

---

## 3. Install on macOS

### Step 1 — Find out which Mac you have

1. Click the Apple menu **** in the upper-left corner.
2. Click **About This Mac**.
3. Look for **Chip** or **Processor**.

Choose the installer as follows:

- If it says **Apple M1, M2, M3, M4, or M5**, download
  `apple-silicon.pkg`.
- If it says **Intel**, download `intel.pkg`.

The wrong package may fail to start or may run through Rosetta unnecessarily.

### Step 2 — Download the package

1. Open the [ScriptureSoundQC Releases page](https://github.com/Voxsama/BibleAudioChecker/releases).
2. Open the newest release marked **Beta**.
3. Scroll to **Assets**.
4. Click the package matching your Mac:
   - `ScriptureSoundQC-v4.0-Beta-macOS-apple-silicon.pkg`, or
   - `ScriptureSoundQC-v4.0-Beta-macOS-intel.pkg`.
5. Wait for the download to finish.

Do not download “Source code (zip)” for a normal installation.

### Step 3 — Install the package

1. Open **Finder → Downloads**.
2. Double-click the downloaded `.pkg` file.
3. Click **Continue**.
4. Select the normal system disk, usually **Macintosh HD**.
5. Click **Install**.
6. Enter the Mac login password or use Touch ID when asked.
7. Wait for **The installation was successful**.
8. Click **Close**.

ScriptureSoundQC is installed in the **Applications** folder. The package
already includes Python and required libraries; do not run `pip install`.

### Step 4 — Open an unsigned Beta safely

Because the Beta is not notarized, double-clicking it may show a message saying
Apple cannot check it for malicious software or the developer cannot be
verified.

First verify that the package came from the official VerseVox Studio GitHub
repository. Then use one of these methods.

#### Method A — Privacy & Security

1. Try to open **Applications → ScriptureSoundQC** once.
2. Close the warning.
3. Open **Apple menu → System Settings**.
4. Select **Privacy & Security**.
5. Scroll down to **Security**.
6. Find the message saying ScriptureSoundQC was blocked.
7. Click **Open Anyway**.
8. Enter the Mac password.
9. Click **Open** in the final confirmation.

#### Method B — Control-click

1. Open the **Applications** folder in Finder.
2. Hold **Control** and click ScriptureSoundQC, or right-click it.
3. Choose **Open**.
4. Choose **Open** again.

macOS normally remembers this approval for that installed version.

### If the Mac says the package is incompatible

Check all three items:

1. macOS is version 13 Ventura or newer.
2. The package architecture matches **About This Mac**.
3. You downloaded the `.pkg`, not the source-code ZIP.

If the computer is an older Intel Mac that cannot upgrade to macOS 13, include
its exact macOS version in a GitHub issue. Do not attempt a Python 3.14 source
installation as a workaround.

---

## 4. First launch and basic setup

The first-run Quick Start window opens automatically.

### No AI download is required for marker checking

Automatic verse marking is temporarily disabled in this Beta while its timing
accuracy is improved. You can still:

- Check existing WAV markers.
- Find missing, extra, duplicate, or misspelled verse markers.
- View and manually edit markers.
- Check loudness, true peak, audio format, and front/back silence.
- Master audio to the selected LUFS and true-peak targets.
- Export QC reports.

You do not need an AI model to perform those tasks.

### Recommended first settings

1. Open **Settings**.
2. Under the QC/standards sections, confirm:
   - Sample rate: **48,000 Hz**
   - Bit depth: **24-bit**
   - Loudness: your delivery target, such as **−18.0 LUFS**
   - True peak: your ceiling, such as **−1.0 dBTP**
   - Silence: normally **2.0 seconds**
3. Choose whether the 2-second silence belongs at the front, back, or both.
4. Under marker settings, confirm:
   - Chapter title: `Chapter Title`
   - Heading: `Heading`
   - Verse word: `Verse`
5. Click **Save** or **OK**.

Change these values when the broadcaster, publisher, or project specification
requires something different.

---

## 5. Check Audio Bible markers

### Prepare filenames

The filename tells ScriptureSoundQC which book and chapter it is checking.
Examples:

```text
Gen_001.wav
1CH_001.wav
Ps_119.wav
MAT_001.wav
Rev_022.wav
```

The audio files do not need to be in the same order as the PDF. For example,
`1CH_001.wav` is matched to 1 Chronicles chapter 1 even if Genesis is the
first book in the PDF.

### Load a Bible PDF when available

1. Click **Load Bible PDF**.
2. Select the Bible PDF for the project.
3. Wait until the script summary appears beside the toolbar.
4. Confirm that the detected number of books, chapters, and verses looks
   reasonable.

For marker checking, the loaded PDF’s verse numbering is preferred. If no PDF
is loaded, the built-in 66-book ESV-compatible verse-count structure is used
as a fallback. The application does not need to bundle the copyrighted verse
text.

### Add audio

1. Click **Add Files** to select particular WAV files, or **Add Folder** to load
   every WAV inside a folder.
2. Select one or more chapters.
3. Click **Check All**.
4. Watch the progress bar. Do not close the application while checking.

### Understand the result

- **Passed** means every enabled check passed.
- **To fix** means at least one enabled check needs attention.
- Open **Chapters & QC** for the results table.
- Open **Review Queue** for a consolidated list of problems.
- Double-click a result when the interface offers more detail.

The verse check reports:

- Missing markers, such as Verse 5.
- Unexpected markers beyond the chapter’s expected count.
- Duplicate verse numbers.
- Unrecognized or misspelled labels.
- A missing Chapter Title or Heading when those are required.

### Inspect and correct markers

1. Select the chapter.
2. Open **Markers & Waveform**.
3. Select a marker in the table or click it on the waveform.
4. Use **Play Around Marker** to listen around its position.
5. Edit the label or time, add/delete a marker, or drag it on the waveform.
6. Use **Undo** if necessary.
7. Choose **Save Reviewed Copy**.

Reviewed copies are saved non-destructively. Keep the original WAV until the
reviewed output has been listened to and approved.

---

## 6. Master audio and apply silence

Before mastering, keep a backup of the original recordings.

1. Add the WAV chapters.
2. Open **Settings** and set:
   - Target LUFS.
   - LUFS tolerance.
   - Maximum true peak.
   - Required output sample rate and bit depth.
   - Front and/or back silence.
3. Open **Processing**.
4. Choose **Master Loaded Chapters**.
5. Select the output location if asked.
6. Wait for the complete operation.
7. Run **Check All** on the mastered copies.
8. Review the generated validation report.

The mastering process is designed to preserve markers, but every finished file
should still receive a final QC check.

---

## 7. AI model packs

AI models are optional in this Beta because automatic verse marking is
disabled. Installing a model is useful for language detection, script
experiments, and future Auto-Mark releases.

### Install a model without Python

1. Open **Processing**.
2. Click **AI Model Packs**.
3. Select a model.
4. Click **Download / Verify**.
5. Leave the application open until download and checksum verification finish.
6. The status should become **Installed** or **Active · Installed**.

Downloads can resume if interrupted.

| Model | Approximate download | Typical use |
|---|---:|---|
| Tiny | 75 MB | Fast test, lowest accuracy |
| Base | 142 MB | Basic testing |
| Small | 466 MB | Lower-memory computers |
| Medium | 1.49 GB | Balanced accuracy and speed |
| Large-v3 Turbo | 1.58 GB | Faster transcription |
| Large-v3 | 3.03 GB | Best general Whisper accuracy |

For Assamese, the optional Meta MMS Assamese Precision pack is separate and is
used only by the Auto-Mark alignment system. It is not required for ordinary
marker checking.

---

## 8. Update the application

### Check manually

1. Open **Processing**.
2. Click **Check for Updates**, or use the equivalent menu item.
3. If a new release is available, open the official release page.
4. Download the installer matching the operating system and architecture.
5. Close ScriptureSoundQC.
6. Run the new installer.

Installing a newer version over the existing version should preserve user
settings and projects stored outside the application folder.

### Enable automatic update checks

Open **Settings** and enable **Automatically check for updates when
ScriptureSoundQC starts**. The application checks for a release; it does not
silently install software.

---

## 9. Uninstall the application

### Windows

1. Open **Settings → Apps → Installed apps**.
2. Search for **ScriptureSoundQC**.
3. Click the three dots.
4. Click **Uninstall** and confirm.

### macOS

1. Close ScriptureSoundQC.
2. Open **Finder → Applications**.
3. Drag ScriptureSoundQC to the Trash.
4. Empty the Trash if desired.

Downloaded AI models are stored separately in the user’s
`~/.cache/whisper` folder and may remain after uninstalling. Remove that
folder only if you also want to delete all downloaded Whisper models.

---

## 10. Troubleshooting

### “No module named PySide6” on macOS

This occurs when someone downloaded the source code and the dependency
installation failed. Normal users should install the correct `.pkg` instead.

If you are intentionally running from source on an Intel Mac, do not use
Python 3.14. Follow the Python 3.12 source instructions in the advanced section.

### “No matching distribution found for pedalboard” on an Intel Mac

The environment is usually Python 3.14. Recreate it with Python 3.12:

```bash
deactivate 2>/dev/null || true
brew install python@3.12 ffmpeg
"$(brew --prefix python@3.12)/bin/python3.12" -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

### “Failed building wheel for llvmlite” or “Failed to build numba” on an Intel Mac

This is not an LLVM installation task for the user. It means pip selected new
releases that no longer provide Intel macOS wheels and then tried to compile
them. The later `No module named PySide6` message is only a secondary symptom:
pip stopped before it finished installing the requirements.

Download or pull the newest ScriptureSoundQC source, open Terminal in that
folder, and run the included repair/setup helper:

```bash
bash setup_mac.sh
source .venv-mac/bin/activate
python main.py
```

On Intel Macs the helper deliberately installs binary wheels for NumPy 1.26.4,
PyTorch 2.2.2, llvmlite 0.44.0, and Numba 0.61.2 before the remaining
requirements. Do not install LLVM and do not let pip build llvmlite from source.

### Windows says “This app can’t run on your PC”

Confirm that:

- Windows is 64-bit.
- The download completed fully.
- You downloaded the Setup `.exe`, not a macOS package.
- The file came from the official repository.

Delete an incomplete download and download it again.

### The application opens slowly the first time

Windows or macOS may scan a newly downloaded unsigned application. The first
start can therefore be slower. Later starts should be faster. Do not repeatedly
launch the app while the first copy is still opening.

### Loudness or true peak says FFmpeg is unavailable

Official packaged builds include FFmpeg. If this appears:

1. Confirm you used the official Setup/`.pkg` rather than running source.
2. Reinstall the same release.
3. If running from source, install FFmpeg:
   - Windows: place `ffmpeg.exe` beside the project.
   - macOS: run `brew install ffmpeg`.

### A PDF loads the wrong chapter for an audio file

Check the filename. It must contain a recognized book abbreviation and chapter
number. `1CH_001.wav` means 1 Chronicles 1; it is not matched by the file’s
position in the folder.

### Marker checking is slow

Disable checks you do not need under **Settings**. Loudness and true-peak
measurement take longer than marker-only checking. AI/script verification also
takes considerably longer.

### AI model download stops

1. Keep the application open.
2. Check the internet connection and available disk space.
3. Open **AI Model Packs** again.
4. Select the same model and click **Download / Verify** to resume.

### The Mac app is still blocked

Use **System Settings → Privacy & Security → Open Anyway** after attempting to
open it once. If there is no Open Anyway option, verify that the app is in
Applications and try Control-click → Open.

### Getting help

Open an issue at
<https://github.com/Voxsama/BibleAudioChecker/issues> and include:

- Windows version or macOS version.
- For Mac, whether the chip is Apple Silicon or Intel.
- The ScriptureSoundQC version.
- The exact step that failed.
- A screenshot of the full error.
- Whether you used the official installer or source code.

Never post passwords, API keys, private Bible manuscripts, or confidential
audio in a public issue.

---

## 11. Build from source—advanced users only

This section is for developers and testers. Normal users should install the
Windows Setup or macOS package.

### Windows source setup

1. Install 64-bit Python 3.12 from <https://www.python.org/downloads/>.
2. During installation, enable **Add Python to PATH**.
3. Install or place `ffmpeg.exe` in the repository root.
4. Download or clone the repository.
5. Open Command Prompt in the repository folder.
6. Run:

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python main.py
```

To build the distributable:

```bat
build_windows.bat
build_installer.bat
```

Outputs:

- Fast-start application:
  `dist-beta\ScriptureSoundQC\ScriptureSoundQC.exe`
- Setup installer:
  `dist\installer\ScriptureSoundQC-Setup-v4.0-Beta.exe`

### macOS source setup

Requirements:

- macOS 13 or newer.
- Xcode Command Line Tools.
- Homebrew.
- Python 3.12 specifically.
- FFmpeg.

Install the prerequisites:

```bash
xcode-select --install
brew install python@3.12 ffmpeg
```

Download the repository, then run:

```bash
cd ~/Documents/BibleAudioChecker
bash setup_mac.sh
source .venv-mac/bin/activate
python main.py
```

The helper creates or repairs the private Python 3.12 environment, installs the
Intel-specific prebuilt compatibility wheels when necessary, installs the
remaining requirements, and verifies the important imports. Do not reuse a
virtual environment created with Python 3.14 on an Intel Mac.

To build a native app and package:

```bash
bash build_mac.sh
```

Outputs:

- `dist-mac/ScriptureSoundQC.app`
- `dist-mac/ScriptureSoundQC-v4.0-Beta-macOS-<architecture>.pkg`

The GitHub Actions workflow builds Intel and Apple Silicon packages separately
with Python 3.12.
