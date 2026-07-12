# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ScriptureSound QC v2.0
Run: pyinstaller ScriptureSoundQC.spec
"""
import os
import sys

block_cipher = None
HERE = os.path.dirname(os.path.abspath(SPEC))

# Collect data files
datas = [
    (os.path.join(HERE, 'engine'), 'engine'),
    (os.path.join(HERE, 'gui'), 'gui'),
    (os.path.join(HERE, 'assets'), 'assets'),
]

# Bundle ffmpeg if present
binaries = []
if os.path.isfile(os.path.join(HERE, 'ffmpeg.exe')):
    binaries.append((os.path.join(HERE, 'ffmpeg.exe'), '.'))

# Icon
icon_path = os.path.join(HERE, 'icon.ico')
icon = icon_path if os.path.isfile(icon_path) else None

# Hidden imports - all engine modules + PySide6 extras
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
    'gui',
    'gui.app',
    'PySide6.QtSvg',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
]

# Exclude heavy packages that are optional (whisper/torch can be installed separately)
excludes = [
    'torch',
    'whisper',
    'openai',
    'numpy',
    'tiktoken',
    'triton',
    'sympy',
    'networkx',
    'scipy',
    'matplotlib',
    'pandas',
    'PIL',
    'cv2',
    'tensorflow',
    'torchaudio',
    'torchvision',
    'numba',
    'llvmlite',
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
    upx=True,
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
