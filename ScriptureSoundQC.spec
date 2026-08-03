# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for ScriptureSound QC v4.0
Run: pyinstaller ScriptureSoundQC.spec

NOTE: This bundles Whisper + torch. The .exe will be ~300-500 MB.
Build time: 5-15 minutes depending on your machine.
"""
import os
import shutil
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
HERE = os.path.dirname(os.path.abspath(SPEC))
IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'

# Collect data files
datas = [
    (os.path.join(HERE, 'engine'), 'engine'),
    (os.path.join(HERE, 'gui'), 'gui'),
    (os.path.join(HERE, 'assets'), 'assets'),
    (os.path.join(HERE, 'CHANGELOG.md'), '.'),
]

# Collect whisper's assets (mel filters, multilingual tokenizer, etc.)
try:
    datas += collect_data_files('whisper')
except Exception:
    pass

# Collect tiktoken data
try:
    datas += collect_data_files('tiktoken_ext')
except Exception:
    pass

# Runtime code/configuration for optional Meta MMS language packs. Model
# weights remain external downloads and are never bundled in the executable.
try:
    datas += collect_data_files('transformers')
except Exception:
    pass

# Indic transliteration loads its script maps and scheme definitions from
# JSON/TOML files at runtime. Collecting Python modules alone is not enough.
try:
    indic_datas = collect_data_files('indic_transliteration')
    required_indic_map = 'language_code_to_script.json'
    if not any(
            os.path.basename(source) == required_indic_map
            for source, _destination in indic_datas):
        raise RuntimeError(
            'Required Indic script map was not found during packaging.')
    datas += indic_datas
except Exception as exc:
    raise RuntimeError(
        'Could not bundle Indic transliteration data: %s' % exc)

# Bundle ffmpeg if present
binaries = []
if IS_WINDOWS and os.path.isfile(os.path.join(HERE, 'ffmpeg.exe')):
    binaries.append((os.path.join(HERE, 'ffmpeg.exe'), '.'))
elif IS_MACOS:
    mac_ffmpeg = os.path.join(HERE, 'ffmpeg')
    if not os.path.isfile(mac_ffmpeg):
        mac_ffmpeg = shutil.which('ffmpeg') or ''
    if mac_ffmpeg:
        binaries.append((mac_ffmpeg, '.'))

# Icon
icon_path = os.path.join(
    HERE, 'icon.icns' if IS_MACOS else 'icon.ico')
icon = icon_path if os.path.isfile(icon_path) else None
version_path = os.path.join(HERE, 'version_info.txt')

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
    'engine.transcription_cache',
    'engine.script_verify',
    'engine.auto_marker',
    'engine.marker_writer',
    'engine.csv_markers',
    'engine.correction_memory',
    'engine.alignment_backends',
    'engine.calibration',
    'engine.exports',
    'engine.marker_editor',
    'engine.model_packs',
    'engine.mms_pack',
    'engine.mms_transcriber',
    'engine.language_resolution',
    'engine.phonetic',
    'engine.project',
    'engine.review',
    'engine.script_cache',
    'engine.mastering',
    'engine.updates',
    'gui',
    'gui.app',
    'PySide6.QtSvg',
    'PySide6.QtCore',
    'PySide6.QtGui',
    'PySide6.QtWidgets',
    'PySide6.QtMultimedia',
    # Whisper + torch
    'whisper',
    'torch',
    'numpy',
    'scipy',
    'scipy.signal',
    'pedalboard',
    'pyloudnorm',
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
    'transformers',
    'transformers.models.wav2vec2',
    'transformers.models.wav2vec2.configuration_wav2vec2',
    'transformers.models.wav2vec2.feature_extraction_wav2vec2',
    'transformers.models.wav2vec2.modeling_wav2vec2',
    'transformers.models.wav2vec2.processing_wav2vec2',
    'transformers.models.wav2vec2.tokenization_wav2vec2',
    'huggingface_hub',
    'safetensors',
    'safetensors.torch',
    'soundfile',
    'yaml',
]

# Cross-script Assamese/Indic phonetic alignment is imported lazily.
try:
    hiddenimports += collect_submodules('indic_transliteration')
except Exception:
    pass

try:
    hiddenimports += collect_submodules('transformers.models.wav2vec2')
except Exception:
    pass

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
    [],
    exclude_binaries=True,
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
    codesign_identity=(
        os.environ.get('MAC_APP_SIGN_IDENTITY') if IS_MACOS else None),
    entitlements_file=None,
    icon=icon,
    version=(version_path if IS_WINDOWS else None),
)

# One-folder installations start much faster than a 400+ MB one-file bundle:
# the runtime no longer has to unpack Qt, Torch, and Whisper on every launch.
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ScriptureSoundQC',
)

if IS_MACOS:
    app = BUNDLE(
        coll,
        name='ScriptureSoundQC.app',
        icon=icon,
        bundle_identifier='studio.versevox.scripturesoundqc',
        info_plist={
            'CFBundleDisplayName': 'ScriptureSoundQC',
            'CFBundleName': 'ScriptureSoundQC',
            'CFBundleShortVersionString': '4.0.0',
            'CFBundleVersion': '4.0.0',
            'LSMinimumSystemVersion': '12.0',
            'NSHighResolutionCapable': True,
        },
    )
