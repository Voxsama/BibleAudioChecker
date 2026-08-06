# Install ScriptureSoundQC

You do **not** need Python, Terminal, Command Prompt, pip, or FFmpeg when using
an official installer.

## 1. Download one file

Open the **[official download page](https://github.com/Voxsama/BibleAudioChecker/releases)**,
open the newest release, and expand **Assets**.

Choose only the file for your computer:

| Your computer | Download this |
|---|---|
| Windows 10 or 11 | `ScriptureSoundQC-Setup-*.exe` |
| Mac with an M1, M2, M3, M4, or M5 chip | `macOS-apple-silicon.pkg` |
| Mac with an Intel processor | `macOS-intel.pkg` |

Do **not** download **Source code (zip)** for a normal installation.

> If the Releases page has no installer under **Assets**, an installer has not
> been published yet. Downloading the source-code ZIP is not a replacement.

## 2. Install it

### Windows

1. Open the downloaded `.exe`.
2. If **Windows protected your PC** appears, click **More info** and then
   **Run anyway**.
3. Click **Install**, then **Finish**.

Only continue when the file came from the official download page above.

### Mac

Not sure which Mac you have? Open **Apple menu → About This Mac** and look for
**Chip** or **Processor**.

1. Open the downloaded `.pkg` and complete the installer.
2. Open **Applications → ScriptureSoundQC**.
3. If Apple blocks it, try opening it once, then go to
   **System Settings → Privacy & Security → Open Anyway**.

Only continue when the package came from the official download page above.

## 3. Check your first WAV file

1. Open ScriptureSoundQC.
2. Click **Add Files** and choose a WAV file.
3. Click **Check All**.
4. Open **Markers & Waveform** to inspect marker names and positions.
5. Correct anything that needs attention and click **Save Reviewed Copy**.

The original WAV is not overwritten.

## 4. Mastering or silence

1. Open **Settings**.
2. Enter the required LUFS and true-peak targets.
3. Choose whether silence belongs at the front, back, or both.
4. Open **Processing** and run the required operation.
5. Run **Check All** on the finished file.

Automatic verse marking is temporarily disabled in this Beta. Existing marker
checking, manual marker editing, mastering, loudness checking, and silence
processing still work. No AI model download is needed for these features.

## Need more help?

See the **[full illustrated-style written guide](INSTALL.md)** for uninstalling,
updates, security warnings, troubleshooting, and advanced source installation.

