# ScriptureSound QC — notes for AI tools and new contributors

Desktop app (PySide6) that checks Bible audio recordings: WAV spec, silence,
verse markers, loudness, mastering, optional AI review via OpenRouter.

## Layout
- `engine/` — pure Python, no Qt. One module per concern (checker, mastering,
  auto_marker, model_packs, ...). `engine/crash_report.py` logs every error with
  the section (file:function:line) that raised it.
- `gui/` — one module per screen: `main_window.py`, `settings_dialog.py`,
  `model_pack_dialog.py`, `quick_start_dialog.py`, `ai_review.py`,
  `waveform_view.py`, `workers.py` (QThread workers), `theme.py` (colours,
  stylesheet, app constants). `gui/app.py` only builds the QApplication.
- `tests/` — `unittest` files plus four script-style self-checks
  (`python -m tests.test_engine` etc.).
- Logs live beside `~/.bible_audio_checker/config.json`: `errors.log`
  (exceptions) and `crash.log` (segfaults, reported at next start).

## Running tests
Use the Linux venv created by `setup_linux.sh` (Python 3.10–3.12):

```sh
.venv-linux/bin/python -m unittest discover -s tests -p 'test_*.py' -v
for t in test_engine test_mastering_validation test_production_features test_reworked_features; do
  .venv-linux/bin/python -m tests.$t; done
```

GUI tests run offscreen. If this editor is a Flatpak (VS Code), the venv is
only usable on the host: prefix commands with `flatpak-spawn --host`.

## Rules
- Keep engine free of Qt imports. Keep each GUI screen in its own module.
- Never swallow exceptions silently; log them with `logging.getLogger(__name__)`.
- Do not edit installer scripts (`installer/`, `build_*.sh`, `*.bat`, `*.spec`)
  without running the installer-edition tests.
