# ScriptureSound QC — Installation Guide

A step-by-step guide to install and run ScriptureSound QC on **Windows** and **macOS**.
No programming knowledge required.

---

## Table of Contents

1. [Windows Installation](#windows-installation)
2. [macOS Installation](#macos-installation)
3. [First Launch — Bypassing Security Warnings](#first-launch--bypassing-security-warnings)
4. [Installing ffmpeg (Required for Loudness Checks)](#installing-ffmpeg)
5. [Installing Whisper (Optional — For Script Verification)](#installing-whisper-optional)
6. [Troubleshooting](#troubleshooting)

---

## Windows Installation

### Option A: Use the Pre-Built .exe (Easiest)

If someone has given you a `ScriptureSoundQC.exe` file:

1. **Copy** `ScriptureSoundQC.exe` to any folder you like (e.g., your Desktop or `C:\Programs\`)
2. **Double-click** it to run
3. If you see a blue "Windows protected your PC" warning — see [Bypassing Security Warnings](#windows--smartscreen-warning) below

That's it! The .exe is a single self-contained file.

---

### Option B: Build It Yourself From Source

Use this if you want the latest version or want to modify the app.

#### Step 1: Install Python

1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.x.x"** button
3. Run the installer
4. **IMPORTANT:** On the first screen, tick the checkbox that says:
   > **"Add Python to PATH"**
5. Click **"Install Now"**
6. Wait for it to finish, then close the installer

**How to verify it worked:**
- Press `Win + R`, type `cmd`, press Enter
- Type `python --version` and press Enter
- You should see something like `Python 3.12.x`

#### Step 2: Install ffmpeg

1. Go to **https://www.gyan.dev/ffmpeg/builds/**
2. Under "Release builds", click **"ffmpeg-release-essentials.zip"**
3. Open the downloaded .zip file
4. Inside you'll find a folder like `ffmpeg-7.x-essentials_build`
5. Open that folder, then open the `bin` folder
6. You'll see `ffmpeg.exe` — **copy this file**
7. Paste it into the ScriptureSound QC project folder (next to `main.py`)

**Or add ffmpeg to your system PATH (advanced):**
- Copy the full path to the `bin` folder (e.g., `C:\ffmpeg\bin`)
- Search "Environment Variables" in the Start menu
- Click "Environment Variables..."
- Under "User variables", select `Path`, click "Edit"
- Click "New", paste the path, click OK

**Verify:** Open a new Command Prompt, type `ffmpeg -version`, press Enter.

#### Step 3: Download ScriptureSound QC

1. Go to **https://github.com/Voxsama/BibleAudioChecker**
2. Click the green **"Code"** button
3. Click **"Download ZIP"**
4. Extract the ZIP to a folder (e.g., `C:\ScriptureSoundQC\`)

#### Step 4: Install Dependencies

1. Open **Command Prompt** (press `Win + R`, type `cmd`, press Enter)
2. Navigate to the folder:
   ```
   cd C:\ScriptureSoundQC\BibleAudioChecker-main
   ```
3. Run:
   ```
   pip install -r requirements.txt
   ```
4. Wait for it to download and install (may take a few minutes)

#### Step 5: Run the App

In the same Command Prompt window:
```
python main.py
```

The app window should open!

#### Step 6 (Optional): Build a Standalone .exe

If you want a single .exe you can share with others:
1. Double-click **`build_windows.bat`**
2. Wait for it to finish (takes 2-5 minutes)
3. Your .exe will be at: `dist\ScriptureSoundQC.exe`

---

## macOS Installation

### Option A: Use the Pre-Built .app or .pkg (Easiest)

**If you have a .pkg file:**
1. Double-click the `.pkg` file
2. Follow the installer steps (Next, Next, Install)
3. Enter your Mac password when asked
4. The app installs to **Applications**
5. Open **Launchpad** or go to `/Applications/` and click **ScriptureSoundQC**

**If you have a .app file:**
1. Drag `ScriptureSoundQC.app` to your **Applications** folder
2. Double-click to open
3. If you see a security warning — see [Bypassing Security Warnings](#macos--unidentified-developer-warning) below

---

### Option B: Build It Yourself From Source

#### Step 1: Install Homebrew (if you don't have it)

Homebrew is a package manager for Mac. Open **Terminal** (search "Terminal" in Spotlight) and paste:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Press Enter and follow the prompts. Enter your Mac password when asked.

#### Step 2: Install Python and ffmpeg

In Terminal:
```bash
brew install python ffmpeg
```
Wait for it to finish.

#### Step 3: Download ScriptureSound QC

1. Go to **https://github.com/Voxsama/BibleAudioChecker**
2. Click the green **"Code"** button
3. Click **"Download ZIP"**
4. Double-click the ZIP in Finder to extract it
5. Move the folder somewhere convenient (e.g., your Documents)

**Or use Terminal:**
```bash
cd ~/Documents
git clone https://github.com/Voxsama/BibleAudioChecker.git
cd BibleAudioChecker
```

#### Step 4: Install Dependencies

In Terminal, navigate to the folder and install:
```bash
cd ~/Documents/BibleAudioChecker
pip3 install -r requirements.txt
```
Wait for it to finish (may take a few minutes).

#### Step 5: Run the App

```bash
python3 main.py
```

The app window should open!

#### Step 6 (Optional): Build a .app and .pkg Installer

To create a proper macOS app bundle + installer:

1. (Optional) Place your `logo.png` (1024x1024) in the project folder
2. (Optional) Copy ffmpeg into the project for a self-contained app:
   ```bash
   cp $(which ffmpeg) ./ffmpeg
   ```
3. Run the build script:
   ```bash
   bash build_mac.sh
   ```
4. Your files will be:
   - `dist/ScriptureSoundQC.app` — the app
   - `dist/ScriptureSoundQC-1.5.pkg` — installer to share

---

## First Launch — Bypassing Security Warnings

### Windows — SmartScreen Warning

When you first run the .exe, you may see a blue screen that says:
> **"Windows protected your PC"**
> Microsoft Defender SmartScreen prevented an unrecognized app from starting.

**How to bypass:**
1. Click **"More info"** (small text link at the bottom)
2. Click **"Run anyway"**
3. The app opens! This warning won't appear again for this file.

**Why this happens:** Windows flags any .exe that isn't from a well-known publisher. The app is safe — it's open source and you can inspect all the code on GitHub.

---

### macOS — "Unidentified Developer" Warning

When you first open the app, macOS may show:
> **"ScriptureSoundQC.app can't be opened because it is from an unidentified developer"**

**Method 1: Right-click to Open (Easiest)**
1. Find the app in Finder (in Applications or wherever you saved it)
2. **Right-click** (or Control-click) on the app
3. Click **"Open"** from the menu
4. A dialog appears — click **"Open"** again
5. The app launches! macOS remembers your choice — it won't ask again.

**Method 2: Terminal Command (One-Time Fix)**

If Method 1 doesn't work, open Terminal and run:
```bash
xattr -cr /Applications/ScriptureSoundQC.app
```
(Change the path if your app is in a different location.)

Then double-click the app normally.

**Method 3: System Settings (If the above don't work)**
1. Open **System Settings** (or System Preferences on older macOS)
2. Go to **Privacy & Security**
3. Scroll down — you'll see a message about the blocked app
4. Click **"Open Anyway"**
5. Enter your password
6. The app launches!

**Why this happens:** Apple requires developers to pay $99/year for a signing certificate. This is a legitimate open-source app — all the code is available at github.com/Voxsama/BibleAudioChecker.

---

## Installing ffmpeg

ffmpeg is needed for the **Loudness** and **True Peak** checks. Without it, the app still works but skips those two checks.

### Windows

1. Go to **https://www.gyan.dev/ffmpeg/builds/**
2. Download **"ffmpeg-release-essentials.zip"**
3. Extract the ZIP
4. Find `ffmpeg.exe` inside the `bin` folder
5. Either:
   - **Easy:** Copy `ffmpeg.exe` next to `ScriptureSoundQC.exe` (same folder)
   - **Advanced:** Add the `bin` folder to your system PATH

### macOS

In Terminal:
```bash
brew install ffmpeg
```

That's it! The app finds it automatically.

### Verify ffmpeg is working

Open the app — if you see "Ready. Add WAV files..." in the status bar (no warning about ffmpeg), you're good!

If you see "ffmpeg not found", double-check the steps above.

---

## Installing Whisper (Optional)

Whisper is only needed if you want the **Script Verification** feature (transcribing audio and comparing it to a PDF script). Skip this section if you don't need that feature.

### Windows

In Command Prompt:
```
pip install openai-whisper
```

**Note:** This downloads a large AI model (1-3 GB depending on which model size you choose in Settings). Make sure you have disk space and a decent internet connection.

### macOS

In Terminal:
```bash
pip3 install openai-whisper
```

### Choosing a Model Size

In the app, go to **Settings** → **Script Verification** → **Model**:

| Model | Size | Speed | Accuracy | Best for |
|---|---|---|---|---|
| `tiny` | 75 MB | Very fast | Lower | Quick tests |
| `base` | 140 MB | Fast | OK | Simple scripts |
| `small` | 460 MB | Medium | Good | Most languages |
| `medium` | 1.5 GB | Slower | Very good | Indian languages (recommended) |
| `large` | 3 GB | Slowest | Best | Best accuracy for all languages |

**Recommendation:** Start with `medium` for Indian languages. Use `base` if you just want to test it quickly.

---

## Troubleshooting

### "Python is not recognized" (Windows)

You didn't tick "Add Python to PATH" during installation.
- **Fix:** Uninstall Python, re-install it, and make sure you tick that checkbox on the first screen.

### "pip is not recognized" (Windows)

Try using `python -m pip` instead:
```
python -m pip install -r requirements.txt
```

### "No module named PySide6" error

The dependencies weren't installed. Run:
```
pip install -r requirements.txt
```
(or `pip3` on macOS)

### App opens but loudness checks show "ffmpeg not found"

ffmpeg is not installed or not on your PATH. See [Installing ffmpeg](#installing-ffmpeg) above.

### macOS: "Permission denied" when running build script

Make it executable:
```bash
chmod +x build_mac.sh
bash build_mac.sh
```

### The app is slow when checking many files

- Loudness checks take the longest (they call ffmpeg for each file)
- If you only need marker/verse checks, disable loudness in **Settings** (uncheck "Loudness" and "True Peak")
- Script verification with Whisper is also slow — use a smaller model or disable it when not needed

### "Qt platform plugin could not be initialized" (Linux)

Install the Qt dependencies:
```bash
sudo apt install libxcb-xinerama0 libxkbcommon-x11-0
```

---

## Quick Start Summary

| Step | Windows | macOS |
|---|---|---|
| 1. Install Python | python.org (tick "Add to PATH") | `brew install python` |
| 2. Install ffmpeg | gyan.dev → copy ffmpeg.exe | `brew install ffmpeg` |
| 3. Get the app | Download ZIP from GitHub | Download ZIP from GitHub |
| 4. Install deps | `pip install -r requirements.txt` | `pip3 install -r requirements.txt` |
| 5. Run | `python main.py` | `python3 main.py` |

---

## Need Help?

If you're stuck, open an issue on GitHub:
**https://github.com/Voxsama/BibleAudioChecker/issues**

Include:
- Your operating system (Windows 10/11, macOS version)
- What step you're on
- The exact error message you see
