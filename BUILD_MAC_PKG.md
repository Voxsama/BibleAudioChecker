# Build the ScriptureSoundQC Mac Installer

This guide is for the project owner or a developer creating a macOS `.pkg`.
Normal users should download an existing installer from the
[Releases page](https://github.com/Voxsama/BibleAudioChecker/releases) and read
[START_HERE.md](START_HERE.md).

## Easiest method: GitHub Actions

Use this method to build both Intel and Apple Silicon packages without owning
both types of Mac.

### 1. Push the newest project files

In GitHub Desktop:

1. Open the `BibleAudioChecker` repository.
2. Review the files under **Changes**.
3. Enter a summary such as `Update Mac installer build`.
4. Click **Commit to main**.
5. Click **Push origin**.

Do not push virtual environments, model downloads, WAV files, Bible PDFs,
`build-*`, or `dist-*` folders.

### 2. Start the build

1. Open <https://github.com/Voxsama/BibleAudioChecker>.
2. Click **Actions** near the top of the page.
3. Select **Build macOS PKG** on the left.
4. Click **Run workflow** on the right.
5. Keep the branch set to `main`.
6. Click the green **Run workflow** button.

If GitHub asks you to enable Actions, enable them for this repository and then
repeat the steps.

### 3. Download the finished packages

1. Wait for the workflow to receive a green check mark. A build can take a
   while because it packages Qt, audio libraries, and the AI runtime.
2. Open the completed workflow run.
3. Scroll to **Artifacts**.
4. Download both artifacts:
   - `ScriptureSoundQC-macOS-apple-silicon`
   - `ScriptureSoundQC-macOS-intel`
5. Extract each downloaded ZIP to find its `.pkg` file.

Running the workflow manually creates downloadable artifacts. Creating and
pushing a version tag such as `v4.0.0-beta.1` also makes the workflow attach
the packages to the matching GitHub Release. See
[GITHUB_RELEASE_GUIDE.md](GITHUB_RELEASE_GUIDE.md).

---

## Build directly on a Mac

A local build creates a package only for that Mac's processor:

- An Intel Mac creates `ScriptureSoundQC-v4.0-Beta-macOS-intel.pkg`.
- An M-series Mac creates
  `ScriptureSoundQC-v4.0-Beta-macOS-apple-silicon.pkg`.

### 1. Get the newest source

Commit and push the newest changes first. On the Mac, pull the repository or
download and extract a new source ZIP. Do not reuse an older folder containing
the dependency files that caused the Intel `llvmlite` error.

### 2. Open Terminal in the project folder

An easy method is:

1. Open Terminal.
2. Type `cd` followed by one space.
3. Drag the extracted `BibleAudioChecker-main` folder into Terminal.
4. Press Return.

The completed command will look similar to:

```bash
cd ~/Downloads/BibleAudioChecker-main
```

### 3. Install the Mac build tools

Run:

```bash
xcode-select --install
brew install python@3.12 ffmpeg
```

If `brew` is not found, install Homebrew from <https://brew.sh>, close and
reopen Terminal, and run the command again. Use Homebrew's normal default
location: `/usr/local` on Intel or `/opt/homebrew` on Apple Silicon.

### 4. Build the package

Run one command:

```bash
bash build_mac.sh
```

The script automatically:

- Detects Intel or Apple Silicon.
- Creates a private Python 3.12 build environment.
- Uses compatible prebuilt dependencies on Intel Macs.
- Bundles the application and FFmpeg.
- Creates the `.app`.
- Uses Apple's `productbuild` tool to create the `.pkg`.
- Prints the finished package's SHA-256 checksum.

Keep Terminal open until it prints `Built pkg:`. Red text during package
installation is not always the final result; use the last lines to determine
whether the build succeeded.

### 5. Find and test the package

Run:

```bash
open dist-mac
```

The `dist-mac` folder contains both the `.app` and `.pkg`. Double-click the
`.pkg`, complete the installation, and test the installed application from the
Applications folder.

The current Beta package is unsigned. On a test Mac, first try opening the app,
then use **System Settings → Privacy & Security → Open Anyway** if macOS blocks
it. Only bypass the warning for a package you built yourself or downloaded from
the official VerseVox Studio repository.

---

## Optional signing

An unsigned package is suitable for private Beta testing. Public distribution
without the normal Gatekeeper warning requires Apple Developer ID certificates
and notarization.

If the Mac already has the correct certificates, list them with:

```bash
security find-identity -v
```

Then build with the exact identity names from Keychain Access:

```bash
MAC_APP_SIGN_IDENTITY="Developer ID Application: YOUR NAME (TEAMID)" \
MAC_INSTALLER_SIGN_IDENTITY="Developer ID Installer: YOUR NAME (TEAMID)" \
bash build_mac.sh
```

Signing is not the same as notarization. The current script can sign the app
and installer but does not yet upload the package to Apple's notarization
service.

Apple's official packaging reference is
<https://developer.apple.com/documentation/xcode/packaging-mac-software-for-distribution>.

---

## Common problems

### `Failed building wheel for llvmlite`

The Mac has an old copy of the repository. Pull or download the newest source
and run `bash build_mac.sh` again. The current build script installs the last
compatible binary wheels on Intel Macs and does not compile LLVM.

### `productbuild was not found`

Run:

```bash
xcode-select --install
```

After installation finishes, close Terminal, reopen it, and build again.

### `Python 3.12 was not found`

Run:

```bash
brew install python@3.12
```

### Loudness or true-peak support is disabled

Install FFmpeg and rebuild:

```bash
brew install ffmpeg
bash build_mac.sh
```

