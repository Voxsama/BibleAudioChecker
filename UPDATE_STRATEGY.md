# ScriptureSoundQC update strategy

## Recommended release flow

Use GitHub Releases to host each versioned Inno Setup installer. The built-in
ScriptureSoundQC update checker reads the repository's HTTPS Releases API in a
background thread. Users can check manually from **Processing > Check for
Updates**, or enable the startup check in **Settings > Updates**.

1. Build `ScriptureSoundQC.exe` and the versioned Setup executable.
2. Digitally sign both files with VerseVox Studio's Windows code-signing
   certificate and a trusted timestamp.
3. Publish the Setup file, SHA-256 checksum, and release notes as a GitHub
   Release. Use a semantic tag such as `v4.0.0-beta.1` or `v4.0.1`.
4. Mark test releases as GitHub prereleases. The Beta channel sees prereleases
   and stable releases; Stable sees only stable releases.
5. The app detects the newer version and asks before opening its official
   HTTPS release page. The user then downloads and runs the Inno Setup update,
   which upgrades the existing installation in place.

## Security rules

- Never replace the running executable directly.
- Never silently download or execute an unsigned installer. The current Beta
  opens the official release page and leaves installation to the user.
- Keep the EdDSA private key and the Windows signing certificate outside the
  repository and build artifacts.
- Use the same Inno Setup `AppId` for every release so updates install over the
  existing version and preserve user settings and downloaded model packs.
- Do not delete `%USERPROFILE%\.bible_audio_checker` during upgrades or normal
  uninstall unless the user explicitly chooses to remove application data.

## Before enabling one-click installation

Create a stable public release URL, obtain a Windows code-signing certificate,
choose the final version numbering policy, and add cryptographic verification
for downloaded installers. Until then, the built-in checker performs discovery
only; running the downloaded Setup file upgrades the existing installation in
place.
