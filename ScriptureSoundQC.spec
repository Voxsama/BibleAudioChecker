# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ScriptureSound QC v2.5
Run: pyinstaller ScriptureSoundQC.spec

NOTE: This bundles Whisper + torch. The .exe will be ~300-500 MB.
Build time: 5-15 minutes depending on your machine.
"""
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

block_cipher = None
HERE = os.path.dirname(os.path.abspath(SPEC))
binaries = []

# Collect data files
datas = [
    (os.path.join(HERE, 'engine'), 'engine'),
    (os.path.join(HERE, 'gui'), 'gui'),
    (os.path.join(HERE, 'assets'), 'assets'),
    (os.path.join(HERE, 'CHANGELOG.md'), '.'),
]

# These packages use lazy imports, package data, or native extensions that
# PyInstaller cannot reliably discover from static imports alone. Collecting
# all package components keeps mastering, PDF parsing, and transcription
# available in the installed application.
package_hiddenimports = []
for package in ('whisper', 'tiktoken', 'pedalboard', 'pyloudnorm',
                'scipy', 'openai'):
    package_datas, package_binaries, package_imports = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    package_hiddenimports += package_imports

# Bundle ffmpeg. build_windows.bat requires this file, so a release build
# always contains loudness and true-peak support.
if os.path.isfile(os.path.join(HERE, 'ffmpeg.exe')):
    binaries.append((os.path.join(HERE, 'ffmpeg.exe'), '.'))

# Icon
icon_path = os.path.join(HERE, 'icon.ico')
icon = icon_path if os.path.isfile(icon_path) else None

# Hidden imports - all engine modules + PySide6 extras + Whisper/torch
hiddenimports = [
    'engine',
    'engine.config',
    'engine.checker',
    'engine.bible_db',
    'engine.loudness',
    'engine.silence',
    'engine.wavio',
    'engine.wav_markers',
    'engine.waveform',
    'engine.pdf_parser',
    'engine.transcriber',
    'engine.script_verify',
    'engine.auto_marker',
    'engine.marker_writer',
    'engine.correction_memory',
    'engine.csv_markers',
    'engine.mastering',
    'gui',
    'gui.app',
    'PySide6.QtSvg',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    # Whisper + torch
    'whisper',
    'torch',
    'numpy',
    'tiktoken',
    'tiktoken_ext',
    'tiktoken_ext.openai_public',
    'numba',
    'llvmlite',
    'llvmlite.binding',
    'sympy',
    'networkx',
    'filelock',
    'regex',
    'tqdm',
    'pedalboard',
    'pyloudnorm',
    'scipy',
    'scipy.signal',
    'openai',
    'fitz',
] + package_hiddenimports

# Exclude heavy packages that are optional
# REMOVED torch/whisper from excludes — they're now bundled for full AI support
excludes = [
    'triton',
    'matplotlib',
    'pandas',
    'PIL',
    'cv2',
    'tensorflow',
    'torchaudio',
    'torchvision',
    'pytest',
    'IPython',
    'jupyter',
    'notebook',
]

a = Analysis(
    [os.path.join(HERE, 'main.py')],
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='ScriptureSoundQC',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed mode (no console)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
