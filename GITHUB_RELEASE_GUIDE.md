# Publishing ScriptureSoundQC updates

The in-app checker reads releases from:

`https://github.com/Voxsama/BibleAudioChecker/releases`

## 1. Upload the project source

Do not commit `dist-*`, `build-*`, model weights, or `ffmpeg.exe`. They are
excluded by `.gitignore`. The repository must contain the source, the `.spec`
file, `requirements.txt`, and `.github/workflows/build-installers.yml`.

If this folder is not already a Git checkout, run these commands once from the
project folder after creating the empty GitHub repository:

```powershell
git init
git branch -M main
git remote add origin https://github.com/Voxsama/BibleAudioChecker.git
git add .
git status --short
git commit -m "ScriptureSoundQC Beta"
git push -u origin main
```

Review the `git status --short` list before committing. It should contain only
source, documentation, icons, tests, installer scripts, and the GitHub
workflow. It must not contain `.venv`, `build-*`, `dist-*`, `tmp`, model
weights, Bible PDFs/audio, `ffmpeg.exe`, API keys, or generated installers.
Do not upload the whole local folder through the GitHub website because web
uploads do not apply your local `.gitignore`; use Git as shown above.

For later source updates:

```powershell
git add .
git commit -m "Describe the update"
git push
```

## 2. Build and publish a Beta

Build the Windows installer locally with `build_windows.bat`, followed by
`build_installer.bat`. Commit and push the source, then create and push a tag:

```powershell
git tag v4.0.0-beta.1
git push origin v4.0.0-beta.1
```

The tag starts **Build installers**, which builds Windows x64, macOS Apple
Silicon, macOS Intel, and Linux x86_64. It publishes Online and Offline editions,
checksums and dependency version lists together after all targets succeed.

For a test build without a tag, use **GitHub → Actions → Build installers →
Run workflow** and download the artifacts. Untagged online installers point
to an unpublished test URL and must not be distributed to users.

See [Installer editions](INSTALLER_EDITIONS.md#build-and-publish) for local
builds and validation. Published offline payloads must not be replaced: their
hashes are embedded in the online installers. Publish corrections under a new
tag. Keep **Set as a pre-release** enabled for Beta tags.

At the top of every release description, include:

```markdown
New user? Read the [short Install and Start guide](https://github.com/Voxsama/BibleAudioChecker/blob/main/START_HERE.md).

- Choose Online for a small downloader or Offline for bundled dependencies.
- Windows: choose the Setup `.exe`.
- Mac: choose `macOS-apple-silicon` or `macOS-intel`; Online is a ZIP, Offline a PKG.
- Linux: choose `Linux-x86_64` and run the `.sh` with bash.
- Language models are separate downloads in both editions.
- Do not download Source code for a normal installation.
```

## 3. Publish the next update

Increase the app/build version, rebuild, commit, and use a higher tag such as
`v4.0.0-beta.2`, `v4.0.1-beta.1`, or a stable `v4.0.1`. The installed app will
compare the tags and offer the newer eligible release.
