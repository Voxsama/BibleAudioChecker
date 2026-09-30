# Online and offline installers

Each release builds two editions for Windows x64, macOS Apple Silicon,
macOS Intel, and Linux x86_64. Both install the same full application,
including Python, Qt, FFmpeg, mastering libraries, Whisper and MMS runtime
dependencies. **Neither includes speech/language model weights.** Download
those separately from **Processing → AI Model Packs**.

| Edition | Download | During installation |
|---|---|---|
| Online | Small launcher | Downloads and verifies the full offline package, then installs it |
| Offline | Full package | Installs the bundled dependencies without pip, apt, or internet |

The online edition reduces the initial setup file size. Its total download
and installed disk footprint are similar to the offline edition. It currently
downloads the full runtime, not individual features on demand. The build uses
CPU-only PyTorch on Windows and Linux to avoid unnecessary NVIDIA libraries;
these packages do not provide CUDA acceleration. macOS retains its native
PyTorch build.

Dependencies are resolved at **build time** using the compatibility ranges in
`requirements.txt`, and the resolved versions are published in each platform's
`*-dependencies.txt`. Both editions use those same bundled versions. The online
installer pins an exact release URL and SHA-256 hash; it does not run `pip
install --upgrade` on the user's computer. Update dependencies by building and
testing a new app release. This avoids an older app unexpectedly receiving an
incompatible library.

## Choose and install

Use the [official Releases page](https://github.com/Voxsama/BibleAudioChecker/releases).
These names apply to new builds; existing releases keep their original files.

| Platform | Online | Offline |
|---|---|---|
| Windows 10/11 x64 | `ScriptureSoundQC-Setup-Beta-Online.exe` | `ScriptureSoundQC-Setup-Beta-Offline.exe` |
| Apple Silicon Mac | `ScriptureSoundQC-Beta-macOS-apple-silicon-Online.zip` | `ScriptureSoundQC-Beta-macOS-apple-silicon-Offline.pkg` |
| Intel Mac | `ScriptureSoundQC-Beta-macOS-intel-Online.zip` | `ScriptureSoundQC-Beta-macOS-intel-Offline.pkg` |
| Linux x86_64 | `ScriptureSoundQC-Beta-Linux-x86_64-Online.sh` | `ScriptureSoundQC-Beta-Linux-x86_64-Offline.sh` |

- **Windows:** open the `.exe`. Online Setup downloads and checks the package,
  then opens the usual installation wizard. Offline Setup opens it directly.
- **macOS:** open the offline `.pkg`, or extract the online `.zip` and open the
  contained `.command`. The online launcher uses Terminal to download and
  verify the package, then opens Apple Installer. Keep Terminal open until
  you finish and close Installer. macOS may require **Privacy & Security →
  Open Anyway** for unsigned Beta downloads.
- **Linux:** in your Downloads directory, run one of the following as your
  normal user, **without sudo**:

  ```bash
  bash ScriptureSoundQC-Beta-Linux-x86_64-Online.sh
  # Or, if you downloaded the offline edition:
  bash ScriptureSoundQC-Beta-Linux-x86_64-Offline.sh
  ```

  Open **ScriptureSoundQC** from Applications afterward. The online launcher
  requires `curl`; choose Offline if it is unavailable. The frozen Linux build
  targets Ubuntu 22.04+ / Zorin 17+ x86_64 desktop systems. It still relies on
  the OS kernel, glibc and working desktop/audio drivers. Other distributions
  need testing; it is not a universal Linux package.

Close the app before updating. Both editions replace the same installed app;
switching editions does not require uninstalling first. A failed download or
checksum check stops before the downloaded installer runs. Retry the online
launcher or download the offline edition. No installer downloads model weights
or submits your audio. Online AI review and initial model downloads still
require internet even after an offline installation.

Linux installs into `${XDG_DATA_HOME:-$HOME/.local/share}/scripturesound-qc/app`
and registers `applications/scripturesound-qc.desktop` beneath that same data
directory. To uninstall, close the app and remove those two items. Settings
under `~/.bible_audio_checker` and downloaded model packs remain. The existing
`setup_linux.sh` / `run_linux.sh` workflow remains available for source users.

## Build and publish

The **Build installers** GitHub Actions workflow builds all four platform
targets, runs the packaged runtime check, and produces both editions. Tagged
builds publish them together with checksums and dependency lists. Windows and
Linux additionally exercise offline installation on the runner. Untagged/PR
builds use an intentionally unpublished URL: their offline artifacts work,
but online artifacts are for inspection until rebuilt with a real release URL.

For a local build, use Python 3.12 and the native platform:

```text
Windows: build_windows.bat, then build_installer.bat
macOS:   bash build_mac.sh
Linux:   bash build_linux.sh
```

Windows requires FFmpeg in the project folder and Inno Setup 6.5+; macOS and
Linux require FFmpeg on PATH. Linux build hosts also need the Qt desktop
libraries listed in `.github/workflows/build-installers.yml`. Build Linux on
Ubuntu 22.04 for the stated compatibility baseline. Building on a newer Linux
system can raise the minimum glibc version required by the resulting app.

Then generate the online launcher from the completed offline artifact, for
example (replace the tag with the release you will actually publish):

```bash
python3 scripts/build_online_installer.py \
  --platform linux \
  --payload dist-linux/ScriptureSoundQC-Beta-Linux-x86_64-Offline.sh \
  --base-url https://github.com/Voxsama/BibleAudioChecker/releases/download/v4.0.1-beta.1
```

Use `--platform windows` with the `.exe` in `dist/installer`, or `--platform
macos` with the `.pkg` in `dist-mac`. On Windows use `python` and place the
arguments on one line. `--iscc` can specify a custom compiler path.

Upload the offline payload and online launcher **from the same build**, plus
their `.sha256` files. Keep published payloads unchanged: replacing an offline
file breaks the hash embedded in existing online installers. Publish fixes
under a new tag; CI deliberately does not overwrite release assets.

Before publishing, try both editions on a clean target machine, try Offline
with networking disabled, and verify launch, WAV checks, marker editing,
mastering, model-pack downloads and uninstall. Also verify Online's retry
behavior with the actual hosted assets. CI cannot exercise a release download
before its assets are published.
